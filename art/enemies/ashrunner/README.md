# Ashrunner: the Cinder Wastes swarm hound (The Unmade)

A lean ash-grey hound of cinder and char with an ember-lined ribcage. It is built, painted, rigged on GF_Swarm_v1,
animated, exported and reviewed from code. **Status: `ai_final_pending_user_approval`.** The user gives the final
visual approval.

| | |
|---|---|
| Content row | `ashrunner` in `content/sheets/enemies.csv`: Swarm, P0, hp 18, speed 5.2, radius 0.36 × scale 1.0 (collider 0.36 m), `Swarmer(jitter: 0.6)`, packs of 2-4, colour `#F2A541`, greybox shape Hound. "Fast ash-hounds that hunt in pairs." |
| Faction | **The Unmade** (Cinder Wastes), glowing molten like the Slag King, with the Unmade teal as the marker |
| Verb | **SPRINT**: one shape verb that reads in under a second at about 40-70 px |
| Build | `tools/blender/gf_assets/enemies/ashrunner.py`, then `enemies/ashrunner_crowd.py` |

## Design decisions

* **Silhouette: an arrow.** The long, low jackal skull is held level with the spine. The chest is a deep keel
  under high withers, the waist is tucked, and the haunches are small and hard. The legs are long, and a brush
  tail streams straight back. Black char shards stream back off the neck like a wind-torn mane. Every long line
  points backward, so the hound reads as speed even standing still. Two big black jackal ears break the outline
  from the game camera. That is the canine read at game size: in an early pass the ears were pinned flat, and the
  crowd silhouette read as lizards.
* **The signature is the ember-lined ribcage.** The hide has burnt away over the chest. Four black rib hoops arc
  from keel to keel over a glowing ember core, and both outer long edges of every rib carry a broken, glowing
  ember stroke. From the 55° camera, pale ash shoulders and a pale rump frame a window of orange-lit black bars:
  a grey streak with a burning chest.
* **The Unmade asymmetry, big enough for 35 px.** The ribcage is burnt open over the whole left flank, but a torn
  flap of ash hide still hangs over the rear ribs on the right. The right ear is torn off halfway, and the mane
  leans right.
* **The bite telegraph uses the clinker's language.** The `head` bone is the skull and upper jaw, hinged at the
  jaw joint. Tipping it nose-up lifts the skull off the lower jaw, whose floor is a teal maw, and turns that maw
  toward the camera. The wind-up is the one moment a large teal shape shows: at game size it is a cyan flash at
  the head, just before the engine's red-white decal. At rest and in the gallop the mouth stays almost shut,
  showing only a thin teal seam.
* **Value plan at game size.** Most of the body is ash-grey top planes, a step lighter than the `#3A2C24`
  floor, and the up-facing planes are lifted further by a painted pass. The underside is burnt from the ground
  up: below a ragged line at about 0.35 m, the lower chest, elbows, stifles and legs char to black, with a dim
  smouldering rust band on the line (the hound runs through cinders). The keel, jaw, mane and ears are black
  char with light brush edges. The ember window and the tail cinder are the one warm accent, and the teal eye
  slits show the facing. Beside the clinker (a dark dome with a pale club and teal cracks), the ashrunner is a
  pale arrow with an orange chest: the two are distinct at a glance but clearly the same faction.
* **Palette (The Unmade, `gfa_spec.FACTIONS`).** Ash `#838079` / light `#B6B0A8` warmed 10 % toward the row
  colour / shadow `#3C3134`; char `#221C1D` with a `#6A5A54` edge; rib `#2A1D1A`, lit `#C0673C`. The ember glow is
  the Slag King's molten ramp (rim `#C8400C`, hot `#FF6B1A`) with a cooled `#FFB070` core instead of the white-hot
  `#FFF3D6`, so there is no white speckle. Teal is ichor (`#1F8F7E` / `#2FBFA8` / `#8FF2D8`). The fangs are
  faction bone a step down (`#B3A58F`). The row colour `#F2A541` sits near the player gold `#FFC940`, so it is
  used only as a faint tint in the ash light. There are no player colours and no red-white.
* **Paint.** This is the gf_assets NPR painter: flat value planes per facet and per part, cavity darks, broken
  brushy edge strokes, and wind-swept streaks along the body instead of grain. `extra_passes()` in the build
  wraps `gfa_paint.paint` for this one asset and adds three passes: the top-plane lift, the burn from below, and
  the ember strokes on the rib edges. The rib strokes are measured to each rib's own edge lines, so no glow runs
  across a rib at its joints. The shared module is unchanged. The cinder cracks are few and bold: one per
  shoulder and one on the rump, 13 mm wide. UV islands are importance-weighted: the hide gets 1.3×, and the
  mostly hidden ember core only 0.4×.
* **Size.** The body, from nose to rump, is about 1.1 m (3 × the 0.36 m collider). With the tail it is 1.44 m.
  The ears reach 0.82 m (0.37 × the hero) and the withers 0.6 m: below the waist line.

## Rig and clips (GF_Swarm_v1, rigid skin)

| Bone | Drives |
|---|---|
| `root` | the gallop bob, the lunge travel, the death drop |
| `body` | fore-chest, neck, ribcage, ember core, keel, lower jaw, lower fangs, mane, the torn right hide flap |
| `head` | the skull + upper jaw, eyes, ears and upper fangs, hinged at the jaw (nose-up opens the teal maw) |
| `legs_a` | both front legs (pivot: the shoulder joints) |
| `legs_b` | both hind legs (pivot: the hip joints) |
| `tail` | the loin, rump and tail (pivot: the loin). It **flexes the spine** |

The gallop is a double-suspension bound. The front pair and the hind pair swing in opposition, and the tail bone
tucks the rump under in the gathered phase and stretches it back in the extended phase. The hind legs hang from
the rump, so their location and pitch are solved from the tail bone every frame (`follow_tail()`), and the hips
stay on.

| Clip | Length | Notes |
|---|---|---|
| `idle@loop` | 1.6 s | a hunting stance: slow breaths, one snarl (the skull lifts off the teal jaw), a sniff dip, a slow rump and tail sway. Sampled every frame |
| `move@loop` | 0.33 s | one gallop stride (10 frames). t=0: the extended suspension; t=0.25: the front stance, nose dipping; t=0.5: the gathered suspension, spine arched; t=0.75: the hind stance. `move_cycle_m` is 1.4, so the row speed of 5.2 m/s gives about 3.7 strides per second |
| `windup` | 0.5 s | it crouches low with the front legs braced and the rump tucked, and the jaws gape: the teal maw faces the camera. It ends on the loaded pose, so the client can time-stretch it |
| `attack` | 0.5 s | the lunge bite: a 0.36 m leap with the jaws wide, the snap shut, two head-shakes, then back to rest (in place overall) |
| `hit` | 0.3 s | a flinch: it rolls away, the mouth pops open, then it settles |
| `death` | 0.9 s | a jolt, a forward stumble, and a roll onto its side, then it crumbles to ash: everything shrinks to 2 % and sinks, a held final pose. The ash burst is engine VFX at `fx_core` |

* **Sockets:** `hit_center` and `fx_core` (the ember core, for the death burst) on `body`; `fx_mouth` (the bite)
  on `head`; `head_top` on `body`.
* **Facing:** the hound faces glTF +Z on y = 0. The engine turns it with `yaw(angle) * rot_y(PI)`
  (ENEMIES.md section 2).

## Metrics

| Tris | Height | Length × width | Textures | Texel density (median) | GLB |
|---|---|---|---|---|---|
| 1,262 | 0.82 m (0.37 × hero) | 1.44 × 0.30 m | 512 + 512 | 192 px/m | 0.56 MB |

The swarm budget is 600-1,500 tris. There is one material (base colour + emissive), no Draco and no meshopt, and
`gfa_validate.py` prints OK. The game camera shows about 49 px/m, so the textures are oversampled about 4×.

## Review images (`reports/`)

* `ashrunner_review.png`: the turnaround, size against the 2.2 m hero, the in-game camera at true size (1x,
  then 3x facing the camera, running across and running away), the game-size silhouette, the key poses at true
  pixel size, the gallop at game size (across the screen and toward the camera), the clip key frames, and the
  textures.
* `ashrunner_crowd_review.png`: the ashrunner beside the clinker and the hero, then **40 ashrunners in 20 hunting
  pairs mixed with 20 clinkers** (all four looks) around two heroes at true 1080p size, with its silhouette and
  the four-player 28 m view, the same horde at 2x, and a hunting pair galloping across the screen frame by frame.
  Every copy is posed from the actions inside the shipped GLBs.
* `ashrunner_crowd.png` (the horde, 2x nearest), `ashrunner_lineup.png`, `ashrunner_34.png` (a close-up of
  the gallop and the wind-up), `ashrunner_build_report.json`.

## Rebuild

```text
set BL="C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
%BL% -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/enemies/ashrunner.py
%BL% -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/enemies/ashrunner_crowd.py
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/ashrunner.glb
```

`--preview` renders flat zone colours in about 10 s, for silhouette iterations. `--no-review` skips the sheets.

## Open items

* The user's visual approval.
* Engine work (in `crates/`, not done here): load the GLB, and map sim state to clips (`move@loop` at
  speed / `move_cycle_m`, `windup` time-stretched to a telegraph, `death` plus the ash burst at `fx_core`). The
  sim's `Swarmer` has no wind-up or lunge state yet, so `windup` and `attack` are ready for a contact-bite or
  lunge behaviour.
