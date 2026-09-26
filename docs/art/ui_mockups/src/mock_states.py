"""Final mockup 5: HUD states — Warlord bar, Team Overdrive ready, a downed ally, a surge from the east, low HP."""
import sys
import time

from fin import *  # noqa: F401,F403
import fin as F
import boss as BS

PLATES = sys.argv[1] if len(sys.argv) > 1 else 'plates'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out'
t0 = time.time()
cv = Canvas(f'{PLATES}/warlord_02.png')

# low HP (< 25 %): danger vignette pulse at the screen edges (red is legitimate here)
w, h = cv.img.size
v = radial_img(w // 6, h // 6, rgba('#FF3B30', 0), rgba('#B0141A', 0.34), rx=0.78, ry=0.78, power=2.6)
cv.img.alpha_composite(v.resize((w, h), Image.BILINEAR))
BS.surge_flash(cv, 'right', 'SURGE', 'from the east')

# world: a hold prompt at the arch watchfire (world-anchored plate, tail down, hold ring round the key)
H.world_prompt(cv, 1140, 318, 'F', 'LIGHT THE WATCHFIRE', 'Watchfire · reveals 80 m', hold=0.45)

# off-screen: the downed ally — the only red-white marker — pulses at the edge
F.edge_pin(cv, 40, 800, 'skull', 'danger', '', '', 225, tint='#FFFFFF', pulse=True)
F.pin_label(cv, 70, 796, 'Bot 3 · revive · 12 s', '34 m', anchor='l')
F.edge_pin(cv, 40, 620, 'anvil', 'gold', '', '', 270)
F.pin_label(cv, 70, 616, 'Anvil', '88 m', anchor='l')

F.party(cv, [(2, 'Bot 2', 'Selene', 'bust_selene', 0.64, 'ok', None), (3, 'Bot 3', 'Kael', 'bust_kael', 0.0, 'downed', 0.6),
             (4, 'Bot 4', 'Selene', 'bust_selene', 0.88, 'ok', None)])
F.toast(cv, 214, 'skull', [('Bot 3', body(17, 'Bold'), 'p3'), (' went down · ', body(17, 'Medium'), 'parch_dim'),
                           ('revive within 12 s', body(17, 'Bold'), 'parch')])
F.toast(cv, 246, 'seal', [('Seal 4 of 7', body(17, 'Bold'), 'gold_lt'), (' · Lair of the Chainyard', body(17, 'Medium'), 'parch_dim')], a=0.7)

# boss bar (top-centre band, only while a boss or the Warlord is engaged)
BS.boss_bar(cv, 'THE BELLOWS', 'II', 'Blaze', 0.58, 0.66, [0.66, 0.33], y=24, w=620, kind='WARLORD')
# callouts drop to y 190 while the boss bar is up
F.callout(cv, RW / 2, 206, 'TEAM OVERDRIVE READY', stops=('#FFFBEA', '#FFD36B', '#FFB23A'))
keycap(cv, RW / 2 + text_w('TEAM OVERDRIVE READY', cinzel(38, 900), 0.06) / 2 + 30, 194, 'V', h=24)

F.wayfinder(cv, map_img=None, minimap=False, seals=4, req=7, timer='11:04', threat=4, warlord='engaged', event=None,
            surge=('EAST', 11, 0.73), objectives=(('poi_gate', 'Boss Gate', 20, 61),))
F.hearth(cv, hp=84, hp_max=380, ghost=150, armor=0, armor_max=6, dash=1, dash_max=2, ult=0.34, q_cd=(6.2, 0.7), e_cd=None, od=1.0,
         aim='MANUAL', aim_note='Deadeye +14%', buffs=())
HC.arsenal(cv, shards=71, ember=118)
F.save_png(cv, f'{OUT}/ui_hud_states_1920.png')
print('done', time.time() - t0)
