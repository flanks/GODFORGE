# GODFORGE — Content Pipeline

> §14: *"Data-driven content (RON/JSON/TOML): chassis, parts, boons, enemies, rooms, drops. Balance via
> spreadsheets → CI-validated import."* · §20.2: *"No hardcoded weapon/boon/enemy stats."*
> §20.10: *"Adding a character must require zero code changes beyond ability scripts."*

## 1. Where content lives

```text
content/sheets/*.csv              ← designers edit these (spreadsheet-friendly, one row per thing)
        │  gf-content import      (typed parse → normalize → validate → re-serialize)
        ▼
assets/content/generated/*.ron    ← generated, committed, never hand-edited (CI checks they're in sync)
assets/content/*.ron              ← hand-authored structured data (tuning, kits, rooms, bosses, biomes)
        │  ContentDb::load_dir    (typed load → cross-reference validation → FNV-1a content hash)
        ▼
host sim + clients                ← the hash is exchanged in the network handshake: mismatched data can't join
```

| Sheet (`content/sheets`) | Generated table | Rows |
|---|---|---|
| `characters.csv` | `characters.ron` | 12 (8 playable at EA, 4 post-1.0) |
| `character_trees.csv` | `trees.ron` | 240 (30 per EA character) |
| `chassis.csv` | `chassis.ron` | 24 |
| `parts.csv` | `parts.ron` | 130 |
| `boons.csv` | `boons.ron` | 116 (100 + 16 duos) |
| `gods.csv` | `gods.ron` | 8 |
| `recipes.csv` | `recipes.ron` | 72 named combos |
| `synergies.csv` | `synergies.ron` | 12 |
| `enemies.csv` | `enemies.ron` | 44 |
| `chaos_tiers.csv` | `chaos_tiers.ron` | 20 |
| `party_scaling.csv` | `party_scaling.ron` | 4 |
| `forge_altar.csv` | `altar.ron` | 120 Altar of Ember nodes |
| `achievements.csv` | `achievements.ron` | 120 |
| `barks.csv` | `barks.ron` | 214 |

| Hand-authored (`assets/content`) | What |
|---|---|
| `game.ron` | Global tuning: movement, revive, Overdrive, synergy window, forge rules, rarity, status, anvil, drops, run economy, Echo, camera, VFX budget, P1–P4 colours |
| `aim_modes.ron` | The AUTO / ASSISTED / MANUAL balance contract (one row each) |
| `kits.ron` | Character kits: passive + 2 actives + ultimate as **ability step lists** (data, not code) |
| `bosses.ron` | Boss phase scripts: HP thresholds, telegraphed attacks, cadence |
| `rooms.ron` | Room templates: bounds, obstacles, spawn zones, exits, anvil spot, encounter budget, decor |
| `biomes.ron` | Biome palettes, spawn tables, mini-boss/boss, room sequence, anvil guarantees |

## 2. Commands

```sh
cargo run -p gf_tools -- import            # sheets → generated RON (validated; refuses to write on errors)
cargo run -p gf_tools -- import --check    # CI: fail if generated files are stale or content is invalid
cargo run -p gf_tools -- validate          # full report; --strict also fails on warnings (EA scope floors)
cargo run -p gf_tools -- audit [--write]   # 100-hour audit → docs/HUNDRED_HOUR_AUDIT.md
```

## 3. Sheet conventions

* Headers are dotted field paths: `stats.max_hp`, `stats.move_speed`.
* Cell kinds per column: plain string · optional string (empty = default) · raw RON (`Element(Flame)`,
  `(1, 3)`) · string list (`flame; bolt`) · raw list (`Element(Flame); Pierce(1)`).
* Keys are `lower_snake_case` and unique per table. Other tables reference rows **by key**, and ids are
  assigned at load, so reordering rows is safe.
* Every row has a `phase` (`P0` prototype · `P1` vertical slice · `EA` · `V1`). The sim filters by the
  build's phase, so content for later milestones can land early without leaking into the demo.
* Errors name the file, row and column: `parts.csv row 14, column mods: …`. Output is re-serialized
  from typed structs, so formatting is canonical and diffs stay reviewable.

### The modifier vocabulary

Parts, boons, chassis innates, recipe bonuses and tree nodes all speak one language:
`gf_core::modifier::Modifier`. A few examples:

```ron
Element(Flame)          Style(Bolt)            Pierce(2)              Projectiles(2)
FireRate(0.15)          Damage(0.25)           CritChance(0.1)        Ricochet(bounces: 2, range: 5.0)
Chain(jumps: 2, range: 4.5, falloff: 0.65)     ApplyStatus(status: Burn, chance: 0.35, stacks: 1, duration: 3.0)
Explode(radius: 1.6, damage: 0.5)              Orbit(count: 3, radius: 1.8, speed: 3.0, damage: 0.4)
```

Rarity scales a modifier's magnitude (`game.ron: rarity.magnitude` = 1.0 / 1.3 / 1.65 / 2.1), so one
part row produces all four tiers. The validator enforces slot identity:

* every Core sets an `Element`;
* Mechanisms and Relics may never change it;
* orbiting blades belong to Mechanisms;
* Sigils (god-souls) may carry anything.

## 4. What validation guarantees

It runs on import, on every load (the game refuses to start on errors) and in CI.

* **Referential integrity**: signature chassis, sigils, boon gods and requirements, recipe ingredients,
  enemy biomes and boss scripts, room and biome spawn tables all resolve.
* **Design rules as code**, including:
  - no player out of the fight > 30 s
  - AUTO's tax ≈ 10 % and it must auto-fire
  - MANUAL has zero magnetism
  - one Legendary per god
  - duo boons need two gods and require a boon from each
  - recipes need ≥ 2 ingredients in distinct slots and are unique
  - synergies pair distinct elements and have no duplicate pairs
  - boss phases are ordered by HP threshold
  - Chaos Tiers are contiguous
  - party scaling is monotonic
* **Scope floors (§15)** as `--strict` warnings: ≥ 8 characters, 16 chassis, 120 parts, 100 boons +
  16 duos, 80 achievements, 3 biomes at EA. Current content passes all of them.

## 5. Recipes

| Task | Steps | Code? |
|---|---|---|
| **New part** | Add a `parts.csv` row (slot, phase, mods, desc). Run `import`. | none |
| **New named combo** | Add a `recipes.csv` row: ingredients (`Chassis("key")`, `Part("key")` or `Element(Flame)`), bonus mods, codex text. | none |
| **New boon / duo** | Add a `boons.csv` row with kind, god(s), requirements and mods. | none |
| **New enemy** | Add an `enemies.csv` row: class, behaviour, stats, shape hint, colour, pack size. Add it to a biome spawn table. | none |
| **New room** | Add a `rooms.ron` entry: bounds, obstacles, spawn zones, exits, encounter budget, decor. | none |
| **New character** | Add a `characters.csv` row, 30 `character_trees.csv` rows and a `kits.ron` kit (ability steps). | none, unless a kit needs a *new* step type |
| **New ability step type** | Add an `AbilityStep` variant in `gf_content::schema` and implement it once in `gf_sim::abilities`. | one match arm |
| **New boss** | Add a `bosses.ron` script (phases → attacks from the shared attack set) and an `enemies.csv` row. | none |
| **Balance pass** | Edit sheet numbers, `import`, then `godforge --bot-run` to compare DPS / clear times. | none |

Kits are how roster growth stays content work (§20.10). All 8 EA characters are expressed with 17
reusable ability steps:

`Leap`, `Blink`, `Rush`, `Nova`, `Line`, `Cone`, `ChainBurst`, `Barricade`, `Turret`, `Buff`, `Field`,
`Taunt`, `Shield`, `RewindWounds`, `TimeStop`, `RefillDash`, `NextShots`

There are also 4 passive archetypes: armor conversion, static charge, ghost step, and plain modifiers.

## 6. Art assets (Blender 5.x → glTF)

Content rows already carry art keys (`EnemyDef.shape` and `key`, `ChassisDef.key`, `CharacterDef.skins`).
The contract for the export step:

| Asset | Path | Notes |
|---|---|---|
| Character | `assets/models/characters/{key}.glb` | master skeleton; clips `{key}_{clip}@loop` |
| Skin | `assets/models/characters/{key}__{skin}.glb` | same skeleton |
| Chassis | `assets/models/chassis/{key}.glb` | `muzzle` empty for VFX anchoring |
| Enemy | `assets/models/enemies/{key}.glb` | falls back to the `shape` greybox when missing |
| Props/decor | `assets/models/props/{decor}.glb` | `LavaCrack`, `BrokenAnvil`, `Brazier`, `Pillar` |

CI (P2) runs `blender -b -P tools/blender/export.py --validate`. It rejects meshes over budget,
missing clips or bad weights. The client resolves models by key and falls back to greybox, so
content and art ship independently.

## 7. Change control

* `import --check` in CI makes the generated RON the reviewed artifact. Designers see the exact data diff.
* The content hash in the handshake means host and clients must run identical data.
* Weekly seeds pin both the build and the content hash, and the leaderboard validates both.
