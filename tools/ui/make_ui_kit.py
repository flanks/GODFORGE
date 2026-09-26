"""GODFORGE UI texture kit generator (lane T of docs/art/UI_STYLE.md, §8).

Renders every texture of UI_STYLE §8.2 (plus the extras the HUD and panel lanes asked for) to
assets/ui/{frames,ornaments,slots,fx,bars,markers}/, writes the manifest assets/ui/ui_kit.json
(file, size, logical size, 9-slice insets, image mode, tint, intended use) and draws the contact
sheet docs/art/ui_mockups/kit_sheet.png.

    python tools/ui/make_ui_kit.py            # everything (parallel)
    python tools/ui/make_ui_kit.py --only niche --no-sheet
    python tools/ui/make_ui_kit.py --sheet-only

Needs Python 3.10+, Pillow, numpy and scipy. Output is deterministic (seeded noise, no
timestamps). Everything is @2x: 2 texture px per logical px. Slice borders in the manifest are in
texture px; use them with `max_corner_scale: 0.5` (§8.2). All art is original to GODFORGE.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "assets", "ui")
SHEET = os.path.join(ROOT, "docs", "art", "ui_mockups", "kit_sheet.png")
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True   # no __pycache__ in tools/ or docs/ (the sheet imports the mockup glyphs)

from kit import slots as _slots  # noqa: E402

RARITIES = ("common", "rare", "epic", "godforged")
CORNERS = ("tl", "tr", "bl", "br")


def E(path, fn, args=(), kwargs=None, logical=None, mode="stretch", slice_px=None, use="", spec=True, **meta):
    """One texture: `fn` is 'module.function' in kit/, called with args/kwargs, returning a PIL image."""
    d = {"file": path, "fn": fn, "args": list(args), "kwargs": kwargs or {}, "logical": list(logical), "mode": mode,
         "use": use, "spec": spec}
    if slice_px is not None:
        d["slice"] = dict(zip(("left", "top", "right", "bottom"), slice_px))
    d.update(meta)
    return d


def registry():
    R = []
    # ── frames ──
    R.append(E("frames/gilt_panel@2x.png", "frames.gilt_panel", logical=(96, 96), mode="nine_slice",
               slice_px=(48, 48, 48, 48), use="Premium panel frame (Forge drawer, help, detail card, door panel) over a "
               "code lacquer body with border_radius 10. Centre clear. Min node 96x96 logical."))
    R.append(E("frames/gilt_panel_bronze@2x.png", "frames.gilt_panel", kwargs={"bronze": True}, logical=(96, 96),
               mode="nine_slice", slice_px=(48, 48, 48, 48), spec=False,
               use="Bronze panel frame: the non-MVP end-screen party cards (§7.3)."))
    for r in RARITIES:
        R.append(E(f"frames/gilt_card_{r}@2x.png", "frames.gilt_card", args=(r,), logical=(48, 48), mode="nine_slice",
                   slice_px=(24, 24, 24, 24), use=f"{r.capitalize()} rarity card rim (sockets, bag cards), r 8, over a "
                   "code body with the rarity top wash. Min node 48x48 logical."))
    R.append(E("frames/card_selected@2x.png", "frames.card_selected", logical=(56, 56), mode="nine_slice",
               slice_px=(28, 28, 28, 28), use="Selection ring: a node 5 px larger than the card on every side (ring "
               "radius 13). Add the ready_glow BoxShadow and the 2 px lift in code."))
    for kind in ("primary", "secondary", "disabled"):
        R.append(E(f"frames/button_{kind}@2x.png", "frames.button", args=(kind, "normal"), logical=(64, 48),
                   mode="nine_slice", slice_px=(32, 32, 32, 32), use=f"{kind.capitalize()} button, chamfer 9. Label is "
                   "text (primary: ink_text; secondary: parch)."))
    for kind in ("primary", "secondary"):
        for st in ("hover", "pressed"):
            R.append(E(f"frames/button_{kind}_{st}@2x.png", "frames.button", args=(kind, st), logical=(64, 48),
                       mode="nine_slice", slice_px=(32, 32, 32, 32), spec=False,
                       use=f"{kind.capitalize()} button, {st} state (swap the image on Hovered / Pressed)."))
    R.append(E("frames/keycap@2x.png", "frames.keycap", logical=(24, 24), mode="nine_slice", slice_px=(16, 16, 16, 16),
               use="Keyboard keycap (20-30 tall). Centre the label 1.5 px above the node centre (the lip is 3 px).",
               content_offset_y=-1.5))
    R.append(E("frames/keycap_pressed@2x.png", "frames.keycap", kwargs={"pressed": True}, logical=(24, 24),
               mode="nine_slice", slice_px=(16, 16, 16, 16), spec=False,
               use="Keycap while its key is held (hold prompts).", content_offset_y=0.4))
    R.append(E("frames/pill@2x.png", "frames.pill", logical=(32, 18), mode="nine_slice", slice_px=(18, 18, 18, 18),
               use="Gold pill: kind pills (Duo / Legendary / Team), the REPLACE tab. Text in ink_text."))
    R.append(E("frames/pill_outline@2x.png", "frames.pill", kwargs={"outline": True}, logical=(32, 18),
               mode="nine_slice", slice_px=(18, 18, 18, 18), spec=False, use="Lacquer pill with a soft gold rim: "
               "the Forge bag filter chips (ALL / CORE / MECH / RELIC)."))
    for st in ("normal", "hover", "disabled"):
        R.append(E(f"frames/chip{'' if st == 'normal' else '_' + st}@2x.png", "frames.chip", args=(st,),
                   logical=(32, 26), mode="nine_slice", slice_px=(16, 16, 16, 16), spec=False,
                   use=f"Small chamfer-6 chip, 26 tall ({st}): the socket REROLL chip, small actions."))
    for m in ("gilt", "bronze"):
        R.append(E(f"frames/ribbon_{m}@2x.png", "frames.ribbon", args=(m,), logical=(32, 22), mode="nine_slice",
                   slice_px=(16, 16, 16, 16), spec=False,
                   use=f"The 22-tall rarity ribbon plaque on boon cards ({m}; bronze for Common)."))
    R.append(E("frames/pchip@2x.png", "frames.pchip", logical=(30, 18), mode="fixed", spec=False,
               use="The P chip plaque under ally medallions; `P2`..`P4` is text in the player colour."))
    R.append(E("frames/tooltip@2x.png", "frames.tooltip", logical=(48, 48), mode="nine_slice",
               slice_px=(32, 32, 32, 32), spec=False, use="Light gilt frame for hover tooltips (the Arsenal "
               "tooltip card) over a code lacquer body, r 6. Min node 48x48."))
    R.append(E("frames/dashed_outline@2x.png", "frames.dashed_outline", logical=(45, 45), mode="nine_slice",
               slice_px=(30, 30, 30, 30), spec=False, sides="tile", tile_logical=15,
               use="The ONE PART AWAY dashed outline (1.6 px, 9 on / 6 off), white: tint `ichor`. Sides TILE "
               "(SliceScaleMode::Tile, one dash per 15 px tile); r 6."))
    R.append(E("frames/minimap_frame@2x.png", "frames.minimap_frame", logical=(286, 182), mode="fixed", spec=False,
               use="MinimapFrame (phase-3 hook): place at (1613, 21) so the 280x176 frame lands at (1616, 24). Rim, "
               "inner line, 30 px horns and the north gem baked; MinimapContent is inset 3 inside the frame.",
               anchor={"frame_rect_logical": [3, 3, 280, 176]}))
    for r in RARITIES:
        R.append(E(f"frames/niche_frame_{r}@2x.png", "frames.niche_frame", args=(r,), logical=(300, 420),
                   use=f"Boon card frame ({r}): rim, keyline, foot horns. Springer gems are nodes at (0, 112) and "
                   "(300, 112)."))
    R.append(E("frames/niche_body@2x.png", "frames.niche_body", logical=(300, 420), tint="god colour (multiply)",
               use="Boon card body: greyscale lacquer + lattice in the niche shape; ImageNode.color = god colour."))
    R.append(E("frames/niche_hairline@2x.png", "frames.niche_hairline", logical=(300, 420), tint="god colour",
               use="Enamel hairline at inset 6.2-7.8, tinted by the god colour (Duo: two nodes clipped to halves)."))
    R.append(E("frames/niche_glow@2x.png", "frames.niche_glow", logical=(300, 420), tint="god colour at ~0.4",
               use="Light pooling under the arch from the apex medallion; tint god colour, alpha ~0.4."))
    # ── ornaments ──
    R.append(E("ornaments/forgehorn@2x.png", "ornaments.forgehorn_texture", args=(128.0, "tl"), logical=(128, 128),
               use="Master top-left forge-horn (stretch to 30/44/60/76; flip for other corners). The panel corner "
               "sits 10 % in; the gem node (19 % of the size) centres at 18.3 % in. Prefer the sized variants.",
               anchor={"panel_corner_frac": 0.1, "gem_centre_frac": 0.1833, "gem_size_frac": 0.19}))
    for s in (30, 40, 44, 60, 64, 76):
        for c in CORNERS:
            R.append(E(f"ornaments/forgehorn_{s}_{c}@2x.png", "ornaments.forgehorn_texture", args=(float(s), c),
                       kwargs={"gem": "#FFB82E"}, logical=(s, s), mode="fixed", spec=False,
                       use=f"Forge-horn {s} px, {c} corner, lit and shadowed for that corner, amber gem baked. "
                       f"The panel corner sits {s * 0.1:g} px in from the texture's outer corner.",
                       anchor={"panel_corner_inset_logical": s * 0.1, "corner": c}))
    for c in CORNERS:
        R.append(E(f"ornaments/forgehorn_bronze_40_{c}@2x.png", "ornaments.forgehorn_texture", args=(40.0, c),
                   kwargs={"gem": "#FFB82E", "stops": "BRONZE"}, logical=(40, 40), mode="fixed", spec=False,
                   use=f"Bronze forge-horn 40 px, {c} corner: non-MVP end-screen cards.",
                   anchor={"panel_corner_inset_logical": 4.0, "corner": c}))
    R.append(E("ornaments/suncrest@2x.png", "ornaments.suncrest", args=(80.0,), logical=(208, 80),
               use="Sun-crest (aspect 2.6:1). Centre it on a panel's top edge with 62 % of its height above the "
               "edge. Prefer the sized variants.", anchor={"boss_centre_frac_y": 0.62}))
    for h in (62, 50):
        R.append(E(f"ornaments/suncrest_{h}@2x.png", "ornaments.suncrest", args=(float(h),),
                   logical=(round(h * 2.6 * 2) / 2, h), mode="fixed", spec=False,
                   use=f"Sun-crest drawn for {h} px tall ({'Forge drawer, help' if h == 62 else 'Legendary boon medallion'}).",
                   anchor={"boss_centre_frac_y": 0.62}))
    R.append(E("ornaments/emberknot_rule@2x.png", "ornaments.emberknot_rule", logical=(256, 14), mode="three_slice_h",
               slice_px=(0, 0, 32, 0), use="Ember-knot half-rule: the left 480 px stretch, the right 32 px is the "
               "point. Its left end meets the knot; flip_x for the left half."))
    R.append(E("ornaments/emberknot_knot@2x.png", "ornaments.emberknot_knot", logical=(56, 14), mode="fixed",
               use="Ember-knot centre: twin curls and the lozenge setting; the gem node (~9 px) centres at (28, 7)."))
    R.append(E("ornaments/finial_leaf@2x.png", "ornaments.finial_leaf", logical=(22, 22), mode="fixed",
               use="HP bar end cap at x 526 (the bar end tucks under the collar, x 0-5)."))
    R.append(E("ornaments/finial_lozenge@2x.png", "ornaments.finial_lozenge", logical=(10, 10), mode="fixed",
               use="Gilt rail end (x 550)."))
    R.append(E("ornaments/boss_horn@2x.png", "ornaments.boss_horn", logical=(34, 30), mode="fixed",
               use="Boss / Warlord bar left end (flip_x for the right). The collar clasps the bar end at x 26-34."))
    R.append(E("ornaments/sunburst16@2x.png", "ornaments.sunburst16", logical=(260, 260), mode="fixed",
               use="End-screen crest rays behind the Ø116 medallion (the #FFB23A glow is a code BoxShadow)."))
    for name, col in (("amber", "#FFB82E"), ("ivory", "#FFE7A6"), ("white", "#F4F4F4")):
        R.append(E(f"ornaments/gem_{name}@2x.png", "ornaments.gem_texture", args=(col,), logical=(16, 16),
                   mode="stretch", spec=False, tint=("any colour (multiply)" if name == "white" else None),
                   use={"amber": "Chrome gem: forge-horn bosses (master horn), crest.",
                        "ivory": "Chrome gem #FFE7A6: ember-knot centre (banner), boss phase notches, the north gem.",
                        "white": "Tintable chrome gem: ember-knot centre in the god colour (boon title)."}[name]))
    R.append(E("ornaments/hearth_rail@2x.png", "ornaments.hearth_rail", logical=(390, 6), mode="stretch", spec=False,
               use="The Hearth's gilt rail (x 146-536, centred on y 955), 3.6 -> 2.4 px."))
    # ── slots ──
    for sh in _slots.SHAPES:
        for part in ("fill", "rim", "mask"):
            R.append(E(f"slots/slot_{sh}_{part}@2x.png", f"slots.slot_{part}", args=(sh,), logical=(64, 64),
                       use=f"{_slots.SHAPE_USE[sh]}: {part}."))
        R.append(E(f"slots/slot_{sh}_glow@2x.png", "slots.slot_glow", args=(sh,), logical=(96, 96), spec=False,
                   tint="ready_glow", use=f"{_slots.SHAPE_USE[sh]}: ready halo. Centre it on the slot at 1.5x the "
                   "slot size; tint ready_glow."))
        R.append(E(f"slots/slot_{sh}_sheen@2x.png", "slots.slot_sheen", args=(sh,), logical=(64, 64), spec=False,
                   use=f"{_slots.SHAPE_USE[sh]}: the ready top sheen (over the icon, under the rim)."))
    R.append(E("slots/medallion_hearth@2x.png", "slots.medallion_hearth", logical=(128, 128),
               use="Hearth medallion metal (Ø128): bezel + 8 studs + trough ticks + inner rim. Clear where the "
               "ult trough (r 54.5-59.5) and the band/window (r < 52.7) show."))
    R.append(E("slots/medallion_rim@2x.png", "slots.medallion_rim", logical=(64, 64),
               use="Plain gilt medallion rim, 3 px at 64 (generic; prefer the sized variants)."))
    for s, rim in ((34, 2.0), (46, 2.2), (60, 2.6), (68, 2.8), (100, 5.0)):
        R.append(E(f"slots/medallion_rim_{s}@2x.png", "slots.medallion_rim", args=(float(s), rim), logical=(s, s),
                   mode="fixed", spec=False, use={34: "Edge pins, badges (Ø34, 2 px)", 46: "Party medallions (2.2 px)",
                                                  60: "Boon chip god medallion (2.6 px)",
                                                  68: "End-screen card medallions (2.8 px)",
                                                  100: "Boon card apex medallion (5 px bezel)"}[s]))
    R.append(E("slots/medallion_rim_116_studded@2x.png", "slots.medallion_rim", args=(116.0, 4.5, 8), logical=(116, 116),
               mode="fixed", spec=False, use="End-screen crest medallion: 4.5 px bezel with 8 studs."))
    R.append(E("slots/enamel_disc@2x.png", "slots.enamel_disc", args=(100.0,), logical=(100, 100), spec=False,
               tint="god colour (multiply)", use="God-colour enamel for medallions (apex, boon chip, badges)."))
    for shp in ("lozenge", "round"):
        R.append(E(f"slots/gem_socket_{shp}@2x.png", "ornaments.gem_socket", args=(shp,), logical=(16, 16), spec=False,
                   use=f"Empty {shp} gilt setting under a gem node (rarity gems, notches)."))
    for st in ("full", "empty", "mask"):
        R.append(E(f"slots/dash_{st}@2x.png", "slots.dash_lozenge", args=(st,), logical=(18, 18), mode="fixed",
                   spec=False, use=f"Dash charge lozenge (r 7.2): {st}."))
    for full in (True, False):
        R.append(E(f"slots/armor_plate_{'full' if full else 'empty'}@2x.png", "slots.armor_plate", args=(full,),
                   logical=(12, 9), mode="three_slice_h", slice_px=(8, 0, 8, 0), spec=False,
                   use="Armour plate (9 tall, 3 px skew), 3-slice: stretch to the plate width."))
    # ── fx ──
    R.append(E("fx/hatch_ward@2x.png", "fx.hatch_ward", logical=(10, 22), mode="tiled",
               use="Ward hatch: Tiled { tile_x: true, stretch_value: 1.0 } over the HP bar."))
    R.append(E("fx/sheen@2x.png", "fx.sheen", logical=(64, 128), use="Diagonal white band for sheens; slide it."))
    R.append(E("fx/spark4@2x.png", "fx.spark4", logical=(32, 32), use="Crit spark, shown at 16-24."))
    # ── bars (optional texture path) ──
    for k in ("hp", "ghost_hp", "boss", "ghost_boss", "elite", "molten", "surge", "white"):
        R.append(E(f"bars/fill_{k}@2x.png", "fx.bar_fill", args=(k,), logical=(8, 22), spec=False,
                   tint=("player colour" if k == "white" else None),
                   use=f"Bar fill '{k}' with a baked glassy sheen (stretch to the fill rect)."))
    R.append(E("bars/meniscus@2x.png", "fx.bar_meniscus", logical=(4, 22), spec=False,
               use="The fill's 1.6 px #FFF4DC leading edge; right edge on the fill end."))
    for thin in (False, True):
        sfx = "_thin" if thin else ""
        R.append(E(f"bars/trough{sfx}@2x.png", "fx.bar_trough", kwargs={"thin": thin},
                   logical=(8, 8) if thin else (20, 20), mode="nine_slice",
                   slice_px=(6, 6, 6, 6) if thin else (10, 10, 10, 10), spec=False,
                   use=f"Bar trough ({'6-10 px bars' if thin else '12-24 px bars'}), under the fills."))
        R.append(E(f"bars/rim{sfx}@2x.png", "fx.bar_rim", kwargs={"thin": thin},
                   logical=(8, 8) if thin else (20, 20), mode="nine_slice",
                   slice_px=(6, 6, 6, 6) if thin else (10, 10, 10, 10), spec=False,
                   use=f"Bar gilt rim ({'thin' if thin else 'standard'}), over the fills. Clear inside."))
    # ── markers ──
    R.append(E("markers/pin_frame_gilt@2x.png", "fx.pin_frame", args=(False,), logical=(56, 56), mode="fixed",
               spec=False, use="Edge pin ring (Ø34) + nub pointing up; rotate about the centre (28, 28) to aim."))
    R.append(E("markers/pin_frame_tint@2x.png", "fx.pin_frame", args=(True,), logical=(56, 56), mode="fixed",
               spec=False, tint="player colour / danger",
               use="White edge pin ring + nub for ally, ping and downed pins; tint in code."))
    R.append(E("markers/pin_disc@2x.png", "fx.pin_disc", logical=(34, 34), mode="fixed", spec=False,
               use="The pin medallion body under the glyph."))
    R.append(E("markers/ally_chevron@2x.png", "fx.ally_chevron", logical=(8, 5), mode="fixed", spec=False,
               tint="player colour", use="Ally tag chevron under the world HP bar."))
    R.append(E("markers/prompt_tail@2x.png", "fx.prompt_tail", logical=(14, 9), mode="fixed", spec=False,
               use="Prompt plate tail pointing down; top edge tucks 1 px under the plate."))
    for lit in (True, False):
        R.append(E(f"markers/threat_pip_{'lit' if lit else 'dark'}@2x.png", "fx.threat_pip", args=(lit,),
                   logical=(15, 11), mode="fixed", spec=False, use="Tracker threat chevron pip."))
    return R


def _render(entry):
    import importlib
    from kit import core
    mod_name, fn_name = entry["fn"].split(".")
    mod = importlib.import_module(f"kit.{mod_name}")
    kwargs = dict(entry["kwargs"])
    if kwargs.get("stops") == "BRONZE":
        kwargs["stops"] = core.BRONZE
    t = time.time()
    img = getattr(mod, fn_name)(*entry["args"], **kwargs)
    path = os.path.join(OUT, entry["file"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, optimize=True)
    return entry["file"], img.size, time.time() - t


def write_manifest(reg):
    items = []
    for e in reg:
        path = os.path.join(OUT, e["file"])
        from PIL import Image
        with Image.open(path) as im:
            size = list(im.size)
        want = [int(round(v * 2)) for v in e["logical"]]
        if size != want:
            raise SystemExit(f"size mismatch {e['file']}: {size} != {want}")
        d = {"file": e["file"], "size": size, "logical_size": e["logical"], "mode": e["mode"]}
        if "slice" in e:
            d["slice"] = e["slice"]
            d["max_corner_scale"] = 0.5
        for k in ("sides", "tile_logical", "tint", "anchor", "content_offset_y"):
            if e.get(k) is not None:
                d[k] = e[k]
        d["spec"] = "UI_STYLE §8.2" if e["spec"] else "extra"
        d["use"] = e["use"]
        items.append(d)
    man = {
        "generator": "tools/ui/make_ui_kit.py",
        "spec": "docs/art/UI_STYLE.md §8",
        "scale": 2,
        "color": "sRGB, straight alpha, RGBA8",
        "sampler": "linear",
        "notes": [
            "Sizes are texture px; logical_size is UI px at UiScale 1.0 (1920x1080).",
            "nine_slice: TextureSlicer { border: slice (texture px), max_corner_scale: 0.5, sides/centre Stretch "
            "unless sides == 'tile' }. Keep sliced nodes >= logical_size on each axis.",
            "three_slice_h: only left/right borders; the middle stretches horizontally.",
            "fixed: draw at logical_size (pre-sized so the texture is sampled at exactly 0.5 at UiScale 1).",
            "stretch: NodeImageMode::Stretch to the node.",
            "tint: the texture is white/greyscale for ImageNode.color.",
            "spec 'extra' = not in the §8.2 table: optional upgrades for lanes K, H and P.",
        ],
        "textures": items,
    }
    # one texture per line keeps the manifest readable and its diffs small
    head = json.dumps({k: v for k, v in man.items() if k != "textures"}, indent=1, ensure_ascii=False)
    rows = ",\n  ".join(json.dumps(t, ensure_ascii=False) for t in items)
    path = os.path.join(OUT, "ui_kit.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(head[:-2] + ',\n "textures": [\n  ' + rows + "\n ]\n}\n")
    with open(path, encoding="utf-8") as f:
        json.load(f)   # stays valid JSON
    return man


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="render only entries whose file path contains this text")
    ap.add_argument("--jobs", type=int, default=max(1, min(10, (os.cpu_count() or 4) // 2)))
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--sheet-only", action="store_true")
    a = ap.parse_args()
    reg = registry()
    if not a.sheet_only:
        todo = [e for e in reg if a.only is None or a.only in e["file"]]
        # the big niche canvases first, so they overlap with the many small jobs
        todo.sort(key=lambda e: -(e["logical"][0] * e["logical"][1]))
        t0 = time.time()
        if a.jobs > 1 and len(todo) > 1:
            with ProcessPoolExecutor(max_workers=a.jobs) as ex:
                futs = [ex.submit(_render, e) for e in todo]
                for f in as_completed(futs):
                    name, size, dt = f.result()
                    print(f"{dt:6.1f}s  {size[0]:4d}x{size[1]:<4d} {name}")
        else:
            for e in todo:
                name, size, dt = _render(e)
                print(f"{dt:6.1f}s  {size[0]:4d}x{size[1]:<4d} {name}")
        print(f"rendered {len(todo)} textures in {time.time() - t0:.1f}s")
        if a.only is None:
            write_manifest(reg)
            print("wrote assets/ui/ui_kit.json")
    if not a.no_sheet and (a.only is None or a.sheet_only):
        from kit import sheet
        sheet.build(OUT, SHEET)
        print(f"wrote {os.path.relpath(SHEET, ROOT)}")


if __name__ == "__main__":
    main()
