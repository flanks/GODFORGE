# GODFORGE: GF_Hero_v1, the master hero skeleton

Every playable hero (Brax now; Valdris, Selene, Kael, Thessaly and the rest later) uses **one skeleton**:
`GF_Hero_v1`. Bone names, parents, roll, deform flags and socket frames are fixed. Only the bone
**positions** change from hero to hero, and they come from that hero's landmark file. One animation clip
therefore drives every hero, and any weapon attaches to any hero.

The contract lives in code, in [`tools/blender/gf_hero/gf_hero_rig.py`](../../tools/blender/gf_hero/gf_hero_rig.py).
That file holds the tables, the builder and the checks. This page explains them; if the two disagree, the
code wins, so fix this page.

**Credit.** GF_Hero_v1 is adapted from the user's Ashen Covenant `AC_Player_Humanoid_v1`
(`D:/Ashen_Covenant/tools/blender/ac_player_rig/`), which is proven there all the way from landmarks to
game import. The following are identical to that rig:
- the 23 core bones: names, parents and connection;
- the 6 twist bones and their Copy Rotation drivers;
- the 15-bone hands;
- the roll convention;
- the deform flags.

The GODFORGE changes are:
- the socket set, built from full frames;
- the roll fallback for bones parallel to the roll target (from `ac_rig_base.py`);
- the twist extraction order;
- plain-data tables that need no Blender.

## 1. Conventions

| | |
|---|---|
| Units | 1 Blender unit = 1 m |
| Axes (Blender) | Z up. The hero faces **-Y**, so +X is the hero's **left**. Feet stand on z = 0, and the origin sits on the ground between the feet |
| Axes (glTF / Bevy) | exported with +Y up: Blender (x, y, z) becomes glTF (x, z, -y). The hero faces glTF **+Z** |
| Rest pose | the stage-2 **T-pose**: arms straight along ±X with palms down, fingers straight, legs straight. Everything is symmetric about x = 0 |
| Armature object | named **`GF_Hero_v1`** in every hero file. Bevy builds `AnimationTargetId`s from bone-name paths starting at the animation root, so a hero-specific name would break clip sharing |
| Bone axes | local +Y runs along each bone |
| Roll, core and twist bones | local +Z faces the hero's front (world -Y). On **both** sides: +X swings the child forward (shoulder, elbow and hip flexion, spine bend); knee flexion is -X; Y twists; Z swings toward world +X. Left and right are built identically, never mirrored. A bone (almost) parallel to -Y (`root`, the toes) rolls its +Z to world up instead |
| Roll, fingers | +Z points along the palm normal (landmarks `palm_normal_L/R`), so **+X curls toward the palm** on both hands. Thumbs roll to `thumb_curl_L/R` |
| Mirroring a pose | a left rotation (x, y, z) in degrees becomes the right rotation **(x, -y, -z)**. With the arms in the T-pose, +Z raises the left arm and lowers the right one |
| Deform flags | every runtime bone has `use_deform = True`, so the glTF exporter keeps it: core, twist, fingers, sockets and per-hero `x_` extras. A control rig, if one is ever added, must be `use_deform = False` |
| Influences | at most **4 per vertex**. Weights under 1 % are dropped and the rest normalised. No unweighted vertex |

## 2. Bones (63)

### Core (23): identical to AC_Humanoid_Enemy_v1 / AC_Player_Humanoid_v1

| # | Bone | Parent | Head landmark | Tail landmark | Weighted | Role |
|---|---|---|---|---|---|---|
| 1 | `root` | (armature) | `root` | `root_tip` | no | ground point between the feet; never keyed (no root motion), never weighted |
| 2 | `pelvis` | `root` | `pelvis` | `spine_01` | yes | hips; carries the body's translation in clips |
| 3 | `spine_01` | `pelvis` | `spine_01` | `spine_02` | yes | lower back |
| 4 | `spine_02` | `spine_01` | `spine_02` | `spine_03` | yes | mid back |
| 5 | `spine_03` | `spine_02` | `spine_03` | `neck` | yes | chest, up to the neck |
| 6 | `neck` | `spine_03` | `neck` | `head` | yes | neck |
| 7 | `head` | `neck` | `head` | `head_tip` | yes | head: face, hair, beard, eyes (no facial rig) |
| 8, 12 | `clavicle_L/R` | `spine_03` | `clavicle_*` | `shoulder_*` | yes | collarbone, shoulder shrug |
| 9, 13 | `upperarm_L/R` | `clavicle_*` | `shoulder_*` | `elbow_*` | yes | upper arm |
| 10, 14 | `lowerarm_L/R` | `upperarm_*` | `elbow_*` | `wrist_*` | yes | forearm (elbow hinge) |
| 11, 15 | `hand_L/R` | `lowerarm_*` | `wrist_*` | `hand_*_tip` (the middle knuckle) | yes | hand (wrist) |
| 16, 20 | `thigh_L/R` | `pelvis` | `hip_*` | `knee_*` | yes | thigh (hip joint) |
| 17, 21 | `shin_L/R` | `thigh_*` | `knee_*` | `ankle_*` | yes | shin (knee hinge) |
| 18, 22 | `foot_L/R` | `shin_*` | `ankle_*` | `ball_*` | yes | foot (ankle) |
| 19, 23 | `toe_L/R` | `foot_*` | `ball_*` | `toe_*_tip` | yes | toes |

The spine is connected: `spine_03` ends at the neck joint, and every limb chain is connected.
Clavicles and thighs start away from their parent's tail.

### Twist (6): driven, never keyed

| Bone | Parent | Span | Driver (Copy Rotation, Y only, local to local, mix ADD, Euler YXZ) |
|---|---|---|---|
| `upperarm_twist_L/R` | `upperarm_*` | shoulder → mid upper arm | **-50 %** of `upperarm_*`'s twist: the skin near the shoulder twists less than the arm |
| `lowerarm_twist_L/R` | `lowerarm_*` | mid forearm → wrist | **+65 %** of `hand_*`'s twist: pronation and supination happen in the forearm |
| `thigh_twist_L/R` | `thigh_*` | hip → mid thigh | **-50 %** of `thigh_*`'s twist |

The glTF exporter samples the constraints, so every clip carries the right twist and the engine needs no
constraint of its own. Clips never key twist bones. Skin weights ramp onto each twist bone along the limb:
- the upper arm and thigh fade out from the joint;
- the forearm fades in toward the wrist.

### Hands (15 per side)

`thumb/index/middle/ring/pinky` × `_01.._03` × `_L/_R`, each chain parented to `hand_*`. Landmarks
`<finger>_<side>_01..03` and `<finger>_<side>_tip`. The fist used by the validation poses and the weapon
reference is +X 80 / 95 / 60° on the four fingers, with the thumb at (40, 0, ∓30), 45 and 35°
(`s3_pose_set.fist`).

### Sockets (4): exported, never weighted, never keyed

| Socket | Parent | Origin | forward (grip +Y) | up (grip +Z) | Used for |
|---|---|---|---|---|---|
| `weapon_R` | `hand_R` | palm centre | along the fingers | out of the back of the hand | the weapon scene's root (its `grip_R`) |
| `weapon_L` | `hand_L` | palm centre | along the left fingers | out of the back of the left hand | off-hand meshes: the `offhand` node, the left gauntlet of a pair |
| `head_top` | `head` | top of the head silhouette, hair included | the face's forward | up | name plate, status icons, head VFX |
| `chest_sigil` | `spine_03` | the chest surface at the emblem (Brax: the furnace sigil) | out of the chest | along the spine | chest VFX, beams, auras |

For the two weapon sockets, the grip frame is the frame of the weapon contract:
- `docs/art/WEAPONS.md` §2;
- the `anvil_gauntlets` README.

The palm centre is the mean of the hand's surface between the wrist joint and the knuckle line.
Stage 2 records it per hero in `reports/stage2/body_fit.json` (`hand_frames`).

Other sockets (feet, back, hips) are appended only when a chassis or VFX needs them, and they follow the same
frame rule. **A contract bone is never renamed or reparented.**

**Per-hero extras.** Leaf chains prefixed `x_` (for example `x_sash_front_01`) may hang off any core bone
for cloth, hair or tails. They are deform bones and may be weighted. Shared clips never key them; they are
driven, simulated in the engine, or keyed only by that hero's unique clips. Brax has none yet.

## 3. Socket frames and the identity attach (the glTF axis mapping)

A weapon GLB is authored in its **grip frame**:
- origin at the palm centre;
- **+Y** along the barrel / fingers;
- **+Z** up / out of the back of the hand;
- +X = Y × Z.

It is exported with +Y up, so a grip-frame point (x, y, z) is stored as **(x, z, -y)**. The weapon's root node
is then:
- **-Z = forward**;
- **+Y = up**;
- **+X = right**.

The glTF exporter keeps Blender's **bone-local axes** as they are. So each socket bone is built with:

| Socket bone axis (Blender) | = grip frame axis | = in glTF (node-local) |
|---|---|---|
| +X | +X (right) | +X |
| +Y (the bone points this way) | +Z (up / back of the hand) | +Y |
| +Z | -Y (backward) | +Z, so -Z is forward |

The socket node's local frame in glTF **is** the weapon's root frame. **Any weapon GLB attaches to a socket
as an identity child. No correction rotation, anywhere.**
- In Blender, where the weapon object keeps its authoring axes, it sits at
  `arm.matrix_world @ pose_bone.matrix @ SOCKET_TO_GRIP`, where `SOCKET_TO_GRIP` is -90° about X. That is
  exactly the +Y-up conversion. `gf_hero_rig.grip_matrix()` computes it.
- The rig file's PREVIEW objects use a Child Of constraint with that inverse matrix.
- In T-pose every socket bone points straight up.

**Proof (Brax, `art/characters/brax/reports/stage3/gltf_check.json`).**
1. The rig is exported the way stage 5 will export it.
2. Each fist gauntlet is exported **alone** in its authoring frame, with an identity object transform, as the
   weapon GLB will be.
3. The gauntlet's glTF vertices are pushed through the exported `weapon_L` / `weapon_R` node's world matrix.

The result lands on the gauntlet held by the rig to within **< 1 µm** (both sides), and all four socket nodes
match their grip frames to within 1e-6.

Mirrored hands have mirrored frames, and both frames are right-handed. With both arms forward and palms down,
a weapon's +X faces the hero's right in **either** hand, so a one-handed weapon moved to the left hand stays
un-mirrored.

A pair such as the anvil_gauntlets ships a **left mesh** that is the mirror image of the right mesh, authored
in the left frame.

**Name note.** `docs/art/WEAPONS.md` §7 (the armory contract) calls the right socket `weapon_socket_R`, which
is the Ashen Covenant name. The GODFORGE skeleton uses **`weapon_R` / `weapon_L`**, as `docs/ART_PIPELINE.md`
and the weapon packs do. §7's preferred choice matches this rig: socket +Y = up in the hold, +Z back along the
aim, identity attach. Only the bone name differs, and the armory agent should update it.

## 4. How the engine attaches things (for the engine agent; the art track does not edit `crates/`)

1. **Load the hero.** Spawn `SceneRoot(assets.load("models/characters/<key>.glb#Scene0"))`. Every glTF node,
   bones included, becomes an entity with a `Name`. Once the scene is spawned (`SceneInstanceReady`), look up
   the descendants named `weapon_R`, `weapon_L`, `head_top` and `chest_sigil`.
2. **Weapon.**
   - Spawn `SceneRoot(assets.load("models/weapons/<chassis>.glb#Scene0"))` as a child of the `weapon_R`
     entity, with **`Transform::IDENTITY`**.
   - Dual weapons and gauntlet pairs: re-parent the weapon scene's `offhand` node, the left gauntlet, to
     `weapon_L`, also with `Transform::IDENTITY`.
   - Two-handed weapons: the weapon scene's `grip_L` node (world transform) is the left hand's IK target.
   - The weapon scene's `muzzle` node is the projectile / strike origin.
3. **Animation.**
   - Shared clips are authored on GF_Hero_v1 and baked per hero (§6); the target ids match across heroes.
   - Sockets are ordinary joints: they ride on their parents. No clip keys them.
   - Recoil, aim offsets and hit flinches stay procedural (ARCHITECTURE §9) and act on core bones or on the
     weapon entity.
4. **UI / VFX.**
   - `head_top`: the world position for name plates, and heat and status icons.
   - `chest_sigil`: the world transform for the Meltdown / Heat emissive VFX and beams (-Z = out of the chest).

## 5. The landmark file: how a hero plugs in

A hero supplies one JSON: `art/characters/<key>/work/<key>_landmarks.json`. It is committed; `work/` is
otherwise local. It lists:
- **points** in metres, in the rest pose: every head/tail key in §2 (`root`, `root_tip`, `pelvis`, `spine_01..03`,
  `neck`, `head`, `head_tip`, `clavicle_*`, `shoulder_*`, `elbow_*`, `wrist_*`, `hand_*_tip`, `hip_*`, `knee_*`,
  `ankle_*`, `ball_*`, `toe_*_tip`, and the finger joints). The `*_mid` twist points are computed when absent;
- **vectors**: `palm_normal_L/R` and `thumb_curl_L/R` (unit);
- **`sockets`**: `{name: {"origin", "forward", "up"}}` for the four sockets;
- **`extra_bones`**: `[name, parent, head, tail]`, names prefixed `x_`;
- **`_meta`**: `contract: "GF_Hero_v1 v1"`, the inputs and their sha256.

`gf_hero_rig.validate_landmarks` rejects the file when:
- a key is missing;
- a bone is shorter than 4 mm;
- a vector is not unit length;
- a socket frame's forward and up are not perpendicular;
- the rest pose is asymmetric (left/right pairs must be mirror images within 2 mm);
- a weapon socket is off its hand;
- an extra bone is not prefixed `x_`.

For heroes built by the stage-2 chain (MakeHuman hm08 fitted to a sculpt), `s3_landmarks.py` derives the file:
- **joints**: the MakeHuman joints mapped through the hero's own stage-2 thin-plate spline, plus the fit's
  radial hand scale;
- **finger joints**: refined to each finger's cross-section on the fitted mesh;
- **palm normal and thumb curl**: from the knuckle line;
- **weapon sockets**: the stage-2 `hand_frames`;
- **`head_top`**: from the head parts;
- **`chest_sigil`**: from the chest surface.

A hero built another way (for example a bulky armoured Valdris with a sculpted, non-MakeHuman body) writes the
same JSON by any means. Only the file is the contract. For armour:
- rigid plates weight 100 % to one bone, or take one blended row per piece (`stage3_skin.json` `rigid_pieces`);
- skirts and tabards use the hang rule;
- a pauldron that must not follow the arm is weighted to `clavicle_*` / `spine_03`.

## 6. The stage-3 chain (per hero)

```sh
python tools/blender/gf_hero/run_stage3.py <key>        # [--from <step>] [--only <step>], about a minute
```

| Step | Script | Output |
|---|---|---|
| landmarks | `s3_landmarks.py` | `work/<key>_landmarks.json` (committed) + `reports/stage3/landmarks.json` |
| seed | `s3_mh_seed.py` | MakeHuman CC0 game_engine weights, exact per BODY vertex (hm08 topology; MPFB is used only as a tool) |
| skin | `s3_skin.py` | `production/<key>_rig.blend` (Git LFS) + `reports/stage3/skin.json` |
| poses | `s3_poses.py` + `s3_pose_set.py` | the validation poses with the signature weapon on the sockets: metrics, weapon limits, renders; the action `GF_ValidationPoses` stashed (muted) in the rig file |
| gltf_check | `s3_gltf_check.py` | a scratch GLB read back: joints, hierarchy, ≤ 4 influences, weights sum, socket frames, the identity attach with the real weapon |
| sheets | `s3_sheets.py` (PIL) | `reports/stage3/stage3_{skeleton,poses_N,ingame,weapon}.png` |
| contract | `check_skeleton.py` (stdlib) | the same check CI runs (`.github/workflows/art.yml`) |

The per-hero numbers live in `art/characters/<key>/stage3_skin.json`:
- the heat / seed mix per region;
- the twist ramps;
- joint blend bands (knee cap with the thigh, olecranon with the forearm);
- spatial smoothing (jaw-over-throat folds, shoulders, knees);
- a rest-shape relax of folding dimples;
- how each separate part is weighted: `head`, `copy` (tight parts), `hang` (skirt cloth: copies the body at the
  top, then hangs from the pelvis and follows the thigh on its side), and rigid pieces.

**The weight rule for the body:**
1. the seed (MakeHuman CC0 weights, exact on hm08-derived bodies) or bone heat;
2. blended as `stage3_skin.json` says;
3. the twist split;
4. the fixes;
5. then limit to 4 and normalise.

Brax's results: `art/characters/brax/reports/rig_report.md`.

## 7. Rules for animators (stage 4) and weapon makers

- **FK on the core bones only.** Never key `root`, the twist bones or the sockets. Clips are in place: `pelvis`
  carries the translation and the engine moves the entity.
- **The validation set is the reference range.** `s3_pose_set.py` holds it: A-pose, punches, guard, deep
  squat, lunge, torso twist, head turns, fist clench, uppercut, forearm twist, and a bare maximum of 145° elbow
  and 135° knee. The weights hold up through that range. The known soft spots are listed in the hero's report:
  a front-shoulder crease with the arms forward, and a flattened knee cap beyond about 120° of flexion.
- **Sleeve weapons** are weapons that enclose the forearm (the anvil_gauntlets, arm cannons). They are rigid on
  the hand socket, so:
  - **keep the wrist straight**: bend 0°, twist free. In straight-wrist poses at most 3 vertices at the elbow end
    leave the sleeve; a 5-10° wrist bend already pushes the forearm through it;
  - the gauntlet's elbow cuff overlaps the elbow joint, so it presses into the biceps beyond about 30-40° of
    elbow flexion.

  `reports/stage3/poses.json` → `weapon_limits` has the measured ranges. A weapon maker can widen them by
  ending the sleeve about 4 cm before the elbow joint, or by flaring the cuff.
- **Fist variants.** When a weapon's closed-fist variant is shown, the hand bones play the fist clench (the
  fingers must be inside the fist mesh). The open variant needs the fingers extended.
- **Retargeting from other rigs** (Mixamo / ActorCore stand-ins): map onto the core names and let the twist
  bones drive themselves.
