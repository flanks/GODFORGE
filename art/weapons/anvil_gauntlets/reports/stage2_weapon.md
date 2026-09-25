# anvil_gauntlets — stage 2 weapon model (made by AI, 2026-09-25; v2 polish pass)

User decisions of 2026-09-25, relayed by the workflow coordinator:
- weapons come off the hero bodies, one model per chassis on hand sockets;
- there is no human artist for stage 2.

The remaining human gate is the user's visual approval.

The orchestrator's review of v1 said the gauntlets read as "boxy tubes with a gold band". v2 rebuilds them
on the blockout's own gauntlet, with chunky rock, thick glowing seams and bigger hands. Before/after:
[`stage2/stage2_weapon_before_after.png`](stage2/stage2_weapon_before_after.png).

Sheets: [`stage2/stage2_weapon.png`](stage2/stage2_weapon.png) (open and fist close-ups, attach frame),
[`stage2/stage2_weapon_wireframe.png`](stage2/stage2_weapon_wireframe.png),
[`stage2/stage2_weapon_textures.png`](stage2/stage2_weapon_textures.png). On the hero:
`art/characters/brax/reports/stage2/stage2_armed.png` and `stage2_ingame.png` (armed rows).

## Build

`tools/blender/gf_hero/s2_weapon.py` + `s2_gauntlet.py`, with parameters in `stage2_weapon.json`.

**The blockout as a field.** Per side, the s202 blockout's radius E(θ, x) around the gauntlet axis is
sampled every 2° and 4 mm by rays toward the axis:
- a median filter (9 × 7 cells) removes the bolts;
- a Gaussian gives its smooth base B;
- the plate centres are the maxima of the lumps E − B, at least 4.6 cm apart. There are 18 per side between
  x = 0.66 and 0.845 m, where the blockout has plates; past that it has a rivet row, replaced by one ring of
  11 synthetic plates.

The whole field is moved 2.8 cm forward onto Brax's fitted forearm (`build_offset`). The blockout's axis
sits behind it.

| Piece | Construction |
|---|---|
| elbow cuff | hexagonal bronze band with a raised centre ridge and 6 studs. Its inner flats clear the forearm by 12 mm. A cog boss sits on the lower front |
| forearm | lava core tube that follows B (scaled) and keeps at least 14 mm over the wearer's forearm, under 29 chunky faceted basalt plates. Each plate is a Voronoi cell of the blockout's plate centres: side walls, an irregular shoulder ring, a top ring and an off-centre peak. The tops follow E × S (the blockout surface, radial scale 1.04–1.10), with 1.5 cm seams |
| strap frame | 6 bronze bars forming an elongated hexagon on the back of the forearm, seated on the plate tops, ending in a bronze wrist ring (approved turnaround sheet) |
| wrist band | hexagonal bronze band with 6 studs |
| hand | a broad superellipse core, 0.33 m wide and up to 0.19 m thick, running to 1.19 m so the wearer's fingers end inside it. It carries 28 plates and 4 massive knuckle chunks |
| fingers | 4 × 3 + thumb × 3 faceted hexagonal rock segments (flattened underside, top ridge) fanned ±9°, with glowing joint faces. The open variant curls 4/8/10°; the fist curls 88/95/70° with the thumb across the front |

**Triangles:** 3,858 per gauntlet, so 7,716 for a pair (budget about 8k), in each variant.

**Topology:**
- 100 closed pieces per gauntlet;
- 0 boundary and 0 non-manifold edges;
- the mesh is quads and triangles only.

**Variants:** open and fist have identical topology, so they share one UV layout and one texture.

## Texture and bakes

One 1024² sRGB base colour, one 1024² sRGB emissive and one 1024² Non-Color tangent-space normal map.

**Normal map.** Baked from a copy of the blockout gauntlet that is radially scaled and moved like the build
(`BAKESRC_L` / `BAKESRC_R` in the work file, never shipped). It is baked onto the rock plates with a 3 cm
cage:
- a texel whose hit is more than 0.8–2 cm from the plate surface fades to flat;
- a 1.2 px normalised blur is applied;
- strength is 0.8.

About 31 % of the rock takes detail: the forearm plate tops, where the build follows the blockout. The hand,
fingers and plate walls keep their faceted geometry.

**Paint** (`s2_paint.py`):
- dark basalt `#291F1E` with a per-plate tone (some cooler purple-grey chunks);
- top faces lifted a little for the 55° camera, and chamfers catching light;
- self-AO folded in;
- the lava light bleeding up the plate feet, and fine lava cracks in patches;
- bronze with a painted highlight band;
- the lava core and joints fully emissive.

Texel density is about 290 px/m, against the hero's 512 px/m. Raise `size` in `stage2_texture.json` to 2048
to match.

**glTF check** (`stage2/gltf_check.json`):
- `M_anvil_gauntlets` exports base colour, emissive and normal textures;
- all 4 primitives carry TANGENT;
- nothing is in `extensionsRequired`.

## Attach frame

- **Origin:** the palm centre.
- **+Y:** along the fingers.
- **+Z:** out of the back of the hand.
- **+X:** Y × Z.

T-pose placement on Brax:
- **Left:** origin (1.016, 0.033, 1.734) m, with X = −Y world, Y = +X world, Z = +Z world.
- **Right:** the mirror.

Stage 3 puts `weapon_L` / `weapon_R` sockets there (children of `hand_L` / `hand_R`), and the objects parent
with an identity local transform. The frames are recorded in `stage2/parts.json` (`socket_frame_tpose`).

## Honest notes

- **At the in-game camera:** the gauntlets now read as lava-seamed rock fists with bronze cuffs. From 55°
  above they read more orange-patterned than dark-massed: the seams and plate feet glow, and the plate tops
  catch the key light. The balance should be judged again with the client's own toon ramp and bloom.
- **Silhouette:** the open hand is palm-down with the fingers fanned in plan, as the rig needs. The
  concept's front view shows the hands fanned vertically, so the armed front IoU dropped from 0.867 to 0.855.
- **Rigidity:** it is one rigid piece per hand, as asked. If a strong wrist flex shows the forearm shell
  cutting into the arm, the forearm section (cuff, core, plates, frame) can be split onto a `lowerarm`
  socket. The pieces are already separate closed parts.
- **Fist variant:** it is built for punches from a T-pose hand frame. Check the thumb against the stage-4
  punch poses.
