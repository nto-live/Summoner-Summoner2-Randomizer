"""Property tests for NTO_LIVE_ seed generation (src/cli.py cmd_seeds).

Feature: nto-live-randomizer-options

Run from repo root:
    python -m pytest tests/test_seed_property.py -q
"""
from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Import the engine CLI from src/ (same seam the engine uses: src on sys.path).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import cli  # noqa: E402


def _generate_seeds(n: int, length: int) -> list[str]:
    """Drive cmd_seeds and pull the seed list out of the JSON it prints on stdout.

    cmd_seeds calls _emit, which prints one JSON document to stdout. We capture that
    document and return the "seeds" array — no coupling to internal helpers beyond
    the public command entry point and its documented output shape.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.cmd_seeds(n, length)
    assert rc == 0
    payload = json.loads(buf.getvalue().strip())
    return payload["seeds"]


# Feature: nto-live-randomizer-options, Property 3: Seed format and casing
#
# For any generation count n >= 1 and any suffix length L >= 1, every seed produced
# by cmd_seeds matches ^NTO_LIVE_[A-Z0-9]{L}$ and equals its own uppercase.
#
# Validates: Requirements 7.1, 7.3
@settings(max_examples=150)
@given(
    n=st.integers(min_value=1, max_value=25),
    length=st.integers(min_value=1, max_value=32),
)
def test_property3_seed_format_and_casing(n: int, length: int) -> None:
    pattern = re.compile(r"^NTO_LIVE_[A-Z0-9]{" + str(length) + r"}$")
    seeds = _generate_seeds(n, length)

    assert len(seeds) == n
    for seed in seeds:
        assert pattern.fullmatch(seed), (
            f"seed {seed!r} does not match ^NTO_LIVE_[A-Z0-9]{{{length}}}$"
        )
        assert seed == seed.upper(), f"seed {seed!r} is not all uppercase"
