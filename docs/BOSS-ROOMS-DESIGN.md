# Boss Rooms — design and hard constraints

The working "boss gauntlet". Start in the opening level turned into an enemy arena; its exit chains
into a sequence of boss rooms; each boss room is a level whose NPCs are replaced by that level's own
boss(es), aggressive on arrival; each exit leads to another boss room (order may be randomised).

This replaces the failed `boss_gauntlet` approach (bosses there were hidden/trigger-gated → empty
rooms). Verified by play-testing + probes in `docs/lab/`.

## The two hard rules (both learned by play-test failures)

1. **Model-safe only.** A creature can be placed in a level ONLY if that level already loads its
   model, or the level load HANGS (black screen + stuck LOADING bar — observed when a boss was put
   into masad, which does not load boss models). Therefore:
   - In a boss room, place only that level's OWN boss (its model is resident).
   - In masad (start), place only creatures masad already spawns: `Orenian Soldier1`, `Orenian
     Soldier2`, `Orenian Scout`, `Orenian Archer`, `Barbarian Fighter` (all `$Team:"hostile"`).
2. **Clean (non-pacified) slots only.** A swapped-in creature INHERITS the NPC placement's
   `+Action` list. If that list has `+Hidden`, `"turn hostile" 0`, `"wait for go"`, or
   `"show/hide" 0`, the creature stays hidden/passive — it will not aggro. So only overwrite
   peaceful placements that carry NONE of those pacifiers. Those spawn a free, aggressive enemy.

Hostility itself is intrinsic to the creature definition (`$Team:"hostile"` in `#Character Info`),
so a clean, model-safe swap aggros on arrival with no scripted activation.

## Size-preserving

`$Character` is rewritten inside its own field width (new name + space pad). Boss/enemy names only
replace NPC names whose field is wide enough (`len(new) <= len(old)`). Door destinations likewise
(`new + spaces + '"'`), declare-and-refuse on the exact bytes, read back after writing.

## The chain (verified feasible — docs/lab/probe_safe_bossrooms.py)

Model-safe boss rooms (own boss fits a clean slot): `IonaExt02` (Luminar), `rand-hills01` (Phoenix
Rider), `sewerboss` (Tentacle Beast), `TempleInt` (Luminar/Machival/Pyrul/Tiger Rider/Titus — 30
clean slots). masad legally reaches IonaExt02 / sewerboss / TempleInt; the rooms inter-link; TempleInt
is terminal (reaches none → natural finale). The chain starts at masad and visits boss rooms until it
can't legally continue. Order among rooms may be seeded/random.

## Scope / honesty

These are boss-type ENEMIES (model, stats, hostility), not the full scripted boss encounters with
intros/stages — which is exactly "walk into a room of fightable bosses". Door hops are legal
(name-width + arrival slot + script-safe) but some reuse overworld doors; label EXPERIMENTAL until
play-verified. masad as an enemy arena means the normal story can't be completed on this disc — it is
a dedicated gauntlet, by design.

## Probes

`probe_npc_to_boss.py` (hostility is in the def, names fit), `probe_clean_npc.py` (clean slots per
level), `probe_safe_bossrooms.py` (model-safe rooms + chain + reachability from masad),
`probe_masad_safe.py` (masad's loaded hostiles + non-story NPCs), `probe_aggro.py` (pacifier actions
block aggro).
