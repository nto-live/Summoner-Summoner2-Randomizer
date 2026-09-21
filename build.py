#!/usr/bin/env python3
r"""Summoner Randomizer — command-line builder.

Same pipeline as the app, no browser. Everything is relative to this folder.

    python build.py --list
    python build.py --disc "D:\summoner.iso" --mode one_hour --seed ABC123
    python build.py --disc "D:\summoner.iso" --mode doors --dry-run
    python build.py --disc "D:\summoner.iso" --matrix --seed SEED1
    python build.py --disc "D:\summoner.iso" --transforms lock_shuffle,xp_boost --seed X

    python build.py --identify "D:\summoner.iso"     # what is this disc?
    python build.py --discs                         # discs the app knows about

Outputs land in work/out/. Nothing is ever uploaded or shared.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

import discover          # noqa: E402
import rando_core as rc  # noqa: E402

OUT_DIR = APP / "work" / "out"


def cmd_list() -> int:
    print("MODES")
    for k, v in rc.MODES.items():
        print(f"  {k:<12} {v['label']:<14} risk={v['risk']}")
        print(f"               {v['blurb']}")
    print("\nTRANSFORMS")
    for k, (label, desc) in rc.TRANSFORM_INFO.items():
        print(f"  {k:<22} {label}")
    print("\nBLOCKED")
    for k, v in rc.PENDING.items():
        print(f"  {k:<24} needs: {v['blocked_by']}")
    return 0


def cmd_identify(path: str) -> int:
    info = discover.identify(path)
    d = info.as_dict()
    print(f"disc        : {d['path']}")
    print(f"bytes       : {d['bytes']:,}")
    print(f"volume id   : {d['volume_id'] or '(blank)'}")
    print(f"boot elf    : {d['boot_elf'] or '(unknown)'}")
    print(f"archives    : {d['vpp_count']}  versions {d['vpp_versions']}")
    print(f"game        : {d['game']}")
    print(f"supported   : {d['supported']}")
    print(f"reason      : {d['reason']}")
    t = discover.find_tables(info.vpps)
    print(f"tables      : {'0x%X (%d entries)' % (t.base, t.count) if t else 'not found'}")
    return 0 if d["supported"] else 2


def cmd_discs() -> int:
    import app as appmod  # reuses the app's config/cache
    rows = appmod.list_isos()
    if not rows:
        print("no discs known. add one with --disc, or drop it into work/in/")
        return 1
    for d in rows:
        mark = "OK " if d["supported"] else "NO "
        print(f"  [{mark}] {d['game']:<12} VPP v{','.join(map(str, d['vpp_versions'])) or '-':<4} "
              f"{d['bytes']:>13,}  {d['path']}")
    return 0


def cmd_dry(disc: str, seed: str, transforms: list[str]) -> int:
    res = rc.dry_run_iso(Path(disc), seed, transforms, progress=lambda m: print(f"  {m}"))
    print()
    for r in res["reports"]:
        print(f"  {r['transform']:<22} {r.get('changed',0):>6} edits  "
              f"{r.get('impact_bytes',0):>8} bytes")
    print(f"\n  total edits      : {res['edit_total']:,}")
    print(f"  blob bytes changed: {res['changed_bytes_total']:,} of {res['blob_bytes']:,}")
    print("  nothing was written")
    return 0


def cmd_build(disc: str, seed: str, mode: str | None, transforms: list[str],
              out: str | None) -> dict:
    src = Path(disc)
    if mode:
        if mode not in rc.MODES:
            raise SystemExit(f"unknown mode '{mode}' — try --list")
        transforms = list(rc.MODES[mode]["transforms"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = src.stem.replace(" ", "")
    tag = mode or "custom"
    dst = OUT_DIR / (out or f"{stem}-{tag}-{seed}.iso")

    print(f"disc  : {src}")
    print(f"seed  : {seed}")
    print(f"mode  : {tag}")
    print(f"edits : {', '.join(transforms) or '(none)'}")
    print(f"out   : {dst}\n")
    t0 = time.time()
    res = rc.randomize_iso(src, dst, seed, transforms, progress=lambda m: print(f"  {m}"))
    edits = sum(r.get("changed", 0) for r in res["reports"])
    print(f"\n  {time.time()-t0:.1f}s · {edits:,} edits · size preserved={res['size_preserved']}")
    print(f"  sha256 {res['dst_sha256']}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--discs", action="store_true")
    ap.add_argument("--identify")
    ap.add_argument("--disc", help="path to your ISO")
    ap.add_argument("--mode")
    ap.add_argument("--transforms", help="comma separated, overrides --mode")
    ap.add_argument("--seed", default="SEED1")
    ap.add_argument("--out")
    ap.add_argument("--matrix", action="store_true")
    ap.add_argument("--modes", help="comma separated subset for --matrix")
    ap.add_argument("--include", help="comma separated transforms to force ON")
    ap.add_argument("--exclude", help="comma separated transforms to force OFF")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.list:
        return cmd_list()
    if a.discs:
        return cmd_discs()
    if a.identify:
        return cmd_identify(a.identify)
    if not a.disc:
        ap.print_help()
        return 1

    info = discover.identify(a.disc)
    if not info.supported:
        print(f"cannot edit this disc — {info.reason}", file=sys.stderr)
        return 2

    tf = [t.strip() for t in a.transforms.split(",") if t.strip()] if a.transforms else []
    if a.mode:
        tf = list(rc.MODES[a.mode]["transforms"])
    inc = [t.strip() for t in (a.include or "").split(",") if t.strip()]
    exc = [t.strip() for t in (a.exclude or "").split(",") if t.strip()]
    for t in inc + exc:
        if t not in rc.TRANSFORMS:
            raise SystemExit(f"unknown transform '{t}' — try --list")
    tf = [t for t in tf if t not in exc]
    for t in inc:
        if t not in tf:
            tf.append(t)

    if a.dry_run:
        if not tf:
            tf = list(rc.MODES[a.mode or "one_hour"]["transforms"])
        return cmd_dry(a.disc, a.seed, tf)
    if a.matrix:
        modes = ([m.strip() for m in a.modes.split(",")] if a.modes
                 else [m for m in rc.MODES if m != "vanilla"])
        print(f"matrix: {len(modes)} modes, seed {a.seed}\n" + "-"*58)
        for m in modes:
            cmd_build(a.disc, a.seed, m, [], None)
            print("-"*58)
        return 0
    if not a.mode and not tf:
        print("need --mode or --transforms (or --dry-run/--matrix)", file=sys.stderr)
        return 1
    if a.mode:
        print(f"mode    : {a.mode} (+{inc or '-'} / -{exc or '-'})")
    cmd_build(a.disc, a.seed, None, tf, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
