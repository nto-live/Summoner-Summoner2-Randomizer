#!/usr/bin/env python3
"""End-to-end build matrix: can a user actually get a working disc, for every mode?

This is suite C of docs/TEST-PLAN.md. Until now the desktop harness proved the
*plumbing* (argv construction, `--list` parsing, a `--dry-run` that writes nothing)
but nothing ever built a real disc and checked the artefact. This walks the mode
list, builds each one for real, and asserts on what lands on disk.

    python tools/test-build-matrix.py                  # every mode
    python tools/test-build-matrix.py --quick          # a representative handful
    python tools/test-build-matrix.py --modes doors,chaos,progression
    python tools/test-build-matrix.py --with-options   # + one non-default option per mode
    python tools/test-build-matrix.py --keep           # keep the .iso outputs

For each row:

  1. exit code 0
  2. the output exists and is non-empty
  3. **output size == source size, byte for byte** - size preservation is the
     project's non-negotiable rule, so a row that breaks it is a P0
  4. the engine's own report agrees (`size_preserved` true)
  5. a mode that lists transforms reports **>= 1 edit** - a "chaos" mode that silently
     changes nothing is a bug, not a pass
  6. **every transform the mode lists appears in the report** - this is the check that
     catches a mode whose blurb promises ten levers and whose argv delivers three
  7. the output still identifies as a supported Summoner disc
  8. **every binary patch the mode names reports `applied` with every declared word read
     back and matching** - a mode whose only lever is an executable patch reports
     `edits: 0` from the text layer, so without this it would pass while proving nothing

By default the built .iso is deleted after each row, so only the small JSON reports
travel: a full run would otherwise write ~1.2 GB x 39. That also makes this the right
job to hand to a spare box - the reports come home, the discs do not.

Contains no game data. Reads the retail ISO; never copies it anywhere.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CLI = HERE / "src" / "cli.py"
DEFAULT_ISO = Path(r"F:\rando\S1\iso\Summoner.iso")
DEFAULT_OUTDIR = Path(r"F:\rando\S1\out")

# A representative spread: one no-op, one cosmetic, one structural, one progression,
# one stacked. Enough to catch a broken argv builder without waiting an hour.
QUICK = ["vanilla", "chaos", "doors", "progression", "chest_shuffle", "stat_chaos"]


def run(cmd: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def catalogue() -> dict:
    rc, out, err = run([sys.executable, str(CLI), "--list", "-q"], timeout=300)
    if rc != 0:
        raise SystemExit(f"cli.py --list failed (rc={rc}):\n{err}")
    return json.loads(out)


def identify(path: Path) -> dict | None:
    rc, out, err = run([sys.executable, str(CLI), "--identify", str(path), "-q"], timeout=300)
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def build(iso: Path, mode: str, seed: str, out: Path, report: Path,
          options: dict | None) -> tuple[int, dict | None, str]:
    cmd = [sys.executable, str(CLI), "--build", str(iso), "--mode", mode,
           "--seed", seed, "--out", str(out), "--report", str(report), "-q"]
    if options:
        cmd += ["--options", json.dumps(options)]
    rc, _out, err = run(cmd)
    rep = None
    if report.exists():
        try:
            rep = json.loads(report.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rep = None
    return rc, rep, err


def non_default_options(cat: dict, mode: str) -> dict:
    """One non-default value per option-bearing transform in this mode."""
    spec = cat["modes"][mode]
    schema = cat.get("options", {})
    out: dict[str, dict] = {}
    for t in spec.get("transforms", []):
        for key, d in (schema.get(t) or {}).items():
            if d.get("type") == "int":
                lo, hi = d.get("min", 1), d.get("max", 100)
                out.setdefault(t, {})[key] = hi if d.get("default") != hi else lo
            elif d.get("type") == "choice":
                ch = [c for c in d.get("choices", []) if c not in (None, d.get("default"))]
                if ch:
                    out.setdefault(t, {})[key] = ch[0]
            elif d.get("type") == "bool":
                out.setdefault(t, {})[key] = not d.get("default", True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", type=Path, default=DEFAULT_ISO)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    ap.add_argument("--modes", type=str, default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--with-options", action="store_true",
                    help="additionally run a variant of each mode with non-default options")
    ap.add_argument("--keep", action="store_true", help="keep the built .iso files")
    ap.add_argument("--report", type=Path, default=None)
    a = ap.parse_args()

    if not a.iso.exists():
        raise SystemExit(f"source ISO not found: {a.iso}")
    cat = catalogue()
    src_size = a.iso.stat().st_size

    if a.modes:
        modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    elif a.quick:
        modes = QUICK
    else:
        modes = list(cat["mode_order"])
    unknown = [m for m in modes if m not in cat["modes"]]
    if unknown:
        raise SystemExit(f"unknown mode(s): {unknown}")

    a.outdir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    width = max(len(m) for m in modes)

    print(f"source : {a.iso}")
    print(f"        {src_size:,} bytes")
    print(f"modes  : {len(modes)}" + ("  (+ option variants)" if a.with_options else ""))
    print()

    for mode in modes:
        variants: list[tuple[str, dict | None]] = [(mode, None)]
        if a.with_options:
            opts = non_default_options(cat, mode)
            if opts:
                variants.append((mode + " (non-default options)", opts))

        for label, opts in variants:
            seed = "MATRIX-" + mode.upper().replace("_", "-")
            out = a.outdir / f"_matrix-{mode}{'-opts' if opts else ''}.iso"
            rep_path = a.outdir / f"_matrix-{mode}{'-opts' if opts else ''}.json"
            for p in (out, rep_path):
                if p.exists():
                    p.unlink()

            want = set(cat["modes"][mode].get("transforms", []))
            binp = cat["modes"][mode].get("binary", [])
            # A mode that selects nothing (the `vanilla` baseline) deliberately refuses to
            # write: there is nothing to change, so a disc would be a pure copy. That is
            # expected behaviour, not a failed row - recorded as such, so the decision is
            # visible instead of silently skipped.
            expect_refusal = not want and not binp

            t0 = time.time()
            rc, rep, err = build(a.iso, mode, seed, out, rep_path, opts)
            secs = time.time() - t0

            if expect_refusal:
                refused = rc != 0 and not out.exists()
                detail = [] if refused else [f"expected a clean refusal, got rc={rc}"]
                rows.append({"mode": mode, "variant": label, "seed": seed,
                             "seconds": round(secs, 1), "edits": 0, "out_bytes": 0,
                             "expect_refusal": True,
                             "checks": {"refuses_cleanly": refused},
                             "detail": detail, "report": None})
                print(f"[{'PASS' if refused else 'FAIL'}] {label:<{width+24}} {secs:6.1f}s  "
                      "(baseline: selects nothing, refuses by design)")
                if not a.keep and out.exists():
                    out.unlink()
                continue

            checks: dict[str, bool] = {}
            detail: list[str] = []

            checks["exit0"] = rc == 0
            if rc != 0:
                detail.append(f"rc={rc} {err.strip().splitlines()[-1:] or ''}")

            exists = out.exists() and out.stat().st_size > 0
            checks["output_written"] = exists
            out_size = out.stat().st_size if out.exists() else 0

            checks["size_preserved"] = exists and out_size == src_size
            if exists and out_size != src_size:
                detail.append(f"size {out_size:,} != {src_size:,}")

            checks["report_says_preserved"] = bool(rep and rep.get("size_preserved"))
            if rep is None:
                detail.append("no report JSON")

            got = {r["transform"] for r in (rep or {}).get("reports", [])}
            edits = (rep or {}).get("edits", 0)

            # 5: a mode that lists transforms must actually change something.
            checks["edits_if_levers"] = (not want) or edits > 0
            if want and edits == 0:
                detail.append("mode lists transforms but reported 0 edits")

            # 6: every listed transform must be accounted for.
            missing = sorted(want - got)
            checks["all_transforms_reported"] = not missing
            if missing:
                detail.append("silent no-op transform(s): " + ", ".join(missing))

            # 7: the container survived.
            idp = identify(out) if exists else None
            checks["still_identifies"] = bool(idp and idp.get("supported"))
            if exists and not checks["still_identifies"]:
                detail.append("output no longer identifies as supported")

            # 8: every binary patch the mode names must report applied, with every
            # declared word read back and matching. Modes whose only lever is a binary
            # patch (endgame_gate, skip_intro) report `edits: 0` from the TEXT layer, so
            # without this check the matrix would pass them while proving nothing at all
            # about the thing they actually do.
            if binp:
                bin_got = {b.get("patch"): b for b in (rep or {}).get("binary", [])}
                bad: list[str] = []
                for name, _params in ((b[0], b[1] if len(b) > 1 else {}) for b in binp):
                    entry = bin_got.get(name)
                    if not entry or not entry.get("applied"):
                        bad.append(name + " (not applied)")
                    elif any(not w.get("ok") for w in entry.get("words", [])):
                        bad.append(name + " (word read-back failed)")
                checks["binary_applied"] = not bad
                if bad:
                    detail.append("binary patch unverified: " + ", ".join(bad))

            ok = all(checks.values())
            rows.append({"mode": mode, "variant": label, "seed": seed,
                         "seconds": round(secs, 1), "edits": edits,
                         "out_bytes": out_size, "checks": checks,
                         "detail": detail, "report": str(rep_path) if rep_path.exists() else None})

            flag = "PASS" if ok else "FAIL"
            fails = ", ".join(k for k, v in checks.items() if not v)
            print(f"[{flag}] {label:<{width+24}} {secs:6.1f}s  edits={edits:<6} "
                  + ("" if ok else "failed: " + fails))

            if not a.keep and out.exists():
                out.unlink()

    passed = sum(1 for r in rows if all(r["checks"].values()))
    print()
    print(f"{passed}/{len(rows)} rows passed")

    # Which checks fail, aggregated - the useful summary when something breaks.
    broken: dict[str, list[str]] = {}
    for r in rows:
        for k, v in r["checks"].items():
            if not v:
                broken.setdefault(k, []).append(r["variant"])
    if broken:
        print()
        for k, who in sorted(broken.items()):
            print(f"  {k}: {len(who)} row(s) - {', '.join(who[:6])}{'...' if len(who) > 6 else ''}")

    if a.report:
        a.report.write_text(json.dumps({"source": str(a.iso), "src_bytes": src_size,
                                        "rows": rows}, indent=2), encoding="utf-8")
        print(f"\nwrote {a.report}")

    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
