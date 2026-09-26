"""Final board: the visual language (tokens, type, frames, widgets, states, icon sampler) at 1920x1080."""
import sys
import time

from fin import *  # noqa: F401,F403
import fin as F
from panels import button, delta_chip, card

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
t0 = time.time()
bg = Image.new('RGB', (1920, 1080), (18, 13, 10))
arr = np.asarray(bg).astype(np.float32)
yy = np.linspace(0, 1, 1080)[:, None, None]
arr = arr * (1.15 - 0.35 * yy) + np.random.default_rng(3).normal(0, 2.2, arr.shape)
cv = Canvas(bg=Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))


def label(x, y, t):
    draw_text(cv, x, y, t, cinzel(15, 800), fill='gold_lt', tracking=0.18)


def small(x, y, t, col='parch_dim', anchor='l'):
    draw_text(cv, x, y, t, body(13, 'Medium'), fill=col, anchor=anchor, shadow_a=0.6)


draw_text(cv, 40, 58, 'GODFORGE UI', cinzel(34, 800), tracking=0.14, grad=[rgba('#FFF4D0'), rgba('#F2C667'), rgba('#B07A30')])
draw_text(cv, 400, 56, 'visual language · 1920×1080 logical px · all shapes original to GODFORGE', body(18, 'Italic'), fill='parch_dim')
F.ember_knot(cv, 960, 80, 1840)

# ── colour tokens ──
label(40, 118, 'TOKENS')
groups = [
    ('lac0', '#0B0807'), ('lac1', '#130D0A'), ('lac2', '#2A1E16'), ('lac3', '#4A3624'),
    ('gold_hi', '#FFECB0'), ('gold_lt', '#F2C667'), ('gold_md', '#C9933E'), ('gold_dk', '#7A5424'), ('gold_sh', '#3B2610'),
    ('parch', '#F4E6C8'), ('parch_dim', '#B9A98C'), ('parch_mute', '#7D705E'), ('ink_text', '#1A120B'),
    ('ichor', '#FFE9B0'), ('ichor_glow', '#FFC873'), ('loss', '#A58C86'),
    ('hp_lt', '#E8574C'), ('hp', '#C8323A'), ('hp_dk', '#7E1420'), ('hp_ghost', '#F0B37A'), ('ward', '#DCE6EA'), ('steel', '#9AA4AE'),
    ('molten', '#FFC95A'), ('danger', '#FF3B30'),
]
x, y = 40, 132
for i, (n, hx_) in enumerate(groups):
    sx = x + (i % 12) * 76
    sy = y + (i // 12) * 70
    m = rr_mask(P(40), P(30), P(5))
    fill_mask(cv, m, P(sx), P(sy), rgba(hx_))
    fill_mask(cv, ring_of(m, max(1, P(1))), P(sx), P(sy), rgba('#5A4232'))
    small(sx, sy + 44, n, 'parch')
    small(sx, sy + 58, hx_)
label(960, 118, 'RESERVED HUES — ONLY IN THEIR DOMAIN')
res = [('RARITY', [('common', '#CFC6B4'), ('rare', '#4FA3FF'), ('epic', '#B865FF'), ('godforged', '#FFB82E')]),
       ('ELEMENT', [('kinetic', '#F4E3C1'), ('flame', '#FF7A1A'), ('storm', '#3FD8FF'), ('void', '#A45CFF'), ('plague', '#86E03A'),
                    ('radiant', '#FFE27A')]),
       ('PLAYER', [('P1', '#FFC940'), ('P2', '#3FD8FF'), ('P3', '#B06CFF'), ('P4', '#5BE37D')])]
yy_ = 136
for gname, items in res:
    small(960, yy_ + 18, gname, 'parch')
    for j, (n, hx_) in enumerate(items):
        sx = 1040 + j * 132
        m = circle_mask(int(P(22)))
        fill_mask(cv, m, P(sx), P(yy_), rgba(hx_))
        small(sx + 28, yy_ + 10, n, 'parch')
        small(sx + 28, yy_ + 24, hx_)
    yy_ += 44

# ── type ramp ──
label(40, 300, 'TYPE')
ty = 346
draw_text(cv, 40, ty, 'VICTORY', cinzel(42, 900), tracking=0.14, grad=[rgba('#FFFBEA'), rgba('#F7CE6A'), rgba('#A86A22')])
small(420, ty - 8, 'display_xl · Cinzel 900 · 96 · +14 %  (shown at half size)')
draw_text(cv, 40, ty + 44, 'THE FORGE', cinzel(34, 800), tracking=0.14, grad=[rgba('#FFF4D0'), rgba('#F2C667'), rgba('#B07A30')])
small(420, ty + 36, 'title · Cinzel 800 · 32–36 · +14 %')
draw_text(cv, 40, ty + 80, 'Leaping Arc', cinzel(26, 800), fill='rare', tracking=0.04)
small(420, ty + 72, 'name · Cinzel 800 · 26 · rarity colour')
draw_text(cv, 40, ty + 108, 'THE WEAPON', cinzel(15, 800), fill='gold_lt', tracking=0.18)
small(420, ty + 104, 'label · Cinzel 800 · 15 · +18 %')
draw_text(cv, 40, ty + 132, 'EPIC RELIC · REPLACES', cinzel(12, 800), fill='parch_dim', tracking=0.12)
small(420, ty + 128, 'micro · Cinzel 800 · 12 · +12–24 %')
draw_text(cv, 40, ty + 166, '1,284   07:32', cinzel(30, 800), fill='#FFF8EA')
small(420, ty + 160, 'numeral · Cinzel 800 · 24–38')
draw_text(cv, 40, ty + 196, '307 / 380   412', body(20, 'Bold'), fill='#FFF8EA')
small(420, ty + 192, 'num · Alegreya Sans Bold · 14–28 · tnum')
rich = [('Hits have a ', body(18, 'Medium'), 'parch'), ('25%', body(18, 'Bold'), 'ichor'), (' chance to ', body(18, 'Medium'), 'parch'),
        ('Shock', body(18, 'Bold'), 'storm'), ('.', body(18, 'Medium'), 'parch')]
rich_line(cv, 40, ty + 226, [(t, f_, ('#FFE9B0' if c == 'ichor' else c)) for t, f_, c in rich])
small(420, ty + 222, 'body · Alegreya Sans Medium 18 · numbers ichor · keywords in hue')
draw_text(cv, 40, ty + 254, 'The Chainyard anvil burns hot', body(17, 'Italic'), fill='parch_dim')
small(420, ty + 250, 'flavour · Alegreya Sans Italic 17')

# ── frames and ornament ──
label(780, 300, 'FRAMES & ORNAMENT')
F.ornate_panel(cv, 790, 346, 270, 150, corner=48, r=10)
F.sun_crest(cv, 925, 346, size=40)
small(925, 522, 'ornate panel · forge-horn corners · sun-crest', 'parch', anchor='m')
quiet_plate(cv, 1090, 350, 220, 64, r=6, alpha=0.85, rim=0.8)
draw_text(cv, 1106, 378, 'QUIET PLATE', cinzel(14, 800), fill='gold_lt', tracking=0.14)
small(1106, 400, 'combat HUD · 1.1 px gold rim')
F.ember_knot(cv, 1200, 450, 220, gem_color='#FFE7A6')
small(1200, 474, 'ember-knot divider', 'parch', anchor='m')
xk = 800
for k in ('Q', 'Tab', 'LMB', 'Esc'):
    xk += keycap(cv, xk, 568, k, h=22) + 10
for pos in ('south', 'east', 'west', 'north'):
    F.pad_stud(cv, xk + 8, 568, pos, r=11)
    xk += 30
small(800, 594, 'keycaps · pad studs by position (no colours, no letters)')

# ── slots, gems, states ──
label(1350, 300, 'SLOT SHAPE = CATEGORY')
shapes = [('core', 'stormcore', 'CORE'), ('mech', 'ricochet', 'MECH'), ('relic', 'nyctian_eye', 'RELIC'), ('sigil', 'sigil_anvilheart', 'SIGIL'),
          ('ability', 'bulwark_slam', 'ABILITY'), ('hex', 'overdrive', 'OVERDRIVE'), ('hexflat', 'colossus_cannon', 'CHASSIS')]
for i, (k, ic, n) in enumerate(shapes):
    sx = 1380 + i * 76
    H.framed_slot(cv, sx, 370, 56, k, ic, icon_scale=0.66, rim_w=1.6)
    small(sx, 416, n, 'parch', anchor='m')
label(1350, 452, 'RARITY GEM CUT')
for i, r in enumerate(('common', 'rare', 'epic', 'godforged')):
    sx = 1380 + i * 128
    F.rarity_gem(cv, sx, 488, 9, r, glow_a=0.6)
    small(sx + 18, 494, r.upper(), r)

# ── ability states / buttons / bars ──
label(40, 640, 'STATES')
H.framed_slot(cv, 80, 700, 60, 'ability', 'siege_stance', icon_scale=0.74, glow_color='#FFC24A')
small(80, 750, 'ready', 'parch', anchor='m')
H.framed_slot(cv, 160, 700, 60, 'ability', 'siege_stance', icon_scale=0.74, state='cooldown', frac_cd=0.42, cd_text='3.4')
small(160, 750, 'cooling', 'parch', anchor='m')
H.framed_slot(cv, 240, 700, 60, 'ability', 'siege_stance', icon_scale=0.74, state='disabled')
small(240, 750, 'disabled', 'parch', anchor='m')
button(cv, 300, 672, 200, 46, 'EQUIP', 'primary', chip=lambda xx, yy_: delta_chip(cv, xx, yy_, 24, size=17, ink=True))
button(cv, 300, 726, 200, 40, 'SALVAGE', 'secondary')
button(cv, 300, 774, 200, 40, 'FUSE', 'disabled', chip=lambda xx, yy_: draw_text(cv, xx, yy_ - 1, 'no twin', body(15, 'Italic'),
                                                                                    fill='parch_mute', anchor='r'))
delta_chip(cv, 560, 700, 24, anchor='l', size=18)
delta_chip(cv, 560, 730, -6, anchor='l', size=18)
delta_chip(cv, 560, 760, 0, anchor='l', size=18)
small(560, 784, 'deltas: value + chevron, never green/red')
card(cv, 700, 660, 150, 70, 'epic', selected=True)
draw_text(cv, 716, 700, 'selected', body(16, 'Bold'), fill='parch')
small(775, 752, 'selected: 2.2 px metal ring + glow', 'parch', anchor='m')

label(880, 640, 'BARS & METERS')
bar(cv, 880, 668, 300, 22, 0.62, [(0, 'hp_lt'), (0.5, 'hp'), (1, 'hp_dk')], ghost=0.8, r=4, rim=0.9)
small(1192, 684, 'HP + ghost')
bar(cv, 880, 704, 300, 22, 0.55, [(0, 'hp_lt'), (0.5, 'hp'), (1, 'hp_dk')], r=4, rim=0.9)
hatch = Image.new('L', (int(P(300)), int(P(22))), 0)
hd = ImageDraw.Draw(hatch)
for xx in range(-int(P(22)), hatch.width, int(P(5))):
    hd.line([(xx, hatch.height), (xx + hatch.height, 0)], fill=255, width=max(1, int(P(1.6))))
clip = Image.new('L', hatch.size, 0)
ImageDraw.Draw(clip).rectangle([P(300) * 0.55, P(2), P(300) * 0.78, P(20)], fill=255)
fill_mask(cv, ImageChops.multiply(hatch, clip), P(880), P(704), rgba('ward', 0.9))
small(1192, 720, 'ward hatch')
for i in range(6):
    sw_ = (230 - 15) / 6
    sx = 880 + i * (sw_ + 3)
    m = poly_mask(P(sw_), P(9), [(P(3), 0), (P(sw_), 0), (P(sw_) - P(3), P(9) - 1), (0, P(9) - 1)])
    fill_mask(cv, m, P(sx), P(744), grad_img(m.width, m.height, [(0, '#EEF2F5'), (0.5, 'steel'), (1, 'steel_dk')]) if i < 4 else rgba('#1A1512'))
for i in range(3):
    gem_at(cv, 1120 + i * 26, 748, 7.2, '#FFE7A6' if i < 2 else '#2A1F18', facet=i < 2, glow_a=0.5 if i < 2 else 0)
small(1192, 754, 'armour · dash')
bar(cv, 880, 778, 300, 14, 0.58, [(0, '#FF7A4A'), (0.45, '#C8261E'), (1, '#5E0A08')], ghost=0.66, ghost_color='#F7C98A', r=3, rim=0.8,
    ticks=[0.33, 0.66])
small(1192, 790, 'boss · notches')

label(1360, 640, 'WORLD & MARKERS')
F.dmg(cv, 1390, 700, 31)
F.dmg(cv, 1450, 700, 44, color='storm')
F.dmg(cv, 1520, 700, 412, 'crit')
small(1372, 726, 'kinetic · element · crit (+spark)')
F.edge_pin(cv, 1392, 780, 'anvil', 'gold', '', '', 270)
F.edge_pin(cv, 1452, 780, 'shrine', 'gold', '', '', 270, tint='#FFC23D')
F.edge_pin(cv, 1512, 780, 'skull', 'danger', '', '', 270, tint='#FFFFFF', pulse=True)
small(1548, 786, 'POI · shrine · downed ally (only red-white)')
F.ally_tag(cv, 1780, 712, 3, 'Bot 3 · Kael', 0.46, show_name=True)

# ── icon sampler ──
label(40, 856, 'ICONS — SILHOUETTE FIRST · IVORY TO CATEGORY TINT · INK OUTLINE')
row1 = [('kinetic', '#F4E3C1'), ('flame', '#FF7A1A'), ('storm', '#3FD8FF'), ('void', '#A45CFF'), ('plague', '#86E03A'), ('radiant', '#FFE27A'),
        ('burn', '#FF7A1A'), ('shock', '#3FD8FF'), ('curse', '#A45CFF'), ('root', '#86E03A'), ('bleed', '#E6CFA0'), ('mark', '#E6CFA0'),
        ('anvil', '#E6CFA0'), ('warlord', '#FF7A5A'), ('lair', '#E6CFA0'), ('shrine', '#FFC23D'), ('reliquary', '#E6CFA0'),
        ('vein', '#E6CFA0'), ('spring', '#E6CFA0'), ('watchfire', '#E6CFA0'), ('gate', '#E6CFA0'),
        ('godshard', '#E6CFA0'), ('ember', '#FFB347'), ('seal', '#D9B56C')]
for i, (g, t) in enumerate(row1):
    F.a_icon(cv, g, 64 + i * 76, 912, 46, tint=t, light=mix(t, '#FFFFFF', 0.6), outline=1.3)
    small(64 + i * 76, 948, g, 'parch_dim', anchor='m')
row2 = [('pyra', '#E0312B'), ('zephyros', '#3FD8FF'), ('nyctia', '#7B3FE0'), ('aeon', '#C9D2DC'), ('gaiaa', '#4E9A3A'), ('morwenn', '#1FA39A'),
        ('seraphel', '#FFD86B'), ('umbra_rex', '#8E1B1B'), ('bust_valdris', '#B08A52'), ('bust_selene', '#B08A52'), ('bust_kael', '#B08A52'),
        ('bulwark_slam', '#D9B56C'), ('siege_stance', '#D9B56C'), ('mountainfall', '#D9B56C'), ('cannon', '#D9B56C'), ('crucible', '#D9B56C'),
        ('aim_auto', '#D9B56C'), ('aim_assisted', '#D9B56C'), ('aim_manual', '#D9B56C'), ('reroll', '#D9B56C'), ('fuse', '#D9B56C'),
        ('salvage', '#D9B56C'), ('lock', '#D9B56C'), ('skull', '#E6CFA0')]
for i, (g, t) in enumerate(row2):
    F.a_icon(cv, g, 64 + i * 76, 996, 46, tint=t, light=mix(t, '#FFFFFF', 0.6), outline=1.3)
    small(64 + i * 76, 1032, g.replace('bust_', ''), 'parch_dim', anchor='m')
F.save_png(cv, f'{OUT}/ui_visual_language_1920.png')
print('done', time.time() - t0)
