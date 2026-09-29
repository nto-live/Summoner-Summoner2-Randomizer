#!/usr/bin/env python3
r"""Binary layer — patch the game executable (SLUS_200.74) inside an ISO.

Everything else in this project edits the *script stream*. This edits the *code*.

    ISO byte image
      ... ISO9660 ...
        SLUS_200.74   <- an 18 MB EE ELF living as a plain file on the disc
            ELF header -> one PT_LOAD: vaddr 0x00100000 -> file offset 0x1000
      ...

    iso_offset = elf_file_offset + (vaddr - segment_vaddr) + segment_file_offset

So once we know where the ELF sits on the disc, a virtual address becomes a
byte-exact offset and an instruction becomes four bytes we can rewrite.

SAFETY RULES, all enforced in code
  * Every patch declares the instruction it EXPECTS to find. If the bytes on the
    disc do not match, the patch is refused. That is what stops us corrupting a
    different disc revision, or the wrong address.
  * 4-byte instruction swaps only. Size-preserving, so nothing moves.
  * Every patch is verified by re-reading it after writing.
  * Patches are reversible: the original word is recorded.

Stdlib only.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
PT_LOAD = 1
VADDR_BASE = 0x00100000      # observed base of SLUS_200.74
ELF_FILE_OFF_BASE = 0x1000   # observed file offset of the first segment


# --------------------------------------------------------------------------- #
# locating the executable inside the disc image
# --------------------------------------------------------------------------- #
@dataclass
class ElfLocation:
    iso_offset: int          # where the ELF starts in the ISO byte image
    size: int                # size of the ELF as stored on disc
    entry: int               # e_entry
    seg_vaddr: int           # PT_LOAD p_vaddr
    seg_offset: int          # PT_LOAD p_offset
    seg_filesz: int          # PT_LOAD p_filesz
    machine: int

    def as_dict(self) -> dict:
        return {
            "iso_offset": f"0x{self.iso_offset:X}",
            "size": self.size,
            "entry": f"0x{self.entry:08X}",
            "segment": f"vaddr 0x{self.seg_vaddr:08X} -> file 0x{self.seg_offset:X}",
            "filesz": self.seg_filesz,
        }


def _valid_elf(b: bytes, off: int) -> ElfLocation | None:
    """Validate a candidate ELF header at `off`. Returns None if implausible."""
    if b[off:off + 4] != ELF_MAGIC:
        return None
    ei_class, ei_data = b[off + 4], b[off + 5]
    if ei_class != 1 or ei_data != 1:          # 32-bit, little-endian
        return None
    e_type, e_machine = struct.unpack_from("<HH", b, off + 16)
    if e_type != 2 or e_machine != 8:          # EXEC, MIPS
        return None
    e_entry, e_phoff = struct.unpack_from("<II", b, off + 24)
    e_phnum = struct.unpack_from("<H", b, off + 44)[0]
    if e_phoff == 0 or e_phnum == 0:
        return None
    # first PT_LOAD tells us how virtual addresses map onto the file
    seg = None
    for i in range(e_phnum):
        po = off + e_phoff + i * 32
        try:
            p_type, p_offset, p_vaddr, _p_paddr, p_filesz = struct.unpack_from(
                "<IIIII", b, po)
        except struct.error:
            return None
        if p_type == PT_LOAD:
            seg = (p_offset, p_vaddr, p_filesz)
            break
    if seg is None:
        return None
    p_offset, p_vaddr, p_filesz = seg
    # size on disc: up to the end of the last section, approximate by the loadable
    # image plus headers; we only need it for bounds checks
    size = max(p_offset + p_filesz, e_phoff + e_phnum * 32)
    return ElfLocation(off, size, e_entry, p_vaddr, p_offset, p_filesz, e_machine)


def find_elf(iso: Path) -> ElfLocation:
    """Scan the image for the game executable. Validates before accepting."""
    with iso.open("rb") as fh:
        # the ELF is a small file on a big disc; scan in chunks for the magic
        chunk = 8 << 20
        pos, carry = 0, b""
        while True:
            fh.seek(pos)
            buf = carry + fh.read(chunk)
            if not buf:
                break
            start = 0
            while True:
                i = buf.find(ELF_MAGIC, start)
                if i < 0:
                    break
                loc = _valid_elf(buf, i)
                if loc is not None:
                    loc.iso_offset += pos - len(carry)
                    return loc
                start = i + 4
            carry = buf[-64:]
            pos += len(buf) - len(carry)
    raise ValueError("no valid PS2 EE ELF found in the image")


# --------------------------------------------------------------------------- #
# address translation
# --------------------------------------------------------------------------- #
def va_to_iso_offset(va: int, loc: ElfLocation) -> int:
    """Virtual address -> absolute byte offset in the ISO image."""
    delta = va - loc.seg_vaddr
    if delta < 0 or delta >= loc.seg_filesz:
        raise ValueError(f"0x{va:08X} is outside the loadable segment")
    return loc.iso_offset + loc.seg_offset + delta


# --------------------------------------------------------------------------- #
# patches
# --------------------------------------------------------------------------- #
@dataclass
class Patch:
    """One named binary edit.

    `va`        virtual address of the instruction, or None if not yet resolved
    `original`  the 4 bytes we EXPECT there (refuse otherwise)
    `encode`    (params) -> new 4-byte instruction
    `blocked`   a reason string when the patch is known-but-unresolved. Such a patch is
                listed in the catalogue and always refuses (never writes) — so a feature
                can be exposed honestly before its address has been found, instead of
                guessing an address and risking a live-call corruption.
    """
    name: str
    va: int | None
    original: int
    encode: object
    label: str
    help: str
    params: dict = field(default_factory=dict)
    blocked: str | None = None
    # Some patches need to rewrite more than one instruction (e.g. an early-return is
    # `jr $ra` + a delay-slot word). `extra` lists additional words as
    # (byte_delta_from_va, expected_original, new_word). Each is verified and refused on
    # mismatch exactly like the primary word, so the safety guarantee is unchanged.
    extra: list = field(default_factory=list)


def enc_slti(rs: int, rt: int, imm: int) -> int:
    """slti rt, rs, imm   (opcode 0x0A)"""
    return (0x0A << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def enc_addiu(rs: int, rt: int, imm: int) -> int:
    """addiu rt, rs, imm  (opcode 0x09)"""
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


# Verified against the disc: 0x00212274 holds 0x28420015 == slti $v0,$v0,21,
# the gamestage test that arms the endgame gate. Raising or lowering the
# threshold changes WHEN the ending becomes available.
PATCHES: dict[str, Patch] = {
    "endgame_gate": Patch(
        name="endgame_gate",
        va=0x00212274,
        original=0x28420015,
        encode=lambda p: enc_slti(2, 2, int(p.get("stage", 5))),
        label="Endgame gate stage",
        help="the gamestage threshold that arms the ending. Lower = ending available earlier.",
        params={"stage": {"type": "int", "default": 5, "min": 1, "max": 30}},
    ),
    # Skip the boot movie. The intro is NOT in the data layer - there are zero `.pss`
    # references in TABLES.VPP; the video is played by the executable itself
    # (`code/vsdk/ps2_movieplayer/mplayer.o`, per MODES.md / docs/FEATURES.md §7). So this
    # is a binary patch.
    #
    # RESOLVED in the Ghidra R5900 project (SLUS_200.74, r5900:LE:32), then corrected after a
    # boot test still showed the movies. The movie player is FUN @ 0x002419C0 (opens/plays a
    # .pss). There are exactly FOUR calls to it, all on the boot logo path:
    #   0x00227E00 (thqlogo.pss)  in FUN_00227DC8
    #   0x00227EC8 (demo.pss)     in FUN_00227E88
    #   0x00227EE0 (thqlogo.pss)  in FUN_00227E88   (which then tail-jumps into FUN_00227DC8)
    #   0x0023FA6C (geeks.pss)    in FUN_0023F9B8
    # Those wrappers are reached from TWO boot state machines (0x0022A1C0 and 0x0022A428), so
    # no-op-ing a single dispatch slot (the first attempt at 0x0022A2C8) did NOT stop playback.
    #
    # The robust fix is at the single choke point: make the movie player return immediately with a
    # non-zero status. Every caller does `bne v0, zero, <skip the rest>` after the call, i.e. a
    # non-zero return means "handled, move on". So overwriting the player's first two instructions
    # with `jr $ra` + `li v0,1` makes all four call sites a no-op that returns "done" without
    # opening any video. One function patched, every path covered, arguments in the delay slots
    # become harmless dead computation.
    #   0x002419C0: 0x27BDFEF0 (addiu sp,sp,-0x110)  -> 0x03E00008 (jr $ra)
    #   0x002419C4: 0xFFB400B0 (sd s4,0xB0(sp))      -> 0x24020001 (li v0,1)  [delay slot]
    # Both originals verified byte-for-byte against the retail ISO. Covers the THQ logo, the
    # attract demo, AND the Volition "geeks" logo.
    "skip_intro": Patch(
        name="skip_intro",
        va=0x002419C0,
        original=0x27BDFEF0,           # addiu sp,sp,-0x110  (movie player prologue)
        encode=lambda p: 0x03E00008,   # jr $ra  -> return immediately
        extra=[
            # delay slot: li v0,1 so callers see a non-zero "handled" status and skip playback
            (0x4, 0xFFB400B0, 0x24020001),
        ],
        label="Skip the startup movie",
        help="Stops the boot/intro videos (THQ logo, attract demo, and Volition logo) from "
             "playing. Executable-side: the intro is not in the script layer (zero .pss refs), so "
             "this is an ELF patch. It makes the movie-player routine return immediately, which "
             "neutralises every boot-movie call at once. NOTE: this removes the .pss FMV logos; "
             "the in-engine story cinematic is a separate $Cutscene and is NOT removed by this "
             "patch (neutering it hangs the boot).",
    ),
    # Skip the tutorials - BLOCKED. Investigated exhaustively in Ghidra AND tested in game; the
    # tutorial machinery is fused with the opening scripted sequence and cannot be separated.
    # Three approaches, all resolved to real addresses, all proven to break the game:
    #   v1  force the ignore-global on  (0x0023D648 `lw v0,-0x3a70(gp)` -> `li v0,1`): early-outs
    #       before the 17-step loop, so the steps' flag_set calls never run -> first-level firewall
    #       never drops. Soft-lock. PROVEN IN GAME.
    #   v2  NOP the popup-activate branch (0x0023D6B4 `bne v0,zero,0x0023d65c` -> nop): popups gone,
    #       but the scripted burning-village intro never advanced (activation also drives the
    #       scene). Stall. PROVEN IN GAME.
    #   v3  auto-advance the tail (0x0023D74C `beq s0,zero,0x0023d760` -> nop): same stall - the
    #       burning-village intro does not advance. PROVEN IN GAME. A CONTROL disc identical except
    #       WITHOUT this patch plays the intro fine, so the patch is the cause.
    # CONCLUSION: the dispatcher FUN_0023D618 runs BOTH the tutorial popups and the opening quest
    # scene advance through the same path; every lever that removes the popups also stalls the
    # scene. There is no separable "display only" chokepoint. Do not re-attempt without a new
    # mechanism. Full write-up: docs/RESEARCH-SKIP-TUTORIAL.md. The va/original below are the last
    # (v3) resolved site, kept for the record; `blocked` makes the applier refuse and write nothing.
    "skip_tutorial": Patch(
        name="skip_tutorial",
        va=0x0023D74C,
        original=0x12000004,           # beq s0,zero,0x0023d760  (dispatcher tail advance gate)
        encode=lambda p: 0x00000000,
        label="Skip the tutorials",
        help="Would turn off the in-game tutorial popups. BLOCKED: proven in game that every "
             "resolved patch also stalls the scripted opening (the burning-village intro never "
             "advances) - the tutorial and the opening quest share the same dispatcher path and "
             "cannot be separated. See docs/RESEARCH-SKIP-TUTORIAL.md.",
        blocked="the tutorial dispatcher (FUN_0023D618) drives both the popups and the opening "
                "scripted scene through one path; all three resolved patches (ignore-global, "
                "NOP-activation, auto-advance) break the burning-village intro in game. No "
                "separable display-only lever exists. See docs/RESEARCH-SKIP-TUTORIAL.md.",
    ),
}


# --------------------------------------------------------------------------- #
# applying patches
# --------------------------------------------------------------------------- #
def apply_patches(iso: Path, patches: list[tuple[str, dict]], progress=None) -> dict:
    """Apply named patches to the executable inside an ISO, in place.

    Returns a report including, per patch, the original and new instruction and
    whether verification passed. Raises on a mismatch rather than guessing.
    """
    say = progress or (lambda _m: None)
    loc = find_elf(iso)
    say(f"executable at ISO 0x{loc.iso_offset:X}: {loc.size:,} bytes, "
        f"seg vaddr 0x{loc.seg_vaddr:08X} -> file 0x{loc.seg_offset:X}")

    results = []
    with iso.open("r+b") as fh:
        for name, params in patches:
            p = PATCHES.get(name)
            if p is None:
                results.append({"patch": name, "applied": False,
                                "notes": ["unknown patch"]})
                continue
            if p.blocked or p.va is None:
                results.append({
                    "patch": name, "applied": False,
                    "notes": [f"BLOCKED: {p.blocked or 'address not resolved'}. "
                              f"Nothing was written."],
                })
                continue
            # Build the full list of words this patch writes: the primary word, then any
            # `extra` words. Each entry is (va, expected_original, new_word).
            words = [(p.va, p.original, p.encode(params))]
            for delta, orig, neww in p.extra:
                words.append((p.va + delta, orig, neww))

            # First pass: read and verify EVERY expected original before writing anything.
            # If any word mismatches, refuse the whole patch and leave the disc untouched.
            refused = None
            reads = []
            for wva, worig, _wnew in words:
                woff = va_to_iso_offset(wva, loc)
                fh.seek(woff)
                wbefore = struct.unpack("<I", fh.read(4))[0]
                reads.append((wva, woff, wbefore))
                if wbefore != worig:
                    refused = (f"REFUSED: expected 0x{worig:08X} at 0x{wva:08X}, "
                               f"found 0x{wbefore:08X}. Wrong disc revision or wrong address.")
                    break
            if refused:
                results.append({
                    "patch": name, "applied": False, "va": f"0x{p.va:08X}",
                    "notes": [refused],
                })
                continue

            # Second pass: write and verify each word.
            changes = []
            all_ok = True
            for (wva, worig, wnew), (_v, woff, wbefore) in zip(words, reads):
                fh.seek(woff)
                fh.write(struct.pack("<I", wnew))
                fh.flush()
                fh.seek(woff)
                wafter = struct.unpack("<I", fh.read(4))[0]
                ok = wafter == wnew
                all_ok = all_ok and ok
                say(f"{name}: 0x{wbefore:08X} -> 0x{wnew:08X} at 0x{wva:08X}"
                    f"{' (verified)' if ok else ' (VERIFY FAILED)'}")
                changes.append({
                    "va": f"0x{wva:08X}", "iso_offset": f"0x{woff:X}",
                    "before": f"0x{wbefore:08X}", "after": f"0x{wafter:08X}", "ok": ok,
                })

            first = changes[0]
            results.append({
                "patch": name, "applied": all_ok, "va": f"0x{p.va:08X}",
                "iso_offset": first["iso_offset"],
                "before": first["before"], "after": first["after"],
                "words": changes,
                "notes": [p.label, p.help] + ([] if all_ok else ["VERIFY FAILED"]),
            })
    return {"elf": loc.as_dict(), "patches": results}


def describe() -> dict:
    """Catalogue of binary patches, for the UI."""
    out = {}
    for name, p in PATCHES.items():
        entry = {
            "label": p.label, "help": p.help,
            "va": (f"0x{p.va:08X}" if p.va is not None else None),
            "expects": (f"0x{p.original:08X}" if p.va is not None else None),
            "params": p.params,
        }
        if p.blocked:
            entry["blocked"] = p.blocked
        out[name] = entry
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        loc = find_elf(Path(sys.argv[1]))
        print(loc.as_dict())
    else:
        print("usage: binary.py <iso>")
