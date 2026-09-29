#!/usr/bin/env python3
r"""Integration tests: dry-run, combined build, verify, and seed shape.

Feature: nto-live-randomizer-options

This is the durable, automated form of task 6.2 ("Dry-run and combined-build
integration tests on the Source ISO"). It drives the real engine (``src/cli.py``)
end to end via ``subprocess`` with an argument LIST — never a shell string — so the
JSON in ``--options`` survives intact on every platform (Windows PowerShell mangles
inline ``{"...":...}`` quoting; an argv list sidesteps that entirely).

The disc-dependent checks operate on the ~1.2 GB retail Summoner (USA) image. That
disc is not present in CI, so every test that needs it is guarded with
``@pytest.mark.skipif(not _ISO.exists())``: CI without the disc still passes (the
tests skip), and on a machine that has the disc they run for real and assert the
JSON reports. The ISO path contains spaces and is handled as a single argv element.

Steps mirrored here (from the design's Verification Approach):
  1. Dry-run of ``enemy_hp_set`` — non-zero edits, no size growth.
  2. Combined build (doors + chests + enemy_hp_set + ``--binary skip_intro``) —
     one ISO produced, door/chest/HP edits present, ``skip_intro`` applied:false
     with a BLOCKED reason.
  3. ``--verify --against`` — same byte length, changes confined to TABLES.VPP
     (``outside_tables == 0``).
  4. ``--seeds 5 --seed-length 8`` — five distinct ``NTO_LIVE_<8 uppercase-alnum>``.

Run from repo root:
    python -m pytest tests/test_integration_build.py -q
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLI = _REPO_ROOT / "src" / "cli.py"

# The retail Source ISO. Path contains spaces on purpose — treated as one argv item.
_ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

# All build/verify/dry-run steps need the real disc; skip cleanly when it is absent.
_needs_iso = pytest.mark.skipif(
    not _ISO.exists(), reason=f"Source ISO not present: {_ISO}"
)

# Where the combined build writes its one output ISO.
_OUT_DIR = _REPO_ROOT / "work" / "out"
_OUT_ISO = _OUT_DIR / "combined.iso"


def _run_cli(*args: str) -> dict:
    """Invoke ``python src/cli.py <args>`` and return the parsed JSON on stdout.

    Uses an argv LIST (shell=False) so ``--options '{"...": ...}'`` and the
    space-bearing ISO path pass through verbatim. Long disc operations are given a
    generous timeout; ``-q`` keeps engine progress off stderr.
    """
    proc = subprocess.run(
        [sys.executable, str(_CLI), *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    # cli emits exactly one JSON document on stdout; parse the last non-empty line.
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, (
        f"no JSON on stdout (exit {proc.returncode})\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr[-1000:]!r}"
    )
    payload = json.loads(lines[-1])
    payload["_returncode"] = proc.returncode
    return payload


def _report_for(result: dict, transform: str) -> dict | None:
    for rep in result.get("reports", []):
        if rep.get("transform") == transform:
            return rep
    return None


# --------------------------------------------------------------------------- #
# Step 4: seed shape (no disc needed — always runs)
# --------------------------------------------------------------------------- #
# Feature: nto-live-randomizer-options
#
# `--seeds 5 --seed-length 8` yields five distinct NTO_LIVE_<8 uppercase-alnum>.
#
# Validates: Requirements 7.1, 7.2
def test_seeds_shape_five_distinct_len8() -> None:
    payload = _run_cli("--seeds", "5", "--seed-length", "8")
    seeds = payload["seeds"]
    assert len(seeds) == 5, f"expected 5 seeds, got {len(seeds)}"
    pattern = re.compile(r"^NTO_LIVE_[A-Z0-9]{8}$")
    for seed in seeds:
        assert pattern.fullmatch(seed), f"seed {seed!r} not NTO_LIVE_<8 upper-alnum>"
        assert seed == seed.upper(), f"seed {seed!r} is not all uppercase"
    assert len(set(seeds)) == 5, f"seeds are not distinct: {seeds}"


# --------------------------------------------------------------------------- #
# Step 1: dry-run of enemy_hp_set (needs the disc)
# --------------------------------------------------------------------------- #
# Feature: nto-live-randomizer-options
#
# A dry-run with enemy_hp_set value=200 reports non-zero HP edits and no size
# growth (dry-run writes no ISO; size is unchanged by construction).
#
# Validates: Requirements 8.1, 8.3, 8.5
@_needs_iso
def test_dryrun_enemy_hp_set_reports_edits() -> None:
    result = _run_cli(
        "--build", str(_ISO),
        "--mode", "custom",
        "--include", "enemy_hp_set",
        "--options", '{"enemy_hp_set": {"value": 200}}',
        "--dry-run", "-q",
        "--report", "dryrun.json",
    )
    assert result["_returncode"] == 0, result
    rep = _report_for(result, "enemy_hp_set")
    assert rep is not None, f"enemy_hp_set missing from reports: {result.get('reports')}"
    assert rep.get("changed", 0) > 0, f"expected non-zero HP edits, got {rep}"
    # A dry-run produces no output image, so there is no size growth to speak of;
    # the transform is size-preserving by construction (see Property 1).


# --------------------------------------------------------------------------- #
# Steps 2 + 3: combined build then verify against source (needs the disc)
# --------------------------------------------------------------------------- #
# Feature: nto-live-randomizer-options
#
# One ISO built from doors + chests + enemy_hp_set + a blocked skip_intro:
#   - door/chest/HP transform edits are present,
#   - skip_intro is reported applied:false with a BLOCKED reason,
#   - the output has the same byte length as the source, and
#   - every changed byte is confined to TABLES.VPP (outside_tables == 0).
#
# Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 6.1, 6.2, 6.3
@_needs_iso
def test_combined_build_and_verify_against_source() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    if _OUT_ISO.exists():
        _OUT_ISO.unlink()

    build = _run_cli(
        "--build", str(_ISO),
        "--mode", "custom",
        "--include", "door_destination_remap",
        "--include", "chest_items",
        "--include", "enemy_hp_set",
        "--binary", "skip_intro",
        "--options", '{"enemy_hp_set": {"value": 50}}',
        "--seed", "NTO_LIVE_TEST01",
        "--out", str(_OUT_ISO),
        "-q",
        "--report", "build.json",
    )
    assert build["_returncode"] == 0, build

    # One ISO produced, same byte length as the source.
    assert _OUT_ISO.exists(), "combined.iso was not produced"
    assert _OUT_ISO.stat().st_size == _ISO.stat().st_size, (
        "output ISO size differs from source"
    )

    # Transform edits present (doors, chests, HP each changed at least one field).
    for name in ("door_destination_remap", "chest_items", "enemy_hp_set"):
        rep = _report_for(build, name)
        assert rep is not None, f"{name} missing from reports"
        assert rep.get("changed", 0) > 0, f"{name} made no edits: {rep}"

    # skip_intro reported applied:false with a BLOCKED reason.
    binary_rows = build.get("binary", [])
    skip_rows = [r for r in binary_rows if r.get("patch") == "skip_intro"]
    assert skip_rows, f"skip_intro missing from binary section: {binary_rows}"
    for row in skip_rows:
        assert row.get("applied") is False, f"skip_intro should be blocked: {row}"
        assert "BLOCKED" in " ".join(row.get("notes", [])), (
            f"skip_intro must carry a BLOCKED reason: {row}"
        )

    # Verify the built ISO against the source: same length, changes confined to
    # TABLES.VPP. skip_intro is blocked so nothing was written to the ELF, which
    # keeps the confinement check green.
    verify = _run_cli(
        "--verify", str(_OUT_ISO),
        "--against", str(_ISO),
        "-q",
        "--report", "verify.json",
    )
    checks = {c["check"]: c for c in verify.get("checks", [])}
    same_len = checks.get("same byte length as the source")
    assert same_len is not None and same_len["ok"], f"length check failed: {same_len}"
    confined = checks.get("changes confined to TABLES.VPP")
    assert confined is not None and confined["ok"], (
        f"changes escaped TABLES.VPP: {confined}"
    )
    assert verify.get("diff", {}).get("outside_tables", -1) == 0, (
        f"outside_tables must be 0: {verify.get('diff')}"
    )
