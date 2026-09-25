# anvil_gauntlets — the forge-gauntlets chassis weapon

Chassis `anvil_gauntlets` (`content/sheets/chassis.csv`): "Short-range shotgun-fists", Melee, Kinetic, style
`Fist`. It is Brax's signature chassis, but **it is not part of Brax's body**. On 2026-09-25 the user decided
that weapons come off the hero bodies. Every chassis is its own model, attached to hand sockets, so any
hero can wield any chassis.

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md) §5 "Weapons". Current state:
[`status.json`](status.json). Nothing here is final; the user's visual approval and the final Hades-II bar
are human gates.

## What it is (v2, polish pass 2026-09-25)

A rigid left/right pair of basalt forge-gauntlets. It is built on the s202 stage-1 blockout's **own
gauntlet** and follows the approved Brax sheets (`art/characters/brax/references/`).

How the blockout is used:
- its radius around the gauntlet axis is sampled per side;
- its bolts are filtered out;
- its plate lumps give the plate centres;
- the plate tops follow its surface, radially scaled 1.04–1.10 so the fists read bigger than the head.

The build axis is moved 2.8 cm forward onto the wearer's forearm.

Pieces:
- a hexagonal bronze elbow cuff with studs and a cog boss;
- chunky faceted basalt plates: a shoulder ring, a top ring and an off-centre peak, like hand-sculpted
  stylised rock. They sit over a glowing lava core with 1.5 cm seams, and the lava light bleeds up the plate
  feet;
- the hexagonal bronze strap frame on the back of the forearm, ending in a wrist ring;
- a hexagonal wrist band with studs;
- a broad plated hand core that covers the wearer's fingers;
- four massive knuckle chunks;
- four fingers and a thumb of faceted rock segments with glowing joints.

Every piece is closed and manifold.

| Object | Variant | Tris | Notes |
|---|---|---|---|
| `GAUNTLET_L`, `GAUNTLET_R` | open (the concept's T-pose hands) | 3,858 each | the default |
| `GAUNTLET_FIST_L`, `GAUNTLET_FIST_R` | closed fist, thumb across the front | 3,858 each | identical topology, so they share the UVs and the texture; use them for punches, which hides the fingers |

Budget: about 8k tris for the pair (7,716).

Texture:
- its own 1024² sRGB base colour, 1024² sRGB emissive and 1024² Non-Color tangent-space normal map
  (`textures/`);
- one material `M_anvil_gauntlets`;
- the normal map is baked from the radially scaled blockout gauntlet onto the rock plates (hit-distance mask,
  normalised blur);
- the emissive covers the lava core, joint faces, plate feet and cracks; the runtime scales it with Heat and
  Meltdown.

The glTF check (`reports/stage2/gltf_check.json`) confirms:
- base colour, emissive and normal textures are exported;
- TANGENT is present on every primitive;
- nothing is in `extensionsRequired`.

## Attach frame (stage 3 sockets)

Each gauntlet is authored in its hand's **weapon socket frame**:

- origin = palm centre (the mean of the hand's surface between the wrist joint and the knuckle line);
- **+Y along the fingers**, **+Z out of the back of the hand**, +X = Y × Z;
- left and right are mirrored frames.

In Brax's T-pose (Blender axes, Z up, facing −Y), the left socket sits at (1.016, 0.033, 1.734) m with
X = −Y world, Y = +X world, Z = +Z world. The right socket is the mirror, with X = +Y world and
Y = −X world.

GF_Hero_v1 (stage 3, 2026-09-25) has `weapon_L` / `weapon_R` sockets, children of `hand_L` / `hand_R`, at exactly
this frame; in glTF the gauntlet is an identity child of the socket node, proven to < 1 µm with the exported
gauntlets (`art/characters/brax/reports/stage3/gltf_check.json`, `docs/art/GF_HERO_SKELETON.md` §3). It is a sleeve
weapon: clips keep the wrist straight, and the elbow cuff presses into the biceps past about 40° of elbow flexion
(`art/characters/brax/reports/rig_report.md` §4). The weapon objects then parent with an identity local transform: their object transform in
`production/anvil_gauntlets_stage2.blend` is only the T-pose placement, so the review renders line up with
Brax. The frame values are recorded in `reports/stage2/parts.json` (`socket_frame_tpose`) and in Brax's
`reports/stage2/body_fit.json` (`hand_frames`).

The gauntlet encloses the wearer's hand and forearm:
- the lava core keeps at least 14 mm of clearance over Brax's forearm and hand extents;
- the hexagonal cuff and band are sized so that their flats clear the arm.

For another hero, rebuild it against that hero's fitted body (`s2_weapon.py` takes the body) or scale it on
the socket.

## Files

| Path | What | In git |
|---|---|---|
| `stage2_weapon.json` | part parameters: blockout field sampling, radial scale, plates, bands, hand, fingers, fist curl | yes |
| `stage2_texture.json` | UV, bake and paint settings (1024 atlas) | yes |
| `production/anvil_gauntlets_stage2.blend` | the four objects + material | yes (Git LFS) |
| `textures/anvil_gauntlets_{basecolor,emissive,normal}.png` | painted textures + normal map | yes (Git LFS) |
| `reports/stage2/` | review sheets (open, fist, attach frame, wireframe, textures, before/after) + build/texture/glTF JSON | yes |
| `reports/stage2_weapon.md` | the stage-2 report for the weapon | yes |
| `work/` | parts file with the bake sources, renders, scratch GLB | no (regenerated) |

Rebuild (with Brax, whose signature weapon it is): `python tools/blender/gf_hero/run_stage2.py brax --from weapon`.
