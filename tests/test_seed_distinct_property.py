"""Property test — Feature: nto-live-randomizer-options, Property 4.

Validates: Requirements 7.2

Property 4: Seeds are distinct per generation.
For any batch of N seeds generated in one `cmd_seeds` call with a suffix length
of at least 6, all N seeds are distinct.

The generation seam is `cmd_seeds` in `src/cli.py`, which emits a single JSON
document ``{"seeds": [...]}`` on stdout via `_emit`. The test captures that
stdout with an `io.StringIO` redirect (a per-example context manager, so it is
reset for every generated input) and parses the ``seeds`` list.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Make `src/` importable so we can drive `cmd_seeds` directly.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import cli  # noqa: E402


def _generate_seeds(n: int, suffix_length: int) -> list[str]:
    """Run cmd_seeds and parse the emitted JSON ``seeds`` list from stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.cmd_seeds(n, suffix_length)
    assert rc == 0
    payload = json.loads(buf.getvalue())
    return payload["seeds"]


@settings(max_examples=150)
@given(
    n=st.integers(min_value=1, max_value=50),
    suffix_length=st.integers(min_value=6, max_value=24),
)
def test_seeds_are_distinct_per_generation(n, suffix_length):
    """Feature: nto-live-randomizer-options, Property 4: Seeds are distinct per generation"""
    seeds = _generate_seeds(n, suffix_length)

    # cmd_seeds must emit exactly the requested count.
    assert len(seeds) == n

    # The core property: every seed in one batch is distinct.
    assert len(set(seeds)) == n
