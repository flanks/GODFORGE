# Selene, stage 4: the clips

Made by AI (Claude) on 2026-09-27 with `python tools/blender/gf_hero/s4_selene_run.py` (about two minutes; Cycles on the
CPU). No animator, no Mixamo / ActorCore seeds. The review record is one board: [`anim/anim_board.png`](anim/anim_board.png)
(four key frames of every clip). The user's visual approval is still pending (`status.json`).

## 1. What was made

**31 clips**, 30 fps, in place, 991 frames: the **24 shared** GF_Hero_v1 clips re-posed for her (`s4_selene.shared_clips`:
the contract's names, loops, layers, events and timing structure of `s4_clips.py`) and **7 kit clips**
(`s4_selene.unique_clips`, brief section 7.1). Actions are `selene_<clip>` / `selene_<clip>@loop`, one muted NLA track
each in `production/selene_anim.blend`.

Her vocabulary (`s4_selene.SV`), in metres and degrees:
* **the hold** - the launcher at her right hip on the aim, the body bladed (hips and chest turned 40° right, the left
  foot leading), the right forearm along the barrel (the wrist never bends: the barrel is the forearm, pitched back up by
  the torso's lean). **The left palm is put on the launcher's `grip_L` frame by frame** (`SClip.poses` -> `apply_hold`:
  solve, read the posed `weapon_R`, place the palm, re-solve), blended by the pose's `hold` weight, so recoil, bobs and
  turns carry both hands and a clip can let go;
* **the carry** - the launcher low in the right hand, the left hand free with open claws (idle, walk, interact);
* arms as (elevation, azimuth) directions interpolated by direction (Valdris's VClip rule), locomotion from
  `s4_clips.locomotion` with her chest held on the aim against the pelvis swing.

| Clip | Frames | Notes |
|---|---|---|
| idle@loop | 90 | relaxed carry, breathing, weight drifting |
| idle_combat@loop | 32 | the hold with a light bounce; frame 0 = the upper-layer reference |
| walk@loop | 28 | light upright walk, carry, the left arm swinging (1.72 m/s design) |
| run@loop | 18 | long light run at 7.0 m/s, the hold on the aim, forward lean |
| strafe_left / strafe_right@loop | 16 | hips toward the travel, chest and launcher on the aim |
| backpedal@loop | 16 | on the balls of her feet, the hold |
| dash / dash_recover | 8 / 14 | a low lunge-glide (the left hand lets go for the lunge), landing into the hold |
| fire_light / fire_heavy (upper) | 8 / 16 | the orb shot: snap, kick up and back; the charged shot: brace, release, buck |
| fire_charge@loop (upper) | 24 | braced low, trembling |
| hit_light (upper) / hit_heavy | 12 / 26 | flinch; stagger with the left hand torn off the foregrip |
| knockdown / get_up | 30 / 36 | Brax's falls and rise, the left hand pushing up, the launcher kept |
| death / downed@loop / revive | 48 / 60 / 40 | the launcher sags, topple; the wraith drift with the launcher trailing; the jolt back into the hold |
| reforge_in | 45 | from a one-knee landing (left claws on the ground), the launcher snapped up |
| victory | 60 | the launcher thrust to the sky, the left hand open |
| ping (upper) | 20 | the left hand leaves the foregrip and points along the aim |
| interact / forge_hammer@loop | 40 / 36 | the left claws pressed on the anvil; the left palm slammed down (the right keeps the launcher) |
| **idle_signature@loop** | 90 | a hover a hand's breadth up, sway, the left claws flexing |
| **arc_nova** (upper) | 18 | gather (left claws at the chest), both hands snap forward and apart ('cast' 6) |
| **blink_out / blink_in** | 10 / 14 | crouch and lean in ('vanish' 8); arrive, land soft ('land' 3), settle into the hold |
| **heavens_verdict_start / heavens_verdict@loop** | 36 / 60 | gather, sweep the arms up, lift off ('call' 22); hover arms raised, the crown raised and swaying |
| **static_charge** (upper) | 24 | the left fist clenched and trembling in front of the chest ('crackle' 12) |

## 2. The cloth and crown pass (`s4_selene_cloth.py`, `selene_cloth.py`)

Her eight cloth chains and six crown shards are keyed in every clip (her secondary-motion layer; the shared set never
keys an `x_` bone). Per clip: each chain bone's hang (its rest direction turned with the body's heading, blended with
riding its parent) under gravity, drag against the clip's design travel and the pin's motion (the run streams the capes
back), a capped share of the pin's acceleration, a first-order lag (cyclic for loops); the sheet's sample points pushed
out of capsules round her legs, arms, hips and torso and above the ground; then the cleared directions smoothed over
time (cyclic) and posed again. Upper-layer one-shots start from and settle into idle_combat's frame-0 cloth state. The
crown shards bob out of phase (zero at every loop seam); in Heaven's Verdict they lift and sway round the head.

## 3. Numbers (`anim/clips.json`, `anim/cloth.json`, `anim/render_checks.json`, `anim/gltf_check.json`)

| | |
|---|---|
| planted-foot slide (world) | max 7.5 mm (strafes, backpedal); gate 10 |
| IK miss | max 39 mm (strafe_left, the lead leg at full stride); gate 60 |
| elbow / knee flexion | max 133° / 150° (get_up's knee at the solver cap); gates 147 / 152 |
| wrist bend | 0.0° (the barrel stays the forearm) |
| arm keep-out residual | max 31 body vertices (get_up); gate 60 |
| ground | feet at most 6 mm under (death) ; gate 15 |
| loops | 12, every seam closed |
| left palm on grip_L | every frame of idle_combat, run, strafes, backpedal, fire_light / heavy / charge; by design off the grip in carry, kit and fall poses |
| solver vs Blender | 7.8e-07 |
| glTF clip check | 31 animations, 0 failures |

## 4. Known limits (no review rounds, by the user's rule)

* The cloth is posed, not simulated. In the floor clips (knockdown, get_up, death) the chains turn up to 57° in one
  frame as the body rolls over, and a few bones still graze the legs (cloth.json counts them per clip).
* The dash and blink lunges let the left hand off the foregrip (the lean puts `grip_L` out of her reach); the heavy
  stagger does so on purpose.
* The launcher itself is not an obstacle for the arm keep-out (it is a carried weapon, see rig_report.md section 3): its
  stock may graze the right hip plate in the hold.
* The hover (idle_signature, Heaven's Verdict) is a clip-side lift of 5-9 cm with the toes pointed; the brief's
  stand-vs-hover question (Q2) is still the user's.
* Not run, by the user's rule: `check_clips.py` (the numbers above are inside its gates).
