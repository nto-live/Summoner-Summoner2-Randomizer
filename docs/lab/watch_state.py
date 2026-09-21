"""Poll the live game state: level name, trigger count, and whether RAM is churning."""
import hashlib
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

REGIONS = (0x1200000, 0x800000, 0x2000000 - 0x80000)


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    with Pine() as p:
        end = time.time() + seconds
        prev = None
        while time.time() < end:
            try:
                name = p.read_string(0x1245410, 24)
                script = p.read_string(0x1245430, 24)
                ntrig = p.read(0x12844FC, 4)
                hashes = [hashlib.md5(p.read_buffer(r, 0x40000)).hexdigest()[:8] for r in REGIONS]
            except Exception as e:  # noqa: BLE001
                print(f"[{time.strftime('%H:%M:%S')}] pine error: {e}", flush=True)
                time.sleep(interval)
                continue
            churn = "".join("." if h == prev[i] else "*" for i, h in enumerate(hashes)) if prev else "-----"
            prev = hashes
            print(f"[{time.strftime('%H:%M:%S')}] level={name!r:26} script={script!r:20} ntrig={ntrig:<3} churn={churn}", flush=True)
            time.sleep(interval)


if __name__ == "__main__":
    main()
