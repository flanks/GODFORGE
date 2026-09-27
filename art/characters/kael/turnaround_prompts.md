# Kael: prompts for the missing stage-0 sheets (optional)

Stage 0 has one approved sheet, the front view
([`references/KAEL_front_approved.png`](references/KAEL_front_approved.png)). These prompts produce the rest:
**side, 3/4, back, expression and colour script**. None of them blocks stage 1 or 2 (the pipeline has run Brax and
Valdris from a front plus the stage-1 blockout), so every item is `optional: true` and stays `pending_human` in
[`status.json`](status.json) until the user approves a sheet. There is **no weapon sheet**: his signature weapon,
`serpent_smg`, is already built as its own model (`assets/models/weapons/serpent_smg.glb`).

Each block below is complete on its own: paste one block into ChatGPT (image generation) **with
`KAEL_front_approved.png` attached**. The user approves every sheet; these prompts are tools for that decision, not
the decision itself.

**Rules these prompts follow (docs/ART_PIPELINE.md):** the only style reference is our own approved concept.
Prompts never name another game, studio or artist. There is no style LoRA; if one is ever trained, it is trained
only on our approved sheets.

## Before generating: proposals the user should confirm or change

The front concept does not show these. The prompts use the proposals from [`brief.md`](brief.md) section 7. If the
user wants something else, edit the matching sentence in the prompt first.

| Question | Proposal used in the prompts |
|---|---|
| Hands | **Empty.** The two revolvers of the concept are weapons (separate models). Every sheet draws him without guns, the hands relaxed and slightly curled, or as loose fists in the T-pose |
| Ghost arm side | His **left** arm (image right in the front view) is the spectral one, and the glowing eye is his left eye, exactly as the approved front draws them |
| The back | One dark violet panel with a centre vent from the waist, the hem torn into long points, two ghost-flame tatters at the back; the collar stands up at the back of the neck; the belts continue round; no emblem |
| Ghost flame | 4 to 6 chunky, glowing mint-green flame-shaped cloth tatters on the coat hem (2 at each front corner, 1-2 at the back); no loose smoke |
| Bullet Ballet | The ghost arm and the tatters flare to their brightest; a translucent ghost copy of his gun in the left hand; ghost afterimages on each dash |

## Accepting a sheet (the stage-0 gate)

Generate several and pick the closest. **Reject** a sheet if any of these is true:
- a gun, knife or any other weapon is in his hands or on his body (the holster on his right thigh stays, empty);
- the coat changed (length to mid-shin, high collar with two points, wide lapels, rolled cuffs, torn hem) or its
  violet turned blue, black or red;
- the ghost arm moved to the other side, lost its glow, or became a skeleton or a claw instead of a ghostly human arm;
- the bandolier, the two belts with the green gem buckle, the right-thigh holster, the thigh straps or the buckled
  boots changed or disappeared, or extra accessories appeared;
- the proportions drifted: about 7.9 heads tall, lean, narrow waist, long legs;
- the green turned grass-green or yellow-green (it must stay a soft teal-mint, close to #80B290 in the painted
  areas and #B1DEBA at its brightest);
- the view has perspective (near and far feet differ in size);
- the background is not flat `#141E27`, or there is text, a floor, a cast shadow, a vignette or loose smoke.

For turnarounds, overlay the sheet on the front view at the same scale: the crown, chin, belt, coat hem, knees and
soles should line up to within a few pixels.

To record an approval, run one command:

```text
python tools/comfy/approve_sheet.py kael <side|three_quarter|back|expression|color_script> <sheet.png> --by "<who approved>"
```

It copies the sheet to `references/KAEL_<sheet>_approved.png`, sets the sheet's item in `status.json` to `done` with
`approved_by` and `approved_on`, and adds the file's sha256 under `references` in `manifest.json`. It never approves
anything by itself. Rejected candidates stay local in `work/` (gitignored).

---

## 1. Side view (left profile)

```text
Use the attached image as the exact design reference. It is the approved front view of Kael, a ghost gunslinger for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style, but WITHOUT the two revolvers: his hands are empty. Do not redesign, add or remove anything else.

CHARACTER (must match the reference): a lean man in a long tattered dark-violet duster coat reaching mid-shin, with a high stand-up collar ending in two points, wide lapels with worn bronze edges, rolled cuffs, and a hem torn into long ragged points; four to six of the hem points turn into chunky glowing mint-green ghost-flame tatters (solid flame-shaped cloth points, not smoke). Under the coat: a black shirt and black scarf, a bandolier of brass-capped cartridges across the chest from his right shoulder to his left hip, two brown leather belts (the upper one with a round bronze buckle holding a glowing green gem, the lower one slung), a torn maroon loin cloth hanging from the belt between the legs, dark trousers with brown leather thigh straps, a long empty brown leather holster on his right thigh, a small pouch on his left hip, tall dark-brown boots with overlapping buckled strap plates. His right forearm has a brown leather bracer and a black fingerless glove. His LEFT arm below the rolled sleeve is a translucent, glowing mint-green ghostly human arm with visible veins, a brown strap around the upper arm. Dark hair swept up and back with a light grey streak on his left side, stubble and a short chin beard, a scar over his right brow, his LEFT eye glowing mint-green with green glow creeping over the left temple and cheek.

PROPORTIONS: about 7.9 heads tall, lean and tall, narrow waist, long legs.

COLOURS (keep exactly): coat #241B24 with lit faces #332930 and shadows #131118; loin cloth #36242F; shirt, scarf and trousers #242328; leather #402A25 with worn edges #5D4235; boots #43322F; bronze buckles and cartridge caps #886F59 with highlights #BA9979; skin #937160 with shadows #59413B; hair #211D1D; ghost green (arm, eye, gem, flame tatters) #80B290 with bright cores #B1DEBA and edges #517B65.

FORMAT: landscape 1536x1024. One full-body figure, head to toe fully visible, the same size and vertical placement as in the reference (crown and soles at the same heights as the reference). Strictly orthographic: no perspective, no camera tilt. Flat solid dark navy background #141E27: no gradient, no floor, no cast shadow, no vignette, no smoke or particles. The same soft, even lighting and the same rendering style as the reference: clean painted illustration with crisp dark linework and cel-style shading. No text, labels, watermark or border. No other characters, no weapons, no props.

VIEW: exact LEFT side profile, rotated 90 degrees from the reference. He faces the LEFT edge of the image and we see his LEFT side, so the glowing ghost arm and the glowing eye are nearest to us. Keep the T-pose: his near (left, ghostly) arm points straight at the viewer, seen end-on as an empty loose fist; his far (right) arm points straight away, hidden behind his body. His legs are apart along the viewing direction, so they overlap in profile. Show the depth of the chest, the coat's collar from the side, the coat hanging behind the legs with its torn hem, the ghost-flame tatters, the pouch on his left hip, the back of the boots.
```

## 2. Front three-quarter view

```text
Use the attached image as the exact design reference. It is the approved front view of Kael, a ghost gunslinger for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style, but WITHOUT the two revolvers: his hands are empty loose fists. Do not redesign, add or remove anything else.

CHARACTER, PROPORTIONS and COLOURS: exactly as in the reference, and as described here: a long tattered dark-violet duster coat (#241B24, lit #332930) to mid-shin with a high two-pointed collar, wide bronze-edged lapels, rolled cuffs and a hem torn into long points, four to six of them chunky glowing mint-green ghost-flame tatters (#80B290, cores #B1DEBA); black shirt, scarf and trousers (#242328); a bandolier of brass-capped cartridges from his right shoulder to his left hip; two brown leather belts (#402A25), the upper one with a bronze buckle (#886F59) holding a glowing green gem; a torn maroon loin cloth (#36242F); an empty long holster on his right thigh; a pouch on his left hip; tall buckled dark-brown boots (#43322F); a leather bracer and black fingerless glove on his right forearm; his LEFT arm below the sleeve a translucent glowing mint-green ghostly human arm; dark swept hair (#211D1D) with a grey streak on his left side, stubble, a short chin beard, a scar over his right brow, his LEFT eye glowing mint-green. About 7.9 heads tall, lean.

FORMAT: landscape 1536x1024, one full-body figure, head to toe, the same size and vertical placement as the reference. Strictly orthographic. Flat solid dark navy background #141E27, no floor, shadow, vignette, smoke or particles. Same lighting and rendering style as the reference. No text, weapons, props or other characters.

VIEW: front three-quarter, turned 45 degrees to HIS LEFT, so we see his front and his left side (the ghost arm side). Keep the T-pose with the arms straight out to the sides (the near ghost arm foreshortened toward the viewer, the far arm foreshortened away). Show how the coat's collar, lapels and side panel wrap round, the bandolier crossing the chest, the pouch on the left hip and the tatters at the left front corner of the hem.
```

## 3. Back view

```text
Use the attached image as the exact design reference. It is the approved front view of Kael, a ghost gunslinger for a stylized isometric action game. Draw the SAME character from DIRECTLY BEHIND, with the SAME design, proportions, colours and rendering style, but WITHOUT the two revolvers: his hands are empty loose fists. Do not redesign.

CHARACTER, PROPORTIONS and COLOURS: exactly as in the reference: the long tattered dark-violet duster (#241B24, lit #332930) to mid-shin; black trousers (#242328); brown leather belts (#402A25); tall buckled dark-brown boots (#43322F); the leather bracer and black fingerless glove on his right forearm; his LEFT arm below the sleeve a translucent glowing mint-green ghostly human arm (#80B290, cores #B1DEBA); dark swept hair (#211D1D) with a grey streak on his left side. About 7.9 heads tall, lean.

THE BACK (new, keep it simple): the high collar stands up behind the neck. The coat's back is one dark violet panel from the shoulders down, with a centre vent opening from the waist, and the hem torn into long ragged points; two of the back hem points are chunky glowing mint-green ghost-flame tatters (solid flame-shaped cloth, not smoke). The belts continue round the waist under the coat. No emblem, no text, no extra straps. The bandolier's strap crosses the back from his left hip to his right shoulder under the coat.

FORMAT: landscape 1536x1024, one full-body figure, head to toe, the same size and vertical placement as the reference. Strictly orthographic. Flat solid dark navy background #141E27, no floor, shadow, vignette, smoke or particles. Same lighting and rendering style as the reference. No text, weapons, props or other characters.

VIEW: exact back view, rotated 180 degrees from the reference, the same T-pose. Because we see his back, his ghostly LEFT arm is now on the image's LEFT side, and his gloved right arm on the image's right.
```

## 4. Expression sheet

```text
Use the attached image as the exact design reference: the approved front view of Kael, a ghost gunslinger for a stylized isometric action game. Draw an EXPRESSION SHEET of the SAME character's head and shoulders, with the same face, the same rendering style and the same colours. Do not redesign him.

FACE (must match the reference): a lean face with sharp cheekbones, tanned skin (#937160, shadows #59413B), dark hair (#211D1D) swept up and back with a light grey streak on his left side, stubble and a short chin beard, a thin scar over his right brow; his LEFT eye glowing mint-green (#80B290 with a #B1DEBA core) with a soft green glow creeping over his left temple and cheek; the high two-pointed collar of the dark-violet duster (#241B24) and a black scarf at the bottom of each frame.

LAYOUT: landscape 1536x1024, six heads in a 3x2 grid, evenly spaced, each the same size, each framed from the top of the hair to the upper chest, all facing the viewer head-on as in the reference, orthographic, the same soft even lighting. Flat solid dark navy background #141E27. No text, labels, numbers, borders or panel frames. No weapons or hands.

EXPRESSIONS, left to right, top row then bottom row:
1. Neutral, a faint knowing smirk, exactly as in the reference.
2. Focused aim: one eye narrowed, jaw set, the glowing eye brighter.
3. Cocky grin: one corner of the mouth up, one brow raised.
4. Taking a hit: teeth clenched, eyes squeezed, head flinching to one side.
5. Ghost Step: a calm, cold look, the green glow spreading further over the left side of the face.
6. Bullet Ballet: a wild grin, the glowing eye at full brightness, faint green wisps rising from the left side of the face.
```

## 5. Colour script

```text
Use the attached image as the exact design reference: the approved front view of Kael, a ghost gunslinger for a stylized isometric action game. Draw a COLOUR SCRIPT sheet: five small copies of the SAME character in the SAME front T-pose, same design, same rendering style, but WITHOUT the two revolvers (empty loose fists), each showing one colour state.

LAYOUT: landscape 1536x1024, five full-body figures side by side in one row, all the same size, head to toe visible, orthographic, on a flat solid dark navy background #141E27. Along the bottom edge, a single row of plain colour swatches of his palette. No text, labels, numbers or borders.

STATES, left to right:
1. FLAT COLOUR: local colours only, no shading, no glow: coat #241B24, loin cloth #36242F, shirt and trousers #242328, leather #402A25, boots #43322F, bronze #886F59, skin #937160, hair #211D1D, ghost green #80B290.
2. APPROVED: identical to the reference, without the guns.
3. GAME LIGHT: a warm golden key light from the upper left, a cool blue fill from the right and a crisp warm-white rim light round the silhouette; the coat's lit faces lift clearly above its shadows; the ghost green stays unlit and glowing.
4. GHOST STEP: mid-dash: the ghost arm, the eye, the gem and the ghost-flame tatters brighter (#B1DEBA cores), a faint translucent green afterimage of him behind.
5. BULLET BALLET: every ghost-green element at full brightness, the flame tatters longer and flaring, a translucent glowing mint-green ghost copy of a gun in his left hand; the rest of the body unchanged, so the dark coat keeps its shape.
```

---

## Later: the same sheets from ComfyUI

The pipeline also allows ComfyUI style-locked workflows for stage 0 (IP-Adapter or a style LoRA). Neither is set up.
An IP-Adapter conditioned on **our own** approved front view would be allowed; a style LoRA needs a style bible of
approved sheets first, and it may never be trained on competitor art. Until then, ChatGPT with the approved front
attached is the stage-0 generator.
