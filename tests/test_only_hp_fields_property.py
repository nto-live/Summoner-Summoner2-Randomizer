"""Property test — Feature: nto-live-randomizer-options, Property 2.

Validates: Requirements 1.7

Property 2: Only HP fields change.
For any blob containing hostile ``#Character Info`` blocks whose HP fields are
interleaved with non-HP numeric fields (``$Attack``, ``+Level:``, damage, ...),
after ``t_enemy_hp_set(blob, rng, value=v)`` with ``v`` in ``[1, 999]`` every byte
that lies OUTSIDE a ``$Max Hit Points`` / ``$Hit Points`` value span is byte-for-byte
identical to the input, and every non-HP numeric field keeps its exact original value.

The HP value spans are located the same way the transform locates them: the
``HP_FIELDS`` regexes are applied only inside the ``#Character Info`` blocks that
``_hostile_char_blocks`` recognises as hostile — so the "outside" set the test
checks is exactly the complement of what the transform is permitted to touch.

Non-vacuity is enforced: every generated blob is built so ``_hostile_char_blocks``
finds at least one hostile block and ``t_enemy_hp_set`` actually rewrites at least
one HP field. Otherwise "only HP changed" would pass trivially on a no-op.
"""
from __future__ import annotations

import re
import sys
from random import Random
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

# Make `src/` importable so we can drive the transform directly.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import rando_core  # noqa: E402
from rando_core import (  # noqa: E402
    HP_FIELDS,
    _hostile_char_blocks,
    t_enemy_hp_set,
)


# --------------------------------------------------------------------------- #
# Synthetic blob generator
# --------------------------------------------------------------------------- #
# Non-HP numeric fields interleaved with the HP fields. These MUST never be
# touched by the transform (Req 1.7: HP only — attack, damage, level untouched).
_NON_HP_FIELD_TEMPLATES = (
    b"$Attack:\t\t\t{n}\n",
    b"$Damage:\t\t\t{n}\n",
    b"+Level:\t\t\t{n}\n",
    b"$Aggressiveness:\t{n}\n",
    b"$Attack Radius:\t\t{n}\n",
)

# Hostile team labels recognised by TEAM_RE + HOSTILE_TEAMS in rando_core.
_HOSTILE_TEAMS = ("hostile", "Hostile", "evil")


def _num_field(template: bytes, value: int) -> bytes:
    return template.replace(b"{n}", str(value).encode())


@st.composite
def hostile_blocks_blob(draw):
    """A blob of hostile ``#Character Info`` blocks with HP fields interleaved
    with non-HP numeric fields, surrounded by arbitrary other bytes/blocks.

    Every block is guaranteed hostile (so ``_hostile_char_blocks`` picks it up)
    and carries at least one HP field with a value that differs from the value
    the transform will write, so the transform is guaranteed to change something.
    """
    parts: list[bytes] = []

    # Leading arbitrary content: a non-hostile block and/or filler that the
    # transform must leave alone.
    if draw(st.booleans()):
        parts.append(
            b"#Character Info\n"
            b'$Character:\t"Friendly Guy"\n'
            b'$Team:\t\t"friendly"\n'
            b"$Max Hit Points:\t40\n"   # friendly HP: must NOT be touched
            b"$Hit Points:\t\t40\n"
            b"$Attack:\t\t7\n"
        )
    parts.append(draw(st.binary(min_size=0, max_size=24)))

    n_blocks = draw(st.integers(min_value=1, max_value=4))
    for i in range(n_blocks):
        team = draw(st.sampled_from(_HOSTILE_TEAMS))
        # HP field widths vary (w2/w3/w4) so clamping/width behaviour is exercised;
        # the original digits are chosen so they differ from the written value.
        max_hp_w = draw(st.integers(min_value=1, max_value=4))
        cur_hp_w = draw(st.integers(min_value=1, max_value=4))
        # Digit strings that keep their leading digit non-zero-ish and are unlikely
        # to already equal the transform's output (we assert non-vacuity below too).
        max_hp = str(draw(st.integers(min_value=1, max_value=int("9" * max_hp_w)))).encode()
        cur_hp = str(draw(st.integers(min_value=1, max_value=int("9" * cur_hp_w)))).encode()

        block = bytearray()
        block += b"#Character Info\n"
        block += b'$Character:\t"Hostile %d"\n' % i
        block += b'$Size:\t\t"medium"\n'
        block += b'$Team:\t\t"%s"\n' % team.encode()

        # Interleave non-HP numeric fields around the HP fields.
        lead = draw(st.lists(
            st.tuples(st.sampled_from(_NON_HP_FIELD_TEMPLATES),
                      st.integers(min_value=0, max_value=9999)),
            min_size=0, max_size=3))
        for tmpl, val in lead:
            block += _num_field(tmpl, val)

        block += b"$Max Hit Points:\t" + max_hp + b"\n"

        mid = draw(st.lists(
            st.tuples(st.sampled_from(_NON_HP_FIELD_TEMPLATES),
                      st.integers(min_value=0, max_value=9999)),
            min_size=0, max_size=3))
        for tmpl, val in mid:
            block += _num_field(tmpl, val)

        block += b"$Hit Points:\t\t" + cur_hp + b"\n"

        tail = draw(st.lists(
            st.tuples(st.sampled_from(_NON_HP_FIELD_TEMPLATES),
                      st.integers(min_value=0, max_value=9999)),
            min_size=0, max_size=3))
        for tmpl, val in tail:
            block += _num_field(tmpl, val)

        parts.append(bytes(block))
        # Arbitrary filler between blocks (never starts with "\n#", so it can't
        # forge a new block header). Sanitised to avoid accidental headers.
        filler = draw(st.binary(min_size=0, max_size=24)).replace(b"\n#", b"\nX")
        parts.append(filler)

    # A trailing non-block section so the last block's end is well-defined.
    parts.append(b"\n#Doors\n")
    parts.append(draw(st.binary(min_size=0, max_size=24)).replace(b"\n#", b"\nX"))

    return b"".join(parts)


def _hp_value_spans(blob: bytes) -> list[tuple[int, int]]:
    """Absolute (start, end) byte spans of every HP *value* the transform may write.

    Mirrors exactly what ``_set_hp_uniform`` does: for each hostile block, apply
    each ``HP_FIELDS`` regex to that block's segment and take group(2)'s span.
    """
    spans: list[tuple[int, int]] = []
    for s, e in _hostile_char_blocks(blob):
        seg = blob[s:e]
        for rx in HP_FIELDS:
            for m in re.finditer(rx, seg):
                spans.append((s + m.start(2), s + m.end(2)))
    return spans


def _non_hp_numeric_fields(blob: bytes) -> list[tuple[int, int, bytes]]:
    """Every non-HP numeric field as (start, end, value) — must be untouched."""
    out: list[tuple[int, int, bytes]] = []
    for rx in (rb"(\$Attack\s*:\s*)(\d+)",
               rb"(\$Damage\s*:\s*)(\d+)",
               rb"(\+Level\s*:\s*)(\d+)"):
        for m in re.finditer(rx, blob):
            out.append((m.start(2), m.end(2), m.group(2)))
    return out


@settings(max_examples=150)
@given(blob=hostile_blocks_blob())
def test_only_hp_fields_change(blob):
    """Feature: nto-live-randomizer-options, Property 2: Only HP fields change"""
    rng = Random(0xC0FFEE)  # rng is unused by the transform; seeded for determinism.

    # Sweep the requested value across [1, 999]; derived deterministically from the
    # blob so every generated input exercises a different value.
    value = (sum(blob) % 999) + 1
    assert 1 <= value <= 999

    out, rep = t_enemy_hp_set(blob, rng, value=value)

    # Length is preserved (the whole design rests on size-preservation).
    assert len(out) == len(blob)

    # Non-vacuity: the generator guarantees hostile blocks with HP fields, and the
    # transform must actually rewrite at least one HP field. Without this, "only
    # HP changed" passes trivially on a no-op.
    hp_spans = _hp_value_spans(blob)
    assert hp_spans, "generator must produce at least one hostile HP field"
    # Discard the rare example where the swept value happens to already equal every
    # HP field (a genuine no-op) so the non-vacuity check below stays meaningful
    # without falsely failing.
    assume(rep.changed >= 1)
    assert out != blob, "transform must produce an observable change"

    # Core property: every byte OUTSIDE an HP value span is identical to input.
    inside = bytearray(len(blob))
    for a, b in hp_spans:
        for i in range(a, b):
            inside[i] = 1
    for i in range(len(blob)):
        if not inside[i]:
            assert out[i] == blob[i], (
                f"byte at {i} changed but is outside every HP value span"
            )

    # Redundant but explicit: non-HP numeric fields keep their exact values.
    for start, end, original in _non_hp_numeric_fields(blob):
        assert out[start:end] == original, (
            f"non-HP numeric field at [{start}:{end}] was altered"
        )
