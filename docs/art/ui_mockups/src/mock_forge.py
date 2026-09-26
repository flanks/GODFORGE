"""Final mockup 2: the Forge drawer at a Hot anvil; camera eased so the hero sits left of the drawer."""
import sys
import time

from fin import *  # noqa: F401,F403
import fin as F
import fin_forge as FF

PLATES = sys.argv[1] if len(sys.argv) > 1 else 'plates'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'out'
t0 = time.time()
src = Image.open(f'{PLATES}/anvil_04.png').convert('RGB')
shift = 420     # PanelFraming: the forge-focus camera offset (hero at ~26 % of the width)
bg = Image.new('RGB', src.size)
bg.paste(src.crop((shift, 0, src.width, src.height)), (0, 0))
strip = src.crop((src.width - shift, 0, src.width, src.height)).transpose(Image.FLIP_LEFT_RIGHT).filter(ImageFilter.GaussianBlur(6))
bg.paste(strip, (src.width - shift, 0))
cv = Canvas(bg=bg)
cv.dim(0.18, '#0A0610')
cv.vignette(0.4)
# the drawer side gets its own scrim so the panel never fights the lava
sc = grad_img(int(P(1100)), int(P(1080)), [(0, rgba('#06050A', 0)), (0.35, rgba('#06050A', 0.55)), (1, rgba('#06050A', 0.62))], horizontal=True)
cv.put(sc, P(820), 0)

# world: the anvil's state prompt stays in the world, left of the drawer
H.world_prompt(cv, 520, 452, 'Tab', 'FORGING', 'Anvil · hot for 19 s')
F.ally_tag(cv, 558, 520, 2, 'Bot 2', 0.95)
F.ally_tag(cv, 512, 402, 4, 'Bot 4', 1.0)

F.party(cv, [(2, 'Bot 2', 'Selene', 'bust_selene', 0.95, 'ok', None), (3, 'Bot 3', 'Kael', 'bust_kael', 0.78, 'ok', None),
             (4, 'Bot 4', 'Selene', 'bust_selene', 1.0, 'ok', None)])
F.toast(cv, 214, 'hammer', [('Equipped ', body(17, 'Medium'), 'parch_dim'), ('Ricochet', body(17, 'Bold'), 'epic'),
                            (' · Mechanism', body(17, 'Medium'), 'parch_dim')])
F.hearth(cv, hp=344, hp_max=380, ghost=344, ult=0.9, e_cd=None, od=0.82, buffs=(('a:anvil', 0.76, '19'),))
FF.forge_drawer(cv)
F.save_png(cv, f'{OUT}/ui_forge_1920.png')
print('done', time.time() - t0)
