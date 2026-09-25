# gf_assets: build GODFORGE weapons and enemies from code

This is the headless Blender 5.2 toolkit that the weapon and enemy agents share. There is no human
artist, so every asset is modelled, painted, rigged, exported, validated and reviewed from a Python
build script. The user gives the final visual approval.

* The contracts: [docs/art/WEAPONS.md](../../../docs/art/WEAPONS.md) and [docs/art/ENEMIES.md](../../../docs/art/ENEMIES.md).
* Working examples: `weapons/sunspike_shotgun.py` (a shipped weapon) and `examples/swarm_example.py`
  (a rigged swarm crawler with all six clips; it writes to `examples/_out/`, which git ignores).

```text
set BL="C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
%BL% -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/weapons/sunspike_shotgun.py -- [--size 1024] [--no-review]
python tools/blender/gf_assets/gfa_validate.py assets/models/weapons/sunspike_shotgun.glb
```

**Machine rules.** Cycles runs on the CPU only, never EEVEE: the 8 GB GPU is shared with ComfyUI,
TRELLIS and the game. Renders stay at or under 1600 px. Many Blender jobs run in parallel. If Blender
fails to get a device, retry.

## Modules

| Module | Needs | What it gives you |
|---|---|---|
| `gfa_spec.py` | nothing | the contract as data: hero and camera numbers, faction palettes, element colours, budgets, required sockets and clips, GF_Swarm_v1 bones |
| `gfa_common.py` | bpy | `reset_scene`, CPU Cycles, `log`, paths (`pack_dir`, `model_path`, `rel`), JSON, `add_empty`, `frame_from_axes`, `count_tris`, `world_bounds`, colours (`hex_linear`), `write_pack_status`, `run_comfy_python`. **The axes are documented at the top of the file** |
| `gfa_model.py` | bpy, bmesh | primitives: `box` (chamfer, taper, shear), `loft_rect`, `cylinder`, `sphere`, `ico`, `lathe`, `ring`, `spike`, `horn`, `tube`, `band`, `catmull`; details: `stud`, `studs`, `rivet_row`, `panel_grid`, `plate_ring`, `ribbon`; operations: `xform`, `orient`, `aim_matrix`, `symmetrize`, `mirrored`, `chip_corners`, `noise_displace`, `jitter`, `mark_sharp`; 2D line generators: `crack_lines`, `rune_glyph`, `rune_band`, `sunburst`; and **`Assembly`**, which merges parts into one mesh with zone slots, per-part ids and bone groups |
| `gfa_paint.py` | bpy, numpy | `zone(...)` and `faction_zone(...)` recipes, `decal_lines(...)`, and **`paint_asset(obj, key, recipes, tex_dir, ...)`**: UV unwrap, Cycles CPU bakes, numpy painting, `<key>_basecolor.png` + `<key>_emissive.png`, one final material |
| `gfa_render.py` | bpy | toon preview (engine-like ramp, rim, ink hull), `turnaround`, `silhouette`, `mannequin`, `weapon_hold_matrix`, `ingame` (55° camera, true 1080p pixels), **`review_weapon`**, **`review_enemy`**, `contact_sheet` |
| `gfa_sheet.py` | PIL (ComfyUI python) | builds the contact sheet PNG from a layout JSON (< 2 MB) |
| `gfa_rig.py` | bpy | **GF_Swarm_v1** (`build_swarm_rig`, `validate_rig`), `skin_rigid`, `add_socket`, poses (`apply_pose`, `merge`), `cycle_clip` (seamless loops), `keyed_clip`, `swarm_clip_set` (all six clips) |
| `gfa_shell.py` | bmesh | **hollow armour**: `thick_patch(fn, nu, nv, thickness, keep=...)` builds a closed plate from a surface function and returns the outer skin + rims and the inner skin separately (paint the inside as a void). Surfaces `rev_fn` (revolve an (r, z) profile), `cap_fn` (dome), `grid_fn` (bent plate); keep-masks `jagged_keep` (torn edges), `bite_keep` (a bite out of a rim). Added by `enemies/forge_warden.py` |
| `gfa_rig_dedicated.py` | bpy | **dedicated rigs** (elites, bosses): `build_armature` from a bone table (GF_Hero_v1 core names in `HERO_CORE`, forward roll convention), `validate_core`, `skin_rigid` for any bone set, world-space posing (`aim_bone`, `two_bone_ik`, `set_matrix`, `rest_frame_now`), `Keys` (pose-to-pose parameter keys with easing), `bake_clip` (solve every frame, then key it; stashed like gfa_rig clips). Added by `enemies/forge_warden.py` |
| `gfa_boss.py` | bpy, bmesh | **bosses and big assets**: `build_rig` (bone table, all bones up with roll 0 = the creature frame, optional tilted bones), `skin_rigid` for any bone set, `cull_hidden_faces` (deletes faces buried inside a closed part on the same bone), `paint_scaled` (paints at e.g. 1/8 scale so the painter's brush features become boss-sized; recipes and decals stay in real metres), `alias_clip` (a second glTF name for a clip), review renders `ingame_frame` (true-pixel 16:9 crop of the game camera), `size_compare` (front view, hero mannequin, measuring pole), `clip_frames` (key-pose strips), `flat_views` (fast Workbench modelling previews). Added by `enemies/slag_king.py` |
| `gfa_export.py` | bpy | **`export_asset(kind, key, tier, root, ...)`**: prepares transforms, exports the GLB (+Y up, no compression, embedded PNGs, NLA tracks as clips), validates, writes `<key>.meta.json`, exits 1 on failure |
| `gfa_validate.py` | nothing (stdlib) | re-checks any shipped GLB against the contract; CLI; exit 1 on errors |

## New weapon in 8 steps

1. Read the chassis row (`content/sheets/chassis.csv`), and pick the family verb and tier in
   WEAPONS.md section 5.
2. Copy `weapons/sunspike_shotgun.py` to `weapons/<key>.py`. Set `KEY` and `TIER`, and pick the
   `ZONES` and the palette.
3. Model in **grip space**: origin = main-hand palm, +Y = barrel, +Z = up. Build parts with
   `gfa_model` and `a.add(part, zone)`. Keep the big masses chunky and the details few.
4. Add the sockets as empties under the root: `grip_R` (origin), `muzzle`, and `grip_L` for
   two-handed weapons, plus `glow_core` if there is a glow.
5. Write the `RECIPES` (one `P.zone(...)` per zone) and any line `decals()`.
6. Run the build. It paints, saves `art/weapons/<key>/source/<key>.blend`, exports and validates
   (exit 1 on failure), and writes the review sheet and `status.json`.
7. **Look at `art/weapons/<key>/reports/<key>_review.png`** with the Read tool. Does the family verb
   read in the 1x in-game silhouette? Does the surface look painted rather than noisy? Iterate.
8. Write `art/weapons/<key>/README.md` (the brief, decisions and metrics). Add
   `art/weapons/<key>/.gitignore` containing `work/`. Commit your paths only.

## New swarm enemy

Start from `examples/swarm_example.py`:

1. `Assembly(..., bones=gfa_rig.BONE_NAMES)`, and give every part a bone (`body`, `head`, `legs_a`,
   `legs_b`, `tail`).
2. `build_swarm_rig(pivots)`, then `skin_rigid(mesh, arm)`.
3. `add_socket(arm, "body", "hit_center", ...)`.
4. `swarm_clip_set(arm, key, ...)`, or your own `cycle_clip` / `keyed_clip`.
5. `paint_asset(...)`.
6. `export_asset("enemy", key, "swarm", arm, ...)`.
7. `review_enemy(...)`.

Elites and bosses get a dedicated rig (ENEMIES.md section 6), but they use the same painter, exporter,
validator and review. `enemies/forge_warden.py` is the worked elite: `gfa_rig_dedicated.build_armature`
with the hero core names, rigid skinning, a per-frame `Solver` (FK spine, IK-planted feet, props that
drive the arms holding them), `Keys` + `bake_clip` for every clip, then `paint_asset`, `export_asset`,
`review_enemy` and its own clip / scale sheets. Hollow, many-part models can pass
`paint_asset(..., uv_zone_scale={"void": 0.35}, uv_small_islands=(0.0012, 0.45))` so hidden inner
skins and thin rims take less of the atlas.

`enemies/slag_king.py` is the worked boss (12.8 m, 21.5k tris, 2048 px). It uses `gfa_boss`: a
part-built `Assembly` with buried-face culling, `paint_scaled` at 1/8, and a rig table where every
bone points up. Its clips are `gfa_rig.keyed_clip` / `cycle_clip` pose dicts that key every joint, so
each clip carries its phase: extra-arm scale, door state, and `_p2` twins. The build also writes four
review sheets (turnaround + size, in-game at true pixels, clip key poses, 3/4 hero). `--preview`
renders flat zone colours in about 10 s, for fast silhouette iterations.

## Paint recipe reference (`gfa_paint.zone`)

| Key | Default | Meaning |
|---|---|---|
| `base`, `shadow`, `light` | `#808080`, derived, derived | the painted value planes. A derived shadow is darker and more saturated, leaning red-violet or blue-violet |
| `planes`, `parts` | 0.05, 0.05 | ± value per flat plane (quantised face normal) and per part |
| `brush`, `brush_freq` | 0.035, 7 /m | low-frequency value noise (never grunge) |
| `stroke`, `stroke_amount`, `stroke_freq` | None, 0, (60, 6) | streaks along a direction: wood grain, drips, cloth |
| `cavity`, `cavity_width` | 0.7, 6 mm | a dark line on concave sharp edges |
| `ao`, `ao_range` | 0.55, (0.25, 0.7) | painted contact shadows from baked AO (thresholded, not a gradient) |
| `edge`, `edge_width`, `edge_breakup` | 0.75, 5 mm, 0.4 | brushy light strokes on convex sharp edges; the width wobbles and the stroke breaks up |
| `gradient` | None | `{"axis" \| "center"[+"axis"], "range", "color", "amount"}`: planar, radial or cylindrical |
| `spots` | None | patches (soot, verdigris, wet sheen) |
| `emit` | None | `{"color" (rim), "hot", "core", "mode": flat \| radial \| axis \| plane, "center", "axis", "radius", "range", "fade", "base_mix", "strength"}` |

Decals: `decal_lines(lines, frame, width, zones, color, rim, emit, mapping="planar" | "cylinder")`.
They are 2D polylines from `crack_lines`, `rune_band` or `sunburst`, projected along the frame's +Z.

Only **sharp** edges count as edges. `Assembly.add(shading="auto")` marks edges above 35°,
`shading="smooth"` only creases above 60°: round sides with no edge strokes, but crisp caps.
`shading="flat"` marks every edge, for faceted rock and obsidian.

## Conventions every script follows

* **Axes and units:** 1 unit = 1 m, Z up. Creatures face -Y (glTF +Z). Weapons are in grip space
  (+Y barrel → glTF -Z). See the header of `gfa_common.py` and WEAPONS.md section 2 for the engine
  mapping.
* **Names:** `key` is the content key (lower_snake_case) and the file stem. Clips are
  `{key}_{clip}[@loop]`. Swarm armatures are called `GF_Swarm_v1`.
* **Outputs:** `assets/models/<weapons|enemies>/<key>.glb` + `.meta.json`, and
  `art/<weapons|enemies>/<key>/{source,textures,reports,work}`. `work/` is local; the pack's
  `.gitignore` covers it.
* **Git:** `.glb`, `.blend` and `art/**/textures/**/*.png` go through LFS. Keep review PNGs under 2 MB.
  Stage your own paths only.
* **Changing the toolkit:** asset agents **add** files (`weapons/<key>.py`, `enemies/<key>.py`, extra
  helpers in new modules). Shared modules may only change in backwards-compatible ways: new optional
  arguments, new functions. If a default has to change, change it in your own recipe instead.

## Blender 5.2 notes (learned while building this)

* `Material.use_nodes` is deprecated and `node_tree` always exists. Clear it and build the nodes.
* The pixel filter width is `scene.render.filter_size` (there is no `cycles.pixel_filter_width`).
* Actions are layered: f-curves live in `action.layers[].strips[].channelbags[]` (`gfa_rig._fcurves`),
  and a new action needs a slot (`act.slots.new`).
* The glTF exporter keeps Blender **bone-local** axes, so a bone pointing up with roll 0 exports with
  an identity rest rotation. It converts **object** axes: an empty's +Y becomes -Z. Empties parented
  to bones export as children of the joint nodes.
* `sys.exit(1)` inside a `-P` script ends Blender with exit code 1. Keep `--python-exit-code 1` on the
  command line anyway, so an uncaught exception also fails.
* The glTF exporter ships Draco and meshopt. `gfa_export` switches both off, because bevy_gltf 0.20
  cannot load them.
