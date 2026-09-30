"""Property tests for `rooms_shuffle` - the within-level anchor permutation.

Feature: project-completion, Requirement 2.

The transform permutes `$Start position` anchors between placements INSIDE one level. The
properties that must hold for every input, every seed and both `how` policies:

  P1  the output stream is byte-length identical to the input (size-preserving);
  P2  no anchor crosses a level boundary - each `#Navpoints` section keeps exactly the
      multiset of anchors it had (so every anchor still exists in the level it names);
  P3  a `$player*` start slot or a `$zzz*` disarm sentinel never moves;
  P4  an unknown `how` is refused with nothing changed;
  P5  the transform is deterministic - same seed, same bytes.

The blob here is synthetic: this file contains no game data.

Run from the repo root:
    python -m pytest tests/test_rooms_shuffle_property.py -q
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import rando_core as rc  # noqa: E402


# --------------------------------------------------------------------------- #
# synthetic world builder
# --------------------------------------------------------------------------- #
_ANCHORS = [b"$npc001", b"$npc002", b"$npc003", b"$npc004",
            b"$npcc001", b"$npcc002",
            b"$hostile09-01", b"$hostile09-02",
            b"$player1-01", b"$zzz001"]


def _section(plans: list[tuple[bytes, bytes]]) -> bytes:
    """One level script section: a `#Navpoints` header, an `#Objects` block, an `#End`.

    `plans` is a list of (character_name, anchor). The navpoint definitions that the anchors
    name are emitted first, so every anchor the placements use really exists in this section.
    """
    out = bytearray(b"#Navpoints\r\n\r\n")
    for anchor in sorted({a for _c, a in plans}):
        out += b'$Name:\t"' + anchor + b'"\r\n$Type:\t"level"\r\n+Plane:\t0\r\n'
        out += b"$Position:\t< 1.0, 2.0, 3.0 >\r\n\r\n"
    out += b"#Objects\r\n\r\n"
    for i, (char, anchor) in enumerate(plans):
        out += b'$Name:\t\t\t"' + char + b'#' + anchor + b'"\r\n'
        out += b'$Character:\t\t\t"' + char + b'"\r\n'
        out += b"+Monster\r\n"
        out += b'$Start position:\t"' + anchor + b'"\r\n\r\n'
    out += b"#End\r\n"
    return bytes(out)


def _build(levels: list[list[tuple[bytes, bytes]]]) -> bytes:
    return b"".join(_section(p) for p in levels)


def _anchors_by_section(blob: bytes) -> dict[int, Counter]:
    """(section index -> Counter of anchor values) using the transform's own segmentation."""
    sections = rc._rooms_sections(blob)
    starts = [s for s, _ in sections]
    import bisect
    out: dict[int, Counter] = {}
    for s, e in rc._placement_records(blob):
        m = rc.START_POS_RE.search(blob, s, e)
        if not m:
            continue
        i = bisect.bisect_right(starts, s) - 1
        out.setdefault(i, Counter())[m.group(2)] += 1
    return out


def _pinned_offsets(blob: bytes) -> dict[int, bytes]:
    """offset -> value for every pinned ($player*/$zzz*) anchor."""
    out = {}
    for s, e in rc._placement_records(blob):
        m = rc.START_POS_RE.search(blob, s, e)
        if m and rc._rooms_kind(m.group(2)) in rc._ROOMS_PINNED_KINDS:
            out[m.start(2)] = m.group(2)
    return out


# --------------------------------------------------------------------------- #
# strategies
# --------------------------------------------------------------------------- #
_anchor = st.sampled_from(_ANCHORS)
_char = st.sampled_from([b"Goblin", b"Rat", b"Guard", b"Priest"])
_plan = st.tuples(_char, _anchor)
_level = st.lists(_plan, min_size=1, max_size=12)
_world = st.lists(_level, min_size=1, max_size=4)


@settings(max_examples=120, deadline=None)
@given(world=_world, seed=st.text(alphabet="ABC012", min_size=1, max_size=8),
       how=st.sampled_from(["shuffle", "swap"]))
def test_rooms_shuffle_properties(world, seed, how) -> None:
    blob = _build(world)

    # P1 + determinism (P5): same seed -> identical bytes.
    out1, rep1 = rc.t_rooms_shuffle(blob, random.Random(seed), how=how)
    out2, _ = rc.t_rooms_shuffle(blob, random.Random(seed), how=how)
    assert out1 == out2, "not deterministic for the same seed"
    assert len(out1) == len(blob), "size changed"
    assert rep1.changed >= 0

    # P2: no anchor crosses a level boundary.
    before = _anchors_by_section(blob)
    after = _anchors_by_section(out1)
    assert before == after, f"anchors crossed a level boundary: {before} != {after}"

    # P3: pinned anchors never move.
    for off, val in _pinned_offsets(blob).items():
        assert out1[off:off + len(val)] == val, "a pinned anchor moved"


@settings(max_examples=60, deadline=None)
@given(world=_world)
def test_rooms_shuffle_unknown_how_is_refused(world) -> None:
    blob = _build(world)
    out, rep = rc.t_rooms_shuffle(blob, random.Random("X"), how="banana")
    assert out == blob, "an unknown how must change nothing"
    assert rep.changed == 0
    assert any("unknown how" in n for n in rep.notes)


def test_rooms_shuffle_only_moves_within_kind_and_width() -> None:
    """A lone anchor of its kind+width stays put; a group of two swaps within itself."""
    blob = _build([[
        (b"Goblin", b"$npc001"), (b"Rat", b"$npc002"),   # same kind+width -> movable pair
        (b"Guard", b"$hostile09-01"),                     # lone -> pinned by the group rule
    ]])
    out, _rep = rc.t_rooms_shuffle(blob, random.Random("1"), how="shuffle")
    # the lone hostile anchor kept its value
    assert b'"$hostile09-01"' in out
    # the npc pair still holds exactly those two anchors somewhere in the section
    assert Counter(_anchors_by_section(out)[0]) == {b"$npc001": 1, b"$npc002": 1,
                                                    b"$hostile09-01": 1}


def test_rooms_shuffle_registered_and_offered() -> None:
    """Requirement 2.1 / 2.6: the transform and its mode are in the catalogue the UI reads."""
    assert "rooms_shuffle" in rc.TRANSFORMS
    assert "rooms_shuffle" in rc.OPTION_AWARE
    assert "rooms_shuffle" in rc.OPTIONS
    assert "rooms" in rc.MODES
    assert rc.MODES["rooms"]["transforms"] == ["rooms_shuffle"]
    # Requirement 3: the NPC Hunt mode selects the two shipped transforms.
    assert rc.MODES["npc_hunt"]["transforms"] == ["spawn_shuffle", "npc_character_shuffle"]
