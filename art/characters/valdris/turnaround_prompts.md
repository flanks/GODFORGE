# Valdris: prompts for the missing stage-0 sheets

Stage 0 has the user's two approved concepts: the turnaround sheet
([`references/VALDRIS_sheet_turnaround.jpg`](references/VALDRIS_sheet_turnaround.jpg): front, side,
back, colour script) and the hero front ([`references/VALDRIS_front_approved.jpg`](references/VALDRIS_front_approved.jpg)).
These prompts produce the sheets that are still missing: **3/4 view, expression sheet, siege-cannon
weapon sheet, Mountainfall anvil-avatar concept and the back-of-cape emblem detail.** None of them
blocks stage 1 or stage 2 (status.json marks them optional); the weapon sheet is the most useful
before the stage-2 cannon.

**How to use.** Paste one block into ChatGPT (image generation) and attach **two images**:
1. [`references/valdris_concept_front_mirrored.png`](references/valdris_concept_front_mirrored.png):
   the resolved front (cannon on his RIGHT arm, anvil chest plate). This is the design authority.
2. [`references/VALDRIS_sheet_turnaround.jpg`](references/VALDRIS_sheet_turnaround.jpg): for the
   side, back, cape and emblem.

Every block names both attachments and says which one wins.

A person approves every sheet. These prompts are tools for that decision, not the decision itself.
Until a sheet is approved its item stays `pending_human` in [`status.json`](status.json).

**Rules these prompts follow (docs/ART_PIPELINE.md):** the only style references are our own
approved concepts. Prompts never name another game, studio or artist. There is no style LoRA.

## Before generating: what the prompts assume

The two concepts disagree in places ([`reports/stage0_sheet_analysis.md`](reports/stage0_sheet_analysis.md)).
The prompts use the resolution below. If the user overrides one, edit the matching sentence first.

| Question | Used in the prompts |
|---|---|
| Weapon arm | The cannon is on his **RIGHT** arm (on the LEFT side of the image in a front view). His LEFT hand is a plated fist |
| Chest | The big anvil-shaped chest plate is kept; its horn points to **his left** |
| Head | Small and sunk between the pauldrons, the crown level with the pauldron tops (the hero front; brief §7.2 Q1) |
| The sheet's side view | Drawn mirrored (it shows the cannon on his left arm). The prompts say to ignore its arm side |
| Background | Flat solid mid-dark grey `#45474D`: dark enough for the mood, light enough that the dark armour keeps a clean silhouette (the approved images use near-black gradients, which hide the plate edges) |

## Accepting a sheet (the stage-0 gate)

Generate several and pick the closest. **Reject** a sheet if any of these is true:
- **the cannon is on his LEFT arm** (image generators flip this often: check it first);
- the anvil chest plate is missing, flattened into the chest, or its horn points to his right;
- the head sticks up above the pauldron tops, or the pauldrons became small layered plates;
- the cannon lost its breech housing with top clamps, its gold bands or its flared glowing muzzle,
  or a hand appeared at its end;
- the red cape changed colour, lost its tattered hem, or the cape emblem changed shape;
- the beard is not iron-grey with five braids ending in gold rings and steel caps;
- extra accessories, weapons, text, runes, labels, a floor, a cast shadow, a gradient or a vignette
  appeared;
- the view has perspective where the prompt asks for orthographic (near and far parts differ in size).

For the 3/4 view, overlay it on the resolved front at the same scale: the crown, pauldron tops, arm
line, anvil top, knees and soles should line up to within a few pixels.

To record an approval, run one command:

```text
python tools/comfy/approve_sheet.py valdris <three_quarter|expression|weapon_cannon|mountainfall_avatar|cape_emblem> <sheet.png> --by "<who approved>"
```

It copies the sheet to `references/VALDRIS_<item>_approved.png`, sets the item in `status.json` to
`done` with `approved_by` and `approved_on`, and adds the file's sha256 under `references` in
`manifest.json`. It never approves anything by itself. Rejected candidates stay local in `work/`.

---

## 1. Front three-quarter view

```text
Attached are two approved reference images of Valdris, the Anvil-Born, a juggernaut hero for a stylized isometric action game. IMAGE 1 (the full-body front view on black) is the design authority. IMAGE 2 (the turnaround sheet) shows his side and back; its side view is drawn mirrored, so ignore which arm holds the cannon there. Draw the SAME character with the SAME design, proportions, colours and rendering style as IMAGE 1. Do not redesign, add or remove anything.

CHARACTER (must match IMAGE 1): a massive, wide, top-heavy armoured giant, a walking siege engine. Thick faceted gunmetal-black plate armour with a cracked surface, every plate edged with a thin forge-gold rim, and thin glowing ember-orange seams in the gaps between plates. Huge boxy pauldrons with an upright back plate and a glowing slot along each side; their tops are level with the top of his head, so the small bald head sits sunk between them. A big anvil-shaped chest plate standing out from the chest: a flat top face level with the arms, a pointed horn on his LEFT side, a narrow waist and two feet, cracked iron with glowing cracks. Below it, a blade-shaped armoured centre plate with gold trim and armoured hip plates, with deep red cloth behind. Bald, scarred head with glowing amber eyes; an iron-grey beard of five thick braids, each ending in a gold ring and a steel cap, resting on the anvil. His RIGHT forearm is a huge siege cannon (no hand): a breech housing with clamps on top and a bracket underneath, three gold bands, a flared muzzle ring and a glowing orange bore. His LEFT hand is a plated gauntlet clenched into a fist, with two gold cuffs. Blocky armoured legs with glowing seams at the knees, heavy square sabatons. A long tattered deep-red cape hangs behind him from the shoulders to mid-shin.

PROPORTIONS: about 11 heads tall; shoulders (pauldron to pauldron) about half his height; short heavy legs, feet planted wide; the cannon about 1.6 times as thick as his fist arm.

COLOURS (keep exactly): armour plate #2A242E (lit faces up to #6F6862); gold trim #FFC24B (in shadow #7C5931); glowing seams #FF6B1A with white-hot cores #FFF5CE; cannon bore #E8741C to #FFF097; cape #7A1F1F; skin #7C5A4A; beard #48413C.

FORMAT: portrait 1024x1536. One full-body figure, head to toe fully visible, about 90% of the image height. Strictly orthographic: no perspective, no camera tilt, eye level at the figure's centre. Flat solid mid-dark grey background #45474D: no gradient, no floor, no cast shadow, no vignette, no particles. Soft even lighting with a warm glow from the seams and a cool rim light from the upper right. The same rendering style as IMAGE 1. No text, labels, watermark or border. No other characters or props.

VIEW: front three-quarter view, the whole body rotated 45 degrees from IMAGE 1. He faces halfway between the viewer and the RIGHT edge of the image, so his RIGHT side (the cannon side) turns toward us. Same pose as IMAGE 1: both arms raised level to the sides; the cannon arm points diagonally toward the viewer and the left of the image, the fist arm diagonally away to the right. Show the side of the anvil plate, the depth of the pauldrons, the cannon's breech housing and top clamps, and the cape falling behind him.
```

## 2. Expression sheet

```text
Attached are two approved reference images of Valdris, the Anvil-Born, a juggernaut hero for a stylized isometric action game. IMAGE 1 (the full-body front view) is the design authority for his face and head. Draw an EXPRESSION SHEET of the SAME character's head and shoulders, with the same face, the same rendering style and the same colours. Do not redesign him.

HEAD (must match IMAGE 1): a small bald head, weathered skin #7C5A4A with cracked scar lines across the forehead and scalp that glow faintly ember-orange; a heavy brow; glowing amber eyes; a broad nose; an iron-grey beard (#48413C) of five thick braids, each ending in a gold ring and a steel cap, with a heavy moustache flowing into it. The head sits sunk between the two huge boxy gunmetal pauldrons (#2A242E with forge-gold rims #FFC24B and glowing side slots #FF6B1A), whose tops are level with the top of his head; the flat top edge of the anvil chest plate is visible at the bottom of each frame, with the beard resting on it.

LAYOUT: landscape 1536x1024, six heads in a 3x2 grid, evenly spaced, each the same size, each framed from just above the pauldron tops to the top of the anvil plate, all facing the viewer head-on, orthographic, soft even lighting with the seams' warm glow from below. Flat solid mid-dark grey background #45474D. No text, labels, numbers, borders or panel frames.

EXPRESSIONS, left to right, top row then bottom row:
1. Neutral and stern, exactly as in IMAGE 1.
2. Battle roar: mouth wide open inside the beard, brows crushed down, the neck straining.
3. Grim half-smile: one corner of the mouth up under the moustache, eyes narrowed, amused and unafraid.
4. Taking a hit: eyes squeezed, teeth clenched, the scalp scars glowing brighter where the damage turns into armour.
5. Siege Stance: a locked, focused glare along his aim, the eyes glowing brighter, the seams on the pauldrons bright.
6. Mountainfall fury: a bellow, eyes white-hot, every scar and seam at full glow, the face lit from below by the glow.
```

## 3. Siege-cannon weapon sheet

```text
Attached are two approved reference images of Valdris, the Anvil-Born, a juggernaut hero for a stylized isometric action game. IMAGE 1 (the full-body front view) is the design authority: the huge siege cannon on his RIGHT arm (on the left of that image). IMAGE 2 (the turnaround sheet) shows the cannon from the side and back. Draw a WEAPON SHEET of this cannon on its own, exactly as designed in IMAGE 1. Do not redesign it.

CANNON (must match IMAGE 1): a forearm cannon that replaces his right forearm and hand: there is NO hand; his forearm sits inside it. Gunmetal-black steel (#2A242E, lit faces #928579) with a cracked, faceted surface. From the elbow end to the muzzle: a boxy breech housing over the elbow with heavy clamps on top and a bracket underneath; three wide forge-gold bands (#FFC24B, in shadow #7C5931) around the barrel; a small glowing ember port on the outer side; riveted steel segments between the bands; a flared, stepped muzzle ring; a deep bore that glows orange (#E8741C) to a white-hot core (#FFF097). Thin glowing seams (#FF6B1A) in a few gaps between the steel segments.

MOUNT (not visible in the references; design it in the same style and keep it simple): the breech housing closes around his elbow like a heavy collar and is held by a gold-banded brace that disappears under the pauldron. Keep the silhouette of IMAGE 1: a thick cylinder with a boxy breech, not a thin rifle.

LAYOUT: landscape 1536x1024, one clean grid of orthographic views of the same cannon, all at the same scale, evenly spaced, on a flat solid mid-dark grey background #45474D, soft even lighting, the same rendering style as IMAGE 1. No text, labels, arrows or borders. No hand, no arm, no character.

VIEWS:
1. Outer side view, muzzle pointing right (the breech housing, the side port, the gold bands, the top clamps and the under-bracket all visible).
2. Top view, muzzle pointing right: this is the view the game camera sees most, so the clamps and bands must read clearly from above.
3. Underside view, muzzle pointing right (the bracket).
4. End-on view of the muzzle: the flared stepped ring and the glowing bore.
5. End-on view of the breech: the elbow opening where the forearm enters, and the collar.
6. A three-quarter view from the front and above.
7. A close-up of one gold band with the steel segments, rivets and a glowing seam beside it.
8. The same side view as 1 at the moment of firing: a SHORT, compact muzzle flash and a dark heavy shell leaving the bore with an ember trail (no huge explosion).
```

## 4. Mountainfall anvil-avatar concept (with the kit's glow states)

```text
Attached are two approved reference images of Valdris, the Anvil-Born, a juggernaut hero for a stylized isometric action game. IMAGE 1 (the full-body front view) is the design authority for his normal form; IMAGE 2 shows his side and back. Draw a CONCEPT SHEET for his ultimate ability, MOUNTAINFALL: for 8 seconds he becomes a colossal anvil-avatar, 1.8 times his normal size; every cannon shot is an exploding boulder, and his footsteps become chained ground pounds.

TOP ROW (most of the image): on the left, Valdris in his normal form exactly as in IMAGE 1, standing, for scale. On the right, the SAME character in his Mountainfall form, drawn exactly 1.8 times taller, in the same front pose. The Mountainfall form keeps his design and silhouette (the flat top line of the huge pauldrons with the small sunk head, the anvil chest plate with its horn on his LEFT, the siege cannon on his RIGHT arm, the fist on his left, the tattered red cape) and turns up everything that says ANVIL and FORGE: the gunmetal plates (#2A242E) darken to a black cooled-iron crust; the glowing seams (#FF6B1A) widen into white-hot (#FFF5CE) molten cracks; heavy iron-and-stone crust grows over the pauldrons into anvil-like blocks; the anvil chest plate glows along its edges; the cannon's bore holds a glowing boulder instead of a shell; molten drips fall from the cannon; the ground cracks under his feet with a ring of shattered stone from a ground pound. The gold trim (#FFC24B) stays. The cape (#7A1F1F) flares with the heat. He must still read as ONE heavy dark block with glowing lines, not as a fire elemental.

BOTTOM ROW (a strip of five small copies of his NORMAL form, same front pose, same size, evenly spaced): 1. Reforged Flesh armour empty: the seams dim ember, never fully dark. 2. Reforged Flesh armour full: the seams bright gold-white. 3. Armour breaking: a flash, plate shards and a shockwave ring on the ground. 4. Siege Stance: braced wide with knees bent, the fist bracing under the cannon, two anchor spikes folded down from each boot into the ground, heat venting from the pauldron slots, a gold-rimmed forge glyph on the ground under him. 5. Firing: a short compact muzzle flash and a dark shell with an ember trail.

FORMAT: landscape 1536x1024. Orthographic views, no camera tilt. Flat solid mid-dark grey background #45474D: no gradient, no floor except the cracked ground patches under the figures, no vignette. The same rendering style as IMAGE 1. No text, labels, numbers or borders. No other characters.
```

## 5. Back-of-cape emblem detail

```text
Attached are two approved reference images of Valdris, the Anvil-Born, a juggernaut hero for a stylized isometric action game. IMAGE 2 (the turnaround sheet) is the design authority for this sheet: its BACK VIEW shows his deep-red cape with a gold emblem. Draw a DETAIL SHEET of that cape and emblem. Do not redesign the emblem.

EMBLEM (must match the back view of IMAGE 2): painted in worn forge gold (#FFC24B, shadowed #A57741) on the deep war-red cloth (#7A1F1F). A long vertical blade pointing DOWN toward the hem, tapering to a point; near its top a small cross-bar with a small diamond above it; across the upper middle two pairs of up-swept branching arms that open like a V (like antlers or a hammer's claw); smaller hooked side-strokes lower down on the blade. Symmetric left to right. The paint is distressed, chipped and follows the folds.

LAYOUT: landscape 1536x1024, three panels side by side on a flat solid mid-dark grey background #45474D, orthographic, soft even lighting, the same rendering style as the references:
1. LEFT: a small back view of Valdris (as in IMAGE 2's back view, the cannon on his RIGHT arm, which is on the RIGHT of the image from behind) showing where the emblem sits: centred between the shoulder blades, from just below the collar to about the waist.
2. MIDDLE (largest): the back of the cape laid out flat and seen straight on, from the draped red collar at the top to the tattered hem, with the emblem large and sharp; the holes and tatters only in the lower third, near the hem.
3. RIGHT: the emblem alone as a clean flat gold shape on flat deep red #7A1F1F, no folds, no wear, sharp edges, as a guide for texture painting.

No text, labels, numbers, runes or borders.
```

---

## Later: the same sheets from ComfyUI

The pipeline also allows ComfyUI style-locked workflows for stage 0 (IP-Adapter or a style LoRA).
Neither is set up. An IP-Adapter conditioned on **our own** approved concepts would be allowed; a
style LoRA needs a style bible of approved sheets first and may never be trained on competitor art.
Until then, ChatGPT with the approved concepts attached is the stage-0 generator.
