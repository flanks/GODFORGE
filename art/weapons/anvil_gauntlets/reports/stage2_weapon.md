# anvil_gauntlets — stage 2 weapon model (made by AI, 2026-09-25)

User decisions of 2026-09-25, relayed by the workflow coordinator:
- weapons come off the hero bodies, one model per chassis on hand sockets;
- there is no human artist for stage 2.

The remaining human gate is the user's visual approval.

Sheets: [`stage2/stage2_weapon.png`](stage2/stage2_weapon.png) (open and fist close-ups, attach frame),
[`stage2/stage2_weapon_wireframe.png`](stage2/stage2_weapon_wireframe.png),
[`stage2/stage2_weapon_textures.png`](stage2/stage2_weapon_textures.png). On the hero:
`art/characters/brax/reports/stage2/stage2_armed.png` and `stage2_ingame.png` (armed rows).

## Build

`tools/blender/gf_hero/s2_weapon.py` + `s2_gauntlet.py`, with parameters in `stage2_weapon.json`. It is
authored around Brax's fitted body (`art/characters/brax/work/brax_s2_body.blend`), then re-expressed in each
hand's socket frame:

| Piece | Construction |
|---|---|
| elbow cuff | hexagonal bronze band with a raised centre ridge. Its inner flats clear the forearm: inner radius = (arm radius + 8 mm) / cos 30°. A cog boss sits on the lower front |
| forearm | lava core tube (emissive) whose ellipse grows to keep at least 15 mm over the wearer's forearm, under 32 faceted basalt plates. The plates are a periodic Voronoi tessellation, each a chamfered prism, and the grooves show the core |
| strap frame | 6 bronze bars forming an elongated hexagon along the back of the forearm, ending in a bronze ring on the back of the wrist (approved turnaround sheet) |
| wrist band | hexagonal bronze band |
| hand | tapered hand block with 6 rock plates on its back, and 4 knuckle plates |
| fingers | 4 × 3 + thumb × 3 bevelled rock segments. The joint faces are emissive. The open variant curls 3/7/9°; the fist curls 88/92/62° with the thumb across the front |

**Triangles:** 2,864 per gauntlet, so 5,728 for a pair (budget 4–8k), in each variant.

**Topology:**
- 70 closed pieces per gauntlet;
- 0 boundary and 0 non-manifold edges;
- the Voronoi plate caps are triangulated, so the mesh is quads and triangles only.

**Variants:** open and fist have identical topology, so they share one UV layout and one texture.

## Texture

One 1024² sRGB base colour and one 1024² sRGB emissive, painted the same way as the hero's (`s2_paint.py`):
- **rock:** dark basalt `#291F1E`, with the top faces lifted toward `#4A3A36` for the 55° camera and the plate
  chamfers catching a little light;
- **fine lava cracks:** in patches;
- **bronze:** a painted highlight band;
- **lava:** core and joints fully emissive.

Texel density is about 300 px/m. That is lower than the hero's 520 px/m on purpose: the weapon has its own
1024 atlas. Raise `size` in `stage2_texture.json` to 2048 to match the hero.

## Attach frame

- **Origin:** the palm centre.
- **+Y:** along the fingers.
- **+Z:** out of the back of the hand.
- **+X:** Y × Z.

T-pose placement on Brax:
- **Left:** origin (1.022, 0.032, 1.733) m, with X = −Y world, Y = +X world, Z = +Z world.
- **Right:** the mirror.

Stage 3 puts `weapon_L` / `weapon_R` sockets there (children of `hand_L` / `hand_R`), and the objects parent
with an identity local transform. The frames are recorded in `stage2/parts.json` (`socket_frame_tpose`).

## Honest notes

- It is one rigid piece per hand, as asked. If a strong wrist flex shows the forearm shell cutting into the arm,
  the forearm section (cuff, core, plates, frame) can be split off onto a `lowerarm` socket. The pieces are
  already separate closed parts, grouped only by object.
- The fist variant is built for punches from a T-pose hand frame. Check the thumb placement against the
  stage-4 punch poses.
- The texture density is lower than the hero's (see above).
