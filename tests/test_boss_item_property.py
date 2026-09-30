"""Property tests for `boss_rush` and `item_hunt` (project-completion Req 4 and Req 5).

Properties that must hold for every input and every seed:

  boss_rush
    B1  the output stream is byte-length identical (size-preserving);
    B2  every moved anchor is a navpoint DECLARED in the boss's own level section;
    B3  bosses in level sections other than the chosen arena are never touched;
    B4  an unusable `arena` is refused with nothing changed.

  item_hunt
    I1  the output stream is byte-length identical;
    I2  every name field keeps its exact width (so no archive boundary can move);
    I3  the multiset of names across the goods and the container slots is unchanged per width
        (an exchange - nothing lost, nothing invented);
    I4  an unknown `sources` is refused with nothing changed.

The blob here is synthetic: no game data.

Run from the repo root:
    python -m pytest tests/test_boss_item_property.py -q
"""
from __future__ import annotations

import bisect
import random
import re
import sys
from collections import Counter
from pathlib import Path

from hypothesis import given, settings, strategies as st

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import rando_core as rc  # noqa: E402


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def _nav(name: bytes) -> bytes:
    return (b'$Name:\t"' + name + b'"\r\n$Type:\t"level"\r\n+Plane:\t0\r\n'
            b"$Position:\t< 1.0, 2.0, 3.0 >\r\n\r\n")


def _placement(char: bytes, anchor: bytes, boss: bool = False) -> bytes:
    out = bytearray()
    out += b'$Name:\t\t\t"' + char + b"#" + anchor + b'"\r\n'
    out += b'$Character:\t\t\t"' + char + b'"\r\n'
    out += b"+Monster\r\n"
    if boss:
        out += b"+Boss\r\n"
    out += b'$Start position:\t"' + anchor + b'"\r\n\r\n'
    return bytes(out)


def _section(navs: list[bytes], placements: list[bytes], extra: bytes = b"") -> bytes:
    out = bytearray(b"#Navpoints\r\n\r\n")
    for n in navs:
        out += _nav(n)
    out += b"#Objects\r\n\r\n"
    for p in placements:
        out += p
    out += extra
    out += b"#End\r\n"
    return bytes(out)


def _container(name: bytes, yield_: bytes) -> bytes:
    return (b'$Name: "' + name + b'"\r\n+Give: 1\r\n+Messagebox: "' + yield_ + b'"\r\n\r\n')


def _shop(names: list[bytes]) -> bytes:
    return b"+Buy List:\r\n" + b"".join(b'"' + n + b'"\r\n' for n in names) + b"$End\r\n\r\n"


def _named_fields(blob: bytes) -> Counter:
    """Counter of (width, name) over every goods/slot name the two transforms look at."""
    c: Counter = Counter()
    for _s, _e, n in rc._container_yields(blob):
        c[(len(n), n)] += 1
    for _s, _e, n in rc._shop_stock(blob):
        c[(len(n), n)] += 1
    for m in rc._GAIN_ITEM_RE.finditer(blob):
        c[(len(m.group(1)), m.group(1))] += 1
    return c


# --------------------------------------------------------------------------- #
# strategies
# --------------------------------------------------------------------------- #
_shot_items = [b"Gem", b"Ruby Ring", b"Amethyst", b"Tonic", b"Healing Draught",
               b"Elixir of Recovery", b"Gold"]
_boss_names = [b"Titus", b"Pyrul", b"Luminar", b"Machival", b"Tiger Rider"]
_anchors = [b"$npc001", b"$npc002", b"$npc003", b"$npc0011", b"$npc0012"]


@settings(max_examples=80, deadline=None)
@given(goods=st.lists(st.sampled_from(_shot_items), min_size=1, max_size=6),
       yields_=st.lists(st.sampled_from(_shot_items), min_size=1, max_size=6),
       seed=st.text(alphabet="XYZ01", min_size=1, max_size=6),
       sources=st.sampled_from(["shops", "quest", "both"]))
def test_item_hunt_properties(goods, yields_, seed, sources) -> None:
    body = bytearray()
    body += _shop([g for g in goods if g != b"Gold"])
    for i, g in enumerate(goods):
        body += b'+Gain Item: "' + g + b'"\r\n'
    for i, y in enumerate(yields_):
        body += _container(b"chest%d" % i, y)
    blob = _section([b"$npc001"], [], extra=bytes(body))

    out, _rep = rc.t_item_hunt(blob, random.Random(seed), sources=sources)

    # I1 size-preserving
    assert len(out) == len(blob), "size changed"
    # I2 every name field keeps its width
    assert sorted(len(n) for _s, _e, n in rc._container_yields(out)) == \
           sorted(len(n) for _s, _e, n in rc._container_yields(blob))
    assert [(s, e) for s, e, _n in rc._container_yields(out)] == \
           [(s, e) for s, e, _n in rc._container_yields(blob)]
    # I3 nothing lost / invented: the per-width name multiset is unchanged
    assert _named_fields(out) == _named_fields(blob), "a name was lost, invented or resized"


@given(sources=st.sampled_from(["bogus", "SHOPS", ""]))
def test_item_hunt_unknown_sources_refused(sources) -> None:
    blob = _section([b"$npc001"], [], extra=_shop([b"Amethyst"]) + _container(b"c", b"Amethyst"))
    out, rep = rc.t_item_hunt(blob, random.Random("1"), sources=sources)
    assert out == blob and rep.changed == 0
    assert any("unknown sources" in n for n in rep.notes)


@settings(max_examples=80, deadline=None)
@given(n_bosses=st.integers(min_value=1, max_value=4),
       n_other=st.integers(min_value=0, max_value=3),
       seed=st.text(alphabet="ABC01", min_size=1, max_size=6))
def test_boss_rush_properties(n_bosses, n_other, seed) -> None:
    navs = [b"$npc001", b"$npc002", b"$npc003", b"$npc004"]
    arena = _section(navs, [_placement(b"Titus", navs[i % len(navs)], boss=True)
                            for i in range(n_bosses)])
    other_navs = [b"$npc001", b"$npc002"]
    other = _section(other_navs, [_placement(b"Pyrul", other_navs[i % len(other_navs)], boss=True)
                                  for i in range(n_other)]) if n_other else b""
    blob = arena + other

    out, rep = rc.t_boss_rush(blob, random.Random(seed), arena="auto")

    # B1 size-preserving
    assert len(out) == len(blob), "size changed"

    # B2: any boss anchor in the output is a navpoint DECLARED in that boss's own section
    secs = rc._rooms_sections(out)
    declared = [rc._section_navpoints(out, a, b) for a, b in secs]
    starts = [a for a, _ in secs]
    for (s, e) in rc._placement_records(out):
        seg = out[s:e]
        m = rc.START_POS_RE.search(seg)
        if not m or b"+Boss" not in seg:
            continue
        sec = bisect.bisect_right(starts, s) - 1
        assert m.group(2) in declared[sec], "a boss anchor moved to a navpoint not in its level"
    # B3: every section other than the chosen arena is byte-identical to the input. The
    # transform's `auto` arena is the section with the most bosses (ties -> lowest index).
    secs = rc._rooms_sections(blob)
    starts = [a for a, _ in secs]
    counts = Counter()
    for (s, e) in rc._placement_records(blob):
        if b"+Boss" in blob[s:e]:
            counts[bisect.bisect_right(starts, s) - 1] += 1
    arena_sec = max(counts, key=lambda k: (counts[k], -k))
    for i, (a, b) in enumerate(secs):
        if i != arena_sec:
            assert out[a:b] == blob[a:b], f"section {i} (not the arena) was touched"


def test_boss_rush_unusable_arena_refused() -> None:
    blob = _section([b"$npc001"], [_placement(b"Titus", b"$npc001", boss=True)])
    out, rep = rc.t_boss_rush(blob, random.Random("1"), arena="not-a-level")
    assert out == blob and rep.changed == 0
    assert any("unusable arena" in n for n in rep.notes)


def test_boss_and_item_registered() -> None:
    for n in ("boss_rush", "item_hunt"):
        assert n in rc.TRANSFORMS and n in rc.OPTIONS and n in rc.OPTION_AWARE
    assert rc.MODES["boss_rush"]["transforms"] == ["boss_rush"]
    assert rc.MODES["item_hunt"]["transforms"] == ["item_scatter", "item_hunt"]
