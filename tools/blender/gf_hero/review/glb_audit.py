"""Independent audit of a shipped GF_Hero_v1 hero GLB (written for the review of Brax stages 3-5,
art/characters/brax/reports/review_stage3_5.md). Nothing is shared with the pipeline's exporter or validator: the
expected skeleton is typed from docs/art/GF_HERO_SKELETON.md section 2, the clip list is required_clips.json, the
maths is gltf_fk.py (glTF-spec FK + linear blend skinning, the weapon as an identity child of its socket, as Bevy
does). It runs in headless Blender only for mathutils.bvhtree (the gauntlet enclosure test):

  blender -b --factory-startup -P glb_audit.py -- <repo> <hero.glb> <weapon.glb> <out.json> [<labels.json>]

Per clip and every frame: joint ranges (elbow, knee, wrist swing), loop seams, in-place drift, planted-ball drift
(a height test, so take-off / landing frames within 10 mm of the ground count too: read the frames before calling it
a slide), the lowest skinned vertex, inverted / crushed triangles, and every skinned vertex ENCLOSED by a gauntlet (6
axis rays hit it: inside its shell or its cavity) that is not the holding forearm / hand / fingers ("foreign"; the own
upper arm, the known cuff overlap, is reported apart; the joined GLB has no part names, so hanging cloth counts too).
"""
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gltf_fk import GLB  # noqa: E402

ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
REPO, HERO, WEAP, OUT = ARGV[:4]
# optional: {"parts": [part name per GLB vertex]} (the joined GLB has no part names) -> foreign intrusion split into
# solid parts and hanging cloth
LABELS = json.load(open(ARGV[4], encoding="utf-8"))["parts"] if len(ARGV) > 4 else None
CLOTH = {"SKIRT_PLATES", "SKIRT_CLOTH", "SASH"}
t0 = time.time()

# ---- the contract, typed from the doc (section 2) --------------------------------------------------------------------
EXP = {"root": None, "pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02",
       "neck": "spine_03", "head": "neck"}
for s in "LR":
    EXP.update({"clavicle_" + s: "spine_03", "upperarm_" + s: "clavicle_" + s, "lowerarm_" + s: "upperarm_" + s,
                "hand_" + s: "lowerarm_" + s, "thigh_" + s: "pelvis", "shin_" + s: "thigh_" + s, "foot_" + s: "shin_" + s,
                "toe_" + s: "foot_" + s, "upperarm_twist_" + s: "upperarm_" + s, "lowerarm_twist_" + s: "lowerarm_" + s,
                "thigh_twist_" + s: "thigh_" + s, "weapon_" + s: "hand_" + s})
    for f in ("thumb", "index", "middle", "ring", "pinky"):
        EXP["%s_01_%s" % (f, s)] = "hand_" + s
        EXP["%s_02_%s" % (f, s)] = "%s_01_%s" % (f, s)
        EXP["%s_03_%s" % (f, s)] = "%s_02_%s" % (f, s)
EXP.update({"head_top": "head", "chest_sigil": "spine_03"})
SOCKETS = ["weapon_R", "weapon_L", "head_top", "chest_sigil"]
TWIST = [b for b in EXP if "_twist_" in b]
NEVER_WEIGHTED = ["root"] + SOCKETS
NEVER_KEYED_MOVING = ["root"] + SOCKETS  # exported with their rest transform held

g = GLB(HERO)
w = GLB(WEAP)
meta = json.load(open(HERO.replace(".glb", ".meta.json"), encoding="utf-8"))
req = json.load(open(os.path.join(REPO, "tools", "blender", "gf_hero", "required_clips.json"), encoding="utf-8"))
key = meta["key"]
R = {"hero": key, "glb": HERO, "problems": [], "notes": []}


def prob(s):
    R["problems"].append(s)
    print("PROBLEM:", s)


# ---- skeleton ---------------------------------------------------------------------------------------------------------
joints, ibm = g.skin(0)
jn = [g.names[j] for j in joints]
R["joints"] = len(jn)
missing = sorted(set(EXP) - set(jn))
extra = sorted(set(jn) - set(EXP))
if missing or extra:
    prob("skeleton: missing %s, extra %s" % (missing, extra))
for b, p in EXP.items():
    if b not in g.idx:
        continue
    gp = g.parent[g.idx[b]]
    got = g.names[gp] if gp >= 0 else None
    if p is None:
        if got != "GF_Hero_v1":
            prob("root's parent is %s, not the armature node GF_Hero_v1" % got)
    elif got != p:
        prob("%s parent %s, doc says %s" % (b, got, p))
scene_roots = [g.names[i] for i in g.j["scenes"][g.j.get("scene", 0)]["nodes"]]
if scene_roots != ["GF_Hero_v1"]:
    prob("scene roots %s" % scene_roots)
RW = g.rest_world()
# inverse bind == rest
ibm_err = max(np.abs(RW[j] @ ibm[k] - np.eye(4)).max() for k, j in enumerate(joints))
R["bind_vs_rest_max"] = float(ibm_err)
if ibm_err > 1e-4:
    prob("inverse bind matrices differ from the node rest pose by %.2e" % ibm_err)


def P(W, name):
    return W[..., g.idx[name], :3, 3]


# rest-pose conventions: +Y up, faces +Z, feet on y=0, T-pose symmetric about x=0
sym = 0.0
for b in EXP:
    if b.endswith("_L"):
        a, c = RW[g.idx[b], :3, 3], RW[g.idx[b[:-2] + "_R"], :3, 3]
        sym = max(sym, float(np.abs(a - c * np.array([-1, 1, 1])).max()))
R["rest_asymmetry_m"] = sym
if sym > 0.002:
    prob("rest pose asymmetric by %.4f m" % sym)
if not (P(RW, "hand_L")[0] > 0.5 and P(RW, "hand_R")[0] < -0.5):
    prob("T-pose arms not along +-X (hero's left must be +X)")
R["rest_heights"] = {b: round(float(P(RW, b)[1]), 4) for b in ("pelvis", "head", "head_top", "toe_L", "foot_L")}

# socket frames (doc section 3 / sidecar)
soc = {}
for s in SOCKETS:
    M = RW[g.idx[s]]
    fwd = -M[:3, 2]
    up = M[:3, 1]
    soc[s] = {"origin": [round(float(x), 5) for x in M[:3, 3]], "forward(-Z)": [round(float(x), 4) for x in fwd],
              "up(+Y)": [round(float(x), 4) for x in up], "det": round(float(np.linalg.det(M[:3, :3])), 6)}
    sc = meta["sockets"][s]
    e = max(np.abs(np.array(sc["translation"]) - M[:3, 3]).max(), np.abs(np.array(sc["forward"]) - fwd).max(),
            np.abs(np.array(sc["up"]) - up).max())
    soc[s]["vs_sidecar"] = float(e)
    if e > 1e-4:
        prob("socket %s differs from the sidecar by %.2e" % (s, e))
R["sockets_rest"] = soc
# weapon sockets: forward along the fingers (the hand's own direction), up = back of the hand (+Y in T-pose, palms down)
for s, sgn in (("weapon_R", -1), ("weapon_L", 1)):
    fwd = np.array(soc[s]["forward(-Z)"])
    if fwd[0] * sgn < 0.95 or soc[s]["up(+Y)"][1] < 0.95:
        prob("%s frame: forward %s up %s (expected fingers along %sX, back of hand +Y in the T-pose)" % (s, fwd, soc[s]["up(+Y)"], "+-"[sgn < 0]))
for s in ("head_top", "chest_sigil"):
    if soc[s]["forward(-Z)"][2] < 0.9:
        prob("%s forward %s is not the hero's front (+Z)" % (s, soc[s]["forward(-Z)"]))

# ---- mesh + weights ---------------------------------------------------------------------------------------------------
mi = g.skinned_mesh()
mesh_nodes = [i for i, n in enumerate(g.nodes) if "mesh" in n]
R["mesh_nodes"] = [g.names[i] for i in mesh_nodes]
md = g.mesh_data(g.nodes[mi]["mesh"])
prims = g.j["meshes"][g.nodes[mi]["mesh"]]["primitives"]
R["primitives"] = len(prims)
pos = md["POSITION"].astype(np.float64)
J = md["JOINTS_0"].astype(np.int64)
Wt = md["WEIGHTS_0"].astype(np.float64)
tri = md["indices"]
R["verts"] = len(pos)
R["tris"] = len(tri)
if "JOINTS_1" in md:
    prob("JOINTS_1 present: more than 4 influences")
if any(k.startswith("COLOR_") for k in md):
    prob("vertex colours present: %s" % [k for k in md if k.startswith("COLOR_")])
nz = (Wt > 0).sum(1)
R["influence_histogram"] = {int(k): int((nz == k).sum()) for k in range(0, 5)}
sums = Wt.sum(1)
R["weight_sum_err_max"] = float(np.abs(sums - 1).max())
R["unweighted_verts"] = int((sums < 1e-6).sum())
R["min_nonzero_weight"] = float(Wt[Wt > 0].min())
if R["unweighted_verts"]:
    prob("%d unweighted vertices" % R["unweighted_verts"])
if R["weight_sum_err_max"] > 1e-3:
    prob("weights not normalised (max error %.2e)" % R["weight_sum_err_max"])
# joints referenced with a non-zero weight
used = {}
for k in range(4):
    for ji in np.unique(J[Wt[:, k] > 0, k]):
        used[jn[ji]] = used.get(jn[ji], 0) + int(((J[:, k] == ji) & (Wt[:, k] > 0)).sum())
R["weighted_joints"] = len(used)
bad = [b for b in NEVER_WEIGHTED if b in used]
if bad:
    prob("never-weighted joints carry weight: %s" % bad)
R["twist_weighted_verts"] = {b: used.get(b, 0) for b in TWIST}
if any(used.get(b, 0) == 0 for b in TWIST):
    prob("a twist bone has no weight: %s" % R["twist_weighted_verts"])
dom = J[np.arange(len(J)), Wt.argmax(1)]          # dominant joint per vertex (skin index)
domname = np.array([jn[i] for i in dom])


def group(n):
    if n in ("pelvis", "spine_01", "spine_02", "spine_03", "neck", "head") or n.startswith("clavicle"):
        return "torso_head"
    for s in "LR":
        if n in ("upperarm_" + s, "upperarm_twist_" + s):
            return "upperarm_" + s
        if n in ("lowerarm_" + s, "lowerarm_twist_" + s):
            return "forearm_" + s
        if n == "hand_" + s:
            return "hand_" + s
        if n.endswith("_" + s) and n.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky"):
            return "fingers_" + s
        if n.startswith(("thigh", "shin", "foot", "toe")) and n.endswith("_" + s):
            return "leg_" + s
    return "other"


vgroup = np.array([group(n) for n in domname])
R["vertex_groups"] = {k: int((vgroup == k).sum()) for k in sorted(set(vgroup))}

# rest triangle data
v0 = pos
e1, e2 = v0[tri[:, 1]] - v0[tri[:, 0]], v0[tri[:, 2]] - v0[tri[:, 0]]
n0 = np.cross(e1, e2)
a0 = np.linalg.norm(n0, axis=1)
ok_tri = a0 > 1e-10
tdom = dom[tri[:, 0]]
tgroup = vgroup[tri[:, 0]]

# ---- weapon meshes ----------------------------------------------------------------------------------------------------
wm = {}
for i, nd in enumerate(w.nodes):
    if "mesh" in nd:
        d = w.mesh_data(nd["mesh"])
        # node-local transform chain inside the weapon scene, relative to the attach node (root or offhand)
        nm = w.names[i]
        wm[nm] = {"pos": d["POSITION"].astype(np.float64), "tri": d["indices"],
                  "parent": w.names[w.parent[i]], "local_is_identity": all(k not in nd for k in ("translation", "rotation", "scale"))}
R["weapon_meshes"] = {k: {"verts": len(v["pos"]), "tris": len(v["tri"]), "parent": v["parent"], "identity": v["local_is_identity"]} for k, v in wm.items()}
wroot = w.names[w.j["scenes"][0]["nodes"][0]]


def weapon_world(W, variant):
    """{side: (verts world (V,3), tris)} for the fist/open variant: right meshes under the weapon root on weapon_R,
    left meshes under offhand re-parented to weapon_L, both identity."""
    out = {}
    for s in "LR":
        nm = "%s_%s_%s" % (wroot, variant[s], s)
        m = wm[nm]
        S = W[g.idx["weapon_" + s]]
        out[s] = (m["pos"] @ S[:3, :3].T + S[:3, 3], m["tri"])
    return out


from mathutils import Vector  # noqa: E402  (run inside Blender: mathutils.bvhtree is C-fast)
from mathutils.bvhtree import BVHTree  # noqa: E402
_BVH = {}


def local_bvh(variant, s):
    k = (variant, s)
    if k not in _BVH:
        m = wm["%s_%s_%s" % (wroot, variant, s)]
        _BVH[k] = BVHTree.FromPolygons([tuple(v) for v in m["pos"]], [tuple(int(i) for i in t) for t in m["tri"]])
    return _BVH[k]


RAYS = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]


def inside_local(points_local, variant, s):
    """points already in the socket-local (weapon authoring) frame -> bool array: ENCLOSED by the gauntlet, i.e. a ray
    along each of the 6 frame axes hits it (inside its shell material or inside its cavity; a point just outside the
    cuff opening is not enclosed). The gauntlets are hollow shells: the hand lives in the cavity."""
    bvh = local_bvh(variant, s)
    out = np.zeros(len(points_local), dtype=bool)
    for i, p in enumerate(points_local):
        o = Vector(p)
        for d in RAYS:
            if bvh.ray_cast(o, d, 1.0)[0] is None:
                break
        else:
            out[i] = True
    return out


def to_socket(W, s, pts):
    S = W[g.idx["weapon_" + s]]
    return (pts - S[:3, 3]) @ S[:3, :3]          # R^T (p - t) for row vectors


# rest: the gauntlets must enclose their hands (fist variant needs the fist pose; at rest the hands are open -> open)
Wrest = RW
rest_in = {}
for s in "LR":
    sel = np.where(np.isin(vgroup, ["hand_" + s]))[0]
    ins = inside_local(to_socket(Wrest, s, pos[sel]), "open", s)
    rest_in[s] = {"hand_verts": len(sel), "outside_open_gauntlet": int((~ins).sum())}
R["rest_hand_in_open_gauntlet"] = rest_in

# ---- clips ------------------------------------------------------------------------------------------------------------
names = g.anim_names()
expected = {}
for c in req["shared"] + req["heroes"].get(key, []):
    expected[key + "_" + c["clip"] + ("@loop" if c["loop"] else "")] = c
R["clip_names_missing"] = sorted(set(expected) - set(names))
R["clip_names_extra"] = sorted(set(names) - set(expected))
if R["clip_names_missing"] or R["clip_names_extra"]:
    prob("clip names: missing %s extra %s" % (R["clip_names_missing"], R["clip_names_extra"]))
if set(meta["clip_info"]) != set(names):
    prob("sidecar clip_info names != GLB animation names")

ELBOW_VALID, KNEE_VALID = 145.0, 135.0      # docs/art/GF_HERO_SKELETON.md section 7: the validated range
KNEE_LIMIT = 150.0                           # s4lib.KNEE_MAX_DEG: 135-150 is the documented knee soft spot
ground_y = 0.0
toe_rest_y = {s: float(P(RW, "toe_" + s)[1]) for s in "LR"}
clips = {}
render_pick = {}
for ai, an in enumerate(names):
    ci = meta["clip_info"].get(an, {})
    times, T, Rq, S, raw = g.sample(ai)
    F = len(times)
    W = g.world(T, Rq, S)
    c = {"frames": F - 1, "sidecar_frames": ci.get("frames"), "loop": an.endswith("@loop")}
    if ci.get("frames") != F - 1:
        prob("%s: %d frames in the GLB, sidecar says %s" % (an, F - 1, ci.get("frames")))
    keyed = sorted({g.names[n] for (n, p) in raw})
    c["keyed_nodes"] = len(keyed)
    # held channels: root, sockets, and every translation except the pelvis
    held = 0.0
    for b in NEVER_KEYED_MOVING:
        i = g.idx[b]
        held = max(held, np.abs(T[:, i] - g.rest_t[i]).max(), np.abs(np.abs((Rq[:, i] * g.rest_r[i]).sum(-1)) - 1).max())
    trans_move = {}
    for b in EXP:
        if b == "pelvis":
            continue
        i = g.idx[b]
        d = float(np.abs(T[:, i] - g.rest_t[i]).max())
        if d > 1e-5:
            trans_move[b] = d
    scl = float(np.abs(S[:, [g.idx[b] for b in EXP]] - 1).max())
    c["root_sockets_held_err"] = float(held)
    if held > 1e-5:
        prob("%s: root/sockets move (%.2e)" % (an, held))
    if trans_move:
        prob("%s: joints other than the pelvis translate: %s" % (an, {k: round(v, 5) for k, v in list(trans_move.items())[:5]}))
    c["joint_scale_dev"] = float(scl)
    if scl > 1e-3:
        prob("%s: joint scale keyed (%.2e)" % (an, scl))
    elif scl > 1e-5:
        R["notes"].append("%s: joint scale sampled %.1e off 1 (matrix-decomposition noise, harmless)" % (an, scl))
    # in place
    rootw = P(W, "root")
    c["root_world_drift_m"] = float(np.abs(rootw - rootw[0]).max())
    pel = P(W, "pelvis")
    pr = P(RW, "pelvis")
    c["pelvis_xz_drift_max_m"] = float(np.hypot(pel[:, 0] - pr[0], pel[:, 2] - pr[2]).max())
    c["pelvis_xz_end_m"] = float(np.hypot(pel[-1, 0] - pr[0], pel[-1, 2] - pr[2]))
    # joint ranges
    for s in "LR":
        sh, el, wr = P(W, "upperarm_" + s), P(W, "lowerarm_" + s), P(W, "hand_" + s)
        u, v = el - sh, wr - el
        ang = np.degrees(np.arccos(np.clip((u * v).sum(1) / np.linalg.norm(u, axis=1) / np.linalg.norm(v, axis=1), -1, 1)))
        c["elbow_max_" + s] = float(ang.max())
        c["elbow_argmax_" + s] = int(ang.argmax())
        hp, kn, an_ = P(W, "thigh_" + s), P(W, "shin_" + s), P(W, "foot_" + s)
        u, v = kn - hp, an_ - kn
        ang = np.degrees(np.arccos(np.clip((u * v).sum(1) / np.linalg.norm(u, axis=1) / np.linalg.norm(v, axis=1), -1, 1)))
        c["knee_max_" + s] = float(ang.max())
        c["knee_argmax_" + s] = int(ang.argmax())
        # wrist swing: the hand's +Y in the forearm's frame vs rest
        Rl = W[:, g.idx["lowerarm_" + s], :3, :3]
        Rh = W[:, g.idx["hand_" + s], :3, :3]
        rel = np.einsum("fji,fjk->fik", Rl, Rh)             # Rl^T Rh
        rel0 = RW[g.idx["lowerarm_" + s], :3, :3].T @ RW[g.idx["hand_" + s], :3, :3]
        y, y0 = rel[:, :, 1], rel0[:, 1]
        c["wrist_swing_max_" + s] = float(np.degrees(np.arccos(np.clip(y @ y0, -1, 1))).max())
    # loops
    if c["loop"]:
        Wp = W[:, :, :3, 3]
        c["loop_seam_pos_err_m"] = float(np.abs(Wp[-1] - Wp[0]).max())
        acc_in = np.abs(Wp[2:] - 2 * Wp[1:-1] + Wp[:-2]).max()
        seam = np.abs(Wp[1] - 2 * Wp[0] + Wp[-2]).max()           # frame -1 == frame F-1 == frame 0
        c["loop_seam_accel_ratio"] = float(seam / max(acc_in, 1e-9))
        if c["loop_seam_pos_err_m"] > 1e-4:
            prob("%s: loop does not close (%.4f m)" % (an, c["loop_seam_pos_err_m"]))
        if c["loop_seam_accel_ratio"] > 1.05:
            prob("%s: the loop seam is rougher than the clip (x%.2f)" % (an, c["loop_seam_accel_ratio"]))
    # foot slide (world: add the design travel back), ball joint = toe_* head
    trav = ci.get("travel_mps") or [0.0, 0.0]
    tv = np.array([trav[0], 0.0, -trav[1]])                  # Blender (x, y) -> glTF (x, -y) on the ground
    slide = {}
    for s in "LR":
        b = P(W, "toe_" + s) + times[:, None] * tv[None]
        planted = b[:, 1] <= toe_rest_y[s] + 0.003          # on the ground (a landing frame 8 mm up is not planted)
        best = 0.0
        k = 0
        while k < F:
            if planted[k]:
                e = k
                while e + 1 < F and planted[e + 1]:
                    e += 1
                if e - k >= 2:
                    seg = b[k:e + 1][:, [0, 2]]
                    best = max(best, float(np.linalg.norm(seg - seg[0], axis=1).max()))
                k = e + 1
            else:
                k += 1
        slide[s] = best
    c["foot_slide_mm"] = {s: round(v * 1000, 1) for s, v in slide.items()}
    c["slide_exempt"] = bool(ci.get("slide_exempt"))
    c["lowest_joint_y_mm"] = round(float(W[:, [g.idx[b] for b in EXP], 1, 3].min() * 1000), 1)
    # mesh-level, every frame
    M = W[:, joints] @ ibm[None]                                   # (F, nj, 4, 4)
    lowest, flips, crushed, worst_ratio, intr, intr_up, finger_out = [], [], [], [], [], [], []
    wv = ci.get("weapon_variant") or {"L": {"start": "fist", "swap_frames": []}, "R": {"start": "fist", "swap_frames": []}}

    def variant_at(s, fr):
        v = wv[s]["start"]
        for sf in wv[s]["swap_frames"]:
            if fr >= sf:
                v = "open" if v == "fist" else "fist"
        return v
    p4 = np.concatenate([pos, np.ones((len(pos), 1))], 1)
    per_frame = []
    FINGERS = {s: np.where(vgroup == "fingers_" + s)[0] for s in "LR"}
    BOX = {}
    for (vv_, ss_) in [(a_, b_) for a_ in ("fist", "open") for b_ in "LR"]:
        m_ = wm["%s_%s_%s" % (wroot, vv_, ss_)]["pos"]
        BOX[(vv_, ss_)] = (m_.min(0) - 0.005, m_.max(0) + 0.005)
    for fr in range(F):
        blend = (M[fr][J] * Wt[:, :, None, None]).sum(1)
        v = np.einsum("vij,vj->vi", blend, p4)[:, :3]
        lowest.append(float(v[:, 1].min()))
        e1, e2 = v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]]
        n = np.cross(e1, e2)
        a = np.linalg.norm(n, axis=1)
        # rest normal carried by the blended skin matrix of the triangle's first vertex (what the shader does)
        Rd = blend[tri[:, 0], :3, :3]
        n0r = np.einsum("tij,tj->ti", Rd, n0)
        cosn = (n * n0r).sum(1) / np.maximum(a * np.linalg.norm(n0r, axis=1), 1e-12)
        ratio = a / np.maximum(a0, 1e-12)
        fl = ok_tri & (cosn < 0.0)
        cr = ok_tri & (ratio < 0.2)
        flips.append(int(fl.sum()))
        crushed.append(int(cr.sum()))
        worst_ratio.append(float(ratio[ok_tri].min()))
        # the gauntlets vs everything that is not the holding forearm / hand / fingers
        var = {s: variant_at(s, fr) for s in "LR"}
        cnt, cnt_up, fo, cnt_solid = {}, {}, {}, {}
        for s in "LR":
            lv = to_socket(W[fr], s, v)                       # every vertex in this socket's frame
            lo, hi = BOX[(var[s], s)]
            inbox = np.all((lv >= lo) & (lv <= hi), 1)
            own = np.isin(vgroup, ["forearm_" + s, "hand_" + s, "fingers_" + s])
            cand = np.where(inbox & ~own)[0]
            inside = cand[inside_local(lv[cand], var[s], s)] if len(cand) else cand
            gg = vgroup[inside]
            cnt[s] = {k: int((gg == k).sum()) for k in set(gg)}
            if LABELS is not None:
                solid = [i for i in inside if vgroup[i] != "upperarm_" + s and LABELS[i] not in CLOTH]
                cnt_solid[s] = len(solid)
            # fingers must be inside the fist mesh while the fist variant shows (and inside the open one when open)
            fsel = FINGERS[s]
            fo[s] = int((~inside_local(lv[fsel], var[s], s)).sum())
        intr.append(cnt)
        finger_out.append(fo)
        per_frame.append({"flips": flips[-1], "crushed": crushed[-1], "lowest": lowest[-1],
                          "intr": sum(sum(x.values()) for x in cnt.values()),
                          "intr_foreign": sum(n for s in "LR" for k, n in cnt[s].items() if k != "upperarm_" + s),
                          "finger_out": fo["L"] + fo["R"], "var": var,
                          "intr_foreign_solid": sum(cnt_solid.values()) if LABELS is not None else None})
    c["lowest_vertex_mm"] = round(min(lowest) * 1000, 1)
    c["lowest_vertex_frame"] = int(np.argmin(lowest))
    c["flipped_tris_max"] = max(flips)
    c["flipped_tris_frame"] = int(np.argmax(flips))
    c["crushed_tris_max"] = max(crushed)
    c["crushed_tris_frame"] = int(np.argmax(crushed))
    c["tri_area_ratio_min"] = round(min(worst_ratio), 4)
    tot = {}
    for cnt in intr:
        for s in "LR":
            for k, n in cnt[s].items():
                kk = "%s>%s" % (s, k)
                tot[kk] = max(tot.get(kk, 0), n)
    c["gauntlet_intrusion_max_verts"] = tot
    c["gauntlet_foreign_intrusion_max"] = max(p["intr_foreign"] for p in per_frame)
    c["gauntlet_foreign_intrusion_frame"] = int(np.argmax([p["intr_foreign"] for p in per_frame]))
    if LABELS is not None:
        sol = [p["intr_foreign_solid"] for p in per_frame]
        c["gauntlet_foreign_solid_max"] = max(sol)
        c["gauntlet_foreign_solid_frame"] = int(np.argmax(sol))
    c["fingers_outside_gauntlet_max"] = max(p["finger_out"] for p in per_frame)
    c["fingers_outside_gauntlet_frame"] = int(np.argmax([p["finger_out"] for p in per_frame]))
    c["per_frame"] = per_frame
    # gates against the validated range
    for s in "LR":
        if c["elbow_max_" + s] > ELBOW_VALID + 2:
            prob("%s: elbow_%s folds to %.1f deg (validated to %.0f) at frame %d" % (an, s, c["elbow_max_" + s], ELBOW_VALID, c["elbow_argmax_" + s]))
        if c["knee_max_" + s] > KNEE_LIMIT + 2:
            prob("%s: knee_%s folds to %.1f deg (limit %.0f) at frame %d" % (an, s, c["knee_max_" + s], KNEE_LIMIT, c["knee_argmax_" + s]))
        elif c["knee_max_" + s] > KNEE_VALID + 2:
            R["notes"].append("%s: knee_%s %.1f deg at frame %d (the documented 135-150 deg soft spot)" % (an, s, c["knee_max_" + s], c["knee_argmax_" + s]))
        if c["wrist_swing_max_" + s] > 0.5:
            prob("%s: wrist_%s swings %.2f deg under a sleeve weapon" % (an, s, c["wrist_swing_max_" + s]))
        if not c["slide_exempt"] and slide[s] > 0.010:
            prob("%s: planted %s ball slides %.1f mm" % (an, s, slide[s] * 1000))
    # frames to render: the most extreme ones
    picks = {}
    for s in "LR":
        picks.setdefault(c["elbow_argmax_" + s], []).append("elbow_%s %.0f" % (s, c["elbow_max_" + s]))
        picks.setdefault(c["knee_argmax_" + s], []).append("knee_%s %.0f" % (s, c["knee_max_" + s]))
    if c["gauntlet_foreign_intrusion_max"]:
        picks.setdefault(c["gauntlet_foreign_intrusion_frame"], []).append("intrusion %d" % c["gauntlet_foreign_intrusion_max"])
    if c["flipped_tris_max"]:
        picks.setdefault(c["flipped_tris_frame"], []).append("flips %d" % c["flipped_tris_max"])
    render_pick[an] = picks
    clips[an] = c
    print("%-26s F%3d elbow %5.1f/%5.1f knee %5.1f/%5.1f wrist %.2f slide %s low %6.1f flips %3d crush %3d intr %s fing %d pelvis %.3f %s" % (
        an, F - 1, c["elbow_max_L"], c["elbow_max_R"], c["knee_max_L"], c["knee_max_R"],
        max(c["wrist_swing_max_L"], c["wrist_swing_max_R"]), c["foot_slide_mm"], c["lowest_vertex_mm"], c["flipped_tris_max"],
        c["crushed_tris_max"], c["gauntlet_foreign_intrusion_max"], c["fingers_outside_gauntlet_max"], c["pelvis_xz_drift_max_m"],
        ("seam %.1e x%.2f" % (c["loop_seam_pos_err_m"], c["loop_seam_accel_ratio"])) if c["loop"] else ""), flush=True)
R["clips"] = clips
R["render_pick"] = render_pick
R["seconds"] = round(time.time() - t0, 1)
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    json.dump(R, f, indent=1)
print("problems:", len(R["problems"]), "in %.0fs" % R["seconds"])
