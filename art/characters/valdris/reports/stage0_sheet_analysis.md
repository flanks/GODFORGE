# Valdris: sheet analysis (stage 0)

The user supplied two approved concepts that disagree in places. This note lists every difference
found, what each image shows, and the resolution the pack uses. The visual version, with numbered
markers matching the numbers below, is [`stage0_sheet_compare.png`](stage0_sheet_compare.png)
(made by `tools/comfy/concept_compare.py` from [`../concept_compare_spec.json`](../concept_compare_spec.json)).

| Image | File (verbatim copy) | sha256 | What it is |
|---|---|---|---|
| **Sheet** | [`references/VALDRIS_sheet_turnaround.jpg`](../references/VALDRIS_sheet_turnaround.jpg) (from `docs/media/playable_characters/VALDRIS THE ANVIL-BORN.jpg`) | `d27bf5f3…7c17` | 1168x784 turnaround labelled "neutral standing pose for 3D blockout": front (A-pose), side profile, back; a four-chip colour script plus "glowing seams white-hot"; a lighting note |
| **Hero** | [`references/VALDRIS_front_approved.jpg`](../references/VALDRIS_front_approved.jpg) (from `docs/media/playable_characters/VALDRIS.jpg`) | `55d018f3…2dfd` | 784x1168 hero front on black, arms out level |
| TRELLIS input (derived) | [`references/valdris_concept_front_mirrored.png`](../references/valdris_concept_front_mirrored.png) | `62fc6eed…146d` | the hero front mirrored left-right, lossless (PNG of the decoded JPEG pixels; mirroring it again gives back the original pixels exactly) |

## The decision

**Cannon on his RIGHT arm, anvil chest plate kept.** This is the orchestrator's default, recorded
on 2026-09-25; the user may override it. The sheet is the labelled blockout reference, and its
front and back put the weapon on the right arm. The hero front is the only image with the anvil
chest plate, which is his "Anvil-Born" identity. Mirroring the hero front satisfies both, so the
stage-1 TRELLIS.2 input is the mirrored hero front.

In every document of this pack, "his right" means the character's own right. On a front view that
is the **left** side of the image.

## Every inconsistency and its resolution

| # | Topic | Sheet | Hero front | Resolution |
|---|---|---|---|---|
| 1 | **Weapon arm** | Front and back: cannon on his RIGHT arm | Cannon on his LEFT arm | **RIGHT** (orchestrator default). TRELLIS input = hero front mirrored. The fist is his LEFT hand |
| 2 | **Chest** | A flat chest plate, integrated with the torso; its outline (wide top, waisted) only hints at an anvil. Glowing seams on the pecs | A big protruding anvil over the chest: flat top face level with the arms, a horn, a waisted body, two feet above the belt; cracked iron with glowing cracks | **Keep the anvil plate.** It is the centre mark of his silhouette and his name |
| 3 | **Head size and height** | About 8.3 heads tall; the crown stands about half a head (0.065 of his height) above the pauldron tops | About 11 heads tall; the crown is level with the pauldron tops, so the head sits sunk between them | **Hero front** (it is the TRELLIS input, and the flat top line reads as "siege engine"). **Flagged for the user**; the alternative is the sheet's larger head |
| 4 | **Pauldrons** | Layered plates with gold rims, rounder, below the crown | Huge boxy blocks with an upright back plate, a glowing slot along each side, rivets and small spikes; tops at crown height | **Hero shape**. Both span 0.52-0.53 of his height. The sheet shows how they look from the side and back |
| 5 | **Cannon build** | A segmented cylinder with gold rings and a glowing bore at the wrist end; no hand. In the side view it is about 40 % thicker than in the front view | A forearm cannon from the elbow: a breech housing with clamps on top and a bracket underneath, three gold bands, a small glowing side port, a flared muzzle ring, a glowing bore. No hand | **Hero design and thickness** (barrel ~0.31 m at 2.3 m). Both agree: the cannon replaces the forearm and hand. The weapon sheet (prompt ready) settles the top, underside, breech and mount |
| 6 | **Off hand** | Relaxed open hand, fingers curled | Closed fist | A pose difference only: the same plated gauntlet with two gold cuffs. Build a normal five-finger gauntlet; the fist is the default gameplay pose |
| 7 | **Front skirt** | A red cloth tabard hanging from a belt with a square gold buckle | An armoured, gold-trimmed centre plate (faulds) shaped like a blade, side tassets on the hips, red cloth behind, the belt hidden under the anvil | **Hero plate**. The red cloth behind it is the cape material (one cloth) |
| 8 | **Beard** | Brown-grey, long and wavy, braided side locks with metal rings, moustache | Iron-grey, five thick braids, each ending in a gold ring and a steel cap, resting on the anvil top | **Hero braids and caps, iron-grey** (measured `#48413C`) |
| 9 | **Eyes** | Red-orange glow | Amber glow | Ember glow (the seams' hot tone). About 8 px wide on either concept and invisible at game scale |
| 10 | **Cape back, collar, emblem** | The only back view: a high red collar behind the head, a gold emblem (a vertical blade with branching arms and a small crown-like top), tatters and holes, hem at mid-shin | Only the sides of the cape show, hem at mid-shin | **Sheet** for the back. The emblem is drawn small; an emblem detail sheet is optional (prompt ready) |
| 11 | **Boots** | A round gold disc on the outer ankle (front and side) | Blocky gold-trimmed sabatons, no disc | **Hero sabatons**; the disc is optional detail |
| 12 | **Pose** | A-pose, feet shoulder-width apart, labelled "neutral standing pose for 3D blockout" | Arms level (T-pose-like), a wider stance | TRELLIS uses the hero pose (the arms stay clear of the body and the cape). The rig binds in its own rest pose (stage 3) |
| 13 | **The side view is mirrored** | He faces image-left, so we see his LEFT side; the near arm carries the cannon. The side view therefore puts the cannon on his LEFT arm, against the sheet's own front and back | — | **Read the side view mirrored**: as his RIGHT profile it matches the resolution. The resolved reference set in `stage0_sheet_compare.png` shows it mirrored |
| 14 | **Side-specific details** | — | — | Mirroring flips the anvil horn to his LEFT and flips a few asymmetric details. See "What mirroring the hero front flips" below |
| 15 | **Colours** | — | — | The two images agree (dE 2-11 per material); the sheet's chips differ from their own labels. See "Colours" below |
| 16 | **Scalp scar** | A mark on the top of the scalp | Cracked scar lines across the forehead and scalp, faintly orange | Hero; a texture detail (it can glow with Reforged Flesh, see brief §7) |
| 17 | **Lighting** | The note says forge key light from below-left and a cool steel rim from above-right; the painting itself is lit mostly from the front and above | Lit from the front and above, warm | Art direction, not geometry: it goes to the shader and colour script (brief §6). TRELLIS bakes some lighting into its texture; stage 2 repaints from the palette |

## What mirroring the hero front flips (item 14)

Mirroring is lossless and changes no shape, only sides. The side-specific details it flips:

* **Weapon arm:** the cannon moves to his right arm, the fist to his left (the intent).
* **Anvil horn:** in the original the horn points to his right (the cannon side); in the mirrored
  input it points to **his left**, toward the fist. Recorded as "the horn points to his left". The
  horn on the fist side balances the heavy cannon side of the silhouette.
* **Cannon details:** the breech housing, the top clamps and the small glowing side port stay on
  the cannon's outer (lateral) side; nothing about the cannon's construction changes.
* **Asymmetric small details:** the scalp scar pattern, the cape's tatter pattern, the rivet
  layout on the pauldrons, and the painted light direction all flip. None is a design rule.
* **Nothing is lettered:** no text, numbers or runes on the hero front would read backwards.

## Colours: the two images agree (item 15)

`tools/comfy/palette_extract.py` measured the same materials on both images with the same filters
(`palette.json`, `cross_checks`). Base tones differ by: plate dE 2.4, cape 3.1, seams 3.5, skin 5.6,
beard 7.1 (the sheet's beard is browner, item 8), gold 10.6 (the sheet's gold is in more shadow).
The two images are one palette.

The sheet's colour-script chips do **not** match their own labels. The labels are the declared
values; the chips are what the image generator painted next to them:

| Label (declared) | Painted chip | dE | Nearest measured tone on the hero |
|---|---|---|---|
| Gunmetal Black `#2A242E` | `#1A1A1A` | 10 | plate shadow `#1E1A17` (dE 11) |
| Forge Gold `#FFC24B` | `#DAA537` | 12 | gold highlight `#CF9F66` (dE 32) |
| Ember Amber `#FF6B1A` | `#B1311B` | 33 | seams rim `#BB6A26` (dE 33) |
| Deep War Red `#7A1F1F` | `#6C0E08` | 8 | cape highlight `#5D2B28` (dE 20) |
| Glowing seams white-hot (no hex) | `#FFF5CE` | — | seams core `#F8AA5D` (dE 44) |

**Rule used by the pack:** the declared hexes are the authority for the NPR base colours (they are
the user's colour script); the measured tones record how the painting shades them. Where they
differ, the paintings are darker and more shaded than the labels, so the textures should be
painted from the labels and lit by the shader. Details in `brief.md` §4.

## Proportions: where the two images differ

Measured on the hero front (mirrored, 819 px crown to sole) and on the sheet front (about 463 px).

| | Hero front | Sheet front |
|---|---|---|
| Heads tall (2 x crown-to-eyes) | ~11 | ~8.3 |
| Crown vs pauldron tops | level | ~0.065 H above |
| Pauldron span / height | 0.53 | 0.52 |
| Outer stance / height | 0.52 | 0.50 |
| Crotch height / height | 0.35 | ~0.36 |
| Cannon barrel / height | 0.14 | ~0.16 (front), ~0.22 (side) |

Everything but the head matches within a few percent. The head is the one real proportion
conflict (item 3).

## What stage 1 and stage 2 build from

1. **Front:** `references/valdris_concept_front_mirrored.png` (the TRELLIS input). Authority for the
   silhouette, the anvil plate, the pauldrons, the cannon design, the fist, the faulds and the
   beard.
2. **Side:** the sheet's side view **mirrored** (his right profile). Authority for the body depth,
   the hunch of the head, the cape's fall and the boot length.
3. **Back:** the sheet's back view as is. Authority for the cape, the collar, the emblem and the
   backs of the pauldrons and cannon.
4. **Where the front and the sheet disagree** on a detail visible in the front, the front wins.
