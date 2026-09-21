#!/usr/bin/env python3
r"""Summoner Randomizer — engine with a JSON interface.

The desktop app drives this. No HTTP, no server: a front end runs this script,
reads progress from stderr and the final result from stdout as JSON.

    python cli.py --list
    python cli.py --identify "D:\Summoner.iso"
    python cli.py --build "D:\Summoner.iso" --mode roguelike --seed ABC123 \
                  --out "D:\out.iso"
    python cli.py --build ... --dry-run
    python cli.py --build ... --exclude shop_shuffle --include permadeath
    python cli.py --build ... --options '{"xp_scale":{"percent":250}}'
    python cli.py --build ... --seed-list 10      # print 10 candidate seeds as JSON

Exit codes: 0 ok, 2 refused (disc not supported), 1 error.
Progress lines on stderr look like:  #progress <message>

Testing surface (engine-side, no GUI needed):

    python cli.py --verify "D:\out.iso"                    # is this a valid, playable image?
    python cli.py --verify "D:\out.iso" --against "D:\src.iso"
                                                        # + every changed byte inside TABLES.VPP
    python cli.py --build ... --report out.json --log run.log
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import string
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

import discover          # noqa: E402
import rando_core as rc  # noqa: E402

try:
    import binary as _binary
except ImportError:
    _binary = None


_LOG = None
_REPORT = None
_VERBOSE = 0          # 0 quiet-ish (default), 1 -v, 2 -vv, 3 -vvv (per-field detail)
_T0 = time.time()


def _stamp() -> str:
    return f"[{time.time() - _T0:9.3f}s]"


def _emit_log(line: str) -> None:
    if _LOG is None:
        return
    try:
        _LOG.write(line + "\n")
        _LOG.flush()
    except Exception:  # noqa: BLE001
        pass


def _progress(msg: str) -> None:
    """A progress line. Timestamped once verbose - the GUI strips the marker either way."""
    prefix = f"{_stamp()} " if _VERBOSE else ""
    print(f"#progress {prefix}{msg}", file=sys.stderr, flush=True)
    _emit_log(f"#progress {prefix}{msg}")


def _dbg(msg: str, level: int = 2) -> None:
    """Extra detail for developers. -vv or higher; never reaches stdout."""
    if _VERBOSE >= level:
        line = f"#progress {_stamp()}   {msg}"
        print(line, file=sys.stderr, flush=True)
        _emit_log(line)


def _header(argv) -> None:
    """Everything a bug report needs, first line of the log."""
    import rando_core
    facts = [
        f"engine: summoner randomizer cli",
        f"argv: {' '.join(argv)}",
        f"cwd: {Path.cwd()}",
        f"python: {sys.version.split()[0]} ({platform.python_implementation()})",
        f"platform: {platform.platform()}",
        f"transforms: {len(rando_core.TRANSFORMS)}  modes: {len(rando_core.MODES)}",
        f"verbose: {_VERBOSE}",
    ]
    for f in facts:
        _emit_log(f"# {f}")
        if _VERBOSE:
            print(f"#progress {_stamp()} {f}", file=sys.stderr, flush=True)


def _open_log(path: str | None, argv=None) -> None:
    """--log writes everything the engine says to a file, for test runs and bug reports."""
    global _LOG
    if not path:
        return
    _LOG = open(path, "w", encoding="utf-8")
    _LOG.write("# Summoner Randomizer engine log\n")
    _header(argv or [])


def _emit(obj) -> None:
    """One JSON document on stdout - the GUI parses this. --report also mirrors it to a file."""
    print(json.dumps(obj, indent=None), flush=True)
    if _VERBOSE:
        _dbg(f"result keys: {sorted(obj)[:12]}", level=2)
    _emit_log(f"# result {json.dumps(obj)}")
    if _REPORT is not None:
        try:
            with open(_REPORT, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2)
        except Exception as e:  # noqa: BLE001
            print(f"#progress could not write report: {e}", file=sys.stderr, flush=True)
            _emit_log(f"# could not write report: {e}")


def cmd_list() -> int:
    _emit({
        "modes": rc.MODES,
        "mode_order": list(rc.MODES.keys()),
        "transforms": sorted(rc.TRANSFORMS),
        "info": rc.TRANSFORM_INFO,
        "options": rc.OPTIONS,
        "option_aware": sorted(rc.OPTION_AWARE),
        "pending": rc.PENDING,
        "binary": (_binary.describe() if _binary else {}),
    })
    return 0


def cmd_identify(iso: str) -> int:
    info = discover.identify(iso)
    d = info.as_dict()
    d["tables"] = None
    t = discover.find_tables(info.vpps)
    if t:
        d["tables"] = {"offset": f"0x{t.base:X}", "entries": t.count}
    _emit(d)
    return 0 if d["supported"] else 2


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def _diff_against(iso: Path, src: Path, region: tuple[int, int] | None, chunk: int = 8 << 20):
    """Byte-compare two images in a stream; report the damage the way a test wants it.

    `region` is the (offset, length) we are *allowed* to have touched. Anything changed outside
    it is a bug, so it is counted separately.
    """
    lo, hi = (region if region else (0, 0))
    differ = outside = 0
    first = last = -1
    with open(iso, "rb") as fa, open(src, "rb") as fb:
        pos = 0
        while True:
            a = fa.read(chunk)
            b = fb.read(chunk)
            if not a and not b:
                break
            if len(a) != len(b):
                return {"error": "length mismatch", "a": len(a), "b": len(b), "offset": pos}
            for i in range(len(a)):
                if a[i] != b[i]:
                    differ += 1
                    off = pos + i
                    if first < 0:
                        first = off
                    last = off
                    if not (lo <= off < lo + hi):
                        outside += 1
            pos += len(a)
    return {"bytes_differ": differ, "first_offset": first, "last_offset": last,
            "outside_tables": outside, "region": {"offset": lo, "bytes": hi}}


def cmd_verify(iso_path: str, against: str | None = None) -> int:
    """Engine-side self-check of a disc image - the testing verb, no GUI and no emulator.

    On its own: is this a valid, playable image? With --against <source>: prove the discipline
    the randomizer holds to - same byte length, and every changed byte inside TABLES.VPP,
    nothing outside it.
    """
    p = Path(iso_path)
    if not p.is_file():
        _emit({"error": f"disc not found: {p}"})
        return 1
    info = discover.identify(iso_path)
    tables = discover.find_tables(info.vpps)
    result = {
        "path": str(p),
        "bytes": info.bytes,
        "sha256": _sha256(p),
        "volume_id": info.volume_id,
        "boot_elf": info.boot_elf,
        "game": info.game,
        "supported": info.supported,
        "archives": len(info.vpps),
        "vpp_version": info.vpp_version,
        "tables": ({"offset": f"0x{tables.base:X}", "bytes": tables.total_size,
                    "entries": tables.count} if tables else None),
        "checks": [],
    }

    def check(name: str, ok: bool, detail: str = "") -> None:
        result["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        _progress(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" - {detail}" if detail else ""))

    first_line = (info.system_cnf.splitlines() or [""])[0] if info.system_cnf else ""
    check("SYSTEM.CNF names a boot elf", "BOOT2" in info.system_cnf, first_line)
    check("boot elf is present in the image", bool(info.boot_elf), info.boot_elf)
    check("disc is a supported Summoner image", info.supported, info.reason)
    check("script archive found", tables is not None,
          f"0x{tables.base:X}, {tables.count} entries" if tables else "no TABLES.VPP")
    check("every archive lies inside the image",
          all(v.base + v.total_size <= info.bytes for v in info.vpps),
          f"{len(info.vpps)} archives")

    if against:
        src = Path(against)
        if not src.is_file():
            _emit({"error": f"source disc not found: {src}"})
            return 1
        check("same byte length as the source", src.stat().st_size == info.bytes,
              f"{info.bytes} bytes")
        region = (tables.base, tables.total_size) if tables else None
        d = _diff_against(p, src, region)
        if "error" in d:
            check("compare against the source", False, str(d))
        else:
            check("changes confined to TABLES.VPP", d["outside_tables"] == 0,
                  f"{d['bytes_differ']} bytes differ, {d['outside_tables']} outside the archive")
            result["diff"] = d

    result["ok"] = all(c["ok"] for c in result["checks"])
    _emit(result)
    return 0 if result["ok"] else 2


def cmd_seeds(n: int, length: int = 6) -> int:
    alpha = string.ascii_uppercase + string.digits
    rng = random.SystemRandom()
    _emit({"seeds": ["".join(rng.choice(alpha) for _ in range(length))
                     for _ in range(max(1, n))]})
    return 0


def _resolve(mode: str, transforms, include, exclude):
    tf = list(rc.MODES[mode]["transforms"]) if mode in rc.MODES else list(transforms or [])
    for t in list(exclude or []):
        if t in tf:
            tf.remove(t)
    for t in list(include or []):
        if t not in tf:
            tf.append(t)
    binary = rc.MODES.get(mode, {}).get("binary") or []
    return tf, binary


def cmd_build(a) -> int:
    iso = Path(a.build)
    if not iso.is_file():
        _emit({"error": f"disc not found: {iso}"})
        return 1

    info = discover.identify(a.build)
    if not info.supported:
        _emit({"error": info.reason, "game": info.game, "supported": False})
        return 2

    tf, binary_spec = _resolve(a.mode, a.transforms, a.include, a.exclude)
    options = json.loads(a.options) if a.options else {}
    if a.exclude_permadeath:
        tf = [t for t in tf if t != "permadeath"]

    if not tf and not binary_spec:
        _emit({"error": "nothing selected to randomize"})
        return 1

    out = Path(a.out) if a.out else (APP / "work" / "out" /
                                     f"{iso.stem}-{a.mode or 'custom'}-{a.seed}.iso")

    if a.dry_run:
        res = rc.dry_run_iso(iso, a.seed, tf, progress=_progress,
                             options=options, binary_patches=binary_spec)
        res["mode"] = a.mode
        res["engine"] = "dry-run"
        _emit(res)
        return 0

    res = rc.randomize_iso(iso, out, a.seed, tf, progress=_progress,
                           options=options, binary_patches=binary_spec)
    res["mode"] = a.mode
    res["name"] = out.name
    res["edits"] = sum(r.get("changed", 0) for r in res["reports"])
    res["engine"] = "build"
    _emit(res)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Summoner Randomizer engine")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--identify")
    ap.add_argument("--seeds", type=int, help="generate N random seeds")
    ap.add_argument("--seed-length", type=int, default=6)
    ap.add_argument("--build")
    ap.add_argument("--mode", default="custom")
    ap.add_argument("--seed", default="SUMMONER")
    ap.add_argument("--out")
    ap.add_argument("--transforms", help="comma separated")
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--exclude-permadeath", action="store_true")
    ap.add_argument("--options", help="JSON object")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", help="check a built (or any) disc image")
    ap.add_argument("--against", help="with --verify: the source disc to compare against")
    ap.add_argument("--log", help="write everything the engine says to this file")
    ap.add_argument("--report", help="write the final JSON result to this file")
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="more output: -v stages, -vv detail, -vvv per-field")
    a = ap.parse_args()

    global _REPORT, _VERBOSE
    _REPORT = a.report
    _VERBOSE = min(3, max(0, a.verbose or 0))
    _open_log(a.log, sys.argv)

    if isinstance(a.transforms, str):
        a.transforms = [t.strip() for t in a.transforms.split(",") if t.strip()]

    if a.list:
        code = cmd_list()
    elif a.identify:
        code = cmd_identify(a.identify)
    elif a.seeds:
        code = cmd_seeds(a.seeds, a.seed_length)
    elif a.verify:
        code = cmd_verify(a.verify, a.against)
    elif a.build:
        code = cmd_build(a)
    else:
        ap.print_help()
        code = 1

    if _LOG is not None:
        _LOG.write(f"# exit {code}\n")
        _LOG.close()
    return code
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
