# Lab scripts

The tooling that produced every verification claim in this repository. They are **not** part of
the shipping product — the app and `cli.py` are — but without them none of the "verified in game"
statements could be checked, so they live here.

All of them talk to a **headless emulator on the developer machine**, not to the game's disc.
Nothing here is required to build or use the randomizer, and nothing here is distributed to end
users.

## Running the game headlessly (and the trap that cost a day)

```
EmuCore/GS Renderer = 13        # Software. With Vulkan the GS device dies every ~30 s in a
                                # session with no interactive desktop: PCSX2 recovers, the boot
                                # test still says PASS, and the GAME IS FROZEN. Whole-RAM churn
                                # scan is how you tell: 2 blocks change vs ~25.
EmuCore EnablePINE = true       # live read/write of the emulated console's memory on port 28011
EmuCore EnableCheats = true     # loads the test-only pnach
```

| Script | What it does |
|---|---|
| `pine.py` | PINE client: read/write EE memory, batched, savestate save/load, `lvlwatch` |
| `watch_state.py` | polls level name, script, trigger count and RAM churn — is the game alive? |
| `churn_scan.py` | whole-32 MB churn scan: the difference between "booted" and "running" |
| `probe_live.py` | entity/player pointers, floats, watch a position |
| `entity_count.py`, `entity_scan.py` | walk `Living_entity_list` and count what is alive, per level |
| `door_brute.py`, `door_push.py`, `force_door.py` | drive the player and the door check from outside |
| `find_counter.py` | find counter-like values (proof a frame loop runs) |
| `dis_va.py` | dump/decode R5900 instructions straight out of the ISO |
| `gp_xref.py` | find every instruction touching a gp-relative global |
| `make_door_test_iso.py` | build a one-door test disc (single in-place field rewrite, read-back verified) |
| `enemy_smoke.py` | run the enemy transforms against the extracted stream and assert size preservation |
| `enemy_explore.py`, `enemy_dump.py`, `monster_census.py`, `char_stats.py`, `char_info_analysis.py` | the text-layer census that produced `ENEMIES.md` |
| `room_probe.py`, `hud_strings.py`, `loc_string.py` | rooms (`+Plane:`), and the string table the HUD draws from |
| `pcsx2_headless_boot.ps1` | boot a disc headlessly and print PASS/PARTIAL/FAIL |
| `pcsx2_ctl.ps1`, `post_keys.ps1` | window enumeration, PrintWindow capture, input injection attempts (see the findings: none of it works here) |
| `door-mechanism.md`, `pcsx2-headless-FINDINGS.md` | the full write-ups, including the dead ends |

## Dead ends, so nobody repeats them

* `QT_QPA_PLATFORM=offscreen` cannot work: PCSX2 2.8.1 builds a real GS device and swapchain for
  every renderer, and offscreen supplies no window handle.
* Vulkan in a session with no desktop → `VK_ERROR_DEVICE_LOST` every ~30 s. **The game freezes
  while the harness still reports PASS.** Use the Software renderer.
* `PrintWindow` on the GS window returns pure black (no compositor in that session), so there are
  no emulator screenshots this way.
* `SendInput` is useless with no foreground window (`GetForegroundWindow()` is 0), and posted
  `WM_KEYDOWN` — even with a faked `WM_ACTIVATE`/`WM_SETFOCUS` — produces no observable effect.
  Drive the *game* (patch + PINE writes), not the host.
* PINE accepts one client at a time: a leftover watcher makes the next command time out.

## Paths

These scripts assume the original development layout (`F:\rando\S1\…` for discs and notes,
`F:\rando\S1\out\` for built images). Change the constants at the top of each file if yours
differs.
