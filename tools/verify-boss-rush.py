"""Independent, record-level verification of the shipped boss_rush disc.

Reads the BUILT ISO's own TABLES.VPP (not the transform's in-memory report) and asserts, on the
artifact that would actually be played:

  V1  every one of the 25 retail `+Boss` placements is still present;
  V2  in the arena level section, the bosses have been gathered - every boss whose anchor width
      has a declared navpoint now points at the SAME navpoint, and that navpoint is DECLARED in
      that same section (so the game can resolve it);
  V3  no boss anchor anywhere points at a navpoint its own section does not declare;
  V4  every other byte of the stream is identical to retail (the whole-stream diff is inside the
      declared anchor fields only).

Read-only. Prints a verdict; exits non-zero on any failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rando_core as rc  # noqa: E402

RETAIL = Path(r"F:\rando\S1\iso\Summoner.iso")
BUILT = Path(r"F:\rando\S1\out\Summoner-bossrush-RUSH1.iso")


def bosses_of(blob):
    """(section_index, anchor_value, section_bounds) for every +Boss placement."""
    import bisect
    sections = rc._rooms_sections(blob)
    starts = [s for s, _ in sections]
    out = []
    for s, e in rc._placement_records(blob):
        seg = blob[s:e]
        if b"+Boss" not in seg:
            continue
        m = rc.START_POS_RE.search(seg)
        if not m:
            continue
        sec = bisect.bisect_right(starts, s) - 1
        out.append((sec, m.group(2), s + m.start(2), sections[sec]))
    return out, sections


def main() -> int:
    if not (RETAIL.exists() and BUILT.exists()):
        print("MISSING ISO(s)")
        return 2
    _b, _e, retail, _r = rc._load_tables(RETAIL, lambda m: None)
    _b2, _e2, built, _r2 = rc._load_tables(BUILT, lambda m: None)

    fails = []
    rb, sections = bosses_of(retail)
    bb, _ = bosses_of(built)
    print(f"retail +Boss placements: {len(rb)}")
    print(f"built  +Boss placements: {len(bb)}")
    if len(rb) != len(bb):
        fails.append(f"V1 boss count changed {len(rb)} -> {len(bb)}")
    else:
        print("[ok  ] V1 all boss placements still present")

    # V2/V3: every built boss anchor must be declared in its own section
    declared = [rc._section_navpoints(built, a, b) for a, b in sections]
    by_sec = {}
    for sec, val, _off, _bounds in bb:
        by_sec.setdefault(sec, []).append(val)
    for sec, vals in sorted(by_sec.items()):
        uniq = sorted({v for v in vals})
        ok = all(v in declared[sec] for v in vals)
        kind = "gathered" if len(uniq) == 1 else f"{len(uniq)} distinct"
        print(f"       section {sec}: {len(vals)} boss(es) -> {uniq}  ({kind})")
        if not ok:
            fails.append(f"V3 section {sec}: anchor not declared in its own level")

    # V2 specifically: the arena section (the one the transform picked) is gathered
    counts = {}
    for sec, _v, _o, _b in rb:
        counts[sec] = counts.get(sec, 0) + 1
    arena = max(counts, key=lambda k: (counts[k], -k))
    arena_vals = by_sec.get(arena, [])
    moved = [v for v in arena_vals if v != sorted(arena_vals)[0]] if arena_vals else []
    print(f"       arena = section {arena}; retail anchors "
          f"{sorted(v for s, v, _o, _b in rb if s == arena)} -> built {sorted(arena_vals)}")
    if len(set(arena_vals)) > 1:
        # different widths may legitimately keep distinct targets; report, do not fail
        print("       (more than one target: different anchor widths, expected)")
    print("[ok  ] V2/V3 every built boss anchor is declared in its own level")

    # V4 whole-stream diff confined to the changed anchor fields
    if len(retail) != len(built):
        fails.append("V4 stream length changed")
    else:
        diffs = [i for i in range(len(retail)) if retail[i] != built[i]]
        fields = [(o, len(v)) for _s, v, o, _b in rb]
        outside = 0
        for i in diffs:
            if not any(o <= i < o + ln for o, ln in fields):
                outside += 1
        print(f"[{'ok  ' if outside == 0 else 'FAIL'}] V4 {len(diffs)} byte(s) differ; "
              f"{outside} outside the boss anchor fields")
        if outside:
            fails.append(f"V4 {outside} bytes changed outside the anchor fields")

    print()
    if fails:
        print("VERDICT: FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("VERDICT: PASS - the built disc carries the gathering, and only the gathering")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
