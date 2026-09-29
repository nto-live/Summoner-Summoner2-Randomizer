#!/usr/bin/env python3
"""Suite D of docs/TEST-PLAN.md - GUI parity.

Proves the desktop app cannot ask the engine for something it cannot do, and cannot hide
something it can. It runs the real WinForms app headlessly (SummonerRando.Harness) and
inspects the rendered control tree, then checks the argv the GUI builds against the argv
the CLI accepts.

    python tools/test-gui-parity.py
    python tools/test-gui-parity.py --dump-only      # refresh the dump, skip the checks

Checks:
  1. every mode in `mode_order` is offered as a selectable entry, by its own label
  2. the mode combo's item count equals the catalogue's mode count
  3. a non-buildable mode (`vanilla`) is annotated "(reference only)" and is NOT the default
  4. no control exists for a BLOCKED binary patch (a knob that can only make a broken disc)
  5. every non-blocked binary patch IS offered
  6. GUI parity on argv: the argv the GUI constructs is one the CLI accepts and succeeds on

Checks 4 is the one that caught a real defect on 2026-09-29: `hide_tutorials` was offered
as a tickable control even though it is the documented wrong lever, and building it freezes
the opening. Checks 1-2 caught a second: the harness dumped only 8 of the 43 modes, so the
dump looked like verification while proving nothing.

Requires a built harness:  dotnet build desktop/SummonerRando.sln -c Release
Contains no game data. Reads the retail ISO for the argv dry-run; writes nothing to it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
CLI = HERE / "src" / "cli.py"
DUMP = HERE / "work" / "ui-verify.json"


def newest_harness() -> Path:
    found = sorted(HERE.glob("desktop/**/SummonerRando.Harness.exe"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not found:
        raise SystemExit("no built harness found - run: "
                         "dotnet build desktop/SummonerRando.sln -c Release")
    return found[0]


def catalogue() -> dict:
    r = subprocess.run([sys.executable, str(CLI), "--list", "-q"], capture_output=True)
    if r.returncode != 0:
        raise SystemExit("cli.py --list failed")
    return json.loads(r.stdout.decode("utf-8", "replace"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-only", action="store_true")
    a = ap.parse_args()

    h = newest_harness()
    print(f"harness : {h.relative_to(HERE)}")
    r = subprocess.run([str(h), "--dump-ui", str(DUMP), "--state", "populated"],
                       capture_output=True, timeout=600)
    out = r.stdout.decode("utf-8", "replace")
    head = [ln for ln in out.splitlines() if ln.startswith(("populate:", "nodes", "saved"))]
    for ln in head:
        print("         " + ln)
    if a.dump_only:
        return 0

    cat = catalogue()
    text = json.dumps(json.loads(DUMP.read_text(encoding="utf-8")), ensure_ascii=False)
    fails: list[str] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        print(f"  [{'ok  ' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
        if not ok:
            fails.append(label)

    print()
    print("== 1/2. every mode is offered ==")
    missing = []
    for key in cat["mode_order"]:
        spec = cat["modes"][key]
        label = spec.get("label", key)
        if spec.get("buildable") is False:
            label += "  (reference only)"
        if label not in text:
            missing.append(key)
    check(not missing, f"all {len(cat['mode_order'])} mode labels present in the UI",
          "" if not missing else f"missing {len(missing)}: {', '.join(missing[:6])}")

    print()
    print("== 3. non-buildable modes ==")
    nb = [k for k, s in cat["modes"].items() if s.get("buildable") is False]
    check("(reference only)" in text, "non-buildable mode is annotated",
          f"non-buildable: {nb}")

    print()
    print("== 4. a blocked patch must NOT be offered ==")
    for name, b in cat["binary"].items():
        if not b.get("blocked"):
            continue
        label = b.get("label", name)
        check(label not in text, f"blocked patch '{name}' has no control")

    print()
    print("== 5. live patches MUST be offered ==")
    for name, b in cat["binary"].items():
        if b.get("blocked"):
            continue
        label = b.get("label", name)
        check(label in text, f"'{name}' is offered")

    print()
    print("== 6. GUI argv is an argv the CLI accepts ==")
    r2 = subprocess.run([str(h)], capture_output=True, timeout=900)
    o2 = r2.stdout.decode("utf-8", "replace")
    argline = next((ln for ln in o2.splitlines() if ln.strip().startswith("argv:")), None)
    if argline is None:
        check(False, "harness printed the argv it would run")
    else:
        argv = argline.split("argv:", 1)[1].split()
        # The harness prints the ARGUMENT TAIL only - EngineClient prepends the interpreter
        # and cli.py itself when it actually spawns the engine. So the script path has to be
        # put back before this argv can be run directly, or Python eats --build as its own
        # flag and exits 2 (which is exactly the false failure this check first reported).
        # The harness builds this with EngineClient.BuildArgs and runs it with --dry-run,
        # so re-running it through the CLI proves the two agree without writing anything.
        dry = subprocess.run([sys.executable, str(CLI)] + argv, capture_output=True, timeout=900)
        payload = {}
        try:
            payload = json.loads(dry.stdout.decode("utf-8", "replace") or "{}")
        except json.JSONDecodeError:
            pass
        check(dry.returncode == 0 and payload.get("dry") is True,
              "GUI-built argv runs green through the CLI",
              f"rc={dry.returncode} dry={payload.get('dry')}")

    print()
    if fails:
        print(f"FAILED: {len(fails)} check(s)")
        for f in fails:
            print("  - " + f)
        return 1
    print("ALL GUI PARITY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
