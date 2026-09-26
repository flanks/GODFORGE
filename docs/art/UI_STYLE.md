# GODFORGE: the UI style (final spec)

The user asked, in Swedish, to make the in-game UI beautiful ("snygga till UI i spelet, gör det
snyggare"). The bar is Hades II's quality: ornate but restrained gilded frames, dark lacquered
panels, classical serif capitals, crisp body text, icons over words, and juicy feedback. It must
not cost readability in a 4-player fight with 400 enemies.

This page is the single spec for that work. Two designers made competing proposals: A, "Gilded
Mythic", and B, "Readable Chaos". This page takes B's layout and information design as the backbone
and grafts on A's ornament, portraits and card silhouette. Implementers match the mockups in
`docs/art/ui_mockups/` and the numbers here. Everything is in **1920×1080 logical px (UiScale
1.0)** unless a line says otherwise. If this page and a mockup disagree, this page wins.

| Mockup | What it shows |
|---|---|
| `ui_hud_fight_1920.png` | The combat HUD in a 4-player fight at an anvil, about 200 enemies on screen |
| `ui_hud_states_1920.png` | Warlord bar, TEAM OVERDRIVE READY, a downed ally (the only red-white marker), a surge from the east, low HP, a hold prompt |
| `ui_forge_1920.png` | The Forge drawer at a Hot anvil, with the camera eased so the hero stands left of it |
| `ui_boons_1920.png` | The boon spread (Common, Rare hovered, Epic Duo), hero framed low under a spotlight |
| `ui_end_victory_1920.png` | The Victory screen |
| `ui_layout_regions_1920.png` | Every anchored region with its rectangle, plus the clear zones |
| `ui_visual_language_1920.png` | Tokens, type ramp, frames, slot shapes, gem cuts, states, bars, markers, icon sampler |

The backgrounds are real frames from the game, captured with the HUD hidden. The mockup generator
is in `docs/art/ui_mockups/src/` (Python 3 + Pillow + numpy + scipy).
- Run `python src/mock_hud_fight.py <plates dir> <out dir>`, and the same for `mock_forge.py`,
  `mock_boons.py`, `mock_end.py` and `mock_states.py`. `mock_board.py <out dir>` draws the board;
  `mock_layout.py <out dir>` draws the regions over the fight mockup already in `<out dir>`.
- The plates are 1920×1080 captures taken with every root UI node hidden: `hordeC_02`, `anvil_04`,
  `shrine_00` and `warlord_02` from `--autoplay --bots 3` with `--horde 400` or `--start-at`.
  `--hud-off` (§11.11) makes these reproducible.
- `src/b/` is designer B's widget kit and `src/a/` is designer A's ornament kit. `src/fin*.py`
  holds this synthesis.
- The T and I lanes (§12) may lift code from these files. Every shape in them is original to
  GODFORGE.

---

## 0. The verdict: what came from where

| Area | Decision | Source | Why |
|---|---|---|---|
| Layout backbone | Four corner clusters: the **Hearth** (me: vitals, kit, ult, Overdrive) bottom-left, the **Arsenal** (build and wallet) bottom-right, **Party** top-left, the **Wayfinder** (minimap and tracker) top-right | B | One eye fixation answers "can I act?" The south lane stays empty. About 8 % screen coverage against about 14 % today. |
| Ultimate | A molten ring in the portrait medallion, with R on a keycap under it | B, with A's molten language | Saves a socket and keeps the Hearth compact |
| Portrait | Silhouette **bust crests** (Valdris horned helm, Selene circlet, Kael hood) inside the medallion, with a player-colour enamel band | A | Reads as a character. B's sigils read as emblems. |
| Party identity | A **P chip** (a lozenge plaque with P2 to P4 in the player colour) under each ally medallion, plus the character name in small caps | A | Co-op needs "which one is P3?" at a glance |
| Slot shapes | Shape = category (Core round, Mechanism octagon, Relic arch, Sigil lozenge, ability chamfered square, Overdrive pointy hex, chassis flat hex) | B | Carries meaning without words or colour |
| Rarity backup | The **gem cut** encodes rarity too: Common round cabochon, Rare lozenge, Epic hexagon, Godforged eight-point star | B | A colour-blind backup, and it stays out of hue |
| Premium ornament | **Forge-horn corners**, the **sun-crest**, the **ember-knot divider**, the lacquer lattice and the 8-stud bezels | A | The most distinctive, original ornament of the two proposals |
| Combat chrome | "Quiet" plates: a gradient plus a 1.1 px gold hairline, and corner shadow pools instead of boxes | B | Ornament stays on the premium screens. The fight stays readable. |
| Forge | B's drawer (weapon row of socket cards, a big live DPS preview, bag cards carrying their DPS delta, a detail pane with stacked actions) inside A's ornate shell (horn corners, sun-crest), with A's dashed **ONE PART AWAY** recipe hint | B + A | B's decision flow is clearer; A's frame is richer |
| Boon offer flow | Two steps: a non-blocking **offer chip**, then Tab opens the **spread**. It also opens on its own when the hero is safe. | B | The game never pauses, and a centred panel in a 400-enemy fight kills |
| Boon cards | A's arched **shrine-niche** silhouette. The apex medallion is god-colour enamel holding the **boon icon**, with god-sigil badges on its shoulder. B's content: kind pill, NEW / UPGRADE, level pips. | A + B | Distinctive and Hades-grade without copying. The icon tells boons of one god apart. |
| End screen | B's structure (sunburst crest, stat row, party cards with a damage-share bar) with A's gilt cards and horn corners. The MVP card is gold; the others are bronze. | B + A | |
| Callouts | B's lane and type, with A's **element cabochons** flanking the name (the two elements that met) | B + A | Teaches the synergy system |
| Tracker | B's icon rows, plus A's ember-knot header rule and **surge countdown row** | B + A | |
| Pad glyphs | Neutral round studs with a lit **position** dot (south, east, west, north), with no colours and no letters | A | B's red "B" stud broke the red-white rule |
| POI colours in UI | Neutral bone glyphs and gilt rings. Only shrines take their god's colour (red gods use their secondary). | new | `palette::poi_kind_color` collides with rarity, player and danger hues (§3.4) |
| Rejected | A's bottom-right "arsenal hand" (720×280, Q/E far from HP). B's `B` key to open boons (B is target bias). A's `G` reroll (G is ping). B's red pad stud. The chip on the right edge at mid-height (it sat in the east approach lane). | | |

---

## 1. Pillars

1. **The battlefield is sacred.** Persistent UI lives in the four corners and a thin top band. The
   hero zone and the four approach lanes hold transients only (§5.4). The south lane is always
   empty.
2. **Answer each question in one place, in 0.2 s.** Am I alive, and can I act? Look at the Hearth.
   Is my team OK? Look at Party. Where do I go? Look at the Wayfinder. What am I wielding? Look at
   the Arsenal. What is happening here? The answer is anchored in the world, at the thing itself.
3. **Icons first, words second.** Abilities, parts, POIs, currencies, statuses, gods and aim modes
   are glyphs. Words appear on premium panels, prompts, the tracker and first encounters.
4. **Gold is a material; colour is a signal.** Chrome gold is always a graded metal gradient. It is
   never flat and never glowing, so it never reads as P1 gold, Godforged gold or Radiant. Signal
   hues appear only in their own domain (§2).
5. **An ornament budget.** Combat chrome is quiet: hairlines, bezels and gems. Full filigree (horn
   corners, sun-crests, lattice) is reserved for the Forge, the boon cards, the boss bar, the
   region banner, the end screen and help.
6. **Forged, not printed.** Feedback is heat and light. Charge pours in as molten metal, a ready
   state flares and cools, and a drain leaves a ghost. Pulses exist only for states that need
   action.

---

## 2. Hard rules (review checklist)

These come from ARCHITECTURE §7 and are not negotiable. Reviewers check every screenshot against
them.

| Rule | In the UI this means |
|---|---|
| **Red with white = danger only** | `danger #FF3B30` with white appears only on the downed-ally marker, pin and party state, the low-HP vignette, the surge edge flash, the elite crown tick and the boss bar's crest gem. Defeat is **not** red. HP drain ghosts are pale amber, never white on red. Pyra and Umbra-Rex reds never sit next to white text or white glyphs; use their secondary colour. |
| **Player colours only for players** | The P band in medallions, P chips, ally tags (the chevron, and the pip in the name capsule), player names in toasts, minimap dots, damage-share bars and card top bands on the end screen. Never on buttons, never on chrome. |
| **Rarity colours only for rarity** | Rarity gems, rarity words, part and boon names, rarity card rims and top washes, niche-card springer gems. Icons never bake rarity in. |
| **Element hues only for elements** | Element cabochons, element-tinted damage numbers, element keywords in text (Shock takes the Storm hue as Storm's status), callout gradients and glows, the chassis element glow. |
| **Deltas by value and shape** | A gain is `ichor` with an up-chevron, a loss is `loss #A58C86` with a down-chevron, and no change is `parch_mute ±0%`. Never green or red (green is P4 and Plague). |
| **Minimum text** | Alegreya text ≥ 13 px at 1080p (the debug strip may use 12). Cinzel caps labels ≥ 11 px, and never in sentences longer than about 5 words. The UiScale curve keeps these ≥ 10 physical px at 900p (§5.1). |
| **Every HUD text over the world** | Gets a `TextShadow` (0, 2) in `ink` at 0.85–0.95 and sits on a corner pool, ink smear or plate. |

---

## 3. Tokens

These are defined once in `ui_theme.rs` as `const Color` (§11.1). Hex values are sRGB.

### 3.1 Surfaces and metal

| Token | Hex | Use |
|---|---|---|
| `lac0` | `#0B0807` | Deepest fill, recesses, empty sockets, scrims' base |
| `lac1` | `#130D0A` | Panel gradient bottom |
| `lac2` | `#2A1E16` | Panel gradient top |
| `lac3` | `#4A3624` | Raised or hover highlight, inner top highlight |
| `scrim` | `#06050A` | Modal dim: 0.18 (Forge, plus the drawer scrim) / 0.55 (help) / 0.64 (boon spotlight) / 0.68 (end) |
| `pool` | `#050302` | Corner shadow pools and ink smears (peak alpha 0.55–0.64) |
| `gold_hi` | `#FFECB0` | Metal ramp stop 0.00 (specular) |
| `gold_lt` | `#F2C667` | Stop 0.22. Also the colour of section labels and gold text. |
| `gold_md` | `#C9933E` | Stops 0.50 and 1.00 |
| `gold_dk` | `#7A5424` | Stop 0.78. Inner lines. |
| `gold_sh` | `#3B2610` | The outer edge line around every gold shape |
| Bronze ramp | `#E6CFA0 → #B08A5A → #6E5234 → #2E2012` | Common frames, disabled rims, niche-card keylines |
| Steel ramp | `#EEF2F5 → #9AA4AE → #4E5660` | Armour plates |

**The gold is always a ramp:** hi 0 → lt 0.22 → md 0.5 → dk 0.78 → md 1.0, top to bottom. Hairlines
use the soft ramp lt → md → dk. Flat gold appears only on 1 px keylines under 60 % alpha.

### 3.2 Text, states and fills

| Token | Hex | Use |
|---|---|---|
| `parch` | `#F4E6C8` | Primary text |
| `parch_dim` | `#B9A98C` | Secondary text, labels at rest |
| `parch_mute` | `#7D705E` | Disabled and tertiary (≥ 13 px) |
| `numeral` | `#FFF8EA` | Big numerals (HP, timer, DPS, stats) |
| `ink` | `#0A0706` | Text shadows and outlines |
| `ink_text` | `#1A120B` | Text on gold (primary buttons, pills) |
| `ichor` | `#FFE9B0` | Ready, emphasis, positive deltas, numbers and keywords in rules text, active events |
| `ichor_glow` | `#FFC873` | Glows behind ichor |
| `ready_glow` | `#FFC24A` | The warm glow around a ready ability slot |
| `loss` | `#A58C86` | Negative deltas |
| Molten ramp | `#FFFBEA → #FFF6DA → #FFC95A → #E8942E → #7A3E12` | Ult ring, Overdrive hex, heat ring, event bars. The top stop is the meniscus. |

### 3.3 Vitals and enemies

| Token | Hex | Use |
|---|---|---|
| `hp_lt` / `hp` / `hp_dk` | `#E8574C` / `#C8323A` / `#7E1420` | The player HP fill, a vertical gradient with a sheen and a 1.6 px `#FFF4DC` leading edge |
| `hp_ghost` | `#F0B37A` | The drain ghost (pale amber, never white) |
| `ward` | `#DCE6EA` | The shield hatch at 0.9. The pattern carries the meaning, not the hue. |
| `boss_fill` | `#FF7A4A → #C8261E → #5E0A08` | Boss and Warlord bar. Ghost `#F7C98A`. |
| `elite_fill` | `#F06A4A → #9A1E1A` | Elite world bars |
| `enemy_label` | `#FF8A70` / `#FFB08A` | Boss kind label, phase line |
| `threat` | `#FFC95A → #E8602E` | Threat chevrons (ember, not telegraph red) |
| `warlord_glyph` | `#FF7A5A` | The Warlord icon everywhere in the UI (§3.4) |
| `danger` | `#FF3B30` + `#FFFFFF` | Real danger only (§2) |

### 3.4 Reserved hues

These are read from content and code; they are never re-typed.

| Domain | Values | Source |
|---|---|---|
| Rarity | Common `#CFC6B4` · Rare `#4FA3FF` · Epic `#B865FF` · Godforged `#FFB82E` | `palette::rarity_color` |
| Element | Kinetic `#F4E3C1` · Flame `#FF7A1A` · Storm `#3FD8FF` · Void `#A45CFF` · Plague `#86E03A` · Radiant `#FFE27A` | `palette::element_color` |
| Player | P1 `#FFC940` · P2 `#3FD8FF` · P3 `#B06CFF` · P4 `#5BE37D` | `game.ron: player_colors` |
| Gods | `color` / `color_secondary` per god | `gods.ron` |

**Conflicts, handled by shape in the UI and reported to their owners:**
- **P2 cyan and Storm are the same hex (`#3FD8FF`).** The UI keeps them apart by shape: player
  colour appears only as rings, bands, pips and chevrons; Storm appears only with the bolt glyph or
  in element text. The content owners could shift P2 to about `#56C8F5`.
- **`palette::poi_kind_color` reuses reserved hues.** Anvil is Godforged gold, Shrine is P1 gold,
  Reliquary is Epic violet, Vein is almost Storm cyan, and Warlord is the telegraph red. So the UI
  never uses `poi_kind_color`.
  - POI glyphs are bone (`#E6CFA0`) in gilt rings.
  - A shrine glyph takes its god's colour, or the secondary for Pyra and Umbra-Rex.
  - The Warlord glyph is `#FF7A5A`.
  - Recommendation for the owner of `palette.rs`: move the world beacons to the same scheme.
- **Gold overload** (chrome, P1, Godforged, Radiant) is solved by the material rule (§1.4). P1
  appears only as a flat enamel band. Godforged always brings its star-cut gem and sheen. Radiant
  appears only with its sunburst glyph.

---

## 4. Typography

### 4.1 Faces, loading and fallback

| Face | File (embedded with `include_bytes!`) | Role |
|---|---|---|
| Cinzel (variable, wght 400–900) | `assets/fonts/Cinzel-Variable.ttf` | Display: titles, names, labels, big numerals, all caps |
| Alegreya Sans Regular / Medium / Bold / Italic | `assets/fonts/AlegreyaSans-*.ttf` | Body, small numerals, damage numbers, flavour |
| DejaVu Sans / DejaVu Serif Bold | `assets/fonts/DejaVuSans.ttf`, `DejaVuSerif-Bold.ttf` | Fallback for symbols only |

- **The default font becomes Alegreya Sans Medium.** `install_fonts` already replaces
  `AssetId::<Font>::default()`; pass the Medium bytes. Plain `text()` is then body type.
- **Stacks.** Every `TextFont.font` is a `FontSource::List` ending in DejaVu:
  - display: `[Cinzel, DejaVu Serif Bold]`
  - body: `[Alegreya <face>, DejaVu Sans]`
  `FontSource::List` flattens to parley's `FontFamily::List`, which falls back per cluster
  (verified in `bevy_text-0.20.0-rc.1/src/text.rs`), so a stray ◆ still renders.
- **The rule stays anyway:** no symbol glyphs in UI strings except `· × – — % + − / :`. Every other
  symbol (◆ ◇ ∞ ▲ ▼ → ✚ ★, keycaps, currencies) is an icon, placed as a node or an `InlineImage`.
- Use **handles, not family names**: the static Alegreya faces may carry legacy family names.
  Cinzel's weight comes from `TextFont.weight = FontWeight(700 | 800 | 900)`; it is variable, so the
  weight drives `wght`. The Alegreya faces are separate handles; never ask them for a weight.
- Numerals in Alegreya use
  `FontFeatures::builder().enable(FontFeatureTag::TABULAR_FIGURES).enable(FontFeatureTag::LINING_FIGURES).build()`.
  The Bold face's default figures are already lining; `tnum` stops counters from jittering.
- Tracking is the `LetterSpacing::Px(size × em)` component.

### 4.2 The type ramp (a closed list)

Every (face, weight, size) pair builds its own glyph atlas, so the set is fixed in
`ui_theme::Ty`. Adding a style means editing that enum and this table.

| `Ty` | Face | Weight | Size | Tracking | Use |
|---|---|---|---|---|---|
| `DisplayXl` | Cinzel | 900 | 96 | 0.14 em | VICTORY / THE FORGE GOES COLD |
| `Banner` | Cinzel | 700 | 44 | 0.08 em | Region banner |
| `Callout` | Cinzel | 900 | 38 | 0.06 em | Combo callouts, TEAM OVERDRIVE READY |
| `Title` | Cinzel | 800 | 36 | 0.14 em | THE FORGE (32 for the boon title, 30 for help) |
| `BossName` | Cinzel | 800 | 30 | 0.12 em | Boss and Warlord name |
| `CardName` | Cinzel | 800 | 26 | 0.04 em | Boon name (auto-fit 26 → 20), part detail name |
| `NumXl` | Cinzel | 800 | 38 | 0 | Forge DPS |
| `NumL` | Cinzel | 800 | 30 | 0 | End-screen stats |
| `NumM` | Cinzel | 800 | 26 / 24 / 22 | 0 | Party-card numbers and shards (26), stage timer (24), heat ring (22) |
| `NumS` | Cinzel | 800 | 19 / 20 | 0 | Seals count (19), wallet (20) |
| `Label` | Cinzel | 800 | 15 | 0.18 em | Section labels (THE WEAPON), socket labels |
| `LabelS` | Cinzel | 800 | 16 / 14 / 13 | 0.08–0.16 em | Prompt verbs (16), tracker words, aim mode, OFFERS (14), god line on cards (13) |
| `Alert` | Cinzel | 900 | 20 / 18 | 0.24 em / 0 | SURGE (20), downed-marker seconds (18) |
| `Micro` | Cinzel | 800 | 12 / 11 | 0.12–0.24 em | Rarity words, HEAT / CHARGES / SHARDS, stat labels, keycap letters, pills |
| `Body` | Alegreya Medium | 500 | 18 (cards) / 17 (toasts, detail) | 0 | Rules text, toasts. Line height 23. |
| `BodyS` | Alegreya Medium | 500 | 16 / 15 / 14 | 0 | Sub-lines, hints, pin names, tracker objective names (17) |
| `Strong` | Alegreya Bold | 700 | same as its body | 0 | Numbers (`ichor`) and keywords (element hue) inside body text; names in toasts |
| `Flavour` | Alegreya Italic | 400 | 24 (end line) / 18 (banner sub) / 17 | 0 | Sub-lines, flavour |
| `Num` | Alegreya Bold, tnum | 700 | 26 (callout ×N) / 19 (HP current) / 15 (HP max) / 16 (distances) / 14 (buff seconds, pin distance) | 0 | Live small numerals |
| `Dmg` | Alegreya Bold, tnum | 700 | 21, crit 28 | 0 | Damage numbers (fixed sizes; pops use `UiTransform.scale`) |

Keycap digits use Alegreya Bold. At small sizes Cinzel's `1` reads as `I`.

---

## 5. Scale, safe areas and layout

### 5.1 UiScale

`r = window_height / 1080`

`ui = if r < 1 { 1 − (1 − r) × 0.6 } else { r }`

`UiScale = ui × user_hud_scale`, where `user_hud_scale` runs from 0.85 to 1.15 and defaults to 1.

| Window height | UiScale |
|---|---|
| 720 | 0.80 |
| 800 (Steam Deck) | 0.84 |
| 900 | 0.90 |
| 1080 | 1.00 |
| 1440 | 1.333 |
| 2160 | 2.00 |

The compressed curve below 1080 keeps body text above 11 physical px. Recompute on
`WindowResized`.

### 5.2 Safe areas and aspect ratios

- **Safe margin:** 24 px on all sides. The TV-safe option sets 48.
- **21:9 and wider:** UiScale follows height, so the extra width is battlefield. The corner
  clusters hug the physical corners. An option, "HUD in a 16:9 frame", parents every cluster to a
  centred `HudFrame` node with `width = min(100 %, h × 16/9)`.
- **16:10 and 4:3:** clusters keep their sizes. When the logical width is under 1500, the tracker
  drops to header, Seals and one objective, and the party frames drop the character name.

### 5.3 Regions at 1920×1080

The board is `ui_layout_regions_1920.png`.

| Region | Rect (x, y) | Anchor | Kind |
|---|---|---|---|
| Party | 24–282, 24–190 | top-left | persistent |
| Toast rail | 16–464, 196–292 | top-left | transient |
| Debug strip | 24–, 4–20 (pushes Party down 18) | top-left | F10 / `--fps` only |
| Minimap | 1616–1896, 24–200 (280×176) | top-right | phase 3 (`Display::None` until then) |
| Tracker | right edge 1896, from y 218 (24 without the minimap), floor y 486 | top-right | persistent |
| Boss bar | 610–1310, 24–150 | top-centre | while a boss or the Warlord is engaged |
| Callout lane | centre 960, baseline 150 (206 while the boss bar is up), ≤ 900 wide | top-centre | transient |
| Region banner | 560–1360, 180–280 | top-centre | transient, 3.5 s, suppressed in boss fights |
| Boon chip | 1566–1896, 846–918 | bottom-right, above the wallet | while an offer waits |
| Hearth | 24–580, 878–1056 | bottom-left | persistent |
| Arsenal | 1550–1896, 924–1056 | bottom-right | persistent |
| Edge pins | centres 40 px inside each edge | edges | persistent while relevant |

### 5.4 Clear zones

Nothing persistent may sit in these zones.

| Zone | Rect | Allowed inside |
|---|---|---|
| South lane | x 700–1220, y 880–1080 | Damage numbers, edge pins |
| Hero zone | Ellipse 300×220 centred (960, 540) | World-anchored transients: damage numbers, ally tags, state banners |
| W lane | x 0–170, y 490–730 | Edge pins only |
| E lane | x 1750–1920, y 490–730 | Edge pins only |

### 5.5 What moves where

| Today | Becomes |
|---|---|
| Top-left vitals panel ("Forgebearer — Valdris, The Anvil-Born", HP text, `Dash ◆◆◇`, three text cooldown bars) | The Hearth (bottom-left). The player name appears only on the end screen and in help. |
| Top-centre stage line "Cinder Wastes · Seals 0/7 · Warlord lives · 00:40 · Threat 1" | The tracker (top-right) |
| Top-right party panel with the net line | Party moves top-left. The net line goes to the debug strip. |
| Bottom-centre arsenal strip, with its `fade_arsenal` | The Arsenal (bottom-right). `fade_arsenal` is deleted. |
| Bottom-centre prompt text | World-anchored prompt plates. Personal states sit under the hero. |
| Bottom-left aim, bias, device and Overdrive panel | Hearth: the V hex plus an aim chip. The bias shows as a toast on change. The device is never shown; prompts swap glyphs instead. |
| Bottom-right "Godshards · Ember · Kills · time" | The wallet in the Arsenal. Time moves to the tracker, kills to the end screen. |
| Synergy toasts ("SHRAPNEL BLAZE!") on the left rail | The callout lane (top-centre) |
| The boon panel popping up centre-screen | The boon chip, then the spread on Tab |
| The help text panel | The help tome (§7.4) |

---

## 6. The combat HUD, element by element

The reference is `ui_hud_fight_1920.png`; the states are in `ui_hud_states_1920.png`.

### 6.1 The Hearth (bottom-left)

- **Corner pool.** A radial `pool` gradient, 1280×500, centred on (0, 1080), with alpha 0.62 at the
  corner falling to 0 with power 1.6.
- **Medallion, Ø128, centred at (88, 980).** It is both the portrait and the ultimate. Its layers,
  outside in:
  1. A gilt bezel, 4.5 px, in the metal ramp, with a 0.9 px `gold_sh` edge and **8 lozenge studs**
     (5.2 px, bronze-ivory `#E9D3A0`) on its mid-line, offset half a step (22.5°).
  2. The **ult trough**, 5 px deep, `#140C08`. It fills **clockwise from 12 o'clock** with the
     molten ramp as a conic fill, plus a 1.6 px `#FFFBEA` meniscus line at the pour front. Ten tick
     marks sit at every 10 % (`#140C08` at 0.85).
  3. A 1.8 px inner gilt rim.
  4. The **P band**: 2.6 px in the player colour, with a 0.9 px `#140B06` separator inside it.
  5. The portrait window, Ø98, with the character's bust crest (§9.3 `portraits/`).
- Ult ready: an outer glow of `#FFB23A` (14 px blur, spread 3). The glow breathes on a 1.6 s period
  and a sheen sweeps every 2.5 s (§10).
- **R keycap**, 21 tall, centred at (88, 1046), straddling the bezel.
- **Passive badge**, a Ø34 round slot at 45° upper-right, centred at (137, 931). It holds the
  passive icon. Passives with a meter or stacks add a thin conic `ichor` arc on the rim and a
  numeral. This replaces `Bar::Passive`. The `Bar::Charge` bar becomes a thin arc on the charging
  Q or E slot.
- **Buffs:** up to 4 round Ø28 slots at y 906, x = 184 + 40·i. Each has a Ø32 `ichor` ring
  that drains clockwise, and seconds (`Num` 14) at its right shoulder. Examples: Siege Stance,
  Forge Aegis while forging, Overdrive active.
- **HP bar, 360×22 at (170, 928), radius 4.**
  - The trough is `#0E0907` at 0.88, with a gilt rim at 0.9. A leaf finial (22 px) caps the right
    end at x 526.
  - The fill is the HP gradient. A **ghost** segment in `hp_ghost` runs between the new and old
    values (§10).
  - **Ward:** a diagonal hatch in `ward` from the HP end to HP + shield, clamped at max.
  - Numerals are right-aligned at x 522, baseline 945: current HP in `Num` 19 `numeral` with a
    0.8 px ink outline, then ` / max` in `Num` 15 `parch_dim`.
- **The gilt rail** (the Hearth's signature: the medallion is the pommel and the bar is the blade)
  runs along y 955 from x 146 to x 536, 2.4–3.6 px in the soft ramp. A 4 px lozenge finial sits at
  x 550.
- **Armour.** Steel plates at y 962–971 from x 170, 230 px in total with 3 px gaps, cut as
  parallelograms with a 3 px skew.
  - Full plates use the steel ramp. Empty plates are `#1A1512` with a `steel_dk` outline.
  - A plate is a `1/armor_max` step, and a partial plate fills from the left.
  - On `ArmorBreak` the plates spall (0.3 s) and a steel toast shows.
  - The plates are hidden when `armor_max = 0`.
- **Dash:** cut lozenges, r 7.2, at y 966, right-aligned so the last sits at x 524, 26 px apart.
  - Full: `#FFE7A6` with a facet highlight and a glow.
  - Empty: `#2A1F18` with a `gold_lt` refill arc sweeping around it.
  - Infinite dash shows one ∞ glyph (`states/infinite_dash`) instead.
- **Kit row, centred on y 1012:**
  - **Q** at (200, 1012) and **E** at (272, 1012) are 60 px chamfered squares (12 px chamfer,
    §8.1) with the kit icon at 74 %.
    - Ready: a `ready_glow` halo (7 px blur) and a top sheen.
    - Cooling, per §6.1a.
  - **V**, the Team Overdrive hex, is a 68 px pointy-top hex at (352, 1010).
    - The team meter fills bottom-up with molten metal under a wavy meniscus (§11.5).
    - Charging, the emblem is stamped dark (`#2A1608`). When ready, it lights in gold with a
      `#FFC940` glow.
    - While active, the meter drains from the top, the edge glows, and every rim in the Hearth and
      the Arsenal gets a 10 % `ichor` bloom.
    - Every Hearth shows V, because any player can trigger it.
  - Keycaps (20 tall) straddle the bottom of each slot at y 1043.
- **Aim chip**, starting at x 398:
  - an aim-mode icon (26 px) at (411, 1004);
  - the mode in `LabelS` 14 `parch` at x 430, baseline 1009;
  - a note in `BodyS` 15 `parch_dim` at baseline 1027: AUTO shows `−10% dmg` (from
    `aim_params.damage_mult`), MANUAL shows `Deadeye +14%` and pops on each stack, ASSISTED shows
    nothing.
  - The target bias appears as a 16 px icon after the note only when it is not Balanced.
- **Low HP (< 30 %):** the bar's brightness pulses 1.0 → 1.25 at 1.2 Hz, and a **danger vignette**
  (a radial from transparent to `#B0141A` at 0.25–0.45, rx 0.78) pulses at 0.9 Hz at the screen
  edges.
- **6.1a The cooldown language** (every slot with a cooldown, and touch buttons):
  - The icon is tinted `#6E655C` (darkened and desaturated by the multiply).
  - A `#050302` at 0.55 **conic sweep** covers the remaining fraction clockwise from 12 o'clock,
    edged by a 1.4 px `gold_lt` line.
  - The remaining seconds are centred in Cinzel 800 at 0.36 × the slot size with an ink shadow:
    one decimal under 10 s, whole seconds above.
  - In the last 0.5 s the rim warms to `gold_hi`.
  - On ready: a 90 ms white-gold flash, a 1.0 → 1.12 → 1.0 pop (220 ms) and a gold ring that
    expands 10 px and fades over 300 ms.

### 6.2 The Arsenal (bottom-right)

- **Corner pool:** 1040×420, alpha 0.6.
- **Chassis:** a 100 px flat-top hex centred at (1846, 1006).
  - It holds the chassis silhouette at 66 px over a radial glow in the current **element** hue at
    0.3.
  - A Ø30 **element cabochon** sits at its lower-left, (1808, 1040).
- **Parts:** four slots, 52 px each, at x 1578 / 1638 / 1698 / 1758 (Core, Mechanism, Relic,
  Sigil, with the Sigil nearest the chassis), y 1014.
  - The slot **shape** is the slot.
  - A rarity gem (r 5.4, cut by rarity) sits under each at y 1046.
  - The locked Sigil carries a 16 px lock at (1778, 993).
  - An empty slot is a dark recess with the ghost slot glyph at 35 %.
- **Wallet:** baseline y 948, right-aligned at x 1896.
  - `ember` icon (26) then the number, and to its left the `godshard` icon (28) then the number,
    both in `NumS` 20.
  - A change counts up over 250 ms, and the icon pops 1.0 → 1.18 → 1.0.
  - Forge charges (hammer icons) appear left of the shards only while an anvil is Hot.
- Hovering the Arsenal for 0.4 s shows a tooltip card (§7.1 detail-pane style) with the weapon
  name, the four part names and the active named combo.

### 6.3 The boon chip (above the wallet)

- It shows when `private.boon_offer` is non-empty and the spread is closed.
- **Layout, right-aligned inside 1566–1896 × 846–918:**
  - an ink smear 340×60 fading left;
  - the **god medallion** Ø60 at (1866, 880): gilt rim, a god-colour radial enamel, and the god
    sigil at 40 px in the god colour (secondary for Pyra and Umbra-Rex);
  - text ending at x 1822: `PYRA OFFERS` in `LabelS` 14 in the god colour (secondary for the red
    gods), and `a boon · 1 waiting` in `BodyS` 16 dim;
  - the **Tab keycap** (22 tall) left of the text. On a pad it is the View stud (§7.6).
- The chip pulses its god glow every 2 s. A queued offer bumps the "waiting" count (from
  `boon_queue`).

### 6.4 Party frames (top-left)

- **Rows** for up to 3 allies at y 24 / 78 / 132 (54 px pitch). Solo play hides the column.
- **Medallion, Ø46**, centred at (47, y + 23): gilt rim 2.2, lacquer window, the ally's bust, and a
  2.6 px P band.
- **P chip** (30×18, a lozenge plaque with `P2`…`P4` in the player colour) centred at (47, y + 46).
- **Name** in `Body` Bold 18 `parch` at x 81, baseline y + 19. The character name follows in
  `Micro` 12 caps `parch_dim`, 9 px after the name.
- **HP bar** 170×8 at (81, y + 28), crimson with a ghost, and a ward hatch when shielded.
- **Status glyphs** at x 265 (16 px): ult ready (the Overdrive star), forging (hammer), at the gate
  (arch).
- **Downed:**
  - the medallion ring and band go `danger` and the portrait becomes the skull;
  - `DOWNED` in `LabelS` 13 `danger` follows the name;
  - the bar becomes a white → `#FFB0A8` countdown with the seconds in `Num` 15 at x 259;
  - the pin priority goes to the top (§6.13).
- **Reforging:** the portrait dims 50 % under a gold anvil glyph, and the bar shows the reforge
  countdown in `gold_lt`.

### 6.5 Toast rail (top-left, under Party)

- Baselines 214, 246 and 278 (32 px pitch), with **3 visible at most**, newest on top. A pool of 3
  recycled nodes; no spawning.
- **Each toast:**
  - an ink smear 440×30 from x 0, fading right;
  - a 2×22 gilt accent bar at x 16;
  - a 20–22 px icon at x 35;
  - rich text from x 52 in `Body` 17: names in bold in their reserved colours (players in player
    colour, parts in rarity colour, boons in their rarity colour), the rest `parch_dim`.
- Identical toasts merge into `×N` (keep today's merge).
- Motion: slide 24 px and fade in over 180 ms, hold 3.0 s, fade over 400 ms, reflow over 150 ms.
- **Voices** (which event goes where):

  | Event | Channel |
  |---|---|
  | Boon taken, equipped, fused, rerolled, salvaged, Seal claimed, ally down or back, armour broken, bias changed | Toast |
  | Synergy, named combo formed, Team Overdrive fired, surge, gate open | Callout (§6.8) |
  | Forge errors | The Forge detail pane (a shake and the reason), never a red toast |

### 6.6 The Wayfinder (top-right): minimap hook and tracker

**Minimap (phase 3 hook).**
- `MinimapFrame` is 280×176 at (1616, 24), radius 10.
  - Its frame: a 2.8 px gilt rim, a 0.9 px `gold_dk` inner line, forge-horn corners at 30 px and a
    north gem (r 6, `#FFE7A6`) at the top centre.
  - Children: `MinimapContent` (inset 3, `Overflow::clip()`, where phase 3 writes its
    `ImageNode`) and `MinimapIcons` (absolute pins).
- It stays `Display::None` until phase 3 fills it, and the tracker then starts at y 24.
- The phase-3 map style is sepia ink: terrain folded to `#140E0A / #463424 / #967650 / #E2C896`
  with a hint of the biome liquid.
  - Player dots are in player colours; the local one is larger and has a facing wedge.
  - POIs use the pin glyph language, and the gate always shows.
  - Fog is a soft ink vignette.
  - `M` opens the full map: the same frame at 70 % of the screen, the gilt panel, region names in
    `Label`, and a legend.

**Tracker.** Right-aligned at x 1896, with no box. Its corner pool is 940×1000, alpha 0.64. Rows,
top down, from y0 = 218 (or 24):

| Row | Contents | Height |
|---|---|---|
| Header | The timer `07:32` in `NumM` 24 `numeral`, an hourglass 18 px, the biome name in `LabelS` 14 0.16 em dim. The ember-knot rule (280 wide) under it at y0 + 34. | 46 |
| Seals | One socket per required Seal at a 24 px pitch, right to left: a claimed Seal is the `seal` icon (26 px), an empty one a Ø17 `lac0` socket with a `gold_dk` ring. Then `3/7` in `NumS` 19 `gold_lt`. Reaching `required` flashes the row. The Warlord's double Seal fills two sockets with a crown flash. | 34 |
| Warlord · Gate | The Warlord glyph (24, `warlord_glyph`) + `WARLORD` → `IN BATTLE` (pulsing) → `SLAIN` (`parch_mute` with a check). The gate glyph (22) + `SEALED` (desaturated) / `GATE OPEN` (`gold_lt`) / `GATHER 6` (with a countdown ring). | 32 |
| Threat | `THREAT III` in `LabelS` + five chevron pips (15×11) lit in the `threat` ramp | 32 |
| Surge (only during a warning or a surge) | `SURGE · EAST` in `LabelS` `#FFD2C0` + seconds + a 262×6 bar (`#FFB08A → #E8602E`) | 38 |
| Active events (0–2) | The POI glyph (22) + `ANVIL · KINDLING` + `92%` in `ichor` + a 262×6 molten bar. Contested: a pause glyph, and the bar at 50 % alpha with `(step inside)` in italic. | 38 each |
| Next objectives (1–2) | The POI glyph (22) + name (`Body` 17 dim) + a bearing chevron (16, `gold_lt`, rotated to the world bearing) + distance (`Num` 16) | 28 each |

- **Floor at y 486.** Rows that would cross it drop from the bottom: next objective 2, then event
  2, then next objective 1.
- The tracker shows state; edge pins show direction.

### 6.7 Boss and Warlord bar (top-centre)

- A legibility halo (radial `pool` 0.7, 980×170).
- The kind label `WARLORD` / `BOSS` in `Micro` 12 0.4 em `enemy_label`, baseline 38.
- The name in `BossName` with the gradient `#FFF4E0 → #FFD2A0 → #E8783A`, a 0.9 px ink stroke and a
  0.3 `#FF5A2A` glow, baseline 72. It is flanked by ember-knot half-rules (92 px) at y 62.
- **The bar**, 620×18 at (650, 86):
  - the fill is `boss_fill`, the ghost `#F7C98A`;
  - a gilt 2 px rim, and **iron-horn finials** (34×30) at both ends;
  - **phase notch gems** (r 4.6, `#FFE7A6`) at each `bosses.ron phases[i].below` on the top edge;
  - a crest gem (`danger`) at the bottom centre.
- The phase line `II · BLAZE` in `LabelS` 14 0.24 em `enemy_label` at baseline 130.
- Data comes from `PrivateView.boss` or `RunView.boss` (OPEN_WORLD §7.5).
- Motion:
  - it slides down 300 ms on engage;
  - on a phase change the notch gem shatters, the bar shakes 2 px for 200 ms and the name
    cross-fades;
  - at 0 HP it bursts into gold motes over 600 ms.
- The region banner is suppressed while it shows, and the callout baseline moves to 206.

### 6.8 The callout lane (top-centre)

- **Callout:**
  - the name in `Callout` 38/900, 0.06 em, with a vertical gradient: `#FFF8E6 → element A → element
    B` for a synergy, `#FFFBEA → #FFD36B → #FFB23A` for gold events;
  - a 1.4 px ink stroke and a 0.55 glow in the second colour;
  - baseline y 150 (206 while the boss bar is up);
  - a radial `pool` halo;
  - an ember-knot underline (name width + 80) at baseline + 16.
- For synergies, **two element cabochons** (Ø30 round slots with the element icons) flank the name
  at ± (width/2 + 30), y baseline − 13, and `×N` in `Body` Bold 26 `gold_lt` follows.
- **One at a time.** A repeat of the same key bumps `×N` (1.1 → 1.0 in 100 ms). A higher priority
  replaces a lower one: surge > gate open > Team Overdrive ready or fired > named combo > synergy.
- `TEAM OVERDRIVE READY` carries an inline V keycap (24 tall) and plays once per charge.
- Motion: 1.3 → 1.0 over 160 ms (ease-out-back), alpha in 100 ms, hold 1.0 s, then rise 12 px and
  fade over 300 ms.

### 6.9 Region banner

- A radial `pool` halo (w + 420 × 170).
- An ember-knot rule with a `#FFE7A6` gem, name width + 180, at y 182.
- The name in `Banner` 44/700 0.08 em with the gradient `#FFF4D0 → #F2C667 → #B07A30` and a 1 px
  ink stroke, baseline 236.
- The sub-line (biome · flavour) in `Flavour` 18 dim at baseline 266.
- Motion: the rule draws out from the centre over 350 ms; the tracking eases from 0.30 to 0.08 em
  over 600 ms; hold 2.1 s; fade 1 s.
- **GATE OPEN** uses the same banner with the gate glyph (Ø40) above the name.

### 6.10 Surge

This is danger, so red-white is allowed.

- A 180 px edge flash on the threatened side: a horizontal gradient to `#FF6A50` at 0.55, faded at
  the top and bottom.
- Three inward chevrons, white over a `danger` glow.
- `SURGE` in Cinzel 900 20 white with a `danger` glow, and `from the east` in `Body` Bold 16
  `#FFD8D0`, centred 40 px in from the edge at mid-height.
- The 3 s warning pulses. During the 15 s surge the flash dims to 0.25, and the tracker's surge row
  counts down.

### 6.11 World-anchored UI

- **Prompt plate** (interactables). One at a time: the nearest valid one.
  - A quiet plate, 44 tall, as wide as its text + 62, radius 6, alpha 0.8, rim 0.7, with a tail
    14×8 pointing down.
  - Anchored 2.6 u above the POI heart. It is clamped out of `HudRects` and never placed in the
    south lane.
  - The keycap (20) or pad stud sits at x + 22.
  - Holds get a Ø30 ring around the key: `ink` 0.6 behind a `gold_lt` conic fill. Shrines use the
    god colour.
  - The verb in `LabelS` 16/800 0.08 em `gold_lt`, and the subject in `BodyS` 14 dim.
  - It fades over 120 ms.
- **Verbs** (OPEN_WORLD §2.3):

  | POI | State | Prompt |
  |---|---|---|
  | Anvil | Dormant | `[F] KINDLE THE ANVIL` · Anvil · 1 Seal |
  | Anvil | Kindling | `HOLD THE RING` with the ring at the %; contested: `PAUSED · step inside` with a pause glyph in `parch_mute` |
  | Anvil | Hot, you are at it | `[Tab] FORGE` · hot for 19 s. While the drawer is open: `FORGING` |
  | Anvil | Spent | No prompt; the label dims to Spent |
  | Shrine | | `[F] PRAY` · Shrine of Pyra, with a god-colour hold ring. Late claim: `[F] CLAIM YOUR BOON` |
  | Reliquary | | `[F] OPEN THE RELIQUARY` (hold) |
  | Vein | | `[F] TAP THE VEIN` (hold) · shards for all |
  | Spring | | `[F] DRINK` · heals 40 %, once |
  | Watchfire | | `[F] LIGHT THE WATCHFIRE` (1 s ring) · reveals 80 m |
  | Gate | Sealed | `SEALED · 5/7 Seals` (no key) |
  | Gate | Open | `[F] GATHER` |
  | Gate | Gathering | `GATHERING 6 s` with four player pips, filled when that player is inside |
  | Lair, Warlord, camps | | No prompt. A POI label and the arena ring. |
  | Downed ally | | `[F] REVIVE` · Bot 3, with a gold hold ring over the downed marker |

- **Personal state banner** (Downed, Reforging, Rekindle):
  - the same plate at 1.2 scale, centred 120 px **below** the hero, with a timer ring;
  - Downed uses a red-white ring and a white timer;
  - Reforging uses gold.
- **Ally tag:**
  - a 46×6 HP bar (no rim, trough `#0B0706`) at head − 8, over a player-colour chevron (8×5);
  - under 60 % HP or when downed, a name capsule is added above it: 19 tall, `#0C0806` at 0.72, a
    Ø7 player pip, the name in `Body` Bold 14;
  - tags that overlap stack upward (keep today's rule);
  - tags never enter `HudRects` or the boss band.
- **Elite bar:** 54×6 in `elite_fill`, with a small `danger` crown tick. Bosses and the Warlord
  have no world bar.
- **POI label** on screen:
  - the POI glyph (28), the name in `LabelS` 15 0.12 em, and the state line in `BodyS` 16 dim
    ("Use to heal 40 %", "Done");
  - no box: a `TextShadow` and the world behind it.
- **Downed marker** over a downed ally:
  - a Ø44 disc of `#1A0806` at 0.85 inside a 3 px `#5A1410` ring;
  - a **white conic countdown** on that ring, with a `danger` glow;
  - the tether glyph (26) in the middle and the seconds in Cinzel 900 18 white below it.

### 6.12 Damage numbers

- **What shows:** own damage only, aggregated per target, 40 alive at most (the current rules).
  - New: only targets within 480 px of the hero spawn numbers, except crits.
  - Numbers are never spawned inside `HudRects` or the callout band.
- **Normal:** `Dmg` 21 in the element hue (Kinetic `#F4E3C1`).
- **Crit:** `Dmg` 28 in `ichor` with a `#FFB347` 0.6 glow and a 16 px radiant spark at the upper
  right.
- **Legibility:** `TextShadow` (0, 2) `ink` 0.9.
- **Motion:** pop 1.4 → 1.0 in 120 ms (crit 1.5 → 1.0 plus the spark), rise 18 px over 0.7 s,
  fade over the last 0.25 s. The pop is **always `UiTransform.scale`, never the font size** (§11.10).
- Damage taken shows no numbers: the Hearth's ghost and the low-HP vignette carry it.

### 6.13 Edge pins (`offscreen.rs`, pool of 16)

- **The pin:**
  - a Ø34 medallion: a `#3A291C → #0D0806` radial at 0.92 and a 2 px ring;
  - an outward nub (11 px) pointing at the target;
  - a glyph at 24 px.
- **Ring and glyph by kind:**

  | Kind | Ring | Glyph |
  |---|---|---|
  | POI | Gilt | Bone |
  | Shrine | Gilt | God colour |
  | Ally | Player colour | Their bust |
  | Downed ally | `danger` with a white inner ring, pulsing 0.8 s | White skull |
  | Ping | The pinger's colour | |

- **Label:** 30 px inward. The distance in `Num` 14 `parch`; the name in `BodyS` 14 dim, only for
  the top-3 priorities.
- **Priority** (OPEN_WORLD §7.4): downed ally > open gate > a POI with an ally present
  (`P2 · Anvil 45%`) > allies > pings > the 3 nearest incomplete POIs > surge.
- **Placement:** centres 40 px inside the edge. Pins slide along the edge off every `HudRects` rect
  (critically damped, about 12 Hz) and fade in over 150 ms. The nub is an `ImageNode` rotated with
  `UiTransform.rotation`; this replaces the `"▲"` glyph.

### 6.14 Debug strip

- The net line (`host · KB/s · corrections`) and FPS move out of the party panel.
- One line in `BodyS` 12 `parch_mute` with tnum, at (24, 4–20). While it shows, it pushes Party
  down 18 px.
- It shows only with `--fps` or the **F10** toggle. Help no longer shows net stats.

### 6.15 Touch overlay

- Touch buttons are 72 px medallions (gilt rim, lacquer, the icon) with conic cooldowns and ready
  pops.
- The stick rings are thin gold circles at 0.4.
- The Hearth keeps its size. The kit row hides on touch, because the buttons carry it.

---

## 7. Panels

### 7.1 The Forge drawer (Tab at a Hot anvil)

Reference: `ui_forge_1920.png`.

**Framing.**
- **PanelFraming:** the camera eases its look offset 420 px to the right (350 ms, ease-out cubic),
  so the hero and anvil sit at about 28 % of the width.
- The world takes a 0.18 cool dim (`#0A0610`) and a 0.4 vignette. A horizontal scrim runs from
  x 820 (0) to x 1920 (0.62).
- The HUD keeps Party, toasts and the Hearth, and hides the Tracker, the Arsenal and the boon chip.
  The anvil's world prompt reads `FORGING`.
- **Forge focus** (time slows when every player forges) is unchanged. The footer says so.

**The shell.** The drawer's rect is x 1008–1896, y 64–1040 (888×976); `x0 = 1008`, `y0 = 64` below.
- The body is lacquer (`lac2 → lac1` at 0.95) with the tooled lozenge lattice at 3 % and an inner
  shadow of 10 px.
- A 3.2 px gilt frame and a bronze keyline 4 px inside it.
- **Forge-horn corners** at 76 px, with their spurs overhanging 10 %, and a `#FFB82E` lozenge gem
  at each boss.
- The **sun-crest** (62 px tall) is centred on the top edge at x 1452, 62 % above it.
- A drop shadow: 18 px blur, (0, 8), black 0.75.

**Header** (relative to the drawer):
- `THE FORGE` in `Title` 36 with the gold gradient and a 0.25 `#FF9A2E` glow, centred at
  (444, 70).
- The sub-line in `Flavour` 17 dim at (444, 96).
- **Left:** the **heat ring** (Ø56, a 6 px trough, the molten conic fill of
  `time_left / hot_window`, whole seconds in `NumM` 22) centred at (72, 62), labelled `HEAT`
  (`Micro` 12) at y 108. **Charges** are three 30 px hammers, lit or desaturated, at x 151 / 181 /
  211, y 58, labelled `CHARGES`.
- **Right:** godshards `56` in `NumM` 26, right-aligned at x w − 40, with the `godshard` icon (32)
  to its left, labelled `SHARDS`.
- An ember-knot divider (w − 120, `#FFE7A6` gem) at y 128.

**THE WEAPON** (the label at y 158; the row at y 172–352):
- **Chassis card**, 196×180 at x 40: the chassis silhouette at 100 px over a Ø80 element glow
  (0.35), the name in `Label` 15, and the element icon (18) + element name in `LabelS` 13 in the
  element hue.
- **Four socket cards**, 138×180 each, 12 px apart, from x 252. Each has:
  - a rarity frame (§8.2 `gilt_card_*`, with the rarity top wash);
  - the slot label (`Micro` 12 0.16 em);
  - the shaped slot (74 px) with the part icon, and a rarity glow for Epic and above;
  - the rarity gem (cut);
  - the part name in `Strong` 16 in the rarity colour (Common in `parch`);
  - a **REROLL chip** (108×26, chamfer 6): the dice icon, `REROLL`, the cost `6` and the shard
    icon. It is disabled, with the reason in the tooltip, without a charge or with too few shards.
    `free` replaces the cost when free actions remain.
- The locked Sigil shows a lock + `LOCKED` in `parch_mute`.
- **The replace target.** When a bag part is selected, the socket it would replace gets a 2 px
  `ichor` outer ring with an `ichor_glow` glow, and a `REPLACE` tab (84×20 `ichor` pill, `Micro` 11
  `ink_text`) straddles its top edge.

**Live DPS** (baseline y 404):
- The current value in `NumXl` 38 `numeral` + `DPS` (`Label` 15 dim).
- When a bag card is selected or hovered: a gold arrow (34×14), then the **preview value in
  `ichor`** with a 0.35 glow, then the delta chip (§2).
- It comes from the existing `preview()` → `apply_action()` → `build_dps()` path.
- On the right: `describe()` tags in `BodyS` 16 dim, and below them what the preview adds, in
  `Strong` 16 `ichor`.

**The recipe hint** (y 424–488):
- **ONE PART AWAY:** a quiet plate with a **dashed `ichor` outline** (9 on, 6 off, 1.6 px), the seal
  icon (36), `ONE PART AWAY` in `Micro` 11 `ichor`, the recipe name in `Label` 17 `gold_lt`, and a
  hint line in `BodyS` 15 dim (`+1 chain, +10% damage · Doomstack is in your bag`).
- On the right, the ingredient mini-sockets (Ø34): owned ones are gilt with a check, and the
  missing one has an `ichor` rim with a glow.
- Priority:
  1. the active named combo: a solid gilt outline, labelled `NAMED COMBO`;
  2. the recipe exactly one ingredient from satisfied (`recipe_ingredients`) whose missing part is
     in the bag;
  3. one with the missing part not owned;
  4. otherwise hidden.
- Compute the hint against the previewed build.
- An ember-knot divider (w − 160, at 0.8) sits at y 508.

**THE BAG** (the label + `6 / 8` at y 540; filter chips ALL · CORE · MECH · RELIC right-aligned):
- **The grid:** 4×2 cards, 194×82, 10 px gap, from (40, 556).
  - A rarity frame with the top wash, and the shaped slot (56) with the icon at the left.
  - The name in `Strong` 17 `parch` at x + 80, baseline + 34.
  - The rarity word in `Micro` 12 in the rarity colour at baseline + 56.
  - The **DPS delta chip** at the bottom-right.
  - A badge (Ø24) at the top-right for a fuse candidate (the fuse glyph) or a recipe completer (the
    seal).
  - Empty cells are `lac0` at 0.6 with a `gold_sh` rim and `EMPTY` in `Micro` `parch_mute`.
- The selected card gets a 2.2 px metal-gold outer ring, a `ready_glow` glow and a 2 px lift.

**The detail pane** (y 746 to h − 64; a quiet plate, rim 0.85):
- **Left:** a 92 px slot with a rarity glow and the gem.
- **Middle:**
  - the name in `CardName` (upper case, rarity colour, 0.25 glow);
  - `EPIC RELIC · REPLACES NYCTIAN EYE` in `Micro` 12 dim;
  - the rules text in `Body` 17 (numbers in `ichor`, element keywords in hue, up to 3 lines at
    380 px).
- **Right**, stacked buttons 214 wide:
  - **EQUIP** (primary, 46 tall) with a delta chip in `ink_text`;
  - **FUSE** (40): shows the result (`Rare → Epic`) or, when disabled, the host's refusal reason in
    italic (`no twin`, `too weak`);
  - **SALVAGE** (40): `+12` with the shard icon. Rare or better needs a 0.4 s hold, shown as a
    ring fill on the button.

**Footer** (y h − 30): key hints `[LMB] SELECT · [Tab] CLOSE` in `Micro` 12 dim with keycaps. On a
pad these swap to studs. The italic forge-focus note in `parch_mute` sits right.

**Feedback.**
- Equip flies the part along an arc from its card to the socket (300 ms), and the socket flares in
  its rarity colour.
- Fuse: two sparks converge, and the new gem fades in one tier up (450 ms).
- Reroll: the dice tumbles, and the socket icon flips (scale-X 1 → 0 → 1 over 250 ms).
- Salvage crumbles the card into shards that fly to SHARDS (350 ms).
- The DPS numeral counts up over 400 ms.
- Errors shake the pane 2 px × 3 in 180 ms and show the reason in the pane.

**Behaviour fix (required).**
- Drop `time_left` from the Forge `PanelKeys` hash. Today the whole panel is despawned and rebuilt
  every second. The heat ring and the wallet update in place.
- Selection and hover live in a `ForgeSelection` resource. The detail pane, the target ring and
  the delta chips update in place; they are never rebuilt on hover.

### 7.2 The boon spread

Reference: `ui_boons_1920.png`.

**Opening.**
- **Tab** (pad: View) opens it from the chip.
- It **auto-opens** when no enemy is within 12 u of the hero for 1.5 s.
- It never opens while the Forge drawer is open; the chip waits.
- **PanelFraming:** the camera eases 200 px so the hero sits at about 69 % of the height (350 ms).
- **Spotlight dim:** the world dims 0.64 except a soft hole of radius 170 around the hero, so
  incoming danger stays visible.
- The HUD stays live: Party, the Hearth, the Arsenal. The Tracker hides.

**Title.**
- `ZEPHYROS ANSWERS` in `Title` 32 with a vertical gradient from `#FFFFFF` to the god colour
  (`#BDF2FF` mid for Zephyros), a 0.8 px stroke and a 0.35 god glow, centred at baseline 58.
- For a mixed offer the title reads `THE GODS ANSWER` in the gold gradient.
- An ember-knot (title width + 160) with a gem **in the god colour** at y 76.
- The sub-line `Shrine of Zephyros · choose one` in `Flavour` 17 dim at 102.

**Cards.** 3 cards (or 4), 300×420, 34 px apart, centred: x 476 / 810 / 1144, y 150.

Card anatomy (card-local coordinates):

| Part | Spec |
|---|---|
| Silhouette | The **shrine niche**: straight sides, a chamfered foot (14), an ogee arch 112 tall with a small apex cusp |
| Body | Lacquer, mixed from the god colour toward `#140E0B` at 80 % at the top, down to `#090605` at the foot. Lattice at 2.5 %. A god-colour radial pool (0.4) under the arch. Duo: a second pool in god 2 on the right half. The god sigil as a **6 % watermark**, 186 px, in the lower half. |
| Frame | A 4.2 px gilt rim (Common: bronze, 3.4 px). An **enamel hairline in the god colour** at inset 6.2–7.8 (Duo: graded left → right from god 1 to god 2). A bronze keyline at inset 11.2–12.4. **Forge-horn corners** (60) at both foot corners. |
| Rarity | **Gems at both arch springers** (0, 112) and (300, 112), r 8, cut by rarity (none for Common). Godforged: a sunburst behind the medallion, a gold aura, and a diagonal sheen every 3 s. |
| Apex medallion | Ø100 centred at (150, 56): a gilt 5 px bezel; god-colour enamel (radial, 50 % darkened at the rim); the **boon icon** at 64 % in ivory. Duo: the enamel splits diagonally between both gods. Legendary: a sun-crest (50) sits over it. |
| God badges | The god sigil in a Ø34 enamel badge on the medallion's lower-right shoulder, centred at (197, 93). Duo: two Ø32 badges at (104, 94) and (196, 94). |
| God line | `ZEPHYROS` (Duo: `ZEPHYROS & NYCTIA` in `parch`) in `LabelS` 13 800, 3 px tracking, the god colour mixed 45 % toward white, baseline 146 |
| Kind pill | For Duo, Legendary and Team only: an 18-tall gold pill with `Micro` 11 `ink_text` at y 158. Everything below moves down 22. The pill carries the `boon_kind/*` glyph; Team uses the chrome-gold chain, never player colours. |
| Name | `CardName` 26 (auto-fit down to 20 at W − 44), 1 px tracking, in the rarity colour (Common `parch`, Godforged a `#FFF6D8 → #FFB82E` gradient), with a 0.3 rarity glow. Baseline 194. |
| Rarity ribbon | A 22-tall chamfered plaque (bronze or gilt) with the rarity gem at the left and the word in `Micro` 11 2.4 px, at y 206 |
| Divider | An ember-knot, 204 wide, with a rarity gem, at y 244 |
| Description | `Body` 18, centred, 248 wide, line height 23, first baseline 284. Numbers and keywords in `Strong`: numbers `ichor`, element and status keywords in their hue. Punctuation stays glued to its token. At most 4 lines. |
| Footer | `NEW` (`ichor`) or `UPGRADE` (`parch_dim`) in `Micro` 11 at (26, 386). Level pips (r 5, lit `ichor` / dark `#3A2A1C`) right-aligned at x 266. The **pick keycap** (30) on the plinth at y 405. |

- **Hover or focus:** the card lifts 12 px over 120 ms, a god-colour aura glows (24 blur, 0.55)
  and the rim brightens.
- **Buttons** under the cards at y 600 (46 tall, 236 wide):
  - `[X] REROLL · 1 left` under the left card;
  - `[Tab] LATER · +1 queued` under the right card, only when the queue is non-empty.
  The gap under the middle card stays clear, so the hero is visible.
- **God theming** comes from `gods.ron`. Pyra's `#E0312B` pairs with her gold `#FFC23D` and never
  with white; Seraphel's white never pairs with red.
- Motion:
  - Cards rise 40 px and fade in, 70 ms apart, over 260 ms (ease-out-back). The medallions flare
    (god glow 0 → 0.9 → 0.45 over 450 ms).
  - Pick: the card flares for 150 ms, the others drop 20 px and fade over 200 ms, and the icon flies
    into the Hearth medallion over 400 ms with a toast.

### 7.3 The end of the run

Reference: `ui_end_victory_1920.png`.

- **World:** blurred (5 px), dimmed 0.68 in `#080508`, with a 0.7 vignette.
- **Crest**, centred at (960, 122):
  - the anvil medallion, Ø116: a gilt bezel with 8 studs, a lacquer window and the anvil glyph at
    76 in the gold style;
  - a **16-ray sunburst** behind it (long rays to 122, short to 96, gold ramp at 0.9);
  - a `#FFB23A` glow (40 blur).
- **Title:**
  - Victory: `VICTORY` in `DisplayXl` with the gradient `#FFFBEA → #F7CE6A → #A86A22`, a 1.4 px ink
    stroke and a 0.4 glow, baseline 300.
  - Defeat: `THE FORGE GOES COLD` in a cold iron gradient (`#E8E2D6 → #7D705E`) with no glow. The
    crest is desaturated and has a crack line. **Never red-white.**
- An ember-knot (660, gem) at y 330, and the run line in `Flavour` 24 `parch` at 366.
- **Stat row:** six 196 px columns centred on 960 (TIME, KILLS, SEALS, OBJECTIVES, EXPLORED, EMBER).
  Each has an icon (34) at y 416, the value in `NumL` 30 at baseline 464, and the label in `Micro`
  12 0.24 em at 486. Gold hairlines (70 tall) separate the columns.
- **Party cards:** 330×314, 24 px apart, at x 264 / 618 / 972 / 1326, y 530. Each card has:
  - a gilded panel with 40 px horn corners: **gold for the MVP** (top damage) with a `#FFB23A` glow,
    **bronze for the rest**;
  - a 4 px band in the player colour inside the top at inset 14;
  - a medallion (Ø68, bust, P band) at (56, 64) with a P chip at (56, 98);
  - the name in `Body` Bold 22 at (104, 62), and the character in `LabelS` 13 0.2 em **in the
    player colour** at (104, 84);
  - for the MVP, a Ø36 badge with the radiant spark and `MVP` at the top-right;
  - kills in `NumM` 26 at (24, 144) and `% of the damage` right-aligned, with labels in `Micro` 11;
  - a share bar 282×8 in the player colour at y 174, scaled so the top share fills 95 %;
  - `THE WEAPON`: the chassis flat hex (44) and four shaped part slots (40, 54 px pitch) with cut
    rarity gems;
  - `BOONS`: the god sigils (24) in pick order.
- **Buttons:** `[Enter] FORGE AGAIN` (primary, 260×52) at x 680 and `[Esc] LEAVE` (secondary) at
  x 980, y 884.
- **Reveal:**
  1. the crest drops in (300 ms);
  2. the title's tracking tightens from 0.3 to 0.14 em (600 ms);
  3. the stats count up (0.8 s);
  4. the cards rise, 80 ms apart;
  5. the buttons fade in last.

### 7.4 Help (H)

- A centred ornate panel, 1040×640: horn corners at 64 and a sun-crest. The world keeps running
  under a 0.55 scrim.
- `THE ARSENAL'S LAW` in `Title` 30 with an ember-knot under it.
- **Two columns**, KEYBOARD & MOUSE and GAMEPAD, with identical rows. Each row is an action icon, a
  verb in `BodyS` 16 and a glyph chip (keycap or stud).

  | Group | Actions |
  |---|---|
  | MOVE & FIGHT | move, aim, fire, dash |
  | KIT | Q, E / RMB, R ultimate, V Team Overdrive |
  | WORLD | F interact, Tab forge or boons, G / MMB ping, T force-target, B bias, M map (phase 3) |
  | AIM | F1 / F2 / F3, one line each with its icon and its trade-off |

- **Footer toggles** as switch chips: N damage numbers · K shake · F10 debug strip · HUD size ·
  reduced motion.
- The help overlay moves from `hud.rs` to `ui.rs` (§12).

### 7.5 Door panel (legacy rooms) and the gate

- **Door panel:** a small ornate panel at the bottom-left above the Hearth. Each door is a prompt
  plate button with the reward icon.
- **Gathering:** the gate prompt shows `GATHERING 6 s` with four player pips. Missing players get
  an edge pin with their distance (priority 2).

### 7.6 Keys and pad for panels

| Action | KB/M | Pad |
|---|---|---|
| Open the pending choice (Forge at a hot anvil in range, else the boon spread) | Tab | View |
| Forge actions | Click EQUIP / FUSE / SALVAGE / REROLL | D-pad focus + South |
| Pick a boon | 1 / 2 / 3 / 4 or click | D-pad + South |
| Reroll boons | X | West |
| Later / close | Tab or Esc | View |
| Help | H | — |
| Debug strip | F10 | — |

- While a panel was opened from a pad, it captures the D-pad and South/West: dash on South and
  aim-mode on D-pad-up are suppressed until it closes.
- Focus uses `bevy_input_focus` (`TabIndex`, `AutoFocus` on EQUIP or the middle card, and
  `AutoDirectionalNavigation`). The focus ring is the selected-card ring.
- Keycaps swap to pad studs when `InputState.device` is Gamepad.

---

## 8. The frame and ornament vocabulary

### 8.1 How each piece is built (cheapest first)

| Piece | Built as | Notes |
|---|---|---|
| Quiet plate (HUD chips, prompts, detail pane, recipe hint) | **Code:** `Node { border_radius }` + `BackgroundGradient(lac2 → lac1 at α)` + `BorderGradient` (soft gold ramp) 1.1 px + `BoxShadow(black 0.55, 0, 3, 0, 9)` | The 0.8 px top highlight is a child node with a `LinearGradient` from `gold_hi` 0.28 to transparent at 35 % |
| Corner pools, halos, spotlight, low-HP vignette | **Code:** `RadialGradient` backgrounds | |
| Bars (HP, party, boss, event, share) | **Code:** a trough node + ghost + fill (`width: Percent`), each with a `LinearGradient`; `BorderGradient` rim | Pointed or leaf ends are separate finial images |
| Round slots, medallion discs, pins | **Code:** `border_radius: MAX` + gradients, plus a rim texture | |
| Shaped slots (octagon, arch, lozenge, chamfer, hexes) | **Textures:** `slots/slot_<shape>_{fill,rim,mask}@2x.png`, stretched to the node | Sweeps are clipped with the radius rule below |
| Gilt panel frame (Forge, help, detail card, tooltip, door panel) | **9-slice texture** `frames/gilt_panel@2x.png` over a code lacquer body | Corners and the crest are separate images |
| Rarity cards (sockets, bag, end cards) | **9-slice** `frames/gilt_card_<rarity>@2x.png` over a code body with a code rarity top wash | |
| Niche boon card | **Fixed-size textures** (300×420 logical): `frames/niche_frame_<rarity>@2x.png` (rim, keyline, foot horns), `niche_body@2x.png` (greyscale lacquer and lattice in the arch shape, tinted by `ImageNode.color`), `niche_hairline@2x.png` (white hairline mask, tinted by god colour; Duo: two nodes clipped to halves), `niche_glow@2x.png` (white radial in the arch, tinted by god colour) | Content is child nodes |
| Forge-horn corner, sun-crest, ember-knot, finials | **Images** sized by `Node` width and height (`NodeImageMode::Stretch`) | Flipped with `ImageNode.flip_x` / `flip_y` |
| Buttons, keycaps | **9-slice** textures | The label is text |

**The chamfer sweep rule.** Bevy clips rectangles only. A conic sweep inside a chamfered square
(chamfer c) therefore sits on a child node inset by the rim width with
`border_radius = 1.71 × c`, because a rounded corner of radius r stays inside a 45° chamfer when
r ≥ c / (2 − √2). The rim texture on top hides the difference. Round slots use `BorderRadius::MAX`.

### 8.2 The textures (lane T); everything is `@2x`

Paths are under `assets/ui/`. PNG, RGBA8, sRGB, transparent where not stated, deterministic.

| File | Size (px) | Slice border (tex px) | Logical use |
|---|---|---|---|
| `frames/gilt_panel@2x.png` | 192×192 | 48 all round; centre transparent | 3.2 px bevelled gold ring, 4 px gap, 1 px bronze keyline, r 10, a baked inner shadow 10 px, `gold_sh` edge |
| `frames/gilt_card_{common,rare,epic,godforged}@2x.png` | 96×96 | 24 | Rarity card rim, r 8. Common is a parchment-grey 1.4 px line. Rare and Epic are a 1.4 px line in the rarity colour, Epic adding an inner 0.8 px line and small corner gems. Godforged is a 2.2 px metal-gold ring with an inner gold line. |
| `frames/card_selected@2x.png` | 112×112 | 28 | The 2.2 px metal-gold selection ring (placed 5 px outside) |
| `frames/button_{primary,secondary,disabled}@2x.png` | 128×96 | 32 | Chamfer 9. Primary: gold gradient `#FFE7A0 → #E8B04E → #9A6224` with a `#3A2208` rim and a top sheen. Secondary: lacquer with a soft gold rim. Disabled: `#221A15` with a `#4E4034` rim. |
| `frames/keycap@2x.png` | 48×48 | 16 | `#3A2B1E → #16100B`, a 1 px soft gold rim, a 3 px bottom lip at 0.45 black, r 4 |
| `frames/pill@2x.png` | 64×36 | 18 | A gold pill (kind pills, REPLACE tab) |
| `frames/niche_frame_{common,rare,epic,godforged}@2x.png` | 600×840 | Stretch at a fixed 300×420 | §7.2 frame: rim, keyline, foot horns (no springer gems; those are gem nodes) |
| `frames/niche_body@2x.png`, `niche_hairline@2x.png`, `niche_glow@2x.png` | 600×840 | Stretch | See §8.1 |
| `ornaments/forgehorn@2x.png` | 256×256 | Stretch to 30 / 44 / 60 / 76 | The top-left forge-horn corner: an L-bracket with spear tips, collar bands, a flame-leaf fan, volutes, a lozenge boss socket and an outward spur. **The panel corner sits at 10 % in** (the spur overhangs). The gem is a separate node at 19 % of the size. |
| `ornaments/suncrest@2x.png` | 416×160 | Stretch (aspect 2.6:1) | 11 tapered rays (long and short alternating) over flame-wings, a lozenge boss and a pendant |
| `ornaments/emberknot_rule@2x.png` | 512×28 | 3-slice: left 480 stretch, right 32 point | A hairline tapering to a point. Used flipped for the right side. |
| `ornaments/emberknot_knot@2x.png` | 112×28 | Fixed 56×14 | Twin curls and the centre lozenge setting; the gem is a node |
| `ornaments/finial_leaf@2x.png` | 44×44 | Fixed 22 | HP bar end |
| `ornaments/finial_lozenge@2x.png` | 20×20 | Fixed 10 | Rail end |
| `ornaments/boss_horn@2x.png` | 68×60 | Fixed 34×30 | Boss bar ends |
| `ornaments/sunburst16@2x.png` | 520×520 | Fixed 260 | The end-screen crest rays |
| `slots/slot_{round,octagon,arch,lozenge,chamfer,hex_pointy,hex_flat}_fill@2x.png` | 128×128 | Stretch | The lacquer gradient `#35261A → #110B08` and an inner radial pool `#6A4A2A` at 0.35 |
| `slots/slot_*_rim@2x.png` | 128×128 | Stretch | A 1.6 px (at 64) gold bevel ring + a 0.7 px `gold_dk` inner line, transparent inside |
| `slots/slot_*_mask@2x.png` | 128×128 | Stretch | The white shape: glow tint, clip-reveal, the molten material's mask |
| `slots/medallion_hearth@2x.png` | 256×256 | Stretch to 128 | Bezel with 8 studs + trough tick marks + the 1.8 px inner rim. Transparent where the trough and window show. |
| `slots/medallion_rim@2x.png` | 128×128 | Stretch to 34–116 | A plain gilt medallion rim (party, pins, crest, cards) |
| `fx/hatch_ward@2x.png` | 20×44 | `Tiled { tile_x: true, stretch_value: 1.0 }` | The ward hatch |
| `fx/sheen@2x.png` | 128×256 | Stretch | A diagonal white band (Godforged sheen, ready gleam) |
| `fx/spark4@2x.png` | 64×64 | Fixed 16–24 | The crit spark |

**The 9-slice rule for `@2x`.** Bevy's UI slicer computes corners in *logical* px from the texture
px: `corner = border × min(target / image, max_corner_scale)` (`bevy_ui_render`
`compute_texture_slices`). An `@2x` texture therefore needs `max_corner_scale: 0.5`, or its
corners draw twice as big:

```rust
ImageNode {
    image: tex.gilt_panel.clone(),
    image_mode: NodeImageMode::Sliced(TextureSlicer {
        border: BorderRect::all(48.0),                  // texture px (= 24 logical)
        center_scale_mode: SliceScaleMode::Stretch,
        sides_scale_mode: SliceScaleMode::Stretch,
        max_corner_scale: 0.5,                          // @2x → 1 logical px per 2 texels
    }),
    ..default()
}
```

- Keep every sliced node at least half the texture size on each axis (for example the gilt panel at
  ≥ 96 logical), or the corners shrink.
- Load all UI textures with a linear sampler.

### 8.3 Recipes

- **Metal:** a height field from the mask's distance transform, a round profile, a top-left light
  (−0.55, −0.85, 0.75), spec^22, 2–6 % hammered noise, mapped through the gold or bronze ramp, with
  a 0.7 px `gold_sh` outer edge. `src/a/gmkit.py: shade_metal / metal_from_mask` is the reference.
- **Lacquer:** a vertical `lac2 → lac1` gradient, an inner edge darkening of 45 %, horizontal
  brushed streaks (±5.5), grain (±2), a warm top sheen (0.06, the top 22 %) and, on premium panels,
  a 3 % tooled lozenge lattice with a 22 px step. `lacquer()` and `lattice()` are the reference.
- **Drop shadows** (`BoxShadow`): combat plates `black 0.55, (0, 3), blur 9`; slots
  `0.75, (0, 2.5), 5`; premium panels `0.75, (0, 8), 18`; cards `0.85, (0, 12), 14`.
- **Glows:** a `BoxShadow` with zero offset, a colour, 6–18 blur and 1–3 spread.

---

## 9. Icons (lane I)

### 9.1 The style

- **Silhouette first.** Every icon reads as a solid black shape at 20 px, with one idea and at most
  two interior cuts. No text, and nothing traced or sampled from any reference.
- **Values:** 2–3. An ivory light `#FFF7E6` at the top grades into the category tint at the bottom
  (the tint mixed 35 % toward `#1A0F08`). An ink outline of about 2 % of the cell (1.3 px at a
  64 px display), `#0A0706` at 0.95.
- **Tints by category:**

  | Category | Tint |
  |---|---|
  | Kit, actions, chrome | `#D9B56C` |
  | POIs, parts, currencies, portraits | Bone `#E6CFA0` (portraits `#B08A52`) |
  | Elements and element statuses | Their element hue |
  | God sigils | The god colour (secondary for Pyra and Umbra-Rex when shown small) |
  | Warlord | `#FF7A5A` |

  Rarity is never baked into an icon, and player colour never appears in one.
- **The grid:** 128×128 masters, glyph drawn inside an 8 % pad on a 64-unit grid, strokes ≥ 1.2
  units. The frame (slot shape, pin, medallion) is drawn by the UI, not the icon.
- **Rarity gems are the one baked-colour exception.** `rarity/gem_*.png` are the cut gems in their
  rarity colour: Common round cabochon, Rare lozenge, Epic hexagon step-cut, Godforged eight-point
  star. Each has a `gold_sh` setting and a facet glint.

### 9.2 Files, table and runtime

- **Masters:** `assets/ui/icons/<group>/<name>.png`, 128×128, RGBA8, transparent background. One
  file per icon, deterministic output from `tools/ui_art/gen_icons.py`.
- **The generated table:** the generator also writes `crates/gf_client/src/icon_table.rs`, a
  generated file owned by lane I:
  `pub const ICONS: &[(&str, &[u8])] = &[("poi/anvil", include_bytes!("../../../assets/ui/icons/poi/anvil.png")), …];`
  The keys are `<group>/<name>`, sorted. `icons.rs` (lane K) `include!`s it, so the game runs from
  any cwd.
- **Runtime:**
  - K decodes each PNG at startup (`Image::from_buffer`) and builds **three levels (128, 64, 32)**
    with a premultiplied 2×2 box filter, so small icons don't alias. Bevy UI has no mipmaps.
  - `icon(IconId, logical_px)` picks the smallest level ≥ `logical_px × UiScale`.
  - `IconId` is a string key; typed helpers map content: `IconId::part(key)`,
    `boon(key)`, `chassis(key)`, `god(key)`, `portrait(key)`, `kit(char, slot)`, `element(e)`,
    `status(s)`, `poi(kind)`.
- A missing key falls back to the group's generic glyph (`parts/_core` and so on) and logs a
  warning once. The generator itself fails when a content key has no icon.

### 9.3 The complete list

Groups and file names under `assets/ui/icons/`. `✓` marks glyphs that already exist as mockup
masters in `docs/art/ui_mockups/src` (`a/gm_icons.py`, `a/busts.py`, `a/sigils.py`,
`b/icons.py`).

| Group | Files |
|---|---|
| `elements/` (6) | `kinetic` ✓ (impact chevrons), `flame` ✓, `storm` ✓ (forked bolt), `void` ✓ (ringed singularity or eclipse), `plague` ✓ (spore drop), `radiant` ✓ (eight-point sun) |
| `rarity/` (4) | `gem_common`, `gem_rare`, `gem_epic`, `gem_godforged` |
| `slots/` (4 ghost glyphs) | `core` ✓ (orb in claws), `mechanism` ✓ (gear), `relic` ✓ (amulet eye), `sigil` ✓ (seal ring with a rune) |
| `poi/` (10) | `anvil` ✓, `warlord` ✓ (crowned skull), `lair` (claw-rake cave; redraw the fang maw), `shrine` ✓ (altar flame), `reliquary` ✓ (chest), `vein` ✓ (crystal cluster), `spring` ✓ (basin and rising drop), `watchfire` ✓ (pyre), `gate` ✓ (arch with seal sockets), `camp` (crossed spears over embers) |
| `currency/` (6) | `godshard` ✓, `ember` ✓ (glowing coal), `seal` ✓ (a stamp with an anvil), `forge_charge` ✓ (hammer), `free_action` (spark over a hammer), `boon_reroll` ✓ (dice) |
| `status/` (6, enemy statuses from `gf_core::status`) | `burn` ✓, `shock` ✓, `curse` ✓ (hex eye), `root` ✓, `bleed` ✓, `mark` ✓ (crosshair lozenge) |
| `states/` (16) | `stun`, `slow`, `armor_break`, `ward`, `taunt`, `doom` ✓ (hourglass tally), `downed` ✓ (skull), `tether` ✓ (hand-flame), `reforging` (anvil + ring), `rekindle`, `invulnerable`, `infinite_dash` ✓ (∞), `forge_aegis` (anvil ward), `deadeye` (eye reticle), `overdrive_active`, `low_hp` |
| `portraits/` (12, bust crests on a Ø116 circular lacquer window, clipped) | `valdris` ✓ (horned great-helm, pauldrons), `selene` ✓ (circlet, storm orb), `kael` ✓ (hood, eye glints), `thessaly` (veiled witch with a spindle), `brax` (furnace-grate jaw, bull neck), `ossian` (hooded archer, stag antler), `mirren` (fox mask, coin earring), `epoch` (clockwork crown), `fenra`, `lyra`, `vex`, `seraph` (from `characters.ron`; each silhouette unique) |
| `kits/` (8 × 4 = 32) | `<char>_q`, `<char>_e`, `<char>_r`, `<char>_passive` for valdris (✓ bulwark_slam, siege_stance, mountainfall, armor passive), selene (arc_nova ✓; blink, heavens_verdict, static_charge), kael (fan_of_blades ✓; shadow_roll, bullet_ballet, ghost_step), thessaly, brax, ossian, mirren, epoch. The motifs are listed below the table. |
| `chassis/` (24) | One silhouette per `chassis.ron` key: `colossus_cannon` ✓, `thundercoil_launcher`, `serpent_smg`, `godsbane_rifle`, `wraith_bow`, `sunspike_shotgun`, `anvil_gauntlets`, `longstrider_rail`, `coinshooter`, `pendulum_repeater`, `bellowfire_projector`, `gravemaw_mortar`, `stormlash`, `seraph_lance`, `tidecaller_harpoon`, `orrery_discs`, `huntmother_javelins`, `chorus_harp`, `plaguebloom_sprayer`, `dawnbreaker_carbine`, `titanfall_hammer`, `voidheart_singularity`, `echoing_greatbow`, `epochal_sundial` |
| `parts/` (130) | One per `parts.ron` key: 38 hand masters for P0 and P1 (✓ stormcore, embercore, ironcore, dawncore, voidcore, mech_ricochet, mech_bounce_fork, mech_multishot, relic_splitspawn, relic_nyctian_eye, relic_vampire, relic_volatile_heart, relic_doomstack, sigil_anvilheart), and the other 92 composed (§9.4) |
| `gods/` (8) | `pyra` ✓ (crowned flame with wrath-horns), `zephyros` ✓ (bolt in gust curls), `nyctia` ✓ (crescent and veiled dagger), `aeon` ✓ (ring dial with hands), `gaiaa` ✓ (faceted heart-stone with roots), `morwenn` ✓ (wave and drop), `seraphel` ✓ (halo over scales), `umbra_rex` ✓ (broken crown over a closed eye) |
| `boons/` (116) | One per `boons.ron` key: hand masters for the 13 P1 boons (✓ blastfire, leaping_arc, quietus, stormbrand, silent_thunder, team_forge), and the rest composed (§9.4) |
| `boon_kind/` (3) | `legendary` (crown), `duo` (split lozenge), `team` (four-link chain in chrome gold, **not** player colours) |
| `aim/` (8) | `auto` ✓, `assisted` ✓ (magnet cone), `manual` ✓ (fine reticle), `bias_balanced`, `bias_nearest`, `bias_strongest`, `bias_lowest_hp`, `bias_pinned` |
| `team/` (4) | `overdrive` ✓ (star emblem; also used stamped in the V hex), `ult_ready`, `ping`, `mvp` (radiant spark) |
| `run/` (11) | `hourglass` ✓, `threat` ✓ (chevron), `surge` (horn with arrows), `gate_open`, `gate_sealed`, `gathering`, `warlord_slain`, `named_combo` ✓ (seal), `boon_queued`, `explored` (compass), `kills` (skull) |
| `ui/` (22) | `equip` ✓, `fuse` ✓, `salvage` ✓, `reroll` ✓, `lock` ✓, `check` ✓, `close`, `back`, `confirm`, `info`, `filter` ✓, `new`, `upgrade`, `delta_up` ✓, `delta_down` ✓, `bearing` ✓ (chevron), `arrowhead` (pin nub), `pause`, `settings`, `help`, `map`, `spark4` |
| `input/` (22) | `mouse_lmb`, `mouse_rmb`, `mouse_mmb`, `mouse_wheel`, `pad_south`, `pad_east`, `pad_west`, `pad_north` (position studs, no colours, no letters), `pad_lb`, `pad_rb`, `pad_lt`, `pad_rt`, `pad_ls`, `pad_rs`, `pad_ls_click`, `pad_rs_click`, `pad_dpad_up`, `pad_dpad_down`, `pad_dpad_left`, `pad_dpad_right`, `pad_view`, `pad_menu`. Keyboard keys are the 9-sliced `keycap` with text, not icons. No platform trademarks. |

**Kit motifs** (from `kits.ron`; each a single original silhouette):

| Character | Q | E | R | Passive |
|---|---|---|---|---|
| Valdris | Bulwark Slam: a fist into the ground raising a barricade ✓ | Siege Stance: a planted tower shield with rising chevrons ✓ | Mountainfall: a peak crowned by an anvil, a boulder falling ✓ | Armour Conversion: stacked plates over a heart ✓ |
| Selene | Arc Nova: a ring of branching bolts ✓ | Blink: a dissolving figure trailing a bolt | Heaven's Verdict: a storm cloud over three bolts | Static Charge: a bolt inside a charging ring |
| Kael | Fan of Blades: three fanned blades ✓ | Shadow Roll: a crescent with afterimages | Bullet Ballet: crossed spectral pistols over a star | Ghost Step: a footprint with a ghost trail |
| Thessaly | Forge Turret: a tripod turret | Binding Hex: a rune circle bound with chains | Sabbath of Sparks: a candle inside a ring of sparks | Curse Weaver: a spindle with a hex eye |
| Brax | Cinder Uppercut: a rising fist over a geyser | Furnace Rush: a shoulder charge with drag lines | Meltdown: dripping molten fists | Heat Gauge: a flame thermometer |
| Ossian | Piercing Comet: a comet through a wall | Skyhook Mortar: an arcing shell splitting into bomblets | Rain of the Hunt: arrows falling on marks | Marked Quarry: a reticle on a stag skull |
| Mirren | Gilded Decoy: a fox mask bursting into coins | Snatch: a hand closing on a gem | Grand Heist: a spilling sack | Fortune's Favour: a coin with a fox ear |
| Epoch | Still Field: a bubble of paused motes | Rewind Wounds: a counter-clockwise arrow around a heart | Stolen Second: a clock with a missing wedge | Borrowed Time: an hourglass with a stride arrow |

### 9.4 The composition kit (the 92 EA parts and 103 non-P1 boons)

- **Parts:** the main shape is a **tag motif** from `parts.ron tags`, first match in this order (the
  slot is not repeated in the icon; the slot frame carries it):

  `chain, ricochet, fork, multishot, pierce, homing, orbit, beam, turret, echo, trail, puddle, explode, volatile, doom, crit, execute, mark, curse, bleed, burn, shock, root, lifesteal, shield, greed, knockback, gravity, spread, charge, velocity, dash, elite, low_hp, luck, coin, nova, shrapnel, contagion, chaos`

  Cores draw the motif inside an orb in their element hue. Sigils draw it as a rune on a seal ring.
  A part with no matching tag gets its slot's generic glyph plus a numeral-free variation seeded by
  its key.
- **Boons:** a per-god motif set (for example Pyra: flame tongue, ember burst, wrath horn; Zephyros:
  bolt, gust, arc) chosen by the boon's first status or mechanic mod, with the god sigil small at
  the upper-right.
- The generator prints the chosen motif per key into `tools/ui_art/out/icon_report.txt` for review.

---

## 10. Motion

All motion runs through `UiTransform` (translation, scale, rotation), colour alpha and gradient
values, never layout properties. **Reduced motion** (an option) drops pulses, sheens, shakes and
flies, and keeps the fades.

| Element | Motion |
|---|---|
| HP, party, boss drain | The fill snaps. The ghost holds 0.35 s, then eases to the fill over 0.45 s (cubic out). |
| Heal | The fill grows over 0.25 s (ease-out), with an `ichor` sheen on the gained part |
| Low HP | Bar brightness 1.0 → 1.25 at 1.2 Hz. Vignette alpha 0.25 → 0.45 at 0.9 Hz. |
| Cooldown | Continuous sweep (write only when the angle moves ≥ 1°). Last 0.5 s: the rim warms. Ready: a 90 ms flash, a 1.0 → 1.12 → 1.0 pop over 220 ms, and a ring burst of +10 px over 300 ms. |
| Ult ring, Overdrive | The level eases 0.2 s toward its target. At full: a white-hot flash (0.2 s), then a glow breathing on a 1.6 s period and a sheen every 2.5 s. The Overdrive meniscus scrolls 12 px/s. |
| Dash lozenge | The refill arc sweeps over the recharge time. On full it pops 1.0 → 1.25 → 1.0 over 150 ms. |
| Buff ring | Drains continuously. The last 2 s blink at 2 Hz (alpha 1 → 0.5). |
| Toast | Slide 24 px and fade over 180 ms, hold 3.0 s, fade 400 ms, reflow 150 ms. A `×N` bump is 1.08 → 1 over 120 ms. |
| Callout | 1.3 → 1.0 over 160 ms (back-out), alpha in 100 ms, hold 1.0 s, rise 12 px and fade over 300 ms. Repeat: 1.1 → 1.0 over 100 ms. |
| Region banner | The rule draws out over 350 ms, tracking 0.30 → 0.08 em over 600 ms, hold 2.1 s, fade 1 s |
| Boss bar | Slides down 300 ms. Phase: the notch shatters, a 2 px shake for 200 ms, the name cross-fades. Death: motes over 600 ms. |
| Edge pins | Critically damped along the edge (about 12 Hz), fade in 150 ms. Downed: the ring pulses on a 0.8 s period. |
| Boon chip | Slides in 24 px from the right over 200 ms. The god glow pulses every 2 s. |
| Boon cards | Rise 40 px, 70 ms apart, over 260 ms (back-out). Medallion flare over 450 ms. Hover lifts 12 px over 120 ms. Pick: a 150 ms flare, the others drop over 200 ms, the icon flies to the Hearth over 400 ms. Godforged: a sheen every 3 s, and the sunburst turns 6°/s. |
| Forge | The drawer slides 40 px from the right and fades over 220 ms. Equip arc 300 ms, fuse 450 ms, reroll flip 250 ms, salvage 350 ms, DPS count 400 ms, error shake 2 px × 3 over 180 ms. |
| Camera framing | The PanelFraming offset eases over 350 ms (cubic out) in and out |
| Damage numbers | Pop 1.4 → 1.0 over 120 ms (crit 1.5), rise 18 px over 0.7 s, fade over the last 0.25 s |
| End screen | Crest 300 ms, title tracking 600 ms, stat count 0.8 s, cards 80 ms apart |

---

## 11. Bevy 0.20 implementation notes

These were checked against `bevy_ui`, `bevy_text` and `bevy_ui_render` 0.20.0-rc.1. **Bevy stays at
`=0.20.0-rc.1`.**

### 11.1 Modules and ownership

| File | Owner | Contents |
|---|---|---|
| `gf_client/src/ui_theme.rs` (new) | K | `tok::*` colours (§3), `Ty` and `ty(Ty) -> (TextFont, LetterSpacing)` (§4.2), `UiFontHandles`, texture handles `UiTex`, sizes and constants (M = 24, region rects) |
| `gf_client/src/ui_kit.rs` (new) | K | Spawn helpers: `quiet_plate`, `gilt_panel(corner, crest)`, `gilt_card(rarity)`, `niche_card(..)`, `ember_knot(width)`, `sun_crest`, `horn_corners`, `slot(shape, size) -> SlotParts { fill, icon, sweep, rim }`, `medallion(kind, size)`, `rarity_gem(rarity, r)`, `keycap(label)`, `pad_stud(pos)`, `button(kind, label, sub)`, `bar(style, w, h) -> BarParts`, `delta_chip(pct)`, `rich_text(spans)`, `outlined_text`; the `HudRects` resource |
| `gf_client/src/ui_fx.rs` (new) + `shaders/ui_molten.wesl` | K | `Ghost`, `Tween`, `Pulse`, `Pop`, `Sweep` components and systems; `MoltenMaterial: UiMaterial`; the `UiScale` system; reduced motion |
| `gf_client/src/icons.rs` (new) + `icon_table.rs` (generated) | K / I | `IconId`, the level builder, `icon(id, px) -> ImageNode` |
| `hud.rs`, `offscreen.rs`, damage-number styling in `vfx.rs` | H | §6 |
| `ui.rs` (+ a small read in `camera.rs`) | P | §7, `PanelFraming` |
| `lib.rs`, `input.rs` (Settings: `debug_strip`, `reduced_motion`, `hud_scale`; F10) | K | `mod` lines and plugin calls only |
| `gf_engine/src/client.rs` | K | **Add only** (never reorder or rename): `install_font_faces(app, &[&'static [u8]]) -> Vec<Handle<Font>>`, and re-exports the UI needs (gradients, `TextureSlicer`, `UiMaterial`, `InlineImage`, `LetterSpacing`, `FontFeatures`, `UiScale`, `AutoDirectionalNavigation`, `TabIndex`, `AutoFocus`) |
| `gf_game` CLI | K | `--ui-shot`, `--hud-off`, `--hud-scale` |

**Hands off:** `scene.rs`, `palette.rs`, `materials.rs`, `models.rs` and `anim.rs` belong to the
model-integration lane. The UI reads colours through `palette::{element_color, rarity_color, hex}`
and never through `poi_kind_color`.

### 11.2 Fonts

```rust
const CINZEL: &[u8] = include_bytes!("../../../assets/fonts/Cinzel-Variable.ttf");
// + AlegreyaSans-{Regular,Medium,Bold,Italic}.ttf, DejaVuSans.ttf, DejaVuSerif-Bold.ttf
let default = gf_engine::client::install_fonts(app, ALEGREYA_MEDIUM, DEJAVU_SERIF_BOLD); // default = body
let [cinzel, reg, med, bold, ital, dv_sans, dv_serif] = /* install_font_faces(...) */;
fn display(px: f32, w: u16) -> TextFont {
    TextFont {
        font: FontSource::List(vec![FontSource::Handle(cinzel), FontSource::Handle(dv_serif)]),
        font_size: FontSize::Px(px),
        weight: FontWeight(w),
        ..default()
    }
}
// + LetterSpacing::Px(px * em) as a component; numerals: font_features = tnum + lnum
```

Legibility: `TextShadow { offset: Vec2::new(0., 2.), color: ink.with_alpha(0.9) }`. There is no
text outline in `bevy_ui` 0.20. The mockups' 1 px ink stroke becomes this shadow, plus the pool or
plate behind the text. The single-instance display texts (callout, region banner, boss name,
VICTORY) also get a real outline: four copies of the text in `ink` at 0.9, offset ±1 px on x and y,
as siblings behind it (`ui_kit::outlined_text`). Never do this for pooled texts such as damage
numbers or labels.

### 11.3 Plates, gradients and shadows

```rust
(Node { border: UiRect::all(px(1.1)), border_radius: BorderRadius::all(px(6.)), ..default() },
 BackgroundGradient(vec![LinearGradient::to_bottom(vec![ColorStop::auto(lac2.with_alpha(0.85)), ColorStop::auto(lac1.with_alpha(0.85))]).into()]),
 BorderGradient(vec![LinearGradient::to_bottom(vec![ColorStop::auto(gold_lt), ColorStop::auto(gold_md), ColorStop::auto(gold_dk)]).into()]),
 BoxShadow(vec![ShadowStyle { color: Color::BLACK.with_alpha(0.55), x_offset: px(0.), y_offset: px(3.), spread_radius: px(0.), blur_radius: px(9.) }]))
```

Corner pools are `RadialGradient` backgrounds on absolute nodes. There is one node per corner, and
it never hit-tests.

### 11.4 Sweeps, rings and fills

- **Cooldown sweep:**
  `BackgroundGradient(vec![ConicGradient::new(UiPosition::CENTER, vec![AngularColorStop::new(dark, 0.), AngularColorStop::new(dark, f * TAU), AngularColorStop::new(Color::NONE, f * TAU), AngularColorStop::new(Color::NONE, TAU)]).with_start(0.).into()])`
  on the sweep child. Angle 0 is 12 o'clock and angles run clockwise (`gradient.wesl`:
  `atan2(-d.x, d.y) + PI`). Use the §8.1 radius rule on chamfers and `BorderRadius::MAX` on rounds.
  Quantise `f` to 1/360 and write only on change.
- **The edge line:** a 1.4×(size/2) child node rotated with `UiTransform.rotation`, pivoting at the
  centre.
- **Ult ring and heat ring:** a trough node (`BorderRadius::MAX`) whose conic background is
  molten stops from 0 to `f`, then `lac0`. The portrait or number node sits on top. The ticks are
  in the medallion texture.
- **Bars:** trough → ghost → fill (`width: Val::Percent`) → shine child → rim. A `Ghost { value,
  hold }` component eases in one system. Write `Node.width` only when |Δ| > 0.001.
- **Shaped bottom-up fills without a shader (the clip-reveal):** a parent node (absolute,
  `bottom: 0`, `height: Percent(fill)`, `overflow: Overflow::clip()`) holds a child `ImageNode` of
  the full slot size anchored at the bottom. Rectangular clipping of a shaped image gives a shaped
  fill. Use it for dash lozenges and as the Overdrive fallback.

### 11.5 `MoltenMaterial` (the Overdrive hex)

- `#[derive(Asset, AsBindGroup, TypePath, Clone)] struct MoltenMaterial { #[uniform(0)] p: Vec4, #[texture(1)] #[sampler(2)] mask: Handle<Image> }`
  - `p` holds (fill, time, ready, active).
  - `impl UiMaterial { fn fragment_shader() -> ShaderRef { "embedded://gf_client/shaders/ui_molten.wesl".into() } }`
  - Add `UiMaterialPlugin::<MoltenMaterial>::default()`, and spawn it with
    `MaterialNode(handle)`.
- **The fragment shader:**
  - reads the mask alpha;
  - builds a wavy level `fill + 0.012 × sin(uv.x × 3π + time × 2.4)`;
  - colours below the level with the molten ramp by height;
  - adds a 1.4 px meniscus line in `#FFFBEA`;
  - above the level, a `#2B1F16 → #0E0907` lacquer;
  - multiplies by the mask.
- Update the uniform only when `fill` moves more than 1/200, plus `time` at 30 Hz while ready.
- Embed it with `embedded_asset!(app, "shaders/ui_molten.wesl")` like the other shaders.

### 11.6 Motion helpers

A generic `Tween { from, to, t, dur, ease, target: TweenTarget::{Scale, Translate, Alpha, Rotation} }`
component, plus one system, drives every pop, slide, lift and flip on `UiTransform` or the node's
colour alpha. `Pulse { hz, lo, hi }` drives breathing glows through `BoxShadow` colour alpha.
Reduced motion clamps `Pulse` and skips the scale and translate tweens.

### 11.7 Inline icons in text

Put keycaps, currency glyphs and delta chevrons inside running text as `InlineImage { image,
color }` children of a `Text`. The box sizes to the image, so use the icon level whose pixel size
matches the text (§9.2).

### 11.8 `HudRects`

`HudRects { rects: SmallVec<[Rect; 12]> }` holds the logical rects of Party, the Toast rail, the
Wayfinder, the Hearth, the Arsenal, the boon chip, the boss bar and the callout band. H fills it
after layout (`PostUpdate`, after `UiSystems::Layout`) from each cluster's `ComputedNode::size()` and
`UiGlobalTransform.translation`, scaled by `inverse_scale_factor()`. The pins, the prompt clamping,
the ally tags and the damage numbers read it. It replaces `offscreen::clear_of_hud`'s hard-coded
table.

### 11.9 Z-order (`GlobalZIndex`)

| Layer | Z |
|---|---|
| World labels, bars, prompts, damage numbers | 1 |
| Edge pins | 5 |
| Corner pools | 8 |
| HUD clusters | 10 |
| Toasts, callouts, banners | 12 |
| Boon chip | 14 |
| Forge drawer, boon spread | 20 |
| End screen | 30 |
| Help | 40 |
| Debug strip | 50 |

### 11.10 Performance rules (and the traps in today's code)

- **Spawn the HUD once, at Startup.** Toasts become a pool of 3 recycled nodes. Keep the pools:
  12 labels, 16 bars, 16 pins, 40 numbers.
- **Write only on change** (`set_if_neq`, or compare first). Quantise:
  - the timer: once per second;
  - cooldown text: 0.1 s steps;
  - sweeps: 1°;
  - bars: 0.001.
- **Forge:** remove `time_left` from `PanelKeys` (§7.1). Hover and selection update in place.
- **`vfx.rs::update_numbers` animates `font_px(n.px * pop)`**, and every distinct size builds a new
  glyph atlas. Use the fixed `Dmg` sizes and animate `UiTransform.scale`.
  `hud::world_labels` sets `font_px(px)` every frame: set the font only when it changes.
- The persistent HUD is ≤ 250 nodes. `UiMaterial` nodes ≤ 2. Distinct UI textures per frame
  ≤ 40.
- `ui_captures` (hovering a button blocks firing) stays as it is.

### 11.11 QA flags and screenshots

- `--ui-shot forge|boon|end|help|kit` (lane P, with `kit` from K) forces a panel open with sample
  data (from the current content) for screenshots. `kit` shows a board of every widget and state
  from `ui_kit`, the in-engine twin of `ui_visual_language_1920.png`. QA only; it is never reachable
  in normal play.
- `--hud-off` (K) hides every UI root node, for clean plates.
- **Acceptance** for each lane:
  - capture 1920×1080 and 1600×900 (`--window`) with `--autoplay --bots 3 --seed 7 --horde 320`
    and `--start-at anvil|shrine|warlord`;
  - compare the shots side by side with the matching mockup;
  - grep the logs for `ERROR`, `panicked` and `wgpu`.

---

## 12. Work split

The lanes run in parallel where they can; the order is at the end. Each lane runs `cargo fmt --all`
and `cargo clippy --workspace --all-targets --release -- -D warnings` before each commit, and
commits only its own paths.

### K: the Rust UI kit, theme and fonts (foundation)

- **Files:** `ui_theme.rs`, `ui_kit.rs`, `ui_fx.rs`, `shaders/ui_molten.wesl`, `icons.rs`, plus the
  `mod` and plugin lines in `lib.rs`, the Settings fields and F10 in `input.rs`, add-only functions
  in `gf_engine/src/client.rs`, and the CLI flags in `gf_game`.
- **Delivers:**
  - the tokens and type ramp (§3, §4);
  - all seven fonts embedded, the default font set to Alegreya Medium, and the `FontSource::List`
    stacks;
  - the UiScale system (§5.1);
  - every `ui_kit` widget (§8.1) with its states (idle, hover, pressed, disabled, selected, focus)
    driven from `Hovered` and `InteractionDisabled`;
  - the slice rule (§8.2), `Tween`, `Pulse` and `Ghost`, `MoltenMaterial`, and the icon levels;
  - `HudRects` (the type; H fills it);
  - an `InputState.panel_pad_capture` flag that `input.rs` honours (P sets it, §7.6);
  - `--ui-shot kit`, `--hud-off` and `--hud-scale`.
- **Also updates:** ARCHITECTURE §7 "Type" (Cinzel and Alegreya Sans, DejaVu as fallback), and the
  README IP-hygiene fonts line (Cinzel and Alegreya Sans, SIL OFL).
- **Done when** `--ui-shot kit` matches `ui_visual_language_1920.png` at 1080p and 900p.

### T: the UI texture kit generator

- **Files:** `tools/ui_art/gen_textures.py` and `tools/ui_art/kit/*.py`. Lift `shade_metal`,
  `lacquer`, `lattice`, `corner_v2_mask`, `crest_img`, `divider`, `niche_poly` and `gem` from
  `docs/art/ui_mockups/src/a/`.
- **Outputs:** every file in §8.2 under `assets/ui/{frames,ornaments,slots,fx}/`, deterministic,
  with the exact sizes and borders; and `tools/ui_art/out/textures_sheet.png`, a contact sheet on
  lacquer and on a game plate.
- **Rules:** @2x, sRGB, straight alpha, no baked text, transparent centres where stated.
  Original shapes only.
- **Done when** each texture on the sheet matches the mockup crops and the 9-slice corners stay
  crisp at 0.5 scale.

### I: the icon generator

- **Files:** `tools/ui_art/gen_icons.py` and `tools/ui_art/glyphs/*.py`. Lift the glyph functions
  from `src/a/gm_icons.py`, `busts.py` and `sigils.py` and from `src/b/icons.py`.
- **Outputs:**
  - every icon in §9.3 as a 128×128 master under `assets/ui/icons/<group>/`;
  - the generated `crates/gf_client/src/icon_table.rs`;
  - `tools/ui_art/out/icons_sheet.png` (all icons at 128 and at 24 px on lacquer, for the
    silhouette test);
  - `tools/ui_art/out/icon_report.txt`.
- **Rule:** reads the content RON keys and **fails** if any part, boon, chassis, character or god
  key lacks an icon.
- **Done when** every content key resolves and every icon passes the 24 px silhouette check on the
  sheet.

### H: the HUD lane

- **Files:** `hud.rs`, `offscreen.rs`, and the damage-number style in `vfx.rs`.
- **Delivers:**
  - §6 in full: the Hearth, the Arsenal, the boon chip, Party, the toast pool, the Wayfinder
    (`MinimapFrame` hook, tracker rows and floor), the boss bar, the callout lane (synergy toasts
    move here), the region banner, surge, the low-HP vignette, prompts and state banners, ally
    tags, elite bars, POI labels, the downed marker, edge pins with `HudRects` avoidance, the debug
    strip and the touch restyle;
  - deletes `fade_arsenal`, the old panels and `Label::Help` (help moves to P).
- **Done when** `--autoplay --bots 3 --horde 320` shots match `ui_hud_fight_1920.png`, and
  `--start-at warlord` shots match `ui_hud_states_1920.png`.

### P: the panels lane

- **Files:** `ui.rs`, the `PanelFraming` read in `camera.rs`, and the panel keys (§7.6).
- **Delivers:**
  - the Forge drawer (§7.1, including the `PanelKeys` fix and `ForgeSelection`);
  - the boon spread and auto-open (§7.2);
  - the end screen, victory and defeat (§7.3);
  - help (§7.4);
  - the door panel and gathering (§7.5);
  - pad focus;
  - `--ui-shot forge|boon|end|help`.
- **Done when** the `--ui-shot` captures match `ui_forge_1920.png`, `ui_boons_1920.png` and
  `ui_end_victory_1920.png`.

### Order and dependencies

1. **T and I start at once.** They need only this page. Each lands a first pass fast, placeholder
   quality allowed, so the files that K embeds with `include_bytes!` exist.
2. **K** lands the theme, fonts and kit (with solid-colour fallbacks until the textures land), then
   switches to the textures and icons.
3. **H and P** start on K's API. They may stub against `ui_kit` signatures agreed in this page.
4. The final polish pass runs after the T and I second passes. Re-capture `docs/media/*.jpg`.

---

## 13. Open items for other owners

- **`palette.rs` (model-integration lane):** move world POI beacons off reserved hues (§3.4). The
  Warlord kind colour should become `#FF7A5A`, not the telegraph red.
- **Content (`game.ron`):** consider P2 `#56C8F5` to separate P2 from Storm (§3.4).
- **`camera.rs`:** P adds one small read for `PanelFraming` (an additive change).
- **Docs to update when K lands:** ARCHITECTURE §7 "Type"; the README IP-hygiene fonts line;
  NEXT_SESSION §4 (the UI notes on `max_corner_scale` for `@2x` slices, the chamfer radius rule and
  the clip-reveal).
