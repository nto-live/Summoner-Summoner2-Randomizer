"""Inspect the dumped UI tree structure and confirm feature labels are present.
Reads desktop/_ui/ui-populated.json (produce it with the harness --dump-ui --state populated)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
UI_JSON = os.path.normpath(os.path.join(HERE, "..", "..", "desktop", "_ui", "ui-populated.json"))

raw = open(UI_JSON, encoding="utf-8").read()
d = json.loads(raw)
c = d["control"]
print("control keys:", list(c.keys()))
ch = c.get("children")
print("children type:", type(ch), "len:", len(ch) if ch else 0)
for tok in ['"rows"', '"gridRows"', '"items"', '"Feature"', '"children"']:
    print(f"{tok} count:", raw.count(tok))
for kw in ["Skip the tutorials", "Skip the startup", "Endgame gate", "Max weapon", "Buff armour",
           "Set enemy HP", "Random enemies", "Random XP", "Guaranteed", "attack damage", "music"]:
    print(f'label "{kw}":', raw.count(kw))
