# Valdris: adversarial review of stages 2-5

Made by AI (Claude) on 2026-09-26, after stage 5 was committed (`39988a2`). The job was to try to refute every claim
the four stage reports make, on the **shipped** files, fix what turned out to be wrong, and say plainly what is still
open. The user's visual approvals of stages 2-5 are still pending; nothing here replaces them.

**Reviewed:** `c13b67a` (stage 2 polish), `139c655` (rig), `d2f0afe` (animation), `39988a2` (export): the reports,
`status.json`, `manifest.json`, `README.md`, and above all `assets/models/characters/valdris.glb` with its sidecar and
the weapon track's `colossus_cannon.glb`.

**How.** The documented commands were re-run (the gate with the Blender re-import, the export). Then three new
Valdris-only tools measured the shipped file independently of the stage-4 audit:

- `tools/blender/gf_hero/valdris_review.py` imports the GLB with Blender's own importer and attaches the cannon as the
  identity child of `weapon_R`, as the client will. It plays **every frame of every clip** (1,288 frames) and measures
  the skinned mesh itself. It also renders Workbench close-ups of each clip's two extreme frames: the highest knee and
  the highest arm.
- `valdris_review_lineup.py` renders the game-size read through the client camera (55°, 22 m view height, true 1080p
  pixels). He stands next to Brax, a greybox capsule and the six Cinder Wastes swarm enemies, and inside a 140-enemy
  horde.
- `valdris_review_sheets.py` builds the sheets in [`review/`](review/).

## 1. Verdict

- **Most of the structural claims hold.**
  - The gate passes and the file re-exports byte-identical.
  - The mesh is closed, the weights are clean and left/right symmetric, and the skeleton and sockets match GF_Hero_v1.
  - All 34 clips are there under the right names, every loop closes exactly, and every loop keeps its soles still.
- **The cloth pass (stage 4) was wrong in ways that show**, and the reports said otherwise:
  - the sabatons pierced the cape whenever he knelt, floated as the wraith or backpedalled;
  - every upper-layer one-shot (the shot he fires 2.6 times a second, the flinch, the ping, the Siege shot) started with
    the cape 0.4-0.6 m away from the pose it layers over;
  - the wraith's cape and the strafing loincloth jittered.
  - **Fixed** (§3).
- **The sidecar gave the engine the wrong reference pose** for `siege_fire` and `mountainfall_pound`. **Fixed** (§3).
- **Two claims stay refuted and are not fixed:**
  - the one-shot foot skids are larger than reported (knockdown 64 mm);
  - his game-size darkness advantage over the swarm is small, because gold rims cover about a fifth of his pixels (§4).
    Changing the look is a stage-2 design call for the user, so the review leaves it and says so.

## 2. The claims, one by one

"Confirmed" means I tried to break the claim and could not. "Refuted" means the shipped file contradicts it.

| # | Claim (stage) | How I tested it | Result |
|---|---|---|---|
| 1 | The gate passes: 0 errors, 1 warning (5) | Re-ran `validate_glb.py --blender` on `valdris.glb` and `brax.glb` | **Confirmed**: both pass; the only warning is the 2.33 m rest height (the pauldron tops; the crown is 2.306 m) |
| 2 | Re-exporting is byte-identical (5) | Re-ran `export_glb.py --key valdris` on the committed `valdris_anim.blend` | **Confirmed**: sha256 `e7fd6b4c…` and the sidecar are unchanged. It holds after the fixes too (§3) |
| 3 | 24,958 tris, 116 joints (63 + 53 `x_`), one mesh, 34 clips, 16.9 MB (2, 5) | Read from the GLB | **Confirmed** |
| 4 | Every part is closed, so a single-sided material is safe (2) | Welded the shipped mesh by position (1e-5 m) and counted the edges | **Confirmed**: 0 open edges, 0 non-manifold. The weapon track's `colossus_cannon.glb` is single-sided with 398 open edges (the sleeve rims), but backface-culled renders of its rear show no hole, because the forearm fills it. That note is for the weapon owner |
| 5 | Weights: at most 4 influences, normalised, 0 unweighted (3) | Read every vertex from the imported mesh | **Confirmed**: at most 4, sums within 1.3e-7. **Left / right:** 8,736 mirror vertex pairs, only 2 differ by more than 0.05 (a foot and a shin, 0.06). **Far influences:** 317 blended influences sit more than 0.35 m from their bone: the cape's pinned rows and the barrel torso, both by design |
| 6 | Skeleton and sockets follow GF_Hero_v1 (3, 5) | Gate + re-import, then socket positions measured against the geometry | **Confirmed**. `weapon_R` is 4.8 cm from the centroid of the right fist, inside it. `chest_sigil` lies on the anvil's surface (0.0 mm). `head_top` is the crown (2.306 m). Mirrored bone heads agree within 1.4 mm (`weapon_L`) |
| 7 | The cannon rides `weapon_R` as an identity child (3, 5) | Attached the shipped cannon as the client will, every frame | **Confirmed** |
| 8 | Clip names and set = `required_clips.json` (4, 5) | Gate + the sidecar against the file | **Confirmed**: 34 of 34. **Kit set vs brief:** it differs from the brief's §8 proposal (one `bulwark_slam` instead of leap + land, `mountainfall` instead of `mountainfall_idle`, and `siege_fire` added). `anim_report.md` documents this and it is within the 6-10 unique clips |
| 9 | Loops close exactly and the seam is no rougher than the clip (4) | Mesh positions at the first and last frame, and the second difference through the seam | **Confirmed**: 0.0 mm in all 13 loops. The walk's seam equals, but does not exceed, the roughest frame inside the clip |
| 10 | No planted sole slides in the loops, at most 2.5 mm per contact (4) | Sole vertices within 5 mm of the ground in two frames, the design travel taken out, the best-anchored vertex summed per contact | **Confirmed**: at most 0.6 mm (the walk). **Metric check:** with a 1 cm threshold the strafes and the backpedal showed one-frame "slips" of 52-58 mm, but those are swinging feet skimming 9 mm over the ground, not planted soles |
| 11 | One-shot foot slip reaches at most 50.3 mm (the Bulwark landing); the steps onto the knee 17 mm (4) | Same metric as row 10 | **Refuted**. **Worst:** the knockdown's right sabaton skids 64 mm in one frame (f3), and the death's 47.5 mm. **Others:** Bulwark 31.5, Siege Stance enter 27.7 and exit 25.5, `hit_heavy` 20.8, revive 16.2. **Not fixed** (§5) |
| 12 | The wrist never bends: the sleeve rule (4) | Forearm-to-hand angle against the rest pose, every frame | **Confirmed**: 0.0002° |
| 13 | Joint maxima: elbow R 61°, knee 149.3° (4) | From the posed joints | **Confirmed** |
| 14 | "The cape ... drapes over his heels when he kneels" (4, `anim_report.md` §4) | Leg-armour triangles cutting a cape triangle (BVH overlap; 0 at rest), plus back views | **Refuted**. The rear sabaton **pierced** the cape in the knockdown (255 faces; its last frame is held until the get-up), the death (371), the get-up (320), the whole wraith loop (531, all 61 frames), every frame of the backpedal (403), `dash_recover` (511) and the revive (470). The stage-4 cloth audit counts cloth vertices inside a plate, so it cannot see a plate passing *between* cloth vertices. **Fixed** |
| 15 | The cloth corrections are "smoothed so it never pops" (4) | Cloth vertices whose velocity reverses between frames at more than 2 cm/frame | **Refuted in part**. **Wraith loop:** the cape reversed in 46 of 60 frames, up to 0.64 m per frame, while the body moved at most 11 mm. **Strafes:** the loincloth moved up to 0.68 m per frame. **Quiet idles:** the hem flicked 0.1-0.25 m in a frame. **Fixed or reduced** |
| 16 | Upper-layer clips start and end on `idle_combat` frame 0, so an engine can layer them additively (contract §8; the sidecar's `playback.upper_layer`) | Every joint's world matrix and every vertex, at the first and last frame, against the reference frame | **Refuted for the cloth chains.** The contract joints match exactly (0.0). **First frame** (cape and braids off the reference): `fire_light` 556 mm, `hit_light` 605, `ping` 430, `siege_fire` 552, `armor_break` 604, `fire_heavy` 458, `mountainfall_pound` 275. **Last frame:** up to 433 mm. At 2.6 shots a second the cape would snap every shot. **Fixed** |
| 17 | The sidecar tells the engine what each clip layers over (5) | The sidecar against `clips.json` | **Refuted.** `siege_fire` layers over `siege_stance` frame 0 and `mountainfall_pound` over `mountainfall` frame 0 (`Clip(base=...)`), but the sidecar had no such field, and its playback text said every upper clip starts on `idle_combat` frame 0. **Fixed** |
| 18 | The cannon sleeve hides the forearm: 1-5 vertices poke out, 29 in `fire_charge` (2-4) | Forearm vertices within the cannon's length whose radial rays escape its outer skin | **Mostly confirmed**: 6-8 in the poses (the thumb tip at the sleeve mouth), 64 in `fire_charge`. The close-ups show nothing visible |
| 19 | Pipeline honesty: `status.json`, `manifest.json`, `README.md` | Read against the files | **Mostly confirmed.** `README.md` still showed stages 4 and 5 as `not_started`, and the cloth claims in rows 14-16 were wrong in `anim_report.md` and `status.json`. **Fixed** |
| 20 | Nothing over 20 MB outside Git LFS | Every tracked file over 10 MB | **Confirmed**: the three are LFS GLBs (`valdris.glb` 16.9 MB and the two TRELLIS sculpt references, 63 and 81 MB) |
| 21 | "The cape is a plain red panel without the concept's tatters and emblem" (5, the export review) | Back views of every clip | **Refuted**: the cape carries the gold forge-sigil emblem and a tattered hem (`review/cape_before_after.png`). From the 55° camera facing him neither shows, because the cape hangs behind him. Corrected in `export_report.json` |

## 3. What I fixed

### 3.1 The cloth pass (`tools/blender/gf_hero/s4_valdris_cloth.py`, Valdris-only)

1. **The drape (rows 14-15).** After the lagged hang, each cape and loincloth chain bone is laid over the legs like a
   rope, top to bottom:
   - it keeps its hang direction unless a leg-armour vertex (cuisses, knee cops, greaves, sabatons) in its lateral band
     would lie *outside* the cloth line;
   - in that case it turns outward (the cape backward, the loincloth forward, in the torso's and pelvis's own frame)
     just past that vertex, plus a 5 cm (cape) or 2 cm (loincloth) margin, and the bones below hang again;
   - a second pass lifts each chain at least 0.75x as far as its neighbours (0.45x two chains away), so the cloth
     between chains never shears open;
   - the floor fold follows.

   The drape counts as a correction like the clear, so it is smoothed over time.
2. **Wider smoothing (row 15).** The cape's and the loincloth's corrections are now dilated over ±2 frames and smoothed
   in four passes (was ±1 and two). The quick braids keep the old kernel: a wide one let their clear lag behind a head
   turn.
3. **Upper-layer one-shots settle on their reference (row 16).**
   - **Cape and loincloth:** the clip's own cloth motion, relative to its own first frame, is laid on the base clip's
     frame-0 cloth state (`idle_combat`, or `clips.json` `base`), eased back into it over the last frames, then draped
     and cleared again.
   - **Braids:** their own solution is eased in and out over two frames.
   - **Result:** the first and last frames are now the reference pose for every bone.
   - **What else was tried:** composing the braids too, re-clearing them, and 8-frame braid ramps. Each drove the braids
     into the pauldrons in `ping` (17 → 36-58 vertices), so they were dropped.

### 3.2 The sidecar (`tools/blender/gf_hero/export_glb.py`, shared, default-off; row 17)

- **`clip_info.<clip>.base`:** `valdris_siege_fire` → `valdris_siege_stance@loop`, and `valdris_mountainfall_pound` →
  `valdris_mountainfall@loop`.
- **`playback.upper_layer`** now names those two exceptions.
- **Brax:** his sidecar has no base, so it is byte-identical (§6).

### 3.3 Before → after, every clip

Measured on the shipped file before (`39988a2`) and after the fix, with `valdris_review.py`.

- **Legs through the cloth:** leg-armour triangles cutting a cloth triangle, the worst frame, with the number of frames
  that have any (at rest: cape 0, loincloth 22).
- **Jitter:** frames in which some cloth vertex reverses direction at more than 2 cm per frame, and the fastest cloth
  vertex.
- **Last column:** the cape and braids' largest distance from the reference pose at the first and last frame of the
  upper-layer clips.

| Clip | Legs through the cape: faces (frames) | Legs through the loincloth: faces (frames) | Cape jitter: frames with reversals / fastest vertex (mm/frame) | Loincloth jitter | Cape + braids off the reference at the first / last frame (mm) |
|---|---|---|---|---|---|
| `idle@loop` | 0 (0) -> 0 (0) | 126 (81) -> 63 (121) | 2 / 219 -> 0 / 167 | 16 / 127 -> 0 / 31 | - |
| `idle_combat@loop` | 6 (1) -> 5 (0) | 118 (41) -> 18 (0) | 6 / 112 -> 0 / 74 | 8 / 210 -> 0 / 56 | - |
| `walk@loop` | 132 (6) -> 153 (6) | 183 (29) -> 26 (0) | 7 / 236 -> 1 / 131 | 10 / 180 -> 2 / 102 | - |
| `run@loop` | 0 (0) -> 0 (0) | 170 (21) -> 111 (10) | 8 / 212 -> 4 / 168 | 10 / 266 -> 3 / 140 | - |
| `strafe_left@loop` | 4 (0) -> 0 (0) | 303 (18) -> 86 (14) | 1 / 123 -> 2 / 194 | 8 / 596 -> 2 / 151 | - |
| `strafe_right@loop` | 41 (18) -> 71 (19) | 537 (19) -> 88 (14) | 6 / 157 -> 3 / 146 | 14 / 679 -> 4 / 151 | - |
| `backpedal@loop` | 403 (18) -> 47 (7) | 156 (19) -> 88 (10) | 14 / 232 -> 10 / 168 | 9 / 369 -> 1 / 68 | - |
| `dash` | 87 (5) -> 92 (4) | 111 (9) -> 58 (7) | 0 / 224 -> 0 / 214 | 3 / 214 -> 0 / 229 | - |
| `dash_recover` | 511 (4) -> 0 (0) | 225 (17) -> 52 (2) | 5 / 489 -> 3 / 216 | 5 / 308 -> 1 / 150 | - |
| `fire_light` | 158 (5) -> 0 (0) | 64 (9) -> 18 (0) | 2 / 171 -> 5 / 166 | 1 / 153 -> 1 / 54 | 556 / 102 -> 0 / 0 |
| `fire_heavy` | 49 (2) -> 0 (0) | 184 (19) -> 23 (0) | 4 / 233 -> 9 / 237 | 6 / 260 -> 3 / 110 | 458 / 433 -> 0 / 0 |
| `fire_charge@loop` | 23 (8) -> 25 (8) | 71 (25) -> 21 (0) | 0 / 33 -> 0 / 24 | 0 / 0 -> 0 / 0 | 306 / 306 -> 222 / 222 |
| `hit_light` | 131 (10) -> 21 (2) | 98 (13) -> 20 (0) | 6 / 206 -> 6 / 233 | 3 / 122 -> 0 / 41 | 605 / 43 -> 0 / 0 |
| `hit_heavy` | 65 (7) -> 50 (6) | 176 (31) -> 65 (4) | 5 / 232 -> 3 / 196 | 9 / 301 -> 3 / 187 | - |
| `knockdown` | 255 (30) -> 0 (0) | 144 (37) -> 61 (28) | 14 / 388 -> 2 / 356 | 8 / 365 -> 4 / 226 | - |
| `get_up` | 320 (19) -> 40 (9) | 304 (40) -> 160 (25) | 16 / 460 -> 5 / 392 | 14 / 298 -> 7 / 219 | - |
| `death` | 371 (50) -> 38 (7) | 141 (57) -> 62 (45) | 26 / 343 -> 9 / 297 | 8 / 354 -> 2 / 188 | - |
| `downed@loop` | 531 (61) -> 48 (47) | 123 (61) -> 56 (28) | 46 / 644 -> 6 / 160 | 9 / 140 -> 1 / 175 | - |
| `revive` | 470 (7) -> 19 (4) | 346 (41) -> 86 (10) | 9 / 482 -> 6 / 285 | 15 / 388 -> 5 / 219 | - |
| `reforge_in` | 298 (16) -> 40 (6) | 251 (47) -> 102 (21) | 20 / 464 -> 12 / 514 | 17 / 358 -> 4 / 248 | - |
| `victory` | 38 (3) -> 59 (6) | 344 (61) -> 22 (0) | 8 / 208 -> 3 / 130 | 16 / 279 -> 2 / 148 | - |
| `ping` | 48 (4) -> 0 (0) | 147 (21) -> 17 (0) | 1 / 212 -> 2 / 221 | 0 / 0 -> 0 / 0 | 430 / 57 -> 0 / 0 |
| `interact` | 89 (13) -> 50 (6) | 193 (39) -> 114 (20) | 14 / 295 -> 11 / 270 | 12 / 267 -> 7 / 220 | - |
| `forge_hammer@loop` | 35 (18) -> 41 (20) | 219 (37) -> 104 (8) | 7 / 641 -> 1 / 480 | 9 / 291 -> 1 / 262 | - |
| `idle_signature@loop` | 35 (4) -> 36 (5) | 149 (89) -> 53 (151) | 18 / 252 -> 7 / 183 | 4 / 195 -> 0 / 40 | - |
| `bulwark_slam` | 4 (0) -> 0 (0) | 399 (51) -> 259 (23) | 13 / 415 -> 13 / 289 | 17 / 453 -> 12 / 287 | - |
| `siege_stance_enter` | 191 (11) -> 59 (8) | 215 (27) -> 89 (12) | 10 / 195 -> 6 / 192 | 9 / 223 -> 4 / 319 | - |
| `siege_stance@loop` | 56 (4) -> 51 (6) | 96 (41) -> 32 (14) | 4 / 160 -> 1 / 74 | 14 / 181 -> 0 / 37 | - |
| `siege_stance_exit` | 38 (5) -> 80 (3) | 154 (21) -> 33 (1) | 7 / 184 -> 7 / 173 | 9 / 239 -> 9 / 195 | - |
| `siege_fire` | 136 (3) -> 0 (0) | 84 (6) -> 11 (0) | 1 / 146 -> 2 / 191 | 0 / 0 -> 0 / 0 | 552 / 181 -> 0 / 0 |
| `mountainfall_start` | 132 (22) -> 78 (19) | 282 (42) -> 66 (8) | 15 / 320 -> 8 / 218 | 20 / 252 -> 6 / 273 | - |
| `mountainfall@loop` | 26 (7) -> 28 (10) | 97 (41) -> 11 (0) | 5 / 146 -> 3 / 113 | 7 / 142 -> 0 / 21 | - |
| `mountainfall_pound` | 183 (12) -> 0 (0) | 44 (34) -> 11 (0) | 11 / 192 -> 3 / 213 | 0 / 0 -> 0 / 33 | 275 / 256 -> 0 / 0 |
| `armor_break` | 30 (3) -> 39 (4) | 265 (33) -> 39 (7) | 13 / 482 -> 19 / 332 | 9 / 193 -> 5 / 139 | 604 / 117 -> 0 / 0 |

**Totals over the 1,288 frames:**

- **Legs through the cape:** 376 → 212 frames. What is left is mostly the cape's side edges touching the calves in the
  walk, the strafes and the dash. The back views show no piercing: `review/closeups_*.png`, and renders of the worst
  frames (walk f1, strafe_right f9, siege_stance_exit f12, dash f8).
- **Legs through the loincloth:** 1,177 → 583 frames.
- **Frames with cape reversals:** 324 → 172.
- **Frames with loincloth reversals:** 299 → 89.
- **Braids:** unchanged (34 → 40, the same clips).

**Where it got worse:**

- **`armor_break`:** its cape is cut by 39 faces in 4 frames (was 30 in 3).
- **`siege_stance_exit`, `strafe_right` and `victory`:** their cape edge touches the legs more (80, 71 and 59 faces,
  was 38, 41 and 38).
- **The quiet idles (`idle`, `idle_signature`):** the loincloth now brushes the thighs in every frame, with a lower worst
  frame. Up to 63 and 53 faces, where before it was up to 126 and 149 faces in 81 and 89 frames.

**The audit agrees:** the stage-4 audit (`reports/anim/render_checks.json`, ray parity) moves the same way:

| Cloth vertices inside a plate | Before | After |
|---|---|---|
| Cape | 51 | 40 |
| Loincloth | 41 | 17 |
| Braids | 17 | 17 |

The lowest cloth vertex went from -69 mm to -30 mm. Every solid column is unchanged. See the refreshed table in
`anim_report.md` §3 and the sheets in `reports/anim/`.

**The picture:** [`review/cape_before_after.png`](review/cape_before_after.png). Before, the sabatons stuck out of the
cape in the wraith, the knockdown, the death and the get-up. After, the cape lies over the rear leg and trails on the
floor; the foot shows below the hem.

**Other measurements of the fixed file** (everything the fix did not change is identical):

| Clip | Sole slip L / R (mm per contact, best-anchored vertex) | Lowest vertex (mm, part) | Cannon: forearm out of the outer skin / other vertices enclosed | Knee / elbow R max (deg) |
|---|---|---|---|---|
| `idle@loop` | 0.0 / 0.0 | -12 (shin_L) | 6 / 6 | 31 / 19 |
| `idle_combat@loop` | 0.0 / 0.0 | -13 (shin_L) | 8 / 14 | 42 / 35 |
| `walk@loop` | 0.6 / 0.6 | -12 (shin_L) | 8 / 4 | 108 / 21 |
| `run@loop` | 0.0 / 0.0 | -0 (foot_R) | 0 / 18 | 132 / 35 |
| `strafe_left@loop` | 0.0 / 0.0 | -0 (foot_L) | 8 / 14 | 131 / 34 |
| `strafe_right@loop` | 0.0 / 0.0 | -0 (foot_R) | 8 / 14 | 131 / 34 |
| `backpedal@loop` | 0.0 / 0.0 | -0 (foot_R) | 8 / 14 | 130 / 34 |
| `dash` | 0.0 / 0.0 | -12 (shin_L) | 8 / 47 | 139 / 44 |
| `dash_recover` | 0.0 / 0.0 | -14 (shin_L) | 8 / 47 | 138 / 44 |
| `fire_light` | 0.0 / 0.0 | -12 (shin_L) | 8 / 16 | 36 / 34 |
| `fire_heavy` | 0.0 / 0.0 | -14 (shin_L) | 8 / 59 | 46 / 46 |
| `fire_charge@loop` | 0.0 / 0.0 | -12 (shin_L) | 64 / 45 | 46 / 44 |
| `hit_light` | 0.0 / 0.0 | -12 (shin_L) | 8 / 16 | 36 / 34 |
| `hit_heavy` | 20.8 / 0.0 | -16 (shin_L) | 8 / 53 | 82 / 45 |
| `knockdown` | 11.6 / 64.0 | -31 (x_knee_R) | 8 / 37 | 137 / 37 |
| `get_up` | 3.2 / 0.0 | -19 (shin_L) | 8 / 16 | 149 / 35 |
| `death` | 7.8 / 47.5 | -35 (x_knee_R) | 8 / 14 | 141 / 34 |
| `downed@loop` | 0.0 / 0.0 | 15 (x_loin_R_03) | 6 / 4 | 146 / 27 |
| `revive` | 16.2 / 15.8 | -17 (shin_R) | 8 / 19 | 148 / 35 |
| `reforge_in` | 1.6 / 0.0 | -19 (shin_L) | 8 / 35 | 149 / 36 |
| `victory` | 0.0 / 0.0 | -19 (shin_L) | 8 / 74 | 57 / 44 |
| `ping` | 0.0 / 0.0 | -12 (shin_L) | 8 / 60 | 36 / 48 |
| `interact` | 0.0 / 0.0 | -33 (shin_L) | 8 / 12 | 78 / 34 |
| `forge_hammer@loop` | 0.0 / 0.0 | -20 (shin_L) | 6 / 4 | 59 / 15 |
| `idle_signature@loop` | 0.0 / 0.0 | -9 (shin_L) | 8 / 16 | 33 / 35 |
| `bulwark_slam` | 23.0 / 31.5 | -40 (foot_R) | 8 / 39 | 121 / 41 |
| `siege_stance_enter` | 27.7 / 0.0 | -16 (shin_R) | 8 / 58 | 113 / 46 |
| `siege_stance@loop` | 0.0 / 0.0 | -13 (x_cape_R2_05) | 8 / 40 | 82 / 41 |
| `siege_stance_exit` | 25.5 / 0.0 | -15 (shin_L) | 8 / 40 | 107 / 41 |
| `siege_fire` | 0.0 / 0.0 | -2 (x_cape_R2_05) | 8 / 39 | 79 / 41 |
| `mountainfall_start` | 0.8 / 1.6 | -23 (shin_R) | 8 / 61 | 119 / 50 |
| `mountainfall@loop` | 0.0 / 0.0 | -9 (shin_L) | 8 / 60 | 56 / 47 |
| `mountainfall_pound` | 0.0 / 0.0 | -9 (shin_L) | 8 / 40 | 52 / 41 |
| `armor_break` | 0.0 / 0.0 | -14 (shin_L) | 8 / 87 | 48 / 61 |

The file still passes the gate (0 errors, the one height warning), the Blender re-import plays all 34 clips (2.7e-5),
the cannon rides `weapon_R` (1.5e-7), `check_clips.py` reports 0 problems, and re-exporting is byte-identical (sha256
`49da26a1…`, 16.89 MB).


## 4. The game-size read

**Setup.**

- [`review/lineup.png`](review/lineup.png) uses the client camera: 55° pitch, yaw 0, orthographic, 22 m view height at
  1080p, 49.1 px/m, true pixels. The shading is the pipeline's toon preview (`s3lib.make_toon_cycles`: a three-band
  ramp times the base colour, a rim and the emissive), **not** the engine's ToonMaterial.
- The top row faces screen-right and the bottom row faces the camera. It is shown on the cinder ground and on a lighter ash ground, and
  at 2x.
- [`review/horde.png`](review/horde.png) is a whole 1920 x 1080 frame. He is braced in the Siege Stance among 140 Cinder
  Wastes swarm enemies, 55 % of them crowding him as the taunt makes them, with Brax 5 m away. There is no P1 ground
  ring and no VFX, which the game has.
- The numbers are the pixels of each subject facing the camera ([`review/lineup_stats.json`](review/lineup_stats.json);
  CIE L*).

| Subject | Opaque px (w x h) | L* mean | L* p10 / p90 | Gold | Glow | Red |
|---|---|---|---|---|---|---|
| Greybox capsule, 2.3 m, r 0.55 (his collider) | 54 x 87 | 48.0 | 33.8 / 53.2 | - | - | - |
| Brax, `idle_combat` | 47 x 70 | 40.0 | 15.6 / 68.4 | 8 % | 14 % | 3 % |
| **Valdris, `idle_combat`** | **83 x 101** | **30.7** | 13.0 / 56.0 | **20 %** | 4 % | 9 % |
| Valdris, walk f7 / `fire_light` shot / Siege Stance | 113 x 117 / 96 x 101 / 82 x 108 | 29.9 / 30.5 / 30.7 | 12.6-12.9 / 55-58 | 18-20 % | 4-6 % | 8-10 % |
| Valdris, Bulwark launch / land | 79 x 103 / 112 x 110 | 31.5 / 30.1 | 12.6-13.4 / 54-61 | 19-20 % | 3-7 % | 10-11 % |
| Valdris, death (last frame) / wraith | 120 x 129 / 114 x 88 | 28.3 / 31.7 | 12.4-13.2 / 50-57 | 14-22 % | 3-4 % | 26 % / 9 % |
| Cinderling | 47 x 47 | 35.4 | 15.8 / 48.8 | 1 % | 6 % | 5 % |
| Ashrunner | 26 x 53 | 48.5 | 17.0 / 68.9 | 7 % | 14 % | 0 |
| Clinker | 42 x 42 | 33.7 | 7.5 / 68.8 | 0 | 0 | 0 |
| Emberwisp | 26 x 42 | 36.1 | 12.4 / 53.9 | 4 % | 8 % | 0 |
| Slagspitter | 50 x 52 | 32.8 | 10.4 / 68.6 | 6 % | 12 % | 0 |
| Kindlejack | 40 x 42 | 43.8 | 9.6 / 92.4 | 2 % | 0 | 0 |

**Does he read as the walking siege engine in under a second?**

- **On open ground: yes.** He is the largest thing on screen: 1.4x Brax's height and 1.8x his width, twice a swarm
  enemy. The square, flat-topped block of the pauldrons with its gold frame reads first, the cannon with its glowing
  muzzle second, the anvil's light bar third.
- **In the taunt crowd: not reliably.** It took me about a second or two to find him in the horde frame, by his size
  and the gold-framed square top. His dark mass does not separate:
  - the cinderlings' grey shells and the slagspitters' brown cones sit at nearly the same value;
  - the gold lines chop his silhouette into bars the size of swarm details.

  The game's P1 ring, the muzzle flash and the Siege glyph will help. The body alone does not carry it.

**Darker than every swarm enemy?**

- **By the mean, yes**, but only just: L* 28-32 against 32.8 for the slagspitter and 33.7 for the clinker (and 35-49
  for the rest).
- **In his darkest tenth, no:** it is lighter (L* 12-13) than the clinker's (7.5), the kindlejack's (9.6) and the
  slagspitter's (10.4).
- **Why.** The brief's rule was "the darkness is his pop" (plate L* 15-18). It does not survive the gold: rims cover
  18-22 % of his pixels at game size (Brax 8 %, the swarm 0-7 %), and the anvil top adds a grey bar.

**Gold trim and anvil visible?**

- **Gold: yes, rather too much.** Every pauldron step, arm band and plate edge carries a 1-2 px gold line. At 22 m he
  reads as gold-and-black stripes, where the concept is dark forged metal with gold at the rims. The stage-5 review said
  the same ("boxier and busier").
- **Anvil: yes, facing the camera:** a light grey bar across the chest. In profile it is a thin wedge.
- **The red cape is hidden** when he faces the camera (8-10 % red). It reads from the side and behind, and in the
  death's held frame: 26 % there, was 10 % before the fix. The cape now lies over his rear leg, so from above it spreads
  out behind him instead of hanging through the leg. With only five bones per chain it drapes in straight segments: a
  close-up shows planes, but at game size it reads as a red spread.

**Not changed** (a design call for the user's stage-2 approval). A recommendation for a later stage-2 texture pass:

- take the gold off the inner step edges of the pauldron tops and the arm bands, and keep it on the outer silhouette
  rims, so the plate reads as one dark block with a gold outline;
- keep the anvil's top lighter than the plate, as the brief asks.

That would move the mean toward L* 25 and gold under 10 % without losing the rim read.

## 5. Still open (not fixed here)

1. **One-shot foot skids** (row 11). Who: stage 4, the keys in `s4_valdris.py`.
   - The knockdown's right sabaton skids 64 mm in one frame (f3), and the death's 47.5 mm.
   - Also Bulwark 23 / 31.5, Siege Stance enter 27.7 and exit 25.5, `hit_heavy` 20.8 and the revive 16 mm per contact.
   - At 49 px/m, 64 mm is 3 px: a visible skid as he is floored.
2. **The game-size value read** (§4): gold coverage and the darkness margin. The user's stage-2 call.
3. **Cloth that is left** (§3.3):
   - the cape's side edges touch the calves in the gait (up to 153 faces);
   - the thighs still brush the loincloth's side panels in 583 frames;
   - the hem swings up to 0.17 m in a frame in the idle and up to 0.5 m at the big impacts (`reforge_in`,
     `forge_hammer`);
   - the braids still enter the pauldron lames in `ping` and `armor_break` (11-17 vertices).

   A runtime cloth spring in the client would replace these channels (`anim_report.md` §5).
4. **Plate-into-plate clipping** as stage 4 reported it, unchanged: the worst is 389 vertices (`strafe_left` f3), the
   median of the clip medians 128. It shows at the armpits and knees in close-ups.
5. **`cloth.json`'s `deepest_mm`** decides inside / outside by the nearest face's normal. It reports false depths up to
   0.6 m (the walk's cape), so trust the ray-parity counts in `render_checks.json`. A later cloth pass could switch
   its penetration report to ray parity.
6. **For the weapon track (`colossus_cannon`):**
   - the GLB is single-sided with 398 open edges at the sleeve rims. Nothing shows while his forearm fills it, but an
     empty cannon (a pickup, the armory) would show through;
   - the earlier asks stand: a wider bore, a shorter rear cuff, and `grip_L` within reach.
7. **Not checked in the engine:** no Bevy import test, and the ToonMaterial is not the review's toon preview. The
   in-engine read of §4 is still owed.
8. **Human gates, all pending:**
   - the visual approvals of stages 2, 3, 4 and 5;
   - the cannon side with the anvil kept;
   - the head size.

## 6. Shared tools, Brax, and what was touched

- **`tools/blender/gf_hero/export_glb.py`** (shared) is the one shared file changed:
  - it writes `clip_info.<clip>.base` only when `clips.json` sets a base;
  - it appends the exceptions to `playback.upper_layer` only when a clip has one.
- **Brax is unchanged.** Brax's stage-5 export was re-run with the changed exporter in a scratch copy of the
  repository: `brax.glb`, `brax.meta.json` and his `export_report.json` came out **byte-identical**
  ([`review/brax_regression.json`](review/brax_regression.json)). Nothing under `art/characters/brax/` was written.
- **Valdris-only files:**
  - `s4_valdris_cloth.py` (the fixes);
  - the three new `valdris_review*.py` tools.
- **Re-run from the cloth step on:**
  - `production/valdris_anim.blend`;
  - `reports/anim/` (`cloth.json`, `render_checks.json`, `gltf_check.json`, every clip sheet and board);
  - the shipped `valdris.glb` + `valdris.meta.json`;
  - `reports/export_report.json`;
  - `reports/stage5/`.
- **Stages 2 and 3 are untouched.**
- **Docs:**
  - `status.json` and `manifest.json` were merged (new `review_stage2_5` blocks, new metrics and hashes);
  - `README.md`: the stage table was out of date;
  - `anim_report.md`: the cloth claims are corrected in place;
  - `docs/ART_PIPELINE.md`: the Valdris lines;
  - `docs/art/GF_HERO_SKELETON.md`: an additive note on the sidecar's `base` field.
- **Not touched:** `crates/`, `assets/content/`, `art/weapons/`, `art/enemies/`, `tools/blender/gf_assets/`,
  `tools/comfy/`.

## 7. Reproduce

```sh
python tools/blender/gf_hero/validate_glb.py assets/models/characters/valdris.glb assets/models/characters/brax.glb \
       --blender "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"          # the gate CI runs
python tools/blender/gf_hero/s4_valdris_run.py --from cloth                              # the fixed cloth pass + audit, sheets (~18 min)
python tools/blender/gf_hero/run_stage5.py valdris                                       # export, re-import, sheets, gate (~45 s)
blender -b --factory-startup --python-exit-code 1 -P tools/blender/gf_hero/valdris_review.py          # ~3 min
blender -b --factory-startup --python-exit-code 1 -P tools/blender/gf_hero/valdris_review_lineup.py   # ~1.5 min, Cycles CPU
<comfy-python> tools/blender/gf_hero/valdris_review_sheets.py [--before <a valdris_review.py --glb <old file> run>]
```

The renders behind the sheets go to `work/review/` (gitignored). `valdris_review.py --glb <file> --out <dir>` measures
any other build, so the "before" columns come from the `39988a2` file (sha256 `e7fd6b4c…`).
