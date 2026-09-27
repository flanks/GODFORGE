# Kael — stages 3 to 5: rig, animation, shipped GLB (made by AI, 2026-09-27)

> **Made by AI, not a stand-in.** No human artist at any stage (the user's decision of 2026-09-25); the user gives
> the final visual approval (`status.json`, items `user_visual_approval` of stages 3, 4 and 5, `pending_human`).
>
> **The weapon is a separate model.** The body has empty hands; the weapon track's `serpent_smg.glb` rides `weapon_R`
> by the identity attach in every review and in the shipped sidecar. The Bullet Ballet twin pistol is a VFX copy on
> `weapon_L`.

Review sheets, one per stage:

| Stage | Sheet |
|---|---|
| 3 rig | [`stage3/stage3_rig.png`](stage3/stage3_rig.png): the skeleton, the dominant bone per vertex, the rest turnaround with the gun on `weapon_R`, 8 check poses (baked stage-4 frames with the cloth pass) |
| 4 animation | [`anim/anim_board.png`](anim/anim_board.png): all 32 clips at their key frames and at the client camera (55°, 22 m, true pixels) |
| 5 export | [`stage5/export_review.png`](stage5/export_review.png): the shipped `kael.glb` re-imported into a fresh Blender next to the stage-4 source |

## 1. Stage 3: GF_Hero_v1 on Kael

`python tools/blender/gf_hero/s3_kael_run.py` (about 30 s, then the review renders).

- **Skeleton.** The master GF_Hero_v1 (never forked): the shared `s3_landmarks.py` derives every contract joint, finger
  and hand frame from the stage-2 fit (Kael is an unarmoured hm08 body), `s3_kael_landmarks.py` adds his **48 `x_`
  cloth bones**, placed on the stage-2 mesh:
  - `x_coat_{LF,LS,LB,RB,RS,RF}_01..04` (parent `pelvis`): six chains down the duster's skirt at 72°, 112°, 152°, 208°,
    248°, 288° round him (0° = his front), joints on the skirt's mid-surface at z 1.32 / 1.12 / 0.92 / 0.72 and the
    column's hem (0.36-0.40 m);
  - `x_loin_{R,C,L}_01..03` (parent `pelvis`) across the loin cloth;
  - `x_wisp_<n>_01..03`, one chain per ghost-flame tatter, hem to tip along its centre line, parented to the last bone
    of the nearest coat column (so the tatters ride the coat and add their own lag).
  There are no driven helpers: every `x_` bone is a cloth chain, keyed by the stage-4 cloth pass.
- **Skin** (shared `s3_skin.py` + the hook `s3_kael_skin.py`, numbers in `stage3_skin.json`):
  BODY as Brax's (MakeHuman CC0 seed + bone heat + twist split + joint blends and Gaussian smoothing, radii for his
  leaner limbs); the coat's **yoke and lapels, the gear and the boots copy the body** at the nearest body point (the yoke
  is the body's own quads pushed 1.5-3 cm out, so each yoke vertex bends with the skin under it: no helper bones were
  needed at the shoulders and elbows); the rolled cuffs, buckles, gem and cartridges are one rigid row each; the collar
  and the scarf's wrap are rigid on `spine_03` 0.6 / `neck` 0.4; the **skirt** is on the `x_coat` grid (linear between the
  two nearest columns by angle; the back pair blended above the vent and split by side below it over 12 cm; hat
  functions along the chain; the tucked top row pinned to the body's own weights, as the yoke over it); the loin cloth on
  the `x_loin` grid; each tatter takes the coat's weights above its hem and its chain below. 8 objects, ≤ 4 influences,
  0 unweighted vertices, weights normalised to 2e-16.
- **Weapon.** `serpent_smg.glb` (the shipped file) imported as `PREVIEW_serpent_smg_R` on `weapon_R` by a Child Of whose
  inverse is SOCKET_TO_GRIP; `s3_gltf_check.py` proves the identity attach in glTF: 3.6e-7 m.

## 2. Stage 4: 32 clips

`python tools/blender/gf_hero/s4_kael_run.py` (about 5 min: bake 12 s, cloth pass 2.5 min, renders).

- **The shared 24** keep `s4_clips.py`'s timing, foot work, pelvis and spine (scaled to his 1.106 m leg and 0.786 m arm)
  with his hand vocabulary swapped in (`s4_kael.py`): the guard is the **one-handed aim** (the serpent_smg down the aim
  line at shoulder height, in hero space so the chest's bounce never swings the muzzle), the ghost hand hangs low and
  loose, the gun hand stays curled round the grip in every frame; a lighter, squarer stance. Re-posed by hand where a
  brawler's fists meant something else: `fire_light` (a snap shot), `fire_heavy` (a braced two-handed shot, the ghost
  hand cupped under the gun), `fire_charge` (two hands, trembling), `ping` (the ghost hand points), `interact` (the ghost
  hand flat on the anvil), `forge_hammer` (the ghost fist hammers), `reforge_in` (the ghost fist planted, a gun flourish),
  `death` (the gun arm flung clear), and the side runs / backpedal on 18 / 16-frame cycles for his 7.2 m/s (the library's
  strides over-reached his leg by 64-78 mm).
- **His 8 kit clips**: `idle_signature@loop` (brings the gun up past his face, flips it twice on his hand, lowers it,
  then flexes the ghost hand in front of him), `fan_of_blades` (upper layer: the gun drops to the hip, the open ghost hand
  fans across it, event `burst`), `shadow_roll` (a real 360° forward roll: dive, tucked roll, crouched landing with the
  gun already coming up; events `roll`, `land`), `ghost_step` (the refreshed dash: a low glide, the gun on the aim, the
  ghost arm trailing), `bullet_ballet_start` (arms crossed, flung wide as the twin forms: `twin`),
  `bullet_ballet@loop` (both arms up, on the balls of the feet), `fire_twin` (upper layer over `bullet_ballet@loop`:
  `shot_r`, `shot_l`), `fire_r` (the rapid shot, 6 frames).
- **Numbers** (`anim/clips.json`): 1,005 frames, 12 loops all seamless, foot slide ≤ 8.0 mm, IK miss ≤ 34 mm, elbow ≤ 146°,
  knee ≤ 150°, the wrist never bends, ≤ 25 body vertices left in a hand's weapon volume, no foot under the ground: inside
  every `check_clips.py` gate.
- **Cloth pass** (`s4_kael_cloth.py`, the method of Valdris's with a coat that hangs all round the legs): per clip and
  chain, a lagged spring on the apparent gravity at the pin plus drag against the design travel (the run streams the
  duster back), a per-column drape over the legs, boots, holster and the low-held gun, the clear out of the body, smoothing
  over time; upper-layer clips start and end on their base clip's cloth state; the tatters are solved on the coat's
  solved chains. In the Shadow Roll the chains follow the body more (gravity × 0.35) so the duster wraps round him.

## 3. Stage 5: `assets/models/characters/kael.glb`

`python tools/blender/gf_hero/run_stage5.py kael --only export`, `python tools/blender/gf_hero/s5_kael.py --sidecar`,
then `--only reimport` and `--only sheet`.

13.76 MB, 24,114 tris, 111 joints (63 contract + 48 `x_`), one skinned mesh `kael_mesh`, one single-sided material with
2048 base colour / emissive / normal textures, 32 clips at 30 fps. The export's gate (validate_glb + source fidelity
1.8e-5) and the fresh-Blender re-import (32 clips played, pose error 6.0e-6, the gun on the imported `weapon_R` at rest
1.5e-7 and through `fire_heavy` f9 6.0e-7): **0 errors, 0 warnings**, height 2.158 m. The sidecar has
`status: ai_final_pending_user_approval`, the events and design speeds, and `clip_info.kael_fire_twin.base`.

## 4. Known limits

- **Cloth in the floor clips.** Lying and kneeling (`get_up`, `knockdown`, `downed`) leave up to 430 skirt vertices
  inside his legs or under him at the worst frame (the skirt under him as he sits up); the standing clips stay under
  45. The loin cloth is pierced by the lifted thigh in the dash lunge (72 of 158 vertices at the worst frame).
- **The dash** throws the duster high over his back (the drape lifts it over the trailing leg, the drag streams it).
  It reads as a ghostly streak at game size; tone it down with `s4_kael_cloth.py`'s coat drag if the user prefers.
- **The gun flourish** is two quick 160° flips of the hand, not a full spin: a full turn would candy-wrap the forearm
  (the twist bone takes 65 %).
- **Planted hands keep the gun.** In `get_up` and `knockdown` the gun hand pushes off the ground with the gun in it.
- **The sidecar's weapon text.** `export_glb.py` words any weapon without an offhand node as a sleeve weapon;
  `s5_kael.py --sidecar` replaces that text for a hand-held gun (nothing else in the sidecar changes).
- The ghost arm stays on his left (`decisions[ghost_arm_side]`, `pending_human`).
