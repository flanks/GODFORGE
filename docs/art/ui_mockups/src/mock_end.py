"""Final mockup 4: the Victory screen."""
import sys
import time

from fin import *  # noqa: F401,F403
import fin as F

PLATES = sys.argv[1] if len(sys.argv) > 1 else 'plates'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out'
t0 = time.time()
src = Image.open(f'{PLATES}/hordeC_02.png').convert('RGB').filter(ImageFilter.GaussianBlur(5))
cv = Canvas(bg=src)
cv.dim(0.68, '#080508')
cv.vignette(0.7)
cx = RW / 2

# crest: the anvil medallion in a sixteen-ray sunburst
R = 58
d = int(P(R * 2))
cm = circle_mask(d)
X, Y = P(cx) - d / 2, P(122) - d / 2
glow(cv, cm, X, Y, '#FFB23A', blur=P(40), alpha=0.55, spread=P(6))
rays = Image.new('L', (int(P(260)), int(P(260))), 0)
rd = ImageDraw.Draw(rays)
c = rays.width / 2
for i in range(16):
    a = math.radians(i * 22.5 - 90)
    L = P(122) if i % 2 == 0 else P(96)
    rd.polygon([(c + P(60) * math.cos(a - 0.08), c + P(60) * math.sin(a - 0.08)), (c + L * math.cos(a), c + L * math.sin(a)),
                (c + P(60) * math.cos(a + 0.08), c + P(60) * math.sin(a + 0.08))], fill=255)
fill_mask(cv, rays, P(cx) - c, P(122) - c, with_alpha(gold_fill(rays.width, rays.height), 0.9))
fill_mask(cv, cm, X, Y, gold_fill(d, d))
F.studs(cv, cx, 122, R - 3, 8, size=6)
inner = shrink(cm, P(7))
fill_mask(cv, inner, X, Y, radial_img(d, d, '#5A3E27', '#120B08', cy=0.4))
fill_mask(cv, ring_of(inner, max(1, P(1.2))), X, Y, rgba('gold_dk'))
F.a_icon(cv, 'anvil', cx, 120, 76, style='gold', outline=1.4)

draw_text(cv, cx, 300, 'VICTORY', cinzel(96, 900), anchor='m', tracking=0.14,
          grad=[rgba('#FFFBEA'), rgba('#F7CE6A'), rgba('#A86A22')], stroke=1.4, stroke_color='#1A0E06', glow_color='#FFB23A', glow_a=0.4)
F.ember_knot(cv, cx, 330, 660, gem_color='#FFE7A6')
draw_text(cv, cx, 366, 'The Last Arsenal holds. The Slag King is unmade.', body(24, 'Italic'), fill='parch', anchor='m')

stats = [('hourglass', '21:48', 'TIME'), ('skull', '4,812', 'KILLS'), ('seal', '7 / 7', 'SEALS'),
         ('poi_anvil', '11', 'OBJECTIVES'), ('poi_watchfire', '64%', 'EXPLORED'), ('ember', '+312', 'EMBER')]
sw = 196
sx = cx - sw * len(stats) / 2
for i, (ic, val, lab) in enumerate(stats):
    x = sx + i * sw + sw / 2
    place_icon(cv, I.get(ic), x, 416, 34)
    draw_text(cv, x, 464, val, cinzel(30, 800), fill='#FFF6E0', anchor='m')
    draw_text(cv, x, 486, lab, cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.24)
    if i:
        m = Image.new('L', (max(1, int(P(1.2))), int(P(70))), 255)
        fill_mask(cv, m, P(sx + i * sw), P(406),
                  grad_img(m.width, m.height, [(0, rgba('gold_md', 0)), (0.5, rgba('gold_md', 0.8)), (1, rgba('gold_md', 0))]))

party = [(1, 'Forgebearer', 'VALDRIS', 'bust_valdris', 1904, 0.38, ['god_pyra', 'god_zephyros', 'boon_team_forge'],
          [('core', 'stormcore', 'rare'), ('mech', 'ricochet', 'epic'), ('relic', 'doomstack', 'epic'), ('sigil', 'sigil_anvilheart', 'godforged')],
          True),
         (2, 'Bot 2', 'SELENE', 'bust_selene', 1320, 0.27, ['god_zephyros', 'god_zephyros', 'god_nyctia'],
          [('core', 'stormcore', 'epic'), ('mech', 'bounce_fork', 'rare'), ('relic', 'volatile_heart', 'rare'), ('sigil', 'sigil_anvilheart', 'rare')],
          False),
         (3, 'Bot 3', 'KAEL', 'bust_kael', 1011, 0.20, ['god_nyctia', 'god_pyra'],
          [('core', 'voidcore', 'rare'), ('mech', 'multishot', 'common'), ('relic', 'nyctian_eye', 'epic'), ('sigil', 'sigil_anvilheart', 'common')],
          False),
         (4, 'Bot 4', 'SELENE', 'bust_selene', 577, 0.15, ['god_pyra', 'god_pyra', 'god_zephyros'],
          [('core', 'embercore', 'rare'), ('mech', 'ricochet', 'rare'), ('relic', 'vampire', 'common'), ('sigil', 'sigil_anvilheart', 'rare')],
          False)]
cw, ch, gap = 330, 314, 24
px0 = cx - (4 * cw + 3 * gap) / 2
py = 530
for i, (pn, name, char, bust, kills, share, gods, parts, mvp) in enumerate(party):
    x = px0 + i * (cw + gap)
    pc = F.PLAYER[f'p{pn}']
    if mvp:
        glow(cv, rr_mask(P(cw), P(ch), P(10)), P(x), P(py), '#FFB23A', blur=P(18), alpha=0.35, spread=P(2))
    F.gilt_card(cv, x, py, cw, ch, rarity='godforged' if mvp else 'common', r=10, corner=40, gem_color='#FFB82E' if mvp else None)
    band = rr_mask(P(cw - 28), P(4), P(2))
    fill_mask(cv, band, P(x + 14), P(py + 12), rgba(pc))
    F.medallion_disc(cv, x + 56, py + 64, 34, pc, bust, band=3.0, rim=2.6)
    F.pchip(cv, x + 56, py + 98, pn - 1)
    draw_text(cv, x + 104, py + 62, name, body(22, 'Bold'), fill='parch')
    draw_text(cv, x + 104, py + 84, char, cinzel(13, 800), fill=pc, tracking=0.2)
    if mvp:
        H.framed_slot(cv, x + cw - 40, py + 52, 36, 'circle', None, rim_w=1.4, glow_color='#FFC940')
        F.a_icon(cv, 'radiant', x + cw - 40, py + 52, 26, tint='#FFC873', light='#FFFBEA', outline=0.8)
        draw_text(cv, x + cw - 40, py + 88, 'MVP', cinzel(11, 800), fill='gold_lt', anchor='m', tracking=0.2)
    draw_text(cv, x + 24, py + 144, f'{kills:,}', cinzel(26, 800), fill='#FFF6E0')
    draw_text(cv, x + 24, py + 162, 'KILLS', cinzel(11, 800), fill='parch_dim', tracking=0.22)
    draw_text(cv, x + cw - 24, py + 144, f'{int(share * 100)}%', cinzel(26, 800), fill='#FFF6E0', anchor='r')
    draw_text(cv, x + cw - 24, py + 162, 'OF THE DAMAGE', cinzel(11, 800), fill='parch_dim', anchor='r', tracking=0.22)
    bar(cv, x + 24, py + 174, cw - 48, 8, share / 0.4, [(0, mix(pc, '#FFFFFF', 0.3)), (1, rgba(pc))], r=4, rim=0.4, sheen=False)
    draw_text(cv, x + 24, py + 212, 'THE WEAPON', cinzel(11, 800), fill='gold_lt', tracking=0.22)
    H.framed_slot(cv, x + 46, py + 248, 44, 'hexflat', 'colossus_cannon', icon_scale=0.66, rim_w=1.6)
    for j, (k, ic, rar) in enumerate(parts):
        xx = x + 100 + j * 54
        H.framed_slot(cv, xx, py + 248, 40, k, ic, icon_scale=0.62, rim_w=1.3)
        F.rarity_gem(cv, xx, py + 272, 4.2, rar, glow_a=0.5)
    draw_text(cv, x + 24, py + 298, 'BOONS', cinzel(11, 800), fill='gold_lt', tracking=0.22)
    for j, g in enumerate(gods):
        place_icon(cv, I.get(g), x + 100 + j * 30, py + 294, 24)

by = py + ch + 40
PN.button(cv, cx - 280, by, 260, 52, 'FORGE AGAIN', 'primary', key='Enter')
PN.button(cv, cx + 20, by, 260, 52, 'LEAVE', 'secondary', key='Esc')
F.save_png(cv, f'{OUT}/ui_end_victory_1920.png')
print('done', time.time() - t0)
