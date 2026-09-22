#!/usr/bin/env python3
r"""Randomizer core: load a Summoner PS2 ISO, transform it, write a new ISO.

File-based on purpose: the N100 has 8 GB total and these images are 1.2-3 GB, so
nothing here ever holds a whole ISO in memory. We only ever touch the TABLES.VPP
region (~7 MB).

Facts this relies on (see notes/summoner-findings.md):
  * Every .VPP starts with magic 0x51890ACE. Layout: 16-byte header, zero pad to
    0x800, then count x 64-byte records (name[48], 3 reserved u32, u32 size),
    then entry data at 0x1000, packed sequentially with no padding.
  * TABLES.VPP entries are arbitrary slices of one continuous text stream, so all
    transforms operate on the reassembled blob and MUST be size-preserving.
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
HEADER_PAD = 0x800
REC_SIZE = 64
DATA_START = 0x1000


# --------------------------------------------------------------------------- #
# VPP over a file handle
# --------------------------------------------------------------------------- #
@dataclass
class VppEntry:
    name: str
    size: int
    offset: int          # relative to data start


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
        off = DATA_START
        for i in range(self.count):
            raw = toc[i * REC_SIZE:(i + 1) * REC_SIZE]
            name = raw[:48].split(b"\x00")[0].decode("latin-1")
            size = struct.unpack_from("<I", raw, 60)[0]
            self.entries.append(VppEntry(name, size, off))
            off += size

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
        fh.seek(b + DATA_START)
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
                     group: int = 1, label: str = "refs") -> bytes:
    """Shuffle capture-group values among matches of equal length."""
    hits = list(re.finditer(pattern, blob))
    if not hits:
        rep.notes.append(f"no {label} found")
        return blob
    by_len: dict[int, list] = {}
    for m in hits:
        by_len.setdefault(len(m.group(group)), []).append(m)
    out = bytearray(blob)
    for ln, ms in by_len.items():
        if len(ms) < 2:
            continue
        vals = [m.group(group) for m in ms]
        shuf = vals[:]
        rng.shuffle(shuf)
        for m, v in zip(ms, shuf):
            if v != m.group(group):
                rep.changed += 1
            out[m.start(group):m.end(group)] = v
    rep.notes.append(f"{len(hits)} {label} across {len(by_len)} length classes")
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


def t_door_name_shuffle(blob, rng):
    """Shuffle $Door names among equal lengths."""
    rep = Report("door_name_shuffle")
    return _shuffle_matches(blob, rb'\$Door:\s*"([^"]+)"', rng, rep,
                            label="$Door names"), rep


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
    out = []
    for m in re.finditer(rb"#Character Info", blob):
        s = m.end()
        nxt = re.search(rb"\n#(?!Character Info)", blob[s:])
        e = s + (nxt.start() if nxt else 3000)
        t = TEAM_RE.search(blob[s:e])
        if t and t.group(2) in HOSTILE_TEAMS:
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


def t_enemies_random(blob, rng):
    """Randomize WHICH creature stands on each monster placement, and at what level.

    Same number of enemies, different ones - the safe direction (contents, not counts). Names
    are swapped only between equal-length names, and `+Level:` only between equal-width
    values, so every edit stays inside its field.
    """
    rep = Report("enemies_random")
    monsters, _ = _analyse_enemies(blob)
    if not monsters:
        rep.notes.append("no +Monster placements found")
        return blob, rep
    out = bytearray(blob)
    by_len: dict[int, list] = {}
    for rec in monsters:
        by_len.setdefault(len(rec["char"]), []).append(rec)
    swapped = 0
    for ln, recs in sorted(by_len.items()):
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
    rep.notes.append(f"{len(monsters)} monster placements, {len(by_len)} name lengths")
    rep.notes.append(f"{swapped} creatures swapped for an equal-length creature")

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
                "enemies_none", "enemies_swarm", "enemies_random", "enemies_amount"}

OPTIONS = {
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
    "dialogue_shuffle": t_dialogue_shuffle,
    "fade_instant": t_fade_instant,
    "dialogue_blank": t_dialogue_blank,
    "enemies_none": t_enemies_none,
    "enemies_amount": t_enemies_amount,
    "enemies_random": t_enemies_random,
    "enemies_swarm": t_enemies_swarm,
    "enemy_difficulty": t_enemy_difficulty,
    "shops_free": t_shops_free,
    "shops_crazy": t_shops_crazy,
    "shops_none": t_shops_none,
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
        "blurb": "No changes. Baseline for comparing against.",
        "transforms": [],
        "risk": "none",
    },
    "doors": {
        "label": "Door Shuffle",
        "blurb": "Door locks, names and sounds shuffled. No progression risk.",
        "transforms": ["lock_shuffle", "door_name_shuffle", "door_sound_shuffle"],
        "risk": "low",
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
        "label": "Chest Shuffle",
        "blurb": "Container payouts shuffled. Only the multi-digit gold chests really move.",
        "transforms": ["chest_shuffle"],
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
    "monster_chaos": {
        "label": "Monster Chaos",
        "blurb": "Creature stats and spawn points shuffled. Enemies stop being uniform and "
                 "show up in unexpected places. The anti-grind mode.",
        "transforms": ["creature_stats_shuffle", "spawn_shuffle"],
        "risk": "medium — changes combat balance, untested in game",
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
        "label": "Roguelike",
        "blurb": "High variance plus resource pressure: creatures, spawns, loot, "
                 "shops and chests all scrambled, XP cut so you cannot out-level the "
                 "content, and prices driven up. Every seed plays as a run.",
        "transforms": ["creature_stats_shuffle", "spawn_shuffle", "item_scatter",
                       "shop_shuffle", "chest_shuffle", "dialogue_shuffle",
                       "sound_shuffle", "music_shuffle", "levelcap_raise",
                       "xp_nerf", "economy_squeeze", "icon_shuffle"],
        "risk": "high — stacks eleven changes, untested in game",
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
    "door_destination_swap": {
        "reason": "Door destinations are not in TABLES.VPP. $Door blocks carry only "
                  "sound + lock data; the door -> level link lives in the .p3d level "
                  "geometry, which is not decoded yet.",
        "blocked_by": ".p3d format",
    },
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


def _apply_transforms(blob: bytes, seed: str, transforms, say,
                      options: dict | None = None) -> tuple[bytes, list[dict]]:
    """Run the transform chain in order. Every step is length-checked.

    Determinism: one Random(seed) fed to the transforms in list order, so the
    same seed + same list + same options always produces the same bytes.

    Options are per-transform keyword arguments, e.g.
        {"ring_hunt": {"anchor": "act3_finished", "count": 2}}
    Only transforms listed in OPTION_AWARE receive them.
    """
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
    new_blob, reports = _apply_transforms(blob, seed, order, say, options)

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
    blob, reports = _apply_transforms(blob, seed, list(transforms), say, options)

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
        "changed_entries_region": {"offset": base + DATA_START, "bytes": len(blob)},
        "reports": reports,
        "binary": binary_report,
    }


def sha256_file(p: Path, chunk: int = 4 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(chunk), b""):
            h.update(blk)
    return h.hexdigest().upper()
