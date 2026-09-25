# GODFORGE: the enemy contract

Every enemy row in `content/sheets/enemies.csv` ships as **one rigged model named after its `key`**:
`assets/models/enemies/<key>.glb`. The `shape` column (Crawler, Spire, Colossus, ...) stays as the
greybox fallback. As with weapons, there is no human artist. Enemies are built from code with
`tools/blender/gf_assets` and the user approves the result. The rig path (GF_Swarm_v1, rigid skin,
the six clips, export and validation) is proven end to end by
`tools/blender/gf_assets/examples/swarm_example.py`.

The concepts come from the user's enemy pack (The Unmade and the Fallen Godworks). Its rules apply to
everything here:

* **Tier silhouette hierarchy**: swarm < elite < mini-boss < boss (section 3).
* **Two factions**, each with its own materials and glow (section 4).
* **Faction glows only**: teal for the Unmade, cold gold for the Godworks. **Never the player colours**
  (gold `#FFC940`, cyan `#3FD8FF`, violet `#B06CFF`, green `#5BE37D`) as accents.
* **Damage telegraphs are red-white and drawn by the engine** as decals and blinks. A model never
  carries red-white.

The numbers on this page also live in `tools/blender/gf_assets/gfa_spec.py`.

## 1. What ships

| File | What |
|---|---|
| `assets/models/enemies/<key>.glb` | rigged glTF binary (+Y up, uncompressed), one mesh, one material (base colour + emissive), clips `{key}_{clip}` |
| `assets/models/enemies/<key>.meta.json` | `kind, key, tier, tris, textures, sockets, clips, skeleton, status: ai_final_pending_user_approval`, bounds, sha256 |
| `art/enemies/<key>/` | `README.md` (brief + decisions), `status.json`, `source/<key>.blend`, `textures/`, `reports/<key>_review.png` |
| `tools/blender/gf_assets/enemies/<script>.py` | the build script (one script may build a base and its variants) |

## 2. Axes, origin, size

* In Blender: 1 unit = 1 m, Z up. The creature **faces -Y** and its left is +X. The origin is on the
  ground (z = 0) under the body centre. The glTF export maps the facing to **+Z** (the glTF front).
* The engine turns meshes with `yaw(angle)` (`palette.rs`), which assumes forward = world -Z. An enemy
  scene therefore needs **`yaw(angle) * Quat::from_rotation_y(PI)`**, which equals
  `Quat::from_rotation_y(angle + FRAC_PI_2)`.
* **Author at final in-game size.** The client places the scene with a unit scale. The `radius` and
  `scale` columns size the collider and the greybox. A model's footprint should be about
  2.2-3 × `radius × scale` (swarms may overlap their neighbours, which reads as a horde). The size is
  recorded in meta.json (`bounds_m`, `size_m`), so the client can fit a model that is off.
* Clips play **in place**. The sim moves the entity; `root` only bobs, drops and tilts.

## 3. Tier hierarchy (hero = 2.2 m)

| Tier (`gfa_spec`) | Height vs hero | Silhouette rule | Triangles | Texture | Rig |
|---|---|---|---|---|---|
| `enemy_swarm` | 0.2-0.5× (never above the waist) | ONE shape verb, read in < 1 s | **600-1,500** (400 on screen) | 512 (≤ 1024) | GF_Swarm_v1 |
| `enemy_elite` | 1.1-1.35× (player + 20 %) | ONE big gimmick that shows in the outline | 4,000-8,000 | 1024 | dedicated, shared clip names |
| `enemy_miniboss` | 1.7-2.4× (2× player) | a unique verb | 10,000-20,000 | 1024-2048 | dedicated |
| `enemy_boss` | 3-9× (a monument, 30-40 % of the arena) | multi-part body; readable phases | 20,000-40,000 | 2048 | dedicated |

Worked sizes for the three concepts:

| Key | Row (radius × scale) | Model |
|---|---|---|
| clinker | Swarm, 0.26 × 0.8 | about 0.7 m long, 0.5-0.6 m tall hunched (the "large dog"), footprint about 0.6 m |
| forge_warden | Elite, 0.75 × 1.2 | 2.6-2.7 m tall; the halo shield is about 1.5 m across and dominates the outline |
| slag_king | Boss, 2.2 × 2.4 | 11-13 m tall, about 10.5 m footprint (the Cinder Throne arena is 48 × 34 m, and the view shows 22-28 m of height) |

## 4. Faction materials

Hex values are sRGB. "shadow / base / light" are the painted value planes (`gfa_paint.faction_zone`),
and "rim / hot / core" are the glow ramp.

**THE UNMADE** is chaos anti-life: cracked obsidian shells, wet ichor, fused flesh and mineral, wrong
asymmetric geometry. Its glow is **toxic teal** `#2FBFA8`. Use `#7CFF6B` only as a small hot core,
because it sits close to the P4 green `#5BE37D`.

| Material | shadow | base | light | glow rim / hot / core |
|---|---|---|---|---|
| obsidian (shell) | `#07060A` | `#1A1720` | `#4B4658` | |
| obsidian_wet (sheen) | `#0B0E12` | `#20262C` | `#7FA7A0` | |
| ichor | `#0D3B35` | `#1F8F7E` | `#8FF2D8` | `#1F8F7E` / `#2FBFA8` / `#B8FFE8` |
| bone (inner shell) | `#6E6152` | `#BDB09A` | `#EDE4CF` | |
| slag | `#0C0908` | `#231A17` | `#4E3A30` | |
| molten (Slag King) | `#7A1E05` | `#FF6B1A` | `#FFC24B` | `#C8400C` / `#FF6B1A` / `#FFF3D6` |

How to paint the Unmade:
* obsidian gets big faceted value planes (`planes` 0.1-0.14) and bright, broken edge strokes;
* cracks are line decals (`crack_lines`) with a burnt dark rim, glowing teal (`emit`);
* the "wet" look is a few painted light streaks along the drip direction (`stroke`), not specular;
* asymmetry lives in the geometry: limbs 3 + 1, a lopsided shell.

**FALLEN GODWORKS** are corrupted divine war-machines: faded god-gold bronze, cracked porcelain masks,
broken runes. Their glow is **cold gold** `#D4B45A`, fading to dead ember `#8A3A1E`.

| Material | shadow | base | light | glow rim / hot / core |
|---|---|---|---|---|
| god_bronze | `#4A3A1E` | `#9C8045` | `#D4B45A` | |
| porcelain | `#8C877E` | `#D9D3C6` | `#F6F2E8` | |
| verdigris (shadow, cavities) | `#10201C` | `#2E4A40` | `#5E8374` | |
| cold_gold_glow | `#5A4A20` | `#D4B45A` | `#F4E6B0` | `#8A6A28` / `#D4B45A` / `#FFF4D0` |
| dead_ember | `#2A0E08` | `#8A3A1E` | `#C8663A` | `#4A1A0C` / `#8A3A1E` / `#E08A50` |

How to paint the Godworks:
* verdigris is the cavity and contact-shadow hue on bronze (give the bronze zone `shadow = #2E4A40`);
* porcelain gets hairline cracks: dark `crack_lines` with no emission;
* broken runes are `rune_band(..., broken=0.4)` decals glowing cold gold;
* the gold is **faded**. Keep it below the saturation of the player gold `#FFC940` and never use a
  warm, saturated gold.

Lessons from the forge_warden art review (judge them through the 55° camera at 1x):
* **One bright metal per enemy.** Keep the body plates at dark bronze (about `#5E5034`) with verdigris
  shadows and patina. Paint the body's gold accents as a dull old-gold trim (about `#86703F`). Only the
  signature shape (the halo) and the focal glows (mask, heart) stay bright. When the body and the
  signature shape share a value, they merge from above.
* **Runes at game size:** paint a few big strokes (2 strokes per glyph, lines about 0.024 m wide), at
  cold-gold value (`#C9AA56` line with a dim emission, core about `#6E5626`), on a dark surface. Small
  runes with a white-gold core turn into white speckle. Never put runes on the surfaces that face the
  camera (pauldron tops) or on the bright halo.
* **Hollow reads need one big gap the camera sees.** A thin gap around a floating helm vanishes at 49
  px/m. Tear one opening of 0.3-0.5 m where the 55° camera looks down into the void, and put the glow
  in it.

## 5. GF_Swarm_v1, the shared swarm skeleton

Six bones, identical in every swarm file, so a swarm clip can drive any swarm scene (Bevy builds
animation targets from bone-name paths). The armature object is always named `GF_Swarm_v1`.

| Bone | Parent | Pivot | Drives (rigid groups) |
|---|---|---|---|
| `root` | - | ground under the body centre | bob, drop, tilt of the whole creature |
| `body` | root | centre of mass | shell / torso |
| `head` | body | neck / jaw hinge | head, jaw, maw, front mass |
| `legs_a` | body | body centre (or hip line) | gait group A: every limb that swings in phase A |
| `legs_b` | body | same | gait group B: the other limbs |
| `tail` | body | where the rear mass hinges | abdomen, tail, back shards, trailing sac |

* **Rigid skinning.** Each part belongs to exactly one bone at weight 1.0
  (`gfa_model.Assembly(bones=...)`, then `gfa_rig.skin_rigid`). A creature without a tail leaves `tail`
  unweighted; the bone still exists.
* **Gait groups.** A tripod gait (L1 + R2 + L3 against R1 + L2 + R3) reads as SKITTER at 6 % of the
  screen. A hound can trot with its diagonal pairs; a blob squashes body and head and leaves the legs
  empty.
* **Rest orientation.** Every bone points straight up with roll 0, so all bones share one local
  frame: **X = the creature's left, Y = up, Z = forward**. glTF keeps these bone axes, so the exported
  joints have identity rest rotations. Rotations are in degrees: **+X** pitches nose-down / folds
  forward, **+Y** yaws to the creature's left, **+Z** rolls the left side up.
* **Sockets** are empties parented to bones (`gfa_rig.add_socket`) and export as children of the
  joints. `hit_center` (on `body`) is **required**: hit VFX and damage numbers. Optional: `fx_core`
  (glow and death burst), `fx_mouth`, `attack_origin` (spit / projectile), `head_top` (status icons),
  `shield`.

### Clip set (all enemies, every tier)

Clips are named `{key}_{clip}`, and loops end in `@loop`. The first two below are loops; the rest are
one-shots.

| Clip | Swarm length | Notes |
|---|---|---|
| `idle@loop` | 1.2-2.0 s | breathing, jitter. Sampled every frame from a periodic pose, so it loops with no hitch |
| `move@loop` | one gait cycle, 0.3-0.6 s | the client scales playback by speed ÷ stride. A per-creature `move_cycle_m` in meta.json is welcome |
| `windup` | 0.3-0.6 s | the client time-stretches it to the sim's windup; ends on the loaded pose |
| `attack` | 0.3-0.7 s | lunge, bite, spit, bash; starts from the windup pose |
| `hit` | 0.2-0.4 s | a flinch that returns to rest |
| `death` | 0.5-1.0 s | collapse, ending in a held pose. Bursts and shatters are engine VFX at `fx_core`; parts may scale to 0 |

`gfa_rig.swarm_clip_set()` generates all six from a few amplitudes. Tune them per creature, or
replace clips with `cycle_clip` / `keyed_clip`. Extra clips are allowed (`clinker_skitter@loop` for a
panic run, for example) but never replace the required six. `gfa_validate.py` fails a GLB when a
required clip is missing or a clip is misnamed.

### Which swarm rows use GF_Swarm_v1

Every `Swarm` row does, whatever its greybox shape:

* Crawler: legs a/b as the tripod gait.
* Hound: diagonal pairs.
* Blob and Wisp: body squash, head bob, legs empty or used for dangling bits.
* Spire (slagspitter, spore_censer, stargazer, collapsar): body = base, head = top/emitter, tail = back.
* Brute swarm (vector).

## 6. Elites, mini-bosses and bosses

* A **dedicated rig** per enemy, with the armature named `GF_<PascalKey>_v1` (for example
  `GF_ForgeWarden_v1`). Humanoid elites reuse the GF_Hero_v1 core bone names (`root`, `pelvis`,
  `spine_01..03`, `neck`, `head`, `upperarm_L/R`, ...), so hero clips can be retargeted later. Props
  get their own bones (`shield`, `spear`, `crown`). Every runtime bone is `use_deform = True`, or the
  exporter drops it.
* The **same clip names** as the swarm set (the six required) plus the enemy's extras:
  * elites add `cast` for Support / ability pulses;
  * bosses name attack clips after the `assets/content/bosses.ron` attack variant in snake_case
    (`slam_trail`, `strike_circle`, `strike_cone`, `strike_line`, `radial`, `pools`, `summon`), so the
    client can map attack kind to clip without a table;
  * boss phase changes are `phase2`, `phase3` (one-shots). Phase-specific loops add a suffix:
    `idle_p2@loop`, `move_p2@loop`.
* Geometry that only appears in a later phase lives in the same GLB on its own bones. It is scaled to
  0 in the earlier phases' clips, and the phase-change clip scales it up.

## 7. The three concepts, mapped to content keys

### E1 Shardling → `clinker` (Swarm, Cinder Wastes, Unmade), base of the crawler family

* **Verb: SKITTER.** A hunched, eyeless, infant-like figure fused into a cracked obsidian carapace. The
  limbs are wrong and asymmetric: three on one side, one on the other. The jaw is a vertical split with
  teal light inside. Ichor weeps from the cracks, and a pale bone inner shell shows at the seams.
* **Rig: GF_Swarm_v1.** The three left limbs form one side, the single right limb the other. Split them
  into gait groups: `legs_a` = L1 + L3, `legs_b` = L2 + R1. The lone right limb swings with the middle
  left one, so the gait alternates but the creature still limps wrong. The
  jaw halves go on `head`, and the back shell plates on `tail` so they rattle.
* **Clips:** idle@loop (hunched crouch, twitching), move@loop (the charge skitter), windup (rear back,
  jaw splits), attack (lunge bite), hit, death (the shell cracks apart; the ichor burst is VFX at
  `fx_core`).
* **Colour:** obsidian black, wet sheen streaks, teal glow `#2FBFA8` from the cracks and the jaw, pale
  bone inner shell. Use the row colour `#9A5B3C` (slag brown) only as a faint warm tint in the shell's
  light plane, to keep it apart from the other variants.
* **Built (2026-09-25, `ai_final_pending_user_approval`).** There are four looks of this one key, one
  GLB each: `clinker.glb` (Shardling), `clinker_v1.glb` (Crested, mirrored), `clinker_v2.glb`
  (Brood-back) and `clinker_v3.glb` (Split-back, mirrored). All four have the same GF_Swarm_v1, sockets
  and clip suffixes, and their clips are named `{file_stem}_{clip}`. The client can pick one per spawn
  from meta.json `variant_set`; `clinker.glb` alone is complete. The `head` bone is the hinged half of the
  vertically split skull, and a yaw opens it into the glowing wind-up wedge. Build script:
  `tools/blender/gf_assets/enemies/clinker.py`. Brief, metrics and the 40-copy horde review:
  [art/enemies/clinker/README.md](../../art/enemies/clinker/README.md).
* **Art review fixes (7.5/10).** The lone arm is now a massive pale bone club, so the three-and-one
  asymmetry reads by value and mass at 35 px instead of as a symmetric tick. Every scute's rear lip
  carries a bright obsidian-light crest stroke (`#7F7278`), so the dark body separates from the Cinder
  floor instead of relying on the teal seams alone.

### The variant rule (cheap roster width)

The crawler family is **one base + three shell variants**. Each variant is a separate content key and
a separate GLB: `rotmite` (Verdant Ruin), `ticker` (Hollow Spire), `nullmite` (The Unmaking). There
is no runtime variant system.

* **Shared:** one build script (`enemies/crawler_family.py`, with a `VARIANTS` table), the same part
  list and topology, GF_Swarm_v1, the same socket names, the clip generator (with per-variant
  amplitudes), and the swarm budget and tier size.
* **Varied per variant:**
  1. proportions: part scales ±15-35 %, limb length, shell height, head size;
  2. shell dressing, still within the budget: rotmite gets a domed beetle carapace, ticker a brass
     watch-case shell with a dial face and a winding crown, nullmite a hollow, cracked void shell
     with nothing inside;
  3. palette. Rotmite and nullmite stay Unmade (obsidian and teal; rotmite tinted by its row colour
     `#7A6B2E`, nullmite by `#6B6385`). Ticker turns Godworks: faded bronze, porcelain dial, cold-gold
     glow;
  4. motion: tempo and amplitude (ticker moves in ticking steps, nullmite drifts).
* **Rule of thumb:** the same skeleton, clips and sockets make a variant; a new silhouette verb makes a
  new enemy.

### E2 Warden Husk → `forge_warden` (Elite, Cinder Wastes, Fallen Godworks)

* **Verb: THE WALL.** A corrupted war-construct 2.6-2.7 m tall. Heavy faded god-bronze plates hang
  over an **empty interior**. The helmet is a cracked porcelain god-mask with no face behind it, and
  cold gold leaks from the eye slits. **The gimmick in the outline is an oversized broken-halo round
  shield**, a fragment of a god's ring, on one arm. The other hand holds a shattered spear. Broken
  runes crawl over the armour.
* **Gameplay link.** The row is `Support(range 6, shield 60, interval 4)`: it wraps nearby Unmade in
  forge-shields. Add a `cast` clip (shield raised, runes flare) and a `shield` socket for the VFX.
* **Rig:** `GF_ForgeWarden_v1`, humanoid core names plus `shield` and `spear` bones; rigid plate
  skinning is fine, since the body is hollow armour.
* **Clips:** idle@loop (shield-up guard), move@loop, windup (shield raised for the bash), attack
  (shield bash), hit, death (the armour collapses inward with sparks; the mask cracks last), cast.
* **Colour:** faded god-bronze `#D4B45A`, cracked white porcelain, dead-ember glow, dark verdigris
  shadows. Budget 4-8k tris, 1024 px.
* **Built (2026-09-25, `ai_final_pending_user_approval`).** The shipped rig is `GF_ForgeWarden_v1`: 30
  bones, the 23 hero core bones plus `pauldron_L/R`, `core`, `mask_L/R`, `shield` and `spear`, all
  rigidly skinned. The shield drives the left arm, and the spear drives the right. Clips: `idle@loop`,
  `move@loop` (`move_cycle_m` 1.571), `windup`, `attack`, `hit`, `death` (the mask halves split last),
  `cast` (the halo is raised overhead) and the extra `shield_up`. The brief's `walk@loop`,
  `shield_bash` and `cast_shield` map to these through meta.json `clip_aliases`. Sockets: `hit_center`,
  `fx_core`, `head_top`, `shield` and `attack_origin`. It is 2.79 m tall (1.27 ×) with 7.5k tris. Build
  script: `tools/blender/gf_assets/enemies/forge_warden.py`, which adds `gfa_shell.py` (hollow thick
  shells) and `gfa_rig_dedicated.py` (dedicated rigs, IK and prop-driven arms, per-frame clip baking).
  Brief, metrics and review sheets: [art/enemies/forge_warden/README.md](../../art/enemies/forge_warden/README.md).
* **Art review fixes (2026-09-25, score 7/10).** Three must-fixes:
  - The body is repainted dark verdigris bronze with an old-gold trim, so only the halo ring, the mask
    and the heart stay bright.
  - The runes on the halo ring and the pauldrons are gone. The shield face carries six big two-stroke
    runes in cold gold instead.
  - The husk is split open down the sternum, so the game camera sees the void and the cold-gold heart.

  Before and after: `art/enemies/forge_warden/reports/forge_warden_review_fix.png`.

### E3 The Slag King → `slag_king` (Boss, Cinder Wastes, Unmade)

* **Verb: THE FURNACE THAT WALKS.** A hunched titan of fused slag, broken anvils and molten god-metal,
  11-13 m tall. Its crown is a ring of broken sword blades fused into a halo. Its face is a furnace door
  over a white-hot core.
* **Phases** (`assets/content/bosses.ron`):

  | Phase | Starts at HP | Attacks | Visual state |
  |---|---|---|---|
  | Molten Court | 100 % | SlamTrail, Strike(Circle, at_self), Radial | furnace door closed; molten drips; two arms |
  | Slagfall | 60 % | Pools, Summon(cinderling ×8), SlamTrail, Strike(Cone) | `phase2`: the door bursts, the core is exposed, molten limbs split into four arms, the blade crown spins |
  | Final Pour | 25 % | Strike(Line), Radial, SlamTrail, Pools | `phase3`: the core pours; the crown glows white |

* **Clips (built):** idle@loop (towering, door closed), move@loop, windup, attack, hit, death, phase2,
  phase3, idle_p2@loop, move_p2@loop, slam_trail (the anvil slams on the windup, the claw follows),
  strike_circle (the two-fisted ground pound), strike_cone (the anvil sweep), strike_line (the pour),
  radial (the crown sprays slag), pools (drips flung wide), summon (the furnace spits cinderlings),
  door_open / door_close, roar. Phase-2 twins: windup_p2, attack_p2, hit_p2, slam_trail_p2,
  radial_p2. The user's brief names are exported as aliases of the same actions: walk@loop,
  ground_pound, sweep, furnace_open, phase2_idle@loop, phase_transition.
* **Phase switching:** every clip keys every joint, so each clip carries its phase. Phase-1 clips hold
  `arm2_upper_L/R` at scale 0.001 and the door shut; `phase2` bursts the door and grows the arms;
  phase-2+ clips hold them. In phase ≥ 2 the client plays `<clip>_p2` when it exists, else `<clip>`.
  The crown spin is procedural: rotate the `crown_spin` joint about its local +Y after animation
  (75°/s in Slagfall, 150°/s in Final Pour). The Final Pour "white crown" is an emissive boost.
  Details: art/enemies/slag_king/README.md and meta.json `phase_switch`.
* **Rig:** `GF_SlagKing_v1`, 26 joints, rigid skin: `door` (bottom hinge), `crown` + `crown_spin`
  (tilted along the crown axis), four arm chains (`upperarm/lowerarm/hand_L/R`,
  `arm2_upper/lower/hand_L/R`), legs, `pelvis`, `spine_01/02`, `head`.
* **Colour:** slag black, molten orange `#FF6B1A`, forge gold `#FFC24B` (only inside the molten glow
  ramp), teal Unmade cracks `#2FBFA8`, white-hot core `#FFF3D6`. Built: 25.0k tris, 2048 px.
* **Art review fixes (2026-09-25, score 7/10).** Five must-fixes:
  - Figure/ground: the up-facing slag planes are lifted to the slag light `#5E4434`, the side planes
    part of the way. Edge strokes are brighter. The feet, shins and fists stand in a molten underglow:
    a dim red band over a hot orange line at the ground.
  - The crown and claw blades are dark sword steel, with a bright strip down each sharpened edge.
    Five crown swords and the two middle claw swords show a grip and a crossguard.
  - The limbs are a smooth-shaded `limb` zone with no facets and no triangle web of edge lines. They
    carry six bold molten or teal cracks.
  - Iron and steel are broad value planes with one brushy top-edge stroke, taken only from the part's
    own edges, and no streaks. The rivets are iron.
  - The furnace face scowls: its eye slits slope down to the centre under a V of iron brows, over a
    jagged mouth of interlocking iron fangs.

  Before and after: `art/enemies/slag_king/reports/slag_king_review_fix.png`.

## 8. Build workflow and checks

```text
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/<script>.py -- [--no-review]
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/<key>.glb
```

`gfa_render.review_enemy` writes `art/enemies/<key>/reports/<key>_review.png`. It contains a rest-pose
turnaround, a pose strip for every clip, the in-game camera beside a 2.2 m mannequin (1x, 3x and a
silhouette), the textures and the palette.

- [ ] The tier size and the one-verb silhouette read in the 1x in-game render beside the mannequin.
- [ ] Faction materials and glow are right; there are no player colours and no red-white.
- [ ] Swarm: GF_Swarm_v1 exactly (six bones, armature `GF_Swarm_v1`), rigid weights, `hit_center`.
- [ ] All six required clips are present, loops are `@loop`, and the names are `{key}_...`.
- [ ] Triangles and texture size are inside the tier budget; there is one material.
- [ ] `gfa_validate.py` prints OK, and meta.json says `ai_final_pending_user_approval`.
- [ ] Variants keep the skeleton, clips and sockets and change proportions, dressing and palette.
