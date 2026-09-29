#!/usr/bin/env python3
"""Generate the feature register from the engine's own catalogue.

`cli.py --list` already emits the whole surface as JSON: modes, transforms, option
schemas, binary patches and the blocked/pending list. So the register is GENERATED
rather than hand-maintained - which is the only way it cannot drift from the code
(doc drift is this project's recurring bug).

    python tools/gen-feature-register.py

Writes docs/FEATURES-REGISTER.md. Contains names and schemas only, never game data.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
OUT = HERE / "docs" / "FEATURES-REGISTER.md"
CACHE = HERE / "work" / "catalogue.json"


def catalogue() -> dict:
    r = subprocess.run(
        [sys.executable, str(HERE / "src" / "cli.py"), "--list", "-q"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise SystemExit("cli.py --list failed:\n" + r.stderr.decode("utf-8", "replace"))
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return d


# Modes whose transform has never been watched in game. Kept explicit and short: this
# is the one list that must be edited by hand, because "has a human seen it" is not
# something the engine can know. Verified tiers live in TEST-PLAN.md.
PLAY_VERIFIED_MODES = {"vanilla", "doors", "door_remap", "chaos", "peaceful"}
PLAY_VERIFIED_BINARY = {"skip_intro"}


def tier(mode: str, c: dict) -> str:
    spec = c["modes"][mode]
    if spec.get("binary"):
        names = [b[0] for b in spec["binary"]]
        if all(n in PLAY_VERIFIED_BINARY for n in names):
            return "play-verified"
        return "boot-verified"
    if mode in PLAY_VERIFIED_MODES:
        return "play-verified"
    return "build-verified"


def main() -> int:
    c = catalogue()
    modes, trans, orders = c["modes"], c["transforms"], c["mode_order"]
    info, options, pending = c["info"], c["options"], c["pending"]
    binary, opt_aware = c["binary"], set(c["option_aware"])

    used = {t for m in modes.values() for t in m.get("transforms", [])}
    orphan = [t for t in trans if t not in used]

    L: list[str] = []
    A = L.append
    A("# Feature register")
    A("")
    A("**Generated** by `tools/gen-feature-register.py` from `src/cli.py --list` \u2014 do not hand-edit.")
    A("Every count below comes from the engine, so this file cannot silently disagree with the code.")
    A("The verification tiers themselves are defined in `TEST-PLAN.md`.")
    A("")
    A("## Summary")
    A("")
    A(f"| | count |")
    A("|---|---|")
    A(f"| Modes | {len(modes)} |")
    A(f"| Transforms | {len(trans)} |")
    A(f"| Option-bearing transforms | {len(opt_aware)} |")
    A(f"| Binary (executable) patches | {len(binary)} |")
    A(f"| Blocked / pending, with a recorded reason | {len(pending)} |")
    A(f"| Transforms not reachable from any mode | {len(orphan)} |")
    A("")
    A("**State key.** `play-verified` \u2014 a human watched it work \u00b7 `boot-verified` \u2014 reaches gameplay "
      "under the harness \u00b7 `build-verified` \u2014 the engine applied it, size preserved, edits confined to "
      "declared fields \u00b7 `blocked` \u2014 refuses to run, reason recorded.")
    A("")
    A("> The tier column is the *worst* claim the mode is entitled to make. A mode built out of "
      "correct-but-unseen transforms is `build-verified` no matter how confident anyone is.")
    A("")

    # ---------------------------------------------------------------- modes
    A("## 1. Modes")
    A("")
    for name in orders:
        m = modes.get(name)
        if not m:
            continue
        A(f"### `{name}` \u2014 {m.get('label', '')}")
        A("")
        A(f"- **Tier:** `{tier(name, c)}`")
        A(f"- **Risk:** {m.get('risk', 'unstated')}")
        ts = m.get("transforms", [])
        bs = m.get("binary", [])
        if ts:
            A(f"- **Transforms ({len(ts)}):** " + ", ".join(f"`{t}`" for t in ts))
        if bs:
            A("- **Binary patches:** " + ", ".join(f"`{b[0]}`" for b in bs))
        opts = m.get("options") or {}
        if opts:
            bits = []
            for t, kv in opts.items():
                for k, v in kv.items():
                    bits.append(f"`{t}.{k}={v}`")
            A("- **Options preset:** " + ", ".join(bits))
        blurb = (m.get("blurb") or "").strip()
        if blurb:
            A(f"- {blurb}")
        A("")

    # ---------------------------------------------------------------- transforms
    A("## 2. Transforms")
    A("")
    A("| transform | what it does | options | used by |")
    A("|---|---|---|---|")
    for t in trans:
        label, blurb = info.get(t, (t, "_(no description in the catalogue)_"))
        blurb = " ".join(blurb.replace("|", "/").split())
        if len(blurb) > 200:
            blurb = blurb[:197] + "..."
        opts = ", ".join(f"`{k}`" for k in options.get(t, {})) or "\u2014"
        users = [n for n in orders if t in modes.get(n, {}).get("transforms", [])]
        use = f"{len(users)}" + (f" ({users[0]}...)" if len(users) > 2 else (" (" + ", ".join(users) + ")" if users else ""))
        A(f"| `{t}` | {blurb} | {opts} | {use} |")
    A("")

    # ---------------------------------------------------------------- binary
    A("## 3. Binary patches (they edit the executable, not the data layer)")
    A("")
    A("| patch | address | expects | state |")
    A("|---|---|---|---|")
    for n, b in binary.items():
        state = "**BLOCKED** \u2014 " + b["blocked"] if b.get("blocked") else (
            "play-verified" if n in PLAY_VERIFIED_BINARY else "verified byte-for-byte, not watched in game")
        A(f"| `{n}` | `{b.get('va', '?')}` | `{b.get('expects', '?')}` | {state} |")
    A("")
    A("Every patch declares the bytes it expects and refuses on mismatch \u2014 that rule is not optional.")
    A("")

    # ---------------------------------------------------------------- blocked
    A("## 4. Blocked and pending \u2014 with the reason and what would unblock it")
    A("")
    A("These are the honest gaps. Each carries a `blocked_by`, so no one has to re-derive why.")
    A("")
    A("| item | blocked by | reason |")
    A("|---|---|---|")
    for n, p in pending.items():
        reason = " ".join(p["reason"].replace("|", "/").split())
        A(f"| `{n}` | {p['blocked_by']} | {reason} |")
    A("")

    if orphan:
        A("## 5. Transforms not reachable from any mode")
        A("")
        A("Implemented and listed, but no mode bundles them. Either wire them into a mode or the "
          "work is invisible to a user.")
        A("")
        for t in orphan:
            A(f"- `{t}`")
        A("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE)}  ({OUT.stat().st_size:,} bytes)")
    print(f"  modes {len(modes)} | transforms {len(trans)} | binary {len(binary)} | "
          f"pending {len(pending)} | orphan transforms {len(orphan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
