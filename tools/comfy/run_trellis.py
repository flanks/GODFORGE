"""TRELLIS.2 image-to-3D blockout driver for GODFORGE heroes (pipeline stage 1).

Adapted from Ashen Covenant tools/trellis/run_trellis_crop.py (the user's own stdlib ComfyUI
driver, proven end to end there): same upload / patch / queue / poll-/history mechanics, the same
seed convention (node seed = base seed + node id) and the same grey conditioning background.
Changes for GODFORGE:

  - the graph is tools/comfy/trellis2_character_api.json, a verbatim copy of the user's
    trellis2_workflow_api.json (API format); every patch is applied in memory and recorded;
  - the TRELLIS.2 path is forced (node 316 = True) AND the Pixal3D branch (319 UNET, 298
    conditioning, MoGe 55/56/242) is pruned from the submitted graph, so Pixal3D can never load:
    only TRELLIS.2's MIT licence is cleared for this project;
  - several seeds run sequentially (one GPU job at a time, the RTX 4070 8 GB is shared with the
    game agent); a CUDA out-of-memory failure waits and retries instead of aborting;
  - --mask-only runs just the graph's own background removal + crop (nodes 122/193/192/248/312)
    and saves the mask and the conditioning crop, so the cut-out can be checked before a
    5-7 minute generation;
  - each run copies the ComfyUI conditioning crop and mask previews next to the GLB and writes a
    provenance JSON (graph sha256, patched inputs, seeds, prompt id, timings, output sha256/size).

OUTPUT IS A SCULPT REFERENCE ONLY (stage 1 of docs/ART_PIPELINE.md): dense topology, no
deformation loops, baked-texture artifacts. It is never shipped and never goes to assets/models/.

Usage:
  python tools/comfy/run_trellis.py <char> <image.png> --seed 101 [--seed 202 ...]
        [--faces 700000] [--tex 4096] [--bg #808080] [--own-mask] [--out DIR] [--timeout 3600]
  python tools/comfy/run_trellis.py <char> <image.png> --mask-only [--own-mask] [--out DIR]

  <char>       hero key (brax); output prefix 3d/GF_<char>_s<seed> in ComfyUI's output folder
  --out        default art/characters/<char>/source/
  --own-mask   use the PNG's own alpha instead of birefnet (LoadImage's MASK is 1 - alpha, so it
               goes through an InvertMask node, as in the Ashen Covenant driver)
  --faces/--tex  the graph's DecimateMesh target and bake size (defaults: the user's character
               settings, 700 000 faces / 4096 px)

Needs ComfyUI on 127.0.0.1:8188 with the TRELLIS.2 nodes and weights. Pure standard library.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
COMFY = "http://127.0.0.1:8188"
COMFY_OUTPUT = r"D:\Comfy-Desktop\ComfyUI-Shared\output"
GRAPH = os.path.join(HERE, "trellis2_character_api.json")

LOAD_IMAGE = "122"
BG_MODEL = "193"
BG_REMOVE = "192"
MASK_SWITCH = "248"
CROP = "312"
COND_PREVIEW = "302"   # PreviewImage of the crop: the exact image TRELLIS.2 is conditioned on
MASK_PREVIEW = "303"   # MaskPreview of the mask the crop used
MODEL_SWITCH = "316"   # PrimitiveBoolean, True = TRELLIS.2
SAVE = "322"           # Save3DAdvanced (the textured, decimated, smoothed mesh)
DECIMATE = "186"
TEX = "288"            # PrimitiveInt feeding UnwrapMesh.resolution and BakeTextureFromVoxel.texture_size
NORMAL_BAKE = "224"
MESH_INFO = "202"      # GetMeshInfo of the high-poly shape decode
SEED_NODES = ("3", "18", "23", "12")
PIXAL_ONLY = ("319", "298", "242", "56", "55")
PIXAL_SWITCHES = ("314", "315", "318")
OWN_MASK_NODE = "901"

LICENCE_NOTE = ("TRELLIS.2 code + weights MIT, run locally. The graph's DINOv3-L conditioning encoder is under "
                "Meta's DINOv3 licence (not MIT, not yet read for GODFORGE: pending_human gate in status.json); "
                "BiRefNet MIT per its repository. Pixal3D pruned.")
OOM_MARKERS = ("out of memory", "outofmemory", "cuda error: out of memory", "allocation on device")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def rel(path):
    try:
        return os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def http_json(url, payload=None, timeout=60):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def upload(path):
    """POST the image to ComfyUI's input folder (multipart by hand); returns the stored name."""
    boundary = "----gf" + uuid.uuid4().hex
    name = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    body = (
        ("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
         "Content-Type: image/png\r\n\r\n" % (boundary, name)).encode()
        + data + ("\r\n--%s\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--%s--\r\n"
                  % (boundary, boundary)).encode()
    )
    req = urllib.request.Request(COMFY + "/upload/image", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["name"]


def load_template():
    """The graph and the sha256 of its bytes with LF line endings (stable across git checkouts)."""
    with open(GRAPH, "rb") as f:
        raw = f.read().replace(b"\r\n", b"\n")
    return json.loads(raw), sha256_bytes(raw)


def prune_pixal(graph):
    """Drop the Pixal3D branch: the switches keep only their TRELLIS.2 (on_true) input."""
    for nid in PIXAL_SWITCHES:
        graph[nid]["inputs"].pop("on_false", None)
    for nid in PIXAL_ONLY:
        graph.pop(nid, None)
    for nid, node in graph.items():
        for key, val in node["inputs"].items():
            if isinstance(val, list) and len(val) == 2 and val[0] in PIXAL_ONLY:
                raise SystemExit("graph still references pruned Pixal3D node %s from %s.%s" % (val[0], nid, key))


def apply_mask_source(graph, own_mask):
    if own_mask:
        graph[OWN_MASK_NODE] = {"class_type": "InvertMask", "inputs": {"mask": [LOAD_IMAGE, 1]},
                                "_meta": {"title": "alpha -> object mask (added by run_trellis.py)"}}
        graph[MASK_SWITCH]["inputs"]["on_false"] = [OWN_MASK_NODE, 0]
        graph[MASK_SWITCH]["inputs"]["switch"] = False
    else:
        graph[MASK_SWITCH]["inputs"]["switch"] = True


def build(image_name, char, seed, faces, tex, bg, own_mask):
    graph, template_sha = load_template()
    patches = {}

    def patch(nid, key, value):
        graph[nid]["inputs"][key] = value
        patches["%s.%s" % (nid, key)] = value

    patch(LOAD_IMAGE, "image", image_name)
    patch(MODEL_SWITCH, "value", True)
    prune_pixal(graph)
    patches["pruned_pixal3d_nodes"] = list(PIXAL_ONLY)
    apply_mask_source(graph, own_mask)
    patches["%s.switch" % MASK_SWITCH] = graph[MASK_SWITCH]["inputs"]["switch"]
    if own_mask:
        patches["%s (added InvertMask)" % OWN_MASK_NODE] = "LoadImage alpha"
    # TRELLIS.2 is conditioned on the crop composited over this colour; the template's black would
    # swallow Brax's black-rock gauntlets (AC: a black statue on black came back as a flat sheet)
    patch(CROP, "background", bg)
    patch(SAVE, "filename_prefix", "3d/GF_%s_s%d" % (char, seed))
    for nid in SEED_NODES:
        patch(nid, "seed", seed + int(nid))
    patch(DECIMATE, "target_face_count", faces)
    patch(TEX, "value", tex)
    patch(NORMAL_BAKE, "resolution", min(tex, 2048))   # template 2048; AC lowers it with --tex for props
    return graph, template_sha, patches


def build_mask_only(image_name, char, bg, own_mask):
    """Only the graph's own cut-out nodes, plus two SaveImage nodes for the mask and the crop."""
    full, template_sha = load_template()
    graph = {nid: full[nid] for nid in (LOAD_IMAGE, BG_MODEL, BG_REMOVE, MASK_SWITCH, CROP)}
    graph[LOAD_IMAGE]["inputs"]["image"] = image_name
    apply_mask_source(graph, own_mask)
    graph[CROP]["inputs"]["masks"] = [MASK_SWITCH, 0]   # the template routes it through MaskPreview 303
    graph[CROP]["inputs"]["background"] = bg
    graph["910"] = {"class_type": "MaskToImage", "inputs": {"mask": [MASK_SWITCH, 0]}}
    graph["911"] = {"class_type": "SaveImage", "inputs": {"images": ["910", 0], "filename_prefix": "GF_%s_maskcheck_mask" % char}}
    graph["912"] = {"class_type": "SaveImage", "inputs": {"images": [CROP, 0], "filename_prefix": "GF_%s_maskcheck_crop" % char}}
    return graph, template_sha


def submit(graph):
    res = http_json(COMFY + "/prompt", {"prompt": graph, "client_id": "gf-trellis"})
    if res.get("node_errors"):
        raise SystemExit("ComfyUI rejected the graph: %s" % json.dumps(res["node_errors"])[:2000])
    return res["prompt_id"]


def wait_queue_idle(poll=15, max_wait=7200):
    """One GPU job at a time: do not queue behind someone else's ComfyUI work."""
    t0 = time.time()
    while time.time() - t0 < max_wait:
        q = http_json(COMFY + "/queue")
        if not q.get("queue_running") and not q.get("queue_pending"):
            return
        print("[trellis] ComfyUI busy (%d running, %d pending); waiting" % (len(q.get("queue_running", [])), len(q.get("queue_pending", []))))
        time.sleep(poll)
    raise SystemExit("ComfyUI queue never became idle")


class RunFailed(Exception):
    def __init__(self, message, oom):
        super().__init__(message)
        self.oom = oom


def wait(prompt_id, timeout):
    t0 = time.time()
    last = 0
    while time.time() - t0 < timeout:
        hist = http_json(COMFY + "/history/" + prompt_id, timeout=30)
        if prompt_id in hist:
            run = hist[prompt_id]
            status = run.get("status", {})
            if status.get("completed"):
                return run
            if status.get("status_str") == "error":
                msgs = [m for m in status.get("messages", []) if m[0] == "execution_error"]
                text = json.dumps(msgs)
                raise RunFailed("ComfyUI run failed: %s" % text[:3000], any(k in text.lower() for k in OOM_MARKERS))
        if time.time() - last > 60:
            print("[trellis]   ... %s running %.0f s" % (prompt_id[:8], time.time() - t0))
            last = time.time()
        time.sleep(5)
    raise SystemExit("timed out after %d s waiting for ComfyUI prompt %s" % (timeout, prompt_id))


def exec_times(run):
    stamps = {m[0]: m[1].get("timestamp") for m in run.get("status", {}).get("messages", []) if isinstance(m[1], dict)}
    start, end = stamps.get("execution_start"), stamps.get("execution_success")
    return {"execution_start_ms": start, "execution_end_ms": end,
            "execution_seconds": round((end - start) / 1000.0, 1) if start and end else None}


def fetch_view(item, dst):
    q = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
    with urllib.request.urlopen(COMFY + "/view?" + q, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    return dst


def comfy_version():
    try:
        return http_json(COMFY + "/system_stats")["system"].get("comfyui_version")
    except Exception:  # noqa: BLE001 - provenance nicety only
        return None


def run_mask_only(args, image_name, out_dir):
    graph, template_sha = build_mask_only(image_name, args.char, args.bg, args.own_mask)
    wait_queue_idle()
    pid = submit(graph)
    run = wait(pid, 600)
    saved = []
    for nid, suffix in (("911", "mask"), ("912", "crop")):
        item = run["outputs"][nid]["images"][0]
        dst = os.path.join(out_dir, "%s_maskcheck_%s.png" % (args.char, suffix))
        fetch_view(item, dst)
        saved.append(rel(dst))
    print("[trellis] mask check %s -> %s" % (pid[:8], ", ".join(saved)))
    return 0


def run_seed(args, image_name, image_sha, out_dir, seed):
    graph, template_sha, patches = build(image_name, args.char, seed, args.faces, args.tex, args.bg, args.own_mask)
    stem = "%s_trellis2_s%d" % (args.char, seed)
    attempt = 0
    while True:
        attempt += 1
        wait_queue_idle()
        t0 = time.time()
        pid = submit(graph)
        print("[trellis] %s: seed %d submitted as %s (attempt %d, %dk faces / %d px, TRELLIS.2 only)"
              % (args.char, seed, pid, attempt, args.faces // 1000, args.tex))
        try:
            run = wait(pid, args.timeout)
            break
        except RunFailed as e:
            if e.oom and attempt < args.oom_retries + 1:
                print("[trellis] CUDA out of memory (GPU shared); waiting %d s before retry" % args.oom_wait)
                time.sleep(args.oom_wait)
                continue
            raise SystemExit(str(e))
    wall = time.time() - t0

    out_rel = run["outputs"][SAVE]["result"][0]                  # e.g. "3d/GF_brax_s101_00001_.glb"
    src = os.path.join(COMFY_OUTPUT, out_rel.replace("/", os.sep))
    dst = os.path.join(out_dir, stem + ".glb")
    shutil.copyfile(src, dst)

    previews = {}
    for nid, suffix in ((COND_PREVIEW, "cond"), (MASK_PREVIEW, "mask")):
        items = run["outputs"].get(nid, {}).get("images", [])
        if items:
            p = fetch_view(items[0], os.path.join(out_dir, "%s_%s.png" % (stem, suffix)))
            previews[suffix] = rel(p)

    info = run["outputs"].get(MESH_INFO, {}).get("text", [""])[0]
    submitted = json.dumps(graph, sort_keys=True).encode()
    record = {
        "asset": args.char,
        "stage": "1-blockout",
        "use": "SCULPT REFERENCE ONLY - never shipped, never copied to assets/models/",
        "tool": "tools/comfy/run_trellis.py",
        "model": "TRELLIS.2 (trellis_2_int8_convrot, trellis_2 shape/texture VAEs bf16), DINOv3-L conditioning, "
                 "birefnet background removal; Pixal3D branch pruned (licence not cleared)",
        "licence": LICENCE_NOTE,
        "comfyui": {"url": COMFY, "version": comfy_version(), "prompt_id": pid, "output": out_rel,
                    "attempts": attempt},
        "input_image": {"path": rel(os.path.abspath(args.image)), "sha256": image_sha, "uploaded_as": image_name},
        "graph": {"template": rel(GRAPH), "template_sha256": template_sha,
                  "submitted_sha256": sha256_bytes(submitted), "patched_inputs": patches},
        "seed": seed,
        "node_seeds": {nid: seed + int(nid) for nid in SEED_NODES},
        "settings": {"target_faces": args.faces, "texture_px": args.tex, "background": args.bg,
                     "mask_source": "PNG alpha (InvertMask)" if args.own_mask else "birefnet"},
        "timings": dict(exec_times(run), wall_seconds=round(wall, 1),
                        generated=time.strftime("%Y-%m-%dT%H:%M:%S")),
        "high_poly_info": info.replace("\n", "; "),
        "output": {"path": rel(dst), "bytes": os.path.getsize(dst), "sha256": sha256_file(dst)},
        "previews": previews,
    }
    with open(os.path.join(out_dir, stem + ".json"), "w", newline="\n") as f:
        json.dump(record, f, indent=1)
        f.write("\n")
    print("[trellis] %s: seed %d done in %.0f s, %s -> %s (%.1f MB)"
          % (args.char, seed, wall, info.replace("\n", "; "), rel(dst), os.path.getsize(dst) / 1e6))
    return record


def main(argv):
    try:
        sys.stdout.reconfigure(line_buffering=True)   # progress lines reach a redirected log as they happen
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("char")
    ap.add_argument("image")
    ap.add_argument("--seed", type=int, action="append", default=[])
    ap.add_argument("--faces", type=int, default=700000)
    ap.add_argument("--tex", type=int, default=4096)
    ap.add_argument("--bg", default="#808080")
    ap.add_argument("--own-mask", action="store_true")
    ap.add_argument("--mask-only", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--oom-retries", type=int, default=3)
    ap.add_argument("--oom-wait", type=int, default=180)
    args = ap.parse_args(argv)

    if not os.path.isfile(args.image):
        raise SystemExit("image not found: %s" % args.image)
    out_dir = os.path.abspath(args.out or os.path.join(ROOT, "art", "characters", args.char, "source"))
    os.makedirs(out_dir, exist_ok=True)
    image_sha = sha256_file(args.image)
    image_name = upload(args.image)

    if args.mask_only:
        return run_mask_only(args, image_name, out_dir)
    if not args.seed:
        raise SystemExit("give at least one --seed")
    for seed in args.seed:          # sequential: one TRELLIS job on the GPU at a time
        run_seed(args, image_name, image_sha, out_dir, seed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
