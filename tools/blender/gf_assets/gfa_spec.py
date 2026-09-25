"""GODFORGE asset contract as data (pure Python: no bpy, no PIL, no numpy).

Imported by the Blender toolkit (gfa_common, gfa_rig, gfa_export), the stand-alone validator
(gfa_validate.py) and the contact-sheet builder (gfa_sheet.py), so the numbers live in ONE place.
docs/art/WEAPONS.md and docs/art/ENEMIES.md explain them; change both together.

Axes (details in gfa_common.py and docs/art/WEAPONS.md section 2):
  Blender: 1 unit = 1 m, Z up. Creatures face -Y (their left is +X). Weapons are authored in GRIP
  space: origin = palm centre of the main hand, +Y = barrel / forward, +Z = up (weapon top).
  glTF export (+Y up): Blender (x, y, z) -> glTF/Bevy (x, z, -y).
  Engine (crates/gf_client/src/palette.rs): sim (x, y) -> world (x, 0, -y); yaw(angle) turns a mesh
  whose forward is world -Z. So a weapon (+Y -> -Z) needs no extra rotation under the aim pivot,
  and a creature (front -Y -> +Z) needs yaw(angle) * Quat::from_rotation_y(PI).
"""

SPEC_VERSION = 1

# ---- the game camera and scale (assets/content/game.ron) ---------------------------------------
HERO_HEIGHT = 2.2                     # m, GF_Hero_v1 proportions (Brax); heroes are 2.0 - 2.3 m
GAME_PITCH_DEG = 55.0                 # camera.pitch_deg
GAME_YAW_DEG = 0.0                    # camera.yaw_deg
GAME_VIEW_HEIGHTS = (22.0, 24.0, 26.0, 28.0)   # camera.view_height per party size (m of world = screen height)
SCREEN_H = 1080                       # judge at 1080p
# Key / fill light directions (Blender world, pointing FROM the scene TOWARD the light), converted
# from crates/gf_client/src/camera.rs KEY_LIGHT_FROM (-10, 22, 9) and the fill (12, 8, -6).
KEY_LIGHT_FROM = (-10.0, -9.0, 22.0)
FILL_LIGHT_FROM = (12.0, 6.0, 8.0)
# Greybox aim pivot (scene.rs spawn_rig): height 1.05 m on a 2.0 m greybox, gun offset r*0.75 to the right.
GREYBOX_PIVOT_HEIGHT = 1.05

# ---- colours ---------------------------------------------------------------------------------
PLAYER_COLORS = ("#FFC940", "#3FD8FF", "#B06CFF", "#5BE37D")   # game.ron player_colors: never enemy accents
ELEMENT_COLORS = {                                              # palette.rs element_color
    "Kinetic": "#F4E3C1", "Flame": "#FF7A1A", "Storm": "#3FD8FF",
    "Void": "#A45CFF", "Plague": "#86E03A", "Radiant": "#FFE27A",
}
TELEGRAPH_COLORS = ("#FF2A2A", "#FFFFFF")   # engine-drawn decals only; models never carry red-white telegraphs

# Faction material palettes (the user's enemy pack). Each material: shadow / base / light (painted
# value planes) and, for glows, rim / hot / core. Hex sRGB.
FACTIONS = {
    "unmade": {
        "glow": "#2FBFA8", "glow_alt": "#7CFF6B",
        "materials": {
            "obsidian": {"shadow": "#07060A", "base": "#1A1720", "light": "#4B4658"},
            "obsidian_wet": {"shadow": "#0B0E12", "base": "#20262C", "light": "#7FA7A0"},
            "ichor": {"shadow": "#0D3B35", "base": "#1F8F7E", "light": "#8FF2D8",
                      "rim": "#1F8F7E", "hot": "#2FBFA8", "core": "#B8FFE8"},
            "bone": {"shadow": "#6E6152", "base": "#BDB09A", "light": "#EDE4CF"},
            "slag": {"shadow": "#0C0908", "base": "#231A17", "light": "#4E3A30"},
            "molten": {"shadow": "#7A1E05", "base": "#FF6B1A", "light": "#FFC24B",
                       "rim": "#C8400C", "hot": "#FF6B1A", "core": "#FFF3D6"},
        },
    },
    "godworks": {
        "glow": "#D4B45A", "glow_alt": "#8A3A1E",      # cold gold fading to dead ember
        "materials": {
            "god_bronze": {"shadow": "#4A3A1E", "base": "#9C8045", "light": "#D4B45A"},
            "porcelain": {"shadow": "#8C877E", "base": "#D9D3C6", "light": "#F6F2E8"},
            "verdigris": {"shadow": "#10201C", "base": "#2E4A40", "light": "#5E8374"},
            "cold_gold_glow": {"shadow": "#5A4A20", "base": "#D4B45A", "light": "#F4E6B0",
                               "rim": "#8A6A28", "hot": "#D4B45A", "core": "#FFF4D0"},
            "dead_ember": {"shadow": "#2A0E08", "base": "#8A3A1E", "light": "#C8663A",
                           "rim": "#4A1A0C", "hot": "#8A3A1E", "core": "#E08A50"},
        },
    },
}

# ---- budgets ---------------------------------------------------------------------------------
# (min_tris, max_tris, max_texture_px). The minimum is a smell test (too few = unfinished), not a gate.
BUDGETS = {
    "weapon_one_handed": (1000, 2500, 1024),
    "weapon_two_handed": (2000, 4000, 1024),
    "weapon_gauntlet_pair": (4000, 8000, 1024),
    "enemy_swarm": (600, 1500, 1024),
    "enemy_elite": (4000, 8000, 1024),
    "enemy_miniboss": (10000, 20000, 2048),
    "enemy_boss": (20000, 40000, 2048),
}
MIN_TEXTURE_PX = 256

# ---- weapons ---------------------------------------------------------------------------------
WEAPON_SOCKETS_REQUIRED = {
    "weapon_one_handed": ("grip_R", "muzzle"),
    "weapon_two_handed": ("grip_R", "grip_L", "muzzle"),
    "weapon_gauntlet_pair": ("grip_R", "grip_L"),
}
WEAPON_SOCKETS_OPTIONAL = ("glow_core", "muzzle_2", "eject", "grip_L", "muzzle", "offhand")
# longest dimension sanity range (m) for a weapon held by a 2.2 m hero
WEAPON_LENGTH_RANGE = (0.2, 2.2)

# ---- enemies ---------------------------------------------------------------------------------
SWARM_SKELETON = "GF_Swarm_v1"
# (name, parent). Every GF_Swarm_v1 file has exactly these six bones (unused ones stay unweighted)
# so any swarm clip can drive any swarm scene. See gfa_rig.py for rest orientation and axes.
SWARM_BONES = (
    ("root", None),
    ("body", "root"),
    ("head", "body"),
    ("legs_a", "body"),
    ("legs_b", "body"),
    ("tail", "body"),
)
ENEMY_CLIPS_REQUIRED = ("idle@loop", "move@loop", "windup", "attack", "hit", "death")
ENEMY_SOCKETS_REQUIRED = ("hit_center",)
ENEMY_SOCKETS_OPTIONAL = ("fx_core", "fx_mouth", "attack_origin", "head_top", "shield")
# height of the whole creature relative to HERO_HEIGHT (min, max): the tier silhouette hierarchy
TIER_HEIGHT_RATIO = {
    "enemy_swarm": (0.2, 0.5),        # never above the hero's waist
    "enemy_elite": (1.1, 1.35),       # player + 20 %
    "enemy_miniboss": (1.7, 2.4),     # 2x player
    "enemy_boss": (3.0, 9.0),         # a monument (30-40 % of the arena)
}

# ---- export --------------------------------------------------------------------------------
# glTF extensions bevy_gltf 0.20 can load when REQUIRED (same list as tools/comfy/check_art.py)
BEVY_OK_EXTENSIONS = {"KHR_lights_punctual", "KHR_materials_unlit", "KHR_texture_transform",
                      "KHR_materials_transmission", "KHR_materials_ior", "KHR_materials_emissive_strength",
                      "KHR_materials_specular", "KHR_materials_volume", "KHR_materials_clearcoat",
                      "KHR_materials_anisotropy"}
BANNED_EXTENSIONS = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_meshopt_compression",
                     "KHR_mesh_quantization"}
STATUS_AI_FINAL = "ai_final_pending_user_approval"
KINDS = {"weapon": "weapons", "enemy": "enemies"}
KEY_RE = r"^[a-z][a-z0-9_]*$"
CLIP_RE = r"^[a-z][a-z0-9_]*(@loop)?$"


def budget_class(kind, tier):
    """'weapon' + 'two_handed' -> 'weapon_two_handed'."""
    c = "%s_%s" % (kind, tier)
    if c not in BUDGETS:
        raise KeyError("unknown budget class %r (known: %s)" % (c, ", ".join(sorted(BUDGETS))))
    return c


def hex_to_rgb01(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
