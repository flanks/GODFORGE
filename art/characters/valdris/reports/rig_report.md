# Valdris — stage 3 rig (GF_Hero_v1), made by AI, 2026-09-26

> **The user's decisions of 2026-09-25, relayed by the workflow coordinator.**
> - There is no human artist at any stage. The AI makes every stage, and the user gives the final visual approval
>   (`status.json` → `3_rig.items.user_visual_approval`, `pending_human`).
> - Weapons are separate models on hand sockets. The siege cannon is the weapon track's `colossus_cannon`
>   (`assets/models/weapons/colossus_cannon.glb`), not part of his body. His body has two armoured arms with plate
>   gauntlet fists.
> - Content over tests: the validators and review renders are the quality gate.

The skeleton contract every hero shares is [`docs/art/GF_HERO_SKELETON.md`](../../../../docs/art/GF_HERO_SKELETON.md).
Brax went through this stage first ([`art/characters/brax/reports/rig_report.md`](../../brax/reports/rig_report.md)).
This report covers Valdris: the same master skeleton on a plate juggernaut.

## Summary

- **Rig.** GF_Hero_v1 with 116 bones: the 63 contract bones plus 53 per-hero `x_` extras.
  - 9 of the extras are **driven helpers** (pauldrons, couters, knee cops, tassets, fauld).
  - 44 are **cloth chains**: the cape 5 × 5, the loincloth 3 × 3 and the braids 5 × 2.
- **Weights.**
  - The under-suit is weighted exactly as Brax's body.
  - Every one of the 137 armour pieces is rigid, one weight row per piece; so are the beard's locks and braid pieces.
  - The cloth hangs on its chains with a linear falloff.
  - Checks: 0 unweighted vertices, at most 4 influences, sums within 2.2e-16 (in the GLB, 1.3e-7).
- **Cannon.** The colossus_cannon rides `weapon_R` as an **identity child**. This is proven in glTF with the
  **shipped** GLB: 4,799 vertices land within **0.28 µm**.
- **Range of motion.** Plate this massive limits every joint. A range-of-motion study (§5) measured how far each
  joint turns before one plate cuts another. It chose the helpers' follow factors and gives stage 4 its ranges (§6).
- **Validation poses.** 13 poses, all inside those ranges except the deliberate stress pose: A-pose, cannon aimed
  forward, guard, Siege Stance brace, deep squat, lunge, torso twist, two head turns, the Bulwark Slam raise, forearm
  twist, and elbow 145° + knee 135°. The cloth is posed clear. Each pose is rendered close up and through the in-game
  camera, and each is measured (§7).
- **Honest limits** (§8), for the user's review:
  - the arms have a small clean range between the anvil and the pauldrons, and straight overhead is impossible
    without keyed pauldrons;
  - the head can barely nod;
  - the cannon's rear cuff meets the upper-arm plate past about 25° of elbow;
  - the cannon's brace handle is out of reach for the left hand.

Review sheets (all in [`stage3/`](stage3/)):

| Sheet | What |
|---|---|
| [`stage3_skeleton.png`](stage3/stage3_skeleton.png) | the 116 bones over the body (core red, twist pink, fingers green, driven helpers orange, cape and loincloth chains violet, braids lime, sockets as RGB = XYZ grip axes), and the dominant bone per vertex on every part: a rigid plate is one flat colour, the cape a grid of blends |
| [`stage3_poses_1.png`](stage3/stage3_poses_1.png) … [`_4`](stage3/stage3_poses_4.png) | the 13 poses: toon 3/4 front and back, clay close-ups (shoulder front and back, elbow, knee, hips, head, the cannon arm), and each pose's numbers |
| [`stage3_ingame.png`](stage3/stage3_ingame.png) | every pose through the client camera (orthographic 55°, 22 m view height, true 1080p pixels) at 1× and 3× |
| [`stage3_weapon.png`](stage3/stage3_weapon.png) | the cannon on `weapon_R`: a section along the barrel (rest and aimed), the arm in the sleeve in five poses, the identity-attach proof, and the elbow range the sleeve allows |
| [`stage3_limits.png`](stage3/stage3_limits.png) | the range-of-motion sweeps as small multiples |
| [`stage3/*.json`](stage3/) | the measurements: landmarks, MakeHuman seed, skin, glTF check, limits, poses, and the Brax regression of the shared-tool hooks |

## 1. Deliverables

| Path | What | Git |
|---|---|---|
| `production/valdris_rig.blend` | contents listed below | LFS |
| `work/valdris_landmarks.json` | his GF_Hero_v1 landmark file: 69 points, 4 vectors, 4 socket frames, 53 extra bones | yes (`git add -f`; the rest of `work/` is local) |
| `stage3_skin.json` | every hand-set rig number: under-suit weight fixes, helpers and their follow factors (each with the measurement that chose it), cloth grids, the armour piece → bone table | yes |
| `reports/stage3/` | sheets + JSON | yes |
| `work/valdris_s3_mh_seed.npz`, `work/renders/stage3/`, `work/gltf_check/` | the seed weights, full-size renders, scratch GLBs | local (regenerated) |

`production/valdris_rig.blend` contains:
- the `GF_Hero_v1` armature, with its twist constraints and the helper drives;
- the 12 skinned stage-2 objects;
- the `GF_ValidationPoses` action, stashed as a muted NLA track with one marker per pose (the cloth chains are keyed as
  posed);
- a `PREVIEW_colossus_cannon (not exported)` collection with `PREVIEW_colossus_cannon_R`. It is the shipped GLB baked
  into one object in its grip frame and held on `weapon_R` by a Child Of constraint whose inverse is `SOCKET_TO_GRIP`.
  Stage 4's arm keep-out reads it as a sleeve weapon.

Rebuild everything with `python tools/blender/gf_hero/s3_valdris_run.py`. It takes about 2 minutes on the CPU:
landmarks → lm_valdris → seed → skin → gltf_check → limits → poses → sheets → contract. The review renders use Cycles
on the CPU and Workbench only; the GPU is shared.

## 2. Skeleton and landmarks

**Contract joints.** The shared `s3_landmarks.py` derives them exactly as for Brax: the MakeHuman joints are mapped
through Valdris's stage-2 thin-plate spline, with the fit's ×1.6 glove hand scale. `s3_valdris_landmarks.py` then
finishes the file for an armoured hero. The landmark JSON is the whole contract, and the skeleton doc allows it:
"a hero built another way writes the same JSON by any means".

- **Fingers on the gauntlet lames.** His visible fingers are the box-section lames, which stage 2 built around its own
  warped joints (`reports/stage2/parts.json` `finger_joints_L`). The finger bones are set back to those joints
  (moves of 0-9 mm from the glove centroids), so the lames pivot where they were built and the fist closes into one
  plated block. The palm normal and the thumb curl are recomputed with the shared formulas.
- **The hand bone's tail on the forearm axis.** The tail is the middle knuckle projected onto the elbow → wrist line,
  a 1.3 cm move. The colossus_cannon is a sleeve weapon coaxial with the forearm, and the sleeve rule (stage 4) only
  twists the hand about its own Y. With the tail off the axis, that twist would tilt the barrel by up to 12°.
  The massive vambrace already lies inside the sleeve wall with 0.7 mm to spare, so it would poke out.
- **`chest_sigil` on the anvil.** His chest emblem is the anvil, 0.35 m in front of the under-suit that the shared
  step ray-casts. The socket sits on the anvil's front face at x = 0, half-way up the anvil body, at
  (0, −0.599, 1.515). Its forward is that face's normal.
- **Sockets.** `weapon_L` / `weapon_R` are the stage-2 hand frames on the forearm axis, at (±0.997, 0, 1.78):
  forward along the fingers, up out of the back of the hand. These are the frames the cannon review was done in.
  `head_top` is (0, −0.10, 2.306), the crown. The pauldron uprights rise 3 cm higher, but a name plate goes on the
  head.

Bone lengths (m). The short upper arm is the one the pauldrons swallow; elbow to palm is set by the cannon's sleeve.

| Bone | Length | Bone | Length |
|---|---|---|---|
| pelvis | 0.112 | spine_01 / 02 | 0.130 / 0.130 |
| spine_03 | 0.484 (to the neck) | neck | 0.130 |
| head | 0.152 | clavicle | 0.381 (it slopes down from 1.96 to the shoulder at 1.78) |
| upperarm | 0.225 | lowerarm | 0.320 |
| hand | 0.121 | thigh | 0.535 |
| shin | 0.486 | foot / toe | 0.253 / 0.104 |

### The per-hero extras (53)

| Extras | Parent | Kind | What they carry |
|---|---|---|---|
| `x_pauldron_L/R` | clavicle | **driven**: a Transformation constraint. The upper arm's **elevation** (the Z part of its swing, with the twist about the arm removed) × **0.6**, upward only, about a hinge by the neck (±0.25, 0, 1.99) | the pauldron stack: top lames, cap, glowing slot, upper lame, upright plate, rivets. The lower arm lame rides the upper arm |
| `x_elbow_L/R` | upperarm | **driven**: Copy Rotation of lowerarm, **0.5** left, **1.0** right | the elbow ring, the couter and its cop |
| `x_knee_L/R` | thigh | **driven**: Copy Rotation of shin, **0.5** | the poleyn and the glowing knee smile |
| `x_tasset_L/R` | pelvis | **driven**: Copy Rotation of thigh, **0.25**, about a hinge on the belt | both tasset lames |
| `x_fauld_01` | pelvis | **driven**: a driver (a simple expression, no Python): `max(thigh_L, thigh_R flexion, 0) × 0.8` | fauld lames 3-4 |
| `x_cape_{R2,R1,C,L1,L2}_01..05` | spine_03 | cloth | the cape: 5 chains at u = −1, −½, 0, ½, 1 across its rows, joints at z 2.03 / 1.70 / 1.36 / 1.02 / 0.68 / 0.30 |
| `x_loin_{R,C,L}_01..03` | pelvis | cloth | the loincloth, from the belt to 0.44 m |
| `x_beard_{1..5}_01..02` | head | cloth | the braids (1 = his right): the root to between lobes 2 and 3, then on to the cap |

- **Rest orientation.** Every helper has the rest orientation of the bone it follows. A local-to-local constraint
  therefore turns it about the same axes.
- **Additive.** The constraints mix AFTER the bone's own rotation. Shared clips leave the helpers at rest, and a
  unique clip may key a helper on top of its drive; the Bulwark Slam needs that (§6).
- **Export.** Blender evaluates the drives, and the stage-5 exporter samples every bone. Clips therefore carry the
  helpers baked, like the twist bones.
- **Cloth chains.** They are never keyed by shared clips: in the game a spring or a unique clip moves them.

## 3. Weights

| Object | Rule | Result |
|---|---|---|
| BODY (the under-suit: mail, padding, the face and the glove; 3,953 v) | exactly Brax's rule: MakeHuman CC0 seed (exact per vertex, match p99 0.9 mm), 50/50 with bone heat on the torso and limbs, 0 heat on the hands, 20 % on the head; the twist split; joint blend bands at the knees and elbows; Euclidean smoothing at the jaw fold, shoulders and knees; the stage-2 extra loops moved onto their profile (57 vertices, ≤ 1 cm) | 1-4 influences (460 / 2,119 / 651 / 723) |
| Armour (CUIRASS, ANVIL, PAULDRONS, ARMS, GAUNTLETS, LEGS, SABATONS, HIPS: 137 pieces) | **rigid per piece.** The face attribute `gf_piece` names the piece, and `stage3_skin.json` `rig.pieces` gives its bone (the stage-2 suggestion where not listed). Every vertex of a piece carries the same row. Only the gorget's neck lame blends: 60 % neck / 40 % spine_03 | 1 influence (the gorget lame: 2) |
| BEARD | the block is hair on the head, its bib blending to 45 % neck at the bottom, so a nod folds it instead of driving it through the gorget; locks and moustache rigid on the head; each braid's lobes, ring and cap rigid on its `x_beard` bones | ≤ 2 |
| CAPE (+ collar) | a vertex at (u, z) blends linearly between its two nearest chains, and along a chain between the bones either side of its height (hat functions on each bone's middle). The top row is pinned to spine_03 (it hangs under the pauldrons). The collar is rigid on spine_03 | ≤ 4 |
| LOINCLOTH | the same grid on the `x_loin` chains, pinned to the pelvis at the belt | ≤ 4 |

Which pieces ride which bone, in brief:
- pauldron stack → `x_pauldron`; lower arm lame and rerebraces → upperarm;
- elbow ring and couter → `x_elbow`;
- first vambrace → lowerarm; second vambrace and wrist cuff → `lowerarm_twist` (they turn with the forearm's
  pronation);
- gauntlet cuff, back and knuckle guard → hand; each finger lame → its finger bone;
- cuisses → thigh; poleyn and knee smile → `x_knee`; greave and shin plate → shin;
- sabaton: the ankle cuff and instep lame → **shin** (§5), the foot shell and sole → foot, toe lames 2-3 → toe;
- tassets → `x_tasset`; fauld 1-2 → pelvis, 3-4 → `x_fauld_01`;
- cuirass bands → spine_03 / 02 / 01 / pelvis; the anvil → spine_03.

**Checks** (`stage3/skin.json`, `stage3/gltf_check.json`), all met on all 12 objects:
- 0 unweighted vertices;
- at most 4 influences;
- sums within 2.2e-16;
- no weight on `root` or a socket.

In the exported GLB:
- all 116 joints are present;
- the hierarchy matches the contract under `GF_Hero_v1`;
- each of the 12 primitives has one JOINTS_0 / WEIGHTS_0 set;
- the weights sum to 1 within 1.3e-7;
- `extensionsRequired` is empty.

## 4. The colossus_cannon on `weapon_R` (the identity attach)

- **In glTF (the engine's truth).**
  1. The rig is exported as stage 5 will export it.
  2. The **shipped** `assets/models/weapons/colossus_cannon.glb` is read as it is. Its scene root is identity.
  3. Every mesh node is pushed through the exported `weapon_R` node's world matrix.

  All 4,799 vertices land on the cannon the rig holds within **0.28 µm**, and the four socket nodes match their grip
  frames within 8e-7. There is **no correction rotation anywhere**. The engine spawns the cannon scene as a child of
  the `weapon_R` entity with `Transform::IDENTITY`.
- **In Blender.** The cannon's rest attach equals the grip frame exactly. Its sockets are recorded on the preview
  object in the grip frame: `grip_R` (0, 0, 0), `grip_L` (−0.186, −0.115, 0.108), `muzzle` (0, 0.8, 0).
- **Sleeve fit.** With the fist clenched, 1,421 right-arm vertices lie inside the sleeve: forearm, vambraces, wrist
  cuff, gauntlet and finger lames. The section in `stage3_weapon.png` shows the forearm and fist in the sleeve.
  - In every cannon pose, **poke-through is 1-5 vertices**: the thumb tip at the sleeve mouth.
  - At bind (open hand) it is 28: the open thumb, as stage 2 found.
- **The sleeve rule holds.** A hand-twist sweep from −90° to +90° leaves 0-1 vertices cut, because the hand's tail
  sits on the forearm axis.
- **Elbow range** (`limits.json` "cannon", the upper arm out 30° and down 20°):

  | Elbow flexion | Cuts by the cannon | What it cuts |
  |---|---|---|
  | 0-20° | 0-1 | nothing |
  | 30° | 8 | the upper-arm plate, inside the elbow crook |
  | 40° | 23 | the upper-arm plate and the lower pauldron lame |
  | 60° | 63 | the same, plus the anvil slab |
  | 90° | 107 | the same |
  | 120° | 505 | the body |

  The rear cuff ends 5 cm in front of the elbow joint. So the right couter rides the forearm (`x_elbow_R` 1.0): a
  couter turning half the bend cut the cuff at any flexion.
- **The inner handle.** The fist closes at `grip_R`. Stage 2 reported that the cannon's inner bar runs along the grip
  Z, across the fingers of a palm-down fist. It is hidden inside the sleeve and changes nothing on the rig.

## 5. Range of motion (`s3_valdris_limits.py`, `stage3/limits.json`, `stage3_limits.png`)

**How it is measured.** Each armour piece is closed, so "one plate cuts another" is exact: a vertex inside another
piece, found by ray parity along two oblique rays and deeper than 3 mm. The nearest-face normal was tried first and
gave false hits at the corners of the boxy plates.

What counts is the change against the rest pose, because shingled lames overlap at rest by design. The new vertices
are sorted into three kinds:

| Kind | Meaning |
|---|---|
| **clipping** | pieces of different regions meet: an arm plate in a pauldron, a knee cop in the anvil |
| **sliding** | lames of one region move against each other, as real plate articulates |
| **suit** | a plate is inside the under-suit |

Each sweep turns one joint from rest.

- **Shoulder** (upper-arm elevation −75..75 × arm out, half forward and forward; pauldron follow 0 / 0.35 / 0.5 /
  0.6 / 0.8; hinge at |x| 0.25 / 0.32 / 0.37).
  - **The pauldron sits directly above the shoulder joint.** Its lowest lame overhangs the arm to the elbow, so a
    raise of only 15° already puts the elbow into it when the pauldron is rigid on the clavicle.
  - **What a follow of 0.6 gives.** With 0.6 and the hinge by the neck, a side raise is clean to 30° and a forward
    raise to 15°.
  - **Past 45°** the forearm meets the pauldron's outer lame whatever the follow.
  - **A higher follow, or a hinge further out,** swings the upright plate toward the head and the braids.
  - **Why elevation only.** A plain Copy Rotation of the arm, the first try, also yawed the pauldron forward into the
    beard when the arm went forward (50 braid vertices).
- **Lowered arm.** It is clean to about −45°. Below that, the rerebrace meets the chest band at the armpit:
  6-10 clipping and 20-35 suit vertices, whatever the follow.
- **Elbow** (left, 0-150°, `x_elbow` 0 or 0.5).
  - Clean to 75°: 22-53 new vertices, most of them the rerebrace at the armpit (the arm is also lowered in this
    sweep).
  - Past 90° the fist reaches the anvil slab: 143-340 vertices.
  - The two settings measure within 20 vertices of each other. 0.5 is kept for the look: the cap stays over the joint
    instead of swinging off with the forearm.
- **Knee** (0-135°). **0 clipping to 90°**, 3 at 105°, 12 at 135°, with or without the helper. At 0.5 the poleyn
  stays over the knee instead of floating off it.
- **Ankle** (foot −30..+40° against the shin). Which bone carries the sabaton's ankle cuff and instep lame decided the
  result:
  - on the foot (stage 2's suggestion): 64 cuts at +20°;
  - on a half-turning helper: 38;
  - on the **shin**: 9.

  So they ride the shin: clean from −10° to +20°. Past +20° the greave and shin plate sink into the foot shell: 42 at
  +30° and 69 at +40°.
- **Hip** (thigh 0-105° with the knee bending, the torso upright or leaning 12°; tasset follow 0 / 0.25 / 0.5 / 0.65;
  the fauld driver on or off).
  - Upright, a higher tasset follow keeps the thigh plate from sliding under the tasset: 0.5-0.65 clean to 45°.
  - Leaning, as in the Siege Stance, it swings the upper tasset into the **anvil's underside**.
  - **0.25** is the compromise, measured on the poses:

    | Tasset follow | Brace | Cannon aim | Guard |
    |---|---|---|---|
    | 0.5 | 207 | 103 | 69 |
    | **0.25** | **171** | **107** | **67** |
    | 0 | 157 | 126 | 85 |

  - Past about 80° the knee cop reaches the anvil whatever the follow.
  - The fauld driver matters only past 60°, where the fauld rides the forward thigh.
- **Head** (neck + head yaw 0-60°, level or nodded 20°; braids at rest on the head). Yaw is clean to about 20°.
  From 25-30° the outer braid meets the pauldron's inner lame: 13 vertices at 20°, 55 at 30°. **A 20° nod drives the
  braids and the beard into the chest band (511).** In the poses the braid chains are posed clear (0 left inside), but
  the chin itself sits on the gorget: the head has almost no nod.
- **Torso twist** (a third on each spine bone, 0-60°). Clipping is 0-3 at every angle. The cuirass bands and the
  anvil's lower gasket slide over the belly band: 37 at 10°, 107 at 40°. That is hidden under the anvil from the
  front. From 55° the anvil's side cuts the belly band.

**Helpers checked by muting them, one at a time, in the loaded poses** (new clipping vertices):

| Pose | All on | All muted | Pauldron muted | Knee muted | Tasset muted |
|---|---|---|---|---|---|
| Siege brace | 171 | 156 | 171 | 170 | 156 |
| Deep squat | 360 | 335 | 360 | 372 | 354 |
| Lunge | 194 | 175 | 194 | 200 | 176 |
| Bulwark raise | 126 | 188 | 188 | 126 | 126 |

- The pauldron and knee helpers clearly help where they act.
- The tasset still costs 15-20 vertices in the leaning poses, where its lift meets the anvil. It is kept at 0.25
  for the upright stance and gait.

## 6. Ranges and rules for stage 4 (Valdris)

These are the clean ranges of his armour. Clips outside them will show plates cutting plates.

| Joint | Clean range | Beyond it |
|---|---|---|
| Upper arm, raised to the side | ≤ 30° above horizontal | the forearm enters the pauldron's outer lame (45°+) |
| Upper arm, raised forward | ≤ 15° | the pauldron front and cap |
| Upper arm, lowered | ≥ −45° (keep the arms out from the body) | the rerebrace into the chest band at the armpit |
| Upper arm, level and straight forward | avoid: aim the arm about 30-40° out | the chest band and the anvil slab |
| Cannon elbow | 0-25° (30-40° acceptable: 8-23 vertices inside the crook) | the rear cuff into the upper-arm plate |
| Left elbow | ≤ 75° with the arm low; the fist must not come in over the anvil | the fist into the anvil slab |
| Knee | ≤ 90° (105° acceptable) | the greave and cuisse lip |
| Ankle | −10° to +20° | the greave into the sabaton; squats past this show it |
| Thigh flexion | ≤ 45° clean; up to 75° acceptable | the knee cop reaches the anvil at about 80° (75° with the torso leaning) |
| Head | yaw ≤ 25°; nod ≤ 5° | the braids into the pauldron; the beard into the gorget |
| Torso twist | ≤ 40° (put it low: spine_01 and the pelvis) | the anvil's side into the belly band |

Rules:
- **Overhead arms** (the Bulwark Slam leap, Mountainfall pounds) are blocked by the pauldrons. They sit right above
  the shoulder joints. The unique clips must **key `x_pauldron_L/R`** (the drive is additive) to swing them up and out
  of the way, or keep the fists in front of the face. The validation raise does the latter (§7).
- **Leave the `x_` bones unkeyed in shared clips.** The contract says shared clips never key `x_` bones. Today
  `s4lib.Rig.keyed` keys every bone but root, the twist bones and the sockets, so it would include his extras. The
  drives are additive, so rest keys are harmless. But the fauld's driver sits on its own `rotation_euler.x` and must
  not be keyed, and cloth chains keyed at rest in every frame would fight the engine's spring. Stage 4 should exclude
  the `x_` prefix from `keyed`. That is a stage-4 change I did not make.
- **The sleeve rule.** The wrist never bends and the hand only twists. The hand bone's tail is on the forearm axis,
  so the twist keeps the barrel coaxial.
- **The keep-out** already finds his sleeve weapon: `PREVIEW_colossus_cannon_R` is in the grip frame.
- **Cloth.** `s3_valdris_cloth.py` (hang + clear) is reusable. Stage 4 can pose the cape, loincloth and braids per
  key with it, or leave them to the engine's spring.

## 7. Validation poses (honest review)

The poses are written with the **stage-4 solver** (`s4lib.Solver`: analytic two-bone IK with the hinge on the lower
bone's X, the sleeve rule, foot placements). Stage 4 inherits the same arm space.

- **Arms** are given as an upper-arm direction and a forearm direction inside the measured ranges.
- **The cannon** stays upright: the back of the hand is up.
- **The cloth** is posed by `s3_valdris_cloth.py` before the pose is measured:
  - each chain bone hangs toward its rest world direction (gravity ramps in along the cape, so its pinned top rides
    the torso);
  - the cloth vertices inside a body or armour piece, or under the ground, turn the bones out, with a cost per
    radian so a chain never swings far to trade one contact for another.

The numbers come from `stage3/poses.json`:
- **clip / slide / suit**: the new vertices of §5 (in brackets, with all helpers muted);
- **cloth**: cape / loincloth / braid vertices inside a piece after the solve;
- **cannon**: poke-through / cuts;
- **suit collapsed**: under-suit vertices whose 1-ring area fell under 40 % (shoulders L / R);
- **stretch**: max / p99.9 in mm.

| Pose | Clip | Slide | Suit | Cloth | Cannon | Suit collapsed | Body volume | Stretch (mm) |
|---|---|---|---|---|---|---|---|---|
| bind | 0 | 0 | 0 | 4 / 2 / 0 (at rest) | 28 / 0 | 0 (0 / 0) | 1.000 | 0 / 0 |
| A-pose | 27 (27) | 75 | 76 | 1 / 2 / 0 | 1 / 1 | 11 (0 / 0) | 1.001 | 24 / 16 |
| cannon aimed | 107 | 279 | 86 | 0 / 3 / 0 | 5 / 13 | 11 (0 / 0) | 0.990 | 29 / 24 |
| guard | 67 | 292 | 55 | 0 / 3 / 0 | 5 / 14 | 11 (0 / 0) | 0.987 | 34 / 23 |
| Siege Stance brace | 171 (156) | 261 | 208 | 0 / 3 / 0 | 5 / 14 | 25 (0 / 0) | 0.957 | 55 / 29 |
| deep squat | 360 (335) | 322 | 203 | 0 / 12 / 0 | 5 / 21 | 36 (0 / 0) | 0.933 | 75 / 37 |
| lunge | 194 (175) | 354 | 169 | 11 / 4 / 1 | 5 / 13 | 21 (1 / 0) | 0.975 | 48 / 28 |
| torso twist 40° | 100 | 326 | 89 | 0 / 3 / 0 | 5 / 13 | 11 (0 / 0) | 0.981 | 33 / 25 |
| head left + down | 44 | 154 | 81 | 1 / 2 / 0 | 1 / 1 | 11 (0 / 0) | 1.000 | 24 / 18 |
| head right + up | 30 | 140 | 88 | 1 / 2 / 0 | 1 / 1 | 11 (0 / 0) | 1.001 | 24 / 18 |
| Bulwark Slam raise | 126 (188) | 164 | 84 | 0 / 2 / 0 | 1 / 29 | 11 (0 / 0) | 0.994 | 39 / 32 |
| forearm twist 100° | 66 | 263 | 50 | 0 / 3 / 0 | 5 / 13 | 11 (0 / 0) | 0.988 | 27 / 24 |
| elbow 145° + knee 135° (bare stress) | 754 | 223 | 557 | 0 / 2 / 0 | – | 33 (3 / 2) | 0.995 | 61 / 31 |

The pose-by-pose numbers are vertex counts on a 25k-triangle model. Most sit on the inner side of a joint, under
another plate. The renders are the judge.

**What holds up.**
- **Shoulders do not collapse under the pauldrons.** In every gameplay pose, 0-1 under-suit vertices collapse at the
  shoulders. The pauldrons lift with a raised arm, and the upright plate by the head barely moves. With the fists
  raised in front of the face (the Bulwark raise), the pauldron helper removes a third of the clipping: 126 against
  188 with it muted.
- **The cannon reads and fits.** In the aim, guard, brace, lunge and twist it points ahead with its glowing muzzle to
  the camera (the in-game sheet). Its sleeve hides the massive forearm, and only the thumb tip shows at the mouth
  (1-5 vertices).
- **Legs and knees.** The knees are clean to 90° (0 clipping). The poleyn covers the knee through the brace, lunge
  and squat. The tassets and fauld swing with the thighs.
- **Cloth.** The cape is clear in 11 of the 13 poses (≤ 1 vertex; bind keeps the 4 rest-pose contacts under the pauldrons,
  the lunge has 11), and the loincloth keeps its 2-3 rest-pose contacts with the fauld.
  The cape hangs vertically on a bent torso, and the braids swing clear of the chest and the pauldrons.
- **At the client camera** (about 114 px tall) every pose reads as a distinct silhouette: the braced turret stance,
  the lunge, the raise with the muzzle up, the aim with the cannon forward.

**What falls short** (for the user's review).
- **The arms live in a narrow space.** Between the protruding anvil, the pauldrons over the shoulders and massive
  plates on a 0.225 m upper arm, there is little room. In the stance poses, 60-110 clipping vertices remain. They are
  mostly:
  - the rerebrace at the armpit and chest band edge, which the camera does not see;
  - the second vambrace touching the lower pauldron lame of the same arm;
  - the couter at the ribs.

  These are the concept's proportions. Real plate this size would lock the same way.
- **The cannon cannot point straight ahead from a relaxed arm.** A straight arm forward goes through the anvil's
  heel, and past 25° of elbow the rear cuff enters the upper-arm plate. The aim poses therefore hold the arm out 38°
  with 33° of elbow and turn the waist 14°: 12-13 vertices inside the crook, hidden. A 5 cm shorter sleeve would give
  the elbow its range. That is the same request made to the gauntlets for Brax.
- **The cannon's brace handle (`grip_L`) is out of reach.** It sits on the sleeve's upper-left, 0.94-0.96 m from the
  left shoulder in the aim poses, against a 0.67 m reach, and the anvil is in the way. Valdris braces with a free
  fist, as in the concept. The Siege Stance validation plants the fist on the left knee. For the weapon track: move
  the handle under the drum's near side, or drop it for him.
- **The head barely nods.** The head is sunk between the pauldrons with the beard on the gorget, so a nod beyond
  about 5° drives the beard and braid roots into the chest band. The poses use 10° with a 25° turn, with the braid
  chains posed clear: 44 clipping vertices, mostly the beard locks at the gorget. Looking down at the horde has to
  come from the neck and a slight torso lean, not the head.
- **Deep squat and lunge.**
  - The greave sinks into the sabaton's foot shell past 20° of ankle: 11-17 vertices per foot.
  - The squat's loincloth bunches between the knees into crumpled strips (12 vertices inside the thighs).
  - The lunge's rear leg pokes through the cape between two chains: 11 vertices.
  - A juggernaut in plate should not squat this deep. The gameplay stances (brace, lunge) show it far less.
- **The torso twist should sit low.** A twist spread over the three spine bones slides the cuirass bands under the
  anvil. It is hidden from the front, but from 55° the anvil's side cuts the belly.
- **The under-suit** is hidden under the plates except at the joints, and its metrics are Brax's: stretch up to
  55-75 mm in the squat, volume 0.93. The **stress pose** (elbow 145° + knee 135°) is not a game pose: the fists end
  inside the pauldrons (754 clipping). It is kept to document the limits.

**Stage-2 findings from stage 3** (not rig problems):
- the gauntlet thumb lames at rest poke out of the cannon mouth (the open hand only);
- the upper-arm lame of the pauldron (on the upper arm) and the upper lame (on the helper) overlap by a few cm, which
  shows as sliding in the raise;
- the tassets end close to the anvil's underside, so they have little room to lift.

## 8. Shared tool changes (backwards compatible) and the Brax regression

| File | Change |
|---|---|
| `s3_skin.py` | an optional per-hero hook: `stage3_skin.json` `"hook": {"module": ...}` imports a module that may drive helpers after the armature is built (`after_armature`), weight parts in mode `"hook"` (`part_weights`), and add a preview weapon (`after_bind`). Without the key, nothing changes |
| `s3_gltf_check.py` | a PREVIEW object carrying `gf_weapon_glb` gets the identity-attach proof with the shipped weapon GLB (its node tree read, pushed through the socket node). Brax's gauntlets keep their own branch |

**Brax regression** (`stage3/brax_regression.json`).
- **How it was run.** Brax's skin and glTF-check steps ran twice in a scratch copy of the repository: once with the
  HEAD scripts, once with the changed ones. Nothing under `art/characters/brax/` was written.
- **Result.** Both reports are identical. The scratch rig GLB and the gauntlet GLBs are **byte-identical**
  (sha256 `e433fad3…`, `3a215a27…`, `bbe8572d…`). The HEAD rerun also reproduces the committed `skin.json`.

Valdris-only files:
- `s3_valdris_run.py`, `s3_valdris_landmarks.py`, `s3_valdris_skin.py` (the hook), `s3_valdris_check.py`,
  `s3_valdris_cloth.py`, `s3_valdris_limits.py`, `s3_valdris_poses.py`, `s3_valdris_sheets.py`;
- `s4lib.py` is only imported, never changed.

## 9. Acceptance checklist

| # | Check | Result |
|---|---|---|
| 1 | GF_Hero_v1, the master skeleton, not forked: identical names, parents, roll, twist drivers, sockets | ✔ built by the shared `gf_hero_rig.build_armature` from his landmark file; hierarchy validated in Blender and in glTF (116 joints) |
| 2 | Landmarks JSON from his mesh, committed | ✔ `work/valdris_landmarks.json`: shared derivation + lame finger joints, hand tip on the forearm axis, chest_sigil on the anvil |
| 3 | Per-character cloth helper bones for the cape (as the contract allows) | ✔ `x_cape` 5 × 5 with grid falloff, pinned under the pauldrons; also `x_loin` 3 × 3 and `x_beard` 5 × 2 |
| 4 | Plates rigid to their bones with blended joints | ✔ 137 armour pieces rigid, one row each; the joint caps ride half-turning helpers (couter, poleyn), the pauldrons lift with the arm's elevation, the under-suit blends at every joint (Brax's rule) |
| 5 | Beard braids to head / neck (optional helpers) | ✔ block and bib on head / neck, braids on `x_beard` chains |
| 6 | `weapon_R` / `weapon_L` at the contract's palm frames; colossus_cannon at an identity transform, fit proven | ✔ 0.28 µm with the shipped GLB; sleeve fit and elbow range measured |
| 7 | Weights: no unweighted vertices, ≤ 4 influences, normalised | ✔ all 12 objects and the GLB |
| 8 | Validation poses: A-pose, cannon aimed forward, guard, deep squat, lunge, twist, head turns, Siege Stance brace; close-up and in-game camera | ✔ 13 poses (+ the Bulwark raise, forearm twist, stress pose); sheets in `stage3/` |
| 9 | Fix plate intersections, collapsing shoulders under the pauldrons, cape penetration | ✔ within the measured ranges: helpers chosen by sweeps, shoulders 0-1 collapsed vertices, cloth solved clear (11 of 13 poses ≤ 1 cape vertex). What remains is listed in §7 and set as stage-4 ranges in §6 |
| 10 | The user's final visual approval | **pending_human** |

## 10. Open items

- **User approval** of the rig (`status.json` → `3_rig.items.user_visual_approval`), and the earlier gates: the
  stage-2 look, the cannon side and anvil, and the head size. The head size matters here too: a larger head above the
  pauldrons would give the neck the range it lacks (§7).
- **Weapon track (colossus_cannon).**
  - Shorten the sleeve's rear end by about 5 cm, so the elbow gets 40°+ clean.
  - Widen the bore for the massive forearm (stage 2).
  - Move or drop `grip_L`, which is out of his reach.
- **Stage 4.**
  - Exclude `x_` bones from `s4lib.Rig.keyed`.
  - Key `x_pauldron` in the overhead unique clips.
  - Keep the §6 ranges; put the torso twist low.
  - Pose or spring the cloth chains.
- **Siege Stance anchor spikes** (brief Q6) are not built. They belong to the Siege Stance clip work: rigid, one bone
  each.
