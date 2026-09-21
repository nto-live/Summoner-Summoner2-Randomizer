"""What is a 'room' in Summoner, and can we name the one the player is standing in?

Facts already known:
  * `#Objects` placements and triggers carry a `+Plane:` field, and the door check compares it
    against `player_entity + 0x698` - so that field is the game's room/plane id.
  * `Level_data.name` (live, read over PINE) is the *level*, not the room.

This script looks for room *names* in the text layer so an on-screen readout can say more than
"room 7".
"""
import collections
import re

BLOB = r"F:\rando\S1\notes\_end_blob.bin"
blob = open(BLOB, "rb").read()

print("=== key census (room-ish names) ===")
c = collections.Counter()
for m in re.finditer(rb"\n[ \t]*([+\$][A-Za-z][A-Za-z ]{1,20}):", blob):
    k = m.group(1).decode("latin-1")
    if re.search(r"room|plane|area|region|zone|sector|navpoint|level", k, re.I):
        c[k] += 1
for k, v in c.most_common(25):
    print(f"  {v:7}  {k}")

print("\n=== raw token counts ===")
for token in (b"$Room", b"#Room", b"+Room", b"$Plane", b"+Plane", b"$Area", b"+Area",
              b"$Zone", b"#Objects", b"$Navpoint", b"+Navpoint"):
    print(f"  {token.decode():12} {len(re.findall(re.escape(token), blob))}")

print("\n=== a +Plane: example, with context ===")
m = re.search(rb"\n[ \t]*\+Plane\s*:", blob)
if m:
    s = max(0, m.start() - 260)
    print(blob[s:m.start() + 260].decode("latin-1"))

print("\n=== distinct +Plane values ===")
vals = collections.Counter()
for m in re.finditer(rb"\+Plane\s*:?\s*([0-9]+)", blob):
    vals[m.group(1).decode()] += 1
print(f"  {len(vals)} distinct; most common: {vals.most_common(12)}")

print("\n=== any '$Name:' values that look like room labels (level-type records) ===")
# navpoint/level records look like:  $Name: \"$npc038\"  $Type: \"level\"  ... $Position: < x,y,z >
rooms = collections.Counter()
for m in re.finditer(rb'\$Name\s*:\s*\"([^\"]+)\"[^\n]*\n[ \t]*\n?[ \t]*\$Type\s*:\s*\"([^\"]+)\"',
                     blob):
    rooms[m.group(2).decode("latin-1")] += 1
print(f"  $Name/$Type pairs by type: {rooms.most_common(15)}")
