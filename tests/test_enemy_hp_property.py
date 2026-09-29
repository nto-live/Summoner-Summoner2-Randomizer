"""Property tests for the standalone "set enemy HP" lever (src/rando_core.py t_enemy_hp_set).

Feature: nto-live-randomizer-options

Run from repo root:
    python -m pytest tests/test_enemy_hp_property.py -q
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Import the engine core from src/ (same seam the other tests use: src on sys.path).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import rando_core as rc  # noqa: E402


# --------------------------------------------------------------------------- #
# Synthetic blob generator
#
# We emit byte strings made of random hostile `#Character Info` blocks exactly as
# `_hostile_char_blocks` recognizes them:
#   * the literal header `#Character Info`
#   * a `$Team: "<hostile team>"` line, where the team is one of HOSTILE_TEAMS
#   * random `$Max Hit Points:` / `$Hit Points:` fields of varying digit widths
#   * interleaved non-HP numeric noise ($Attack, +Level) to prove HP-only scope
#
# A block runs from just after its `#Character Info` header to the next `\n#`, so
# every block is closed by starting the next section with `\n#`. We assert the
# generator's blocks are actually found by `_hostile_char_blocks` (below) so the
# property can never be vacuous.
# --------------------------------------------------------------------------- #

# The teams _char_info_blocks treats as hostile. TEAM_RE only captures [A-Za-z]+,
# so every value here is a clean single-token team name.
_HOSTILE_TEAMS = sorted(t.decode("latin-1") for t in rc.HOSTILE_TEAMS)


@st.composite
def _hp_field(draw) -> tuple[str, int]:
    """Draw one HP field digit string and report its width.

    Widths 1..4 cover the w2/w3/w4 hostile-side classes described in the design,
    plus width 1 as an extra edge. The value itself is arbitrary within the width.
    """
    width = draw(st.integers(min_value=1, max_value=4))
    if width == 1:
        digits = str(draw(st.integers(min_value=0, max_value=9)))
    else:
        lo = 10 ** (width - 1)
        hi = 10 ** width - 1
        digits = str(draw(st.integers(min_value=lo, max_value=hi)))
    assert len(digits) == width
    return digits, width


@st.composite
def _hostile_block(draw) -> str:
    """One hostile `#Character Info` block as text.

    Contains a hostile `$Team:`, at least one `$Max Hit Points` and one `$Hit Points`
    field (possibly several of each, of varying widths), plus non-HP numeric noise.
    """
    team = draw(st.sampled_from(_HOSTILE_TEAMS))
    lines = ["#Character Info", f'\t$Team: "{team}"']

    # non-HP numeric noise before/around the HP fields
    lines.append(f"\t$Attack: {draw(st.integers(min_value=0, max_value=9999))}")

    n_max = draw(st.integers(min_value=1, max_value=3))
    for _ in range(n_max):
        digits, _w = draw(_hp_field())
        lines.append(f"\t$Max Hit Points: {digits}")

    lines.append(f"\t+Level: {draw(st.integers(min_value=1, max_value=99))}")

    n_cur = draw(st.integers(min_value=1, max_value=3))
    for _ in range(n_cur):
        digits, _w = draw(_hp_field())
        lines.append(f"\t$Hit Points: {digits}")

    return "\n".join(lines)


@st.composite
def _blob(draw) -> bytes:
    """A whole synthetic blob: one or more hostile blocks, each closed by the next `\\n#`.

    Blocks are separated by `\\n` so the following `#Character Info` supplies the
    `\\n#` boundary that closes the previous block. A trailing `\\n#End` closes the
    final block, matching how a real stream has a following section.
    """
    n = draw(st.integers(min_value=1, max_value=4))
    blocks = [draw(_hostile_block()) for _ in range(n)]
    text = "\n".join(blocks) + "\n#End\n"
    return text.encode("latin-1")


# HP field regexes, compiled from the module's own patterns so the test tracks the code.
_HP_RES = tuple(re.compile(rx) for rx in rc.HP_FIELDS)


def _hp_fields_in_hostile_blocks(blob: bytes) -> list[tuple[int, int]]:
    """Absolute (value_start, value_end) span of every HP field in recognized hostile blocks.

    The span is `group(2)` of the module's own HP_FIELDS regexes — the exact bytes
    `_set_hp_uniform` rewrites in place. Since the write is size-preserving, the same
    absolute byte range in the OUTPUT holds the rewritten (space-padded) value, so the
    span width proves per-field width preservation and reading it back proves the value.

    We only match against the ORIGINAL blob: HP_FIELDS' prefix ends in `\\s*`, which on
    the output would greedily eat the new leading-space padding and misreport the span.
    """
    out: list[tuple[int, int]] = []
    for s, e in rc._hostile_char_blocks(blob):
        for rx in _HP_RES:
            for m in rx.finditer(blob, s, e):
                out.append((m.start(2), m.end(2)))
    return sorted(out)


# --------------------------------------------------------------------------- #
# Feature: nto-live-randomizer-options, Property 1: Uniform HP write, per-field
# clamp, width preserved
#
# For any blob of hostile #Character Info blocks and any requested value v in
# [1, 999], after t_enemy_hp_set(blob, rng, value=v) every $Max Hit Points and
# $Hit Points field parses to min(v, int("9" * field_width)), each field keeps its
# original byte width, and len(output) == len(input).
#
# Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.8, 8.5
# --------------------------------------------------------------------------- #
@settings(max_examples=200)
@given(blob=_blob(), value=st.integers(min_value=1, max_value=999))
def test_property1_uniform_hp_write_per_field_clamp_width_preserved(
    blob: bytes, value: int
) -> None:
    rng = random.Random(1234)  # transform ignores rng; a seeded dummy is fine

    # The generator must produce blocks the code actually recognizes, else the
    # property would be vacuous. Capture the original HP field value spans here.
    original = _hp_fields_in_hostile_blocks(blob)
    assert original, "generator produced no recognized hostile HP fields (vacuous)"

    out, rep = rc.t_enemy_hp_set(blob, rng, value=value)

    # Size preserved exactly (Req 1.6, 8.5).
    assert len(out) == len(blob), "output length must equal input length"

    # The write is in place and size-preserving, so each field occupies the SAME
    # absolute byte range in the output. We read those input-derived spans straight
    # out of the output rather than re-matching, because HP_FIELDS' `\s*` prefix would
    # otherwise absorb the new leading-space padding and misreport the span.
    for start, end in original:
        width = end - start  # original byte width of this field's value span
        field_bytes = out[start:end]

        # Width preserved per field: the value span is unchanged in length (Req 1.6).
        assert len(field_bytes) == width

        # The field is the value right-justified into its own width, space-padded
        # (Req 1.8) — so it parses cleanly and holds only spaces + digits.
        assert re.fullmatch(rb" *\d+", field_bytes), (
            f"field {field_bytes!r} is not space-padded digits of width {width}"
        )

        # Value is min(v, all-nines-of-this-width) (Req 1.3 both fields, 1.4, 1.5).
        expected = min(value, int("9" * width))
        assert int(field_bytes) == expected, (
            f"field of width {width}: expected {expected}, got {int(field_bytes)}"
        )
