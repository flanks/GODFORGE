# Valdris, stage 4: animation on GF_Hero_v1

Made by AI (Claude) on 2026-09-26 with the automated Blender 5.2 chain `tools/blender/gf_hero/s4_valdris_run.py`, on
the stage-3 rig (`139c655`). Following the user's decision there is no animator and there are no Mixamo or ActorCore
seeds: the clips are key poses written in Python and solved every frame. The quality gates are the metrics, the
every-frame audit and the review sheets. The user's visual approval is the one human gate left (`status.json` →
`4_animation.items.user_visual_approval`).

**What exists now**
- **34 clips** on GF_Hero_v1 in [`production/valdris_anim.blend`](../production/valdris_anim.blend) (Git LFS): the
  stage-3 rig file plus one action and one muted NLA track per clip, named `valdris_<clip>[@loop]`.
- **24 shared clips**: the library's contract (names, loop flags, layers, events and timing structure of
  `s4_clips.py`), re-posed for his plate (§2).
- **10 unique clips** for his kit: the signature idle, Bulwark Slam, Siege Stance (enter, loop, exit, fire), Mountainfall
  (cast, loop, ground pound) and the Reforged Flesh armour break.
- **The cloth pass**: his cape (5 × 5 chains), loincloth (3 × 3) and braids (5 × 2) are keyed in every clip.
- **1254 frames** in total, 30 fps, in place. The 13 loops close by construction (the last frame is the first, cloth included).

The review sheets are in [`anim/`](anim/): one per clip and three game-size boards next to the concept. The numbers are
in [`anim/clips.json`](anim/clips.json) (the bake), [`anim/cloth.json`](anim/cloth.json) (the cloth pass),
[`anim/render_checks.json`](anim/render_checks.json) (the every-frame audit) and
[`anim/gltf_check.json`](anim/gltf_check.json) (the export read back).

## 1. Clip table

Loops are named `valdris_<clip>@loop`, one-shots `valdris_<clip>`. Frames are at 30 fps; a clip runs frames / 30 s and
has frames + 1 samples. "upper" clips keep the lower body on their base clip's stance, so `spine_01` and its children
layer over locomotion; their first and last frames are frame 0 of `idle_combat` (or of the base named in brackets).
The event frames are pose markers on each action and are listed in `clips.json`.

| Clip (glTF animation) | Frames | Loop | Layer | Purpose | Plays for (sim state / ability) | Events |
|---|---|---|---|---|---|---|
| `valdris_idle@loop` | 120 (4.00 s) | loop | full | relaxed heavy stance: slow deep breaths lift the pauldrons, the weight rolls between the feet, a slow look around | alive, not moving, out of combat (no enemy near, no attack for 2 s; hub) | - |
| `valdris_idle_combat@loop` | 40 (1.33 s) | loop | full | combat stance: planted wide, the cannon down the aim, a heavy breathing sink on the knees | alive, not moving, in combat (enemies near or an attack in the last 2 s). Frame 0 is the reference pose of every upper-layer clip | - |
| `valdris_walk@loop` | 28 (0.93 s) | loop | full | heavy walk: a wide rolling gait, the weight dropping onto each sabaton, the cannon swinging low | moving at under about 55 % of move speed (stick partly pushed, slows); playback rate = speed / 1.70 m/s | - |
| `valdris_run@loop` | 20 (0.67 s) | loop | full | juggernaut run: low and heavy, the pelvis sinks on every footfall, the cannon held down the aim, the fist pumping | moving within 45 deg of the aim at move speed; playback rate = speed / 5.6 m/s | - |
| `valdris_strafe_left@loop` | 18 (0.60 s) | loop | full | side run to his left: the hips open toward the travel, the chest and the cannon kept on the aim | moving 45-135 deg to the left of the aim; playback rate = speed / 5.6 m/s | - |
| `valdris_strafe_right@loop` | 18 (0.60 s) | loop | full | side run to his right (the chest and the cannon kept on the aim) | moving 45-135 deg to the right of the aim; playback rate = speed / 5.6 m/s | - |
| `valdris_backpedal@loop` | 18 (0.60 s) | loop | full | heavy backpedal: short driving steps, the weight forward over the cannon, the cannon on the aim | moving more than 135 deg away from the aim; playback rate = speed / 5.6 m/s | - |
| `valdris_dash` | 8 (0.27 s) | - | full | the dash burst: a low bull rush behind the anvil and both pauldrons, the cannon low and forward | the 0.16 s dash (MoverState.dash_left > 0); the client faces the hero along the dash for its duration | launch 1 |
| `valdris_dash_recover` | 16 (0.53 s) | - | full | out of the dash: the lead sabaton slams down, the rear one after it, a heavy absorb on both knees | the first 0.5 s after a dash ends when the hero is not moving on (else blend into locomotion) | land 3 |
| `valdris_fire_light` | 8 (0.27 s) | - | upper | a cannon shot: the muzzle kicks up, the shoulder and chest take it, the weight settles back (recoil stays procedural) | each primary shot of a light chassis (fire_rate >= 2/s): the colossus_cannon's 2.6 shots/s | shot 1 |
| `valdris_fire_heavy` | 18 (0.60 s) | - | upper | a heavy shot: brace into it, the cannon bucks up and drives the shoulder back, a slow settle | a heavy / charged release (fire_rate < 1/s, charge release, splash chassis) | shot 6 |
| `valdris_fire_charge@loop` | 24 (0.80 s) | loop | upper | holding a charge: braced into the cannon, the fist clenched, the barrel trembling with stored power | fire held on a Charge chassis (FireKind::Charge) until release (then fire_heavy) | - |
| `valdris_hit_light` | 12 (0.40 s) | - | upper | a flinch: the chest and pauldrons rock back, the cannon knocked off the aim, absorbed at once | PlayerFlags::HIT on a light hit (damage < 10 % max HP), layered over whatever plays | impact 1 |
| `valdris_hit_heavy` | 30 (1.00 s) | - | full | a big stagger: rocked back, the lead sabaton steps back, a deep absorb on both knees, stepping back in | PlayerFlags::HIT on a heavy hit (damage >= 10 % max HP or a stun); interrupts upper-layer clips | impact 1 |
| `valdris_knockdown` | 36 (1.20 s) | - | full | floored: rocked back off the lead foot, a stagger step back, then crashing down onto one knee, propped on the cannon | a knockback / launch strong enough to floor the hero (stun >= 0.8 s); holds its last frame until get_up | impact 1, ground 14 |
| `valdris_get_up` | 40 (1.33 s) | - | full | shoving up off the knee, the rear sabaton stamps forward under him, the lead foot resets, back into the stance | the knockdown's stun ends | stand 30 |
| `valdris_death` | 56 (1.87 s) | - | full | the fatal blow: rocked back, a knee gives and he crashes down onto it, then slumps over his knee and the cannon, a statue | LifeState::Downed begins (GameEvent::Downed); holds its last frame, then downed@loop (wraith look) | impact 1, knee 17, slump 32 |
| `valdris_downed@loop` | 60 (2.00 s) | loop | full | the wraith drift: slumped, floating off the ground, the cannon and the fist hanging, a slow heavy bob | LifeState::Downed (the Soul-Tether wraith; moves at 45 % speed with no gait, the client adds the ghost material) | - |
| `valdris_revive` | 40 (1.33 s) | - | full | dragged back into the body: a jolt, the sabatons slam down, a deep crouch, up into the stance | an ally completes the Soul-Tether revive (Downed -> Alive) | jolt 6, land 12 |
| `valdris_reforge_in` | 46 (1.53 s) | - | full | forged anew: rises off one knee (propped on the cannon), stamps in and throws both arms wide as the seams flare | LifeState::Reforging ends: the hero reappears next to an ally | stand 20, flare 26 |
| `valdris_victory` | 60 (2.00 s) | - | full | the roar: a crouch, then the cannon and the fist thrown up to the sky, chest out; holds the pose | the run is won (GameEvent victory / boss down, results screen); holds its last frame | roar 17 |
| `valdris_ping` | 20 (0.67 s) | - | upper | a ping: the left gauntlet thrusts out with the hand open, pointing ahead, the head follows | the ping / marker input (party callout) | ping 5 |
| `valdris_interact` | 40 (1.33 s) | - | full | work the anvil: a step in, lean over and press the plated fist down onto it, then step back | the interact input at an anvil / forge / shrine POI (PoiState use); 1.3 s | contact 13, release 26 |
| `valdris_forge_hammer@loop` | 36 (1.20 s) | loop | full | hammering the anvil with the plated left fist, the cannon arm braced at his side | the forge / hub anvil upgrade (Forge screen open, hub idle at the anvil) | hammer_hit 8 |
| `valdris_idle_signature@loop` | 150 (5.00 s) | loop | full | signature idle: a forge-deep breath vents the pauldron slots, he lifts the cannon to look down the barrel, flexes the fist | alive and idle for 6 s or more (out of combat); in the hub and the character select | vent 24, flex 100 |
| `valdris_bulwark_slam` | 50 (1.67 s) | - | full | Bulwark Slam: a deep crouch, a heavy leap with both arms raised overhead, the cannon slammed down on landing | kits.ron valdris active1 Bulwark Slam: the 7 m / 0.45 s leap runs from 'launch' to 'land' (the sim moves the entity); Nova (r 3.4) on 'land', the forge Barricade on 'barricade' | launch 8, land 21, barricade 25 |
| `valdris_siege_stance_enter` | 26 (0.87 s) | - | full | Siege Stance: two stamping steps out into a wide low brace, the fist planted on the knee, the cannon locked on the aim | kits.ron valdris active2 Siege Stance cast: rooted from 'anchor' (the anchor VFX / ground glyph); then siege_stance@loop | stomp_l 8, anchor 15 |
| `valdris_siege_stance@loop` | 40 (1.33 s) | loop | full | the Siege Stance brace: rooted wide and low, the fist on the knee, heavy breaths, the cannon dead steady | replaces idle_combat and locomotion for the 6 s Siege Stance (rooted); siege_fire layers the shots over it | - |
| `valdris_siege_stance_exit` | 20 (0.67 s) | - | full | out of the brace: he straightens and steps both sabatons back in under him | Siege Stance ends (6 s): back to idle_combat / locomotion | - |
| `valdris_siege_fire` | 5 (0.17 s) | - | upper (siege_stance) | a Siege Stance shot: a short hard kick of the cannon and the right shoulder, braced (recoil stays procedural) | each shot during Siege Stance (5.7 shots/s = one per 5.3 frames), layered over siege_stance@loop; first and last frame are siege_stance frame 0 | shot 1 |
| `valdris_mountainfall_start` | 46 (1.53 s) | - | full | Mountainfall: gathers low, steps wide and rises with both arms flung out and up as he grows, a ground-shaking stamp | kits.ron valdris ultimate Mountainfall cast: the x1.8 scale ramps from 'grow', the first shockwave on 'stomp'; then mountainfall@loop | grow 16, stomp 30 |
| `valdris_mountainfall@loop` | 40 (1.33 s) | loop | full | the Mountainfall avatar stance: wider and lower, heavy slow breaths rolling the pauldrons, the cannon on the aim | replaces idle_combat while Mountainfall lasts (8 s, model scale x1.8); shots and mountainfall_pound layer on top | - |
| `valdris_mountainfall_pound` | 33 (1.10 s) | - | upper (mountainfall) | the Mountainfall ground pound: both arms heaved overhead, then the cannon and the fist hammered down at the ground | every 1.1 s during Mountainfall (33 frames = 1.1 s): the pound (r 4.5) on 'pound'; upper layer over mountainfall@loop or locomotion, first and last frame are mountainfall frame 0 | pound 15 |
| `valdris_armor_break` | 32 (1.07 s) | - | upper | Reforged Flesh break: hunched against the blow, then the chest and both arms thrown open in a roar as the plates blast off | the Reforged Flesh passive when the Armor breaks: the shockwave (r 5.0) and the 3 s taunt start on 'break'; upper layer over anything | break 7, roar 12 |

## 2. Why his shared set is re-posed, and how the clips are made

Brax's library is written for a bare-armed brawler. Baked on Valdris unchanged (tried first), it drove his arms
180-350 mm into his own body: the keep-out had to push the fists that far, and what was left was not a juggernaut. His
stage-3 rig (`rig_report.md` §6) rules the library's arm and foot keys out:

| Limit (stage 3) | What it does to Brax's keys |
|---|---|
| Cannon elbow clean to 25°, acceptable to about 33° | Brax's guard, pump and punches bend the elbows 90-105°: the cannon's rear cuff goes 100+ vertices into the upper-arm plate |
| Upper arm clean from −45° to +30° of elevation (+15° forward); the left fist must stay off the anvil | Brax's guard holds both fists at the chin, in front of the anvil |
| Head: nod ≤ 5°, yaw ≤ 25° | the library stabilises the head in world space, which nods it into the gorget whenever the torso leans |
| The sabaton's instep lame and first toe lame ride the SHIN; the sole is one rigid plate 0.27 m past the ball (found in this stage) | a shin tipped forward over a flat foot drives the lame into the ground (9° = 4 cm); a heel raised about the ball drives the sole's front into it (5° = 2.4 cm, 34° = 15 cm) |

So `tools/blender/gf_hero/s4_valdris.py` keeps the library's contract and structure and re-poses every key in his own
vocabulary (`V`):

- **Arms by direction.** An arm is its upper-arm and forearm directions (elevation above the horizontal, azimuth from
  straight out to the side toward the front) in the rest chest frame, so every key is written against the ranges above.
  Between two such keys the target is re-solved from the *interpolated directions* every frame (`VClip`): s4lib
  interpolates effector points, and a swing from a low fist to a raised one cut past the shoulder and folded the elbow
  to 90-120° in between.
- **Planted feet with upright shins** (`V.stance`). The pelvis is solved (damped least squares through s4lib's own leg
  IK and pole formula) so that each flat foot's shin keeps its rest lean and the knee bends in its rest plane: the hips
  go back instead of the knees forward. His pelvis sits 0.21 m behind the balls of his feet at rest and 0.3-0.4 m behind
  them in his stances, so his feet stand forward of the root and the pelvis stays over it.
- **Feet roll about the sole's edges** (`V.foot`, `SOLE_TIP`, `SOLE_HEEL`): a heel raise lifts and advances the ball
  joint so the rigid sole pivots on its front edge, and a heel strike pivots on its rear edge, as real sabatons must. The
  gait uses the same roll through the contact and the swing, and a planted sabaton's heel rises at least as far as its
  shin tips forward past the rest lean (`V.shin_lean`), so the instep lame never reaches the ground.
- **Feet in the air hang in line with their shins** (`V.neutral_heel`): the greave drives into the foot shell past about
  20° of ankle flexion either way, so a lifted foot's pitch is solved (bisected: the pitch moves the ankle, the ball is
  the IK target) to keep the ankle at its rest angle, and the key's heel becomes a small offset. The run, strafe and
  backpedal swings and most stepping keys use it. The walk, the dash and its landing, the wraith and the steps into and
  out of the kneel keep written heels: hung, they jerked the thigh at toe-off, swung a knee into the anvil or flipped
  the knee plane.
- **One knee down** (`V.genuflect`) is built, not solved: the front shin upright, the rear knee's poleyn on the ground
  (the knee joint 0.27-0.30 m up: the knee cop is thick) and its sabaton rolled onto the sole's front edge. The feet end up
  about 1.1 m apart front to back, so the knockdown and the death step back into it.
- **His gait** (`vloco`, adapted from `s4_clips.locomotion`): a wide track (each sabaton is 0.43 m wide and 0.73 m long),
  the pelvis sinking on every footfall and rolling over the stance leg, the knee plane 10° out from the toes, the
  roll-off about the sole's edge. The run holds the cannon on the aim and pumps the fist; the walk swings the cannon low.
- **The torso twist stays low** (60 % on spine_01, 40 % on spine_02) and the head is FK (40 % on the neck).
- **Overhead arms** (the Bulwark Slam leap, the Mountainfall cast and pound) key `x_pauldron_L/R` a little on top of
  their drive (`Clip.extra_keyed`), the only extras a clip keys. A larger key swung the pauldrons' inner lames down into
  his beard, so the raised fists stay in front of his face.
- **The cloth pass** (`s4_valdris_cloth.py`) keys the cape, loincloth and braid chains after the bake. Each chain bone
  follows a lagged hang: a damped spring toward the apparent gravity at its pin (so a landing throws the cape forward),
  limited to a cone around the vertical so the heavy cape never flips over his back, with drag against the design
  travel (the run streams it back). Then the stage-3 clear step pushes the cloth out of the plates and the ground every
  frame, and its corrections are dilated and smoothed over time so nothing pops. Without the pass the cape rides the
  torso like a board and the legs stride through it; the client has no cloth spring yet.

## 3. Validation

Every number comes from `reports/anim/*.json`; the audit columns cover EVERY frame of every clip (1288 frames), not only the key frames.

| Clip | Ball slide / sole slip (mm) | Loop seam (deg/frame², seam / inside) | Elbow L / R (°) | Knee (°) | Keep-out push (mm) / left | Plate clipping max (median) | Cannon poke / cuts | Cloth inside cape / loin / braids | Lowest solid / cloth (mm) |
|---|---|---|---|---|---|---|---|---|---|
| `idle` | 0.0 / 0.0 | 0.04 / 0.09 | 22 / 19 | 31 | 0 / 0 | 64 (52) | 4 / 1 | 25 / 7 / 0 | -12 / 130 |
| `idle_combat` | 0.0 / 0.0 | 0.49 / 0.49 | 49 / 35 | 42 | 8 / 0 | 133 (122) | 5 / 14 | 24 / 12 / 0 | -13 / 114 |
| `walk` | 0.0 / 2.5 | 29.12 / 29.12 | 28 / 21 | 108 | 0 / 0 | 126 (105) | 5 / 0 | 26 / 14 / 0 | -12 / 143 |
| `run` | 0.0 / 2.4 | 24.31 / 35.47 | 53 / 35 | 132 | 23 / 1 | 226 (154) | 1 / 14 | 25 / 15 / 0 | -0 / 154 |
| `strafe_left` | 0.0 / 1.8 | 22.11 / 57.02 | 50 / 34 | 131 | 12 / 0 | 389 (207) | 5 / 14 | 24 / 39 / 0 | -0 / 146 |
| `strafe_right` | 0.0 / 1.8 | 24.09 / 57.02 | 50 / 34 | 131 | 12 / 0 | 380 (165) | 5 / 14 | 28 / 41 / 0 | -0 / 116 |
| `backpedal` | 0.0 / 2.0 | 21.81 / 50.49 | 50 / 34 | 130 | 12 / 0 | 203 (165) | 5 / 14 | 51 / 14 / 0 | -0 / 75 |
| `dash` | 0.0 / 0.0 | - | 49 / 44 | 139 | 8 / 0 | 171 (161) | 5 / 28 | 24 / 15 / 0 | -12 / 51 |
| `dash_recover` | 0.0 / 0.0 | - | 58 / 44 | 138 | 17 / 0 | 168 (131) | 5 / 28 | 38 / 17 / 0 | -14 / 58 |
| `fire_light` | 0.0 / 0.0 | - | 50 / 34 | 36 | 8 / 0 | 117 (115) | 5 / 14 | 34 / 7 / 0 | -12 / 130 |
| `fire_heavy` | 0.0 / 0.0 | - | 61 / 46 | 46 | 8 / 0 | 133 (116) | 5 / 30 | 31 / 20 / 0 | -14 / 84 |
| `fire_charge` | 0.0 / 0.0 | 0.43 / 0.43 | 58 / 44 | 46 | 0 / 0 | 130 (127) | 29 / 28 | 20 / 6 / 0 | -12 / 100 |
| `hit_light` | 0.0 / 0.0 | - | 49 / 34 | 36 | 8 / 0 | 125 (118) | 5 / 14 | 33 / 9 / 0 | -12 / 123 |
| `hit_heavy` | 0.0 / 0.0 | - | 58 / 45 | 82 | 18 / 0 | 167 (126) | 6 / 28 | 32 / 23 / 0 | -16 / 16 |
| `knockdown` | 0.0 / 16.8 | - | 86 / 37 | 137 | 133 / 2 | 191 (142) | 5 / 17 | 36 / 11 / 0 | -31 / -55 |
| `get_up` | 0.0 / 16.8 | - | 81 / 35 | 149 | 133 / 1 | 374 (141) | 5 / 14 | 34 / 34 / 0 | -19 / -69 |
| `death` | 0.0 / 16.8 | - | 49 / 34 | 141 | 138 / 1 | 258 (196) | 5 / 14 | 40 / 11 / 1 | -35 / -66 |
| `downed` | 0.0 / 0.0 | 0.12 / 0.15 | 32 / 27 | 146 | 0 / 0 | 250 (240) | 4 / 4 | 45 / 14 / 0 | 140 / -3 |
| `revive` | 0.0 / 0.0 | - | 49 / 35 | 148 | 46 / 0 | 250 (122) | 5 / 16 | 32 / 29 / 1 | -17 / -14 |
| `reforge_in` | 0.0 / 16.8 | - | 92 / 36 | 149 | 134 / 1 | 361 (128) | 5 / 16 | 37 / 32 / 0 | -19 / -30 |
| `victory` | 0.0 / 0.0 | - | 58 / 44 | 57 | 18 / 0 | 161 (154) | 6 / 28 | 34 / 20 / 0 | -19 / 40 |
| `ping` | 0.0 / 0.0 | - | 49 / 48 | 36 | 8 / 0 | 122 (108) | 6 / 29 | 26 / 7 / 17 | -12 / 126 |
| `interact` | 0.0 / 0.0 | - | 86 / 34 | 78 | 51 / 0 | 162 (133) | 5 / 12 | 30 / 18 / 0 | -33 / 105 |
| `forge_hammer` | 0.0 / 0.0 | 8.77 / 65.92 | 101 / 15 | 59 | 54 / 1 | 170 (137) | 4 / 0 | 32 / 19 / 0 | -20 / 77 |
| `idle_signature` | 0.0 / 0.0 | 0.15 / 18.92 | 26 / 35 | 33 | 0 / 0 | 70 (51) | 5 / 14 | 27 / 6 / 0 | -9 / 117 |
| `bulwark_slam` | 0.0 / 50.3 | - | 49 / 40 | 121 | 124 / 3 | 248 (128) | 5 / 22 | 30 / 35 / 0 | -40 / -32 |
| `siege_stance_enter` | 0.0 / 28.2 | - | 58 / 46 | 113 | 18 / 0 | 154 (135) | 6 / 28 | 37 / 15 / 1 | -16 / -38 |
| `siege_stance` | 0.0 / 0.0 | 0.23 / 0.24 | 28 / 41 | 82 | 0 / 0 | 135 (129) | 5 / 25 | 18 / 6 / 0 | -0 / -13 |
| `siege_stance_exit` | 0.0 / 27.4 | - | 55 / 41 | 107 | 8 / 0 | 142 (124) | 5 / 24 | 30 / 12 / 0 | -15 / 26 |
| `siege_fire` | 0.0 / 0.0 | - | 25 / 41 | 79 | 0 / 0 | 120 (112) | 5 / 24 | 31 / 4 / 0 | -0 / -16 |
| `mountainfall_start` | 0.0 / 16.8 | - | 49 / 50 | 119 | 8 / 0 | 146 (114) | 6 / 32 | 39 / 25 / 0 | -23 / -22 |
| `mountainfall` | 0.0 / 0.0 | 0.37 / 0.37 | 53 / 47 | 56 | 0 / 0 | 133 (119) | 6 / 29 | 22 / 8 / 0 | -10 / 39 |
| `mountainfall_pound` | 0.0 / 0.0 | - | 48 / 41 | 52 | 0 / 0 | 134 (110) | 5 / 25 | 32 / 2 / 0 | -9 / 26 |
| `armor_break` | 0.0 / 0.0 | - | 51 / 61 | 48 | 119 / 0 | 163 (67) | 6 / 44 | 43 / 17 / 11 | -14 / 128 |

How to read the columns:
- **Ball slide**: s4_anim's metric, the world drift of a planted ball joint inside one contact (the design travel added back). **Sole slip**: the audit's, how far the sabaton sole's vertices touching the ground move between frames, summed over one contact: a rolling foot keeps its contact edge still, so this is the honest foot-slide number for him.
- **Loop seam**: the last frame IS the first (0.0000° and 0.000 mm in every loop); the two numbers are the largest second difference through the seam against anywhere inside the clip.
- **Keep-out push**: how far the arm keep-out moved a fist target out of the body (0 = clean as written); **left**: body vertices still inside a hand's volume (the cannon or the bare forearm), gated at 60.
- **Plate clipping**: vertices of one armour piece inside a piece of another region that the rest pose does not have (stage 3's exact ray-parity test, 3 mm deep), the worst frame and the median frame. Rest-pose overlaps (shingled lames) do not count; lames of one region sliding over each other are reported apart in `render_checks.json`.
- **Cannon**: right-arm vertices out of the sleeve (poke) and other pieces enclosed by it (cuts, mostly the upper-arm plate in the elbow crook at the aim's 33° elbow, as in stage 3).
- **Cloth inside**: cloth vertices more than 3 mm inside a solid piece, including the cape's and loincloth's pinned top rows, which overlap the plates they hang from at rest (25 cape vertices in the idle).
- **Lowest**: the lowest vertex of the solid parts and of the cloth; negative is under the ground.

The glTF check (`anim/gltf_check.json`): 34 animations named as `clips.json` says, sampled at 30 fps, the root never moves, only the pelvis translates, the sockets never change, every loop's last sample equals its first, the twist bones animate in 34 clips, `extensionsRequired` is empty; the scratch GLB with the mesh and every clip is 16.9 MB. It passes.

## 4. What the sheets show (my review)

I looked at every clip sheet (the front 3/4 close-up, the side, the client camera at true 1080p pixels and at 2.5x
nearest) and at the three game-size boards next to the concept.

- **At game size** his silhouette is the concept's block: the pauldrons level with his crown, the chest anvil and the
  cannon. From pose to pose, what changes is the cannon's direction, the depth of the stance and the cape. The arms and
  legs are a few pixels. `idle_combat`, `siege_stance@loop` and `mountainfall@loop` look almost the same at 22 m: the
  brace is about 0.2 m lower and wider, and Mountainfall's x1.8 scale comes from the sim. The anchor glyph and the
  Mountainfall VFX must carry those states.
- **Locomotion.** The run is low and heavy: the pelvis drops on every footfall, the cannon stays down the aim and the
  cape streams back. The walk rolls from sabaton to sabaton with the cannon swinging low. The strafes open the hips 40
  deg toward the travel and keep the chest and cannon on the aim. At the passing position one sabaton crosses behind the
  other (a 1.5 m stride at 5.6 m/s on feet 0.43 m wide), and in the close-up it shows as a sabaton through the other
  greave for two or three frames. The backpedal takes short driving steps.
- **Feet.** No planted sole slides in the loops (sole slip at most 2.5 mm per contact). The sabatons roll on the edges
  of their soles, and in the air they hang in line with the shins. The instep lame still dips up to 12-13 mm under the
  ground in the stances, because it rides the shin.
- **Combat clips** are small on purpose: `fire_light` is a short kick for 2.6 shots/s, the hits rock him from the knees
  up, and the dash is a low bull rush behind the anvil.
- **The knee-down set.** The knockdown and the death step back onto one knee with the rear sabaton's toes tucked under.
  The death ends slumped over his knee and the cannon, a statue for the wraith to rise from. The get-up and the reforge
  push off the knee and stamp the rear foot forward. When he leans, the front knee's poleyn touches the underside of the
  chest anvil (15-30 vertices). Where the stepping leg swings past the kneel, the in-betweens reach 360-374 clipping
  vertices for a frame (f14).
- **His kit.** Bulwark Slam has an 8-frame crouch, then the leap with the cannon swung overhead. The left fist stays in
  front of his face, because a higher arm drives the pauldron's inner lames into his beard. It lands in a squat and hits
  the barricade beat on f25. I straightened the landing (lean 18 -> 9 deg, clip maximum 321 -> 248 vertices), but the
  front knee still pushes into the chest anvil's underside, about 40 vertices over f22-f28. Siege Stance steps out into
  a wide low brace with the fist on the knee and holds it with heavy breaths; `siege_fire` is a 5-frame kick.
  Mountainfall gathers, steps wide, flings both arms up and stamps. Its loop breathes wider and lower, and the pound
  heaves both arms up and hammers them down. The armour break hunches, then throws the chest and arms open. The
  signature idle vents the pauldrons, lifts the cannon to look down the barrel and flexes the fist.
- **Cloth.** The cape hangs heavy, trails in the run and drapes over his heels when he kneels. The thighs push the
  loincloth in the strafes. A few cape-hem vertices (at most 7) go under the ground when he kneels or lands (down to -69
  mm).

## 5. Mapping notes for the engine agent (`crates/` is not the art track's)

- **Locomotion** as for every hero: `run`, `strafe_left`, `strafe_right` and `backpedal` by the angle between velocity
  and aim, `walk` below about 55 % of move speed; playback rate = speed / `design_speed_mps` (`clips.json`: 5.6 m/s for
  the run set, 1.70 m/s for the walk).
- **Fire.** His colossus_cannon fires 2.6 shots/s: play `fire_light` (8 frames, the kick on frame 1) per shot over
  locomotion or `idle_combat`. Recoil itself stays procedural. `fire_heavy` / `fire_charge` serve other chassis.
- **Bulwark Slam** (active 1): play `bulwark_slam` on cast. The sim's 0.45 s leap should run from the `launch` event
  (frame 8) to `land` (frame 21: 13 frames ≈ 0.43 s); Nova on `land`, the forge Barricade on `barricade` (frame 25). The
  clip's first 8 frames are the crouch (0.27 s): start the leap on `launch`, or start the clip 8 frames before the cast.
- **Siege Stance** (active 2, 6 s rooted): `siege_stance_enter` (the anchor VFX / ground glyph on `anchor`, frame 15),
  then `siege_stance@loop` for the duration instead of `idle_combat` and locomotion, with `siege_fire` (5 frames) layered
  per shot (5.7 shots/s); then `siege_stance_exit`.
- **Mountainfall** (ultimate, 8 s, scale × 1.8): `mountainfall_start` (the scale ramps from `grow`, frame 16; the first
  shockwave on `stomp`, frame 30), then `mountainfall@loop` replaces `idle_combat`; `mountainfall_pound` (33 frames =
  1.1 s, `pound` on frame 15) layers over it or over locomotion every 1.1 s.
- **Reforged Flesh**: when the Armor breaks, `armor_break` (upper layer) with the shockwave and the taunt on `break`
  (frame 7) and the roar on `roar` (frame 12).
- **Idles**: `idle@loop` out of combat, `idle_signature@loop` after 6 s idle and in the hub / character select.
- **Life states**: `death` holds its last frame (he ends on one knee, slumped over his cannon), then `downed@loop` with
  the ghost material; `revive` or `reforge_in` returns to the stance. `knockdown` holds its last frame until `get_up`.
- **Pelvis travel**: the knockdown, get up, death and reforge clips carry the pelvis up to about 0.6 m back / forward
  (one knee down needs the feet 1.1 m apart); only the pelvis translates, the root never moves.
- **Cloth channels**: the `x_cape_*`, `x_loin_*` and `x_beard_*` bones are keyed in every clip. A future cloth spring in
  the client can take them over by ignoring those channels.
- **Events** are pose markers in the `.blend` and are listed in `clips.json`; stage 5 writes them to the sidecar.

## 6. Honest findings and open issues

1. **The user's visual approval is the one open gate** (`status.json` -> `4_animation.items.user_visual_approval`).
   Nothing was checked in the engine: the client plays none of these clips yet, and stage 5 (the GLB export and the
   events sidecar) is not done.
2. **Plate clipping remains in every clip.** It counts armour vertices inside a piece of another region that the rest
   pose does not have. The median of the clip medians is 128 vertices; the worst frame is 389 (`strafe_left` f3). The
   recurring pairs, by size: the upper-arm plate into the chest at the armpit (6-13 in every pose, the idle included);
   the left tasset into the anvil and its gasket (9); the greave and shin plate into their own sabaton's foot shell in
   the gait and the steps (15-25 per foot, less than before: the run went 249 -> 226 and the backpedal 229 -> 203 once
   the swinging foot hangs in line with its shin); the strafes' passing legs (20-45 per pair); the vambraces into the
   pauldron lames when the arms go up (`victory` 22, `forge_hammer` 31); the front poleyn into the chest anvil in the
   kneels and on the Bulwark landing (15-45); and the in-betweens of the knee-down steps (up to 374). Most of these are
   hidden inside the silhouette at the game camera, but a close-up (the hub, character select) will show the armpit and
   the knee.
3. **Ground contact.** In the stances the instep lame dips up to 12-13 mm. On the knee the poleyn goes up to 35 mm into
   the ground (`death` -35 mm when he slumps). In the Bulwark crouch and push-off the right sabaton goes 21-40 mm into
   the ground (f2-f7).
4. **Foot slip in the kit.** Every loop keeps its soles still (at most 2.5 mm per contact). The one-shots slip where the
   pelvis travels a long way: the Bulwark landing 43-50 mm (the sabatons settle while he absorbs), the Siege Stance
   steps 27-28 mm and the steps onto the knee 17 mm.
5. **Motion.** The fastest joint accelerations sit in the gait at the toe-off and the landing: the strafes 57
   deg/frame², the backpedal 50, the run 35. The rolling sabaton snaps from its toe edge into the swing. At play speed
   it reads as a stomp, but it wants an in-engine look. `forge_hammer` reaches 66 at the hammer's impact, on purpose.
6. **Cloth.** The pinned top rows of the cape and the loincloth overlap the plates they hang from, as at rest (25 cape
   vertices in the idle). The loincloth is pushed through by the thighs in the strafes (39-41 vertices). The braids go
   into the pauldron lames in `ping` and `armor_break` (11-17). Cape-hem vertices go under the ground in the kneels and
   landings (at most 7 vertices, down to -69 mm).
7. **The cannon.** In the elbow crook the upper-arm plate is enclosed by the sleeve at the aim's 33 deg elbow: cuts of
   up to 44 vertices (`armor_break`; 14 at the plain aim), the case stage 3 accepted. The sleeve's poke-through stays at
   1-6 vertices, except 29 in `fire_charge`.
8. **Keep-out pushes.** In the knee-down clips and the Bulwark leap the written fists land in the thigh or knee. The arm
   keep-out pushes them out (up to 138 mm) and leaves at most 3 body vertices inside a hand.
9. **Knee flexion** reaches 149 deg on the knee, inside the documented 135-150 deg soft spot of the stage-3 weights.
10. **Timing assumptions for the engine agent.** The Bulwark leap's 8-frame crouch comes before `launch` (§5).
    `interact` assumes that the sim steps him to the anvil's point of interest. The Siege Stance anchor spikes of the
    brief are VFX, not rig parts.
11. **Which keys keep written heels.** The walk, the dash and its landing, the wraith, and the feet stepping into and
    out of the kneel keep the heel angles I wrote. Hanging those feet from the shin cut some clipping but jerked the
    thigh at toe-off (half as much again angular acceleration in the walk), flipped the get-up's knee plane (a one-frame
    twist flip) or folded the wraith's sabatons into its tassets. The kneel steps use a steeper written heel (65 deg
    instead of 40): the death's maximum went 343 -> 258 and the knockdown's 252 -> 191, with the motion unchanged.

## 7. Shared tool changes (backwards compatible) and the Brax regression

| File | Change |
|---|---|
| `s4lib.py` | `Rig.keyed` skips `x_` extras (docs/art/GF_HERO_SKELETON.md §2: shared clips never key them); `Clip(extra_keyed=..., base=...)` |
| `s4_anim.py` | optional hero hooks: `s4_<key>.shared_clips(K)` (asserted against `s4_contract.SHARED_CLIPS`), `KEEPOUT_LOOSE_PARTS`, `KEEPOUT_OWN_BONES`; a clip's `extra_keyed` bones are keyed; `extra_keyed` / `base` go to `clips.json` only when set |
| `required_clips.json` | the `valdris` block (his 10 unique clips), for stage 5 |

`s4_gltf_check.py`, `check_clips.py`, `s4_contract.py`, `s4_clips.py` and `s4_brax.py` are unchanged.

**Brax regression** ([`anim/brax_regression.json`](anim/brax_regression.json)). Brax's anim and glTF-check steps ran
twice in a scratch copy of the repository, with the HEAD scripts and with the changed ones: `clips.json` and
`gltf_check.json` are identical, and the scratch GLB is byte-identical (sha256 `cfba1ff0…`). Nothing under
`art/characters/brax/` was written.

Valdris-only files: `s4_valdris.py`, `s4_valdris_run.py`, `s4_valdris_cloth.py`, `s4_valdris_render.py`,
`s4_valdris_sheets.py`.

## 8. Rebuild

```sh
python tools/blender/gf_hero/s4_valdris_run.py                  # anim, cloth, render, sheets, gltf_check, contract (about 12 min)
python tools/blender/gf_hero/s4_valdris_run.py --only anim      # re-bake the clips (about 20 s); then run --from cloth
```

To tune a clip, edit its keys in `tools/blender/gf_hero/s4_valdris.py` (`build`), then run the chain from `anim`
(the cloth pass must follow every bake: the bake re-creates the actions without the cloth keys).
