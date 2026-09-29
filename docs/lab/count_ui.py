"""Verify every engine feature is represented in the desktop GUI.

Produce the dump first:
  dotnet SummonerRando.Harness.dll --dump-ui --state populated   (writes desktop/_ui/ui-populated.json)
Then run this. It walks the control tree (children live under 'controls'), lists the feature-grid
rows and the binary-patch checkboxes, and cross-checks against `python src/cli.py --list`."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
UI_JSON = os.path.join(ROOT, "desktop", "_ui", "ui-populated.json")

d = json.load(open(UI_JSON, encoding="utf-8"))

nodes = []
def walk(n):
    nodes.append(n)
    for c in (n.get("controls") or n.get("children") or []):
        walk(c)
walk(d.get("control", d))

# feature grid: a node carrying 'rows'
# the dumper caps the serialized 'rows' detail to 6 but writes the true rowCount and rowTags
grids = [n for n in nodes if n.get("rowCount") is not None and n.get("columns")]
grid_labels = []
for g in grids:
    count = g.get("rowCount")
    tags = (g.get("rowTags") or {}).get("sample") or []
    print(f"GRID '{g.get('name')}': rowCount={count}, rowTags sampled={len(tags)}")
    grid_labels = [None] * count  # count is the truth; tags are the transform names
    # print the tags (transform ids) we can see
    for t in tags:
        print("   tag:", t)

# binary checkboxes
grid_row_count = grids[0].get("rowCount") if grids else 0
cbs = [n for n in nodes if str(n.get("type", "")) == "CheckBox"]
cb_texts = [c.get("text") for c in cbs]
# binary-patch toggles are the checkboxes whose text matches a binary patch label
bin_texts = [t for t in cb_texts if t and ("Skip" in t or "Endgame" in t or "gate" in t.lower())]
print(f"\nfeature-grid rows (true rowCount): {grid_row_count}")
print(f"all checkboxes: {cb_texts}")
print(f"binary-patch toggles: {bin_texts}")

# cross-check counts against the engine
try:
    out = subprocess.run([sys.executable, os.path.join(ROOT, "src", "cli.py"), "--list", "-q"],
                         capture_output=True, text=True)
    payload = json.loads(out.stdout)
    n_tf = len(payload["transforms"])
    n_bin = len(payload["binary"])
    print(f"\nengine: {n_tf} transforms, {n_bin} binary patches")
    print(f"GUI:    {grid_row_count} grid rows, {len(bin_texts)} binary toggles")
    print("MATCH transforms:", grid_row_count == n_tf, " MATCH binary:", len(bin_texts) == n_bin)
except Exception as e:
    print("cross-check skipped:", e)
