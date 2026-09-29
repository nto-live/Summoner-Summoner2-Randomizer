"""How many enemy/NPC placements exist in the masad starting area, and how many are
convertible to monsters? 'Add 100 enemies' can only be done size-preservingly by converting
existing placements (adding new records grows the file, which is forbidden)."""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    # locate the masad level file span (between its "Level file for" markers or $Level:)
    # masad appears many times; find the biggest contiguous masad level chunk by looking for
    # a "$Level:" masad followed by lots of records.
    marks = [(m.start(), m.group(1).decode("latin-1")) for m in re.finditer(rb'\$Level:\s*"([^"]+)"', blob)]
    # find masad chunks and measure span to next $Level:
    spans = []
    for i, (pos, name) in enumerate(marks):
        if name.lower() == "masad":
            end = marks[i + 1][0] if i + 1 < len(marks) else len(blob)
            spans.append((pos, end, end - pos))
    spans.sort(key=lambda s: -s[2])
    print(f"masad $Level: chunks: {len(spans)}; largest span {spans[0][2]} bytes at 0x{spans[0][0]:X}" if spans else "no masad chunk")

    if not spans:
        return
    s, e, _ = spans[0]
    seg = blob[s:e]

    # count placements: $Character (npc/monster placements), +Monster markers, $Start position navpoints
    chars = re.findall(rb'\$Character:\s*"([^"]+)"', seg)
    monsters = re.findall(rb'\+Monster\b', seg)
    peaceful = len(chars) - len(monsters)
    navpoints = re.findall(rb'\$Start position:\s*"([^"]+)"', seg)
    print(f"  $Character placements in masad chunk: {len(chars)}")
    print(f"  +Monster markers: {len(monsters)}")
    print(f"  peaceful (convertible) placements ~= {peaceful}")
    print(f"  $Start position navpoints: {len(navpoints)}")

    # also across ALL masad chunks (the level may be split)
    total_chars = total_mon = 0
    for cs, ce, _ in spans:
        sg = blob[cs:ce]
        total_chars += len(re.findall(rb'\$Character:\s*"([^"]+)"', sg))
        total_mon += len(re.findall(rb'\+Monster\b', sg))
    print(f"\n  ALL masad chunks: {total_chars} $Character, {total_mon} +Monster, "
          f"~{total_chars - total_mon} convertible")

    # sample a placement block to see what conversion needs
    m = re.search(rb'\$Character:\s*"[^"]+"', seg)
    if m:
        print("\n  sample placement block:")
        print("  ", seg[m.start():m.start() + 200].replace(b"\r", b"").replace(b"\t", b" ").decode("latin-1", "replace"))


if __name__ == "__main__":
    main()
