"""Explore the text-layer script language: what does a $Character block look like, and how are
enemies placed in a level?

  python enemy_explore.py blocks <n>          # show n complete $Character blocks
  python enemy_explore.py types               # distribution of $Type values
  python enemy_explore.py near <needle> ...   # show the text around a needle
  python enemy_explore.py census              # keys inside $Character blocks
"""
import collections
import re
import sys

BLOB = r"F:\rando\S1\notes\_end_blob.bin"


def load():
    return open(BLOB, "rb").read()


def blocks(blob, key=b"$Character"):
    """Yield (start, end, text) for each occurrence of the key up to the next top-level $key."""
    out = []
    for m in re.finditer(rb"\n[ \t]*" + re.escape(key) + rb"\s*:", blob):
        start = m.start()
        nxt = re.search(rb"\n\$[A-Za-z]", blob[start + 1:])
        end = start + 1 + (nxt.start() if nxt else 4096)
        out.append((start, end, blob[start:end]))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    blob = load()
    cmd = sys.argv[1]
    if cmd == "blocks":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        bl = blocks(blob)
        print(f"{len(bl)} $Character blocks")
        for i in range(min(n, len(bl))):
            s, e, t = bl[i * 7]
            print(f"--- block {i * 7} @ 0x{s:X} ({e - s} bytes) ---")
            print(t.decode("latin-1"))
    elif cmd == "types":
        bl = blocks(blob)
        c = collections.Counter()
        for s, e, t in bl:
            m = re.search(rb"\$Type\s*:\s*([^\r\n]*)", t)
            if m:
                c[m.group(1).decode("latin-1").strip()] += 1
        print(f"{len(bl)} blocks; $Type distribution:")
        for k, v in c.most_common(40):
            print(f"  {v:6}  {k!r}")
    elif cmd == "near":
        for needle in sys.argv[2:]:
            nb = needle.encode()
            for m in re.finditer(re.escape(nb), blob):
                s = max(0, m.start() - 120)
                print(f"--- {needle} @ 0x{m.start():X} ---")
                print(blob[s:m.start() + 200].decode("latin-1"))
                break
    elif cmd == "census":
        bl = blocks(blob)
        keys = collections.Counter()
        for s, e, t in bl:
            for m in re.finditer(rb"\n[ \t]*([+\$][A-Za-z][A-Za-z ]{1,24}):", t):
                keys[m.group(1).decode("latin-1")] += 1
        print(f"keys inside {len(bl)} $Character blocks:")
        for k, v in keys.most_common(60):
            print(f"  {v:7}  {k}")


if __name__ == "__main__":
    main()
