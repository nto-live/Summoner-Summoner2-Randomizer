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

    `va`        virtual address of the instruction
    `original`  the 4 bytes we EXPECT there (refuse otherwise)
    `encode`    (params) -> new 4-byte instruction
    """
    name: str
    va: int
    original: int
    encode: object
    label: str
    help: str
    params: dict = field(default_factory=dict)


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
            off = va_to_iso_offset(p.va, loc)
            fh.seek(off)
            before = struct.unpack("<I", fh.read(4))[0]
            if before != p.original:
                results.append({
                    "patch": name, "applied": False, "va": f"0x{p.va:08X}",
                    "notes": [f"REFUSED: expected 0x{p.original:08X} at 0x{p.va:08X}, "
                              f"found 0x{before:08X}. Wrong disc revision or wrong address."],
                })
                continue
            new = p.encode(params)
            fh.seek(off)
            fh.write(struct.pack("<I", new))
            fh.flush()
            # verify
            fh.seek(off)
            after = struct.unpack("<I", fh.read(4))[0]
            ok = after == new
            say(f"{name}: 0x{before:08X} -> 0x{new:08X} at 0x{p.va:08X}"
                f"{' (verified)' if ok else ' (VERIFY FAILED)'}")
            results.append({
                "patch": name, "applied": ok, "va": f"0x{p.va:08X}",
                "iso_offset": f"0x{off:X}",
                "before": f"0x{before:08X}", "after": f"0x{after:08X}",
                "notes": [p.label, p.help] + ([] if ok else ["VERIFY FAILED"]),
            })
    return {"elf": loc.as_dict(), "patches": results}


def describe() -> dict:
    """Catalogue of binary patches, for the UI."""
    return {
        name: {"label": p.label, "help": p.help, "va": f"0x{p.va:08X}",
               "expects": f"0x{p.original:08X}", "params": p.params}
        for name, p in PATCHES.items()
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        loc = find_elf(Path(sys.argv[1]))
        print(loc.as_dict())
    else:
        print("usage: binary.py <iso>")
