#!/usr/bin/env python3
r"""Randomizer core: load a Summoner PS2 ISO, transform it, write a new ISO.

File-based on purpose: the N100 has 8 GB total and these images are 1.2-3 GB, so
nothing here ever holds a whole ISO in memory. We only ever touch the TABLES.VPP
region (~7 MB).

Facts this relies on (see notes/summoner-findings.md):
  * Every .VPP starts with magic 0x51890ACE. Layout: 16-byte header, zero pad to
    0x800, then count x 64-byte records (name[48], 3 reserved u32, u32 size),
    then entry data, packed sequentially with no padding between entries.
  * The data area does NOT start at a fixed 0x1000: it starts at the next 0x800
    boundary after the table of contents, and the TOC is count*64 bytes. For
    TABLES.VPP that is 527 records ending at 0x8BC0, so its data starts at 0x9000 -
    not 0x1000. Reading from 0x1000 shifted every entry in the archive by 32 KB and
    truncated the tail, which is where the 52 level files (and all 218 door
    triggers) live. Verified against the disc: with the rule below every entry's
    padding is clean zeros and the last entry ends exactly at the declared archive
    size, for all nine archives in the image.
  * TABLES.VPP entries are arbitrary slices of one continuous text stream, so all
    transforms operate on the reassembled blob and MUST be size-preserving.
  * Entry boundaries are 0x800-aligned in the file but the blob is the *tight*
    concatenation of the slices, so a transform never sees the padding and nothing
    has to be aware of it - only the per-entry offsets do.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

try:
    import binary  # binary layer: patches the executable inside the ISOfile
    _HAVE_BINARY = True
except ImportError:  # keeps the table layer usable on its own
    binary = None
    _HAVE_BINARY = False

VPP_MAGIC = 0x51890ACE
HEADER_PAD = 0x800       # the table of contents starts here
REC_SIZE = 64
ENTRY_ALIGN = 0x800      # entry data is 0x800-aligned inside the archive


def _align_up(value: int, align: int = ENTRY_ALIGN) -> int:
    return (value + align - 1) & ~(align - 1)


def data_start(count: int) -> int:
    """Where the first entry begins: after the TOC, on the next 0x800 boundary.

    Not a constant. A fixed 0x1000 is only right while the TOC fits below it, and for
    TABLES.VPP's 527 records it does not - the TOC runs to 0x8BC0 and the real data
    starts at 0x9000. Assuming 0x1000 mis-reads every entry in the archive and loses
    the last ~620 KB of it.
    """
    return _align_up(HEADER_PAD + count * REC_SIZE)


# --------------------------------------------------------------------------- #
# VPP over a file handle
# --------------------------------------------------------------------------- #
@dataclass
class VppEntry:
    name: str
    size: int
    offset: int          # relative to the archive base


class VppFile:
    def __init__(self, fh, base: int):
        self.fh = fh
        self.base = base
        fh.seek(base)
        head = fh.read(16)
        magic, self.version, self.count, self.total_size = struct.unpack("<IIII", head)
        if magic != VPP_MAGIC:
            raise ValueError(f"no VPP magic at 0x{base:X}")
        fh.seek(base + HEADER_PAD)
        toc = fh.read(self.count * REC_SIZE)
        self.entries: list[VppEntry] = []
        self.data_start = data_start(self.count)
        off = self.data_start
        for i in range(self.count):
            raw = toc[i * REC_SIZE:(i + 1) * REC_SIZE]
            name = raw[:48].split(b"\x00")[0].decode("latin-1")
            size = struct.unpack_from("<I", raw, 60)[0]
            self.entries.append(VppEntry(name, size, off))
            off = _align_up(off + size)

    def blob(self) -> bytes:
        out = bytearray()
        for e in self.entries:
            self.fh.seek(self.base + e.offset)
            out += self.fh.read(e.size)
        return bytes(out)

    def ranges(self):
        """(iso_offset, size, name) per entry."""
        for e in self.entries:
            yield self.base + e.offset, e.size, e.name


def find_all_vpps(fh, chunk_cap: int = 64 << 20) -> list[int]:
    """Locate all plausible VPP bases without loading the image."""
    magic = struct.pack("<I", VPP_MAGIC)
    bases, pos, size = [], 0, fh.seek(0, 2)
    fh.seek(0)
    overlap = 8
    while pos < size:
        fh.seek(pos)
        buf = fh.read(min(chunk_cap, size - pos))
        if not buf:
            break
        start = 0
        while True:
            i = buf.find(magic, start)
            if i < 0:
                break
            abs_pos = pos + i
            try:
                fh.seek(abs_pos + 4)
                ver, cnt = struct.unpack("<II", fh.read(8))
                if ver == 1 and 0 < cnt < 20000:
                    bases.append(abs_pos)
            except struct.error:
                pass
            start = i + 4
        if len(buf) < chunk_cap:
            break
        pos += len(buf) - overlap
    fh.seek(0)
    return sorted(set(bases))


_BASE_CACHE: dict[tuple, list[int]] = {}
_BASE_CACHE_FILE = Path(__file__).resolve().parent / "scan-cache.json"
_BASE_CACHE_LOADED = False


def _cache_load():
    """Load the persisted VPP-base map once per process.

    Scanning a 1.2 GB (or 3.1 GB) image for VPP magic takes real time, and it is
    deterministic, so it is worth keeping across restarts. Keyed on path + size +
    mtime, so a changed or replaced image can never serve a stale answer.
    """
    global _BASE_CACHE_LOADED
    if _BASE_CACHE_LOADED:
        return
    _BASE_CACHE_LOADED = True
    try:
        data = json.loads(_BASE_CACHE_FILE.read_text("utf-8"))
        for k, v in (data.get("entries") or {}).items():
            _BASE_CACHE[tuple(json.loads(k))] = list(v)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass


def _cache_save():
    try:
        entries = {json.dumps(list(k)): v for k, v in _BASE_CACHE.items()}
        tmp = _BASE_CACHE_FILE.with_name(_BASE_CACHE_FILE.name + ".tmp")
        tmp.write_text(json.dumps({"entries": entries}), "utf-8")
        tmp.replace(_BASE_CACHE_FILE)
    except OSError:
        pass


def find_all_vpps_cached(fh, path: Path, chunk_cap: int = 64 << 20) -> list[int]:
    """find_all_vpps + a persistent one-entry-per-image cache.

    The cached value is only the VPP base offsets, which are deterministic for a
    given image, so this cannot affect output bytes.
    """
    _cache_load()
    try:
        st = path.stat()
        key = (str(Path(path).resolve()), st.st_size, st.st_mtime_ns)
    except OSError:
        return find_all_vpps(fh, chunk_cap)
    hit = _BASE_CACHE.get(key)
    if hit is not None:
        fh.seek(0)
        return hit
    bases = find_all_vpps(fh, chunk_cap)
    _BASE_CACHE.clear()
    _BASE_CACHE[key] = bases
    _cache_save()
    return bases


def pick_tables(fh, bases) -> tuple[int, VppFile] | tuple[None, None]:
    """TABLES.VPP is the VPP whose stream looks like the script blob."""
    for b in bases:
        try:
            v = VppFile(fh, b)
        except ValueError:
            continue
        if v.count == 527:
            return b, v
        fh.seek(b + v.data_start)
        sample = fh.read(512)
        if b"$Door" in sample or b"#Doors" in sample or b"$Level" in sample:
            return b, v
    return None, None


# --------------------------------------------------------------------------- #
# Transforms — every one must preserve blob length exactly
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    transform: str
    changed: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self):
        return {"transform": self.transform, "changed": self.changed, "notes": self.notes}


def _shuffle_matches(blob: bytes, pattern: bytes, rng: Random, rep: Report,
                     group: int = 1, label: str = "refs",
                     exclude: "set[bytes] | None" = None) -> bytes:
    """Shuffle capture-group values among matches of equal length.

    `exclude` names are PINNED: they keep their own value AND are removed from the shuffle pool, so
    nothing else lands on them either. This protects records the ENGINE references by hardcoded
    name (e.g. the burning-village fire barrier "invis-door02", which the executable removes via a
    literal string - renaming its record soft-locks the opening). See
    docs/lab/ANALYSIS-invis-door02-fire-barrier.md.
    """
    hits = list(re.finditer(pattern, blob))
    if not hits:
        rep.notes.append(f"no {label} found")
        return blob
    excl = exclude or set()
    by_len: dict[int, list] = {}
    for m in hits:
        by_len.setdefault(len(m.group(group)), []).append(m)
    out = bytearray(blob)
    pinned = 0
    for ln, ms in by_len.items():
        # only the movable matches take part in the shuffle; pinned ones stay put
        movable = [m for m in ms if m.group(group) not in excl]
        pinned += len(ms) - len(movable)
        if len(movable) < 2:
            continue
        vals = [m.group(group) for m in movable]
        shuf = vals[:]
        rng.shuffle(shuf)
        for m, v in zip(movable, shuf):
            if v != m.group(group):
                rep.changed += 1
            out[m.start(group):m.end(group)] = v
    note = f"{len(hits)} {label} across {len(by_len)} length classes"
    if pinned:
        note += f"; {pinned} pinned (engine-referenced, protected)"
    rep.notes.append(note)
    return bytes(out)


def t_lock_shuffle(blob, rng):
    """Shuffle +Locked: values among all doors."""
    rep = Report("lock_shuffle")
    hits = list(re.finditer(rb"\+Locked:\s*([0-9]+\.[0-9]+)", blob))
    if not hits:
        rep.notes.append("no +Locked fields found")
        return blob, rep
    widths = {len(m.group(1)) for m in hits}
    if len(widths) != 1:
        rep.notes.append(f"mixed widths {sorted(widths)} -> refused to stay size-safe")
        return blob, rep
    vals = [m.group(1) for m in hits]
    shuf = vals[:]
    rng.shuffle(shuf)
    out = bytearray(blob)
    for m, v in zip(hits, shuf):
        out[m.start(1):m.end(1)] = v
    rep.changed = sum(1 for a, b in zip(vals, shuf) if a != b)
    rep.notes.append(f"{len(hits)} +Locked fields, width {widths.pop()}")
    return bytes(out), rep


# Door records the ENGINE removes/toggles by hardcoded name (see the burning-village fire barrier:
# the executable calls remove_object("invis-door02") with a literal string). Renaming these records
# means the hardcoded call no longer matches -> the object is never removed -> the opening
# soft-locks. They are PINNED out of every name shuffle. Proof + call site:
# docs/lab/ANALYSIS-invis-door02-fire-barrier.md.
ENGINE_PINNED_DOOR_NAMES = {
    b"invis-door01", b"invis-door02", b"invis-door03",
}


def t_door_name_shuffle(blob, rng):
    """Shuffle $Door names among equal lengths, pinning engine-referenced doors in place."""
    rep = Report("door_name_shuffle")
    return _shuffle_matches(blob, rb'\$Door:\s*"([^"]+)"', rng, rep,
                            label="$Door names", exclude=ENGINE_PINNED_DOOR_NAMES), rep


def t_door_sound_shuffle(blob, rng):
    """Shuffle door sound filenames among equal lengths."""
    rep = Report("door_sound_shuffle")
    return _shuffle_matches(blob, rb'"(Doors\\[^"]+)"', rng, rep,
                            label="door sounds"), rep


def t_npc_name_shuffle(blob, rng):
    """Shuffle $Character: values among equal lengths (visual chaos)."""
    rep = Report("npc_character_shuffle")
    return _shuffle_matches(blob, rb'\$Character:\s*"([^"]+)"', rng, rep,
                            label="$Character values"), rep


def t_model_ref_shuffle(blob, rng):
    """Shuffle .mvf model references among equal lengths."""
    rep = Report("model_ref_shuffle")
    return _shuffle_matches(blob, rb'"([A-Za-z0-9_\-]+\.mvf)"', rng, rep,
                            label=".mvf refs"), rep


def t_cutscene_order_shuffle(blob, rng):
    """Shuffle $Cutscene: names among equal lengths."""
    rep = Report("cutscene_shuffle")
    return _shuffle_matches(blob, rb'\$Cutscene:\s*"([^"]+)"', rng, rep,
                            label="$Cutscene names"), rep


# --------------------------------------------------------------------------- #
# Pacing transforms — every one is same-width so the blob length never changes
# --------------------------------------------------------------------------- #
XP_RE = re.compile(rb"(\+AddXP:\s*)(\d+)")
CAP_RE = re.compile(rb"(\+Levelcap:\s*)(\d+)")
CUT_RE = re.compile(rb"(\$)Cutscene(\s*:)")


def _remap_same_width(digits: bytes, factor: int, floor_val: int | None = None) -> bytes:
    """Scale a decimal literal but keep the exact same digit count.

    We cannot lengthen the field (the blob is a fixed-offset slice stream), so
    instead of multiplying by 10 we push the value toward the top of its own
    digit range. 15000 -> 95000 at factor 9, 3-digit 100 -> 900, and so on.
    """
    w = len(digits)
    hi = int("9" * w)
    val = int(digits)
    new = min(hi, val * factor)
    if floor_val is not None and new < floor_val:
        new = min(hi, floor_val)
    return str(new).zfill(w).encode()


def t_xp_boost(blob, rng, factor=9):
    """Scale every +AddXP: reward up within its own field width. Kills the grind."""
    rep = Report("xp_boost")
    hits = list(XP_RE.finditer(blob))
    if not hits:
        rep.notes.append("no +AddXP fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        new = _remap_same_width(m.group(2), factor)
        if new != m.group(2):
            rep.changed += 1
        out[m.start(2):m.end(2)] = new
    vals = [int(m.group(2)) for m in hits]
    rep.notes.append(f"{len(hits)} rewards, factor {factor}")
    rep.notes.append(f"min {min(vals)} -> {min(int(_remap_same_width(str(v).encode(), factor)) for v in vals)}")
    rep.notes.append("in-game effect unverified — needs a boot test")
    return bytes(out), rep


def t_levelcap_raise(blob, rng, target=50):
    """Push +Levelcap: values up, same width, so creatures scale with you."""
    rep = Report("levelcap_raise")
    hits = list(CAP_RE.finditer(blob))
    if not hits:
        rep.notes.append("no +Levelcap fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        d = m.group(2)
        w = len(d)
        cap = min(int("9" * w), max(int(d), target if target < 10 ** w else 9 * (10 ** (w - 1))))
        new = str(cap).zfill(w).encode()
        if new != d:
            rep.changed += 1
        out[m.start(2):m.end(2)] = new
    rep.notes.append(f"{len(hits)} level caps raised toward {target}")
    rep.notes.append("in-game effect unverified")
    return bytes(out), rep


def _remap_down(digits: bytes, divisor: int = 3, keep_width: bool = True) -> bytes:
    """Shrink a decimal literal within its own field width.

    '15000' / 3 -> '05000'. Width is preserved so the blob never shifts; a value
    that divides below its width is zero-padded rather than shortened.
    """
    w = len(digits)
    val = int(digits)
    new = max(1, val // max(1, divisor))
    if keep_width:
        new = min(new, int("9" * w))
        return str(new).zfill(w).encode()
    return str(new).encode()


def t_xp_nerf(blob, rng, divisor=3):
    """Scale every +AddXP: reward DOWN. Levelling gets slow on purpose.

    Roguelike pressure: you cannot out-level the content, so encounters stay
    dangerous for the whole run instead of becoming trivial. Same-width, so the
    blob length never changes.
    """
    rep = Report("xp_nerf")
    hits = list(XP_RE.finditer(blob))
    if not hits:
        rep.notes.append("no +AddXP fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        new = _remap_down(m.group(2), divisor)
        if new != m.group(2):
            rep.changed += 1
        out[m.start(2):m.end(2)] = new
    rep.notes.append(f"{len(hits)} rewards divided by {divisor}")
    rep.notes.append("in-game effect unverified")
    return bytes(out), rep


VALUE_RE = re.compile(rb"(\$Value:\s*)(\d+)")
GP_RE = re.compile(rb"(\+AdjustGP:\s*)(-?\d+)")


# --------------------------------------------------------------------------- #
# Progression control — XP, levelling, permadeath
# --------------------------------------------------------------------------- #
def _scale_width(digits: bytes, percent: int) -> bytes:
    """Scale a decimal literal by a percentage, staying inside its field width.

    percent=100 leaves it alone, 300 triples it, 33 cuts it to a third. Clamped to
    the value's own digit count so the blob never shifts.
    """
    w = len(digits)
    hi = int("9" * w)
    val = int(digits)
    if val == 0:
        return digits
    new = (val * percent) // 100
    new = max(1, min(hi, new))
    return str(new).zfill(w).encode()


def t_xp_scale(blob, rng, percent=100):
    """Scale EVERY +AddXP: reward by a percentage. The XP dial.

    100 = vanilla, 300 = triple, 33 = a third. Deterministic by design — difficulty
    pressure should not be a dice roll.
    """
    rep = Report("xp_scale")
    hits = list(XP_RE.finditer(blob))
    if not hits:
        rep.notes.append("no +AddXP fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        new = _scale_width(m.group(2), percent)
        if new != m.group(2):
            rep.changed += 1
        out[m.start(2):m.end(2)] = new
    rep.notes.append(f"{len(hits)} XP rewards scaled to {percent}% of vanilla")
    rep.notes.append("deterministic — identical on every seed")
    return bytes(out), rep


def t_levelcap_set(blob, rng, percent=100):
    """Scale every +Levelcap: by a percentage. The levelling dial.

    100 = vanilla, 200 = creatures scale twice as high, 50 = they stop growing early.
    """
    rep = Report("levelcap_set")
    hits = list(CAP_RE.finditer(blob))
    if not hits:
        rep.notes.append("no +Levelcap fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        new = _scale_width(m.group(2), percent)
        if new != m.group(2):
            rep.changed += 1
        out[m.start(2):m.end(2)] = new
    rep.notes.append(f"{len(hits)} level caps scaled to {percent}%")
    rep.notes.append("deterministic — identical on every seed")
    return bytes(out), rep


# Revive references, and WHERE they matter:
#   $Action: "spell_revive"   x6  — the ability itself. Disabling this is the real lever.
#   "Revive Scroll"           x11 — but only 2 are $Item: pickups; 2 are the item's own
#                                   $Name definition and 7 are "you found" +Messagebox text.
#
# Renaming ALL ELEVEN is a no-op: the definition and its references get renamed together,
# so the item still works and is merely called something else. To actually stop the item
# being obtainable, rename only the GRANT sites, leaving the definition intact so the
# grant points at a name that no longer exists.
REVIVE_ACTION_RE = re.compile(rb'(\$Action:\s*")(spell_revive)(")')
REVIVE_GRANT_RE = re.compile(rb'((?:\$Item|\+Gain Item):\s*")(Revive Scroll)(")')


def t_permadeath(blob, rng, block_ability=True, block_items=True):
    """Make death stick by removing the revive paths. Both layers are table-side.

    block_ability — renames `$Action: "spell_revive"`, which is the revive capability
    itself. This is the reliable lever.

    block_items — renames ONLY the grant sites ($Item: / +Gain Item:), leaving the
    item's own $Name definition alone, so the pickup points at a name that no longer
    exists. Renaming every occurrence would be cosmetic (definition and references
    rename together and the item keeps working) which is why this is restricted.

    RISKY in both cases: the engine looks actions and items up by name, so an unknown
    name may be quietly ignored (intended) or may error (not intended). Same byte
    length throughout and fully reversible. Untested in game.
    """
    rep = Report("permadeath")
    out = bytearray(blob)
    if block_ability:
        hits = list(REVIVE_ACTION_RE.finditer(bytes(out)))
        for m in hits:
            out[m.start(2):m.end(2)] = b"spell_none__"       # 12 -> 12
            rep.changed += 1
        rep.notes.append(f"{len(hits)} revive abilities disabled")
    if block_items:
        hits = list(REVIVE_GRANT_RE.finditer(bytes(out)))
        for m in hits:
            out[m.start(2):m.end(2)] = b"Inert Scrap  "       # 13 -> 13
            rep.changed += 1
        rep.notes.append(f"{len(hits)} revive item grants orphaned (definition left intact)")
    if not rep.changed:
        rep.notes.append("no revive references found")
    rep.notes.append("RISKY: unknown action/item name may error rather than be ignored")
    rep.notes.append("size-preserving and reversible; untested in game")
    return bytes(out), rep


def t_economy_squeeze(blob, rng, factor=9):
    """Squeeze the economy: prices driven up, gold rewards driven down.

    Prices are pushed toward the top of their own digit width and +AdjustGP
    toward the bottom. Nothing to buy, nothing to buy it with — so shops stop
    being a source of safety and you live off what you find.
    """
    rep = Report("economy_squeeze")
    out = bytearray(blob)
    hits = list(VALUE_RE.finditer(blob))
    for m in hits:
        new = _remap_same_width(m.group(2), factor)
        if new != m.group(2):
            rep.changed += 1
        out[m.start(2):m.end(2)] = new
    rep.notes.append(f"{len(hits)} prices pushed up (factor {factor})")

    out = bytes(out)
    gp = list(GP_RE.finditer(out))
    if gp:
        buf = bytearray(out)
        for m in gp:
            d = m.group(2)
            if not d.isdigit():
                continue
            new = _remap_down(d, factor)
            if new != d:
                rep.changed += 1
            buf[m.start(2):m.end(2)] = new
        out = bytes(buf)
        rep.notes.append(f"{len(gp)} gold rewards cut")
    rep.notes.append("in-game effect unverified")
    return out, rep


def t_cutscene_bypass(blob, rng):
    """Neuter cutscene triggers by breaking the $Cutscene token in place.

    Size-preserving by construction: we overwrite one byte of the token rather
    than deleting lines. Restoring is a single-byte revert. This is the biggest
    wall-clock saving in the game and it is trivially reversible.
    """
    rep = Report("cutscene_bypass")
    hits = list(CUT_RE.finditer(blob))
    if not hits:
        rep.notes.append("no $Cutscene tokens found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        i = m.start(1) + 1  # the 'C'
        out[i] = ord("X")   # $Cutscene -> $Xutscene
        rep.changed += 1
    rep.notes.append(f"{len(hits)} $Cutscene tokens neutered ($Cutscene -> $Xutscene)")
    rep.notes.append("size-preserving, single-byte revert, in-game effect unverified")
    return bytes(out), rep


def t_material_shuffle(blob, rng):
    """Shuffle material names — the colour lever the table layer exposes.

    The field is $Default Material: (356 records), not $Material as first assumed,
    so the original pattern silently matched nothing.
    """
    rep = Report("material_shuffle")
    out = blob
    for pat, label in ((rb'\$[A-Za-z ]*Material\s*:\s*"([^"]+)"', "$Material"),
                       (rb'\$Mat\s*:\s*"([^"]+)"', "$Mat")):
        out2 = _shuffle_matches(out, pat, rng, rep, label=label)
        out = out2
    return out, rep


# --------------------------------------------------------------------------- #
# World / progression transforms
# --------------------------------------------------------------------------- #
RING_FLAG = b"ready_for_end"

# +Event: flags exactly as long as "ready_for_end" (13 chars), so they can be
# renamed to it in place. Found by surveying the corpus, not guessed.
RING_HUNT_ANCHORS = [
    "act3_finished", "die_haidi_die", "gesualdo_done", "got_map_quest",
    "ikaemostopint", "no_more_korel", "unhide_cerval", "unhide_luvela",
    "unhide_madog2", "unhide_statue", "unhide_tathal",
]
# anchors that read like progression milestones — safest default
RING_HUNT_SAFE_ANCHORS = ["act3_finished", "gesualdo_done", "no_more_korel", "got_map_quest"]

# Anchors that sit directly beside a ring acquisition in the script. Renaming all of
# these to ready_for_end means the ending can trigger on ANY of the rings they cover:
#   act3_finished  -> Ring of Jade, Ring of the Four Winds
#   ikaemostopint  -> Ring of Fire, Ring of Stone
#   unhide_luvela  -> Ring of Darkness, Ring of Forest
#   unhide_tathal  -> Ring of Fire, Ring of Water
# That is 7 of the 8 rings. Only the Ring of Light has no adjacent 13-character anchor.
RING_HUNT_RING_ANCHORS = ["act3_finished", "ikaemostopint", "unhide_luvela", "unhide_tathal"]
RING_HUNT_ANCHOR_SETS = {
    "any-ring": RING_HUNT_RING_ANCHORS,
    "safe": RING_HUNT_SAFE_ANCHORS,
}

EVENT_RE = re.compile(rb'(\+Event:\s*")([^"]+)(")')


def t_ring_hunt(blob, rng, anchor=None, count=1, safe_only=True):
    """Open the Forge of Urath at a chosen event instead of full ring collection.

    The game has no ring counter. The ending is gated by one flag, ready_for_end,
    and gamestage 21 is defined as that flag. ready_for_end is exactly 13
    characters, so any other 13-character +Event flag can be renamed to it in
    place — identical byte length, no format work, trivially reversible.

    Trade-off: the chosen anchor stops setting its original flag, so anything that
    checks that flag no longer fires. End-of-act style anchors are safest.
    """
    rep = Report("ring_hunt")
    hits = [m for m in EVENT_RE.finditer(blob)
            if len(m.group(2)) == len(RING_FLAG) and m.group(2) != RING_FLAG]
    if not hits:
        rep.notes.append("no 13-character +Event flags available")
        return blob, rep

    pool = {m.group(2): m for m in hits}

    # anchor may name one flag, or one of the predefined pools
    if isinstance(anchor, str) and anchor in RING_HUNT_ANCHOR_SETS:
        wanted = {a.encode() for a in RING_HUNT_ANCHOR_SETS[anchor]}
        pool = {k: v for k, v in pool.items() if k in wanted}
        rep.notes.append(f"anchor set '{anchor}': {len(pool)} flag(s) in pool")
        anchor = None
        count = len(pool) or 1
    elif safe_only:
        narrowed = {k: v for k, v in pool.items()
                    if k.decode() in RING_HUNT_SAFE_ANCHORS}
        if narrowed:
            pool = narrowed

    if anchor:
        want = anchor.encode() if isinstance(anchor, str) else anchor
        if want not in pool:
            rep.notes.append(f"anchor '{anchor}' unavailable; choosing randomly instead")
            anchor = None

    if anchor:
        chosen = [pool[want]]
    else:
        keys = sorted(pool)  # deterministic order, independent of dict hashing
        n = max(1, min(int(count or 1), len(keys)))
        chosen = [pool[k] for k in rng.sample(keys, n)]

    out = bytearray(blob)
    for m in chosen:
        out[m.start(2):m.end(2)] = RING_FLAG
        rep.changed += 1

    names = ", ".join(m.group(2).decode() for m in chosen)
    rep.notes.append(f"endgame now unlocks at: {names}")
    rep.notes.append(f"{len(pool)} candidate anchor(s) in pool")
    rep.notes.append("anchor no longer sets its original flag — end-of-act anchors are safest")
    return bytes(out), rep


def t_item_scatter(blob, rng):
    """Shuffle which item sits at which loose pickup point."""
    rep = Report("item_scatter")
    return _shuffle_matches(blob, rb'\$Item:\s*"([^"]+)"', rng, rep,
                            label="$Item pickup"), rep


def t_shop_shuffle(blob, rng):
    """Shuffle shop prices among equal widths."""
    rep = Report("shop_shuffle")
    return _shuffle_matches(blob, rb'\$Value:\s*(\d+)', rng, rep,
                            label="$Value price"), rep


VALUE_RE = re.compile(rb'(\$Value:\s*)(\d+)')
NAME_VAL_RE = re.compile(rb'(\$Name\s*:\s*")([^"]+)(")')
# Either key that can open a definition block: `$Name:` (a placement) or `$Character:` (a
# dialogue / stat definition). Used to attribute a bare `+Shop` marker to its character.
KEY_LINE_RE = re.compile(rb'\n[ \t]*(\$Name|\$Character)\s*:\s*"([^"]+)"')


def t_shops_free(blob, rng):
    """Every `$Value` price becomes 0, the field's own width preserved.

    A price only ever moves inside its own digit field, so a 4-digit 7500 becomes 0000 -
    the same width, a value the loader reads as zero.
    """
    rep = Report("shops_free")
    hits = list(VALUE_RE.finditer(blob))
    if not hits:
        rep.notes.append("no $Value fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        digits = m.group(2)
        new = b"0" * len(digits)
        if new != digits:
            out[m.start(2):m.end(2)] = new
            rep.changed += 1
    rep.notes.append(f"{len(hits)} $Value prices; {rep.changed} set to 0, field width kept")
    rep.notes.append("a price is only ever rewritten inside its own digit count")
    return bytes(out), rep


def t_shops_crazy(blob, rng):
    """Every `$Value` becomes the largest value its own field can hold (all 9s).

    A 3-digit field becomes 999, a 6-digit field 999999 - the most the loader can read
    from that many digits, so nothing ever has to grow.
    """
    rep = Report("shops_crazy")
    hits = list(VALUE_RE.finditer(blob))
    if not hits:
        rep.notes.append("no $Value fields found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        digits = m.group(2)
        new = b"9" * len(digits)
        if new != digits:
            out[m.start(2):m.end(2)] = new
            rep.changed += 1
    rep.notes.append(f"{len(hits)} $Value prices; {rep.changed} pinned to all-9s of the same width")
    return bytes(out), rep


def _shopkeeper_names(blob: bytes):
    """Character names whose definition block carries the bare `+Shop` marker.

    In the retail stream `+Shop` is a flag on the character's dialogue/topic definition
    (a block keyed by `$Character: "Name"`), not on a `#Character Info` stat block. A
    shopkeeper is therefore the name on the nearest preceding `$Name:`/`$Character:` line;
    `+Shop` is only ever attached where that key is `$Character:`.
    """
    names = set()
    for m in re.finditer(rb"\+Shop\b", blob):
        best = None
        for k in KEY_LINE_RE.finditer(blob, 0, m.start()):
            best = k
        if best and best.group(1) == b"$Character":
            names.add(best.group(2))
    return names


def t_shops_none(blob, rng):
    """Make every shop absent: the shopkeeper's own placement stops naming them.

    A shop exists because a character whose name matches a `+Shop` definition is reached;
    the game resolves the shopkeeper by name (`level_script_get_shopkeeper_info(char *)`).
    So the placement's `$Name:` - the name the game looks up - is re-pointed at an
    equal-length non-shopkeeper name. The definitions themselves are never touched.
    When no equal-length non-shopkeeper name exists the placement is skipped and reported.
    """
    rep = Report("shops_none")
    shop_names = _shopkeeper_names(blob)
    if not shop_names:
        rep.notes.append("no +Shop definitions found - nothing to remove")
        return blob, rep

    monsters, peaceful = _analyse_enemies(blob)
    targets = []
    for rec in monsters + peaceful:
        m = NAME_VAL_RE.search(blob[rec["start"]:rec["end"]])
        if m and m.group(2) in shop_names:
            targets.append((rec["start"] + m.start(2), rec["start"] + m.end(2), m.group(2)))

    pool: dict[int, set] = {}
    for rec in peaceful:
        m = NAME_VAL_RE.search(blob[rec["start"]:rec["end"]])
        if not m:
            continue
        nm = m.group(2)
        if nm in shop_names:
            continue
        pool.setdefault(len(nm), set()).add(nm)

    out = bytearray(blob)
    skipped = 0
    for a, b, nm in targets:
        cands = sorted(pool.get(len(nm), ()))
        if not cands:
            skipped += 1
            continue
        new = cands[rng.randrange(len(cands))]
        if new == nm:
            continue
        out[a:b] = new
        rep.changed += 1
    rep.notes.append(f"{len(shop_names)} shopkeeper definitions; {len(targets)} placements "
                     f"name one; {rep.changed} re-pointed at an equal-length non-shopkeeper")
    if skipped:
        rep.notes.append(f"{skipped} skipped - no equal-length non-shopkeeper name exists")
    rep.notes.append("only the placement's $Name is rewritten - the +Shop definitions are "
                     "never touched")
    return bytes(out), rep


def t_chest_shuffle(blob, rng):
    """Shuffle chest/container payouts (+Give amounts) among equal widths."""
    rep = Report("chest_shuffle")
    out = _shuffle_matches(blob, rb'\+Give:\s*(\d+)', rng, rep,
                           label="+Give payout")
    rep.notes.append("most single-digit values are item counts, so only multi-digit "
                     "gold payouts really move")
    return out, rep


# Gold in Summoner is NOT an enemy drop - there is no enemy->gold mechanism in the tables (verified:
# zero `+Drop: "Gold"`, and soldier records carry no gold field; see docs/lab/probe_gold.py). Gold
# exists only as CONTAINER pickups: a `+Give: N` immediately followed by `+Messagebox: "Gold"`
# (crates/barrels/wells). There are 17 of them. The `+Give` number is a FIXED-WIDTH field with no
# padding (`+Give: 30\r\n`), so size-preservation caps us at the field's own digit count: a 1-digit
# field maxes at 9, 2-digit at 99, 3-digit at 999. **1000 gold is impossible without adding a byte
# and shifting the stream** (no gold field has 4 digits). So `gold_max` fills every gold pickup to
# the largest value its field can hold (9s). This is the honest ceiling the data allows for "more
# gold per pickup"; it does NOT make soldiers drop gold (the data has no such mechanism).
_GOLD_GIVE_RE = re.compile(rb'(\+Give:\s*)(\d+)(\s*\r\n\+Messagebox:\s*"Gold")')


def t_gold_max(blob, rng):
    """Set every GOLD container pickup (`+Give: N` + `+Messagebox: "Gold"`) to the max its fixed-
    width field allows (all 9s). Size-preserving; rng unused (deterministic). Honest limits: gold
    is a container pickup, not an enemy/soldier drop, and 1000 does not fit any field (max is 999
    for the widest, 99 for the common two-digit ones). See docs/lab/probe_gold.py / probe_gold_widths.py.
    """
    rep = Report("gold_max")
    out = bytearray(blob)
    changed = 0
    widths: dict[int, int] = {}
    for m in _GOLD_GIVE_RE.finditer(blob):
        digits = m.group(2)
        w = len(digits)
        maxed = b"9" * w
        widths[w] = widths.get(w, 0) + 1
        if maxed != digits:
            out[m.start(2):m.end(2)] = maxed
            changed += 1
    if not widths:
        rep.notes.append("no gold container pickups found - nothing changed")
        return blob, rep
    rep.changed = changed
    total = sum(widths.values())
    rep.notes.append(f"{total} gold pickup(s) maxed to their field width "
                     + ", ".join(f"{c}x{w}-digit->{'9'*w}" for w, c in sorted(widths.items())))
    rep.notes.append("size-preserving: +Give is fixed width, so 1000+ cannot fit (max 999); gold "
                     "is a container pickup, NOT a soldier/enemy drop (no such mechanism in the data)")
    return bytes(out), rep


# A container is a block that carries BOTH `+Give:` and `+Messagebox:`. `+Give:` is the AMOUNT
# (a count, or a gold sum); the thing you actually receive is the `+Messagebox:` string:
#
#     $Name: "I-docktrunk14"
#     +Give: 1
#     +Messagebox: "Amethyst"
#
# Measured on the retail stream 2026-09-22: 92 such blocks, 35 distinct yields (no quoted item
# name exists inside `+Give:` anywhere - the field is numeric on every block).
_BLOCK_ANCHOR_RE = re.compile(rb"(?m)^(?:\$Name:|#)")
_MSGBOX_RE = re.compile(rb'\+Messagebox:\s*"([^"]+)"')
_GOLD = b"gold"


def _container_yields(blob: bytes) -> list[tuple[int, int, bytes]]:
    """(start, end, name) of the yield field of every container block in the stream."""
    anchors = [m.start() for m in _BLOCK_ANCHOR_RE.finditer(blob)]
    anchors.append(len(blob))
    found = []
    for a, c in zip(anchors, anchors[1:]):
        blk = blob[a:c]
        if b"+Give:" not in blk or b"+Messagebox:" not in blk:
            continue
        mb = _MSGBOX_RE.search(blk)
        if mb:
            found.append((a + mb.start(1), a + mb.end(1), mb.group(1)))
    return found


def t_chest_items(blob, rng, how="shuffle"):
    """Shuffle WHAT a container yields - the `+Messagebox:` name - between equal-length names.

    The payout amount (`+Give:`) is deliberately not touched; that is `chest_shuffle`'s job. This
    is the real chest randomisation: a crate that held a tonic can hold something precious.

    `how` - "shuffle" permutes all yields inside a length class; "swap" trades pairs.

    Gold chests are always pooled among themselves. That is not a policy knob because it cannot
    be anything else on this disc: measured 2026-09-22, every gold yield is the 4-character string
    `Gold`/`gold` and **no item name in the container catalogue is 4 characters long**, so gold
    can only ever trade with gold (91 movable yields; 20 of them gold).

    Size-preserving by construction: a name only ever moves into a field of the same length, and
    a name is never blanked, so no container ends up empty.

    Rings are out of scope on purpose: container grants do not set the `got_ring_of_*` flags
    (see `PLANNED.md` 1.3), so ring progression cannot be routed through containers. No ring name
    appears in the container catalogue, and a permutation cannot introduce one.
    """
    rep = Report("chest_items")
    if how not in ("shuffle", "swap"):
        rep.notes.append(f"unknown how={how!r} - refused, nothing changed")
        return blob, rep

    fields = _container_yields(blob)
    if not fields:
        rep.notes.append("no container blocks (+Give: together with +Messagebox:) found - "
                         "nothing changed")
        return blob, rep

    # a case-only twin (Gold vs gold) is the same yield to a case-insensitive lookup, so those
    # entries are pooled together and never counted as a change on their own
    pools: dict[tuple[str, int], list] = {}
    for start, end, name in fields:
        kind = "gold" if name.lower() == _GOLD else "item"
        pools.setdefault((kind, len(name)), []).append((start, end, name))

    out = bytearray(blob)
    changed = skipped = movable = 0
    for (_kind, _ln), members in sorted(pools.items()):
        if len(members) < 2:
            skipped += len(members)
            continue
        movable += len(members)
        vals = [m[2] for m in members]
        shuf = vals[:]
        if how == "swap":
            order = list(range(len(vals)))
            rng.shuffle(order)
            for i in range(0, len(order) - 1, 2):
                a, b = order[i], order[i + 1]
                shuf[a], shuf[b] = shuf[b], shuf[a]
        else:
            rng.shuffle(shuf)
        for (start, end, old), new in zip(members, shuf):
            if new == old or new.lower() == old.lower():
                skipped += 1
                continue
            out[start:end] = new
            changed += 1

    rep.changed = changed
    n_gold = sum(1 for f in fields if f[2].lower() == _GOLD)
    rep.notes.append(f"{len(fields)} container yields found ({n_gold} gold, "
                     f"{len(fields) - n_gold} items) in {len(pools)} length/kind pool(s)")
    rep.notes.append(f"{changed} yields rewritten, {skipped} left as they were "
                     f"({movable} were movable)")
    rep.notes.append("the item NAME is the +Messagebox: string, NOT +Give: - that field is an "
                     "amount (a count or a gold sum) and it is left alone here")
    rep.notes.append("gold is pooled separately and cannot become an item: every gold yield is "
                     "4 characters and no item name is that short")
    rep.notes.append("size-preserving: names only move into same-length fields, never blanked")
    return bytes(out), rep


def t_dialogue_shuffle(blob, rng):
    """Shuffle spoken text so NPCs say each other's lines.

    Deliberately does NOT touch +Topic: ids. Topic names are reference keys —
    +Add Topic: and +Remove Topic: point at the same namespace — so shuffling
    them independently breaks the links and can strand a quest. Only the spoken
    payloads are shuffled, which leaves every reference intact.
    """
    rep = Report("dialogue_shuffle")
    out = blob
    for pat, label in ((rb'\+NPCText:\s*\{([^}]+)\}', "+NPCText line"),
                       (rb'\+Messagebox:\s*"([^"]+)"', "+Messagebox text")):
        out = _shuffle_matches(out, pat, rng, rep, label=label)
    rep.notes.append("topic ids left alone on purpose — they are reference keys")
    return out, rep


# --------------------------------------------------------------------------- #
# Second wave — table-driven shuffles over one or more payload patterns
#
# Each entry is a list of (regex, label) pairs. Every pattern's capture group is
# shuffled only among matches that share its exact byte length, so all of these
# are size-preserving by construction. Counts are from the Summoner 1 corpus.
# --------------------------------------------------------------------------- #
# NOTE: patterns use [^"]+\.ext rather than a character class, so paths with
# backslashes (e.g. "Doors\Open_Stone_verylarge.wav") match too. An earlier
# version over-escaped the dot as \\. which required a literal backslash before
# the extension and silently matched nothing.
_SHARED_SOUND = rb'"([^"]+\.wav)"'

_SHUFFLE_SPECS: dict[str, list[tuple[bytes, str]]] = {
    # 1,605 refs — very audible, zero progression risk
    "sound_shuffle": [
        (_SHARED_SOUND, "sound .wav ref"),
    ],
    # 77 + 1,077 — the wrong track plays in the wrong place
    "music_shuffle": [
        (rb'\$Soundtrack:\s*"([^"]+)"', "$Soundtrack"),
        (rb'\$Sound:\s*"([^"]+)"', "$Sound"),
    ],
    # 4,590 — relocates who stands where. Spawn anchors are valid navpoints.
    "spawn_shuffle": [
        (rb'\$Start position:\s*"([^"]+)"', "$Start position"),
    ],
    # 2,141 + 345 — characters perform the wrong animations
    "animation_shuffle": [
        (rb'\$Animation:\s*"([^"]+)"', "$Animation"),
        (rb'\+Animation class:\s*"([^"]+)"', "+Animation class"),
    ],
    # 11,602 — NPC and enemy BEHAVIOUR. Actions drive scripts, so this can break
    # scripted sequences. Chaos only, never in a progression mode.
    "action_shuffle": [
        (rb'\+Action:\s*"([^"]+)"', "+Action"),
    ],
    # 570 + 572 — items display the wrong icon, gear looks wrong
    "icon_shuffle": [
        (rb'\$Icon:\s*"([^"]+)"', "$Icon"),
        (rb'"([^"]+\.vbm)"', ".vbm ref"),
    ],
    # 412 — wrong spell and impact effects
    "vfx_shuffle": [
        (rb'"([^"]+\.vfx)"', ".vfx ref"),
    ],
    # 92 + 91 — cutscenes shot from the wrong angles
    "camera_shuffle": [
        (rb'\$Camera:\s*"([^"]+)"', "$Camera"),
        (rb'"([^"]+\.csc)"', ".csc ref"),
    ],
    # 100 — visibility and atmosphere invert per level
    "fog_shuffle": [
        (rb'\$Fog:\s*([0-9.]+)', "$Fog"),
    ],
    # 280 + 96 — gear lands in the wrong equipment slot
    "slot_shuffle": [
        (rb'\+Slot:\s*"([^"]+)"', "+Slot"),
        (rb'\$Slot:\s*"([^"]+)"', "$Slot"),
    ],
    # The creature stat block. This is the anti-grind lever that was listed as
    # blocked: the values are ordinary equal-width numbers, so they are swappable.
    "creature_stats_shuffle": [
        (rb'\$Speed:\s*([0-9.]+)', "$Speed"),
        (rb'\$Weight:\s*([0-9.]+)', "$Weight"),
        (rb'\$Attack Radius:\s*([0-9.]+)', "$Attack Radius"),
        (rb'\$Max Hit Points:\s*([0-9.]+)', "$Max Hit Points"),
        (rb'\$Hit Points:\s*([0-9.]+)', "$Hit Points"),
        (rb'\$Damage:\s*([0-9.]+)', "$Damage"),
        (rb'\$Protection:\s*([0-9.]+)', "$Protection"),
        (rb'\$Aggressiveness:\s*([0-9.]+)', "$Aggressiveness"),
        (rb'\$Teamwork:\s*([0-9.]+)', "$Teamwork"),
        (rb'\$Conservation:\s*([0-9.]+)', "$Conservation"),
        (rb'\$Detection range:\s*([0-9.]+)', "$Detection range"),
        (rb'\$Field of view range:\s*([0-9.]+)', "$Field of view range"),
        (rb'\$Max ability Points:\s*([0-9.]+)', "$Max ability Points"),
        (rb'\$Ability Points:\s*([0-9.]+)', "$Ability Points"),
        (rb'\$Speedup rate:\s*([0-9.]+)', "$Speedup rate"),
        (rb'\$Slowdown rate:\s*([0-9.]+)', "$Slowdown rate"),
    ],
    # 143 — what a slain enemy drops. `+Drop: "Item Name" <weight>` — shuffle WHICH item
    # each drop entry yields (among equal-length names), leaving the drop-chance weight
    # alone. Enemies now drop different loot; size-preserving, no item is invented or lost.
    "enemy_drops_random": [
        (rb'\+Drop:\s*"([^"]+)"', "+Drop item"),
    ],
    # 77 — the background MUSIC only ($Soundtrack), NOT sound effects. The wrong track plays
    # in the wrong place, but heal still sounds like heal. (music_shuffle scrambles $Sound too,
    # i.e. SFX as well; this is the music-only lever.)
    "music_tracks_shuffle": [
        (rb'\$Soundtrack:\s*"([^"]+)"', "$Soundtrack"),
    ],
}


def _make_multi_shuffle(tname: str):
    specs = _SHUFFLE_SPECS[tname]

    def fn(blob, rng):
        rep = Report(tname)
        out = blob
        for pat, label in specs:
            out = _shuffle_matches(out, pat, rng, rep, label=label)
        if not rep.notes:
            rep.notes.append("no matching payloads found")
        return out, rep

    fn.__name__ = "t_" + tname
    return fn


# --------------------------------------------------------------------------- #
# Pacing — less dialogue, faster transitions
# --------------------------------------------------------------------------- #
# Fade lines carry three numbers: start, DURATION, and a third value.
#   $Fade In:  0.0 2.0 0     $Fade Out: 3.0 1.5 7
# We zero the duration, keeping the field width so nothing shifts.
FADE_RE = re.compile(rb'(\$Fade (?:In|Out):\s*)([0-9.]+)(\s+)([0-9.]+)')
NPCTEXT_RE = re.compile(rb'(\+NPCText:\s*\{)([^}]*)(\})')
STAGE_RE = re.compile(rb'(\+Stage:\s*")([^"]*)(")')


def _zeros_like(digits: bytes) -> bytes:
    """Same-width zero: '2.0' -> '0.0', '1.50' -> '0.00'."""
    w = len(digits)
    if b"." in digits:
        head, _, tail = digits.partition(b".")
        return b"0." + b"0" * len(tail) if tail else b"0" * w
    return b"0" * w


def t_fade_instant(blob, rng):
    """Zero every scene fade duration so transitions stop dawdling.

    Fades are the small waits between scenes, cutscenes and level loads. Setting
    the duration to 0 keeps the fade logic intact but removes the pause. Purely a
    presentation value — no progression impact.
    """
    rep = Report("fade_instant")
    hits = list(FADE_RE.finditer(blob))
    if not hits:
        rep.notes.append("no fade lines found")
        return blob, rep
    out = bytearray(blob)
    for m in hits:
        z = _zeros_like(m.group(4))
        if z != m.group(4):
            rep.changed += 1
        out[m.start(4):m.end(4)] = z
    rep.notes.append(f"{len(hits)} fade durations zeroed")
    rep.notes.append("presentation only — removes the pause between scenes")
    return bytes(out), rep


def t_dialogue_blank(blob, rng):
    """Blank spoken dialogue and quest text, preserving every byte of structure.

    Dialogue is 2.6 million characters across 5,446 payloads — the single largest
    time cost in a run. We overwrite the printable body with spaces, keeping the
    exact length, and keep newlines so the line structure survives. Boxes still
    appear and still need advancing, but there is nothing left to read.

    Note: this does NOT skip the advance prompt. If the engine waits for a button
    press per box, the wait remains. What it removes is the reading.
    """
    rep = Report("dialogue_blank")
    total = 0
    out = bytearray(blob)
    for rx, label in ((NPCTEXT_RE, "+NPCText"), (STAGE_RE, "+Stage")):
        hits = list(rx.finditer(bytes(out)))
        chars = 0
        for m in hits:
            body = m.group(2)
            blank = bytes(10 if c == 10 else (13 if c == 13 else 32) for c in body)
            if blank != body:
                chars += 1
            out[m.start(2):m.end(2)] = blank
        rep.changed += chars
        rep.notes.append(f"{len(hits)} {label} payloads blanked")
        total += chars
    rep.notes.append("length preserved exactly; newlines kept")
    rep.notes.append("removes the reading, not the key press")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Enemies - the two halves of the model
#
# A hostile placement, inside a level's #Objects section:
#
#   $Name:			"Bone King#$npc038"
#   $Character:			"Bone King"
#   +Monster
#   $Start position:	"$npc038"
#
# 2,220 of those exist (80 distinct creatures, 75 of them also defined in text). `$Name` binds
# the instance to the `$npcNNN` navpoint that `$Start position` references, so the record is a
# *placement*: 12,822 `$Position` records exist, one per navpoint, and 4,017 `$Character`
# records are not monsters at all (NPCs, shopkeepers, props).
#
# A creature's numbers live in one of 101 `#Character Info` blocks:
#
#   $Character:			"Abbot Laurent"
#   $Size:				"medium"
#   $Team:				"friendly"        <- 50 friendly, 49 hostile, 1 Hostile, 1 evil
#   $Max Hit Points:	40
#   $Aggressiveness:	50
#   $Attack Radius:		1.0
#   $Field of view range:	4.0
#   $Detection range:	4.0
#   $Speedup rate:		3.0
#
# Everything below is **size-preserving**: values are rewritten inside their own field width, so
# the 527-entry TABLES.VPP stream never shifts. Anything that would need *new* bytes - one more
# placement, one more flag - is not here, and is not possible until the archive-slack question
# is answered (PROJECT.md §6).
# --------------------------------------------------------------------------- #
NAME_LINE_RE = re.compile(rb"\n[ \t]*\$Name\s*:")
MONSTER_FLAG_RE = re.compile(rb"\n[ \t]*\+Monster\b")
PLACEMENT_CHAR_RE = re.compile(rb'(\$Character\s*:\s*")([^"]+)(")')
START_POS_RE = re.compile(rb'(\$Start position\s*:\s*")([^"]+)(")')
PLACEMENT_LEVEL_RE = re.compile(rb"(\+Level\s*:\s*)(\d+)")
TEAM_RE = re.compile(rb'(\$Team\s*:\s*")([A-Za-z]+)(")')
HOSTILE_TEAMS = {b"hostile", b"Hostile", b"evil"}

CREATURE_NUM_FIELDS = (
    rb"(\$Max Hit Points\s*:\s*)(\d+)",
    rb"(\$Hit Points\s*:\s*)(\d+)",
    rb"(\$Max ability Points\s*:\s*)(\d+)",
    rb"(\$Ability Points\s*:\s*)(\d+)",
    rb"(\$Aggressiveness\s*:\s*)(\d+)",
)
CREATURE_FLOAT_FIELDS = (
    rb"(\$Attack Radius\s*:\s*)(\d+\.\d+)",
    rb"(\$Field of view range\s*:\s*)(\d+\.\d+)",
    rb"(\$Detection range\s*:\s*)(\d+\.\d+)",
    rb"(\$Speedup rate\s*:\s*)(\d+\.\d+)",
    rb"(\$Slowdown rate\s*:\s*)(\d+\.\d+)",
)

# The dial the owner asked for: easy easy -> impossible. 100 = vanilla.
ENEMY_DIFFICULTY = {    "trivial": 50,
    "easy": 75,
    "normal": 100,
    "hard": 160,
    "brutal": 250,
    "deadly": 400,
    "impossible": 999,
}


def _scale_float_width(digits: bytes, percent: int) -> bytes:
    """Scale a d.d value inside its own width, clamping to the widest value that still fits."""
    w = len(digits)
    try:
        val = float(digits)
    except ValueError:
        return digits
    if val == 0:
        return digits
    decimals = len(digits.split(b".")[1]) if b"." in digits else 0
    int_digits = w - (1 + decimals if decimals else 0)
    hi = float(("9" * max(1, int_digits)) + (("." + "9" * decimals) if decimals else ""))
    scaled = max(0.0, min(hi, val * percent / 100.0))
    text = f"{scaled:.{decimals}f}".encode()
    if len(text) < w:
        text = b" " * (w - len(text)) + text
    return text[:w]


def _placement_records(blob: bytes):
    """(start, end) for every `$Name:` record that actually places a character."""
    starts = [m.start() for m in NAME_LINE_RE.finditer(blob)]
    starts.append(len(blob))
    out = []
    for i in range(len(starts) - 1):
        s, e = starts[i], starts[i + 1]
        seg = blob[s:e]
        if b"$Start position" in seg and b"$Character" in seg:
            out.append((s, e))
    return out


def _analyse_enemies(blob: bytes):
    """Split every placement into monsters (has +Monster) and peaceful ones."""
    monsters, peaceful = [], []
    for s, e in _placement_records(blob):
        seg = blob[s:e]
        cm = PLACEMENT_CHAR_RE.search(seg)
        if cm is None:
            continue
        rec = {
            "start": s,
            "end": e,
            "char": cm.group(2),
            "char_abs": (s + cm.start(2), s + cm.end(2)),
        }
        (monsters if MONSTER_FLAG_RE.search(seg) else peaceful).append(rec)
    return monsters, peaceful


def _hostile_char_blocks(blob: bytes):
    """(start, end) for every `#Character Info` block whose `$Team:` is hostile."""
    return _char_info_blocks(blob, HOSTILE_TEAMS)


def _char_info_blocks(blob: bytes, teams):
    """(start, end) for every `#Character Info` block whose `$Team:` is in `teams`.

    A block runs from just after its `#Character Info` header to the START of the next
    section of ANY kind — the next `\\n#...`, including the next `#Character Info`. The
    earlier rule skipped over following `#Character Info` headers, which let one block's
    range swallow the blocks after it and mis-attribute their fields; anchoring on the
    next `\\n#` keeps each block's fields its own.
    """
    out = []
    for m in re.finditer(rb"#Character Info", blob):
        s = m.end()
        nxt = re.search(rb"\n#", blob[s:])
        e = s + (nxt.start() if nxt else 3000)
        t = TEAM_RE.search(blob[s:e])
        if t and t.group(2) in teams:
            out.append((s, e))
    return out


def _unlink_monster_navpoints(blob: bytes, monsters, out: bytearray) -> int:
    """Rewrite every monster placement's `$Start position` (and the matching `$Name`
    suffix) from `$npcNNN` to `$zzzNNN`, a navpoint that exists nowhere. Same width,
    so the record stays the same length and can never bind to a position again.

    Returns the number of fields rewritten. Shared by `enemies_none` and
    `enemies_amount` so the shipped, in-game-verified behaviour is reproduced exactly.
    """
    edits = 0
    for rec in monsters:
        seg = bytes(blob[rec["start"]:rec["end"]])
        for m in START_POS_RE.finditer(seg):
            val = m.group(2)
            if val.startswith(b"$npc"):
                off = rec["start"] + m.start(2)
                out[off:off + len(val)] = b"$zzz" + val[4:]
                edits += 1
        for m in re.finditer(rb'"([^"\n]*#)(\$npc[^"\n]*)"', seg):
            off = rec["start"] + m.start(2)
            val = m.group(2)
            out[off:off + len(val)] = b"$zzz" + val[4:]
            edits += 1
    return edits


def _hostile_name_pool(blob: bytes, monsters) -> dict:
    """Hostile creature names grouped by name length, from the monster placements.

    Only names whose `#Character Info` block is hostile qualify (when that set is
    non-empty), because it is the *definition* that carries `$Team: "hostile"`.
    """
    hostile_names = set()
    for s, e in _hostile_char_blocks(blob):
        m = PLACEMENT_CHAR_RE.search(blob[s:e])
        if m:
            hostile_names.add(m.group(2))
    pool: dict[int, list] = {}
    for rec in monsters:
        if hostile_names and rec["char"] not in hostile_names:
            continue
        pool.setdefault(len(rec["char"]), [])
        if rec["char"] not in pool[len(rec["char"])]:
            pool[len(rec["char"])].append(rec["char"])
    return pool


def _convert_peaceful(blob: bytes, targets, pool, rng: Random, out: bytearray):
    """Re-point peaceful placements at a hostile name of the same length.

    Returns (converted, skipped). A placement is skipped when no hostile name shares
    its length - the honest ceiling of this layer, since a name cannot be lengthened.
    """
    converted = skipped = 0
    for rec in targets:
        cands = sorted(pool.get(len(rec["char"]), ()))
        if not cands:
            skipped += 1
            continue
        new = cands[rng.randrange(len(cands))]
        if new == rec["char"]:
            continue
        a, b = rec["char_abs"]
        out[a:b] = new
        converted += 1
    return converted, skipped


# The enemy-count dial: three requested options are the same lever at different values.
AMOUNT_VALUES = ("none", "few", "normal", "many", "all")


def t_enemies_amount(blob, rng, amount="normal"):
    """One dial over how many enemies there are.

    * ``none``   - unlink every monster placement from its navpoint. Reproduces the shipped,
                   in-game-verified `enemies_none(how="navpoint")` byte for byte.
    * ``few``    - unlink a seeded majority (~70%) of the monster placements.
    * ``normal`` - vanilla; nothing is edited, and the report says so.
    * ``many``   - convert a seeded share (~50%) of the peaceful placements into hostile
                   creatures of equal name length.
    * ``all``    - convert every convertible peaceful placement (the rest have no hostile
                   name of their length and are reported as skips).

    Seeded through ``rng`` and therefore deterministic per seed. An unknown value changes
    nothing and says so.
    """
    rep = Report("enemies_amount")
    amount = str(amount)
    if amount not in AMOUNT_VALUES:
        rep.notes.append(f"unknown amount {amount!r} - pick one of {list(AMOUNT_VALUES)}; "
                         f"nothing changed")
        return blob, rep
    if amount == "normal":
        rep.notes.append("amount='normal' = vanilla by design: 0 edits, nothing changed")
        return blob, rep

    monsters, peaceful = _analyse_enemies(blob)

    if amount in ("none", "few"):
        if not monsters:
            rep.notes.append("no +Monster placements found")
            return blob, rep
        out = bytearray(blob)
        if amount == "none":
            chosen = monsters
        else:
            order = list(range(len(monsters)))
            rng.shuffle(order)
            k = max(1, round(len(monsters) * 0.70))
            chosen = [monsters[i] for i in sorted(order[:k])]
        rep.changed = _unlink_monster_navpoints(blob, chosen, out)
        rep.notes.append(f"{len(monsters)} monster placements; {len(chosen)} unlinked from "
                         f"their navpoints ({amount})")
        rep.notes.append("$npcNNN -> $zzzNNN: same width, a navpoint that exists nowhere")
        rep.notes.append("size-preserving; nothing else about the record changes")
        return bytes(out), rep

    # many / all - re-point peaceful placements at hostile creatures of equal name length
    pool = _hostile_name_pool(blob, monsters)
    out = bytearray(blob)
    if amount == "all":
        targets = peaceful
    else:
        order = list(range(len(peaceful)))
        rng.shuffle(order)
        k = max(1, round(len(peaceful) * 0.50))
        targets = [peaceful[i] for i in sorted(order[:k])]
    converted, skipped = _convert_peaceful(blob, targets, pool, rng, out)
    rep.changed = converted
    rep.notes.append(f"{len(peaceful)} peaceful placements; {len(targets)} targeted; "
                     f"{converted} now name a monster")
    if skipped:
        rep.notes.append(f"{skipped} skipped - no hostile name of that length")
    rep.notes.append(f"hostile name pool: {sum(len(v) for v in pool.values())} names "
                     f"in {len(pool)} length classes")
    rep.notes.append("no bytes added - placements are re-pointed, not created")
    return bytes(out), rep


def t_enemies_none(blob, rng, how="navpoint"):
    """No hostiles. Every monster placement is unlinked from the navpoint it spawns on.

    The placement binds to `$Start position: "$npcNNN"`; renaming that (and the matching
    suffix in `$Name:`) to `$zzzNNN` - a navpoint that exists nowhere - leaves the record
    intact and unreachable. `how="team"` is the other lever: re-team the hostile creature
    definitions themselves, which also covers creatures placed by code rather than by a
    `#Objects` record.

    Neither lever adds or removes a byte.
    """
    rep = Report("enemies_none")
    monsters, _ = _analyse_enemies(blob)
    if not monsters:
        rep.notes.append("no +Monster placements found")
        return blob, rep
    out = bytearray(blob)
    if how == "team":
        # Verified in game 2026-09-21: rewriting $Team: "hostile" -> "neutral" (and "evil" ->
        # "good") made the game never load a level at all - Level_data.name stayed empty for a
        # whole 110 s run. Those are almost certainly not valid team identifiers, and an invalid
        # one takes the level load down with it. Blocked, with the reason, rather than shipped.
        rep.notes.append("BLOCKED: re-teaming is not safe - 'neutral'/'good' are not valid $Team "
                         "values; the level never loads (verified in game 2026-09-21). "
                         "Use how='navpoint'.")
        return blob, rep

    if how == "both":
        base, sub = t_enemies_none(blob, rng, how="navpoint")
        rep.changed += sub.changed
        rep.notes.append("how='both' currently does the navpoint lever only - the team lever is "
                         "blocked (see the report below)")
        rep.notes.extend(sub.notes)
        return bytes(base), rep

    rep.changed = _unlink_monster_navpoints(blob, monsters, out)
    rep.notes.append(f"{len(monsters)} monster placements unlinked from their navpoints")
    rep.notes.append("$npcNNN -> $zzzNNN: same width, a navpoint that exists nowhere")
    rep.notes.append("size-preserving; nothing else about the record changes")
    return bytes(out), rep


def t_enemies_random(blob, rng, scope="per_level", broad_min=5):
    """Randomize WHICH creature stands on each monster placement, and at what level.

    Same number of enemies, different ones - the safe direction (contents, not counts). Names
    are swapped only between equal-length names, and `+Level:` only between equal-width
    values, so every edit stays inside its field.

    Only `+Monster` placements are ever touched - NPC/shopkeeper/prop placements (the peaceful
    ones) are never changed, so quests never break.

    `scope`:
      * ``per_level`` (default, SAFE) - a placement only receives a creature name that already
        appears in the SAME level (segmented by `#Objects`). Every swapped-in creature's model
        is therefore already loaded for that level, so nothing goes missing. Limited variety in
        small levels (the starting area only has a couple of monster types).
      * ``broad`` (SAFE, more variety) - each monster placement is re-pointed at a creature drawn
        from the "broadly available" pool: creatures that appear as placed monsters in at least
        `broad_min` distinct levels (default 5), so their models are loaded widely and very likely
        present. Only picks an equal-length name (size-preserving). This lets a Green Bacite / Lich
        / Fire Imp turn up in the starting area without the missing-graphics risk of `global`.
      * ``global`` (EXPERIMENTAL) - swap among all equal-length names game-wide. Can pull in a
        creature whose model the level does not load -> MISSING WORLD GRAPHICS. Not recommended.
    """
    rep = Report("enemies_random")
    scope = str(scope)
    if scope not in ("per_level", "broad", "global"):
        rep.notes.append(f"unknown scope {scope!r} - pick per_level, broad or global; nothing changed")
        return blob, rep
    monsters, _ = _analyse_enemies(blob)
    if not monsters:
        rep.notes.append("no +Monster placements found")
        return blob, rep
    out = bytearray(blob)

    import bisect
    obj_marks = sorted(m.start() for m in re.finditer(rb"\n#Objects\b", blob))

    def seg_of(off: int) -> int:
        return bisect.bisect_right(obj_marks, off) - 1 if obj_marks else 0

    if scope == "broad":
        # Build the broadly-available pool: creatures placed as monsters in >= broad_min distinct
        # level segments, grouped by name length. Then each monster placement independently draws
        # a same-length creature from that pool. Deterministic per seed.
        from collections import defaultdict
        levels_of: dict[bytes, set] = defaultdict(set)
        for rec in monsters:
            levels_of[rec["char"]].add(seg_of(rec["start"]))
        pool_by_len: dict[int, list] = defaultdict(list)
        for name, segs in levels_of.items():
            if len(segs) >= broad_min:
                pool_by_len[len(name)].append(name)
        for k in pool_by_len:
            pool_by_len[k].sort()   # stable order before seeded choice
        swapped = 0
        no_pool = 0
        for rec in monsters:
            cands = pool_by_len.get(len(rec["char"]))
            if not cands:
                no_pool += 1
                continue
            new = cands[rng.randrange(len(cands))]
            if new != rec["char"]:
                a, b = rec["char_abs"]
                out[a:b] = new
                swapped += 1
        pool_total = sum(len(v) for v in pool_by_len.values())
        rep.changed += swapped
        rep.notes.append(f"{len(monsters)} monster placements, scope=broad "
                         f"(pool: {pool_total} creatures in {len(pool_by_len)} length classes, "
                         f">= {broad_min} levels each)")
        rep.notes.append(f"{swapped} placements re-pointed at a broadly-available creature; "
                         f"{no_pool} left alone (no same-length creature in the pool)")
        rep.notes.append("only +Monster placements touched; NPCs untouched; models broadly loaded")
    else:
        # per_level (safe) or global (experimental): permute existing names within the group.
        groups: dict[tuple, list] = {}
        for rec in monsters:
            key = (seg_of(rec["start"]) if scope == "per_level" else 0, len(rec["char"]))
            groups.setdefault(key, []).append(rec)
        swapped = 0
        for key, recs in groups.items():
            if len(recs) < 2:
                continue
            names = [r["char"] for r in recs]
            shuf = names[:]
            rng.shuffle(shuf)
            for rec, name in zip(recs, shuf):
                if name != rec["char"]:
                    a, b = rec["char_abs"]
                    out[a:b] = name
                    swapped += 1
        rep.changed += swapped
        rep.notes.append(f"{len(monsters)} monster placements, scope={scope}, {len(groups)} groups")
        rep.notes.append(f"{swapped} creatures swapped for an equal-length creature "
                         + ("in the same level (models stay loaded)" if scope == "per_level"
                            else "game-wide (may pull unloaded models)"))

    levels = []
    for rec in monsters:
        seg = blob[rec["start"]:rec["end"]]
        for m in PLACEMENT_LEVEL_RE.finditer(seg):
            levels.append((rec["start"] + m.start(2), rec["start"] + m.end(2), m.group(2)))
    if levels:
        by_w: dict[int, list] = {}
        for item in levels:
            by_w.setdefault(len(item[2]), []).append(item)
        lv_moved = 0
        for w, items in sorted(by_w.items()):
            if len(items) < 2:
                continue
            vals = [d for _, _, d in items]
            shuf = vals[:]
            rng.shuffle(shuf)
            for (a, b, old), v in zip(items, shuf):
                if v != old:
                    out[a:b] = v
                    lv_moved += 1
        rep.changed += lv_moved
        rep.notes.append(f"{len(levels)} placement +Level values shuffled ({lv_moved} moved)")
    return bytes(out), rep


def t_enemies_swarm(blob, rng, keep_towns=False):
    """Far more enemies: peaceful placements are re-pointed at hostile creatures.

    `$Character:` selects the creature *definition*, and it is the definition that carries
    `$Team: "hostile"` - so an NPC placement that names a monster becomes a monster on the
    spot. That is the strongest thing this layer can do without adding bytes: the placement
    count cannot be raised, only re-pointed.

    Cost, stated plainly: quest NPCs and shopkeepers placed this way stop being people, so
    quests that expect them will not complete. That is what "spawn way more" buys, and why
    this is an opt-in chaos-tier mode, not a default.
    """
    rep = Report("enemies_swarm")
    monsters, peaceful = _analyse_enemies(blob)
    pool = _hostile_name_pool(blob, monsters)
    out = bytearray(blob)
    converted, skipped = _convert_peaceful(blob, peaceful, pool, rng, out)
    rep.changed += converted
    rep.notes.append(f"{len(peaceful)} peaceful placements; {converted} now name a monster")
    if skipped:
        rep.notes.append(f"{skipped} left alone - no hostile name of that length")
    rep.notes.append(f"hostile name pool: {sum(len(v) for v in pool.values())} names "
                     f"in {len(pool)} length classes")
    rep.notes.append("no bytes added - placements are re-pointed, not created")
    return bytes(out), rep


def t_enemy_difficulty(blob, rng, level="normal", level_shift=0):
    """The difficulty dial, easy easy -> impossible.

    Scales the hostile creature definitions' own numbers (hit points, aggressiveness, view and
    detection range, attack radius, movement rates) and the per-placement `+Level:`, each
    inside its own field width. `impossible` pushes every value to the maximum that fits.

    Deterministic on purpose - a difficulty setting should not be a dice roll.
    """
    rep = Report("enemy_difficulty")
    percent = ENEMY_DIFFICULTY.get(str(level))
    if percent is None:
        rep.notes.append(f"unknown difficulty {level!r}; pick one of {sorted(ENEMY_DIFFICULTY)}")
        return blob, rep
    out = bytearray(blob)
    blocks = _hostile_char_blocks(blob)
    field_hits = 0
    for s, e in blocks:
        seg = bytes(out[s:e])
        for rx in CREATURE_NUM_FIELDS:
            for m in re.finditer(rx, seg):
                new = _scale_width(m.group(2), percent)
                if new != m.group(2):
                    out[s + m.start(2):s + m.end(2)] = new
                    field_hits += 1
        for rx in CREATURE_FLOAT_FIELDS:
            for m in re.finditer(rx, seg):
                new = _scale_float_width(m.group(2), percent)
                if new != m.group(2):
                    out[s + m.start(2):s + m.end(2)] = new
                    field_hits += 1
    monsters, _ = _analyse_enemies(blob)
    lvl_hits = 0
    for rec in monsters:
        seg = blob[rec["start"]:rec["end"]]
        for m in PLACEMENT_LEVEL_RE.finditer(seg):
            digits = m.group(2)
            w = len(digits)
            try:
                val = int(digits)
            except ValueError:
                continue
            val = val + level_shift if level_shift else (val * percent) // 100
            val = max(1, min(int("9" * w), val))
            new = str(val).zfill(w).encode()
            if new != digits:
                out[rec["start"] + m.start(2):rec["start"] + m.end(2)] = new
                lvl_hits += 1
    rep.changed = field_hits + lvl_hits
    rep.notes.append(f"{len(blocks)} hostile creature definitions scaled to {percent}% "
                     f"({field_hits} fields)")
    rep.notes.append(f"{lvl_hits} placement +Level values scaled"
                     + (f" (+{level_shift} shift)" if level_shift else ""))
    rep.notes.append("every value rewritten inside its own field width - size preserving")
    rep.notes.append("deterministic - identical on every seed")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Creature stats — SHUFFLE (not scale). enemy_difficulty scales hostile numbers;
# these two move them between creatures instead, hostile and friendly kept apart.
#
# Mechanism: every numeric field in CREATURE_NUM_FIELDS / CREATURE_FLOAT_FIELDS,
# collected across one side's `#Character Info` blocks, is permuted among the other
# creatures on that same side. Size-preserving by construction — see the two styles.
#
#   style="floor" (default) — permute values only within their own byte-width class,
#       per field. Width IS the magnitude tier here, so a three-digit boss HP can only
#       land on another three-digit HP: the top class stays the top class, and a boss
#       never wakes up with 15 HP. This is the honest reading of "randomized stats".
#   style="pure" — permute a field's values across ALL widths, writing each back only
#       where it still fits (right-justified, never grown). A small value CAN drop into
#       a big field, so a boss can end up paper-thin. Funnier, riskier; opt-in.
#
# Both shuffle each SIDE separately: the party's numbers stay in the party, the
# hostiles' stay hostile, so the two items are genuinely distinct features.
# --------------------------------------------------------------------------- #
FRIENDLY_TEAMS = {b"friendly"}
STAT_STYLES = ("floor", "pure")


def _friendly_char_blocks(blob: bytes):
    """(start, end) for every `#Character Info` block whose `$Team:` is friendly.

    The mirror of `_hostile_char_blocks`: same block bounds, opposite team filter, so
    the playable party is selected the same way the enemy side is.
    """
    return _char_info_blocks(blob, FRIENDLY_TEAMS)


def _shuffle_stats_in_blocks(blob: bytes, rng: Random, blocks, style: str, rep: Report) -> bytes:
    """Shuffle every creature stat field among the given blocks, size-preserving.

    For each field regex, gathers (absolute_offset, value) across all `blocks`, then:
      * floor — permutes the values inside each byte-width group (a value never changes
        width, so it never leaves its magnitude tier);
      * pure  — permutes the values across all widths, but writes a chosen value back
        only where it fits the destination field width, right-justified for integers
        and width-matched for floats; anything that will not fit falls back to a
        same-width pick, so the stream can never grow.
    Returns the edited blob and fills `rep` with the per-field counts.
    """
    out = bytearray(blob)
    is_float = {rx: True for rx in CREATURE_FLOAT_FIELDS}
    total = 0
    for rx in CREATURE_NUM_FIELDS + CREATURE_FLOAT_FIELDS:
        occ = []  # (abs_start, abs_end, value)
        for s, e in blocks:
            seg = bytes(out[s:e])
            for m in re.finditer(rx, seg):
                occ.append((s + m.start(2), s + m.end(2), m.group(2)))
        if len(occ) < 2:
            continue
        vals = [v for _, _, v in occ]
        if style == "pure":
            new_vals = _pure_assign(occ, rng)
        else:
            new_vals = _floor_assign(occ, rng)
        changed = 0
        for (a, b, old), new in zip(occ, new_vals):
            if new is not None and new != old and len(new) == (b - a):
                out[a:b] = new
                changed += 1
        if changed:
            label = rx.split(b"\\")[0].decode("latin-1", "ignore").lstrip("(").lstrip("$")
            rep.notes.append(f"{label or 'field'}: {len(occ)} values, {changed} moved")
        total += changed
    rep.changed += total
    return bytes(out)


def _floor_assign(occ, rng: Random):
    """Permute values inside each byte-width group; every value keeps its width."""
    by_w: dict[int, list[int]] = {}
    for i, (_, _, v) in enumerate(occ):
        by_w.setdefault(len(v), []).append(i)
    new = [None] * len(occ)
    for _, idxs in by_w.items():
        if len(idxs) < 2:
            new[idxs[0]] = occ[idxs[0]][2] if idxs else None
            continue
        vals = [occ[i][2] for i in idxs]
        shuf = vals[:]
        rng.shuffle(shuf)
        for i, v in zip(idxs, shuf):
            new[i] = v
    return new


def _pure_assign(occ, rng: Random):
    """Permute values across ALL widths; write back only where the value fits.

    A shorter value is right-justified into a wider field (a small number CAN land in a
    boss's field — that is the point of pure). A longer value cannot fit a narrower field,
    so those positions keep a same-width value instead, and the stream never grows.
    """
    n = len(occ)
    order = list(range(n))
    rng.shuffle(order)
    new = [None] * n
    # width-bucketed fallbacks so a non-fitting pick can still be filled same-width
    by_w: dict[int, list[bytes]] = {}
    for _, _, v in occ:
        by_w.setdefault(len(v), []).append(v)
    for w in by_w:
        rng.shuffle(by_w[w])
    for dst, src in zip(range(n), order):
        a, b, _ = occ[dst]
        width = b - a
        cand = occ[src][2]
        if len(cand) <= width:
            is_float = b"." in cand
            if is_float:
                # only reuse a float in an equal-width float field to keep the decimal shape
                new[dst] = cand if len(cand) == width else None
            else:
                new[dst] = cand.rjust(width, b" ") if width != len(cand) else cand
        if new[dst] is None:
            pool = by_w.get(width)
            new[dst] = pool.pop() if pool else occ[dst][2]
    return new


# Both `$Max Hit Points` and the current `$Hit Points` carry the HP number; the "one HP"
# lever writes the same value into both so a creature cannot heal back above it.
HP_FIELDS = (
    rb"(\$Max Hit Points\s*:\s*)(\d+)",
    rb"(\$Hit Points\s*:\s*)(\d+)",
)


def _parse_hp_option(hp) -> int | None:
    """Turn the `hp` option into a fixed value, or None to mean 'leave HP in the shuffle'.

    'shuffle' (or blank) -> None; 'one' -> 1; a numeric string/int -> that number (>=1).
    Anything else -> None, so an unrecognised value degrades to the normal shuffle rather
    than doing something surprising.
    """
    if hp is None:
        return None
    s = str(hp).strip().lower()
    if s in ("", "shuffle"):
        return None
    if s == "one":
        return 1
    try:
        return max(1, int(s))
    except ValueError:
        return None


def _fit_int_to_width(value: int, width: int) -> bytes:
    """The integer `value` written into a field of exactly `width` bytes, size-preserving.

    Padded with leading spaces (the game parses the number, not the padding). A value too
    large for the field is clamped to that field's all-nines maximum, so nothing ever grows.
    """
    v = max(0, value)
    hi = int("9" * width)
    v = min(v, hi)
    return str(v).encode().rjust(width, b" ")


def _set_hp_uniform(blob: bytes, blocks, value: int, rep: Report) -> bytes:
    """Set every HP field in `blocks` to `value`, each written inside its own field width.

    This is the "all enemies at one HP" lever. HP fields come in several byte widths
    (w2 / w3 / w4 on the hostile side), and the size rule forbids changing a field's
    length — so the value is right-justified into whatever width each field already has,
    and clamped down if it will not fit. Reversible field-by-field, nothing shifts.
    """
    out = bytearray(blob)
    hits = 0
    for s, e in blocks:
        seg = bytes(out[s:e])
        for rx in HP_FIELDS:
            for m in re.finditer(rx, seg):
                width = len(m.group(2))
                new = _fit_int_to_width(value, width)
                if new != m.group(2):
                    a = s + m.start(2)
                    out[a:a + width] = new
                    hits += 1
    rep.changed += hits
    rep.notes.append(f"{hits} HP fields set to {value} (padded to each field's own width)")
    return bytes(out)


def t_enemy_stats_random(blob, rng, style="floor", hp="shuffle"):
    """Shuffle the hostile creatures' own numbers between each other — or flatten their HP.

    Randomized enemy HP and stats: every numeric field in the hostile `#Character Info`
    blocks — hit points, ability points, aggressiveness, attack radius, view/detection
    range, movement rates — is permuted among the other hostiles. `enemy_difficulty`
    *scales* these; this *shuffles* them, so the mix changes without the average moving.

    style='floor' (default) keeps every value in its own byte-width class, so a boss stays
    a boss; style='pure' lets values cross widths where they fit, so a boss can end up
    weak. Only the hostile side is touched. Size-preserving.

    hp='one' overrides the shuffle and sets EVERY hostile HP field to 1 (a one-hit-kill
    run); hp='<number>' sets them all to that number, clamped to each field's own width;
    hp='shuffle' (default) leaves HP in the stat shuffle. Because HP fields differ in byte
    width, a uniform value is padded into each field rather than changing its length.
    """
    rep = Report("enemy_stats_random")
    style = str(style)
    if style not in STAT_STYLES:
        rep.notes.append(f"unknown style {style!r} - pick one of {list(STAT_STYLES)}; "
                         f"nothing changed")
        return blob, rep
    blocks = _hostile_char_blocks(blob)
    if len(blocks) < 2:
        rep.notes.append(f"only {len(blocks)} hostile #Character Info block(s) - nothing to shuffle")
        return blob, rep

    # "all enemies at one HP" — a fixed value wins over the shuffle for the HP fields.
    hp_value = _parse_hp_option(hp)
    if hp_value is not None:
        out = _set_hp_uniform(blob, blocks, hp_value, rep)
        rep.notes.insert(0, f"{len(blocks)} hostile creature definitions, hp={hp_value} (uniform)")
        rep.notes.append("every hostile HP flattened; other stats left as vanilla")
        rep.notes.append("size-preserving; each HP written inside its own field width")
        return out, rep

    out = _shuffle_stats_in_blocks(blob, rng, blocks, style, rep)
    rep.notes.insert(0, f"{len(blocks)} hostile creature definitions, style={style}")
    rep.notes.append("hostiles shuffled among themselves only; friendly side untouched")
    rep.notes.append("size-preserving; every value rewritten inside a field of its own width")
    return out, rep


def t_player_stats_random(blob, rng, style="floor"):
    """Shuffle the playable party's numbers between each other.

    Randomized player stats: the same numeric fields as the enemy version, but taken from
    the `$Team: "friendly"` `#Character Info` blocks — the party — and permuted among
    themselves. There is no Strength/Dexterity/Intelligence in this game; "player stats"
    means HP, ability points, aggression, attack radius, field-of-view, detection and the
    speed-up / slow-down rates.

    style='floor' (default) keeps each value in its own byte-width class; style='pure'
    lets them cross widths where they fit. Only the friendly side is touched.
    Size-preserving.
    """
    rep = Report("player_stats_random")
    style = str(style)
    if style not in STAT_STYLES:
        rep.notes.append(f"unknown style {style!r} - pick one of {list(STAT_STYLES)}; "
                         f"nothing changed")
        return blob, rep
    blocks = _friendly_char_blocks(blob)
    if len(blocks) < 2:
        rep.notes.append(f"only {len(blocks)} friendly #Character Info block(s) - nothing to shuffle")
        return blob, rep
    out = _shuffle_stats_in_blocks(blob, rng, blocks, style, rep)
    rep.notes.insert(0, f"{len(blocks)} friendly creature definitions, style={style}")
    rep.notes.append("party shuffled among themselves only; hostile side untouched")
    rep.notes.append("size-preserving; every value rewritten inside a field of its own width")
    return out, rep


# --------------------------------------------------------------------------- #
# Rooms - the safe half of "randomised rooms"
#
# A level's script entry is one `#Navpoints` section: it starts at the `#Navpoints` header and
# runs to the next `#End`. Everything that populates the level - NPCs, monsters, props,
# shopkeepers - is a `$Name:` record carrying `$Start position: "<navpoint>"`, and every one of
# those anchors is a navpoint DEFINED in that same section (measured on the retail disc:
# 4,257 of 4,257 placements). `rooms_shuffle` permutes those anchors between placements inside
# one level, among anchors of the same namespace (`$npc`, `$hostile`, ...) and the same width,
# so a level is furnished differently while every anchor still exists in the level it names and
# the stream never changes size. Doors, quests, the level graph and the navpoint definitions are
# never touched, so an unreachable region is impossible by construction (PLANNED.md 1.5).
#
# Pinned, never moved: `$player*` (a level's own start slots) and `$zzz*` (the disarm sentinel
# `enemies_none` writes) - permuting either would undo work another transform owns.
_ROOMS_SECTION_RE = re.compile(rb"#Navpoints")
_ROOMS_END_RE = re.compile(rb"#End")
_ROOMS_KIND_RE = re.compile(rb"[A-Za-z]+")
_ROOMS_PINNED_KINDS = (b"$player", b"$zzz")


def _rooms_kind(val: bytes) -> bytes:
    """The anchor's namespace: `$npc033` -> `$npc`, `$hostile09-01` -> `$hostile`."""
    if val[:1] == b"$":
        m = _ROOMS_KIND_RE.match(val, 1)
        return b"$" + (m.group(0) if m else b"")
    return b"<raw>"


def _rooms_sections(blob: bytes) -> list[tuple[int, int]]:
    """(start, end) for every level script section: `#Navpoints` to the next `#End`/`#Navpoints`."""
    import bisect
    navs = [m.start() for m in _ROOMS_SECTION_RE.finditer(blob)]
    ends = [m.start() for m in _ROOMS_END_RE.finditer(blob)]
    out = []
    for i, p in enumerate(navs):
        nxt = navs[i + 1] if i + 1 < len(navs) else len(blob)
        j = bisect.bisect_right(ends, p)
        if j < len(ends):
            nxt = min(nxt, ends[j])
        out.append((p, nxt))
    return out


def t_rooms_shuffle(blob, rng, how="shuffle"):
    """Permute `$Start position` anchors BETWEEN placements INSIDE one level.

    The safe half of random rooms. A level's population is its placements - each a `$Name:`
    record with a `$Start position: "<navpoint>"` anchor - and every anchor names a navpoint
    defined in the same level script section (`#Navpoints` .. `#End`). Permuting those anchors
    within the section leaves the level graph, the doors, the quests and the navpoint
    definitions exactly as they were; every destination anchor still exists, so nothing can
    become unreachable. Anchors are only traded between placements of the same namespace and
    the same byte width, so the stream keeps its length.

    `how`:
      * ``shuffle`` (default) - every group's anchors are permuted.
      * ``swap`` - pairs inside each group are traded instead.
    A group of one is left alone and reported. `$player*` (level start slots) and `$zzz*`
    (the `enemies_none` sentinel) are pinned and never move.
    """
    import bisect
    rep = Report("rooms_shuffle")
    how = str(how)
    if how not in ("shuffle", "swap"):
        rep.notes.append(f"unknown how {how!r} - pick 'shuffle' or 'swap'; nothing changed")
        return blob, rep

    sections = _rooms_sections(blob)
    if not sections:
        rep.notes.append("no #Navpoints sections found - nothing changed")
        return blob, rep
    starts = [s for s, _ in sections]

    groups: dict[tuple[int, bytes, int], list[tuple[int, bytes]]] = {}
    pinned = 0
    for s, e in _placement_records(blob):
        m = START_POS_RE.search(blob, s, e)
        if not m:
            continue
        val = m.group(2)
        kind = _rooms_kind(val)
        if kind in _ROOMS_PINNED_KINDS:
            pinned += 1
            continue
        sec = bisect.bisect_right(starts, s) - 1
        if sec < 0:
            continue
        groups.setdefault((sec, kind, len(val)), []).append((m.start(2), val))

    if not groups:
        rep.notes.append("no movable $Start position anchors found - nothing changed")
        return blob, rep

    out = bytearray(blob)
    changed = 0
    held = 0
    for _key, members in sorted(groups.items()):
        if len(members) < 2:
            held += len(members)
            continue
        vals = [v for _o, v in members]
        if how == "swap":
            order = list(range(len(vals)))
            rng.shuffle(order)
            for i in range(0, len(order) - 1, 2):
                a, b = order[i], order[i + 1]
                vals[a], vals[b] = vals[b], vals[a]
        else:
            rng.shuffle(vals)
        for (off, old), new in zip(members, vals):
            if new != old:
                out[off:off + len(old)] = new
                changed += 1

    rep.changed = changed
    rep.notes.append(f"{len(groups)} within-level anchor group(s) across "
                     f"{len({k[0] for k in groups})} level section(s)")
    rep.notes.append(f"{held} lone placement(s) held (no same-kind, same-width partner)")
    if pinned:
        rep.notes.append(f"{pinned} pinned ($player* start slots / $zzz* disarm sentinel)")
    rep.notes.append("anchors permuted inside one level only; graph, doors, quests, navpoints untouched")
    rep.notes.append("size-preserving: an anchor only ever moves into a field of its own width")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Boss Rush - gather a level's bosses onto one navpoint of that same level
#
# A boss is a placement record carrying `+Boss` (measured 2026-09-30: 25 of them across 11
# level sections). The requested mode is "all bosses in one arena", but the anchor field is a
# `$Start position: "<navpoint>"` NAME and navpoint names are NOT globally unique - `$npc001`
# is declared in 107 different level sections (same for `$player1-01`, 102). So the name is
# resolved per level, and a boss sent to a navpoint that its OWN level does not declare simply
# never spawns (the `$zzz` mechanism `enemies_none` relies on, in-game verified).
#
# Therefore the sound, size-preserving version gathers each level's bosses WITHIN that level:
# every `+Boss` placement whose anchor is N bytes long is re-pointed at one navpoint of exactly
# N bytes declared in the same level, so they stand together and are still found. The
# cross-level single arena is documented as blocked (it needs placement records moved between
# level entries, i.e. extra bytes - the archive-slack question) in PLANNED.md.
_NAVP_DEF_RE = re.compile(rb'(?m)^[ \t]*\$Name\s*:\s*"(\$[^"]+)"[ \t]*\r?\n[ \t]*\$Type')


def _section_navpoints(blob: bytes, a: int, b: int) -> set[bytes]:
    """Navpoint names DECLARED in [a, b): a `$Name: "$..."` line directly followed by `$Type:`."""
    return {m.group(1) for m in _NAVP_DEF_RE.finditer(blob, a, b)}


def t_boss_rush(blob, rng, arena="auto"):
    """Gather a level's boss placements onto a single navpoint of that SAME level.

    `arena` picks the level section to gather in: ``auto`` (default) = the section that holds
    the most `+Boss` placements; or an integer section index. Because a navpoint name resolves
    only inside the level that declares it, bosses in other levels are left alone and reported -
    a true single arena is a documented blocked extension (see the banner above and PLANNED.md).

    Size-preserving: an anchor is only ever replaced by a navpoint of the exact same byte
    length, declared in the same section, so the entry cannot grow or shrink. A boss whose
    width has no navpoint in the level is left where it is and counted as held.
    """
    import bisect
    rep = Report("boss_rush")
    sections = _rooms_sections(blob)
    if not sections:
        rep.notes.append("no #Navpoints sections found - nothing changed")
        return blob, rep
    starts = [s for s, _ in sections]

    bosses: list[tuple[int, int, bytes]] = []
    for s, e in _placement_records(blob):
        seg = blob[s:e]
        if b"+Boss" not in seg:
            continue
        m = START_POS_RE.search(seg)
        if not m:
            continue
        sec = bisect.bisect_right(starts, s) - 1
        if sec >= 0:
            bosses.append((sec, s + m.start(2), m.group(2)))
    if not bosses:
        rep.notes.append("no +Boss placements found - nothing changed")
        return blob, rep

    by_sec: dict[int, list] = {}
    for sec, off, val in bosses:
        by_sec.setdefault(sec, []).append((off, val))
    rep.notes.append(f"boss inventory: {len(bosses)} +Boss placement(s) across "
                     f"{len(by_sec)} level section(s)")

    if str(arena) in ("auto", "None", ""):
        arena_sec = max(by_sec, key=lambda k: (len(by_sec[k]), -k))
    else:
        try:
            arena_sec = int(arena)
        except (TypeError, ValueError):
            rep.notes.append(f"unusable arena {arena!r} - refused, nothing changed")
            return blob, rep
        if arena_sec not in by_sec:
            rep.notes.append(f"arena section {arena_sec} holds no +Boss placement - nothing changed")
            return blob, rep

    a, b = sections[arena_sec]
    navs = _section_navpoints(blob, a, b)
    members = by_sec[arena_sec]
    if not navs:
        rep.notes.append(f"arena section {arena_sec} declares no navpoints - nothing changed")
        return blob, rep

    out = bytearray(blob)
    moved = 0
    held = 0
    for w in sorted({len(v) for _o, v in members}):
        pool = sorted(n for n in navs if len(n) == w)
        if not pool:
            held += sum(1 for _o, v in members if len(v) == w)
            continue
        target = pool[0]                      # every width class gathers onto ONE navpoint
        for off, val in members:
            if len(val) != w:
                continue
            if val == target:
                held += 1
                continue
            out[off:off + w] = target
            moved += 1

    rep.changed = moved
    elsewhere = sum(len(v) for k, v in by_sec.items() if k != arena_sec)
    rep.notes.append(f"arena = section {arena_sec}: {len(members)} boss placement(s), "
                     f"{len(navs)} navpoints; {held} held (no same-width navpoint there)")
    if elsewhere:
        rep.notes.append(f"{elsewhere} boss placement(s) in other levels left unchanged - "
                         f"navpoint names repeat across levels, so an anchor only resolves in "
                         f"its own level (a global arena is blocked, see PLANNED.md)")
    rep.notes.append("size-preserving: an anchor only ever becomes a same-width navpoint")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Item Hunt - goods out of the shop stock and the quest rewards, into the containers
# --------------------------------------------------------------------------- #
# A shop's stock is a `+Buy List:` / `+Sell List:` header followed by one quoted item name per
# line, terminated by `$End` (measured 2026-09-30: 47 + 47 lists, 4,455 entries, 332 distinct
# names). A quest reward is a `+Gain Item: "<name>"` field (157 of them). The destinations are
# the container yields `chest_items` already knows: the `+Messagebox:` name in a block that also
# carries `+Give:` (92 slots, 35 distinct yields).
_SHOP_LIST_RE = re.compile(rb"\+Buy List:|\+Sell List:")
_SHOP_END = b"$End"
_QUOTED_RE = re.compile(rb'"([^"]+)"')
_GAIN_ITEM_RE = re.compile(rb'\+Gain Item:\s*"([^"]+)"')


def _shop_stock(blob: bytes) -> list[tuple[int, int, bytes]]:
    """(start, end, name) for every item name inside a shop `+Buy List:` / `+Sell List:` body."""
    out = []
    for m in _SHOP_LIST_RE.finditer(blob):
        end = blob.find(_SHOP_END, m.end())
        if end < 0:
            continue
        body = blob[m.end():end]
        for q in _QUOTED_RE.finditer(body):
            s = m.end() + q.start(1)
            out.append((s, s + len(q.group(1)), q.group(1)))
    return out


def t_item_hunt(blob, rng, sources="both"):
    """Trade a good out of the shop stock / quest rewards and into a container, equal width only.

    `sources`: ``shops`` (the `+Buy List:`/`+Sell List:` stock), ``quest`` (the `+Gain Item:`
    rewards), or ``both`` (default).

    The move is an EXCHANGE, never a deletion: the good's name is written into an equal-length
    container yield, and the yield that was in that container takes the good's old slot on the
    shelf / in the reward. That keeps every entry the same byte length (so the 527-entry archive
    never shifts) and loses nothing - it only decides that the good has to be FOUND rather than
    bought or handed over. A good with no equal-width container slot is left in place and
    counted as held, exactly as the acceptance criteria require.

    Gold yields are pooled out (they are the 4-character `Gold`/`gold` and never trade with a
    real item name), and so is anything already identical to its candidate slot.
    """
    rep = Report("item_hunt")
    sources = str(sources)
    if sources not in ("shops", "quest", "both"):
        rep.notes.append(f"unknown sources {sources!r} - pick shops/quest/both; nothing changed")
        return blob, rep

    goods: list[tuple[int, int, bytes]] = []
    if sources in ("shops", "both"):
        s0 = _shop_stock(blob)
        goods += s0
        rep.notes.append(f"{len(s0)} shop-stock item(s)")
    if sources in ("quest", "both"):
        q0 = [(m.start(1), m.end(1), m.group(1)) for m in _GAIN_ITEM_RE.finditer(blob)]
        goods += q0
        rep.notes.append(f"{len(q0)} quest-reward item(s)")

    slots = [(s, e, n) for s, e, n in _container_yields(blob) if n.lower() != _GOLD]
    if not goods or not slots:
        rep.notes.append("nothing to move (no goods or no non-gold container slots) - nothing changed")
        return blob, rep

    by_w_goods: dict[int, list] = {}
    for t in goods:
        by_w_goods.setdefault(len(t[2]), []).append(t)
    by_w_slots: dict[int, list] = {}
    for t in slots:
        by_w_slots.setdefault(len(t[2]), []).append(t)

    out = bytearray(blob)
    moved = 0
    for w in sorted(set(by_w_goods) & set(by_w_slots)):
        g = by_w_goods[w][:]
        s = by_w_slots[w][:]
        rng.shuffle(g)
        rng.shuffle(s)
        for (gs, ge, gn), (ss, se, sn) in zip(g, s):
            if gn == sn:
                continue
            out[gs:ge] = sn
            out[ss:se] = gn
            moved += 1

    rep.changed = moved
    rep.notes.append(f"{len(goods)} good(s) vs {len(slots)} non-gold container slot(s); "
                     f"{moved} exchanged (good -> container, old yield -> shelf/reward)")
    rep.notes.append(f"{max(0, len(goods) - moved)} good(s) left in place "
                     f"(no equal-width container slot)")
    rep.notes.append("size-preserving: a name only ever trades inside its own width")
    return bytes(out), rep


def t_enemy_hp_set(blob, rng, value=1):
    """Set EVERY hostile creature's HP fields to a single user-chosen value.

    Standalone size-preserving lever, independent of enemy_stats_random's bundled
    `hp` option. Writes the same number into each $Max Hit Points and $Hit Points
    of every hostile #Character Info block, right-justified inside the field's own
    byte width (all-9s clamp if the value will not fit). HP only — attack, damage
    and level fields are never touched. rng is unused: the value is deterministic.
    """
    rep = Report("enemy_hp_set")
    try:
        v = max(1, int(value))
    except (TypeError, ValueError):
        rep.notes.append(f"unusable value {value!r} - refused, nothing changed")
        return blob, rep
    blocks = _hostile_char_blocks(blob)
    if not blocks:
        rep.notes.append("no hostile #Character Info blocks found - nothing changed")
        return blob, rep
    out = _set_hp_uniform(blob, blocks, v, rep)
    rep.notes.insert(0, f"{len(blocks)} hostile creature definitions, hp set to {v}")
    rep.notes.append("HP only; attack/damage/level untouched")
    rep.notes.append("size-preserving; each HP written inside its own field width")
    return out, rep


# NOTE: Summoner's hostile creatures have NO defence/protection stat in the data tables
# (verified: 0 `$Protection` fields across all 80 hostile #Character Info blocks). The only
# combat-softening lever that exists in the tables is their `$Damage` (how hard they hit) and
# their HP (`enemy_hp_set`). So "make enemies easier" = lower their damage. This transform does
# that; there is no defence value to lower.
_HOSTILE_DAMAGE_RE = re.compile(rb"(\$Damage\s*:\s*)(\d+)")


def t_enemy_damage_set(blob, rng, value=0):
    """Set every hostile creature's `$Damage` (how hard it hits) to a chosen value - lower = softer.

    Summoner enemies have no defence stat, so this is the real "make enemies weaker" lever
    besides HP. `$Damage` lives in each hostile `#Character Info` block (distinct from weapon
    `$Damage`, which is scoped by an adjacent `$Damage Type` and NOT touched here). Default 0 =
    enemies deal minimal damage. Right-justified into each field's own width, clamped. rng unused.
    """
    rep = Report("enemy_damage_set")
    try:
        v = max(0, int(value))
    except (TypeError, ValueError):
        rep.notes.append(f"unusable value {value!r} - refused, nothing changed")
        return blob, rep
    blocks = _hostile_char_blocks(blob)
    if not blocks:
        rep.notes.append("no hostile #Character Info blocks found - nothing changed")
        return blob, rep
    out = bytearray(blob)
    hits = 0
    for s, e in blocks:
        seg = bytes(out[s:e])
        for m in _HOSTILE_DAMAGE_RE.finditer(seg):
            width = len(m.group(2))
            new = _fit_int_to_width(v, width)
            if new != m.group(2):
                a = s + m.start(2)
                out[a:a + width] = new
                hits += 1
    if hits == 0:
        rep.notes.append("no hostile $Damage fields found (or already at value) - nothing changed")
        return bytes(out), rep
    rep.changed += hits
    rep.notes.insert(0, f"{len(blocks)} hostile creature definitions, $Damage set to {v} "
                        f"({hits} fields)")
    rep.notes.append("enemy attack damage only, hostiles only; weapons and the party are untouched")
    rep.notes.append("NOTE: enemies have no defence stat in the tables; damage is the soften lever")
    rep.notes.append("size-preserving; each value written inside its own field width")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Gear stats - weapon $Damage and armour $Protection
#
# These fields live on ITEM records, NOT on creatures. Two record shapes matter:
#
#   $Type:  "weapon"                 <- (or "Weapon") a weapon item
#     $Skill:  "sword weapons"
#     $Class:  "swords"
#     $Damage: 35                    <- attack power  (also creatures carry $Damage,
#     $Damage Type: "..."               so we ONLY touch $Damage that is followed by
#                                       a $Damage Type line, which is a weapon marker)
#
#   $Armor:                          <- an armour item record header
#     $Name:  "leather cap"
#     $Protection: 8                 <- defence  (creatures also carry $Protection inside
#     $Ore: 0                           #Character Info; we scope armour by requiring the
#                                       nearest preceding "$Armor:" header)
#
# Both edits are size-preserving: the number is right-justified into the field's own byte
# width and clamped to that width's all-nines maximum, exactly like enemy_hp_set. So a value
# of 999 becomes "99" in a 2-wide field, "999" in a 3-wide field, etc. - never larger.
# --------------------------------------------------------------------------- #

# A weapon's $Damage is the one immediately followed (within a short window) by a
# "$Damage Type:" line. That marker is what tells a weapon record apart from a creature's
# bare $Damage inside #Character Info.
_WEAPON_DAMAGE_RE = re.compile(
    rb"(\$Damage\s*:\s*)(\d+)(?=[^\n]*\n[^\n]*\$Damage Type)")
# Armour records begin with a "$Armor:" header line; everything up to the next "$Armor:" or
# a new "#" block header belongs to one armour item. $Protection inside such a span is armour.
_ARMOR_HEADER_RE = re.compile(rb"\$Armor\s*:")
_PROTECTION_RE = re.compile(rb"(\$Protection\s*:\s*)(\d+)")
_ARMOR_FIELD_RE = re.compile(rb"(\$Armor\s*:\s*)(\d+)")   # a numeric $Armor: value, if any


def _armor_spans(blob: bytes):
    """(start, end) byte spans that belong to armour item records.

    An armour record starts at a "$Armor:" header and runs until the next "$Armor:" header
    or the next "#..." block header, whichever comes first. Scoping $Protection to these
    spans keeps us off creature $Protection fields in #Character Info.
    """
    starts = [m.start() for m in _ARMOR_HEADER_RE.finditer(blob)]
    if not starts:
        return []
    # next block header after each start bounds the record
    spans = []
    for i, s in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else len(blob)
        # also stop at the next "#" block header if it comes sooner
        hdr = blob.find(b"\n#", s, nxt)
        end = hdr if hdr != -1 else nxt
        spans.append((s, end))
    return spans


def t_weapon_attack_max(blob, rng, value=999):
    """Set every WEAPON's $Damage to a single high value (default 999, clamped per field).

    Scope: only $Damage fields that are part of a weapon record (identified by an adjacent
    "$Damage Type:" line), so creature damage is never touched. Size-preserving: the value
    is right-justified into each field's own width and clamped to that width's maximum.
    rng is unused - deterministic.
    """
    rep = Report("weapon_attack_max")
    try:
        v = max(1, int(value))
    except (TypeError, ValueError):
        rep.notes.append(f"unusable value {value!r} - refused, nothing changed")
        return blob, rep
    out = bytearray(blob)
    hits = 0
    # iterate over a snapshot so match offsets stay valid (widths never change)
    for m in list(_WEAPON_DAMAGE_RE.finditer(bytes(out))):
        width = len(m.group(2))
        new = _fit_int_to_width(v, width)
        if new != m.group(2):
            a = m.start(2)
            out[a:a + width] = new
            hits += 1
    if hits == 0:
        rep.notes.append("no weapon $Damage fields found (or already maxed) - nothing changed")
        return bytes(out), rep
    rep.changed += hits
    rep.notes.insert(0, f"{hits} weapon $Damage fields set to {v}")
    rep.notes.append("weapons only (scoped by the adjacent $Damage Type marker); creatures untouched")
    rep.notes.append("size-preserving; each value written inside its own field width (all-9s clamp)")
    return bytes(out), rep


_XP_GAINED_RE = re.compile(rb"(\$Experience Gained\s*:\s*)(\d+)")


def t_enemy_xp_random(blob, rng, style="floor"):
    """Randomize how much XP each mob gives on death.

    `$Experience Gained` is the per-creature kill reward, one per hostile `#Character Info`
    block (distinct from the global xp_scale/xp_boost multipliers and from scripted `+AddXP:`
    quest rewards). We shuffle those values AMONG the hostiles, so a trash mob may be worth a
    boss's XP and vice-versa. Size-preserving: a value only moves into a field of its own byte
    width (style=floor), so nothing grows. style=pure lets values cross widths where they fit.
    Hostiles only - the party's own blocks are never touched.
    """
    rep = Report("enemy_xp_random")
    style = str(style)
    if style not in STAT_STYLES:
        rep.notes.append(f"unknown style {style!r} - pick one of {list(STAT_STYLES)}; "
                         f"nothing changed")
        return blob, rep
    blocks = _hostile_char_blocks(blob)
    if not blocks:
        rep.notes.append("no hostile #Character Info blocks found - nothing changed")
        return blob, rep

    # collect every hostile $Experience Gained value with its absolute offset + width
    entries = []  # (abs_off, width, value_bytes)
    for s, e in blocks:
        seg = bytes(blob[s:e])
        for m in _XP_GAINED_RE.finditer(seg):
            entries.append((s + m.start(2), len(m.group(2)), m.group(2)))
    if len(entries) < 2:
        rep.notes.append(f"only {len(entries)} $Experience Gained field(s) - nothing to shuffle")
        return blob, rep

    # group by width (floor) or allow cross-width where it fits (pure), then permute values
    out = bytearray(blob)
    hits = 0
    if style == "floor":
        from collections import defaultdict
        by_w = defaultdict(list)
        for off, w, val in entries:
            by_w[w].append((off, val))
        for w, items in by_w.items():
            vals = [v for _o, v in items]
            order = list(range(len(vals)))
            rng.shuffle(order)
            for (off, _old), j in zip(items, order):
                new = vals[j]
                if new != _old:
                    out[off:off + w] = new
                    hits += 1
    else:  # pure: permute all values, right-justify into each destination width, clamp
        vals = [int(v) for _o, _w, v in entries]
        order = list(range(len(vals)))
        rng.shuffle(order)
        for (off, w, old), j in zip(entries, order):
            new = _fit_int_to_width(vals[j], w)
            if new != old:
                out[off:off + w] = new
                hits += 1

    rep.changed += hits
    rep.notes.insert(0, f"{len(entries)} hostile $Experience Gained fields, {hits} moved "
                        f"(style={style})")
    rep.notes.append("hostiles only; the party is untouched")
    rep.notes.append("size-preserving; each value stays inside a field of its own width")
    return bytes(out), rep


_DROP_WEIGHT_RE = re.compile(rb'(\+Drop:\s*"[^"]+"\s*)(\d+)')


def t_enemy_drops_always(blob, rng):
    """Force every existing enemy drop to be guaranteed.

    A `+Drop: "Item" <weight>` entry's number is the drop CHANCE (2..100 in the shipped data;
    100 = always). This maxes every weight to the largest value its field width holds - so a
    3-wide field becomes 100 (guaranteed), a 2-wide 99, a 1-wide 9. Any enemy that CAN drop an
    item now (almost) always does. Size-preserving; rng unused (deterministic).

    HONEST LIMIT: this can only boost drops that already exist. An enemy with NO `+Drop` entry
    cannot be given one without adding bytes (which would break size-preservation), so a truly
    drop-less enemy stays drop-less. In the shipped data the +Drop entries are attached to
    creatures' attack/death records, not the bare stat block, so coverage is broad but not
    provably every single hostile.
    """
    rep = Report("enemy_drops_always")
    out = bytearray(blob)
    hits = 0
    for m in list(_DROP_WEIGHT_RE.finditer(bytes(out))):
        width = len(m.group(2))
        # the field's max that still fits: min(100, all-nines-of-width). 100 needs 3 digits.
        cap = 100 if width >= 3 else int("9" * width)
        new = _fit_int_to_width(cap, width)
        if new != m.group(2):
            a = m.start(2)
            out[a:a + width] = new
            hits += 1
    if hits == 0:
        rep.notes.append("no +Drop weights found (or already maxed) - nothing changed")
        return bytes(out), rep
    rep.changed += hits
    total = len(_DROP_WEIGHT_RE.findall(bytes(blob)))
    rep.notes.insert(0, f"{total} +Drop weights, {hits} raised to their field max (100 where it fits)")
    rep.notes.append("boosts EXISTING drops to guaranteed; cannot add a drop to a drop-less enemy "
                     "(that needs extra bytes and would break size-preservation)")
    rep.notes.append("size-preserving; each weight written inside its own field width")
    return bytes(out), rep


def t_enemy_xp_set(blob, rng, value=999):
    """Set EVERY hostile creature's $Experience Gained to one chosen value - fast leveling.

    The kill reward for every hostile becomes `value`, right-justified into each field's own byte
    width and clamped to that width's all-nines maximum (so a 4-digit reward field can hold 9999,
    a 3-digit one 999, etc. - the disc never changes size). Set it high to level fast. Distinct
    from enemy_xp_random (which shuffles) and from the global xp_scale/xp_boost multipliers.
    rng is unused: the value is deterministic.
    """
    rep = Report("enemy_xp_set")
    try:
        v = max(0, int(value))
    except (TypeError, ValueError):
        rep.notes.append(f"unusable value {value!r} - refused, nothing changed")
        return blob, rep
    blocks = _hostile_char_blocks(blob)
    if not blocks:
        rep.notes.append("no hostile #Character Info blocks found - nothing changed")
        return blob, rep
    out = bytearray(blob)
    hits = 0
    for s, e in blocks:
        seg = bytes(out[s:e])
        for m in _XP_GAINED_RE.finditer(seg):
            width = len(m.group(2))
            new = _fit_int_to_width(v, width)
            if new != m.group(2):
                a = s + m.start(2)
                out[a:a + width] = new
                hits += 1
    if hits == 0:
        rep.notes.append("no $Experience Gained fields found (or already at value) - nothing changed")
        return bytes(out), rep
    rep.changed += hits
    rep.notes.insert(0, f"{len(blocks)} hostile creature definitions, "
                        f"$Experience Gained set to {v} ({hits} fields)")
    rep.notes.append("XP-on-kill only; other stats untouched. Set high to level fast.")
    rep.notes.append("size-preserving; each value written inside its own field width (all-9s clamp)")
    return bytes(out), rep


def t_armor_protect_max(blob, rng, value=999):
    """Buff armour: set every armour item's $Protection (and numeric $Armor:) high.

    Scope: only $Protection fields inside armour record spans (led by a "$Armor:" header),
    so creature $Protection inside #Character Info is never touched. Size-preserving and
    clamped per field. rng is unused - deterministic.
    """
    rep = Report("armor_protect_max")
    try:
        v = max(1, int(value))
    except (TypeError, ValueError):
        rep.notes.append(f"unusable value {value!r} - refused, nothing changed")
        return blob, rep
    out = bytearray(blob)
    spans = _armor_spans(bytes(out))
    if not spans:
        rep.notes.append("no $Armor: record headers found - nothing changed")
        return bytes(out), rep
    hits = 0
    for s, e in spans:
        seg = bytes(out[s:e])
        for rx in (_PROTECTION_RE, _ARMOR_FIELD_RE):
            for m in rx.finditer(seg):
                width = len(m.group(2))
                new = _fit_int_to_width(v, width)
                if new != m.group(2):
                    a = s + m.start(2)
                    out[a:a + width] = new
                    hits += 1
    if hits == 0:
        rep.notes.append("no armour $Protection fields found (or already maxed) - nothing changed")
        return bytes(out), rep
    rep.changed += hits
    rep.notes.insert(0, f"{len(spans)} armour records, {hits} protection fields set to {v}")
    rep.notes.append("armour only (scoped to $Armor: record spans); creatures untouched")
    rep.notes.append("size-preserving; each value written inside its own field width (all-9s clamp)")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Doors - where a door LEADS, which is a name in the level's own `.tbl`
#
# A door is one entry of a level file's `#Triggers` block:
#
#   //-------------
#   #Triggers
#   //-------------
#
#   $Trigger: "catacombs"          <- THE DESTINATION LEVEL NAME (inline, fixed width)
#       +Id: "load level"          <- this is what makes it a door and not an animation cue
#       +Index: 1                  <- player start id used at the destination
#       +Type: "spline"
#       +Spline name: "$loadarea01"
#
# `level_script_check_level_load` (0x002023C0) copies the trigger's name straight into
# `Level_data.name`, and the engine then builds `<name>.s3d` / `<name>.p3d` / `<name>_script.tbl`
# from it. The name IS the destination, so rewriting that one quoted string redirects a door:
# no binary patch, no new bytes, fully reversible. Proven end to end - a rewritten door was
# watched loading a different level - in `DOOR-REMAP.md` sections 3, 4 and 4.5.
#
# 218 of them exist on the retail disc, spread over the 52 level files. A `$Trigger:` in a
# *character* `.tbl` is animation timing and carries no `+Id:` - hence the two-part rule below.
# --------------------------------------------------------------------------- #
DOOR_TRIGGER_RE = re.compile(rb'\$Trigger:\s*"([^"\r\n]{1,40})"')
DOOR_ID_RE = re.compile(rb'\+Id:\s*"([^"]{0,40})"')
DOOR_LEVEL_RE = re.compile(rb"Level file for ([^\r\n*]+)")
DOOR_BLOCK_WINDOW = 400

# Every name the game can resolve to a level index: the 51 `Level_info` names from the
# executable's level-name table (`0x1213E68`, stride 0x3C). `level_script_get_level_index`
# looks a name up in that table with a case-insensitive linear search and returns -1 for an
# unknown name, which the loader then uses as an index - so this table *is* the list of legal
# destinations. Metadata only: the names, never the levels.
DOOR_TARGET_NAMES = (
    "Wolong", "Catacombs", "test", "masad", "worldmap1", "lenele1b", "lenele1c", "lenele1d",
    "lenele1e", "sewer", "rand-hills01", "IkaemosBottomInt", "IkaemosTopInt", "IkaemosExt",
    "KhosaniLab", "IonaExt", "WolongCaverns", "TempleInt", "rand-forest01", "rand-forestnite1",
    "Liangshan", "Rand-Desert", "IonaExt02", "KhosaniStrng", "LPalaceInt", "tancredhouse",
    "LPalaceInt02", "KhosaniLab2", "Wolong2", "eleh", "lenele2aa", "lenele2ab", "lenele3a",
    "lenele3d", "jadetemple", "lenele1aa", "lenele1ab", "TempleInt2", "IkaemosExt2",
    "IkaemosBottomInt2", "Rand-HillsNite01", "Rand-Iceland01", "Rand-Grassland01",
    "Rand-Orenia01", "Rand-OreniaNite01", "Rand-DesertNite01", "Rand-GrasslandNite01",
    "Rand-IcelandNite01", "endgame", "lenele2d", "sewerboss",
)
# Two of those are legal *names* but not legal *targets*: `test` is a developer level, and
# `endgame` is the Forge the whole run is aimed at - "never into the endgame" is one of the
# recorded design constraints (RESEARCH-ENTRANCE-LOGIC.md section 4).
DOOR_TARGET_EXCLUDE = frozenset({"test", "endgame"})
DOOR_SENTINEL = "$zzz"      # reserved by the enemy disarm (`enemies_none`); never emitted

# Doors whose SOURCE level is the opening area or the overworld hub are left alone. Their loads
# passed every static check (real Level_info name, len<=old, +Index slot present, +Script safe)
# yet still bounced to the main menu in game ("Exit to Unknown?" -> title). The overworld/masad
# use a load path we cannot fully validate from the tables, and these are the very first
# transitions every run hits, so a bad remap is game-breaking. Held until the crossing is
# understood (see DOOR-REMAP.md / PLANNED.md). Matched by _door_key against the door's source.
DOOR_SOURCE_EXCLUDE = frozenset({"masad", "worldmap", "worldmap1"})

DOOR_HOW_VALUES = ("shuffle", "swap", "off")


def _door_key(name) -> str:
    """A comparison key for a level name: lower case, letters and digits only."""
    s = name.decode("latin-1") if isinstance(name, (bytes, bytearray)) else str(name)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _door_same_level(src_display: str | None, candidate: str) -> bool:
    """Is `candidate` the level this door already stands in?

    The stream names a door's source level only as a human comment (`Level file for
    Catacombs`), never as an index, so this is a name comparison. Exact after normalisation,
    or a prefix relationship between two names long enough that it cannot be coincidence
    (`worldmap1` vs `worldmap`, `IkaemosBottomInt` vs `Ikaemos Bottom Interior`). Deliberately
    conservative: a false positive only removes one candidate, while a false negative is a
    door that leads back to where it already is.
    """
    if not src_display:
        return False
    a, b = _door_key(src_display), _door_key(candidate)
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 8 and (a.startswith(b) or b.startswith(a))


# A door with no explicit +Script: uses its DESTINATION NAME as the script name; the engine then
# looks that name up in the destination level's own script list and bounces to the menu ("Exit to
# Unknown") if it is absent. So a no-script door may only target a level that provides a script
# equal to its own name. That mapping is the authoritative script_filenames.tbl, a member of
# TABLES.VPP: one contiguous run of `$Level:`/`+Script:` records between the shipped
# "CHANGING THE ORDER" banner and the next `#End`. We parse it straight from the blob so the rule
# always matches the disc in hand (see docs/lab/DOOR-SCRIPT-RULE.md; verified: 51 levels, and every
# level except `endgame` provides its own-named script, so `endgame` is the only unsafe target -
# and it is already excluded as the ending).
_SCRIPT_TABLE_BANNER = b"CHANGING THE ORDER"
_SCRIPT_LEVEL_RE = re.compile(rb'\$Level:\s*"([^"\r\n]{1,40})"')
_SCRIPT_ENTRY_RE = re.compile(rb'\+Script:\s*"([^"\r\n]{1,40})"')


def _no_script_safe_targets(blob: bytes) -> set[str]:
    """Set of level keys (via _door_key) that a NO-+Script: door may safely target.

    A level qualifies iff it declares a `+Script:` whose name equals the level name
    (case-insensitively) - i.e. the name-as-script default resolves. Parsed from
    script_filenames.tbl inside the blob. Conservative: if the table cannot be located, returns
    an empty set, which makes the caller hold every no-script door (refuse rather than guess).
    """
    b = blob.find(_SCRIPT_TABLE_BANNER)
    if b < 0:
        return set()
    first = _SCRIPT_LEVEL_RE.search(blob, b)
    if not first:
        return set()
    end = blob.find(b"#End", first.start())
    if end < 0:
        end = min(first.start() + 0x4000, len(blob))
    body = blob[first.start():end]
    lvls = list(_SCRIPT_LEVEL_RE.finditer(body))
    safe: set[str] = set()
    for i, m in enumerate(lvls):
        name = m.group(1).decode("latin-1")
        seg_end = lvls[i + 1].start() if i + 1 < len(lvls) else len(body)
        seg = body[m.end():seg_end]
        scripts = [s.group(1).decode("latin-1") for s in _SCRIPT_ENTRY_RE.finditer(seg)]
        if any(_door_key(s) == _door_key(name) for s in scripts):
            safe.add(_door_key(name))
    return safe


def _door_records(blob: bytes) -> list[dict]:
    """Every `+Id: "load level"` door in the stream, with the level file it stands in.

    Parsed, never looked up from a precomputed table: a door is a `$Trigger: "name"` whose
    own block's `+Id:` is `"load level"`, and its source level is the nearest preceding
    `Level file for X` comment. A `$Trigger:` that is not a door (a character `.tbl`'s
    animation cue) has no `+Id:` before the next `$Trigger:`, so it is skipped rather than
    mis-counted. One forward pass, no regex backtracking across the stream.
    """
    heads = [(m.start(), m.group(1).strip().decode("latin-1", "replace"))
             for m in DOOR_LEVEL_RE.finditer(blob)]
    recs: list[dict] = []
    src = None
    hi = 0
    for m in DOOR_TRIGGER_RE.finditer(blob):
        while hi < len(heads) and heads[hi][0] < m.start(1):
            src = heads[hi][1]
            hi += 1
        end = min(m.end() + DOOR_BLOCK_WINDOW, len(blob))
        nxt = DOOR_TRIGGER_RE.search(blob, m.end(), end)
        if nxt:
            end = nxt.start()
        idm = DOOR_ID_RE.search(blob, m.end(), end)
        if not idm or idm.group(1) != b"load level":
            continue
        # the arrival start-id: `+Index: N`. The destination MUST provide a player-start
        # navpoint for this slot or the load fails and the game bounces to the menu (the
        # "exit to the unknown" symptom). Captured so candidate selection can honour it.
        seg = blob[m.end():end]
        idxm = re.search(rb"\+Index:\s*(\d+)", seg)
        index = int(idxm.group(1)) if idxm else None
        # does this door declare an explicit +Script:? If not, its script name defaults to the
        # destination name, which is the "Exit to Unknown" trap when remapped (see the transform).
        has_script = re.search(rb'\+Script:\s*"', seg) is not None
        recs.append({"off": m.start(1), "name": m.group(1), "src": src,
                     "index": index, "has_script": has_script})
    return recs


# player-start navpoints are named `$player<party>-<slot>`. A door's `+Index: K` arrives at
# slot K, so a destination is only safe for that door if it declares a `$player*-K` navpoint.
_PLAYER_START_RE = re.compile(rb"\$player\d+-(\d+)")
_LEVEL_DECL_RE = re.compile(rb'\$Level:\s*"([^"]{1,40})"')


def _level_start_slots(blob: bytes) -> dict[str, set[int]]:
    """Map each level name (lower-case) -> the set of start-id slots it actually provides.

    Built by segmenting the stream on every level marker (`Level file for X` comment and
    `$Level: "X"` declaration) and collecting the `$player*-<slot>` navpoint slots that fall
    in each level's span. Conservative: a level only "provides" a slot we can actually see,
    so an unproven target is simply not offered (refuse rather than guess). Used to stop a
    door being remapped to a level that cannot spawn the player at the door's `+Index`.
    """
    import bisect
    marks = [(m.start(), m.group(1).strip().decode("latin-1", "replace"))
             for m in DOOR_LEVEL_RE.finditer(blob)]
    marks += [(m.start(), m.group(1).decode("latin-1", "replace"))
              for m in _LEVEL_DECL_RE.finditer(blob)]
    marks.sort()
    starts = [p for p, _ in marks]
    names = [n for _, n in marks]
    slots: dict[str, set[int]] = {}
    for pm in _PLAYER_START_RE.finditer(blob):
        i = bisect.bisect_right(starts, pm.start()) - 1
        if i < 0:
            continue
        key = _door_key(names[i])
        slots.setdefault(key, set()).add(int(pm.group(1)))
    return slots


def _door_candidates(old_len: int, src_display: str | None,
                     index: int | None = None,
                     slots_by_level: dict[str, set[int]] | None = None,
                     has_script: bool = True,
                     safe_targets: set[str] | None = None) -> list[str]:
    """Every legal target for one door. Empty means the door is left alone, not guessed at.

    Constraints, all enforced (never guessed):
      * `len(new) <= len(old)` - fixed-width field;
      * a real `Level_info` name, never the dev/ending exclusions or the `$zzz` sentinel;
      * never the door's own source level;
      * if `index`/`slots_by_level` given: the target must PROVIDE that start-id slot, so the
        player can actually spawn (else the load bounces to the menu);
      * if the door has NO explicit `+Script:` (`has_script` False) and `safe_targets` is given:
        the target must be in `safe_targets` - a level that provides a script equal to its own
        name - or the name-as-script default fails to resolve ("Exit to Unknown").
    """
    out = []
    for name in DOOR_TARGET_NAMES:
        if len(name) > old_len:                     # the field is fixed width
            continue
        if name.lower() in DOOR_TARGET_EXCLUDE:     # a dev level / the ending itself
            continue
        if name.startswith(DOOR_SENTINEL):          # reserved by `enemies_none`
            continue
        if _door_same_level(src_display, name):     # never back to its own level
            continue
        if index is not None and slots_by_level is not None:
            provided = slots_by_level.get(_door_key(name))
            if not provided or index not in provided:
                continue                            # can't spawn the player here at this slot
        if not has_script and safe_targets is not None:
            if _door_key(name) not in safe_targets:
                continue                            # name-as-script would not resolve
        out.append(name)
    return out


def _diff_outside(a: bytes, b: bytes, fields: list[tuple[int, int]]) -> int:
    """How many bytes differ OUTSIDE the declared fields.

    Compares the complement of the fields rather than every byte: the regions between them
    are sliced and compared whole, so this is a C-speed equality check plus a per-byte count
    only over regions that actually differ (which must be none).
    """
    n = 0
    pos = 0
    for off, ln in sorted(fields):
        if a[pos:off] != b[pos:off]:
            n += sum(1 for x, y in zip(a[pos:off], b[pos:off]) if x != y)
        pos = max(pos, off + ln)
    if a[pos:] != b[pos:]:
        n += sum(1 for x, y in zip(a[pos:], b[pos:]) if x != y)
    return n


# --------------------------------------------------------------------------- #
# Boss Gauntlet - chain the boss levels' exit doors into a sequence
#
# Idea (user request): instead of hunting bosses across the world, beat one boss area and its exit
# takes you to the NEXT boss area, through a gauntlet. The bosses stay in their home levels; we
# rewrite ONE exit door per level to point at the next level in the chain.
#
# The boss->level identity is the VPP MEMBER FILENAME (recovered + verified: docs/lab/
# probe_boss_member.py, probe_gauntlet_feasible2.py). A full 11-level chain is NOT possible - the
# door-name field must fit the target name (len(new) <= len(old)), several boss levels only own
# `worldmap1` doors, and `jadetemple` has no doors at all. The LONGEST legal chain (verified by
# probe_gauntlet_path.py against the retail disc) visits 7 levels / 16 of the 25 bosses:
#
#   khosanilab2(Pyrul) -> khosanilab(Giant Salamanka) -> rand-hills01(Phoenix Rider)
#     -> IonaExt02(Luminar) -> sewerboss(Tentacle Beast x4) -> masad(3 Riders)
#     -> TempleInt(Tiger Rider, Luminar, Machival, Pyrul, Titus)
#
# Each hop rewrites one specific door, identified by its CURRENT destination name + arrival +Index
# (unique enough on the retail disc), with declare-and-refuse on the exact field bytes. Four hops
# reuse `worldmap1` overworld doors; those are statically legal (name fits, slot exists, script-
# safe) but overworld transitions have historically risked a title-screen bounce, so this feature
# is EXPERIMENTAL and must be play-verified. Not coverable in the chain: jadetemple (0 doors),
# TempleInt2 / Rand-Forest01 / Rand-Forestnite1 (long names or only worldmap1 doors) - reported.
#
# Pair with `boss_rush` (clusters each level's bosses onto one spot) so each stop is one fight.
#
# Each hop: (from_level, to_level, current_dest_name, arrival_index). The transform matches a door
# whose source level (by VPP member, re-derived here) == from_level AND current dest == that name
# AND +Index == that index, then rewrites the dest field to to_level, size-preserving.
_BOSS_GAUNTLET_CHAIN = [
    ("khosanilab2", "khosanilab",   b"KhosaniStrng", 2),
    ("khosanilab",  "rand-hills01", b"KhosaniStrng", 2),
    ("rand-hills01", "IonaExt02",   b"worldmap1",    3),
    ("IonaExt02",   "sewerboss",    b"worldmap1",    4),
    ("sewerboss",   "masad",        b"LPalaceInt",   1),
    ("masad",       "TempleInt",    b"worldmap1",    2),
]
# bosses not reachable in the chain, for honest reporting
_BOSS_GAUNTLET_UNCOVERED = {
    "jadetemple": "4 Riders (level has no doors - cannot chain onward)",
    "TempleInt2": "Machival/Evil Urath/Evil Joseph (only worldmap1 doors; long name)",
    "Rand-Forest01": "Serpent Rider (long name / overworld-only doors)",
    "Rand-Forestnite1": "Ghost Rider (long name / overworld-only doors)",
}


def _member_level_map(blob: bytes):
    """blob-offset -> level name, from the VPP member directory. The gauntlet needs to know which
    LEVEL a door sits in, and the only reliable key is the VPP member filename (the 'Level file
    for' comment is unreliable). The blob is the tight concatenation of member DATA, so we rebuild
    the member boundaries by re-reading the TOC is impossible from the blob alone - instead the
    boundaries are recovered from the one in-blob anchor that IS per-member: this function is given
    the member ranges by the driver via _BOSS_GAUNTLET_RANGES when available, else returns None.
    """
    ranges = _BOSS_GAUNTLET_RANGES
    if not ranges:
        return None
    # ranges is a list of (level_name, blob_start, blob_end)
    return ranges


# The driver sets this to [(level_name, blob_start, blob_end), ...] before running the transform,
# because the blob alone does not carry the member directory. Left None otherwise (the transform
# then refuses rather than guess).
_BOSS_GAUNTLET_RANGES = None


def set_boss_gauntlet_ranges(ranges):
    """Driver hook: hand the transform the VPP member->blob-range map (level_name, start, end)."""
    global _BOSS_GAUNTLET_RANGES
    _BOSS_GAUNTLET_RANGES = ranges


def _gauntlet_level_at(off, ranges):
    for name, s, e in ranges:
        if s <= off < e:
            return name
    return None


def t_boss_gauntlet(blob, rng):
    """Chain the boss levels' exit doors into a sequence (see the banner above).

    Reuses the door machinery: a door is identified by (source level via VPP member, current
    destination name, +Index), then its destination field is rewritten to the next chain level.
    Size-preserving (new name + space pad + closing quote == old field width); declare-and-refuse
    on the exact field bytes; read back after writing. EXPERIMENTAL: four hops reuse overworld
    `worldmap1` doors that may bounce to the title in game - play-verify before trusting.
    """
    rep = Report("boss_gauntlet")
    ranges = _member_level_map(blob)
    if ranges is None:
        rep.notes.append("REFUSED: boss_gauntlet needs the VPP member map (driver must call "
                         "set_boss_gauntlet_ranges); nothing changed")
        return blob, rep

    recs = _door_records(blob)
    out = bytearray(blob)
    patches = []            # (off, expect, repl)
    done = []
    for frm, to, cur, idx in _BOSS_GAUNTLET_CHAIN:
        to_b = to.encode("latin-1")
        match = None
        for r in recs:
            if r["name"] != cur:
                continue
            if r.get("index") != idx:
                continue
            lvl = _gauntlet_level_at(r["off"], ranges)
            if lvl is None or _door_key(lvl) != _door_key(frm):
                continue
            match = r
            break
        if match is None:
            rep.notes.append(f"HOP SKIPPED {frm}->{to}: no door with dest {cur.decode()!r} "
                             f"idx {idx} found in {frm}")
            continue
        old = match["name"]
        if len(to_b) > len(old):
            rep.notes.append(f"HOP SKIPPED {frm}->{to}: name too long for field")
            continue
        off = match["off"]
        expect = old + b'"'
        if bytes(out[off:off + len(expect)]) != expect:
            rep.notes.append(f"REFUSED: door at 0x{off:X} ({frm}->{to}) does not hold "
                             f"{expect!r}; nothing written")
            return blob, rep
        repl = to_b + b" " * (len(old) - len(to_b)) + b'"'
        patches.append((off, expect, repl))
        done.append(f"{frm}->{to}")

    if not patches:
        rep.notes.append("no gauntlet hops could be applied - nothing changed")
        return blob, rep

    for off, _expect, repl in patches:
        out[off:off + len(repl)] = repl
    bad = [off for off, _e, repl in patches if bytes(out[off:off + len(repl)]) != repl]
    if bad:
        rep.notes.append(f"REFUSED: {len(bad)} hop(s) did not read back ({bad[:3]}); nothing written")
        return blob, rep

    rep.changed = len(patches)
    rep.notes.append(f"gauntlet chain: {' -> '.join(['khosanilab2'] + [h.split('->')[1] for h in done])}")
    rep.notes.append(f"{len(patches)}/{len(_BOSS_GAUNTLET_CHAIN)} hops wired, size-preserving, read back OK")
    rep.notes.append("EXPERIMENTAL: 4 hops reuse overworld worldmap1 doors that may bounce to "
                     "the title - PLAY-VERIFY before trusting")
    rep.notes.append("pair with boss_rush so each stop is a single fight")
    uncov = ", ".join(f"{k} ({v})" for k, v in _BOSS_GAUNTLET_UNCOVERED.items())
    rep.notes.append(f"bosses NOT in the chain: {uncov}")
    return bytes(out), rep


# --------------------------------------------------------------------------- #
# Boss Rooms - the WORKING boss gauntlet (NPC->boss swap + door chain)
#
# The scripted boss_gauntlet failed because bosses are hidden/trigger-gated: you walked into empty
# rooms (play-verified). The fix (user's idea): don't rely on the level's own bosses - OVERWRITE a
# level's NPC placements with hostile BOSS creatures. Hostility comes from the creature DEFINITION
# ($Team:"hostile" in #Character Info), so a placement whose $Character is renamed to "Ghost Rider"
# spawns a live, aggressive Rider on arrival - no +Boss, no +Action, no activation gate. This is the
# same mechanism as enemies_random, just aimed at NPC (peaceful) placements and seeded with bosses.
# Size-preserving: $Character is rewritten inside its own field width (boss names 5-15 chars fit the
# wide NPC name slots - verified docs/lab/probe_npc_to_boss.py). Then each level's exit door is
# rewritten to the next level in the chain (same door machinery as door_destination_remap).
#
# Chain starts at masad (the opening level, where the player begins) and runs through host levels
# that (a) have NPC slots wide enough for bosses and (b) can legally door-link. 32 levels qualify;
# a long legal chain exists (docs/lab/probe_bossroom_chain.py). We build the chain dynamically from
# the live data so it adapts, starting at masad.
#
# Honest scope: these are boss-type ENEMIES (the creature's stats/model/hostility), not the full
# scripted boss encounters with intros/stages. That is exactly "drop into a room of fightable
# bosses", and it is the version that actually works in game.
_BOSS_ROOM_CREATURES = [
    b"Ghost Rider", b"Tiger Rider", b"Phoenix Rider", b"Serpent Rider",
    b"Luminar", b"Pyrul", b"Titus", b"Machival", b"Giant Salamanka",
    b"Tentacle Beast", b"Evil Urath", b"Evil Joseph",
]


def _boss_room_level_map():
    """The driver supplies (level_name, blob_start, blob_end) via set_boss_gauntlet_ranges."""
    return _BOSS_GAUNTLET_RANGES


# Pacifier actions: if a placement carries any of these, a creature swapped onto it stays
# hidden/passive and will NOT aggro. We only overwrite CLEAN placements (none of these).
_BOSS_ROOM_PACIFIERS = (b"+Hidden", b'"turn hostile"\t0', b'"turn hostile" 0',
                        b'"wait for go"', b'"show/hide"\t0', b'"show/hide" 0')

# masad (the start level) only loads these hostile creature models, so only these are model-safe to
# place there (anything else hangs the load). All are $Team:"hostile".
_MASAD_ENEMIES = [b"Orenian Soldier1", b"Orenian Soldier2", b"Orenian Archer",
                  b"Orenian Scout", b"Barbarian Fighter"]
_BOSS_ROOM_START = "masad"


def t_boss_rooms(blob, rng, levels=5, per_level=0):
    """Boss Rooms gauntlet - the WORKING design (see docs/BOSS-ROOMS-DESIGN.md).

    masad (start): clean non-story NPCs become model-safe hostile enemies (Orenian Soldier/Scout/
    Archer/Barbarian - loaded in masad, so no load hang; aggro because the slots are clean). Its
    exit chains into the boss rooms.
    Boss rooms: each level's clean NPC slots become that level's OWN boss (model resident, aggro on
    arrival). Each exit leads to another boss room (seeded order). TempleInt is terminal.

    Two hard rules enforced: (1) MODEL-SAFE - only place a creature a level already loads; (2) CLEAN
    SLOTS ONLY - skip placements with +Hidden/"turn hostile 0"/"wait for go"/"show/hide 0", else the
    creature won't aggro. Size-preserving, declare-and-refuse, read back. EXPERIMENTAL door hops.
    """
    rep = Report("boss_rooms")
    ranges = _boss_room_level_map()
    if ranges is None:
        rep.notes.append("REFUSED: boss_rooms needs the VPP member map (driver hook); nothing changed")
        return blob, rep

    def level_at(off):
        for name, s, e in ranges:
            if s <= off < e:
                return name
        return None

    keyname = {}
    for name, s, e in ranges:
        keyname.setdefault(_door_key(name), name)

    # which bosses each level OWNS (its models are loaded there -> model-safe to place)
    own_bosses: dict[str, list[bytes]] = {}
    for s, e in _placement_records(blob):
        seg = blob[s:e]
        if b"+Boss" not in seg:
            continue
        cm = PLACEMENT_CHAR_RE.search(seg)
        lv = level_at(s)
        if cm and lv:
            own_bosses.setdefault(_door_key(lv), []).append(cm.group(2))

    # clean peaceful placements per level (no pacifier) - the only safe aggro slots
    _m, peaceful = _analyse_enemies(blob)
    clean_by_level: dict[str, list] = {}
    for rec in peaceful:
        seg = blob[rec["start"]:rec["end"]]
        if any(p in seg for p in _BOSS_ROOM_PACIFIERS):
            continue
        lv = level_at(rec["start"])
        if lv:
            clean_by_level.setdefault(_door_key(lv), []).append(rec)

    # door legality (same rules as door_destination_remap)
    slots = _level_start_slots(blob)
    safe = _no_script_safe_targets(blob)
    recs = _door_records(blob)
    doors_by_level: dict[str, list] = {}
    for r in recs:
        lv = level_at(r["off"])
        if lv:
            doors_by_level.setdefault(_door_key(lv), []).append(r)

    def legal_door(frm_key, to_name):
        for d in doors_by_level.get(frm_key, []):
            dn = d["name"].decode("latin-1")
            if len(to_name) > len(dn):
                continue
            if d["index"] is not None and d["index"] not in slots.get(_door_key(to_name), set()):
                continue
            if not d["has_script"] and _door_key(to_name) not in safe:
                continue
            return d
        return None

    # a level is a usable BOSS ROOM if it owns a boss that fits at least one of its clean slots
    def room_fill(key):
        bosses = own_bosses.get(key, [])
        if not bosses:
            return []
        picks = []
        for rec in sorted(clean_by_level.get(key, []), key=lambda r: -len(r["char"])):
            w = len(rec["char"])
            fit = [b for b in bosses if len(b) == w]   # EQUAL-LENGTH ONLY (no padding; see 1a)
            if fit:
                picks.append((rec, fit))
        return picks

    boss_rooms = [k for k in own_bosses if room_fill(k) and k != _door_key(_BOSS_ROOM_START)]

    start = _door_key(_BOSS_ROOM_START)
    if start not in clean_by_level:
        rep.notes.append("REFUSED: masad has no clean NPC slots; nothing changed")
        return blob, rep

    # build the chain: masad -> boss rooms, each hop a legal door, seeded order among rooms
    chain = [start]
    remaining = boss_rooms[:]
    rng.shuffle(remaining)
    cur = start
    while len(chain) < max(2, int(levels)) and remaining:
        nxt = next((r for r in remaining if legal_door(cur, keyname[r])), None)
        if nxt is None:
            break
        chain.append(nxt)
        remaining.remove(nxt)
        cur = nxt
    if len(chain) < 2:
        rep.notes.append("REFUSED: could not chain masad to any boss room; nothing changed")
        return blob, rep

    out = bytearray(blob)
    npc_edits = 0

    # 1a) masad: fill clean non-story NPC slots with model-safe hostile enemies.
    # EQUAL-LENGTH ONLY - $Character must NOT be space-padded (padding corrupts the record: the
    # engine reads past the name and dereferences script text -> TLB-miss freeze, observed in game.
    # Verified: of 1102 $Character names in retail, zero are pad-padded). So a slot is only usable
    # if a masad-loaded hostile exists at EXACTLY its name width.
    masad_filled = 0
    for rec in sorted(clean_by_level.get(start, []), key=lambda r: -len(r["char"])):
        w = len(rec["char"])
        fits = [c for c in _MASAD_ENEMIES if len(c) == w]
        if not fits:
            continue
        new = fits[rng.randrange(len(fits))]
        a, b = rec["char_abs"]
        if bytes(out[a:b]) != rec["char"]:
            continue
        out[a:b] = new                      # exact width, no padding
        npc_edits += 1
        masad_filled += 1

    # 1b) each boss room: fill EVERY clean slot with that room's OWN boss(es) (model-safe, aggro).
    # per_level=0 (default) means fill them all - as many bosses as the room has clean slots.
    room_fills = {}
    cap = int(per_level) if int(per_level) > 0 else None
    for key in chain[1:]:
        picks = room_fill(key)
        n = 0
        for rec, fit in picks:
            if cap is not None and n >= cap:
                break
            new = fit[rng.randrange(len(fit))]   # fit entries are exactly len(rec["char"])
            a, b = rec["char_abs"]
            if bytes(out[a:b]) != rec["char"]:
                continue
            out[a:b] = new                       # exact width, no padding
            npc_edits += 1
            n += 1
        room_fills[key] = n

    # 2) chain the exits
    door_edits = 0
    hop_notes = []
    for i in range(len(chain) - 1):
        frm, to = chain[i], chain[i + 1]
        to_name = keyname[to]
        d = legal_door(frm, to_name)
        if not d:
            continue
        old = d["name"]
        off = d["off"]
        expect = old + b'"'
        if bytes(out[off:off + len(expect)]) != expect:
            continue
        out[off:off + len(expect)] = to_name.encode("latin-1") + b" " * (len(old) - len(to_name)) + b'"'
        door_edits += 1
        hop_notes.append(f"{keyname[frm]}->{to_name}")

    rep.changed = npc_edits + door_edits
    rep.notes.append("chain: " + " -> ".join(keyname[k] for k in chain))
    rep.notes.append(f"masad start: {masad_filled} non-story NPCs -> model-safe hostile enemies "
                     f"(Orenian Soldier/Scout/Archer/Barbarian), aggro on arrival")
    rep.notes.append("boss rooms: " + ", ".join(f"{keyname[k]}={room_fills.get(k,0)} boss(es)"
                                                 for k in chain[1:]))
    rep.notes.append(f"{door_edits} exit door(s) chained: {', '.join(hop_notes)}")
    rep.notes.append("MODEL-SAFE (only creatures the level loads) + CLEAN SLOTS only (so they aggro)")
    rep.notes.append("EXPERIMENTAL: door hops may reuse overworld doors; play-verify")
    return bytes(out), rep


DOOR_SCOPE_VALUES = ("interior", "overworld", "all")


def t_door_destination_remap(blob, rng, how="shuffle", require_script=False, scope="interior"):
    """Rewrite where every door leads. The headline feature.

    All 218 doors are eligible. The "Exit to Unknown" trap - a door with no explicit `+Script:`
    using its destination NAME as the script name (door-mechanism.md 5b caveat 2) - is now
    handled precisely: such doors are constrained to the `+Script:` safe-target set (levels that
    provide a script equal to their own name), parsed from script_filenames.tbl in the blob. That
    set is every level but `endgame` (see docs/lab/DOOR-SCRIPT-RULE.md), and `endgame` is already
    excluded, so no-script doors keep essentially the full pool while never bouncing to the menu.
    `require_script=True` is a stricter opt-in that remaps only explicit-+Script doors.

    Each door's destination name is replaced by another real level name that fits its field,
    so the byte count in and out is identical and the stream never shifts. Everything is
    checked and refused rather than guessed:

      * the target must be a real `Level_info` name (the whole list is in the code);
      * `len(new) <= len(old)` - the field is fixed width;
      * a door never points at its own source level;
      * the `$zzz` sentinel is never emitted - it belongs to the enemy disarm;
      * a door with no legal target is left alone and counted as a skip.

    Discipline, the same the binary layer and the lab applier hold to: every patch declares the
    bytes it expects and is refused if the disc does not match; every patch is bounds-checked
    and read back; and the whole reassembled stream is then compared byte for byte to prove
    nothing outside a deliberately patched field moved.

    `how`:
      * ``shuffle`` (default) - each door independently gets a seeded random legal target.
      * ``swap`` - the doors' own destinations are permuted among doors that can hold them,
        so no destination is invented and none disappears. The gentler policy.
      * ``off`` - change nothing and say so.

    `scope` - which transitions are eligible:
      * ``interior`` (default) - only the non-overworld doors. The safe, play-verified set;
        the opening-area/overworld-hub transitions are held (they bounce to the title in game).
      * ``overworld`` - ONLY the overworld/opening transitions. EXPERIMENTAL, not play-verified;
        these can bounce to the title.
      * ``all`` - every door, holding nothing. EXPERIMENTAL, same overworld bounce risk.

    Risk this carries and does not hide: it changes the level graph itself. Reachability is
    NOT checked, so a seed can strand the player. That guard is a separate work item.
    """
    rep = Report("door_destination_remap")
    how = str(how)
    if how not in DOOR_HOW_VALUES:
        rep.notes.append(f"unknown how {how!r} - pick one of {list(DOOR_HOW_VALUES)}; "
                         f"nothing changed")
        return blob, rep
    scope = str(scope)
    if scope not in DOOR_SCOPE_VALUES:
        rep.notes.append(f"unknown scope {scope!r} - pick one of {list(DOOR_SCOPE_VALUES)}; "
                         f"nothing changed")
        return blob, rep

    recs = _door_records(blob)
    if not recs:
        rep.notes.append("no `+Id: \"load level\"` doors found in this stream - nothing changed")
        return blob, rep

    # `scope` selects WHICH transitions are eligible, split on the opening-area/overworld-hub
    # doors (DOOR_SOURCE_EXCLUDE). Those loads pass every static check but bounce to the title in
    # game and are the first transitions a run hits, so they are held by default:
    #   interior  (default) - remap only the NON-overworld doors (the safe, proven set)
    #   overworld           - remap ONLY the held overworld/opening transitions (experimental)
    #   all                 - remap everything, hold nothing (experimental; can bounce to title)
    def _is_overworld(r) -> bool:
        srck = _door_key(r.get("src") or "")
        return any(srck == _door_key(x) or srck.startswith(_door_key(x))
                   for x in DOOR_SOURCE_EXCLUDE)

    total = len(recs)
    if scope == "interior":
        recs = [r for r in recs if not _is_overworld(r)]
        held = total - len(recs)
        rep.notes.append(f"scope=interior: {len(recs)} interior door(s) eligible ({held} "
                         f"overworld/opening transitions held - they bounce to the title even "
                         f"when valid)")
    elif scope == "overworld":
        recs = [r for r in recs if _is_overworld(r)]
        held = total - len(recs)
        rep.notes.append(f"scope=overworld (EXPERIMENTAL): {len(recs)} overworld/opening "
                         f"transition(s) eligible ({held} interior doors held). These can bounce "
                         f"to the title in game - not play-verified.")
    else:  # all
        rep.notes.append(f"scope=all (EXPERIMENTAL): all {len(recs)} door(s) eligible, including "
                         f"overworld/opening transitions - these can bounce to the title in game, "
                         f"not play-verified.")
    if not recs:
        rep.notes.append("no doors in the selected scope - nothing changed")
        return blob, rep

    # The +Script: safe-target set (levels a no-script door may point at without the
    # "Exit to Unknown" bounce). Parsed from script_filenames.tbl in the blob. `require_script`
    # is kept as a stricter opt-in: if a caller sets it True we ONLY remap doors that carry an
    # explicit +Script: (belt-and-braces); by default we remap every door but constrain the
    # no-script ones to the safe set - which the sub-agent proved is every level but `endgame`.
    safe_targets = _no_script_safe_targets(blob)
    if not safe_targets:
        rep.notes.append("WARNING: could not parse script_filenames.tbl - holding all no-script "
                         "doors (they would risk 'Exit to Unknown')")
    else:
        rep.notes.append(f"+Script safe-target set: {len(safe_targets)} levels")
    if require_script:
        held = sum(1 for r in recs if not r.get("has_script"))
        recs = [r for r in recs if r.get("has_script")]
        rep.notes.append(f"require_script=True: remapping only the {len(recs)} explicit-+Script "
                         f"doors, holding {held} no-script doors")
        if not recs:
            rep.notes.append("no doors with an explicit +Script: - nothing changed")
            return blob, rep

    # sanity check on the level list itself: every destination already in the stream has to be
    # a name this build knows, or the list is wrong for this disc and nothing should be written
    known = {n.lower() for n in DOOR_TARGET_NAMES}
    unknown = sorted({r["name"].decode("latin-1") for r in recs
                      if r["name"].decode("latin-1").lower() not in known})
    if unknown:
        rep.notes.append(f"REFUSED: {len(unknown)} existing destination(s) are not in the "
                         f"known level list {unknown[:6]} - the list does not match this disc, "
                         f"so nothing was written")
        return blob, rep

    if how == "off":
        rep.notes.append("policy 'off' - nothing changed")
        return blob, rep

    # Map each level to the player-start slots it provides, so a door is only sent somewhere
    # the player can actually spawn at that door's +Index. Without this, a door whose +Index
    # the destination lacks fails to load and bounces to the menu ("exit to the unknown").
    slots_by_level = _level_start_slots(blob)
    rep.notes.append(f"start-id map: {len(slots_by_level)} levels with known player-start slots")

    # deterministic per seed: the door order and the destination pool are both seeded, and the
    # chain's Random is used in list order like every other transform
    order = list(range(len(recs)))
    rng.shuffle(order)
    pool: list[bytes | None] = []
    if how == "swap":
        pool = [r["name"] for r in recs]
        rng.shuffle(pool)

    patches: list[tuple[int, bytes, bytes]] = []
    skipped: dict[str, int] = {}

    def _skip(why: str) -> None:
        skipped[why] = skipped.get(why, 0) + 1

    for idx in order:
        rec = recs[idx]
        old = rec["name"]
        door_index = rec.get("index")
        door_has_script = rec.get("has_script", True)
        if how == "shuffle":
            cands = _door_candidates(len(old), rec["src"], door_index, slots_by_level,
                                     door_has_script, safe_targets)
            if not cands:
                _skip(f"no legal target of length <= {len(old)} that provides start-id "
                      f"{door_index}" + ("" if door_has_script else " and is +Script-safe"))
                continue
            new = cands[rng.randrange(len(cands))].encode("latin-1")
        else:
            pick = None
            for j, cand in enumerate(pool):
                if cand is None or len(cand) > len(old):
                    continue
                cand_name = cand.decode("latin-1")
                if cand_name.lower() in DOOR_TARGET_EXCLUDE:
                    continue
                if cand.startswith(DOOR_SENTINEL.encode()):
                    continue
                if _door_same_level(rec["src"], cand_name):
                    continue
                # honour the arrival slot: the swapped-in destination must be able to spawn
                # the player at this door's +Index, or it would bounce to the menu
                if door_index is not None:
                    provided = slots_by_level.get(_door_key(cand_name))
                    if not provided or door_index not in provided:
                        continue
                # a no-script door must land on a +Script-safe level (name-as-script resolves)
                if not door_has_script and safe_targets is not None:
                    if _door_key(cand_name) not in safe_targets:
                        continue
                pick = j
                break
            if pick is None:
                _skip("no remaining destination fits this field, start-id and +Script rule")
                continue
            new = pool[pick]                      # type: ignore[assignment]
            pool[pick] = None

        # the field is the name plus its closing quote. The padding must go INSIDE the quotes:
        # new name, then spaces to fill the old name's width, then the single closing quote.
        # (The previous version put the quote right after the name and padded AFTER it, which
        # left the real closing quote dangling -> a malformed "name" " destination the game
        # could not resolve, so transitions silently failed. This keeps exactly one closing
        # quote adjacent and pads within the field: len(new)+pad+1 == len(old)+1 bytes.)
        repl = new + b" " * (len(old) - len(new)) + b'"'
        expect = old + b'"'
        off = rec["off"]
        if blob[off:off + len(expect)] != expect:    # declares-and-refuses, and bounds-checks
            rep.notes.append(f"REFUSED: the door at stream offset 0x{off:X} does not hold "
                             f"{expect!r}; nothing was written")
            return blob, rep
        patches.append((off, expect, repl))

    # write into a copy, then read every patch back
    out = bytearray(blob)
    fields: list[tuple[int, int]] = []
    for off, _expect, repl in patches:
        out[off:off + len(repl)] = repl
        fields.append((off, len(repl)))
    bad = [off for off, _e, repl in patches
           if bytes(out[off:off + len(repl)]) != repl]
    if bad:
        rep.notes.append(f"REFUSED: {len(bad)} patch(es) did not read back ({bad[:3]}); "
                         f"nothing was written")
        return blob, rep

    # and prove the rest of the stream did not move: a differing byte outside a declared
    # field would mean the write drifted, and then nothing is accepted
    outside = _diff_outside(blob, bytes(out), fields)
    if outside:
        rep.notes.append(f"REFUSED: {outside} byte(s) differ outside a declared field")
        return blob, rep

    changed = sum(1 for off, _e, repl in patches if blob[off:off + len(repl)] != repl)
    rep.changed = changed
    noop = sum(1 for off, expect, repl in patches if blob[off:off + len(repl)] == repl)
    skipped_n = sum(skipped.values())
    rep.notes.append(f"{changed} destination(s) rewritten, {noop} landed on the name they "
                     f"already had, {skipped_n} skipped")
    for why, n in sorted(skipped.items()):
        rep.notes.append(f"   skipped {n}: {why}")
    rep.notes.append("every field is len(old)+1 bytes in and out - the stream never shifts")
    rep.notes.append(f"policy '{how}'; targets are real level names only, never the door's "
                     f"own level, never the $zzz sentinel")
    rep.notes.append(f"read back: {len(patches)}/{len(patches)} patches verified, 0 bytes "
                     f"changed outside a declared field")
    rep.notes.append("RISK: changes the level graph; reachability is not checked, so a seed "
                     "can strand the player")
    return bytes(out), rep


# Modes carry option VALUES as well as transform lists. Two rules, and they were both broken
# until this was written down:
#   1. a mode that includes a dial transform at its default does nothing - 100% is vanilla, and
#      `enemy_difficulty` at `normal` is a no-op. Every mode that uses one must set a value.
#   2. mode values are the DEFAULTS, not an override: an explicit request wins. The engine
#      merges them in one place (`mode_options`) so the CLI, the app and any harness agree.
def mode_options(mode: str, options: dict | None = None) -> dict:
    """Mode defaults, with the caller's explicit options laid over the top."""
    merged = {k: dict(v) for k, v in (MODES.get(mode, {}).get("options") or {}).items()}
    for name, vals in (options or {}).items():
        if vals is None:
            continue
        merged.setdefault(name, {}).update(vals)
    return merged


# transforms that accept keyword options from the request
OPTION_AWARE = {"ring_hunt", "xp_scale", "levelcap_set", "permadeath", "enemy_difficulty",
                "player_stats_random", "enemy_stats_random", "enemy_hp_set",
                "enemies_none", "enemies_swarm", "enemies_random", "enemies_amount",
                "door_destination_remap", "chest_items",
                "weapon_attack_max", "armor_protect_max", "enemy_xp_random",
                "enemy_xp_set", "enemy_damage_set", "rooms_shuffle",
                "boss_rush", "boss_rooms", "item_hunt"}

OPTIONS = {
    "boss_rooms": {
        "levels": {
            "type": "int", "default": 4, "min": 2, "max": 12,
            "label": "How many boss rooms to chain",
            "help": "Length of the gauntlet: how many levels (starting at the opening) get their "
                    "NPCs replaced with bosses and chained exit-to-exit.",
        },
        "per_level": {
            "type": "int", "default": 0, "min": 0, "max": 60,
            "label": "Bosses per room (0 = fill every slot)",
            "help": "How many of each boss room's clean NPC slots become bosses. 0 (default) fills "
                    "EVERY clean slot - as many bosses as the room holds.",
        },
    },
    "boss_rush": {
        "arena": {
            "type": "str", "default": "auto",
            "label": "Arena level",
            "help": "'auto' = gather the level that holds the most bosses; or a level-section "
                    "index. Bosses are gathered WITHIN the chosen level, because a navpoint name "
                    "only resolves in the level that declares it (names repeat across up to 107 "
                    "levels). Bosses in other levels are left unchanged.",
        },
    },
    "item_hunt": {
        "sources": {
            "type": "choice", "default": "both", "choices": ["shops", "quest", "both"],
            "label": "Where to take goods from",
            "help": "'shops' = the +Buy List: / +Sell List: stock · 'quest' = +Gain Item: "
                    "reward slots · 'both' (default). Each good is exchanged (equal width only) "
                    "with a container yield, so it must be found rather than bought.",
        },
    },
    "rooms_shuffle": {
        "how": {
            "type": "choice", "default": "shuffle", "choices": ["shuffle", "swap"],
            "label": "How",
            "help": "'shuffle' permutes every anchor inside its own level, kind and width · "
                    "'swap' trades pairs inside each group instead. Anchors never cross a "
                    "level boundary.",
        },
    },
    "chest_items": {
        "how": {
            "type": "choice", "default": "shuffle", "choices": ["shuffle", "swap"],
            "label": "How",
            "help": "'shuffle' permutes every yield inside its own length class · "
                    "'swap' trades pairs instead",
        },
    },
    "xp_scale": {
        "percent": {
            "type": "int", "default": 100, "min": 5, "max": 999,
            "label": "XP multiplier (%)",
            "help": "100 = vanilla, 300 = triple XP, 33 = a third. Deterministic.",
        },
    },
    "levelcap_set": {
        "percent": {
            "type": "int", "default": 100, "min": 5, "max": 999,
            "label": "Level cap (%)",
            "help": "100 = vanilla, 200 = creatures scale twice as high, 50 = stop early.",
        },
    },
    "permadeath": {
        "block_ability": {
            "type": "bool", "default": True,
            "label": "Disable the revive ability",
            "help": "renames $Action: spell_revive in place",
        },
        "block_items": {
            "type": "bool", "default": True,
            "label": "Neutralise Revive Scroll pickups",
            "help": "renames the item in place",
        },
    },
    "ring_hunt": {
        "anchor": {
            "type": "choice", "default": None,
            "choices": [None, "any-ring", "safe"] + RING_HUNT_ANCHORS,
            "label": "Endgame anchor",
            "help": "'any-ring' = unlock on any of the seven rings with an anchor · "
                    "'safe' = end-of-act milestones only · blank = seeded random pick",
        },
        "count": {
            "type": "int", "default": 1, "min": 1, "max": len(RING_HUNT_ANCHORS),
            "label": "How many anchors",
            "help": "how many events should unlock the ending",
        },
        "safe_only": {
            "type": "bool", "default": True,
            "label": "Prefer end-of-act anchors",
            "help": "restrict the pool to milestones that read like act endings",
        },
    },
    "enemy_difficulty": {
        "level": {
            "type": "choice", "default": "normal",
            "choices": ["trivial", "easy", "normal", "hard", "brutal", "deadly",
                        "impossible"],
            "label": "Enemy difficulty",
            "help": "Scales hostile creatures - hit points, aggression, view/detection range, "
                    "attack radius, movement rates - and every placement's +Level:, each value "
                    "rewritten inside its own field width. impossible = everything pinned to "
                    "the largest value that still fits.",
        },
        "level_shift": {
            "type": "int", "default": 0, "min": -20, "max": 20,
            "label": "Creature level shift (flat)",
            "help": "Adds this many levels to every placed monster instead of scaling. "
                    "0 = use the dial above.",
        },
    },
    "enemy_stats_random": {
        "style": {
            "type": "choice", "default": "floor", "choices": list(STAT_STYLES),
            "label": "Shuffle style",
            "help": "floor = keep every value in its own width class, so a boss stays a boss · "
                    "pure = let values cross widths where they fit, so a boss can end up weak. "
                    "Hostiles are shuffled among themselves only.",
        },
        "hp": {
            "type": "str", "default": "shuffle",
            "label": "Enemy HP",
            "help": "shuffle = HP moves in the stat shuffle (default) · one = every enemy set "
                    "to 1 HP for a one-hit-kill run · a number (e.g. 50) = every enemy set to "
                    "that HP. A uniform value is padded into each field's own width, never "
                    "clamped past what the field can hold, so the disc never changes size.",
        },
    },
    "player_stats_random": {
        "style": {
            "type": "choice", "default": "floor", "choices": list(STAT_STYLES),
            "label": "Shuffle style",
            "help": "floor = keep every value in its own width class · pure = let values cross "
                    "widths where they fit. The party is shuffled among themselves only.",
        },
    },
    "enemy_hp_set": {
        "value": {
            "type": "int", "default": 1, "min": 1, "max": 999,
            "label": "Enemy HP",
            "help": "Every hostile creature is set to this many hit points. Clamped "
                    "per field to the largest value that fits its width, so the disc "
                    "never changes size.",
        },
    },
    "weapon_attack_max": {
        "value": {
            "type": "int", "default": 999, "min": 1, "max": 999,
            "label": "Weapon damage",
            "help": "Every weapon's $Damage is set to this value, clamped per field to the "
                    "largest number that fits its width, so the disc never changes size. "
                    "999 = as high as each field allows.",
        },
    },
    "armor_protect_max": {
        "value": {
            "type": "int", "default": 999, "min": 1, "max": 999,
            "label": "Armour protection",
            "help": "Every armour item's $Protection is set to this value, clamped per field "
                    "to the largest number that fits its width, so the disc never changes size. "
                    "999 = as tanky as each field allows.",
        },
    },
    "enemy_xp_random": {
        "style": {
            "type": "choice", "default": "floor", "choices": ["floor", "pure"],
            "label": "Shuffle style",
            "help": "floor = XP values stay in their own width class (a big reward stays big-ish) "
                    "\u00b7 pure = values cross widths where they fit, so any mob can pay any amount.",
        },
    },
    "enemy_xp_set": {
        "value": {
            "type": "int", "default": 9999, "min": 0, "max": 999999,
            "label": "XP per kill",
            "help": "Every enemy gives this much XP on death, clamped per field to the largest "
                    "number that fits (so a 4-wide field caps at 9999). Set high to level fast.",
        },
    },
    "enemy_damage_set": {
        "value": {
            "type": "int", "default": 0, "min": 0, "max": 999,
            "label": "Enemy attack damage",
            "help": "Every hostile creature's $Damage is set to this. 0 = enemies barely hurt you "
                    "(softest). Enemies have no defence stat, so this is the soften lever. Clamped "
                    "per field to its width. Weapons untouched.",
        },
    },
    "enemies_random": {
        "scope": {
            "type": "choice", "default": "broad",
            "choices": ["per_level", "broad", "global"],
            "label": "Swap scope",
            "help": "broad (recommended) = re-point each monster at a creature that appears in "
                    "many levels, so you get variety (a Lich/Green Bacite in the start area) with "
                    "models still loaded. per_level = only creatures already in the same level "
                    "(safest, less variety). global = game-wide (experimental; can cause missing "
                    "world graphics).",
        },
    },
    "enemies_none": {
        "how": {
            "type": "choice", "default": "navpoint",
            "choices": ["navpoint", "both", "team"],
            "label": "How to disarm them",
            "help": "navpoint = unlink every spawn from the navpoint it stands on (the verified "
                    "lever). team = re-team the hostile definitions - BLOCKED, it stops the level "
                    "loading at all. both = navpoint for now.",
        },
    },
    "enemies_amount": {
        "amount": {
            "type": "choice", "default": "normal",
            "choices": list(AMOUNT_VALUES),
            "label": "How many enemies",
            "help": "none = unlink every monster placement from its navpoint (the lever verified "
                    "in game); few = unlink a seeded ~70%; normal = vanilla, no edits; "
                    "many = turn a seeded ~50% of the peaceful placements into monsters; "
                    "all = turn every convertible peaceful placement into a monster.",
        },
    },
    "door_destination_remap": {
        "how": {
            "type": "choice", "default": "shuffle",
            "choices": list(DOOR_HOW_VALUES),
            "label": "How to pick the new destination",
            "help": "shuffle = every door picks its own seeded random real level of the same "
                    "length or shorter; swap = the doors' own destinations are permuted among "
                    "doors that can hold them, so no destination is invented and none "
                    "disappears; off = change nothing. A door with nowhere legal to go is left "
                    "alone and reported, never guessed at.",
        },
        "require_script": {
            "type": "bool", "default": False,
            "label": "Explicit-script doors only",
            "help": "Off (default): remap ALL doors; no-script doors are constrained to levels "
                    "whose script matches their name, so none can bounce to 'Exit to Unknown'. "
                    "On: stricter - only remap doors that carry an explicit +Script:.",
        },
        "scope": {
            "type": "choice", "default": "interior",
            "choices": list(DOOR_SCOPE_VALUES),
            "label": "Which transitions to randomize",
            "help": "interior (default, play-verified) = randomize only the regular in-level "
                    "doors; the overworld/opening map transitions are left alone because they "
                    "bounce to the title screen when remapped. overworld = randomize ONLY those "
                    "overworld/opening transitions (experimental, can bounce to title). all = "
                    "randomize every transition, holding nothing (experimental, same risk).",
        },
    },
}


TRANSFORM_INFO = {
    "lock_shuffle": (
        "Door lock values",
        "Shuffles the +Locked: values across every door, so a door's lock no longer "
        "matches what is behind it.",
    ),
    "door_name_shuffle": (
        "Door names",
        "Shuffles $Door names among equal widths.",
    ),
    "enemies_none": (
        "No enemies",
        "Unlinks every monster placement (2,220 of them) from the navpoint it spawns on, and "
        "optionally re-teams the hostile creature definitions. Nothing added, nothing moved.",
    ),
    "enemies_amount": (
        "How many enemies",
        "One dial over the enemy count: none (unlink every monster placement from its "
        "navpoint), few (a seeded ~70%), normal (vanilla, no edits), many (a seeded ~50% of "
        "the peaceful placements become monsters) or all (every convertible peaceful "
        "placement becomes a monster).",
    ),
    "door_destination_remap": (
        "Door destinations",
        "Rewrites the destination name inside every door's `$Trigger:` record, so doors lead "
        "somewhere else. Finds the doors by parsing the level tables, rewrites only names that "
        "fit the field, refuses anything it cannot prove, and changes the level graph itself - "
        "reachability is not checked yet.",
    ),
    "shops_free": (
        "Free shops",
        "Every $Value price becomes 0, padded to its own field width. Everything is free.",
    ),
    "shops_crazy": (
        "Crazy prices",
        "Every $Value price becomes the largest value its own field can hold (all 9s).",
    ),
    "shops_none": (
        "No shops",
        "Re-points the placements that name a +Shop character at equal-length non-shopkeeper "
        "names, so the shopkeeper is never reached and the shop is absent from the world. "
        "The definitions themselves are never touched.",
    ),
    "enemies_random": (
        "Random enemies",
        "Swaps which creature stands on each monster placement, and its +Level:, between "
        "equal-length values only.",
    ),
    "enemies_swarm": (
        "Enemy swarm",
        "Re-points peaceful placements (NPCs, props, shopkeepers) at hostile creatures. "
        "Far more enemies to fight, at the cost of the people who lived there.",
    ),
    "enemy_difficulty": (
        "Enemy difficulty",
        "The dial: scales hostile creature stats and placement levels from trivial through "
        "easy / normal / hard / brutal / deadly to impossible, inside each field's own width.",
    ),
    "door_sound_shuffle": (
        "Door sounds",
        "Shuffles open/close .wav references across doors — you hear the wrong door.",
    ),
    "npc_character_shuffle": (
        "NPC / enemy characters",
        "Shuffles $Character values — who stands where changes.",
    ),
    "model_ref_shuffle": (
        "Model references",
        ".mvf model references reshuffled among equal lengths.",
    ),
    "cutscene_shuffle": (
        "Cutscene order",
        "Shuffles $Cutscene names among equal lengths.",
    ),
    "material_shuffle": (
        "Materials",
        "Shuffles $Material / $Mat names — colour swaps wherever those records exist.",
    ),
    "xp_boost": (
        "XP boost",
        "Scales every +AddXP: reward up inside its own digit width. Kills the grind. "
        "In-game effect unverified.",
    ),
    "levelcap_raise": (
        "Level cap raise",
        "Pushes +Levelcap: values up, same field width, so creatures scale with you. "
        "In-game effect unverified.",
    ),
    "cutscene_bypass": (
        "Cutscene bypass",
        "Breaks the $Cutscene token in place ($Cutscene -> $Xutscene). Single-byte "
        "revert, the biggest wall-clock saving available.",
    ),
    "ring_hunt": (
        "Ring Hunt",
        "Opens the Forge of Urath at a chosen event instead of after all eight rings. "
        "The game has no ring counter — the ending is gated by the single flag "
        "ready_for_end, which is 13 characters, so any 13-character +Event flag can be "
        "renamed to it in place. Changes how the game ENDS.",
    ),
    "item_scatter": (
        "Item scatter",
        "Shuffles which item sits at which loose pickup point.",
    ),
    "shop_shuffle": (
        "Shop prices",
        "Shuffles $Value prices among equal widths.",
    ),
    "chest_shuffle": (
        "Chest payouts",
        "Shuffles +Give payouts among equal widths. Most single digits are item "
        "counts, so only the multi-digit gold payouts really move.",
    ),
    "gold_max": (
        "Max gold pickups",
        "Sets every gold container pickup to the biggest value its fixed-width field allows "
        "(e.g. 30->99, 500->999). Honest limits: gold is a container pickup, not an enemy/soldier "
        "drop (the data has no enemy->gold mechanism), and 1000 cannot fit any field without "
        "resizing (max is 999). Size-preserving.",
    ),
    "chest_items": (
        "Chest contents",
        "Shuffles WHAT a container yields — the +Messagebox: name in a block that also "
        "carries +Give: — between equal-length names, so a cheap crate can hold something "
        "precious. The amount is not touched.",
    ),
    "dialogue_shuffle": (
        "Dialogue chaos",
        "Shuffles spoken text so NPCs say each other's lines. Topic ids are left "
        "alone on purpose — they are reference keys and shuffling them breaks quests.",
    ),
    "sound_shuffle": (
        "Sound effects",
        "Shuffles every .wav reference, so the wrong noise plays everywhere. Very "
        "audible, no progression risk.",
    ),
    "music_shuffle": (
        "Music",
        "Shuffles $Soundtrack / $Sound — the wrong track plays in the wrong place.",
    ),
    "spawn_shuffle": (
        "Spawn points",
        "Shuffles $Start position anchors, so NPCs and creatures appear at other "
        "points in the level. Relocates who stands where.",
    ),
    "rooms_shuffle": (
        "Rooms (within a level)",
        "Randomised rooms, the safe half: permutes $Start position anchors between "
        "placements INSIDE one level (same kind, same width), so a level is furnished "
        "differently while every anchor still exists in that level. Doors, quests, the "
        "level graph and the navpoint definitions are never touched, so nothing can become "
        "unreachable. Size-preserving.",
    ),
    "boss_rooms": (
        "Boss Rooms (gauntlet)",
        "The working boss gauntlet: fills chained levels' NPC slots with hostile boss creatures "
        "(live on arrival - hostility is intrinsic to the creature, so no scripted activation is "
        "needed), and chains each level's exit to the next, starting at the opening level. Walk in, "
        "fight a room of bosses, exit to the next room. Size-preserving. These are boss-type "
        "enemies, not the full scripted boss intros. EXPERIMENTAL: some door hops may reuse "
        "overworld doors; play-verify.",
    ),
    "boss_gauntlet": (
        "Boss Gauntlet",
        "Chains boss levels' exit doors into a sequence: clear one boss area and its exit sends "
        "you to the next, through 7 levels / 16 of the 25 bosses (khosanilab2 -> khosanilab -> "
        "rand-hills01 -> IonaExt02 -> sewerboss -> masad -> TempleInt). Size-preserving, "
        "declare-and-refuse. EXPERIMENTAL: four hops reuse overworld doors that may bounce to the "
        "title; play-verify. Pair with Boss Rush so each stop is one fight. A full 11-level chain "
        "is impossible (name-field widths, levels with no usable doors).",
    ),
    "boss_rush": (
        "Boss Rush",
        "Gathers a level's `+Boss` placements onto a single navpoint of that same level (same "
        "width only), so the bosses stand together and are fought in one place. Not a single "
        "global arena: a navpoint name resolves only inside the level that declares it (names "
        "repeat across up to 107 levels), so bosses in other levels are left unchanged - a "
        "documented blocked extension. Size-preserving.",
    ),
    "item_hunt": (
        "Item Hunt",
        "Moves goods out of the shop stock (+Buy List: / +Sell List:) and the quest rewards "
        "(+Gain Item:) and into the containers: each good is exchanged, equal width only, with "
        "a container yield, and that container's old yield takes the good's shelf/reward slot. "
        "A good with no equal-width container slot stays put. Nothing lost, nothing invented. "
        "Size-preserving.",
    ),
    "animation_shuffle": (
        "Animations",
        "Shuffles $Animation and +Animation class, so characters perform the wrong "
        "movements.",
    ),
    "action_shuffle": (
        "NPC behaviour",
        "Shuffles +Action verbs — the AI and script instructions. Characters do the "
        "wrong things. Actions drive scripted sequences, so this CAN break them.",
    ),
    "icon_shuffle": (
        "Item icons",
        "Shuffles $Icon and .vbm refs, so items and gear display the wrong art.",
    ),
    "vfx_shuffle": (
        "Spell effects",
        "Shuffles .vfx references — the wrong visual effect fires for a spell.",
    ),
    "camera_shuffle": (
        "Cutscene cameras",
        "Shuffles $Camera and .csc, so cutscenes are shot from the wrong angles.",
    ),
    "fog_shuffle": (
        "Fog and visibility",
        "Shuffles $Fog values so each level's atmosphere and draw distance changes.",
    ),
    "slot_shuffle": (
        "Equipment slots",
        "Shuffles +Slot / $Slot, so gear lands in the wrong equipment slot.",
    ),
    "enemy_stats_random": (
        "Random enemy HP & stats",
        "Shuffles the hostile creatures' own numbers — hit points, ability points, "
        "aggression, attack radius, view/detection range, movement rates — among each "
        "other. enemy_difficulty scales these; this moves them between creatures instead. "
        "style=floor keeps a boss a boss; style=pure lets a boss end up weak. Hostiles only.",
    ),
    "player_stats_random": (
        "Random player stats",
        "Shuffles the playable party's numbers among themselves — HP, ability points, "
        "aggression, ranges and turn rates (this game has no Str/Dex/Int). style=floor "
        "keeps each value in its own width tier; style=pure lets them cross where they fit. "
        "Friendly side only.",
    ),
    "enemy_hp_set": (
        "Set enemy HP",
        "Sets every hostile creature's $Max Hit Points and $Hit Points to one value "
        "you choose, padded into each field's own width (all-9s clamp if it will not "
        "fit). HP only - attack, damage and level are left alone. Independent of the "
        "enemy_stats_random 'hp' option. Size-preserving. In-game effect unverified.",
    ),
    "weapon_attack_max": (
        "Max weapon damage",
        "Sets every weapon's $Damage to one high value (default 999, clamped into each "
        "field's own width). Scoped to weapon records by the adjacent $Damage Type marker, "
        "so creature damage is never touched. Size-preserving. In-game effect unverified.",
    ),
    "armor_protect_max": (
        "Buff armour protection",
        "Sets every armour item's $Protection to one high value (default 999, clamped into "
        "each field's own width). Scoped to $Armor: record spans, so creature protection is "
        "never touched. Size-preserving. In-game effect unverified.",
    ),
    "enemy_drops_random": (
        "Random enemy drops",
        "Shuffles which item each enemy `+Drop:` yields, among equal-length item names. The "
        "drop-chance weight is left alone, so rates are unchanged - only WHAT drops moves. "
        "Nothing is invented or lost. Size-preserving.",
    ),
    "music_tracks_shuffle": (
        "Random music (tracks only)",
        "Shuffles the background music tracks ($Soundtrack) among equal-length names, so the "
        "wrong track plays in the wrong place - but sound effects are left alone. Use "
        "music_shuffle instead if you want SFX scrambled too. Size-preserving.",
    ),
    "enemy_xp_random": (
        "Random XP per kill",
        "Shuffles $Experience Gained among hostile creatures, so how much XP a mob is worth on "
        "death is scrambled - a trash mob may pay a boss's XP and vice-versa. Separate from the "
        "global XP multipliers and from scripted quest XP. Hostiles only. Size-preserving.",
    ),
    "enemy_xp_set": (
        "Set XP per kill (fast leveling)",
        "Sets every hostile creature's $Experience Gained to one value you choose, clamped per "
        "field to the largest number that fits its width. Set it high to level up fast. Separate "
        "from the global XP multipliers. Hostiles only. Size-preserving.",
    ),
    "enemy_damage_set": (
        "Set enemy attack damage (lower = softer)",
        "Sets every hostile creature's $Damage to one value you choose (default 0 = they barely "
        "hurt you). Summoner enemies have no defence stat, so lowering their damage is the way to "
        "make them softer. Weapons and the party are untouched. Hostiles only. Size-preserving.",
    ),
    "enemy_drops_always": (
        "Guaranteed enemy drops",
        "Maxes every enemy +Drop chance (to 100 where the field allows), so any enemy that can "
        "drop an item almost always does. Cannot add a drop to an enemy that has none (that needs "
        "extra bytes). Size-preserving.",
    ),
    "creature_stats_shuffle": (
        "Creature stats",
        "Shuffles the creature stat block — speed, weight, hit points, damage, "
        "protection, aggression, detection range, turn rates. This is the anti-grind "
        "lever: enemies stop being uniform.",
    ),
    "fade_instant": (
        "Instant fades",
        "Zeroes every scene fade duration, so the pauses between scenes, cutscenes "
        "and level loads disappear. Presentation only.",
    ),
    "xp_nerf": (
        "XP nerf",
        "Scales every +AddXP: reward DOWN, so you cannot out-level the content. "
        "Roguelike pressure — encounters stay dangerous the whole run.",
    ),
    "economy_squeeze": (
        "Economy squeeze",
        "Drives shop prices up and gold rewards down within their own field widths. "
        "Shops stop being a safety net; you live off what you find.",
    ),
    "xp_scale": (
        "XP control",
        "Scales every +AddXP: reward by a percentage you choose. 100 = vanilla, "
        "300 = triple, 33 = a third. Deterministic, so difficulty is not a dice roll.",
    ),
    "levelcap_set": (
        "Level cap control",
        "Scales every +Levelcap: by a percentage you choose — how high creatures are "
        "allowed to grow. 100 = vanilla, 200 = twice as high.",
    ),
    "permadeath": (
        "Permadeath",
        "Disables the revive ability and neutralises Revive Scroll pickups so death "
        "sticks. Both are table-defined. Risky: an unknown name may error.",
    ),
    "dialogue_blank": (
        "Blank dialogue",
        "Empties every spoken line and quest objective, keeping the exact byte length "
        "and line structure. Removes 2.6 million characters of reading. The boxes "
        "still need advancing — this removes the reading, not the key press.",
    ),
}

TRANSFORMS = {
    "lock_shuffle": t_lock_shuffle,
    "door_name_shuffle": t_door_name_shuffle,
    "door_sound_shuffle": t_door_sound_shuffle,
    "npc_character_shuffle": t_npc_name_shuffle,
    "model_ref_shuffle": t_model_ref_shuffle,
    "cutscene_shuffle": t_cutscene_order_shuffle,
    "material_shuffle": t_material_shuffle,
    "xp_boost": t_xp_boost,
    "levelcap_raise": t_levelcap_raise,
    "cutscene_bypass": t_cutscene_bypass,
    "xp_nerf": t_xp_nerf,
    "economy_squeeze": t_economy_squeeze,
    "xp_scale": t_xp_scale,
    "levelcap_set": t_levelcap_set,
    "permadeath": t_permadeath,
    "ring_hunt": t_ring_hunt,
    "item_scatter": t_item_scatter,
    "shop_shuffle": t_shop_shuffle,
    "chest_shuffle": t_chest_shuffle,
    "chest_items": t_chest_items,
    "gold_max": t_gold_max,
    "dialogue_shuffle": t_dialogue_shuffle,
    "fade_instant": t_fade_instant,
    "dialogue_blank": t_dialogue_blank,
    "enemies_none": t_enemies_none,
    "enemies_amount": t_enemies_amount,
    "enemies_random": t_enemies_random,
    "enemies_swarm": t_enemies_swarm,
    "enemy_difficulty": t_enemy_difficulty,
    "enemy_stats_random": t_enemy_stats_random,
    "player_stats_random": t_player_stats_random,
    "enemy_hp_set": t_enemy_hp_set,
    "enemy_damage_set": t_enemy_damage_set,
    "weapon_attack_max": t_weapon_attack_max,
    "armor_protect_max": t_armor_protect_max,
    "enemy_xp_random": t_enemy_xp_random,
    "enemy_xp_set": t_enemy_xp_set,
    "enemy_drops_always": t_enemy_drops_always,
    "shops_free": t_shops_free,
    "shops_crazy": t_shops_crazy,
    "shops_none": t_shops_none,
    "door_destination_remap": t_door_destination_remap,
    "rooms_shuffle": t_rooms_shuffle,
    "boss_rush": t_boss_rush,
    "boss_gauntlet": t_boss_gauntlet,
    "boss_rooms": t_boss_rooms,
    "item_hunt": t_item_hunt,
}

# second wave: generated from _SHUFFLE_SPECS so each is a plain (blob, rng) transform
for _n in _SHUFFLE_SPECS:
    TRANSFORMS[_n] = _make_multi_shuffle(_n)

# --------------------------------------------------------------------------- #
# Modes — named presets over the transform set
# --------------------------------------------------------------------------- #
MODES = {
    "vanilla": {
        "label": "Vanilla",
        "blurb": "No changes. Baseline for comparing against - a reference, not a build "
                 "target, because there is nothing to change. Use Vanilla \u00b7 No Tutorials "
                 "if you want a disc that still differs from retail by one lever.",
        "transforms": [],
        "risk": "none",
        # Selection is legal (it is how you compare), building is not (it would write a
        # byte-identical copy of the source). The engine refuses with a reason and the
        # UI must not offer it as a build target. See docs/TEST-PLAN.md defect D6.
        "buildable": False,
    },
    # "Vanilla minus X" - the retail game with exactly ONE lever moved. The point is
    # isolation: a disc that differs from retail by a single change is the only honest
    # way to play-test that change, because nothing else can be blamed for what you see.
    # It is also how the 2026-09-29 tutorial retraction should have been tested.
    "vanilla_no_tutorial": {
        "label": "Vanilla \u00b7 No Tutorials",
        "blurb": "Nothing randomised at all - the retail game, with only the opening tutorials "
                 "turned off. The one-lever baseline: a clean comparison disc, and the honest "
                 "way to play-test the tutorial patch on its own, with no randomisation "
                 "confounded into the result.",
        "transforms": [],
        "binary": [["skip_tutorial", {}]],
        "risk": "low - no randomisation; the only change is the tutorial patch",
        "tested": True,
    },
    # The play-verified gameplay recipe (the "CHAOS" build Joshua played end-to-end): tutorials
    # off, enemies randomized within their own area, everything dies in one hit, loot drops and
    # gold maxed, XP boosted. This is the one combination confirmed to boot, move, and progress
    # past the opening in game. Marked TESTED.
    "tested_chaos": {
        "label": "Tested \u00b7 No Tutorial + 1HP + Random Loot",
        "blurb": "The play-verified recipe: tutorials off, enemies randomized (same-area), every "
                 "enemy dies in one hit, random drops and maxed gold, boosted XP. Confirmed in "
                 "game to boot, move, and progress past the opening. At the burning village, talk "
                 "to the first NPC a couple of times for the fire to drop (a known, non-blocking "
                 "quirk of the tutorial-skip).",
        "transforms": ["enemies_random", "enemy_hp_set", "enemy_drops_random", "gold_max",
                       "xp_scale"],
        "options": {"enemies_random": {"scope": "per_level"}, "enemy_hp_set": {"value": 1},
                    "xp_scale": {"percent": 200}},
        "binary": [["skip_intro", {}], ["skip_tutorial", {}]],
        "risk": "play-verified (CHAOS2 seed); the one combination tested end-to-end in game",
        "tested": True,
    },
    "doors": {
        "label": "Door Shuffle",
        "blurb": "Door locks, names and sounds shuffled. Engine-referenced doors (the "
                 "burning-village fire barrier) are pinned so the opening cannot soft-lock.",
        "transforms": ["lock_shuffle", "door_name_shuffle", "door_sound_shuffle"],
        "risk": "low",
    },
    "door_remap": {
        "label": "Door Remap",
        "blurb": "Where every door LEADS: all 218 door destinations are rewritten to other "
                 "real levels, each name staying inside its own field so the archive cannot "
                 "grow. This changes the level graph itself - doors can send you somewhere "
                 "the game never intended, and nothing yet checks that the world stays "
                 "completable.",
        "transforms": ["door_destination_remap"],
        "risk": "high - changes the level graph; reachability is unchecked",
    },
    "chaos": {
        "label": "Chaos",
        "blurb": "Everything cosmetic at once — characters, models, cutscene order, materials.",
        "transforms": ["npc_character_shuffle", "model_ref_shuffle", "cutscene_shuffle",
                       "material_shuffle", "door_sound_shuffle"],
        "risk": "low",
    },
    "short": {
        "label": "Short Run",
        "blurb": "Cutscenes bypassed and combat scaled so a playthrough is hours not days.",
        "transforms": ["cutscene_bypass", "xp_boost"],
        "risk": "medium — untested in game",
    },
    "one_hour": {
        "label": "One Hour",
        "blurb": "Aggressive pacing: no cutscenes, no grind, scaled creatures. Door logic still "
                 "unrandomized pending .p3d.",
        "transforms": ["cutscene_bypass", "xp_boost", "levelcap_raise"],
        "risk": "medium — untested in game",
    },
    "peaceful": {
        "label": "No Enemies",
        "blurb": "Every monster spawn unlinked from its navpoint and hostile creature "
                 "definitions re-teamed. Walk the world, fight nobody.",
        "transforms": ["enemies_none"],
        "risk": "medium - the disarm mechanism is not yet verified in game",
    },
    "invasion": {
        "label": "Enemy Swarm",
        "blurb": "Peaceful placements become monsters and the monsters are reshuffled. The "
                 "harshest thing the text layer can do without adding bytes.",
        "transforms": ["enemies_swarm", "enemies_random"],
        "risk": "high - quest NPCs are consumed; quests will not complete",
    },
    "impossible": {
        "label": "Impossible Enemies",
        "blurb": "Hostile creatures pinned to the top of every stat field they own and to "
                 "the highest level their +Level: field can hold.",
        "transforms": ["enemy_difficulty"],
        "options": {"enemy_difficulty": {"level": "impossible"}},
        "risk": "high - untested in game; may be unwinnable by design",
    },
    "easy_enemies": {
        "label": "Easy Enemies",
        "blurb": "Hostile creatures cut to three quarters hit points, aggression and reach - "
                 "plus whatever the difficulty dial is set to.",
        "transforms": ["enemy_difficulty"],
        "options": {"enemy_difficulty": {"level": "easy"}},
        "risk": "low",
    },
    "oops_all_enemies": {
        "label": "Oops, All Enemies",
        "blurb": "Every peaceful placement becomes a hostile creature of equal name length, "
                 "and the existing monsters are reshuffled for good measure. The people who "
                 "lived in the world are gone.",
        "transforms": ["enemies_amount", "enemies_random"],
        "options": {"enemies_amount": {"amount": "all"}},
        "risk": "high - quest NPCs and shopkeepers are consumed; quests will not complete",
    },
    "everything": {
        "label": "Everything",
        "blurb": "All implemented transforms except NPC behaviour, pacing included.",
        "transforms": ["lock_shuffle", "door_name_shuffle", "door_sound_shuffle",
                       "npc_character_shuffle", "model_ref_shuffle", "cutscene_shuffle",
                       "material_shuffle", "cutscene_bypass", "xp_boost", "levelcap_raise",
                       "item_scatter", "shop_shuffle", "chest_shuffle", "dialogue_shuffle",
                       "sound_shuffle", "music_shuffle", "spawn_shuffle",
                       "animation_shuffle", "icon_shuffle", "vfx_shuffle",
                       "camera_shuffle", "fog_shuffle", "slot_shuffle",
                       "creature_stats_shuffle"],
        "risk": "medium — excludes +Action on purpose",
    },

    # ---- world / progression ----
    "ring_hunt": {
        "label": "Ring Hunt",
        "blurb": "The Forge of Urath opens at a chosen event instead of after all eight "
                 "rings. Changes how the game ENDS, not how it looks.",
        "transforms": ["ring_hunt"],
        "risk": "medium — changes progression, needs a boot test",
    },
    "ring_hunt_any": {
        "label": "Ring Hunt · Any Ring",
        "blurb": "The ending opens on ANY of the seven rings that have a nearby anchor, "
                 "instead of all eight. Find one ring, finish the game.",
        "transforms": ["ring_hunt"],
        "options": {"ring_hunt": {"anchor": "any-ring"}},
        "risk": "medium — changes progression, needs a boot test",
    },
    "ring_hunt_short": {
        "label": "Ring Hunt · Short",
        "blurb": "Ring Hunt plus no cutscenes and no grind. The intended one-sitting run.",
        "transforms": ["ring_hunt", "cutscene_bypass", "xp_boost", "levelcap_raise"],
        "risk": "medium — two untested levers stacked",
    },
    "progression": {
        "label": "Progression",
        "blurb": "Dial the two progression levers yourself: XP per kill and how high "
                 "creatures are allowed to level. Deterministic by design, so a seed "
                 "plays the same every time. Defaults double both.",
        "transforms": ["xp_scale", "levelcap_set"],
        "options": {"xp_scale": {"percent": 200}, "levelcap_set": {"percent": 200}},
        "risk": "low — pacing dials only, nothing structural moved; untested in game",
    },

    # ---- content ----
    "item_scatter": {
        "label": "Item Scatter",
        "blurb": "Which item sits at which pickup point is shuffled, so loot is not where "
                 "you remember it.",
        "transforms": ["item_scatter"],
        "risk": "low — cosmetic placement, no lock risk",
    },
    "shop_shuffle": {
        "label": "Shop Shuffle",
        "blurb": "Every shop price is shuffled among equal widths. A 25-gold item can cost "
                 "600 and vice versa.",
        "transforms": ["shop_shuffle"],
        "risk": "low",
    },
    "free_shops": {
        "label": "Free Shops",
        "blurb": "Every shop price becomes 0, each inside its own field width. Take what you "
                 "like.",
        "transforms": ["shops_free"],
        "risk": "low - prices only, no structure moved",
    },
    "crazy_prices": {
        "label": "Crazy Prices",
        "blurb": "Every shop price becomes the largest number its own field can hold - 999, "
                 "9999, 999999 - so nothing is affordable.",
        "transforms": ["shops_crazy"],
        "risk": "low - prices only, no structure moved",
    },
    "no_shops": {
        "label": "No Shops",
        "blurb": "Every shopkeeper's placement is re-pointed at an equal-length non-shopkeeper, "
                 "so no shop can be reached. The shop definitions themselves are left "
                 "untouched.",
        "transforms": ["shops_none"],
        "risk": "medium - shopkeepers stop existing; quests that need one cannot complete",
    },
    "chest_shuffle": {
        "label": "Chest Randomisation",
        "blurb": "Container payouts shuffled AND the yield itself randomised, so a crate can "
                 "hold something precious. Gold chests stay gold.",
        "transforms": ["chest_shuffle", "chest_items"],
        "risk": "low",
    },
    "dialogue_chaos": {
        "label": "Dialogue Chaos",
        "blurb": "NPCs say each other's lines. Topic ids untouched, so quests still link.",
        "transforms": ["dialogue_shuffle"],
        "risk": "low — text only, no reference keys moved",
    },
    "sound_chaos": {
        "label": "Sound Chaos",
        "blurb": "Every sound effect and music cue is shuffled. The loudest, safest, "
                 "funniest mode in the list.",
        "transforms": ["sound_shuffle", "music_shuffle"],
        "risk": "low — audio only",
    },
    "rooms": {
        "label": "Random Rooms",
        "blurb": "Randomised rooms, the safe half: within each level the placements swap "
                 "their $Start position anchors, so a level is furnished differently while "
                 "every anchor still exists in that level. Doors, quests, the level graph and "
                 "the navpoint definitions never change, so nothing can become unreachable.",
        "transforms": ["rooms_shuffle"],
        "options": {"rooms_shuffle": {"how": "shuffle"}},
        "risk": "low — anchors permute inside one level only; graph and doors untouched",
    },
    "npc_hunt": {
        "label": "NPC Hunt",
        "blurb": "NPCs are neither where you left them nor who you expect: every placement's "
                 "$Start position anchor moves within its level, and who stands there ($Character) "
                 "is shuffled among equal lengths. The people of the world are relocated and "
                 "re-cast. Cross-level NPC relocation is a designed extension, not shipped "
                 "here - see PLANNED.md 2.5.",
        "transforms": ["spawn_shuffle", "npc_character_shuffle"],
        "risk": "medium — quest NPCs can be re-cast or relocated; quests may not complete",
    },
    "boss_rush": {
        "label": "Boss Rush (BLOCKED)",
        "blurb": "BLOCKED - not achievable in the data. A boss-rush (rooms of fightable bosses, "
                 "chained exit-to-exit) was exhaustively attempted and play-tested; every approach "
                 "crashes or shows empty rooms. Bosses are hidden/scripted set-pieces, NOT "
                 "placement-registered enemies, so they cannot be placed as live foes (the engine "
                 "name-lookup faults); the levels that own them have no disposable NPCs; cross-level "
                 "door chaining into mid-story levels renders black. Full analysis + "
                 "instruction-level crash proof: docs/BOSS-RUSH-INVESTIGATION.md.",
        "transforms": ["boss_rush"],
        "options": {"boss_rush": {"arena": "auto"}},
        "risk": "BLOCKED - see docs/BOSS-RUSH-INVESTIGATION.md",
        "buildable": False,
    },
    "boss_rooms": {
        "label": "Boss Rooms (BLOCKED)",
        "blurb": "BLOCKED - the NPC->boss swap crashes in game. Placing a boss on a normal NPC slot "
                 "faults the engine name-lookup (bosses aren't placement-registered), padding names "
                 "corrupts the record, and the boss levels' NPCs are all scene-critical. "
                 "See docs/BOSS-RUSH-INVESTIGATION.md.",
        "transforms": ["boss_rooms", "enemy_hp_set", "enemy_drops_random"],
        "options": {"boss_rooms": {"levels": 4, "per_level": 6}, "enemy_hp_set": {"value": 1}},
        "binary": [["skip_intro", {}], ["skip_tutorial", {}]],
        "risk": "BLOCKED - see docs/BOSS-RUSH-INVESTIGATION.md",
        "buildable": False,
    },
    "boss_gauntlet": {
        "label": "Boss Gauntlet (BLOCKED)",
        "blurb": "BLOCKED - chaining the boss levels drops you into EMPTY rooms: the bosses are "
                 "hidden/trigger-gated and never activate out of sequence, and some hops bounce to "
                 "the title or render black. See docs/BOSS-RUSH-INVESTIGATION.md.",
        "transforms": ["boss_gauntlet", "boss_rush"],
        "options": {"boss_rush": {"arena": "auto"}},
        "binary": [["skip_tutorial", {}]],
        "risk": "BLOCKED - see docs/BOSS-RUSH-INVESTIGATION.md",
        "buildable": False,
    },
    "item_hunt": {
        "label": "Item Hunt",
        "blurb": "Goods have to be found, not bought: shop stock and quest-reward item names are "
                 "exchanged into containers (equal width only), and the container's old yield "
                 "takes the shelf/reward slot. Stacked with the loose-pickup scatter. Nothing is "
                 "lost or invented - only where a thing is found changes.",
        "transforms": ["item_scatter", "item_hunt"],
        "options": {"item_hunt": {"sources": "both"}},
        "risk": "low — names trade slots at equal width; no totals moved",
    },
    "monster_chaos": {
        "label": "Monster Chaos",
        "blurb": "Creature stats and spawn points shuffled. Enemies stop being uniform and "
                 "show up in unexpected places. The anti-grind mode.",
        "transforms": ["creature_stats_shuffle", "spawn_shuffle"],
        "risk": "medium — changes combat balance, untested in game",
    },
    "enemy_stats": {
        "label": "Random Enemy Stats",
        "blurb": "Randomized enemy HP and stats: the hostile creatures' own numbers are "
                 "shuffled among each other, so the mix changes without the average moving. "
                 "Bosses stay top-tier (style=floor); enemy_difficulty scales, this shuffles.",
        "transforms": ["enemy_stats_random"],
        "options": {"enemy_stats_random": {"style": "floor"}},
        "risk": "medium — combat balance moves; untested in game",
    },
    "glass_enemies": {
        "label": "One-HP Enemies",
        "blurb": "Every enemy is set to 1 hit point — everything hostile dies in a single hit. "
                 "HP fields vary in width, so the 1 is padded into each field rather than "
                 "changing its length; nothing else about a creature is touched.",
        "transforms": ["enemy_stats_random"],
        "options": {"enemy_stats_random": {"hp": "one"}},
        "risk": "medium — trivialises combat by design; untested in game",
    },
    "player_stats": {
        "label": "Random Player Stats",
        "blurb": "Randomized player stats: the playable party's HP, ability points, aggression, "
                 "ranges and turn rates are shuffled among the party. Width tiers preserved so "
                 "nobody is left unplayable (style=floor).",
        "transforms": ["player_stats_random"],
        "options": {"player_stats_random": {"style": "floor"}},
        "risk": "medium — party balance moves; untested in game",
    },
    "stat_chaos": {
        "label": "Stat Chaos",
        "blurb": "Both stat shufflers at once: enemy numbers reshuffled among enemies, party "
                 "numbers among the party. Each side stays internally coherent; the balance "
                 "between and within sides is scrambled.",
        "transforms": ["enemy_stats_random", "player_stats_random"],
        "options": {"enemy_stats_random": {"style": "floor"},
                    "player_stats_random": {"style": "floor"}},
        "risk": "medium — combat and party balance both move; untested in game",
    },
    "behaviour_chaos": {
        "label": "Behaviour Chaos",
        "blurb": "NPC actions and animations shuffled. Characters do the wrong things, in "
                 "the wrong way.",
        "transforms": ["action_shuffle", "animation_shuffle"],
        "risk": "high — +Action drives scripted sequences and can break them",
    },
    "visual_chaos": {
        "label": "Visual Chaos",
        "blurb": "Item icons, spell effects, fog and cutscene cameras all shuffled. The "
                 "game looks wrong on purpose.",
        "transforms": ["icon_shuffle", "vfx_shuffle", "fog_shuffle", "camera_shuffle"],
        "risk": "low — presentation only",
    },
    "total_chaos": {
        "label": "Total Chaos",
        "blurb": "Every single transform, behaviour included. Expect it to be broken; "
                 "that is the point.",
        "transforms": ["lock_shuffle", "door_name_shuffle", "door_sound_shuffle",
                       "npc_character_shuffle", "model_ref_shuffle", "cutscene_shuffle",
                       "material_shuffle", "cutscene_bypass", "xp_boost", "levelcap_raise",
                       "item_scatter", "shop_shuffle", "chest_shuffle", "dialogue_shuffle",
                       "sound_shuffle", "music_shuffle", "spawn_shuffle",
                       "animation_shuffle", "action_shuffle", "icon_shuffle",
                       "vfx_shuffle", "camera_shuffle", "fog_shuffle", "slot_shuffle",
                       "creature_stats_shuffle", "fade_instant"],
        "risk": "very high — includes +Action, which can break scripts",
    },

    # ---- pacing the opening ----
    "fast_start": {
        "label": "Fast Start",
        "blurb": "Cut the opening down: cutscenes skipped, dialogue blanked, fades "
                 "instant, combat scaled. Gets you into the game.",
        "transforms": ["cutscene_bypass", "dialogue_blank", "fade_instant", "xp_boost"],
        "risk": "medium — untested in game",
    },
    "no_dialogue": {
        "label": "No Dialogue",
        "blurb": "Every spoken line and quest objective blanked. Play the game, skip "
                 "the reading.",
        "transforms": ["dialogue_blank", "cutscene_bypass"],
        "risk": "medium — untested in game",
    },

    # ---- genre modes ----
    "roguelike": {
        "label": "Roguelike (BLOCKED)",
        "blurb": "BLOCKED. High variance plus resource pressure: creatures, spawns, loot, "
                 "shops and chests all scrambled, XP cut so you cannot out-level the "
                 "content, and prices driven up. Not offered as a build target "
                 "(stacks eleven unverified changes; marked blocked pending validation).",
        "transforms": ["creature_stats_shuffle", "spawn_shuffle", "item_scatter",
                       "shop_shuffle", "chest_shuffle", "dialogue_shuffle",
                       "sound_shuffle", "music_shuffle", "levelcap_raise",
                       "xp_nerf", "economy_squeeze", "icon_shuffle"],
        "risk": "BLOCKED",
        "buildable": False,
    },
    "roguelike_short": {
        "label": "Roguelike · Short",
        "blurb": "Roguelike pressure with the length taken out: no cutscenes, instant "
                 "fades, blanked dialogue. A single-sitting run.",
        "transforms": ["creature_stats_shuffle", "spawn_shuffle", "item_scatter",
                       "shop_shuffle", "chest_shuffle", "sound_shuffle",
                       "levelcap_raise", "xp_nerf", "economy_squeeze",
                       "cutscene_bypass", "dialogue_blank", "fade_instant"],
        "risk": "high",
    },
    "hardcore": {
        "label": "Hardcore",
        "blurb": "The Roguelike stack plus permadeath: creatures, spawns, loot, shops "
                 "and chests scrambled, XP cut, prices driven up — and the revive "
                 "ability and Revive Scrolls removed so death sticks.",
        "transforms": ["creature_stats_shuffle", "spawn_shuffle", "item_scatter",
                       "shop_shuffle", "chest_shuffle", "dialogue_shuffle",
                       "sound_shuffle", "music_shuffle", "levelcap_raise",
                       "xp_nerf", "economy_squeeze", "icon_shuffle", "permadeath"],
        "risk": "very high — permadeath is untested; a bad action/item name may error",
    },
    # ---- BINARY LAYER: patches the executable, not the script stream ----
    "endgame_gate": {
        "label": "Endgame Gate (binary)",
        "blurb": "Patches the executable itself: lowers the gamestage threshold that arms "
                 "the ending, so the Forge becomes available much earlier. One instruction, "
                 "verified by re-reading it after writing.",
        "transforms": [],
        "binary": [["endgame_gate", {"stage": 5}]],
        "risk": "medium — changes progression, needs a boot test",
    },
    "skip_intro": {
        "label": "Skip Intro Movie (binary)",
        "blurb": "Stops the boot/intro video from playing: it makes the movie-player routine "
                 "return immediately, which neutralises every boot-movie call at once. The intro "
                 "is not in the script layer (zero .pss refs), so this is an executable patch. "
                 "Play-verified - the THQ logo is gone. NOTE: this removes the .pss FMV logos; the "
                 "in-engine story cinematic is a separate $Cutscene and is NOT removed by this "
                 "patch (neutering it hangs the boot).",
        "transforms": [],
        "binary": [["skip_intro", {}]],
        "risk": "low - presentation only; play-verified (boot logos gone)",
    },
    # ---- Modes added to give the 2026-09-28 levers a home ---------------------------
    # Nine transforms shipped with no mode referencing them, so a user browsing the mode
    # list could not find them at all (docs/FEATURES-REGISTER.md \u00a75, defect D4).
    # They fall into three coherent groups, so they get three modes rather than one
    # kitchen sink. Every option below is the transform's own default, stated explicitly
    # so the mode reads as a promise instead of depending on a default that may move.
    "power_trip": {
        "label": "Power Trip",
        "blurb": "You are the boss fight. Every enemy dies in one hit and barely scratches "
                 "you, your weapons and armour are pinned to the top of their fields, every "
                 "kill pays maximum XP, and anything that can drop an item does. Nothing is "
                 "randomised - this is a straight power fantasy, for blasting through the "
                 "story or checking a later area early.",
        "transforms": ["enemy_hp_set", "enemy_damage_set", "weapon_attack_max",
                       "armor_protect_max", "enemy_xp_set", "enemy_drops_always"],
        "options": {"enemy_hp_set": {"value": 1}, "enemy_damage_set": {"value": 0},
                    "enemy_xp_set": {"value": 9999}},
        "risk": "high - trivialises combat by design; untested in game",
    },
    "random_rewards": {
        "label": "Random Rewards",
        "blurb": "Kills stop being predictable: how much XP a creature is worth and which "
                 "item it drops are both shuffled between creatures. A trash mob can pay a "
                 "boss's XP. Shuffling, not inflating - the average is unmoved, only who "
                 "pays what changes.",
        "transforms": ["enemy_xp_random", "enemy_drops_random"],
        "risk": "low - rewards move between enemies; no totals changed",
    },
    "music_only": {
        "label": "Music Only",
        "blurb": "The background music is shuffled and nothing else is touched - the wrong "
                 "track plays in the wrong place, but every sound effect stays correct. The "
                 "gentlest mode in the list; useful on its own or stacked onto another.",
        "transforms": ["music_tracks_shuffle"],
        "risk": "low - music only, no sound effects, no progression risk",
    },
}

PENDING = {
    "anti_grind_encounters": {
        "reason": "Encounter rate and creature stats live in the Rand-* overworld scripts and "
                  "the 59 #Resistances stat blocks. These are addressable but the record "
                  "layout inside those blocks is not yet mapped, so scaling them is unsafe.",
        "blocked_by": "#Resistances block layout",
    },
    "character_colours": {
        "reason": "Only 17 $Material/$Mat records exist in the table layer, which is far too "
                  "few for every character. The real colour data is palettes inside the "
                  ".peg texture packs, which are not decoded.",
        "blocked_by": ".peg texture format",
    },
    # `door_destination_swap` used to be blocked here on the claim that "door destinations are
    # not in TABLES.VPP". That was overturned on 2026-09-20: a door IS the `$Trigger:` name in
    # the level's own `.tbl`, and rewriting it is the `door_destination_remap` transform below.
    # The entry is gone rather than left lying.
    "item_shuffle": {
        "reason": "Item records exist but their location is unconfirmed: .tbl chunk "
                  "names are arbitrary slices, so 'items.tbl' is not the item table.",
        "blocked_by": "blob segmentation map",
    },
    "level_order": {
        "reason": "Needs the runtime numeric level-ID -> name table, which appears to "
                  "live in SLUS_200.74.",
        "blocked_by": "ELF analysis / MAIN.MAP symbols",
    },
    "one_hour_mode": {
        "reason": "Needs the full flag graph plus a reachability solver so seeds can "
                  "never be unbeatable.",
        "blocked_by": "flag graph solver",
    },
    "character_models": {
        "reason": "CHARS.VPP holds 2,556 .mvf files; the format is undecoded.",
        "blocked_by": ".mvf format",
    },
}


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def probe_iso(src: Path) -> dict:
    with src.open("rb") as fh:
        bases = find_all_vpps(fh)
        base, v = pick_tables(fh, bases)
        info = {
            "path": str(src),
            "bytes": src.stat().st_size,
            "vpp_count": len(bases),
            "vpp_bases": [f"0x{b:X}" for b in bases],
        }
        if base is not None:
            info["tables_offset"] = f"0x{base:X}"
            info["tables_entries"] = v.count
            info["tables_declared_size"] = v.total_size
        return info


def _load_tables(src: Path, say, use_cache: bool = True):
    """Read the TABLES.VPP region of an image. The ISO itself is never held in RAM.

    Returns (base, entry_count, blob, ranges).
    """
    with src.open("rb") as fh:
        bases = find_all_vpps_cached(fh, src) if use_cache else find_all_vpps(fh)
        say(f"found {len(bases)} VPP archives")
        base, v = pick_tables(fh, bases)
        if base is None:
            raise ValueError("could not identify TABLES.VPP")
        say(f"TABLES.VPP at 0x{base:X}: {v.count} entries")
        blob = v.blob()
        say(f"script blob {len(blob):,} bytes")
        return base, v.count, blob, list(v.ranges())


def _blob_member_ranges(ranges):
    """Convert VPP (iso_offset, size, member_name) ranges into (level_name, blob_start, blob_end).

    The blob is the tight concatenation of member DATA in member order, so blob offsets are the
    running sum of sizes. The level name is the member filename with _script.tbl/.tbl and a _vN
    suffix stripped (the door-usable level name; see docs/lab/probe_boss_member.py). This is the
    reliable member->level key the boss_gauntlet transform needs.
    """
    out = []
    pos = 0
    for _iso_off, size, name in ranges:
        lvl = name
        for suf in ("_script.tbl", ".tbl"):
            if lvl.lower().endswith(suf):
                lvl = lvl[: -len(suf)]
                break
        lvl = re.sub(r"_v\d+$", "", lvl)
        out.append((lvl, pos, pos + size))
        pos += size
    return out


def _apply_transforms(blob: bytes, seed: str, transforms, say,
                      options: dict | None = None, ranges=None) -> tuple[bytes, list[dict]]:
    """Run the transform chain in order. Every step is length-checked.

    Determinism: one Random(seed) fed to the transforms in list order, so the
    same seed + same list + same options always produces the same bytes.

    Options are per-transform keyword arguments, e.g.
        {"ring_hunt": {"anchor": "act3_finished", "count": 2}}
    Only transforms listed in OPTION_AWARE receive them.

    `ranges` (VPP member ranges) is used to give boss_gauntlet the member->level map, which the
    blob alone does not carry.
    """
    set_boss_gauntlet_ranges(_blob_member_ranges(ranges) if ranges else None)
    rng = Random(seed)
    options = options or {}
    reports: list[dict] = []
    for name in transforms:
        fn = TRANSFORMS.get(name)
        if not fn:
            reports.append({"transform": name, "changed": 0, "refused": True,
                            "notes": ["not implemented"]})
            continue
        kw = dict(options.get(name) or {}) if name in OPTION_AWARE else {}
        kw = {k: v for k, v in kw.items() if v is not None}
        new_blob, rep = fn(blob, rng, **kw) if kw else fn(blob, rng)
        if len(new_blob) != len(blob):
            reports.append({"transform": name, "changed": 0, "refused": True,
                            "notes": [f"REFUSED: size changed {len(blob)} -> {len(new_blob)}"]})
            continue
        blob = new_blob
        reports.append(rep.as_dict())
        say(f"{name}: {rep.changed} edits")
    return blob, reports


def _diff_bytes(a: bytes, b: bytes) -> int:
    """Count byte positions that differ. Chunked int-XOR, no per-byte Python loop."""
    if len(a) != len(b):
        return -1
    step = 1 << 20
    diff = 0
    for i in range(0, len(a), step):
        xa, xb = a[i:i + step], b[i:i + step]
        x = int.from_bytes(xa, "big") ^ int.from_bytes(xb, "big")
        diff += len(xa) - x.to_bytes(len(xa), "big").count(0)
    return diff


def dry_run_iso(src: Path, seed: str, transforms: list[str], progress=None,
                options: dict | None = None, binary_patches=None) -> dict:
    """Work out exactly what a build would change without writing the big ISO.

    Reads only the ~7 MB TABLES.VPP region, runs the same transform chain the
    real pipeline would, and reports per-transform edit counts plus how many
    blob bytes would differ. No output file is created.
    """
    say = progress or (lambda _m: None)
    say("dry run: reading TABLES.VPP only, no output written")
    base, entries, blob, ranges = _load_tables(src, say)
    order = list(transforms)
    new_blob, reports = _apply_transforms(blob, seed, order, say, options, ranges=ranges)

    # per-transform impact measured on its own, against the untouched blob
    for rep in reports:
        fn = TRANSFORMS.get(rep["transform"])
        if not fn or rep.get("refused"):
            rep["impact_bytes"] = 0
            continue
        kw = {}
        if rep["transform"] in OPTION_AWARE:
            kw = {k: v for k, v in ((options or {}).get(rep["transform"]) or {}).items()
                  if v is not None}
        solo_blob, _solo = fn(blob, Random(seed), **kw) if kw else fn(blob, Random(seed))
        rep["impact_bytes"] = _diff_bytes(blob, solo_blob) if len(solo_blob) == len(blob) else 0

    changed_positions = _diff_bytes(blob, new_blob)
    say(f"would change {changed_positions:,} of {len(blob):,} blob bytes")

    # binary layer, read-only: confirm the instructions we expect are actually
    # present in the executable. Nothing is written during a dry run.
    binary_report: list[dict] = []
    if binary_patches:
        if not _HAVE_BINARY:
            binary_report = [{"patch": n, "applied": False,
                              "notes": ["binary.py missing"]} for n, _p in binary_patches]
        else:
            try:
                loc = binary.find_elf(src)
                with src.open("rb") as fh:
                    for name, params in binary_patches:
                        p = binary.PATCHES.get(name)
                        if p is None:
                            binary_report.append({"patch": name, "applied": False,
                                                  "notes": ["unknown patch"]})
                            continue
                        off = binary.va_to_iso_offset(p.va, loc)
                        fh.seek(off)
                        word = int.from_bytes(fh.read(4), "little")
                        ok = word == p.original
                        binary_report.append({
                            "patch": name, "applied": False, "dry": True,
                            "va": f"0x{p.va:08X}", "iso_offset": f"0x{off:X}",
                            "found": f"0x{word:08X}", "expects": f"0x{p.original:08X}",
                            "would_write": f"0x{p.encode(params):08X}",
                            "ready": ok,
                            "notes": [p.label] + ([] if ok else
                                      [f"REFUSED: expected 0x{p.original:08X}, found 0x{word:08X}"]),
                        })
                say(f"binary: {sum(1 for r in binary_report if r.get('ready'))}"
                    f"/{len(binary_report)} patch(es) ready")
            except Exception as exc:  # noqa: BLE001
                binary_report = [{"patch": "(elf)", "applied": False,
                                  "notes": [f"could not inspect executable: {exc}"]}]

    return {
        "dry": True,
        "seed": seed,
        "src": str(src),
        "src_bytes": src.stat().st_size,
        "tables_offset": f"0x{base:X}",
        "tables_entries": entries,
        "entries_read": len(ranges),
        "blob_bytes": len(blob),
        "changed_bytes_total": changed_positions,
        "edit_total": sum(r.get("changed", 0) for r in reports),
        "transforms": order,
        "options": options or {},
        "reports": reports,
        "writes_file": False,
        "binary": binary_report,
    }


def randomize_iso(src: Path, dst: Path, seed: str, transforms: list[str],
                  progress=None, options: dict | None = None,
                  binary_patches=None) -> dict:
    say = progress or (lambda _m: None)

    src_bytes = src.stat().st_size
    dst.parent.mkdir(parents=True, exist_ok=True)

    base, entries, blob, ranges = _load_tables(src, say)
    blob, reports = _apply_transforms(blob, seed, list(transforms), say, options, ranges=ranges)

    say("copying image")
    shutil.copyfile(src, dst)

    say("patching entries")
    pos = 0
    with dst.open("r+b") as out:
        out.seek(0, 2)
        if out.tell() != src_bytes:
            raise ValueError("copy size mismatch")
        for iso_off, size, _ename in ranges:
            out.seek(iso_off)
            out.write(blob[pos:pos + size])
            pos += size
        out.flush()
        if pos != len(blob):
            raise ValueError(f"entry sizes ({pos}) != blob size ({len(blob)})")

    # ---- binary layer: patch the executable itself -------------------------
    binary_report = []
    if binary_patches:
        if not _HAVE_BINARY:
            raise ValueError("binary.py is missing; cannot apply binary patches")
        say("patching the executable")
        bres = binary.apply_patches(dst, list(binary_patches), progress=say)
        binary_report = bres["patches"]

    return {
        "seed": seed,
        "src": str(src),
        "dst": str(dst),
        "transforms": list(transforms),
        "options": options or {},
        "src_sha256": sha256_file(src),
        "dst_sha256": sha256_file(dst),
        "src_bytes": src_bytes,
        "dst_bytes": dst.stat().st_size,
        "size_preserved": src_bytes == dst.stat().st_size,
        "tables_entries": entries,
        "changed_entries_region": {"offset": base + data_start(entries), "bytes": len(blob)},
        "reports": reports,
        "binary": binary_report,
    }


def sha256_file(p: Path, chunk: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest().upper()
