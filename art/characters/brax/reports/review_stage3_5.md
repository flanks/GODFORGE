# Brax, stages 3-5: adversarial review

2026-09-26, AI (Claude). Scope: stage 3 (`4a7d54c`, the GF_Hero_v1 rig and weights), stage 4 (`fca2a2a`, the 34
clips) and stage 5 (`6b4a358`, the shipped `brax.glb`, its sidecar and the gauntlets). The job was to refute each
claim, fix what is confirmed, and keep the pipeline honest. The user's visual approvals of stages 3, 4 and 5 stay
`pending_human`: nothing here is final.

**Verdict.**
- **Stage 3 holds.** The skeleton, sockets, weights and the identity weapon attach all check out independently.
- **Stage 4 had real defects, and its checks did not see them.**
  - Elbows folded to 173-179°, crushing the gauntlet into the shoulder, head or chest.
  - A knee folded to 172°.
  - Between key frames the gauntlets went through thighs, knees, the chest and the belt: up to 416 solid-body
    vertices inside one gauntlet.

  All three are fixed in the shared solver, so every future hero gets the fix. Three key poses were retouched, the
  clips re-baked, and the clip gate now catches all three defect classes.
- **Stage 5 reproduces byte for byte from a clean checkout.** It was re-exported after the fixes.

## Claims checked

| Claim (stage) | Verdict | Evidence (details below) |
|---|---|---|
| The chain rebuilds from a clean checkout; re-export is byte-identical (5) | **holds** | §1: fresh worktree of `122f07f`, stage 2 base → 3 → 4 → 5 gives the same `brax.glb` and `anvil_gauntlets.glb` sha256 |
| No hard-coded machine paths (3-5) | **holds, with two rough edges fixed** | §1: `$BLENDER` / `$COMFY_PY`; fresh-clone bootstrap added |
| 63 joints, parents, roll, sockets as in `GF_HERO_SKELETON.md` (3) | **holds** | §2: typed from the doc, checked against the GLB |
| Weights: ≤ 4 influences, normalised, nothing unweighted, sockets / root unweighted (3) | **holds** | §2 |
| Any weapon attaches as an identity child of its socket (3) | **holds** | §2: the hands sit inside the open gauntlets at rest (191/191 vertices), and the fingers stay inside the gauntlet in every frame of every clip |
| Clip names = `required_clips.json`, 30 fps, in place, loops closed (4, 5) | **holds** | §2 |
| Planted feet slide ≤ 0.9 mm (4) | **holds** | §2: 0.0-0.2 mm with a 3 mm contact test |
| One-shot upper-layer clips start and end on `idle_combat` frame 0 (4) | **holds** (≤ 3e-8 m) | §2. `fire_charge@loop` does not: it's a held loop, and the doc now says so |
| The clips stay inside the stage-3 validated range (elbow 145°, knee 135°) (4) | **refuted, fixed** | §3.1: elbows 172.7° (`dash`), 179.4° (`death`), 173.3° (`uppercut`); knee 171.7° (`get_up`) |
| "Gauntlet cutting into the body: at most 58 vertices per frame, mostly the elbow cuff" (4) | **refuted, fixed** | §3.2: every frame, the cavity included: 958 foreign vertices in `get_up`, 413 in `uppercut`, 377 in `death`, 303 in `meltdown_start`, 191 in `run` |
| Key poses read at game size; the gauntlets lead the silhouette (4, 5) | **holds from the front and side; weak from behind** | §4 |
| status.json / manifest.json are truthful; nothing over 20 MB outside LFS | **status holds; manifest was stale (fixed); LFS holds** | §5 |

## 1. Reproducibility

- **Clean checkout.** A fresh `git worktree` of `122f07f` (scratch, outside the repo) ran the documented commands:
  1. `python tools/blender/gf_hero/run_stage5.py brax` (56 s);
  2. then the whole chain: `run_stage2.py brax --only base` (8 s), `run_stage3.py brax` (102 s),
     `run_stage4.py brax --only anim|gltf_check|contract` (25 s) and `run_stage5.py brax --only export|validate` (33 s).

  Both times `brax.glb` (sha256 `13ebdcf7…`) and `anvil_gauntlets.glb` (`32523398…`) came out **byte-identical**.
  The JSON reports differ only in `updated` / `generated` / `built` dates and `seconds` timings. The rig and animation
  `.blend` files differ in bytes only; Blender stores save timestamps.
- **Paths.**
  - `BLENDER` and `COMFY_PY` were environment-overridable already.
  - The Pillow-sheet Python defaulted to a path on the dev machine. It now falls back to the running Python
    (`run_stage3/4/5.py`).
  - `run_stage3.py` needed two gitignored stage-2 intermediates (`work/<key>_s2_mh_landmarks.json`,
    `work/<key>_s2_body_base.blend`), so it failed on a fresh clone. It now rebuilds them itself: `run_stage2.py <key>
    --only base`, deterministic, 4 s. Tested on the clean worktree.
  - `D:/Ashen_Covenant/…` appears only in credit comments.
- **Not verifiable here.** The CI job `hero-glb` downloads Blender 5.2 for Linux; it has not run on GitHub because
  nothing is pushed.
- **Nit, not fixed.** Every rerun on a new day rewrites the date fields in the sidecars, `brax_landmarks.json` and the
  reports, so an unchanged rebuild still dirties the tree. The GLBs themselves stay byte-identical.

## 2. The shipped file, audited independently

The audit is new code (`tools/blender/gf_hero/review/`):
- a glTF-spec reader with forward kinematics and linear blend skinning in numpy, the maths Bevy runs;
- the weapon as an identity child of its socket, and `offhand` re-parented to `weapon_L`;
- the expected skeleton typed from `GF_HERO_SKELETON.md` §2;
- every frame of every clip (1,113 frames).

Nothing is shared with `export_glb.py` or `validate_glb.py`. Results on the file shipped at `6b4a358` (the numbers
are unchanged after the fixes unless stated):

- **Skeleton.**
  - 63 joints, every parent as documented, one scene root `GF_Hero_v1`.
  - Inverse bind matrices equal the rest pose within 1.1e-6; the T-pose is left/right symmetric within 4.2e-7 m.
- **Sockets.**
  - `weapon_R` / `weapon_L` point -Z along the fingers and +Y out of the back of the hand.
  - `head_top` and `chest_sigil` face the hero's front.
  - All four match the sidecar within 4.4e-6.
- **Weights.**
  - 12,539 exported vertices by influence count (1/2/3/4): 3,199 / 5,116 / 2,079 / 2,145.
  - Weight sums off by at most 1.2e-7; no unweighted vertex; the smallest weight is 1.005 %.
  - `root` and the sockets carry no weight; all six twist bones do.
- **Weapon fit.**
  - At rest, all 191 hand vertices per side are enclosed by the open gauntlet.
  - In every frame of every clip, no finger vertex leaves the gauntlet variant the sidecar shows.
- **Clips.**
  - The 34 names equal `required_clips.json`, with `@loop` exactly on the loops.
  - Frame counts match the sidecar.
  - `root` and the sockets hold their rest transform; only `pelvis` translates.
  - Loop seams close within 1.4e-7 m; the seam is never rougher than the inside of the clip (ratio ≤ 1.00).
  - Joint scale samples are up to 8.6e-5 off 1: matrix-decomposition noise, harmless.
- **Feet.**
  - With a 3 mm contact test, planted balls drift at most 0.2 mm.
  - A first pass with a 10 mm test reported "slides" of 18 mm (strafes), 67 mm (backpedal) and 12 mm (death). The
    per-frame dump shows these are take-off and landing frames, 6-9 mm above the ground and moving at 2-4 m/s, not
    planted feet.
- **Wrist.** The hand's axis stays within 0.10° of the forearm's: the twist axis, not a bend. The sleeve-weapon rule
  holds.

## 3. Deformation and the weapon: the defects

### 3.1 Joints folded past the validated range

The stage-3 weights are validated to 145° of elbow and 135° of knee (`s3_pose_set.py`). The solver had no joint
limit. Wherever an in-between frame's interpolated fist or foot target passed close to the shoulder or hip, the
two-bone IK folded the limb flat:

| Clip | Before | After |
|---|---|---|
| `dash` f1 | elbow R 172.7° | 129.5° |
| `death` f7 | elbow R 179.4° (L 145.5°) | 132.9° (107.8°) |
| `uppercut` f17 / f23 | elbow L 173.3°, R 165.2° | 127.3°, 126.3° |
| `get_up` f15 | knee R 171.7° | 150.0° |
| `death` f30 | knee L 152.9° | 149.5° |

With a rigid 38 cm gauntlet on the forearm, a 173-179° elbow puts the gauntlet inside the shoulder, the head or the
chest (`review35/review_elbow_folds.png`). The 172° knee crushed the calf into the thigh: a lump beside him in the get-up
(`review35/review_knee_fold.png`).

### 3.2 Gauntlets through the body

The stage-4 check counted body vertices inside gauntlet material, on key frames only. The damage happens between
keys and inside the gauntlet's cavity: the gauntlet is a hollow shell, so a thigh inside the sleeve is not inside its
material. The audit counts every vertex enclosed by a gauntlet (six axis rays all hit it), every frame. It excludes
the holding forearm, hand and fingers and, separately, the own upper arm (the known cuff overlap).
- "All foreign" also counts hanging cloth: the skirt plates, the underskirt and the sash, which are rigid and have no
  secondary motion yet.
- "Solid" counts only the body, belt, wraps, hair and beard. The GLB is one joined mesh, so parts were labelled by
  matching every rest vertex to the rig file's part meshes (exact, 0.0 m).

| Clip | All foreign, max per frame (before → after) | Solid parts (before → after) |
|---|---|---|
| `get_up` | 958 → 69 | 416 (f14) → 61 (f15) |
| `uppercut` | 413 → 56 | 413 (f23) → 2 |
| `death` | 377 → 73 | 136 (f27) → 22 |
| `meltdown_start` | 303 → 72 | 29 → 0 |
| `run` | 191 → 6 | 47 → 0 |
| `idle_signature` | 53 → 12 | 5 → 0 |
| `heat_vent` | 50 → 0 | 50 → 0 |
| `dash` / `dash_recover` | 38 / 27 → 20 / 16 | 38 / 27 → 2 / 1 |
| `reforge_in`, `victory`, `fire_charge`, `revive`, `fire_heavy`, `forge_hammer` | 28, 14, 13, 4, 2, 2 → 20, 0, 0, 0, 0, 0 | 28, 14, 13, 4, 2, 2 → 0 |
| `interact` | 27 → 27 | 0 → 0 (all cloth) |

After the fix, 29 of the 34 clips have no solid-body vertex inside a gauntlet in any frame. See
`review35/review_gauntlet_in_body.png`, and the `get_up` and `uppercut` strips.

### 3.3 The fixes (shared solver, every hero)

- **Soft joint limits** (`s4lib.py`).
  - `ELBOW_MAX_DEG` = 145 and `KNEE_MAX_DEG` = 150. A target closer than the reach at the limit is eased out softly.
  - The knee eases the ankle **horizontally**, so a kneeling foot never goes into the ground. A first version eased it
    along the hip-ankle line and pushed the `death` heel 22 mm down; that was caught and changed.
  - `clips.json` reports the eased frames (`elbow_fold_eased`, `knee_fold_eased`).
  - 150° is past the 135° validated range. Knees between 135° and 150° are documented as the soft spot (kneels and
    tucks, hidden by the skirt at game size).
- **The arm keep-out** (`s4lib.KeepOut`, built in `s4_anim.py`).
  - Every frame, the solver skins the body: body, belt, wraps, hair and beard. Hanging cloth steers nothing.
  - It tests the body against a radial map of the hand's rigid volume in the grip frame: the signature weapon's fist
    and open meshes for a sleeve weapon, else the bare forearm and fist.
  - An overlap pushes the fist target out along the **body's own surface normal** and re-solves the arm. A first version
    pushed across the forearm and flung the arms out sideways in `heat_vent`; the renders caught that. The pushes are
    smoothed over time, and a clip's end frames stay pinned so upper-layer clips still start and end on the guard.
  - Clean poses are untouched: `idle`, the guard (`idle_combat`), the jabs, the walk, strafes and backpedal, the
    hits, `ping`, `interact`, the Rush and Meltdown loops. 16 clips were pushed.
- **Three key poses**, where the written targets were the problem:
  - `get_up` GU2: the free fist now rides outside and above the raised knee.
  - `heat_vent`: a new f18 key brings the fists round in front of the hips on the way back to the guard, instead of up
    through the ribs.
  - `uppercut` slam: the fists land 4 cm further in front of the knees. 8 cm or more left the arms short of the ground.
- **Gates** (`s4_contract.py`, `check_clips.py`, the CI job `hero-clips`):
  - `MAX_KNEE_FLEXION_DEG` = 152;
  - `MAX_KEEPOUT_RESIDUAL_VERTS` = 60 per arm, the solver's own residual; Brax's largest is 42;
  - the existing `MAX_ELBOW_FLEXION_DEG` = 147.

  On the shipped `6b4a358` data these gates fail `dash`, `death`, `get_up` and `uppercut`; on the re-bake, 0 problems.
- **Scratch glTF check.** `s4_gltf_check.py` no longer exports vertex colours, matching the shipped export.

I watched every pushed clip before and after, as filmstrips of the shipped file. Every gesture reads as before; a
push shows only as a fist held a little wider where it used to cut the body. The largest visible changes:
- the `uppercut` slam's downswing (f23) arcs around the chest instead of through it;
- `death` f7 throws the arms out on the impact instead of folding the right gauntlet into the shoulder;
- `get_up`'s free fist rides outside the knee.

**Side effects, measured and accepted.**
- At the `uppercut` slam the two fists now press together: 50-106 vertices of one shell inside the other on the
  slam frames, 12 before. It's a double-fist slam; before, the fists sat on the knees instead.
- Arm reach at the slam: 54.7 mm short (gate 60).
- The stage-5 validator, the Blender re-import and every other gate pass on the re-export
  (`sha256 6fca8890c1ff278c3cb5d1621f4c054f7fe0ad59a3e5b9d84c17e7abc1908e9a`, 9,967,940 bytes).

### 3.4 Still open, measured

- **Residual solid overlap.** `get_up` f15 (61 vertices: the right gauntlet against the tucked right leg), `death` f27
  (22), `dash` / `uppercut` (2).
- **Kneeling knee in the ground.** The `uppercut` slam's kneeling knee sinks about 6 cm into the floor (lowest skinned
  vertex -60 mm).
- **Rigid cloth in the ground.** The skirt plates and sash go into the ground in the lying poses (up to 23 cm face
  down). Unchanged: they need `x_` cloth bones or engine springs, which is already a stage-3/4 open issue.
- **Cuff into the biceps.** The gauntlet cuff presses into the biceps whenever the elbow bends past about 40° (up to
  39 vertices a side, `hit_heavy`). That's weapon geometry: shorten or flare the sleeve (the armory agent's pack).
- **Knee soft spot.** Knees 135-150° flatten; this is the stage-3 finding.

## 4. The game-size read

`review35/review_game_board_1x.png` is at **true pixel size**: the 55° orthographic client camera, 1080 px = the view
height. It shows 22 m (one player) at yaw 0, 90 and 180, and 28 m (four players) at yaw 0 and 180. The greybox hero
the client falls back to stands beside him: a 1.7 m capsule plus head, in Brax's colour, from `scene.rs` `spawn_rig`.
Two silhouette columns split the gauntlets from the rest (`review_game_silhouettes.json`).

- **Size.** At 22 m Brax is 62-83 px tall from the front, about the greybox's height and a little narrower. At 28 m
  he is about 58 px, 5.4 % of the screen, and about 50 px at the 32 m cap for a spread party. `ART_PIPELINE.md`'s
  "6-8 % of screen height" holds for one or two players only; the doc now says so.
  `game.ron` `min_character_screen_frac` = 0.06 is declared but used nowhere in the engine.
- **Poses that read in under a second, front and side.**
  - idle: the gauntlets hang as two big glowing blocks;
  - guard: compact, the gauntlets framing the face;
  - uppercut launch and apex: one gauntlet above the head breaks the silhouette. This is the strongest read in the kit;
  - slam: a crouch with the gauntlets glowing on the ground;
  - downed: slumped, arms hanging;
  - run: the gauntlets pump in front.

  From the front the gauntlets take 23-40 % of his silhouette pixels; they are the widest and brightest shapes.
- **Weak reads.**
  - From **behind** (yaw 180) his back hides the gauntlets in the run (10-12 %) and the slam (4 %).
  - A jab thrown **straight at the camera** foreshortens to a lean; it reads well from the side.

  In play these lean on the slam's flame geysers, the hit-stop and the Heat glow. An emissive accent on the back of
  the cuffs would help the rear view (the armory agent's pack).

## 5. Pipeline honesty

- **status.json holds.** Stages 3-5 are `done` with `produced_by: AI`, and each has a `user_visual_approval` /
  `user_final_approval` item at `pending_human`, exactly as `ART_PIPELINE.md` §1 prescribes. `final` is false, and
  the sidecar says `ai_final_pending_user_approval`. Updated now with:
  - the re-bake's metrics;
  - a `reviews` entry pointing at this report;
  - the stage-4 note on what the first bake got wrong.
- **manifest.json was stale.** It stopped at stage 3 and its stage-2 texture list omitted `brax_normal.png`. It now
  lists the stage-4 file and the shipped GLBs and sidecars, with bytes and sha256.
- **Reports corrected.**
  - The stage-4 summary said at most 58 vertices cut the body. The first bake had up to 416 solid-body vertices inside a
    gauntlet, measured between keys and inside the cavity.
  - `anim_report.md` §3 and §6 now carry the re-bake's table, a revision note, and the corrected contact claims.
- **Large files.** No tracked file over 20 MB lives outside Git LFS. The only one over 20 MB, the 63 MB stage-1
  sculpt reference, is in LFS. `check_art.py`: 0 errors.
- **Still unverified.** Nothing is verified in the Bevy client; the engine agent owns that, and the status item
  `bevy_import_test` says `not_started`.

## 6. What changed

- `tools/blender/gf_hero/`:
  - `s4lib.py`: joint limits, `KeepOut`, `bake()` with smoothed pushes; the twist bones now get their own matrix, where
    a `startswith` branch used to re-solve the whole limb;
  - `s4_anim.py`: builds the keep-out, adds the new metrics;
  - `s4_clips.py` (GU2) and `s4_brax.py` (`heat_vent`, the slam);
  - `s4_contract.py`, `check_clips.py`: the gates;
  - `s4_gltf_check.py`;
  - `run_stage3/4/5.py`: the Pillow Python fallback and the stage-3 bootstrap;
  - `review/`: the independent audit and review renders. `python tools/blender/gf_hero/review/run_review.py <key>`
    writes to `work/review/`.
- `art/characters/brax/`:
  - `production/brax_anim.blend`;
  - `reports/anim/*` (clips, render checks, glTF check, the contact sheets and boards);
  - `reports/anim_report.md`, `reports/export_report.json`, `reports/stage5/export_review.png`;
  - `status.json`, `manifest.json`, `README.md`;
  - this report and `reports/review35/`.
- `assets/models/characters/brax.glb` and `.meta.json`, re-exported. The gauntlets are unchanged.
- `docs/art/GF_HERO_SKELETON.md` §7-8 (the limits, the keep-out, the upper-layer wording) and `docs/ART_PIPELINE.md`
  (stage-4 table, the 4-player size).

## 7. Evidence in `reports/review35/`

| File | What |
|---|---|
| `review_elbow_folds.png` | `dash` f1, `death` f7, `uppercut` f17 / f23, before and after: full body and the folded arm |
| `review_gauntlet_in_body.png` | `get_up` f14, `meltdown_start` f6, `run` f4, `death` f27, before and after |
| `review_knee_fold.png` | `get_up` f15: the 172° knee lump and the 150° result |
| `review_strip_get_up.png`, `review_strip_uppercut.png`, `review_strip_heat_vent.png` | the whole clip before and after |
| `review_game_board_1x.png` + `review_game_silhouettes.json` | the client camera at true pixel size, with the greybox and the silhouette split |
| `audit_before.json`, `audit_after.json` | the independent audit of the two files: 6 problems before (the joint folds), 0 after; per-clip metrics |

Re-run the review of any shipped hero with `python tools/blender/gf_hero/review/run_review.py <key>`: audit, the worst
frame of every clip in close-up, and the game board, in a few minutes.
