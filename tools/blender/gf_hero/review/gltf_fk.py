"""Independent glTF reader for the stage 3-5 review: forward kinematics + linear blend skinning in numpy, written
from the glTF 2.0 spec only (nothing shared with the pipeline's validator or exporter). This is the maths Bevy runs:
joint world matrix = parent chain of node TRS; skinned vertex = sum_i w_i * (J_i @ IBM_i) @ v; a weapon scene is an
identity child of its socket node.
"""
import json
import struct

import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class GLB:
    def __init__(self, path):
        b = open(path, "rb").read()
        magic, ver, length = struct.unpack_from("<III", b, 0)
        assert magic == 0x46546C67 and ver == 2 and length == len(b), "not a glTF 2 binary"
        n, t = struct.unpack_from("<II", b, 12)
        assert t == 0x4E4F534A
        self.j = json.loads(b[20:20 + n])
        off = 20 + n
        n2, t2 = struct.unpack_from("<II", b, off)
        assert t2 == 0x004E4942
        self.bin = b[off + 8: off + 8 + n2]
        self.nodes = self.j["nodes"]
        self.names = [nd.get("name", "#%d" % i) for i, nd in enumerate(self.nodes)]
        self.idx = {nm: i for i, nm in enumerate(self.names)}
        self.parent = [-1] * len(self.nodes)
        for i, nd in enumerate(self.nodes):
            for c in nd.get("children", []):
                self.parent[c] = i
        # topological order (parents first)
        order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            if self.parent[i] >= 0:
                visit(self.parent[i])
            seen.add(i)
            order.append(i)
        for i in range(len(self.nodes)):
            visit(i)
        self.order = order
        self.rest_t = np.array([nd.get("translation", [0, 0, 0]) for nd in self.nodes], dtype=np.float64)
        self.rest_r = np.array([nd.get("rotation", [0, 0, 0, 1]) for nd in self.nodes], dtype=np.float64)
        self.rest_s = np.array([nd.get("scale", [1, 1, 1]) for nd in self.nodes], dtype=np.float64)
        for i, nd in enumerate(self.nodes):
            assert "matrix" not in nd, "matrix nodes not handled"

    def acc(self, i):
        a = self.j["accessors"][i]
        bv = self.j["bufferViews"][a["bufferView"]]
        dt = np.dtype(CT[a["componentType"]])
        nc = NC[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0)
        if stride and stride != dt.itemsize * nc:
            raw = np.frombuffer(self.bin, dtype=np.uint8, count=stride * a["count"], offset=off).reshape(a["count"], stride)
            arr = raw[:, :dt.itemsize * nc].copy().view(dt).reshape(a["count"], nc)
        else:
            arr = np.frombuffer(self.bin, dtype=dt, count=a["count"] * nc, offset=off).reshape(a["count"], nc)
        if a.get("normalized"):
            arr = arr.astype(np.float64) / np.iinfo(dt).max
        return arr

    # -- transforms --------------------------------------------------------------------------------------------------
    @staticmethod
    def qmat(q):
        """(..., 4) xyzw -> (..., 3, 3)"""
        q = q / np.linalg.norm(q, axis=-1, keepdims=True)
        x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
        m = np.empty(q.shape[:-1] + (3, 3))
        m[..., 0, 0] = 1 - 2 * (y * y + z * z)
        m[..., 0, 1] = 2 * (x * y - z * w)
        m[..., 0, 2] = 2 * (x * z + y * w)
        m[..., 1, 0] = 2 * (x * y + z * w)
        m[..., 1, 1] = 1 - 2 * (x * x + z * z)
        m[..., 1, 2] = 2 * (y * z - x * w)
        m[..., 2, 0] = 2 * (x * z - y * w)
        m[..., 2, 1] = 2 * (y * z + x * w)
        m[..., 2, 2] = 1 - 2 * (x * x + y * y)
        return m

    @classmethod
    def trs(cls, t, r, s):
        m = np.zeros(t.shape[:-1] + (4, 4))
        m[..., :3, :3] = cls.qmat(r) * s[..., None, :]
        m[..., :3, 3] = t
        m[..., 3, 3] = 1.0
        return m

    def world(self, T, R, S):
        """T, R, S: (F, N, 3/4/3) local channels -> (F, N, 4, 4) world matrices."""
        L = self.trs(T, R, S)
        W = np.empty_like(L)
        for i in self.order:
            p = self.parent[i]
            W[:, i] = L[:, i] if p < 0 else W[:, p] @ L[:, i]
        return W

    def rest_world(self):
        return self.world(self.rest_t[None], self.rest_r[None], self.rest_s[None])[0]

    # -- animation ---------------------------------------------------------------------------------------------------
    def anim_names(self):
        return [a["name"] for a in self.j.get("animations", [])]

    def sample(self, ai, fps=30.0):
        """-> times (F,), T, R, S (F, N, .), keyed {(node, path)}, raw {(node, path): (times, values)}"""
        a = self.j["animations"][ai]
        raw = {}
        tmax = 0.0
        for ch in a["channels"]:
            s = a["samplers"][ch["sampler"]]
            tt = self.acc(s["input"])[:, 0].astype(np.float64)
            vv = self.acc(s["output"]).astype(np.float64)
            assert s.get("interpolation", "LINEAR") in ("LINEAR", "STEP"), s.get("interpolation")
            raw[(ch["target"]["node"], ch["target"]["path"])] = (tt, vv, s.get("interpolation", "LINEAR"))
            tmax = max(tmax, tt[-1])
        nf = int(round(tmax * fps)) + 1
        times = np.arange(nf) / fps
        N = len(self.nodes)
        T = np.repeat(self.rest_t[None], nf, 0)
        R = np.repeat(self.rest_r[None], nf, 0)
        S = np.repeat(self.rest_s[None], nf, 0)
        for (node, path), (tt, vv, interp) in raw.items():
            if path == "rotation":
                # nlerp between the bracketing keys (samples sit on the frames, so this is exact there)
                k = np.clip(np.searchsorted(tt, times, side="right") - 1, 0, len(tt) - 1)
                k2 = np.clip(k + 1, 0, len(tt) - 1)
                dt = np.where(tt[k2] > tt[k], tt[k2] - tt[k], 1.0)
                u = np.clip((times - tt[k]) / dt, 0.0, 1.0)[:, None]
                if interp == "STEP":
                    u = u * 0
                q1, q2 = vv[k], vv[k2].copy()
                q2[(q1 * q2).sum(-1) < 0] *= -1
                q = q1 * (1 - u) + q2 * u
                R[:, node] = q / np.linalg.norm(q, axis=-1, keepdims=True)
            elif path in ("translation", "scale"):
                arr = np.stack([np.interp(times, tt, vv[:, c]) for c in range(3)], -1)
                (T if path == "translation" else S)[:, node] = arr
        return times, T, R, S, raw

    # -- skinning ----------------------------------------------------------------------------------------------------
    def skinned_mesh(self):
        for i, nd in enumerate(self.nodes):
            if "skin" in nd and "mesh" in nd:
                return i
        return None

    def mesh_data(self, mesh_index, prim=0):
        p = self.j["meshes"][mesh_index]["primitives"][prim]
        at = p["attributes"]
        out = {k: self.acc(v) for k, v in at.items()}
        out["indices"] = self.acc(p["indices"])[:, 0].astype(np.int64).reshape(-1, 3)
        out["material"] = p.get("material")
        return out

    def skin(self, si=0):
        sk = self.j["skins"][si]
        joints = sk["joints"]
        ibm = self.acc(sk["inverseBindMatrices"]).astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1)  # column-major
        return joints, ibm

    def lbs(self, W, joints, ibm, pos, J, Wt):
        """W: (N, 4, 4) node world; pos (V, 3); J (V, 4) joint indices into skin.joints; Wt (V, 4) -> (V, 3)"""
        M = W[joints] @ ibm                                    # (nj, 4, 4)
        Mv = M[J.astype(np.int64)]                             # (V, 4, 4, 4)
        blend = (Mv * Wt[:, :, None, None]).sum(1)             # (V, 4, 4)
        p = np.concatenate([pos, np.ones((len(pos), 1))], 1)
        return np.einsum("vij,vj->vi", blend, p)[:, :3]

    def image_bytes(self, ii):
        im = self.j["images"][ii]
        bv = self.j["bufferViews"][im["bufferView"]]
        o = bv.get("byteOffset", 0)
        return self.bin[o:o + bv["byteLength"]], im.get("mimeType")
