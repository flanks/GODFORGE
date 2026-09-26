"""Final mockup 1: the combat HUD in a 4-player fight at an anvil (~200 enemies on screen)."""
import os
import sys
import time

from fin import *  # noqa: F401,F403
import fin as F
from mapclean import clean_map

PLATES = sys.argv[1] if len(sys.argv) > 1 else 'plates'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out'
t0 = time.time()
cv = Canvas(f'{PLATES}/hordeC_02.png')

# ── world-anchored layer (under the HUD) ──
F.ally_tag(cv, 1048, 574, 2, 'Bot 2', 172 / 190)
F.ally_tag(cv, 1082, 592, 4, 'Bot 4', 174 / 190)
F.ally_tag(cv, 1029, 692, 3, 'Bot 3 · Kael', 0.46, show_name=True)
for (x, y, n, k, c) in [(708, 486, 31, 'normal', None), (732, 574, 27, 'normal', None), (790, 452, 412, 'crit', None),
                        (760, 742, 29, 'normal', None), (1310, 452, 44, 'normal', 'storm'), (1352, 494, 38, 'normal', 'storm')]:
    F.dmg(cv, x, y, n, k, color=c)

# ── off-screen pins (edge band, 40 px inset, clear of the HUD clusters) ──
F.edge_pin(cv, 40, 470, 'shrine', 'gold', '', '', 270, tint='#FFC23D')
F.pin_label(cv, 70, 466, 'Shrine of Pyra', '58 m', anchor='l')
F.edge_pin(cv, 1010, 40, 'gate', 'gold', '', '', 0, tint='#B9A98C')
F.pin_label(cv, 1040, 38, 'Boss Gate', '203 m', anchor='l')
F.edge_pin(cv, 1330, 1040, 'reliquary', 'gold', '', '', 180)
F.pin_label(cv, 1360, 1036, 'Reliquary', '96 m', anchor='l')

# ── corner clusters ──
F.party(cv, [(2, 'Bot 2', 'Selene', 'bust_selene', 172 / 190, 'ok', 'ult'), (3, 'Bot 3', 'Kael', 'bust_kael', 0.46, 'ok', None),
             (4, 'Bot 4', 'Selene', 'bust_selene', 174 / 190, 'ok', None)])
F.toast(cv, 214, None, [('Bot 2', body(17, 'Bold'), 'p2'), (' took ', body(17, 'Medium'), 'parch_dim'),
                        ('Tailwind', body(17, 'Bold'), 'rare')], a_glyph=('zephyros', '#3FD8FF'))
F.toast(cv, 246, 'seal', [('Seal claimed', body(17, 'Bold'), 'gold_lt'), (' · Lair of Ingot Row', body(17, 'Medium'), 'parch_dim')], a=0.7)

# the phase-3 minimap look: a map preview folded to sepia ink (optional; the frame renders empty without it)
MAP = os.environ.get('GF_MAP_PREVIEW', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'shots',
                                                    'p2fix_map_run7.png'))
mapimg = sepia_map(clean_map(Image.open(MAP).convert('RGB').crop((350, 200, 650, 390))), 0.7) if os.path.exists(MAP) else None


def dots(x0, y0):
    for (mx, my, col, big) in [(x0 + 132, y0 + 94, 'p2', False), (x0 + 128, y0 + 102, 'p3', False), (x0 + 140, y0 + 100, 'p4', False),
                               (x0 + 138, y0 + 92, 'p1', True)]:
        r = 5.8 if big else 3.8
        m = circle_mask(int(P(r * 2)))
        shadow(cv, m, P(mx - r), P(my - r), blur=P(1.5), off=(0, 0), alpha=0.95)
        fill_mask(cv, m, P(mx - r), P(my - r), rgba(col))
    for (g, dx, dy, s, t) in [('anvil', 150, 84, 20, '#E6CFA0'), ('vein', 214, 64, 18, '#E6CFA0'), ('warlord', 206, 140, 20, '#FF7A5A'),
                              ('shrine', 58, 112, 18, '#FFC23D'), ('gate', 250, 30, 18, '#B9A98C')]:
        F.a_icon(cv, g, x0 + dx, y0 + dy, s, tint=t, light=mix(t, '#FFFFFF', 0.6), outline=1.0)


F.wayfinder(cv, map_img=mapimg, seals=3, req=7, timer='07:32', threat=3, event=('poi_anvil', 'ANVIL · KINDLING', 0.92),
            map_dots=dots)
F.callout(cv, RW / 2, 150, 'RAILSHOCK', count=6, stops=('#FFF8E6', '#F4E3C1', '#3FD8FF'), elems=('el_kinetic', 'el_storm'))
F.boon_chip(cv, 'pyra', waiting=1)
F.hearth(cv, hp=307, hp_max=380, ghost=338, armor=4, armor_max=6, dash=2, dash_max=3, ult=0.67, q_cd=None, e_cd=(3.4, 0.42),
         od=0.96, bust='bust_valdris')
HC.arsenal(cv, shards=30, ember=74)
F.save_png(cv, f'{OUT}/ui_hud_fight_1920.png')
print('done', time.time() - t0)
