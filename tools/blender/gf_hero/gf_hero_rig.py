"""GF_Hero_v1 - the one master skeleton for every GODFORGE hero (docs/art/GF_HERO_SKELETON.md).

Adapted from the user's Ashen Covenant AC_Player_Humanoid_v1 (D:/Ashen_Covenant/tools/blender/ac_player_rig/
ac_player_rig.py, with the core table of ac_humanoid_enemy/ac_humanoid_rig.py and the roll fallback of
ac_humanoid_enemy/ac_rig_base.py). Kept identical: the 23 core bones (names, parents, connection), the twist
bones driven by Copy Rotation, the 15-bone hands, the roll convention and the deform flags. GODFORGE changes:
  * the sockets are the GODFORGE set (weapon_R / weapon_L at the weapon grip frame, head_top, chest_sigil) and
    each one is built from a full FRAME (origin, forward, up), not from a head/tail pair, so a weapon or VFX
    authored in the grip frame attaches in the engine as an identity child (see SOCKET FRAMES below);
  * a bone that runs (almost) parallel to the roll target rolls toward +Z instead (ac_rig_base.py rule; in the
    source rig this only touched root and toe, which Blender already rolled to +Z);
  * the twist extraction uses Euler order YXZ (swing-twist), which changes nothing in the contract;
  * the tables are plain data: this module imports bpy / mathutils only inside the build functions, so the
    stdlib validator (check_skeleton.py, CI) can read the contract without Blender.

Conventions (identical to AC_Player_Humanoid_v1)
  * 1 unit = 1 m, the hero faces -Y in Blender (+Z in glTF), +X is the hero's LEFT, Z up, feet on z = 0.
  * Every bone's local +Y runs along the bone. Core and twist bones roll so local +Z faces the hero's front
    (world -Y): a positive rotation about local X swings the child toward the front on BOTH sides (shoulder and
    elbow flexion +X, knee flexion -X, spine forward bend +X), Y twists, Z swings toward world +X. Left and right
    are built identically, never mirrored.
  * Finger bones roll to the palm normal (landmarks palm_normal_L/R), so +X curls toward the palm on both
    hands; thumbs roll to thumb_curl_L/R.
  * Every runtime bone (core, twist, fingers, sockets, per-hero x_ extras) has use_deform = True so the glTF
    exporter keeps it. root and the sockets never carry weights. A control rig, if one is ever added, is
    use_deform = False.
  * The armature OBJECT is named GF_Hero_v1 in every hero file (Bevy AnimationTargetIds are bone-name paths
    from the animation root, so one clip drives every hero).

SOCKET FRAMES
  A socket is defined by a grip frame in the rest pose: origin, forward F and up U (Blender world axes). For the
  weapon sockets F = along the fingers and U = out of the back of the hand (docs/art/WEAPONS.md, the anvil_gauntlets
  frame): the weapon asset's own +Y (barrel / fingers) and +Z (top / back of the hand). The socket BONE is built
  with bone +Y = U, bone +Z = -F, bone +X = F x U (= the grip frame's +X). The glTF exporter keeps bone-local
  axes, and a weapon exported with +Y up stores its grip-frame (x, y, z) as (x, z, -y); so the socket node's
  local frame in glTF (-Z = forward, +Y = up, +X = right) IS the weapon GLB's root frame, and the weapon
  scene attaches as an identity child. In Blender the same object sits at pose_bone.matrix @ SOCKET_TO_GRIP
  (a -90 degree turn about X): see grip_matrix().
"""

RIG_NAME = "GF_Hero_v1"
CONTRACT_VERSION = 1

# --- core: (name, parent, head_landmark, tail_landmark, connected) - identical to AC_Humanoid_Enemy_v1 ------------
CORE_BONES = [
    ("root", None, "root", "root_tip", False),
    ("pelvis", "root", "pelvis", "spine_01", False),
    ("spine_01", "pelvis", "spine_01", "spine_02", True),
    ("spine_02", "spine_01", "spine_02", "spine_03", True),
    ("spine_03", "spine_02", "spine_03", "neck", True),
    ("neck", "spine_03", "neck", "head", True),
    ("head", "neck", "head", "head_tip", True),
    ("clavicle_L", "spine_03", "clavicle_L", "shoulder_L", False),
    ("upperarm_L", "clavicle_L", "shoulder_L", "elbow_L", True),
    ("lowerarm_L", "upperarm_L", "elbow_L", "wrist_L", True),
    ("hand_L", "lowerarm_L", "wrist_L", "hand_L_tip", True),
    ("clavicle_R", "spine_03", "clavicle_R", "shoulder_R", False),
    ("upperarm_R", "clavicle_R", "shoulder_R", "elbow_R", True),
    ("lowerarm_R", "upperarm_R", "elbow_R", "wrist_R", True),
    ("hand_R", "lowerarm_R", "wrist_R", "hand_R_tip", True),
    ("thigh_L", "pelvis", "hip_L", "knee_L", False),
    ("shin_L", "thigh_L", "knee_L", "ankle_L", True),
    ("foot_L", "shin_L", "ankle_L", "ball_L", True),
    ("toe_L", "foot_L", "ball_L", "toe_L_tip", True),
    ("thigh_R", "pelvis", "hip_R", "knee_R", False),
    ("shin_R", "thigh_R", "knee_R", "ankle_R", True),
    ("foot_R", "shin_R", "ankle_R", "ball_R", True),
    ("toe_R", "foot_R", "ball_R", "toe_R_tip", True),
]
CORE_NAMES = [b[0] for b in CORE_BONES]

# --- twist: (name, parent, head_landmark, tail_landmark, driver_bone, factor) - identical to AC_Player_Humanoid_v1 --
# upperarm/thigh twist covers the proximal half and COUNTER-rotates half of the limb's own twist (the skin near
# the shoulder / hip twists less than the limb); lowerarm twist covers the distal half and follows 65 % of the
# hand's twist (pronation / supination happens in the forearm, not the wrist).
TWIST_BONES = [
    ("upperarm_twist_L", "upperarm_L", "shoulder_L", "upperarm_mid_L", "upperarm_L", -0.5),
    ("lowerarm_twist_L", "lowerarm_L", "lowerarm_mid_L", "wrist_L", "hand_L", 0.65),
    ("thigh_twist_L", "thigh_L", "hip_L", "thigh_mid_L", "thigh_L", -0.5),
    ("upperarm_twist_R", "upperarm_R", "shoulder_R", "upperarm_mid_R", "upperarm_R", -0.5),
    ("lowerarm_twist_R", "lowerarm_R", "lowerarm_mid_R", "wrist_R", "hand_R", 0.65),
    ("thigh_twist_R", "thigh_R", "hip_R", "thigh_mid_R", "thigh_R", -0.5),
]
MID_PAIRS = {"upperarm_mid_L": ("shoulder_L", "elbow_L"), "upperarm_mid_R": ("shoulder_R", "elbow_R"),
             "lowerarm_mid_L": ("elbow_L", "wrist_L"), "lowerarm_mid_R": ("elbow_R", "wrist_R"),
             "thigh_mid_L": ("hip_L", "knee_L"), "thigh_mid_R": ("hip_R", "knee_R")}

# --- hands: 5 chains of 3 per side, landmarks <finger>_<side>_01..03 + _tip ------------------------------------
FINGERS = ("thumb", "index", "middle", "ring", "pinky")


def finger_bones(side):
    out = []
    for f in FINGERS:
        parent = "hand_" + side
        for i in (1, 2, 3):
            name = "%s_%02d_%s" % (f, i, side)
            head = "%s_%s_%02d" % (f, side, i)
            tail = "%s_%s_%02d" % (f, side, i + 1) if i < 3 else "%s_%s_tip" % (f, side)
            out.append((name, parent, head, tail))
            parent = name
    return out


FINGER_BONES = finger_bones("L") + finger_bones("R")

# --- sockets: (name, parent, meaning). Exported (use_deform) but never weighted. Frames come from the landmark
# file's "sockets" block: {name: {"origin": xyz, "forward": xyz, "up": xyz}} in the rest pose. ------------------
SOCKET_BONES = [
    ("weapon_R", "hand_R", "right-hand weapon grip: origin palm centre, forward = along the fingers, up = out of the "
                           "back of the hand (docs/art/WEAPONS.md grip frame). Every weapon GLB root / grip_R attaches here"),
    ("weapon_L", "hand_L", "left-hand weapon grip, the mirrored frame (forward = along the left fingers, up = back of "
                           "the left hand). Off-hand meshes (offhand node, the left gauntlet) attach here"),
    ("head_top", "head", "top of the head silhouette (hair included): name plates, status icons, head VFX; "
                         "forward = the face's forward, up = up"),
    ("chest_sigil", "spine_03", "chest emblem on the sternum surface (Brax: the furnace sigil): chest VFX, beams, "
                                "auras; forward = out of the chest, up = along the spine"),
]
SOCKET_NAMES = [b[0] for b in SOCKET_BONES]
SOCKET_LENGTH = 0.08       # display only; the frame is what matters

# SOCKET_TO_GRIP: the grip frame expressed in the socket bone's frame. grip +X = bone +X, grip +Y (forward) = bone
# -Z, grip +Z (up) = bone +Y: a -90 degree rotation about X. It is exactly glTF's +Y-up conversion, which is why the
# attach is an identity in the engine.
SOCKET_TO_GRIP = ((1.0, 0.0, 0.0, 0.0),
                  (0.0, 0.0, 1.0, 0.0),
                  (0.0, -1.0, 0.0, 0.0),
                  (0.0, 0.0, 0.0, 1.0))

VECTOR_KEYS = ["palm_normal_L", "palm_normal_R", "thumb_curl_L", "thumb_curl_R"]
POINT_KEYS = sorted({k for b in CORE_BONES for k in (b[2], b[3])}
                    | {k for b in FINGER_BONES for k in (b[2], b[3])})
LANDMARK_KEYS = POINT_KEYS + VECTOR_KEYS
EXTRA_PREFIX = "x_"         # per-hero leaf chains (cloth, hair, tails); never rename or reparent a contract bone


def core_bone_names():
    return list(CORE_NAMES)


def twist_bone_names():
    return [b[0] for b in TWIST_BONES]


def finger_bone_names():
    return [b[0] for b in FINGER_BONES]


def socket_bone_names():
    return list(SOCKET_NAMES)


def contract_bone_names():
    return core_bone_names() + twist_bone_names() + finger_bone_names() + socket_bone_names()


def non_weight_bone_names():
    """Bones that must never carry skin weights."""
    return ["root"] + socket_bone_names()


def weight_bone_names():
    """Bones that may carry skin weights (the deform set)."""
    nw = set(non_weight_bone_names())
    return [n for n in contract_bone_names() if n not in nw]


def contract_parents():
    """{bone: parent} for every contract bone."""
    out = {b[0]: b[1] for b in CORE_BONES}
    out.update({b[0]: b[1] for b in TWIST_BONES})
    out.update({b[0]: b[1] for b in FINGER_BONES})
    out.update({b[0]: b[1] for b in SOCKET_BONES})
    return out


# ---- pure-python landmark checks (used by check_skeleton.py in CI and by the build) ----------------------------------

def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return _dot(a, a) ** 0.5


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def point(lm, key):
    """A landmark point, computing the twist mid-points when the file does not list them."""
    if key in lm:
        return [float(v) for v in lm[key]]
    if key in MID_PAIRS:
        a, b = (point(lm, k) for k in MID_PAIRS[key])
        return [(a[i] + b[i]) * 0.5 for i in range(3)]
    raise KeyError("landmark '%s' missing" % key)


def socket_axes(frame):
    """(origin, X, Y_forward, Z_up) of a socket frame, orthonormalised (up is made perpendicular to forward)."""
    o = [float(v) for v in frame["origin"]]
    f = [float(v) for v in frame["forward"]]
    u = [float(v) for v in frame["up"]]
    fl = _len(f)
    f = [v / fl for v in f]
    d = _dot(u, f)
    u = [u[i] - f[i] * d for i in range(3)]
    ul = _len(u)
    u = [v / ul for v in u]
    return o, _cross(f, u), f, u


def validate_landmarks(lm):
    """Problems (empty list = OK) with a hero landmark dict: missing keys, zero-length bones, bad vectors, socket
    frames, left/right mirror consistency of the core joints (heroes are symmetric in the rest pose)."""
    problems = []
    for k in LANDMARK_KEYS:
        if k not in lm:
            problems.append("missing landmark %s" % k)
    if problems:
        return problems
    for table in (CORE_BONES, FINGER_BONES):
        for b in table:
            if _len(_sub(point(lm, b[3]), point(lm, b[2]))) < 0.004:
                problems.append("bone %s is shorter than 4 mm" % b[0])
    for b in TWIST_BONES:
        if _len(_sub(point(lm, b[3]), point(lm, b[2]))) < 0.004:
            problems.append("twist bone %s is shorter than 4 mm" % b[0])
    for k in VECTOR_KEYS:
        if abs(_len(lm[k]) - 1.0) > 0.02:
            problems.append("vector %s is not unit length" % k)
    socks = lm.get("sockets", {})
    for name in SOCKET_NAMES:
        fr = socks.get(name)
        if fr is None:
            problems.append("missing socket frame %s" % name)
            continue
        for key in ("origin", "forward", "up"):
            if key not in fr or len(fr[key]) != 3:
                problems.append("socket %s has no %s" % (name, key))
        if any(p.startswith("socket %s" % name) for p in problems):
            continue
        f, u = fr["forward"], fr["up"]
        if _len(f) < 1e-6 or _len(u) < 1e-6:
            problems.append("socket %s has a zero axis" % name)
        elif abs(_dot(f, u)) / (_len(f) * _len(u)) > 0.02:
            problems.append("socket %s: forward and up are not perpendicular (cos %.3f)" % (name, _dot(f, u) / (_len(f) * _len(u))))
    for k in POINT_KEYS:
        if k.endswith("_L") or "_L_" in k:
            k2 = k[:-2] + "_R" if k.endswith("_L") else k.replace("_L_", "_R_")
            if k2 in lm:
                a, b = point(lm, k), point(lm, k2)
                if abs(a[0] + b[0]) > 0.002 or abs(a[1] - b[1]) > 0.002 or abs(a[2] - b[2]) > 0.002:
                    problems.append("%s / %s are not mirror images (rest pose must be symmetric)" % (k, k2))
    for n, p in (("weapon_L", "hand_L"), ("weapon_R", "hand_R")):
        if n in socks and "origin" in socks[n]:
            w = point(lm, "wrist_" + p[-1])
            t = point(lm, p + "_tip")
            o = socks[n]["origin"]
            if _len(_sub(o, w)) > 1.5 * _len(_sub(t, w)) + 0.05:
                problems.append("socket %s origin is not on the hand" % n)
    for eb in lm.get("extra_bones", []):
        if not str(eb[0]).startswith(EXTRA_PREFIX):
            problems.append("per-hero bone %s must be prefixed %s" % (eb[0], EXTRA_PREFIX))
    return problems


# ---- Blender: build + validate ------------------------------------------------------------------------------------

def build_armature(landmarks, extra_bones=None, name=RIG_NAME, collection=None):
    """Create GF_Hero_v1 from a landmark dict (metres, rest pose). extra_bones: per-hero leaf bones
    [(name, parent, head_xyz, tail_xyz)] prefixed x_ (default: landmarks["extra_bones"]).
    Returns the armature object in OBJECT mode with the twist constraints installed."""
    import bpy
    from mathutils import Vector

    forward = Vector((0.0, -1.0, 0.0))
    up = Vector((0.0, 0.0, 1.0))
    problems = validate_landmarks(landmarks)
    if problems:
        raise ValueError("landmarks rejected: " + "; ".join(problems[:12]))
    extra = list(landmarks.get("extra_bones", [])) if extra_bones is None else list(extra_bones)

    arm_data = bpy.data.armatures.new(name)
    arm_obj = bpy.data.objects.new(name, arm_data)
    (collection or bpy.context.scene.collection).objects.link(arm_obj)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def make(bname, parent, head, tail, connected, roll_vec):
        b = eb.new(bname)
        b.head = head
        b.tail = tail
        b.use_deform = True
        b.use_connect = False
        if parent:
            b.parent = eb[parent]
            b.use_connect = connected and (eb[parent].tail - head).length < 1e-6
        axis = (tail - head).normalized()
        rv = Vector(roll_vec)
        if abs(axis.dot(rv.normalized())) > 0.95:        # ac_rig_base.py rule: parallel to the target -> roll to +Z
            rv = up if abs(axis.dot(up)) < 0.95 else forward
        b.align_roll(rv)
        return b

    P = lambda k: Vector(point(landmarks, k))  # noqa: E731
    for bname, parent, hk, tk, connected in CORE_BONES:
        make(bname, parent, P(hk), P(tk), connected, forward)
    for bname, parent, hk, tk, _drv, _f in TWIST_BONES:
        make(bname, parent, P(hk), P(tk), False, forward)
    for bname, parent, hk, tk in FINGER_BONES:
        side = bname[-1]
        roll = landmarks["thumb_curl_" + side] if bname.startswith("thumb") else landmarks["palm_normal_" + side]
        make(bname, parent, P(hk), P(tk), False, roll)
    for bname, parent, _doc in SOCKET_BONES:
        o, _x, f, u = socket_axes(landmarks["sockets"][bname])
        b = eb.new(bname)
        b.head = Vector(o)
        b.tail = Vector(o) + Vector(u) * SOCKET_LENGTH       # bone +Y = up
        b.align_roll(-Vector(f))                             # bone +Z = -forward
        b.use_deform = True
        b.use_connect = False
        b.parent = eb[parent]
    for bname, parent, head, tail in extra:
        make(bname, parent, Vector(head), Vector(tail), False, forward)
    bpy.ops.object.mode_set(mode="OBJECT")

    for bname, _parent, _hk, _tk, driver, factor in TWIST_BONES:
        pb = arm_obj.pose.bones[bname]
        c = pb.constraints.new("COPY_ROTATION")
        c.name = "twist_from_" + driver
        c.target = arm_obj
        c.subtarget = driver
        c.use_x = False
        c.use_z = False
        c.use_y = True
        c.invert_y = factor < 0
        c.euler_order = "YXZ"          # twist first: the Y angle is the swing-twist twist
        c.mix_mode = "ADD"
        c.owner_space = "LOCAL"
        c.target_space = "LOCAL"
        c.influence = abs(factor)

    arm_data.display_type = "OCTAHEDRAL"
    arm_obj.show_in_front = True
    cols = {n: arm_data.collections.new(n) for n in ("Core", "Twist", "Fingers", "Sockets", "Extras")}
    twist, fingers, sockets = set(twist_bone_names()), set(finger_bone_names()), set(SOCKET_NAMES)
    for bone in arm_data.bones:
        if bone.name in CORE_NAMES:
            cols["Core"].assign(bone)
        elif bone.name in twist:
            cols["Twist"].assign(bone)
        elif bone.name in fingers:
            cols["Fingers"].assign(bone)
        elif bone.name in sockets:
            cols["Sockets"].assign(bone)
        else:
            cols["Extras"].assign(bone)
    arm_obj["gf_contract"] = "%s v%d" % (RIG_NAME, CONTRACT_VERSION)
    return arm_obj


def validate_hierarchy(arm_obj):
    """Problems (empty = OK) comparing an armature to the contract: names, parents, deform flags, extras."""
    problems = []
    if arm_obj.name != RIG_NAME:
        problems.append("armature object is named %s, must be %s" % (arm_obj.name, RIG_NAME))
    bones = arm_obj.data.bones
    for bname, parent in contract_parents().items():
        if bname not in bones:
            problems.append("missing bone %s" % bname)
            continue
        actual = bones[bname].parent.name if bones[bname].parent else None
        if actual != parent:
            problems.append("%s parent is %s, expected %s" % (bname, actual, parent))
    known = set(contract_parents())
    for b in bones:
        if b.name not in known and not b.name.startswith(EXTRA_PREFIX):
            problems.append("unknown bone %s (per-hero bones must be prefixed %s)" % (b.name, EXTRA_PREFIX))
        if "." in b.name:
            problems.append("non-canonical bone name %s" % b.name)
        if not b.use_deform:
            problems.append("runtime bone %s is not flagged deform (the glTF export would drop it)" % b.name)
    return problems


def grip_matrix(arm_obj, socket, pose=True):
    """World matrix of the grip frame at a socket (Blender axes): where a weapon object authored in the grip frame
    (+Y forward, +Z up) sits. pose=False gives the rest-pose frame."""
    from mathutils import Matrix
    m = arm_obj.pose.bones[socket].matrix if pose else arm_obj.data.bones[socket].matrix_local
    return arm_obj.matrix_world @ m @ Matrix(SOCKET_TO_GRIP)
