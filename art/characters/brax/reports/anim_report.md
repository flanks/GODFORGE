# Brax, stage 4: animation on GF_Hero_v1

Made by AI (Claude) on 2026-09-25 with the automated Blender 5.2 chain `tools/blender/gf_hero/run_stage4.py`. Following
the user's decision, there is no animator and there are no Mixamo or ActorCore seeds. The clips are key poses written in
Python and solved every frame. The quality gates are the metrics and the review renders; the user's visual approval is
the one human gate left (`status.json` → `4_animation.items.user_visual_approval`).

**What exists now**
- **34 clips** on GF_Hero_v1, in [`production/brax_anim.blend`](../production/brax_anim.blend) (Git LFS). The file is
  the stage-3 rig file plus one action and one muted NLA track per clip.
- **24 shared clips**, valid for every hero on the master skeleton. They are baked per hero from the hero's landmark
  file and move speed, so Valdris and the others get them with no extra work.
- **10 unique clips** that sell Brax's kit.
- **1,079 frames** in total, 30 fps, in place. The 13 loops close by construction.
- **Planted feet slide at most 0.9 mm** (the walk's heel-to-toe roll; 0.0 mm in every other clip). The one exception
  is the Furnace Rush skid-charge, which slides on purpose.
- **The anvil_gauntlets wrist rule holds everywhere:** the wrist swings 0.00°, because the hands only twist.
- **The glTF export check passes:** 34 animations, correct names and durations, the root never moves, only the
  pelvis translates, the sockets never move, every loop's last sample equals its first, and the twist bones are baked.

The contract, naming and authoring model are in [`docs/art/GF_HERO_SKELETON.md`](../../../../docs/art/GF_HERO_SKELETON.md)
§8. The review sheets are in [`anim/`](anim/): one per clip plus three game-size boards. The raw numbers are in:
- [`anim/clips.json`](anim/clips.json): the clip manifest;
- [`anim/render_checks.json`](anim/render_checks.json): the mesh checks;
- [`anim/gltf_check.json`](anim/gltf_check.json): the export check.

## 1. Clip table

Loops are named `brax_<clip>@loop`, one-shots `brax_<clip>` (ARCHITECTURE §9). Frames are at 30 fps; a clip runs frames
/ 30 s and has frames + 1 samples. "upper" means the lower body stays on the combat stance, so `spine_01` and its
children layer over locomotion. The first and last frames of those clips are `idle_combat` frame 0, which makes them
additive-friendly. The event frames are also pose markers on each action.

| Clip (glTF animation) | Frames | Loop | Layer | Purpose | Plays for (sim state / ability) | Events |
|---|---|---|---|---|---|---|
| `brax_idle@loop` | 90 (3.00 s) | loop | full | relaxed breathing stance, weight drifting between the feet | alive, not moving, out of combat (no enemy near, no attack for 2 s; hub) | - |
| `brax_idle_combat@loop` | 32 (1.07 s) | loop | full | combat-ready stance: guard up, a light bounce on the knees | alive, not moving, in combat (enemies near or an attack in the last 2 s). Frame 0 is the reference pose of every upper-layer clip | - |
| `brax_walk@loop` | 28 (0.93 s) | loop | full | heavy walk, gauntlets swinging at the sides | moving at under about 55 % of move speed (stick partly pushed, slows); playback rate = speed / 1.80 m/s | - |
| `brax_run@loop` | 20 (0.67 s) | loop | full | brawler run: forward lean, gauntlets pumping in front of the ribs | moving within 45 deg of the aim at move speed; playback rate = speed / 6.2 m/s | - |
| `brax_strafe_left@loop` | 20 (0.67 s) | loop | full | side run to the hero's left, hips opened toward the travel, chest and guard kept on the aim | moving 45-135 deg to the left of the aim; playback rate = speed / 6.2 m/s | - |
| `brax_strafe_right@loop` | 20 (0.67 s) | loop | full | side run to the hero's right (the mirror of strafe_left) | moving 45-135 deg to the right of the aim; playback rate = speed / 6.2 m/s | - |
| `brax_backpedal@loop` | 18 (0.60 s) | loop | full | backpedal on the balls of the feet, guard up, weight forward | moving more than 135 deg away from the aim; playback rate = speed / 6.2 m/s | - |
| `brax_dash` | 8 (0.27 s) | - | full | the dash burst: a low shoulder-led lunge-glide, the lead gauntlet driving forward, the rear one trailing | the 0.16 s dash (MoverState.dash_left > 0); the client faces the hero along the dash for its duration | launch 1 |
| `brax_dash_recover` | 14 (0.47 s) | - | full | landing out of the dash: the lead foot plants, a heavy absorb, back to the guard | the first 0.45 s after a dash ends when the hero is not moving on (else blend into locomotion) | land 3 |
| `brax_fire_light` | 8 (0.27 s) | - | upper | generic light shot: the weapon hand thrusts along the aim and snaps back (recoil stays procedural) | each primary shot of a light chassis (fire_rate >= 2/s); Brax plays brax_jab_l / brax_jab_r instead | shot 2 |
| `brax_fire_heavy` | 16 (0.53 s) | - | upper | generic heavy shot: load back, both arms drive forward, the body takes the kick | a heavy / charged release (fire_rate < 1/s, charge release, splash chassis) | shot 7 |
| `brax_fire_charge@loop` | 24 (0.80 s) | loop | upper | holding a charge: rear hand loaded at the hip, braced, trembling with stored power | fire held on a Charge chassis (FireKind::Charge) until release (then fire_heavy) | - |
| `brax_hit_light` | 12 (0.40 s) | - | upper | a flinch: head snaps, the guard is knocked back, absorb, recover | PlayerFlags::HIT on a light hit (damage < 10 % max HP), layered over whatever plays | impact 1 |
| `brax_hit_heavy` | 26 (0.87 s) | - | full | a big stagger: blown back, the lead foot steps back, absorb low, step back in | PlayerFlags::HIT on a heavy hit (damage >= 10 % max HP or a stun); interrupts upper-layer clips | impact 1 |
| `brax_knockdown` | 30 (1.00 s) | - | full | blown off the feet: impact, a backward fall, the bounce, lying on the back | a knockback / launch strong enough to floor the hero (stun >= 0.8 s); holds its last frame until get_up | impact 1, ground 14 |
| `brax_get_up` | 36 (1.20 s) | - | full | from the back: sit up on the hands, roll onto one knee, push up into the guard | the knockdown's stun ends | stand 30 |
| `brax_death` | 48 (1.60 s) | - | full | the fatal blow: head snaps back, knees buckle to the ground, topples face down | LifeState::Downed begins (GameEvent::Downed); holds its last frame, then downed@loop (wraith look) | impact 1, knee 20, ground 36 |
| `brax_downed@loop` | 60 (2.00 s) | loop | full | the wraith drift: slumped, floating 0.35 m off the ground, limbs trailing, a slow bob | LifeState::Downed (the Soul-Tether wraith; moves at 45 % speed with no gait, the client adds the ghost material) | - |
| `brax_revive` | 40 (1.33 s) | - | full | pulled back into the body: a jolt, the feet slam down, crouch, rise into the guard | an ally completes the Soul-Tether revive (Downed -> Alive) | jolt 6, land 12 |
| `brax_reforge_in` | 45 (1.50 s) | - | full | forged anew: rises from a one-knee landing (fist planted), clashes the gauntlets, takes the guard | LifeState::Reforging ends: the hero reappears next to an ally | clash 28 |
| `brax_victory` | 60 (2.00 s) | - | full | the roar: a crouch, then one gauntlet thrust to the sky, chest out; holds the pose | the run is won (GameEvent victory / boss down, results screen); holds its last frame | roar 17 |
| `brax_ping` | 20 (0.67 s) | - | upper | a ping: the right arm points along the aim with the hand open, the head follows | the ping / marker input (party callout); the open gauntlet variant shows while the hand is open | ping 5 |
| `brax_interact` | 40 (1.33 s) | - | full | work the anvil: lean over and press both gauntleted fists onto it (knuckles down), then straighten | the interact input at an anvil / forge / shrine POI (PoiState use); 1.3 s | contact 12, release 26 |
| `brax_forge_hammer@loop` | 36 (1.20 s) | loop | full | hammering the anvil with the right fist, the left fist bracing the work | the forge / hub anvil upgrade (Forge screen open, hub idle at the anvil) | hammer_hit 8 |
| `brax_idle_signature@loop` | 120 (4.00 s) | loop | full | signature idle: rolls each shoulder, cracks the neck side to side, knocks the gauntlets together twice | alive and idle for 6 s or more (out of combat); in the hub and the character select | knock_1 86, knock_2 92 |
| `brax_jab_l` | 10 (0.33 s) | - | upper | lead jab: the left gauntlet snaps straight down the aim line and back | anvil_gauntlets strike (fire_rate 3/s), alternating with jab_r; the strike lands on frame 3 | hit 3 |
| `brax_jab_r` | 10 (0.33 s) | - | upper | rear straight: hips and the rear heel turn, the right gauntlet drives down the aim line | anvil_gauntlets strike (fire_rate 3/s), alternating with jab_l; the strike lands on frame 3 | hit 3 |
| `brax_hook` | 16 (0.53 s) | - | upper | lead hook: load to the left, the torso whips through, the left gauntlet sweeps across at head height | every third strike of a held string, and every strike at max Heat (ignite + stagger); lands on frame 6 | hit 6 |
| `brax_uppercut` | 48 (1.60 s) | - | full | Cinder Uppercut: coil low, a rising uppercut that launches, a hang, a double-fist slam into the ground | kits.ron brax active1 Cinder Uppercut: Nova (launch) on 'launch', Field (flame geysers) on 'slam' | launch 10, slam 25 |
| `brax_furnace_rush@loop` | 12 (0.40 s) | loop | full | Furnace Rush: head down behind both gauntlets like a ram, legs churning, very low | kits.ron brax active2 Furnace Rush while the Rush moves (8 m in 0.4 s = 12 frames); the enemy drag is sim-side | - |
| `brax_furnace_rush_end` | 18 (0.60 s) | - | full | the brake: the lead foot plants in a skid, both gauntlets shove the dragged line away, back to the guard | Furnace Rush ends (after 0.4 s): the drag releases on 'release' | plant 3, release 5 |
| `brax_meltdown_start` | 40 (1.33 s) | - | full | Meltdown ignition: gather low, a chest-out roar with the arms flung wide, the gauntlets slam together | kits.ron brax ultimate Meltdown cast: the buff starts on 'ignite', the clash is the shockwave VFX cue | ignite 13, clash 27 |
| `brax_meltdown@loop` | 24 (0.80 s) | loop | full | Meltdown stance: lower and wider, fists forward, a fast bounce and rolling shoulders | replaces idle_combat while the Meltdown buff lasts (8 s); strikes layer on top as usual | - |
| `brax_heat_vent` | 30 (1.00 s) | - | upper | Heat vent: shoulders thrown back, arms dropped wide, chest out, head back as the cracks vent | the Heat Gauge passive reaches max (attacks start to ignite); the steam / ember VFX sit on chest_sigil | vent 6 |

**Unique set (Brax, 10):** `idle_signature@loop`, `jab_l`, `jab_r`, `hook`, `uppercut` (Cinder Uppercut), `furnace_rush@loop`,
`furnace_rush_end`, `meltdown_start`, `meltdown@loop` and `heat_vent`. `hook` (the heavy strike) replaces the brief's
separate `cinder_slam`, because the slam lives inside `uppercut`: one ability, one clip, two event frames.
`furnace_rush_start` is the shared `dash` (a 0.16 s burst), so the rush clip itself is the loop the 0.4 s Rush plays.

## 2. How the clips are made

- **Solver** (`tools/blender/gf_hero/s4lib.py`). A key pose is a set of parameters:
  - FK angles;
  - the pelvis offset and a world rotation;
  - the fist's target, the elbow's pole point and the direction the back of the hand faces;
  - each foot's ball position on the ground, its yaw, heel roll and lift, and a knee hint;
  - a stabilised head;
  - the fist curl.

  Keys are interpolated in that parameter space with a Kochanek-Bartels spline: a tension per key (a held key is at
  rest), linear segments for snaps into contact, cyclic for loops. A channel that holds its value into or out of a key
  is at rest there, so a planted foot cannot drift on overshoot. Every frame is then solved with an analytic two-bone
  IK: the hinge is the lower bone's local X, the reach is soft, and a ground clamp keeps the toes up. The result is
  baked as LINEAR keys. The solver agrees with Blender's own evaluation of the baked actions to 8.5e-07 (every clip,
  3 frames each).
- **Locomotion** (`s4_clips.locomotion`) is procedural. During contact the feet move under the body at exactly the
  design speed; the swing is a Hermite curve whose end tangents match the ground speed. Heel-roll, lift and
  pelvis-bob curves set the gait. Frame 0 sits in the passing phase, so the loop seam is not on a footfall.

  | Clip | Design speed | Cycle | Duty | Notes |
  |---|---|---|---|---|
  | `run` | 6.2 m/s (Brax's `move_speed`) | 20 frames, 2 steps | 0.25 | 16° pelvis + 13° spine lean, pumping gauntlets |
  | `walk` | 1.8 m/s | 28 frames | 0.62 | heel strike, pelvis highest at mid-stance |
  | `strafe_left` / `strafe_right` | 6.2 m/s sideways | 20 frames | 0.24 | hips open 38° toward the travel, the chest counter-rotates to the aim, guard held |
  | `backpedal` | 6.2 m/s backwards | 18 frames | 0.30 | on the balls of the feet, weight forward |

  The engine sets the playback rate to `speed / design_speed` (in `clips.json`), and the feet then stay planted in the
  world at any speed.
- **Style.**
  - Every action has an anticipation, a contact and a follow-through, and weight shows in the pelvis. For example:
    - the uppercut coils 22 cm down and then rises onto the toes;
    - the slam drops the pelvis 50 cm;
    - `hit_heavy` steps the lead foot back and steps it in again.
  - The head is stabilised in world space while the body works, and goes limp (FK) in falls.
  - The guard holds both gauntlets up by the chin with the forearms parallel. From the 55° camera they frame the face;
    an earlier chest-height guard crossed the gauntlets into an X and read as crossed arms.
  - Every punch drives a gauntlet along the aim line, and the dash is shoulder-led, so a gauntlet leads the silhouette
    at every yaw.
- **Contacts.**
  - Planted feet keep their exact ball position. The feet always leave the ground to move: death, get up and the rush
    brake step or hop, they never skate.
  - The slam and forge fists land on points in absolute space: the ground, and one shared anvil top at 1.07 m, 0.58 m
    in front.
  - Knocks and clashes are spaced so that only the knuckle faces meet (at most 43 vertices touch). The exception is
    the `uppercut` double-fist slam, where the fists press together (up to 106 vertices, §3).
- **Gauntlet variants.** The fist or open variant follows the fingers. Only `ping` opens a hand: the right hand opens
  on frame 4 and closes on frame 16 (`clips.json` `weapon_variant`). Every other clip shows the fist variant, with the
  body's fingers clenched inside it.

## 3. Validation

> **Revised by the review of stages 3-5 (2026-09-26, [`review_stage3_5.md`](review_stage3_5.md)).** The first bake
> folded elbows to 173-179° (`dash`, `death`, `uppercut`: the gauntlet crushed into the shoulder, head or chest), a
> knee to 172° (`get_up`), and drove the gauntlets through thighs, knees, the chest and the belt between key frames
> (up to 416 solid-body vertices inside a gauntlet in `get_up`, 413 in `uppercut`). The "gauntlet cuts body" column
> below never saw it: it samples key frames only and counts vertices inside gauntlet material, not inside its cavity.
> The solver now has soft limits (elbow 145°, knee 150°) and the arm keep-out (`s4lib.KeepOut`), and three key poses
> moved (`get_up` GU2's free fist, `heat_vent`'s return through the front, the `uppercut` slam in front of the knees).
> The table is the re-bake. "Keep-out push" is how far the solver moved a fist target out of the body.

Every number comes from `reports/anim/*.json`. The chain re-runs everything with `python tools/blender/gf_hero/run_stage4.py brax`.

| Clip | Foot slide max (mm) | Loop seam | IK miss (mm) | Wrist swing (deg) | Elbow max L/R (deg) | Knee max (deg) | Keep-out push (max mm) | Gauntlet cuts body (max verts) | Gauntlets touch (max) | Lowest body / cloth vertex (mm) |
|---|---|---|---|---|---|---|---|---|---|---|
| `idle` | 0.0 | closed, 0.01 / 0.05 deg | 0.0 | 0.00 | 37 / 37 | 32 | 0 | 0 | 0 | 5.1 / 305.5 |
| `idle_combat` | 0.0 | closed, 0.50 / 0.50 deg | 0.0 | 0.00 | 93 / 102 | 61 | 0 | 32 | 0 | 5.1 / 352.5 |
| `walk` | 0.9 | closed, 6.91 / 14.57 deg | 0.0 | 0.00 | 48 / 48 | 75 | 0 | 6 | 0 | 5.1 / 126.2 |
| `run` | 0.0 | closed, 38.23 / 59.81 deg | 0.0 | 0.00 | 104 / 104 | 126 | 116 | 33 | 0 | -2.6 / 169.8 |
| `strafe_left` | 0.0 | closed, 9.00 / 27.64 deg | 3.7 | 0.00 | 90 / 100 | 117 | 0 | 32 | 0 | 5.1 / 293.7 |
| `strafe_right` | 0.0 | closed, 9.31 / 27.64 deg | 3.7 | 0.00 | 90 / 100 | 117 | 0 | 32 | 0 | 5.1 / 193.9 |
| `backpedal` | 0.0 | closed, 19.11 / 31.14 deg | 0.8 | 0.00 | 89 / 99 | 109 | 0 | 30 | 0 | 5.1 / 115.0 |
| `dash` | 0.0 | - | 0.0 | 0.00 | 91 / 130 | 120 | 231 | 31 | 0 | 5.1 / 174.4 |
| `dash_recover` | 0.0 | - | 0.0 | 0.00 | 95 / 114 | 113 | 254 | 36 | 0 | 5.1 / 174.4 |
| `fire_light` | 0.0 | - | 0.0 | 0.00 | 91 / 100 | 56 | 0 | 31 | 0 | 5.1 / 356.2 |
| `fire_heavy` | 0.0 | - | 0.0 | 0.00 | 103 / 110 | 56 | 89 | 37 | 0 | 5.1 / 356.0 |
| `fire_charge` | 0.0 | closed, 0.92 / 0.92 deg | 0.0 | 0.00 | 78 / 118 | 62 | 138 | 35 | 0 | 5.1 / 352.3 |
| `hit_light` | 0.0 | - | 0.0 | 0.00 | 108 / 100 | 56 | 0 | 38 | 0 | 5.1 / 356.1 |
| `hit_heavy` | 0.0 | - | 0.0 | 0.00 | 138 / 126 | 90 | 0 | 54 | 0 | 5.1 / 190.5 |
| `knockdown` | 0.0 | - | 2.8 | 0.00 | 121 / 118 | 144 | 0 | 40 | 0 | 5.1 / -91.4 |
| `get_up` | 0.0 | - | 0.0 | 0.00 | 111 / 113 | 150 | 282 | 36 | 0 | 0.8 / -97.7 |
| `death` | 0.0 | - | 0.0 | 0.00 | 108 / 133 | 150 | 351 | 35 | 0 | -3.8 / -230.5 |
| `downed` | 0.0 | closed, 0.10 / 0.10 deg | 0.0 | 0.00 | 44 / 45 | 140 | 0 | 6 | 0 | 156.5 / 237.0 |
| `revive` | 0.0 | - | 0.0 | 0.00 | 117 / 121 | 140 | 61 | 39 | 0 | 5.1 / 191.8 |
| `reforge_in` | 0.0 | - | 0.0 | 0.00 | 115 / 119 | 137 | 173 | 44 | 42 | -3.4 / -79.1 |
| `victory` | 0.0 | - | 0.0 | 0.00 | 118 / 122 | 75 | 102 | 35 | 0 | 5.1 / 304.3 |
| `ping` | 0.0 | - | 12.3 | 0.00 | 91 / 101 | 56 | 0 | 33 | 0 | 5.1 / 356.3 |
| `interact` | 0.0 | - | 0.0 | 0.00 | 105 / 105 | 64 | 0 | 36 | 43 | 5.1 / 276.3 |
| `forge_hammer` | 0.0 | closed, 8.64 / 19.37 deg | 0.0 | 0.00 | 85 / 122 | 64 | 100 | 33 | 26 | 5.1 / 361.4 |
| `idle_signature` | 0.0 | closed, 0.19 / 12.13 deg | 11.1 | 0.00 | 93 / 93 | 29 | 69 | 27 | 21 | 5.1 / 304.0 |
| `jab_l` | 0.0 | - | 0.0 | 0.00 | 101 / 103 | 60 | 0 | 32 | 0 | 5.1 / 356.3 |
| `jab_r` | 0.0 | - | 0.0 | 0.00 | 104 / 113 | 73 | 0 | 37 | 0 | 5.1 / 356.3 |
| `hook` | 0.0 | - | 0.0 | 0.00 | 116 / 110 | 69 | 60 | 41 | 0 | 5.1 / 354.3 |
| `uppercut` | 0.0 | - | 54.7 | 0.00 | 127 / 126 | 133 | 286 | 37 | 106 | 3.4 / -25.9 |
| `furnace_rush` | 1200.2 (exempt) | closed, 65.67 / 65.67 deg | 0.0 | 0.00 | 98 / 102 | 127 | 0 | 32 | 0 | 4.4 / 100.3 |
| `furnace_rush_end` | 0.0 | - | 0.0 | 0.00 | 95 / 100 | 108 | 0 | 31 | 0 | 2.6 / 100.3 |
| `meltdown_start` | 0.0 | - | 0.0 | 0.00 | 130 / 129 | 89 | 121 | 44 | 39 | 5.1 / 231.3 |
| `meltdown` | 0.0 | closed, 0.69 / 0.93 deg | 0.0 | 0.00 | 82 / 93 | 89 | 0 | 29 | 0 | 5.1 / 231.3 |
| `heat_vent` | 0.0 | - | 0.0 | 0.00 | 116 / 123 | 56 | 238 | 44 | 0 | 5.1 / 356.2 |

How to read the columns:
- **Foot slide**: the largest world-space drift of a ball joint inside one contact interval. The design travel is added
  back for locomotion. For `furnace_rush`, the 1,200 mm is the skid-charge by design (§6).
- **Loop seam**: the last frame minus the first is 0.0000° and 0.000 mm in every loop. The two numbers are the
  largest second difference (deg per frame²) through the seam against anywhere inside the clip. The seam is never the
  roughest point.
- **IK miss**: a target the limb cannot reach, which the soft IK eases. The largest are the full extensions in the
  uppercut launch (55 mm) and in the signature idle's hanging arms (32 mm). All are under the 60 mm gate.
- **Keep-out push**: the largest move of a fist target out of the body by the arm keep-out (`clips.json`
  `keepout_push`; `keepout_residual_verts_max` is what still overlaps, gated at 60 per arm). 0 means the clip was
  clean as written.
- **Gauntlet cuts body**: body vertices inside gauntlet material on the key frames, the weapon's own forearm and hand
  excluded. The 21-44 vertices are almost all the known elbow cuff pressing into the biceps (15-27 a side)
  whenever the elbow bends past about 40° (§6). Every frame, and the gauntlet cavity too, is measured by the review's
  audit (`tools/blender/gf_hero/review/`): after the re-bake at most 61 solid-body vertices sit inside a gauntlet
  (`get_up` f15, the right gauntlet against the tucked right leg), 0 in 29 of the 34 clips.
- **Gauntlets touch**: at the `uppercut` slam the two fists press together (50-106 vertices of one shell inside the
  other on the slam frames): a double-fist slam. Before the review they sat on the knees instead.
- **Lowest vertex**: the body set (skin, wraps, hair, beard, belt) and the rigid cloth (skirt plates, sash, underskirt)
  are reported separately. The body stays within 4 mm of the ground in every clip. The cloth goes through the ground
  only in the lying and kneeling poses (§6).
- **Pelvis drift** (horizontal, from the origin):
  - at most 30 mm in locomotion, the idles, the strikes and the stance clips;
  - 50-113 mm where the body shifts on purpose: the dash lunge, the reaches to the anvil, the `hit_heavy` stagger
    and the `reforge_in` landing;
  - 0.18 m in `death`;
  - 0.42 m in `knockdown` and `get_up`, because he lands on his back behind his feet.

  Only the pelvis carries it; the root never moves.

The glTF check passes (`anim/gltf_check.json`):
- 34 animations, named exactly as the manifest, with nothing unexpected;
- 9 to 121 samples at 30 fps;
- the root never moves, sockets never change, only the pelvis translates;
- every loop's last sample equals its first (0.0);
- the twist bones animate in all 34 clips (the Copy Rotation constraints are sampled);
- `extensionsRequired` is empty;
- the scratch GLB with the mesh and all clips is 10.1 MB.

The clip contract passes. `check_clips.py` also runs in CI as the job `hero-clips` in `.github/workflows/art.yml`.

## 4. What the sheets show (my review)

I looked at every clip sheet and the three boards (`anim/anim_board_{1,2,3}.png`).

- **Reads well at game size (65-86 px):**
  - the guard stance (the gauntlets frame the face);
  - the jabs and hook (a gauntlet thrust along the aim; clearest at yaw 90);
  - the Cinder Uppercut: the fist straight overhead at the launch, the crouched double-fist slam;
  - the Meltdown ignition (the arms-wide roar is the strongest silhouette in the set);
  - the Furnace Rush ram (head down behind both fists);
  - the shoulder-led dash;
  - knockdown, then lying on the back, then get up;
  - the one-knee collapse into a face-down death;
  - the wraith's hunched float;
  - the victory fist to the sky;
  - hammering at the anvil.
- **Reads but is quiet:**
  - `idle` and `idle_signature` are subtle, as idles should be. The gauntlet knocks at frames 86 and 92 are the one
    clear beat;
  - `hit_light` is a small flinch, and the engine's procedural flinch will carry more of it;
  - `fire_light`, `fire_heavy` and `fire_charge` are deliberately generic: a thrust or brace for any chassis.
- **The run** leans well and drives the knees. From the front (yaw 0) the pumping gauntlets sit at the hips and
  make the silhouette wide rather than dynamic. From the side (yaw 90) it reads as a sprint.

## 5. Mapping notes for the engine agent (`crates/` is not the art track's)

- **Locomotion blend:** choose from the angle between velocity and aim, using `run`, `strafe_left`, `strafe_right`
  and `backpedal`. `walk` plays below about 55 % of move speed. Set the playback rate to `speed / design_speed_mps`.
- **Upper-layer clips** (`fire_*`, `hit_light`, `ping`, `jab_l`, `jab_r`, `hook`, `heat_vent`): mask `spine_01` and its
  children over the current base clip.
  - Strikes alternate `jab_l` and `jab_r` at the chassis rate: 3 per second, and each clip is 10 frames.
  - `hook` is every third strike of a held string, and every strike at max Heat.
- **The dash** is authored facing the dash direction: turn the hero along `dash_dir` for 0.16 s, then play
  `dash_recover` or blend into locomotion.
- **Abilities.** Cinder Uppercut: Nova on the `launch` event (frame 10), Field on `slam` (frame 25). Furnace Rush:
  `furnace_rush@loop` for the 0.4 s rush, then `furnace_rush_end`, whose `release` event (frame 5) lets go of the drag.
  Meltdown: `meltdown_start`, then `meltdown@loop` replaces `idle_combat` for the 8 s buff.
- **Life states.**
  - `death` holds its last frame; `downed@loop` plays with the ghost material; `revive` or `reforge_in` returns to the
    guard.
  - `knockdown` holds its last frame until `get_up`.
- **Events** are pose markers in the `.blend` and are listed in `clips.json`. Stage 5 writes them to the GLB's sidecar
  (`assets/models/characters/brax.meta.json`); glTF has no events.

## 6. Honest findings and open issues

1. **The gauntlet cuff presses into the biceps** in every bent-arm pose: the guard, the strikes, the run pump. The
   cost is 15-27 vertices a side, and 21-44 per key frame in total. It is weapon geometry: the stage-3 report
   measured a clean elbow range of 0-30°. A brawler cannot keep his elbows that straight, so the clips accept the
   overlap. It is invisible at game size, but visible in the close-ups. The fix belongs to the weapon: end the sleeve
   about 4 cm before the elbow, or flare the cuff (`art/weapons/anvil_gauntlets`, the armory agent's pack).
2. **The rigid skirt plates and sash tails** follow the pelvis and thighs rigidly (stage 3). Consequences:
   - lying on the back (`knockdown`, `get_up`), the back plates go up to 9.8 cm into the ground;
   - face down (`death`), the front sash tails go 23 cm in;
   - kneeling (`reforge_in`), 8 cm;
   - with the knees high (run, dash, uppercut), the front sash crosses the thigh.

   The fix is the stage-3 follow-up already listed: secondary `x_` bones for the sash tails and skirt panels, driven
   by engine springs (shared clips never key `x_` bones), or a cloth pass. Clamping the cloth to the floor per frame
   could do in the meantime.
3. **Furnace Rush slides by design.** The Rush moves at 20 m/s (8 m in 0.4 s). No leg cycle can plant at that speed,
   so the legs churn at an 8 m/s stride and the feet slide 1.2 m per contact in the world: a skid-charge. The clip is
   marked `slide_exempt` and the contract lets it through. `furnace_rush_end` plants cleanly (0.0 mm): it hops out of
   the rush pose for 2 frames.
4. **Deep knee flexion shows the stage-3 knee flattening** past about 110°. The solver now stops a knee at 150°
   (it reached 172° in the `get_up` tuck, a crushed lump). The worst are:
   - the uppercut slam (133°);
   - `get_up` (150° in the tuck, at the limit);
   - the death kneel and the wraith float (140-150°).

   It is hidden by the skirt at game size. The uppercut slam's kneeling knee still sinks about 6 cm into the ground
   (the lowest skinned vertex, -60 mm).
5. **The fire clips are generic.** `fire_light`, `fire_heavy` and `fire_charge` are body-and-arm thrusts that any
   chassis can use. A two-handed gun's left hand still needs the engine's IK to `grip_L`, and recoil and aim stay
   procedural. **Aim offsets are not authored**: at the 55° top-down camera the hero turns to the aim, and the
   torso-versus-legs split is covered by the strafe and backpedal clips. A procedural spine yaw is cheaper if more is
   needed.
6. **Not verified in the Bevy client.** The clips were checked in Blender and in a read-back of the exported glTF only.
   Wiring them up is the engine agent's work, and stage 5 writes the shipped GLB.
7. **Retargeting** to a second hero is untested until Valdris is rigged. The shared set is built for it: every offset
   scales with the hero's leg and arm length, and the speed comes from `characters.csv`.

## 7. Rebuild

```sh
python tools/blender/gf_hero/run_stage4.py brax            # anim, render, sheets, gltf_check, contract (about 10 min)
python tools/blender/gf_hero/run_stage4.py brax --only anim  # re-bake the clips only (about 5 s)
```

To tune a clip, edit its keys in `tools/blender/gf_hero/s4_clips.py` (shared) or `s4_brax.py` (unique). Then run the
`anim` step, and `s4_render.py -- brax --only <clip>` for its renders.
