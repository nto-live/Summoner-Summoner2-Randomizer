#!/usr/bin/env python3
r"""Disc discovery and identification for the Summoner Randomizer app.

Answers three questions about an ISO the user points us at:

  1. What game is this?          -> volume ID, boot ELF, disc build stamp
  2. Which VPP archive revision? -> v1 (Summoner 1) or v2 (Summoner 2)
  3. Can we actually edit it?    -> supported / unsupported, and why

Why this exists: the app must never silently do nothing. Passing a Summoner 2
disc to a v1-only pipeline previously reported "0 archives found", which reads
like a broken file rather than an unsupported format. Detection makes the
difference explicit and gives the UI something honest to display.

Stdlib only. Uses pycdlib when available for the ISO9660 layer; degrades to a
raw magic scan if it is not.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

VPP_MAGIC = 0x51890ACE

# Volume IDs of the retail US releases
KNOWN_VOLUMES = {
    "SLUS20074": ("Summoner", 1, True),
    "SLUS-20074": ("Summoner", 1, True),
    "SLUS20448": ("Summoner 2", 2, False),
    "SLUS-20448": ("Summoner 2", 2, False),
}

# TABLES.VPP entry count on the Summoner 1 disc, used as a content fingerprint
S1_TABLES_ENTRIES = 527


@dataclass
class VppInfo:
    base: int
    version: int
    count: int
    total_size: int


@dataclass
class DiscInfo:
    path: str = ""
    bytes: int = 0
    volume_id: str = ""
    boot_elf: str = ""
    system_cnf: str = ""
    vpps: list[VppInfo] = field(default_factory=list)
    # verdict
    game: str = "unknown"
    vpp_version: int = 0
    supported: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "bytes": self.bytes,
            "volume_id": self.volume_id,
            "boot_elf": self.boot_elf,
            "system_cnf": self.system_cnf.strip(),
            "vpp_count": len(self.vpps),
            "vpp_bases": [f"0x{v.base:X}" for v in self.vpps],
            "vpp_versions": sorted({v.version for v in self.vpps}),
            "vpp_entries": {f"0x{v.base:X}": v.count for v in self.vpps},
            "game": self.game,
            "vpp_version": self.vpp_version,
            "supported": self.supported,
            "reason": self.reason,
        }


# --------------------------------------------------------------------------- #
# VPP scan — records EVERY revision, unlike the older v1-only filter
# --------------------------------------------------------------------------- #
def scan_vpps(fh, chunk_cap: int = 64 << 20) -> list[VppInfo]:
    """Locate every VPP archive, across BOTH known header revisions.

    v1 header: version at +0x04, entry count at +0x08, archive size at +0x0C
    v2 header: version at +0x04, entry count at +0x3C, archive size at +0x40
               (the v2 header has a large zeroed region, so the v1 offsets read 0)

    Reading only the v1 offsets made a Summoner 2 disc look like it contained no
    archives at all, which is a far more confusing message than "unsupported".
    """
    magic = struct.pack("<I", VPP_MAGIC)
    found: dict[int, VppInfo] = {}
    size = fh.seek(0, 2)
    pos = 0
    overlap = 8
    fh.seek(0)
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
            info = _parse_header(fh, abs_pos, size)
            if info is not None:
                found[abs_pos] = info
            start = i + 4
        if len(buf) < chunk_cap:
            break
        pos += len(buf) - overlap
    fh.seek(0)
    return [found[b] for b in sorted(found)]


def _parse_header(fh, base: int, image_size: int) -> VppInfo | None:
    """Read one candidate header. Returns None if it is not a plausible VPP."""
    try:
        fh.seek(base + 4)
        head = fh.read(16)
        if len(head) < 16:
            return None
        version = struct.unpack_from("<I", head, 0)[0]
        if not (0 < version < 16):
            return None
        if version == 1:
            count, total = struct.unpack_from("<II", head, 4)
        elif version == 2:
            fh.seek(base + 0x3C)
            count, total = struct.unpack("<II", fh.read(8))
        else:
            return None
    except (struct.error, OSError):
        return None
    if not (0 < count < 100000):
        return None
    if not (0 < total <= image_size):
        return None
    return VppInfo(base, version, count, total)


# --------------------------------------------------------------------------- #
# ISO9660 metadata
# --------------------------------------------------------------------------- #
def _iso_metadata(path: Path) -> tuple[str, str, str]:
    """(volume_id, boot_elf, system_cnf_text) — best effort."""
    volume_id = boot_elf = syscnf = ""
    try:
        import pycdlib
    except ImportError:
        # fall back to a raw scan for SYSTEM.CNF
        try:
            with path.open("rb") as fh:
                head = fh.read(4 << 20)
                if b"SYSTEM.CNF" in head:
                    syscnf = ""
            return volume_id, boot_elf, syscnf
        except OSError:
            return volume_id, boot_elf, syscnf

    try:
        cd = pycdlib.PyCdlib()
        cd.open(str(path))
        try:
            volume_id = cd.pvd.volume_identifier.decode(errors="replace").strip()
        except Exception:
            pass
        target = None
        for dirpath, _dirs, files in cd.walk(iso_path="/"):
            for fn in files:
                if fn.upper().startswith("SYSTEM.CNF"):
                    target = dirpath.rstrip("/") + "/" + fn
                    break
            if target:
                break
        if target:
            rec = cd.get_record(iso_path=target)
            data = bytearray()
            sink = _Sink(data)
            cd.get_file_from_iso_fp(sink, iso_path=target)
            syscnf = bytes(data).rstrip(b"\x00").decode(errors="replace")
            for line in syscnf.splitlines():
                if line.upper().startswith("BOOT2") and "=" in line:
                    boot_elf = line.split("=", 1)[1].strip()
        cd.close()
    except Exception:
        pass
    return volume_id, boot_elf, syscnf


class _Sink:
    def __init__(self, ba: bytearray):
        self.ba = ba

    def write(self, b):
        self.ba.extend(b)
        return len(b)

    def close(self):
        pass


# --------------------------------------------------------------------------- #
# verdict
# --------------------------------------------------------------------------- #
def identify(path: str | Path) -> DiscInfo:
    p = Path(path)
    info = DiscInfo(path=str(p))
    if not p.is_file():
        info.reason = f"not a file: {p}"
        return info
    info.bytes = p.stat().st_size

    with p.open("rb") as fh:
        info.vpps = scan_vpps(fh)

    info.volume_id, info.boot_elf, info.system_cnf = _iso_metadata(p)

    versions = sorted({v.version for v in info.vpps})
    info.vpp_version = versions[0] if len(versions) == 1 else (versions[-1] if versions else 0)

    vol = info.volume_id.upper().replace("-", "")
    known = KNOWN_VOLUMES.get(info.volume_id.upper()) or KNOWN_VOLUMES.get(vol)

    # content fingerprint: Summoner 1's TABLES.VPP has exactly 527 entries
    looks_like_s1 = any(v.version == 1 and v.count == S1_TABLES_ENTRIES for v in info.vpps)

    if known:
        info.game, ver, supported = known
        info.supported = supported
        if not supported:
            info.reason = (
                f"{info.game} detected (volume {info.volume_id}). Its archives use VPP "
                f"version {ver}; this build only edits version 1. The v2 header layout is "
                f"documented but the reader is not written yet."
            )
        else:
            info.reason = "Supported."
        return info

    if looks_like_s1 or (1 in versions and 2 not in versions):
        info.game = "Summoner"
        info.supported = True
        info.reason = ("No known volume ID, but the archive layout matches Summoner 1 "
                       "(VPP v1, 527 table entries). Treating as supported.")
        return info

    if 2 in versions:
        info.game = "Summoner 2 (probable)"
        info.supported = False
        info.reason = ("Archives are VPP version 2, which this build cannot read yet. "
                       "That is the Summoner 2 format.")
        return info

    if not info.vpps:
        info.reason = ("No VPP archives found. This does not look like a Summoner disc, "
                       "or the image is compressed/trimmed.")
        return info

    info.game = "unknown"
    info.reason = f"Unrecognised archive layout (VPP versions {versions})."
    return info


def find_tables(infos: list[VppInfo]) -> VppInfo | None:
    """The archive holding the script blob: v1 with the 527-entry fingerprint."""
    for v in infos:
        if v.version == 1 and v.count == S1_TABLES_ENTRIES:
            return v
    return None
