# anvil_gauntlets — the forge-gauntlets chassis weapon

Chassis `anvil_gauntlets` (`content/sheets/chassis.csv`): "Short-range shotgun-fists", Melee, Kinetic, style
`Fist`. It is Brax's signature chassis, but **it is not part of Brax's body**. On 2026-09-25 the user decided
that weapons come off the hero bodies. Every chassis is its own model, attached to hand sockets, so any
hero can wield any chassis.

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md) §5 "Weapons". Current state:
[`status.json`](status.json). Nothing here is final; the user's visual approval and the final Hades-II bar
are human gates.

## What it is

A rigid left/right pair of basalt forge-gauntlets, built to the design of the approved Brax sheets
(`art/characters/brax/references/`):
- a hexagonal bronze elbow cuff with a cog boss;
- faceted basalt plates over a glowing lava core (the grooves between the plates glow);
- a hexagonal bronze strap frame along the back of the forearm, ending in a ring on the back of the wrist;
- a hexagonal wrist band;
- a hand block with rock plates on its back, and knuckle plates;
- four fingers and a thumb, each three chunky rock segments with lava in the joints.

Every piece is closed and manifold.

| Object | Variant | Tris | Notes |
|---|---|---|---|
| `GAUNTLET_L`, `GAUNTLET_R` | open (the concept's T-pose hands) | see `reports/stage2/texture.json` | the default |
| `GAUNTLET_FIST_L`, `GAUNTLET_FIST_R` | closed fist, thumb across the front | same | identical topology, so they share the UVs and the texture; use them for punches, which hides the fingers |

Budget: about 4 to 8k tris for the pair. Texture: its own 1024² sRGB base colour + 1024² sRGB emissive
(`textures/`), with one material `M_anvil_gauntlets`. The emissive covers the lava core, joint faces and cracks;
the runtime scales it with Heat and Meltdown.

## Attach frame (stage 3 sockets)

Each gauntlet is authored in its hand's **weapon socket frame**:

- origin = palm centre (the mean of the hand's surface between the wrist joint and the knuckle line);
- **+Y along the fingers**, **+Z out of the back of the hand**, +X = Y × Z;
- left and right are mirrored frames.

In Brax's T-pose (Blender axes, Z up, facing −Y), the left socket sits at (1.022, 0.032, 1.733) m with
X = −Y world, Y = +X world, Z = +Z world. The right socket is the mirror, with X = +Y world and
Y = −X world.

Stage 3 adds `weapon_L` / `weapon_R` sockets on GF_Hero_v1, children of `hand_L` / `hand_R`, at exactly
this frame. The weapon objects then parent with an identity local transform: their object transform in
`production/anvil_gauntlets_stage2.blend` is only the T-pose placement, so the review renders line up with
Brax. The frame values are recorded in `reports/stage2/parts.json` (`socket_frame_tpose`) and in Brax's
`reports/stage2/body_fit.json` (`hand_frames`).

The gauntlet encloses the wearer's hand and forearm. The lava core keeps at least 15 mm of clearance over
Brax's forearm and hand extents. The polygonal cuff and band are sized so that their flats clear the arm.
For another hero, rebuild it against that hero's fitted body (`s2_weapon.py` takes the body) or scale it on
the socket.

## Files

| Path | What | In git |
|---|---|---|
| `stage2_weapon.json` | part parameters: sizes, plates, bands, fingers, fist curl | yes |
| `stage2_texture.json` | UV / paint settings (1024 atlas) | yes |
| `production/anvil_gauntlets_stage2.blend` | the four objects + material | yes (Git LFS) |
| `textures/anvil_gauntlets_{basecolor,emissive}.png` | painted textures | yes (Git LFS) |
| `reports/stage2/` | review sheets (open, fist, attach frame, wireframe, textures) + build/texture JSON | yes |
| `reports/stage2_weapon.md` | the stage-2 report for the weapon | yes |
| `work/` | parts file, renders, logs | no (regenerated) |

Rebuild (with Brax, whose signature weapon it is): `python tools/blender/gf_hero/run_stage2.py brax --from weapon`.
