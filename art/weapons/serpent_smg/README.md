# Serpent SMG (`serpent_smg`)

**Status: the AI build is done and waiting for the user's approval.** meta.json says
`ai_final_pending_user_approval`, and `status.json` has stage `2_user_approval` set to `pending_human`.

This is Kael's signature weapon. It is built end to end from code with `tools/blender/gf_assets`. There
is no concept art and nothing was edited by hand:

```text
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P art/weapons/serpent_smg/source/serpent_smg_build.py -- [--size 1024] [--no-review] [--quick]
```

`tools/blender/gf_assets/weapons/serpent_smg.py` runs the same script, following the toolkit's
convention. One run takes about 35 s on the CPU and rebuilds everything listed under Files. `--quick`
builds only the geometry and writes flat-colour Workbench turnarounds and game-size silhouettes to
`work/quick/` in a few seconds. That is the loop for silhouette changes.

![3/4 view](reports/serpent_smg_34.png)

Two review images go with it:

* [reports/serpent_smg_review.png](reports/serpent_smg_review.png): the standard sheet (turnaround,
  in-game camera at 1x and 3x, silhouettes, textures).
* [reports/serpent_smg_held.png](reports/serpent_smg_held.png): the gun in the 2.2 m mannequin's
  right hand at its grip frame, through the in-game camera (55° pitch), zoomed and at true size.

## Brief

The row in `content/sheets/chassis.csv` says: Kinetic, style Needle, Auto, 11 shots/s, damage 7, 6°
spread, range 11, tags `rapid; kael`, and the line "A hissing stream of needles. Never stops talking."
It is the `signature_chassis` of **Kael, the Wraithshot** (`characters.csv`: a ghost gunslinger and
agile duelist, colour `#9A7CFF`).

* **Family RAPID, verb THE STREAM** (docs/art/WEAPONS.md section 5). **Tier `one_handed`**: 1,000-2,500
  tris, sockets `grip_R` and `muzzle`, no `grip_L`. The tier is confirmed here.
* **One serpent is the whole gun.**
  * **Tail.** A beaded bone rattle lies on the back of the receiver.
  * **Body.** It winds **four tight coils** around the bronze receiver. They are the rapid family's
    "many small repeated elements": a dark/bronze stripe rhythm and a serrated top and bottom edge in
    the 1x silhouette.
  * **Neck.** It runs forward, **lean and slightly raised** like a snake about to strike, along a
    thin dark-iron barrel. Four **glowing needle quills** on its spine sweep backward, which gives
    the forward sweep and a row of small lights leading to the muzzle.
  * **Head (the muzzle).** A wedge viper skull with a bronze crown plate and backswept bone horns.
    The jaws are wide open, with two long bone fangs and small lower fangs. The eyes glow and have
    slit pupils. The throat, palate and tongue glow, and the throat spits the **needle barrel**, the
    family's small muzzle.
* **Drum magazine.** It sits Thompson-style under the front coils, in front of the grip. Its faces
  are painted as a **coiled serpent tail** in scales, and its bronze band carries **engraved
  overlapping scales**. This covers the "coiled drum" and the "scale-textured drum" in both briefs.
* **Grip.** A raked pistol grip in dark wood with two dark-violet leather wraps, a gold pommel and a
  bronze trigger guard that runs into the drum.

## Paint and value

* **Value rhythm, back to front:** a bone rattle; then dark coils over a bronze core (stripes); then a
  dark neck and head; then the brightest values at the front: bone fangs and horns, the glowing eyes
  and mouth, and the white-hot needle. The bronze drum is the mid-value mass below.
* **Snake skin.** A post-pass on top of `gfa_paint.paint`, in the build script (`skin_postpass`).
  gfa_paint itself is not changed, because the hook is swapped in only for this run. Each texel is
  mapped into body coordinates: arc length along the serpent's centre-line and angle around the tube.
  The skin is painted there as a **diamond-back chain**: bone-gold outlines with a black halo, a
  lighter violet fill and a muted-bronze inner diamond. There is a soft lattice of overlapping scales,
  lighter at each scale's free tip, plus bone flecks low on the flanks and bone **belly scutes** on the
  inner side of the coils. The same painter draws the spiral on the drum faces. The body stays a
  **dark** mass at game size, and the pattern only shows up close.
* **Everything else** uses the stock gfa_paint zones: flat value planes, cavity darks, broken brushy
  edge highlights, brushed streaks on the bronze, wood grain, and a leather grain on the wrap. The
  viper's **eye stripe** is a painted line decal (bone-gold with a black halo, like the body pattern).
* **Glow (emissive texture)** is Kinetic: core `#FFF6DE`, then `#F4E3C1` (`palette.rs`), then warm
  gold `#D9A85C`/`#E09A48` at the edges. It is in the eyes (with a dark slit pupil and no emission
  there), the throat, palate and tongue, the four quills (at 0.75 strength) and the needle, which is
  white-hot at the tip. There is no telegraph red.
* **Palette:** scales `#2E2438`, diamond fill `#4E4062`, outline `#D6B97E`, belly `#D2C09A`, bronze
  `#B87A35`, gold `#E4B24A`, bone `#E8DCC0`, iron `#3B3340`, wood `#4E2E22`, wrap `#3E2A4E`. The violet
  in the scales and the wrap is a quiet nod to Kael's `#9A7CFF`. It stays out of the glow channel, which
  belongs to the Kinetic element.

## Metrics (last build)

| | |
|---|---|
| Triangles | 2,370 (one-handed budget 1,000-2,500) |
| Parts / zones | 43 parts in 13 paint zones, one mesh, one material `M_serpent_smg` (roughness 0.85, metallic 0, single-sided) |
| Textures | base colour 1024² and emissive 1024² (PNG, embedded). Texel density is 910 px/m median (823-961), atlas coverage 40 % |
| Length | 0.77 m from the rattle to the needle tip (the SMG class is 0.6-0.85 m), about 38 px at 1080p. The drum is 0.124 m across |
| GLB | 1.2 MB, no compression extensions (safe for bevy_gltf 0.20); validation OK with no warnings |
| Sockets (glTF) | `grip_R` (0, 0, 0); `muzzle` (0, 0.095, -0.528) at the needle tip; `glow_core` (0, 0.095, -0.378) in the throat |

**Grip frame.** The origin is the right palm centre on the pistol grip. Blender +Y is the barrel
(glTF -Z) and +Z is up. The bore axis sits 0.095 m above the palm. The weapon is an identity child of
the aim pivot or `weapon_socket_R` (docs/art/WEAPONS.md section 7).

## Files

| Path | In git |
|---|---|
| `assets/models/weapons/serpent_smg.glb` + `.meta.json` | yes (the GLB through LFS) |
| `source/serpent_smg_build.py` | yes: the build script |
| `source/serpent_smg.blend` | yes (LFS); it references the textures relatively |
| `textures/serpent_smg_basecolor.png`, `_emissive.png` | yes (LFS) |
| `reports/serpent_smg_review.png`, `_34.png`, `_held.png`, `build_report.json` | yes |
| `work/` (every review render, the sheet layouts, `quick/`) | no (`.gitignore`) |

## Open points for the user's review

* **The hold.** The review mannequin holds the gun at chest height with the grip frame from
  `gfa_render.weapon_hold_matrix`. The real hold comes from GF_Hero_v1's `weapon_socket_R`.
* **The mouth glow.** The glowing palate and tongue are what make the open jaws read from the side.
  If they look too white in the engine, lower `strength` on the `glow_throat` recipe before
  shrinking the geometry.
* **The quills.** They are glowing Kinetic needles, which is a design choice: the needles the serpent
  spits. For a plain look, set the `quill` zone's `emit` to None to turn them into bone spines.
* **The Kael tie-in.** Kael has no model yet. The violet in the scales and the grip wrap is an
  assumption, and it is two hex values in `SKIN` and `RECIPES` if his palette ends up different.
