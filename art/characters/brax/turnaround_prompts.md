# Brax: prompts for the missing stage-0 sheets

Stage 0 has one approved sheet, the front view
([`references/BRAX_front_approved.png`](references/BRAX_front_approved.png)). These prompts produce
the rest: **side, 3/4, back, expression, gauntlet (weapon) and colour script**. Each block below is
complete on its own, so paste one block into ChatGPT (image generation) **with
`BRAX_front_approved.png` attached**.

A human approves every sheet. These prompts are tools for that decision, not the decision itself.
Until a sheet is approved, its status stays `pending_human` in [`status.json`](status.json).

**Rules these prompts follow (docs/ART_PIPELINE.md):** the only style reference is our own approved
concept. Prompts never name another game, studio or artist. There is no style LoRA yet; if one is
ever trained, it is trained only on our approved sheets.

## Before generating: proposals the approver should confirm or change

The front concept does not show these. The prompts use the proposals in the right-hand column (from
[`brief.md`](brief.md) section 7). If the approver wants something else, edit the matching sentence
in the prompt first.

| Question | Proposal used in the prompts |
|---|---|
| The back | Lava cracks continue over the trapezius and shoulder blades, thinner and dimmer than on the chest. **No second sigil.** The belt goes around without a buckle. The sash is knotted at the front only. The scale skirt wraps all the way around. |
| The fist | Rigid rock plates per finger segment that overlap when curled. The knuckle plates form a flat punching face. |
| Heat states | Cooled embers at 0 Heat (never fully dark), bright cracks and skin veins at max Heat. |
| Meltdown | The cracks widen into yellow-white seams, and the rock stays dark between them so the fist keeps its shape. The sigil and eyes go white-hot. |

## Accepting a sheet (the stage-0 gate)

Generate several and pick the closest. **Reject** a sheet if any of these is true:
- the gauntlet design changed (plate shape, two bronze bands per arm, cog knob under the elbow ring,
  lava only in the grooves);
- the chest sigil changed (a ring plus a vertical line);
- the sash knot or tail length moved;
- the wraps, bare feet or skirt tiers changed;
- extra accessories appeared;
- the proportions drifted: about 7.3 heads tall, each gauntlet about 37 % of his height;
- the view has perspective (the near and far feet or gauntlets differ in size);
- the background is not flat `#171E25`, or there is text, a floor, a shadow or a vignette.

For turnarounds, overlay the sheet on the front view at the same scale: the crown, chin, belt, skirt
hem, knees and soles should line up to within a few pixels.

To record an approval, run one command:

```text
python tools/comfy/approve_sheet.py brax <side|three_quarter|back|expression|weapon_gauntlet|color_script> <sheet.png> --by "<who approved>"
```

It copies the sheet to `references/BRAX_<sheet>_approved.png`, sets the sheet's item in
`status.json` to `done` with `approved_by` and `approved_on`, and adds the file's sha256 under
`references` in `manifest.json`. It never approves anything by itself. Rejected candidates stay
local in `work/` (gitignored).

---

## 1. Side view (left profile)

```text
Use the attached image as the exact design reference. It is the approved front view of Brax, a bare-knuckle demigod brawler for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style. Do not redesign, add or remove anything.

CHARACTER (must match the reference): huge black basalt-rock forge gauntlets running from the fingertips to just past the elbows, built from chunky polygonal rock plates with glowing orange-yellow lava only in the cracks between the plates; each gauntlet has a wide bronze ring at the elbow end with a round cog-like knob on its underside, and a thin bronze band around the middle of the forearm. Bare, very muscular torso with a strong V-taper. A glowing lava sigil on the centre of the chest (a ring with a vertical line through it, from the collarbones down to the navel) and thin glowing lava cracks across the chest, shoulders and upper arms. Short spiky dark hair, short full dark beard, glowing amber eyes under a heavy brow. Dark riveted leather belt with a round bronze buckle. A teal sash knotted below the belt with two long frayed tails hanging down the front to mid-shin, with a thin gold meander pattern. A skirt of overlapping bronze leaf-shaped scale plates in three tiers over a torn dark red-brown cloth under-skirt. Teal cloth wraps criss-crossed over pale linen from the ankles to mid-calf. Barefoot.

PROPORTIONS: about 7.3 heads tall; each gauntlet is about 37% of his total height long and about 1.6 times thicker than his bare upper arm; shoulders about twice as wide as the waist; the skirt flares wide.

COLOURS (keep exactly): skin #B46746 with shadows #854936; gauntlet rock #291F1E; lava #F2753B with #FEE265 cores and #E7480D edges; bronze #955B32 with #D99452 highlights; teal sash #1F5A64; gold pattern #7A6435; under-skirt cloth #4A2B26; belt #291E1B; ankle wraps #284244 over linen #715846; hair and beard #1C1210.

FORMAT: landscape 1536x1024. One full-body figure, head to toe fully visible, the same size and vertical placement as in the reference (about 95% of the image height, crown and soles at the same heights as the reference). Strictly orthographic: no perspective, no camera tilt, eye level at the figure's centre. Flat solid dark navy background #171E25: no gradient, no floor, no cast shadow, no vignette, no particles. The same soft, even lighting as the reference. The same rendering style as the reference: clean painted illustration with crisp dark linework and cel-style shading. No text, labels, watermark or border. No other characters or props.

VIEW: exact LEFT side profile, rotated 90 degrees from the reference. He faces the LEFT edge of the image and we see his LEFT side (his left shoulder is nearest to us). Keep the same T-pose: his near (left) arm points straight at the viewer, so the near gauntlet is seen end-on (open fingertips and knuckle plates facing us, the bronze elbow ring behind them), and his far (right) arm points straight away, hidden behind his body. His legs are apart along the viewing direction, so they overlap in profile. Show the depth of the chest and back, the sash tails hanging in front of the skirt, the scale plates wrapping around the hip, the back of the calves and the heels.
```

## 2. Front three-quarter view

```text
Use the attached image as the exact design reference. It is the approved front view of Brax, a bare-knuckle demigod brawler for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style. Do not redesign, add or remove anything.

CHARACTER (must match the reference): huge black basalt-rock forge gauntlets running from the fingertips to just past the elbows, built from chunky polygonal rock plates with glowing orange-yellow lava only in the cracks between the plates; each gauntlet has a wide bronze ring at the elbow end with a round cog-like knob on its underside, and a thin bronze band around the middle of the forearm. Bare, very muscular torso with a strong V-taper. A glowing lava sigil on the centre of the chest (a ring with a vertical line through it, from the collarbones down to the navel) and thin glowing lava cracks across the chest, shoulders and upper arms. Short spiky dark hair, short full dark beard, glowing amber eyes under a heavy brow. Dark riveted leather belt with a round bronze buckle. A teal sash knotted below the belt with two long frayed tails hanging down the front to mid-shin, with a thin gold meander pattern. A skirt of overlapping bronze leaf-shaped scale plates in three tiers over a torn dark red-brown cloth under-skirt. Teal cloth wraps criss-crossed over pale linen from the ankles to mid-calf. Barefoot.

PROPORTIONS: about 7.3 heads tall; each gauntlet is about 37% of his total height long and about 1.6 times thicker than his bare upper arm; shoulders about twice as wide as the waist; the skirt flares wide.

COLOURS (keep exactly): skin #B46746 with shadows #854936; gauntlet rock #291F1E; lava #F2753B with #FEE265 cores and #E7480D edges; bronze #955B32 with #D99452 highlights; teal sash #1F5A64; gold pattern #7A6435; under-skirt cloth #4A2B26; belt #291E1B; ankle wraps #284244 over linen #715846; hair and beard #1C1210.

FORMAT: landscape 1536x1024. One full-body figure, head to toe fully visible, the same size and vertical placement as in the reference (about 95% of the image height, crown and soles at the same heights as the reference). Strictly orthographic: no perspective, no camera tilt, eye level at the figure's centre. Flat solid dark navy background #171E25: no gradient, no floor, no cast shadow, no vignette, no particles. The same soft, even lighting as the reference. The same rendering style as the reference: clean painted illustration with crisp dark linework and cel-style shading. No text, labels, watermark or border. No other characters or props.

VIEW: front three-quarter view, the whole body rotated 45 degrees from the reference. He faces halfway between the viewer and the LEFT edge of the image, so his LEFT side (on the right of the reference image) turns toward us and his left shoulder is closer to us than his right. Keep the same T-pose: the near (left) arm points diagonally toward the viewer and to the right of the image, the far (right) arm diagonally away and to the left. Both gauntlets stay fully visible and, because the view is orthographic, the same size. Show the side of the ribcage, the turn of the skirt plates around the hip and the sash tails in front.
```

## 3. Back view

```text
Use the attached image as the exact design reference. It is the approved front view of Brax, a bare-knuckle demigod brawler for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style. Do not redesign, add or remove anything.

CHARACTER (must match the reference): huge black basalt-rock forge gauntlets running from the fingertips to just past the elbows, built from chunky polygonal rock plates with glowing orange-yellow lava only in the cracks between the plates; each gauntlet has a wide bronze ring at the elbow end with a round cog-like knob on its underside, and a thin bronze band around the middle of the forearm. Bare, very muscular torso with a strong V-taper. Short spiky dark hair. Dark riveted leather belt. A teal sash knotted at the front below the belt. A skirt of overlapping bronze leaf-shaped scale plates in three tiers over a torn dark red-brown cloth under-skirt. Teal cloth wraps criss-crossed over pale linen from the ankles to mid-calf. Barefoot.

PROPORTIONS: about 7.3 heads tall; each gauntlet is about 37% of his total height long and about 1.6 times thicker than his bare upper arm; shoulders about twice as wide as the waist; the skirt flares wide.

COLOURS (keep exactly): skin #B46746 with shadows #854936; gauntlet rock #291F1E; lava #F2753B with #FEE265 cores and #E7480D edges; bronze #955B32 with #D99452 highlights; teal sash #1F5A64; under-skirt cloth #4A2B26; belt #291E1B; ankle wraps #284244 over linen #715846; hair #1C1210.

FORMAT: landscape 1536x1024. One full-body figure, head to toe fully visible, the same size and vertical placement as in the reference (about 95% of the image height, crown and soles at the same heights as the reference). Strictly orthographic: no perspective, no camera tilt, eye level at the figure's centre. Flat solid dark navy background #171E25: no gradient, no floor, no cast shadow, no vignette, no particles. The same soft, even lighting as the reference. The same rendering style as the reference: clean painted illustration with crisp dark linework and cel-style shading. No text, labels, watermark or border. No other characters or props.

VIEW: exact BACK view, rotated 180 degrees from the reference: we see his back, and his LEFT arm is now on the LEFT side of the image. Same T-pose: arms straight out at shoulder height, the backs of the gauntlets (back-of-hand plates and the tops of the finger plates) facing us, legs apart. BACK DESIGN: thin glowing lava cracks continue over the trapezius and shoulder blades, thinner and dimmer than on the chest, and there is NO sigil on the back. A broad muscular back with a strong V-taper. The leather belt continues around the back without a buckle. The teal sash is knotted at the front, so from behind only the band of teal cloth around the waist shows. The bronze scale plates wrap all the way around the hips, with the torn under-skirt below them. The backs of the legs, the heels, and the wraps from behind. The back of the head shows short spiky hair.
```

## 4. Expression sheet

```text
Use the attached image as the exact design reference: the approved front view of Brax, a bare-knuckle demigod brawler for a stylized isometric action game. Draw an EXPRESSION SHEET of the SAME character's head and shoulders, with the same face, the same rendering style and the same colours. Do not redesign him.

FACE (must match the reference): a strong square jaw with a short full dark beard (#1C1210), short spiky dark hair, a heavy brow, glowing amber eyes (#F5A611 with #FAEA3C cores), warm sun-dark skin (#B46746, shadows #854936), thin glowing lava cracks on the neck, collarbones and shoulders (#F2753B), and the top of the chest sigil (a glowing ring with a vertical line) just visible at the bottom of each frame.

LAYOUT: landscape 1536x1024, six heads in a 3x2 grid, evenly spaced, each the same size, each framed from the top of the hair to the upper chest, all facing the viewer head-on as in the reference, orthographic, with the same soft even lighting. Flat solid dark navy background #171E25. No text, labels, numbers, borders or panel frames.

EXPRESSIONS, left to right, top row then bottom row:
1. Neutral and stern, exactly as in the reference.
2. Battle roar: mouth wide open showing teeth, brows crushed down, neck tendons straining.
3. Cocky half-grin: one corner of the mouth up, one brow raised, eyes narrowed.
4. Taking a hit: eyes squeezed shut, teeth clenched, head flinching slightly to one side.
5. Heat building: a focused glare, eyes glowing brighter, lava cracks on the neck brighter.
6. Meltdown fury: a snarl, eyes white-hot, every lava crack at full glow, the face lit from below by the glow.
```

## 5. Gauntlet (weapon) sheet

```text
Use the attached image as the exact design reference: the approved front view of Brax, a bare-knuckle demigod brawler for a stylized isometric action game. Draw a WEAPON SHEET of his RIGHT forge gauntlet on its own, exactly as designed in the reference. Do not redesign it.

GAUNTLET (must match the reference): black basalt rock (#291F1E, lighter top faces #4A3A36) made of chunky, bevelled polygonal plates; glowing lava (#F2753B, cores #FEE265, edges #E7480D) ONLY in the grooves between the plates; each finger has three rigid plated segments, with heavy knuckle plates over the back of the hand; a wide bronze ring (#955B32, highlights #D99452) at the elbow end with a round cog-like knob on its underside; a thin bronze band around the middle of the forearm; the gauntlet is cut cleanly just above the elbow ring, where a dark leather cuff and the bare upper arm would begin.

LAYOUT: landscape 1536x1024, one clean grid of orthographic views, all at the same scale, evenly spaced, on a flat solid dark navy background #171E25, with the same soft even lighting and the same rendering style as the reference (clean painted illustration, crisp dark linework, cel-style shading). No text, labels, arrows or borders.

VIEWS:
1. Top view (back of the hand), fingers extended.
2. Palm view, fingers extended.
3. Outer side view (little-finger side).
4. Inner side view (thumb side).
5. End-on view looking at the fingertips.
6. Closed fist, top view.
7. Closed fist, side view, showing how the rock plates overlap and slide over each other as the fingers curl, and how the knuckle plates form a flat punching face.
8. A close-up detail of a few rock plates with the glowing cracks between them, plus the bronze elbow ring and its cog knob.
```

## 6. Colour script

```text
Use the attached image as the exact design reference: the approved front view of Brax, a bare-knuckle demigod brawler for a stylized isometric action game. Draw a COLOUR SCRIPT sheet: six small copies of the SAME character in the SAME front T-pose, same design, same rendering style, each showing one colour state.

LAYOUT: landscape 1536x1024, six full-body figures side by side in one row (or a 3x2 grid), all the same size, head to toe visible, orthographic, on a flat solid dark navy background #171E25. Along the bottom edge, a single row of plain colour swatches of his palette. No text, labels, numbers or borders.

STATES, left to right:
1. FLAT COLOUR: local colours only, no shading, no glow: skin #B46746, gauntlet rock #291F1E, lava #F2753B, bronze #955B32, teal sash #1F5A64, gold pattern #7A6435, under-skirt cloth #4A2B26, belt #291E1B, ankle wraps #284244, linen #715846, hair and beard #1C1210, eyes #F5A611.
2. APPROVED: identical to the reference.
3. GAME LIGHT: a warm golden key light from the upper left, a cool blue fill from the right and a crisp warm-white rim light around the silhouette; the shadows stay warm and never go grey.
4. HEAT ZERO: the lava cracks cooled to dim dark-red embers (still faintly visible, never completely dark), the chest sigil faint, the eyes dim amber.
5. HEAT MAX: the cracks bright orange-yellow, thin glowing veins spreading over the shoulders and upper chest, the eyes bright, small embers rising from the fists.
6. MELTDOWN: the gauntlets go molten, the cracks widening into glowing yellow-white seams while the rock stays dark between them so the fists keep their shape; the chest sigil and eyes white-hot; heat shimmer around the fists.
```

---

## Later: the same sheets from ComfyUI

The pipeline also allows ComfyUI style-locked workflows for stage 0 (IP-Adapter or a style LoRA).
Neither is set up yet. An IP-Adapter conditioned on **our own** approved front view would be
allowed. A style LoRA needs a style bible of approved sheets first, and it may never be trained on
competitor art. Until then, ChatGPT with the approved front attached is the stage-0 generator.
