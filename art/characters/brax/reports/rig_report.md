# Brax — stage 3 rig (GF_Hero_v1), made by AI, 2026-09-25

> **The user's decisions of 2026-09-25, relayed by the workflow coordinator.**
> - There is no human artist at any stage: the AI makes every stage, and the user gives the final visual approval
>   (`status.json` → `3_rig.items.user_visual_approval`, `pending_human`).
> - Weapons are separate models per chassis on hand sockets, so any hero can wield any chassis.
> - Content over tests: validators and review renders are the quality gate.

The skeleton contract every hero shares is [`docs/art/GF_HERO_SKELETON.md`](../../../../docs/art/GF_HERO_SKELETON.md).
This report covers Brax's rig on that skeleton.

Review sheets (all in [`stage3/`](stage3/)):

| Sheet | What |
|---|---|
| [`stage3_skeleton.png`](stage3/stage3_skeleton.png) | the 63 bones over the body, the sockets as RGB = XYZ grip axes, and the dominant bone per vertex |
| [`stage3_poses_1.png`](stage3/stage3_poses_1.png) … [`_3`](stage3/stage3_poses_3.png) | the 13 validation poses: toon full body, clay close-ups (shoulder front/back, elbow, knee, hands, head) with the gauntlets in slate blue, and each pose's numbers |
| [`stage3_ingame.png`](stage3/stage3_ingame.png) | every pose through the client camera (orthographic 55°, 22 m view height, true 1080p pixels) at 1× and 3× |
| [`stage3_weapon.png`](stage3/stage3_weapon.png) | bare hands vs gauntlets (fist clench, guard, forearm twist) and the weapon_L frame |
| [`stage3/*.json`](stage3/) | the measurements: landmarks, MakeHuman seed, skin, poses (+ weapon limits), glTF check |

## 1. Deliverables

| Path | What | Git |
|---|---|---|
| `production/brax_rig.blend` | contents listed below | LFS |
| `work/brax_landmarks.json` | Brax's GF_Hero_v1 landmark file: 69 points, 4 vectors, 4 socket frames, no extras | yes (`git add -f`; the rest of `work/` is local) |
| `stage3_skin.json` | every hand-set skinning number | yes |
| `reports/stage3/` | sheets + JSON | yes |
| `work/brax_s3_mh_seed.npz`, `work/renders/stage3/`, `work/gltf_check/` | the seed weights, full-size renders, scratch GLBs | local (regenerated) |

`production/brax_rig.blend` contains:
- the `GF_Hero_v1` armature: 63 bones, twist constraints installed;
- the 8 skinned stage-2 objects;
- the `GF_ValidationPoses` action, stashed as a muted NLA track with one marker per pose;
- a `PREVIEW_anvil_gauntlets (not exported)` collection. It links the weapon file's meshes (it does not copy them)
  and holds them on the sockets with the identity attach. The fist variant is shown and the open variant hidden.

Rebuild everything with `python tools/blender/gf_hero/run_stage3.py brax`. It takes about 45 s:
landmarks → seed → skin → poses → gltf_check → sheets → contract. The review renders use Cycles on the CPU and
Workbench only.

## 2. Skeleton and landmarks

- The joints are the stage-2 fit's own landmarks. The MakeHuman joints are mapped through Brax's thin-plate
  spline, which reproduces the hand-measured `stage2_fit.json` joints exactly, and the fit's ×1.3 radial hand
  scale is applied on top.
- Every finger joint is then refined to the centre of its finger's cross-section on the fitted mesh (moves of
  3-8 mm). The tips sit 40 % of the finger radius (11-15 mm) inside the fingertips.
- The palm normal comes from the knuckle line: (0.03, -0.02, -1.00), palm down. The thumb curls toward the palm.
- The elbow, wrist and knee stay on the measured hinge line. The elbow ring's centroid is only reported: it sits
  3.6 cm in front of the hinge because the stage-2 elbow bulges forward.

Bone lengths (m):

| Bone | Length | Bone | Length |
|---|---|---|---|
| pelvis | 0.104 | spine_01 | 0.096 |
| spine_02 | 0.086 | spine_03 | 0.415 (to the neck) |
| neck | 0.114 | head | 0.158 |
| clavicle | 0.246 | upperarm | 0.330 |
| lowerarm | 0.325 | hand | 0.136 |
| thigh | 0.580 | shin | 0.502 |
| foot | 0.225 | toe | 0.147 |

Sockets, rest pose, Blender axes:

| Socket | Origin (m) | Frame |
|---|---|---|
| `weapon_L` | (1.01645, 0.03267, 1.7339) | forward +X, up +Z. **Exactly** the stage-2 `hand_frames` the anvil_gauntlets were authored in |
| `weapon_R` | mirror of `weapon_L` | mirrored frame |
| `head_top` | (0, 0.014, 2.199) | the top of the hair |
| `chest_sigil` | (0, -0.174, 1.72) | on the chest surface at the sigil centre (`stage2_texture.json`), forward = the surface normal tilted 11° up |

## 3. Weights

| Object | Rule | Result |
|---|---|---|
| BODY (3,927 v) | **seed**: MakeHuman CC0 game_engine weights, exact per vertex, blended **50/50** with Blender bone-heat on the torso and limbs, **0** heat on the hands, **20 %** on the head; then the twist split and the fixes (details below) | 1-4 influences (497 / 2,118 / 754 / 558 vertices) |
| HAIR, BEARD (with the teeth) | 100 % `head` | 1 influence |
| WRAPS | copy the body at the closest point (tight) | ≤ 4 |
| BELT | the band copies the body; the buckle ring and boss are rigid, one row each | ≤ 4 |
| SASH | the wrap copies the body; below the belt it hangs (as the skirt) | ≤ 4 |
| SKIRT_CLOTH | hang: copies the body at the belt; below that, the pelvis plus the thigh on its side, rising to 85 % thigh at the knee (both thighs at the centre line) | ≤ 4 |
| SKIRT_PLATES (60) | the hang rule, **rigid per plate** (one row per plate): the plates never bend, they swing with the thighs | ≤ 4 |

About the BODY seed:
- The fit keeps hm08's vertex order: 98 % of the base edges survive, and the match distance to hm08 has a median of
  0 and a 99th percentile of 0.9 mm.
- The 166 stage-2 extra-loop vertices take the mean of their neighbours.
- The 104 eyeball vertices go to `head`.

The seed and the heat weights disagree most on `head` (0.36 mean absolute difference), `foot`, `hand`, `neck` and
`spine_03`. That is why the head keeps mostly the seed (its face loops) and the hands keep only the seed (heat is
unreliable on fingers).

Hand-style fixes, in order:
1. **Rest-shape prep.** Stage 2 inserted its knee, elbow and wrist loops at edge midpoints after the fit, so they
   sat on the chords. 102 loop vertices move onto the 4-point subdivision curve of their edge loop (≤ 8 mm).
2. **Twist split.**
   - `upperarm_twist` and `thigh_twist` take the proximal share, fading out by 85 % of the bone.
   - `lowerarm_twist` fades in from 15 % of the forearm to the wrist.
3. **Joint blend bands** (±6-6.5 cm across the joint plane). On the outside of the bend the band moves: the
   knee cap stays with the thigh (+4 cm) and the olecranon with the forearm (-3 cm).
4. **Euclidean smoothing.**
   - The jaw-over-throat fold: σ 1.5 cm. Edges of 1.7 mm between the jaw and the throat carried different
     weights and tore 3-4 cm when the head turned.
   - The shoulders: σ 2.5 cm.
   - The knees: σ 3.5 cm.
5. **Limit and normalise.** 4 influences, weights under 1 % dropped, normalised.

**Checks** (`stage3/skin.json`, `stage3/gltf_check.json`), all met on every object:
- 0 unweighted vertices;
- at most 4 influences;
- sums within 2e-16;
- no weight on `root` or a socket.

In the exported GLB:
- all 63 joints are present;
- the hierarchy matches the contract under the `GF_Hero_v1` node;
- each of the 8 primitives has one JOINTS_0 / WEIGHTS_0 set;
- the weights sum to 1 within 1e-7;
- `extensionsRequired` is empty.

## 4. The weapon on the sockets (the identity attach)

- **In glTF (the engine's truth).**
  1. The rig is exported as stage 5 will export it.
  2. Each fist gauntlet is exported **alone**, with an identity object transform (its authoring frame, as the
     weapon GLB will be).
  3. The gauntlet's glTF vertices are pushed through the `weapon_L` / `weapon_R` node's world matrix.

  They land on the gauntlet held by the rig within **0.9 µm** (L) and **0.7 µm** (R). All four socket nodes equal
  their grip frames within 7e-7. **No correction rotation exists anywhere.** The socket bone's +Y is the grip's up
  and its +Z is the grip's back, which cancels glTF's +Y-up conversion. See the skeleton doc §3.
- **In Blender.** The authored T-pose placement of all four gauntlet objects equals the rest-pose attach within
  1.8e-7.
- **Coverage.** With the fist clenched, all 553 forearm and hand vertices per side are covered by the fist
  gauntlet at rest.

Weapon limits, measured by `s3_poses.py` on the left arm with the fist gauntlet (`poses.json → weapon_limits`):

| Joint | Clean range (0 vertices out / in) | ≤ 2 vertices |
|---|---|---|
| elbow flexion | 0-30° | 0-40° |
| wrist extension / flexion | 0° | -10-0° |
| wrist radial / ulnar deviation | -5-0° | -10-5° |
| forearm twist | -100-60° | ±120° (full sweep) |

What these limits mean:
- **The anvil_gauntlets are a sleeve weapon.** Rigid on the hand, they enclose the whole forearm, so **the wrist
  must stay straight** (twist only). The validation poses aim the hand along the forearm, and **poke-through there
  is 0-3 vertices per arm**, all at the elbow end.
- **The elbow cuff overlaps the elbow joint by 2 cm.** From about 40° of flexion it presses into the biceps: 12-17
  vertices at the punch, guard, squat and fist-clench bends. In the close-ups this reads as the arm entering the
  cuff. It is a weapon-geometry limit, not a skinning one. **Recommendation to the weapon track:** end the sleeve
  about 4 cm before the elbow joint, or flare the cuff's rim.
- **Animation rule** (stage 4): gauntlet clips keep the wrist straight. The fist variant goes with the body's fist
  clench (the thumb folds across the fingers).

## 5. Validation poses (honest review)

Numbers from `stage3/poses.json`:
- **stretch**: mm of edge growth;
- **±40 %**: edges over 5 mm that grew or shrank by more than 40 %;
- **collapsed**: vertices whose 1-ring area fell under 40 %;
- **forearm**: the mean ratio of the distal forearm radius.

| Pose | Stretch max / p99.9 (mm) | +40 % / -40 % edges | Collapsed | Body volume | Forearm L | Gauntlet poke / cut (L) |
|---|---|---|---|---|---|---|
| bind (open gauntlets) | 0 / 0 | 0 / 0 | 0 | 1.000 | 1.00 | – |
| A-pose | 26 / 20 | 88 / 88 | 14 | 0.993 | 1.00 | 0 / 0 |
| punch, both | 44 / 36 | 167 / 116 | 18 | 0.938 | 1.00 | 2 / 12 |
| guard | 45 / 37 | 172 / 102 | 15 | 0.932 | 0.95 | 1 / 16 |
| deep squat | 50 / 40 | 235 / 156 | 34 | 0.864 | 1.00 | 2 / 17 |
| lunge + right cross | 60 / 44 | 197 / 167 | 32 | 0.865 | 0.95 | 0 / 0 |
| torso twist (55°) | 30 / 25 | 108 / 110 | 20 | 0.974 | 1.00 | 2 / 9 |
| head left + down | 28 / 25 | 114 / 95 | 14 | 0.991 | 1.00 | 0 / 0 |
| head right + up | 44 / 27 | 126 / 90 | 14 | 0.992 | 1.00 | 0 / 0 |
| fist clench | 38 / 26 | 122 / 100 | 16 | 0.973 | 1.00 | 3 / 16 |
| uppercut (left arm overhead) | 40 / 28 | 108 / 97 | 16 | 0.988 | 0.92 | 0 / 1 |
| forearm twist 100° | 43 / 35 | 154 / 124 | 27 | 0.938 | 0.90 | 1 / 4 |
| elbow 145° + knee 135° (bare) | 97 / 46 | 166 / 114 | 23 | 0.934 | 1.00 | – |

**What holds up.**
- **Shoulders in the A-pose and the uppercut.** The deltoid stays round and the armpit does not collapse under
  the raised arm. The pec below it wrinkles slightly.
- **Elbows to about 90°.** The fist-clench elbow is clean in profile.
- **Wrists and forearm twist: no candy-wrapper.**
  - At 100° of twist the distal forearm keeps 90 % of its radius on average (85 % at the worst vertex).
  - The uppercut's 90° twist keeps 92 %.
  - This is the limit of linear blend skinning with one forearm twist bone at 65 %.
- **Head turns.** The jaw fold stays closed.
- **Fists.** The fist clench reads as a closed fist. The knuckle webbing folds inside, and the gauntlet hides it.
- **The lunge.** Knees and hips hold. The skirt plates lie on the forward thigh.
- **At the client camera** (`stage3_ingame.png`, about 60 px tall) every pose reads cleanly. The punches, the
  guard, the squat and the uppercut read as distinct silhouettes.

**What falls short** (for the user's review):
- **Front-shoulder crease with the arms forward.** In the punch and the guard a sharp fold runs from the pec to
  the deltoid (the anterior axillary crease). Wider smoothing (σ 4 cm) did not remove it and made the metrics
  worse, so it stays. It is visible only in close-ups.
- **Knees past ~110°.**
  - In the deep squat the knee cap flattens into planes and the inner back of the knee pinches.
  - At 135° (the bare stress pose) a small fold opens at the front of the knee.
  - The joint bands and the smoothing reduced this but did not remove it.
  - Part of it is stage-2 topology: the knee's extra loops left a pinched pole beside the knee cap. It is visible
    at rest as a dimple, and the loop-profile fix does not reach it.
  - The gameplay range (running, the lunge) is clean.
- **Body volume 0.86 in the squat and the lunge.** The thighs press into the belly and the calves into the thighs.
  This is contact, not collapse. The metric counts the overlap.
- **Cloth.**
  - The rigid plates follow the thigh on their side. That holds in the lunge and the squat.
  - With a 112° high knee, the raised thigh still passes through part of the underskirt.
  - The sash's long front tails (down to 0.21 m) hang from the pelvis. The tail on the raised leg's side follows
    it; the other hangs straight.
  - Real draping needs secondary `x_` bones (driven or sprung in the engine), a stage-4 item.
- **Gauntlet cuff vs biceps.** See §4: a weapon-geometry limit.

**Stage-2 defects that stage 3 exposed** (not rig problems; listed so stage 2 can be polished):
- **Ankle wraps.** The skin shows through the ankle wraps at the back of the ankle already at rest.
- **Elbow shape.** The elbow is a ball wider than the forearm and upper arm (radius +2.5 cm at |x| 0.6), with a
  groove above it. It is hidden under the gauntlet cuff and visible bare-armed.
- **Knee dimple.** The pinched pole by the knee cap, above.
- **Extra loops placed on chords.** The stage-2 extra loops sit on the chords. Stage 3 corrects this on the rest
  shape (§3.1). `s2_body_fit.py` should place them with the same 4-point rule.

## 6. Acceptance checklist

| # | Check | Result |
|---|---|---|
| 1 | One master skeleton adapted from AC_Player_Humanoid_v1: identical core names, parents and roll, twist bones driven by Copy Rotation, 15-bone hands, deform flags | ✔ `gf_hero_rig.py`; hierarchy validated in Blender and in the exported glTF |
| 2 | Sockets: `weapon_R` / `weapon_L` at the grip frame (identity attach), `head_top`, `chest_sigil`; `root` at the feet with no root motion | ✔ identity attach proven with the real weapon: < 1 µm |
| 3 | Contract documented for every hero through a landmark JSON only | ✔ `docs/art/GF_HERO_SKELETON.md`; `check_skeleton.py` in CI |
| 4 | Brax's landmarks from the stage-2 fit | ✔ `work/brax_landmarks.json` |
| 5 | MakeHuman CC0 seed + automatic weights + hand-style fixes; rigid parts; hair and beard on the head | ✔ §3 |
| 6 | No unweighted vertex, ≤ 4 influences, normalised | ✔ on all 8 objects and in the GLB |
| 7 | Validation poses (A-pose, punch, guard, squat, lunge, twist, head turns, fist) with the gauntlets on the sockets, close-up and at the in-game camera | ✔ 13 poses, sheets in `stage3/` |
| 8 | Candy-wrapper, collapsing shoulders, gauntlet/forearm intersections fixed | ✔ no candy-wrapper (≥ 0.85 radius at 100°); shoulders hold volume with a front crease (§5); straight-wrist poses: 0-3 vertices at the elbow end. The elbow cuff presses into the biceps (a weapon limit, §4) |
| 9 | The user's final visual approval | **pending_human** |

## 7. Open items

- **User approval** of the rig (`status.json` → `3_rig.items.user_visual_approval`).
- **`docs/art/WEAPONS.md` §7** calls the right socket `weapon_socket_R` (the Ashen Covenant name). The contract
  name is `weapon_R` / `weapon_L`. §7's axis choice matches this rig, so only the name must change. That file is
  the armory agent's.
- **Weapon track, anvil_gauntlets.**
  - The elbow cuff overlaps the elbow joint: shorten the sleeve about 4 cm or flare the cuff.
  - Stage 5 exports the left gauntlet as the `offhand` node, authored in its own left grip frame.
- **Stage 2 polish.** The knee pole, the elbow ball and groove, the ankle wraps, and the loop placement in
  `s2_body_fit.py` (§5).
- **Stage 4.**
  - Secondary `x_` bones for the sash tails and the underskirt.
  - A retarget test between two heroes once the second hero (Valdris) is rigged (the Ashen Covenant p07 step).
