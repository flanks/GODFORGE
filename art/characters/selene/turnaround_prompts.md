# Selene: prompts for the missing stage-0 sheets

Stage 0 has one approved sheet, the T-pose front
([`references/SELENE_front_approved.png`](references/SELENE_front_approved.png)). These prompts produce
the rest: **side, back, 3/4 and expression**. All four are **optional** (`pending_human` in
[`status.json`](status.json)): stage 1 and stage 2 can proceed from the front and the proposals in
[`brief.md`](brief.md) section 7.2. The side and back sheets are the most useful before stage 2 (the cape
attachment, the back of the bodysuit, the bun, the sabaton depth).

Each block is complete on its own: paste one block into ChatGPT (image generation) **with
`SELENE_front_approved.png` attached**. A human approves every sheet; the prompts are tools for that
decision, not the decision itself.

**Rules these prompts follow (docs/ART_PIPELINE.md):** the only style reference is our own approved
concept. Prompts never name another game, studio or artist. There is no style LoRA.

**The coils.** The front shows two floating coil devices beside her hands. They are weapon / VFX, not
part of the body: every prompt below leaves them out and asks for empty, relaxed hands.

## Before generating: proposals the approver should confirm or change

| Question | Proposal used in the prompts |
|---|---|
| Crown shards | Six small storm-crystal shards (three per side, symmetric) float in a ring around the head, as drawn |
| The capes | Two long outer capes attach at the ornate shoulder bows and hang behind the arms and down the back to about knee height, deep blue fading to ragged pale storm-cloud edges; not sewn to the arms |
| The back | The black bodysuit is closed at the back, with a thin gold filigree line down the spine; the high collar wraps round the neck; the silver bun is a wrapped knot with a few loose strands |
| The feet | Pointed armoured sabatons; the side view shows a flat sole under the pointed toe, not a ballet point |

## Accepting a sheet (the stage-0 gate)

Generate several and pick the closest. **Reject** a sheet if any of these is true:
- the design changed: the high collar with the blue diamond gem, the gold straps over the bust, the two
  belt rings, the long pale centre tabard, the two hip panels, the two outer capes, the gold-trimmed
  greaves with cyan V-glows, the pointed sabatons, the dark fingerless gauntlets with ice-blue claw tips,
  the lightning-vein tattoos on the bare arms;
- the floating coils (or any weapon) appear, or extra accessories;
- the proportions drifted: about 8.4 heads tall including the bun, long legs (crotch at about 0.54 of the
  height), a slender waist;
- the view has perspective, or the background is not flat `#17202A`, or there is text, a floor, a shadow
  or a vignette.

For turnarounds, overlay the sheet on the front at the same scale: the bun top, chin, belt rings, knee
plates and sabaton tips should line up to within a few pixels.

To record an approval:

```text
python tools/comfy/approve_sheet.py selene <side|back|three_quarter|expression> <sheet.png> --by "<who approved>"
```

It copies the sheet to `references/SELENE_<sheet>_approved.png`, sets the item in `status.json` to `done`
with `approved_by` / `approved_on`, and records its sha256 in `manifest.json`.

---

## 1. Side view (right profile)

```text
Use the attached image as the exact design reference. It is the approved front view of Selene, a storm sorceress hero for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style, seen exactly from her right side (she faces image-right). Do not redesign, add or remove anything.

CHARACTER (must match the reference): a tall, slender woman. Silver-white hair swept back into a high bun, a few loose strands by the face; six small storm-crystal shards (gold-edged, ice-blue cores) float in a ring around her head, not touching it. Glowing ice-blue eyes. A black, high-collared, sleeveless bodysuit with thin gold filigree trim, gold straps over the bust, and a glowing blue diamond gem at the front of the collar. Bare arms with glowing blue lightning-vein tattoos from the shoulders to the wrists; dark fingerless gauntlets from mid-forearm to the knuckles with short ice-blue claw tips on the fingers. Ornate dark-and-gold shoulder bows at the top of each arm. Two gold belt rings at the hips, gold-edged hip plates, a long pale storm-blue tabard panel hanging at the front between the legs, two long storm-blue hip panels, and two long outer capes attached at the shoulder bows that hang behind the arms and down the back, deep blue fading to ragged pale storm-cloud edges. Black leggings, gold-trimmed dark navy armoured greaves with small glowing cyan V-slots, pointed armoured sabatons with a flat sole.

POSE: relaxed A-pose, arms about 30 degrees out from the body, hands open and empty, standing on the ground. NO weapons, NO floating coil devices, nothing in or near the hands.

COLOURS (keep exactly): skin #C6ABA1; hair #ADB1BD with #DDEAF3 highlights; bodysuit #1E252B; leggings #222C3F; gold trim #8F7D68 highlights over #635346; capes #213F6F fading to #7788A8 at the edges; hip panels #40648D; tabard #3F5D8D paling toward the hem; greaves and sabatons #2C303B; glows (eyes, gem, veins, greave slots) #5BD4F4 with near-white #A4EFFA cores, kept small.

FORMAT: landscape 1536x1024. One full-body figure, head to toe fully visible, the same size and vertical placement as the reference (bun top and sabaton tips at the same heights). Strictly orthographic: no perspective, no camera tilt. Flat solid dark navy background #17202A: no gradient, no floor, no cast shadow, no vignette, no particles. The same soft even lighting and the same rendering style as the reference: clean painted illustration with crisp dark linework. No text, labels, watermark or border. No other characters or props.
```

## 2. Back view

```text
Use the attached image as the exact design reference. It is the approved front view of Selene, a storm sorceress hero for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style, seen exactly from behind. Do not redesign, add or remove anything.

CHARACTER (must match the reference): a tall, slender woman with silver-white hair in a high wrapped bun with a few loose strands; six small storm-crystal shards (gold-edged, ice-blue cores) float in a ring around her head. From behind: the black high-collared sleeveless bodysuit is closed at the back with a thin gold filigree line down the spine; the high collar wraps round the neck. Bare arms with glowing blue lightning-vein tattoos continuing over the backs of the arms; dark fingerless gauntlets. Two long outer capes hang from the ornate shoulder bows down her back to about knee height, deep blue at the top fading to ragged pale storm-cloud edges with torn hems and darker cloud blotches; between them the two storm-blue hip panels and the back of the black leggings. Gold-trimmed dark navy greaves and pointed armoured sabatons.

POSE: relaxed A-pose, arms about 30 degrees out from the body, hands open and empty, standing on the ground. NO weapons, NO floating coil devices.

COLOURS (keep exactly): skin #C6ABA1; hair #ADB1BD with #DDEAF3 highlights; bodysuit #1E252B; leggings #222C3F; gold trim #8F7D68 over #635346; capes #213F6F fading to #7788A8; hip panels #40648D; greaves and sabatons #2C303B; glows #5BD4F4 with #A4EFFA cores, kept small.

FORMAT: landscape 1536x1024. One full-body figure, the same size and vertical placement as the reference. Strictly orthographic. Flat solid dark navy background #17202A: no gradient, floor, shadow, vignette or particles. The same rendering style as the reference. No text, labels, watermark or border. No other characters or props.
```

## 3. Front three-quarter view

```text
Use the attached image as the exact design reference. It is the approved front view of Selene, a storm sorceress hero for a stylized isometric action game. Draw the SAME character with the SAME design, proportions, colours and rendering style, turned 45 degrees to her left (her right shoulder toward the viewer). Do not redesign, add or remove anything.

CHARACTER (must match the reference): a tall, slender woman; silver-white hair in a high bun; six small storm-crystal shards floating in a ring around her head; glowing ice-blue eyes; black high-collared sleeveless bodysuit with thin gold filigree, gold straps over the bust and a glowing blue diamond gem at the collar; bare arms with glowing blue lightning-vein tattoos; dark fingerless gauntlets with ice-blue claw tips; ornate shoulder bows; two gold belt rings; a long pale storm-blue tabard at the front, two storm-blue hip panels, two long outer capes from the shoulder bows, deep blue fading to ragged pale storm-cloud edges; black leggings; gold-trimmed greaves with small cyan V-glows; pointed armoured sabatons.

POSE: relaxed A-pose, arms about 30 degrees out, hands open and empty, standing on the ground. NO weapons, NO floating coil devices.

COLOURS (keep exactly): skin #C6ABA1; hair #ADB1BD; bodysuit #1E252B; leggings #222C3F; gold #8F7D68 over #635346; capes #213F6F fading to #7788A8; panels #40648D; tabard #3F5D8D; greaves and sabatons #2C303B; glows #5BD4F4 with #A4EFFA cores, small.

FORMAT: landscape 1536x1024, one full-body figure, the same size and vertical placement as the reference. Orthographic, no perspective. Flat solid dark navy background #17202A: no gradient, floor, shadow, vignette or particles. The same rendering style as the reference. No text, labels, watermark or border.
```

## 4. Expression sheet

```text
Use the attached image as the exact design reference. It is the approved front view of Selene, a storm sorceress hero for a stylized isometric action game. Draw a head-and-shoulders expression sheet of the SAME character in the SAME rendering style: six heads in two rows of three, all front-facing, the same size and framing.

CHARACTER (must match the reference): silver-white hair swept back into a high bun with a few loose strands by the face; six small storm-crystal shards floating in a ring around her head; glowing ice-blue eyes; pale cool skin; the black high collar with the glowing blue diamond gem; bare shoulders with glowing blue lightning-vein tattoos.

EXPRESSIONS: 1 neutral and cold (as in the reference); 2 focused, casting (eyes blazing brighter, lightning crackling at the temples); 3 a thin confident smirk; 4 hurt, wincing; 5 furious, shouting, hair lifted by static; 6 serene, eyes half-closed, the crown shards spread wider (her ultimate).

COLOURS (keep exactly): skin #C6ABA1; hair #ADB1BD with #DDEAF3 highlights; collar #1E252B with gold #8F7D68 trim; glows #5BD4F4 with #A4EFFA cores.

FORMAT: landscape 1536x1024. Flat solid dark navy background #17202A, no gradient or vignette. The same rendering style as the reference: clean painted illustration with crisp dark linework. No text, labels, numbers, watermark or border.
```
