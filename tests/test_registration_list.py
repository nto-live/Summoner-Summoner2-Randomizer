"""Example test: the `cli.py --list` JSON exposes the new registration and blocked patch.

Feature: nto-live-randomizer-options

Drives cli.cmd_list() and captures the JSON document it emits on stdout (the same
seam the seed tests use), then asserts the enemy_hp_set registration and the
skip_intro blocked binary patch are visible in the catalogue the UI consumes.

Run from repo root:
    python -m pytest tests/test_registration_list.py -q
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Import the engine CLI from src/ (same seam the engine uses: src on sys.path).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import cli  # noqa: E402


def _list_payload() -> dict:
    """Drive cmd_list and pull the single JSON document it prints on stdout.

    cmd_list calls _emit, which prints one JSON document to stdout. We capture that
    document and return it — no coupling to internals beyond the public command
    entry point and its documented output shape.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_list()
    assert rc == 0
    return json.loads(buf.getvalue().strip())


# Feature: nto-live-randomizer-options
#
# The --list catalogue the UI reads must expose the enemy_hp_set registration
# (transform, info label/description, and its "value" option contract) and must
# surface the skip_intro binary patch as blocked with a human-readable reason.
#
# Validates: Requirements 1.1, 1.2, 6.2
def test_list_exposes_enemy_hp_set_and_blocked_skip_intro() -> None:
    payload = _list_payload()

    # 1.1 — enemy_hp_set is a registered transform.
    assert "enemy_hp_set" in payload["transforms"], (
        "enemy_hp_set missing from transforms list"
    )

    # 1.1 — info entry present, carrying a label + description.
    info = payload["info"]
    assert "enemy_hp_set" in info, "enemy_hp_set missing from info"
    hp_info = info["enemy_hp_set"]
    # info entries are (label, description) pairs; both must be non-empty.
    assert len(hp_info) >= 2, f"enemy_hp_set info malformed: {hp_info!r}"
    label, description = hp_info[0], hp_info[1]
    assert isinstance(label, str) and label.strip(), "enemy_hp_set label missing"
    assert isinstance(description, str) and description.strip(), (
        "enemy_hp_set description missing"
    )

    # 1.2 — the option contract for the enemy HP value.
    options = payload["options"]
    assert "enemy_hp_set" in options, "enemy_hp_set missing from options"
    value = options["enemy_hp_set"]["value"]
    assert value["type"] == "int", f"expected int, got {value.get('type')!r}"
    assert value["default"] == 1, f"expected default 1, got {value.get('default')!r}"
    assert value["min"] == 1, f"expected min 1, got {value.get('min')!r}"
    assert value["max"] == 999, f"expected max 999, got {value.get('max')!r}"

    # 1.2 — enemy_hp_set is option-aware (receives keyword options).
    assert "enemy_hp_set" in payload["option_aware"], (
        "enemy_hp_set missing from option_aware"
    )

    # 6.2 — the binary catalogue lists skip_intro, and it is blocked with a reason.
    binary = payload["binary"]
    assert "skip_intro" in binary, "skip_intro missing from binary catalogue"
    skip_intro = binary["skip_intro"]
    assert "blocked" in skip_intro, "skip_intro is not marked blocked"
    reason = skip_intro["blocked"]
    assert isinstance(reason, str) and reason.strip(), (
        "skip_intro blocked reason is empty"
    )
