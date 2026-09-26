"""Final mockup 3: the boon spread (opened from the chip with Tab); hero framed low, world dimmed around a spotlight."""
import sys
import time

from fin import *  # noqa: F401,F403
import fin as F
import fin_boon as FB
import boons as BN

PLATES = sys.argv[1] if len(sys.argv) > 1 else 'plates'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out'
t0 = time.time()
src = Image.open(f'{PLATES}/shrine_00.png').convert('RGB')
shift = 200     # PanelFraming: the camera eases so the hero sits at ~70 % of the height
bg = Image.new('RGB', src.size)
bg.paste(src.crop((0, 0, src.width, src.height - shift)), (0, shift))
top = src.crop((0, 0, src.width, shift)).transpose(Image.FLIP_TOP_BOTTOM).filter(ImageFilter.GaussianBlur(6))
bg.paste(top, (0, 0))
cv = Canvas(bg=bg)
hero = (960, 541 + shift)
BN.spotlight_dim(cv, hero[0], hero[1] - 20, 170, a=0.64)

F.party(cv, [(2, 'Bot 2', 'Selene', 'bust_selene', 0.95, 'ok', None), (3, 'Bot 3', 'Kael', 'bust_kael', 0.7, 'ok', None),
             (4, 'Bot 4', 'Selene', 'bust_selene', 1.0, 'ok', 'ult')])
F.hearth(cv, hp=301, hp_max=380, ghost=301, ult=1.0, e_cd=(1.2, 0.2), od=0.4)
HC.arsenal(cv, shards=46, ember=69)

cx = RW / 2
title = 'ZEPHYROS ANSWERS'
f = cinzel(32, 800)
draw_text(cv, cx, 58, title, f, anchor='m', tracking=0.14, grad=[rgba('#FFFFFF'), rgba('#BDF2FF'), rgba('#3FD8FF')], stroke=0.8,
          stroke_color='#06141A', glow_color='#3FD8FF', glow_a=0.35)
tw = text_w(title, f, 0.14)
F.ember_knot(cv, cx, 76, tw + 160, gem_color='#3FD8FF')
draw_text(cv, cx, 102, 'Shrine of Zephyros  ·  choose one', body(17, 'Italic'), fill='parch_dim', anchor='m')

w, gap = 300, 34
x0 = (RW - (3 * w + 2 * gap)) / 2
y0 = 150
FB.place_card(cv, x0, y0, ['zephyros'], 'Stormbrand', 'common', 'Standard',
              '[+15%] damage; hits have a [25%] chance to [Shock.]', '1', I.get('boon_stormbrand'), tag='NEW')
FB.place_card(cv, x0 + w + gap, y0 - 12, ['zephyros'], 'Leaping Arc', 'rare', 'Standard',
              'Hits arc to [2] more enemies; each jump deals [half] the damage of the last.', '2', I.get('boon_leaping_arc'),
              tag='UPGRADE', level=(2, 3), hover=True)
FB.place_card(cv, x0 + 2 * (w + gap), y0, ['zephyros', 'nyctia'], 'Silent Thunder', 'epic', 'Duo',
              '[+12%] crit chance; [+30%] damage to [Shocked] enemies.', '3', I.get('boon_silent_thunder'), tag='NEW')

by = y0 + 420 + 30
PN.button(cv, x0 + 20, by, 236, 46, 'REROLL', 'secondary', key='X', icon='dice',
          chip=lambda xx, yy: draw_text(cv, xx, yy - 1, '1 left', body(15, 'Italic'), fill='parch_dim', anchor='r'))
PN.button(cv, x0 + 3 * w + 2 * gap - 256, by, 236, 46, 'LATER', 'secondary', key='Tab',
          chip=lambda xx, yy: draw_text(cv, xx, yy - 1, '+1 queued', body(15, 'Italic'), fill=ICHOR, anchor='r'))
F.save_png(cv, f'{OUT}/ui_boons_1920.png')
print('done', time.time() - t0)
