//! Authored glTF models over the greybox (docs/ART_PIPELINE.md §5, docs/art/*.md).
//!
//! * **Lookup by key.** `models/characters/<hero>.glb`, `models/weapons/<chassis>.glb` and
//!   `models/enemies/<enemy>.glb` under the asset root (`gf_engine::client::find_asset_dir`), each
//!   with its art sidecar `<key>.meta.json` (clip list, clip info, sockets, weapon variants). The
//!   first request reads the sidecar and starts Bevy's glTF load; [`Models::get`] answers `None`
//!   until the file and its dependencies are in, and forever for a key without a file, a failed
//!   load or under `--greybox` (env `GODFORGE_GREYBOX=1`). The caller keeps its greybox meanwhile.
//! * **One animation graph per asset** ([`ClipLib`]): every clip in one graph, full-body clips under
//!   a base blend node, upper-layer clips (`layer: "upper"`) beside it with the lower body masked
//!   out (`spine_01` and its children play them; see `anim.rs`). Instances share the graph.
//! * **Toon materials.** A spawned instance swaps each glTF `StandardMaterial` for a toon material
//!   cached per (source material, [`Skin`]), so every Brax in slot 1 shares one handle and a horde
//!   of one enemy kind shares a handful.
//! * **Weapons** ride the hero's `weapon_R` socket as an identity child; a gauntlet pair's `offhand`
//!   node moves to `weapon_L`, and the open-hand variants start hidden ([`HeroGear`]).
//!
//! Presentation only: the simulation never waits for or reads any of this.

use crate::ClientSet;
use crate::anim::{Animator, lower_body_targets};
use crate::materials::{InkHull, ToonMaterial, ToonStyle, toon_from_standard};
use crate::palette::{Palette, hdr, hex, mix, status_color};
use gf_engine::bevy::animation::{AnimationTargetId, graph::AnimationNodeIndex};
use gf_engine::bevy::camera::visibility::NoFrustumCulling;
use gf_engine::bevy::mesh::skinning::SkinnedMesh;
use gf_engine::bevy::world_serialization::WorldInstanceReady;
use gf_engine::client::{NotShadowCaster, NotShadowReceiver, SystemParam};
use gf_engine::prelude::*;
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::Arc;

/// Mask group of the lower body (root, pelvis, legs and anything hanging off them).
pub const LOWER_BODY_GROUP: u32 = 0;

/// Which folder of `assets/models` a key lives in.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ModelKind {
    Character,
    Weapon,
    Enemy,
}

impl ModelKind {
    fn dir(self) -> &'static str {
        match self {
            ModelKind::Character => "characters",
            ModelKind::Weapon => "weapons",
            ModelKind::Enemy => "enemies",
        }
    }
}

/// One hand's weapon variant through a clip (`clip_info.<clip>.weapon_variant.<L|R>`): which mesh
/// shows at frame 0, and the times (s) where it swaps between fist and open.
#[derive(Clone, Debug, Default)]
pub struct HandVariant {
    pub open_at_start: bool,
    pub swaps: Vec<f32>,
}

impl HandVariant {
    /// Is the open-hand variant showing at `t` seconds into the clip?
    pub fn open_at(&self, t: f32) -> bool {
        (self.swaps.iter().filter(|s| t >= **s).count() % 2 == 1) != self.open_at_start
    }
}

/// What the sidecar says about one clip.
#[derive(Clone, Debug, Default)]
pub struct ClipMeta {
    pub looping: bool,
    /// `layer: "upper"`: played over locomotion with the lower body masked out.
    pub upper: bool,
    /// Ground speed the feet are planted at (locomotion: playback rate = speed / this).
    pub design_speed: Option<f32>,
    /// Metres travelled per cycle of an enemy's move loop (`move_cycle_m`): the loop plays at
    /// `speed / move_cycle` cycles per second.
    pub move_cycle: Option<f32>,
    /// Named events (hit frames, launch, slam…) at their time in seconds.
    pub events: Vec<(String, f32)>,
    /// Per hand (L, R), when the clip swaps a gauntlet pair between fist and open.
    pub hands: Option<[HandVariant; 2]>,
}

impl ClipMeta {
    pub fn event(&self, name: &str) -> Option<f32> {
        self.events.iter().find(|(n, _)| n == name).map(|(_, t)| *t)
    }
}

/// The parts of a sidecar the client uses (the whole JSON stays in `raw`).
#[derive(Clone, Debug, Default)]
pub struct ModelMeta {
    pub key: String,
    /// Clip info keyed by the short name (`idle`, `run`, `jab_l`: no `<key>_` prefix, no `@loop`).
    pub clips: HashMap<String, ClipMeta>,
    /// A hero's own weapon (`weapon.default`).
    pub default_weapon: Option<String>,
    /// A weapon's hand variants: node names of the fist and open meshes, (L, R).
    pub fist_nodes: Option<[String; 2]>,
    pub open_nodes: Option<[String; 2]>,
    pub height: Option<f32>,
    /// An enemy's looks (`variant_set`): one file per look, the same rig, sockets and clip
    /// suffixes. Empty when the key has one look.
    pub variants: Vec<String>,
    /// Bounding box (glTF axes: +Y up, +Z the creature's front), in metres.
    pub bounds: Option<(Vec3, Vec3)>,
    /// Socket positions in the rest pose (glTF axes), by name.
    pub sockets: HashMap<String, Vec3>,
    pub raw: Value,
}

/// Seconds of a clip event: a number, or the first of a list (`spawn: [0.63, 1.0, 1.37]`).
fn event_time(v: &Value) -> Option<f32> {
    v.as_f64().or_else(|| v.as_array()?.first()?.as_f64()).map(|t| t as f32)
}

fn vec3(v: &Value) -> Option<Vec3> {
    let a = v.as_array()?;
    Some(Vec3::new(a.first()?.as_f64()? as f32, a.get(1)?.as_f64()? as f32, a.get(2)?.as_f64()? as f32))
}

impl ModelMeta {
    fn parse(key: &str, raw: Value) -> ModelMeta {
        let mut clips = HashMap::new();
        let info = raw.get("clip_info");
        // `move_cycle_m`: one number (the move loop's), or per loop (`{"move@loop": 4.45, …}`).
        let cycles = raw.get("move_cycle_m");
        let cycle_of = |short: &str| -> Option<f32> {
            match cycles? {
                Value::Object(m) => {
                    m.iter().find(|(k, _)| k.strip_suffix("@loop").unwrap_or(k) == short).and_then(|(_, v)| v.as_f64())
                }
                v if short == "move" => v.as_f64(),
                _ => None,
            }
            .map(|c| c as f32)
        };
        for full in raw.get("clips").and_then(Value::as_array).into_iter().flatten().filter_map(Value::as_str) {
            let short = short_clip_name(key, full);
            // Enemy sidecars key `clip_info` by the short name (`idle@loop`, `slam_trail`).
            let ci = info.and_then(|i| {
                i.get(full)
                    .or_else(|| i.get(short))
                    .or_else(|| i.get(full.strip_prefix(key).and_then(|r| r.strip_prefix('_')).unwrap_or(full)))
            });
            let fps = ci.and_then(|c| c.get("fps")).and_then(Value::as_f64).unwrap_or(30.0) as f32;
            let hand = |side: &str| -> Option<HandVariant> {
                let h = ci?.get("weapon_variant")?.get(side)?;
                Some(HandVariant {
                    open_at_start: h.get("start").and_then(Value::as_str) == Some("open"),
                    swaps: h
                        .get("swap_frames")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                        .filter_map(Value::as_f64)
                        .map(|f| f as f32 / fps)
                        .collect(),
                })
            };
            let mut events: Vec<(String, f32)> = ci
                .and_then(|c| c.get("events"))
                .and_then(Value::as_object)
                .map(|evs| {
                    evs.iter()
                        .filter_map(|(n, e)| {
                            let t = e
                                .get("time_s")
                                .and_then(Value::as_f64)
                                .or_else(|| e.get("frame").and_then(Value::as_f64).map(|f| f / f64::from(fps)))?;
                            Some((n.clone(), t as f32))
                        })
                        .collect()
                })
                .unwrap_or_default();
            // Enemy sidecars: `clip_info.<clip>.events_s` and the top-level `clip_events_s`.
            let timed = ci
                .and_then(|c| c.get("events_s"))
                .into_iter()
                .chain(raw.get("clip_events_s").and_then(|e| e.get(full)))
                .filter_map(Value::as_object)
                .flatten();
            for (n, e) in timed {
                if let Some(t) = event_time(e) {
                    events.push((n.trim_end_matches("_s").to_string(), t));
                }
            }
            let meta = ClipMeta {
                looping: full.ends_with("@loop")
                    || ci.and_then(|c| c.get("loop")).and_then(Value::as_bool) == Some(true),
                upper: ci.and_then(|c| c.get("layer")).and_then(Value::as_str) == Some("upper"),
                design_speed: ci.and_then(|c| c.get("design_speed_mps")).and_then(Value::as_f64).map(|v| v as f32),
                move_cycle: ci
                    .and_then(|c| c.get("move_cycle_m"))
                    .and_then(Value::as_f64)
                    .map(|v| v as f32)
                    .or_else(|| cycle_of(short)),
                events,
                hands: match (hand("L"), hand("R")) {
                    (Some(l), Some(r)) => Some([l, r]),
                    _ => None,
                },
            };
            clips.insert(short.to_string(), meta);
        }
        let bounds = raw.get("bounds_m").and_then(|b| Some((vec3(b.get("min")?)?, vec3(b.get("max")?)?)));
        let sockets = raw
            .get("sockets")
            .and_then(Value::as_object)
            .map(|s| s.iter().filter_map(|(n, v)| Some((n.clone(), vec3(v.get("translation")?)?))).collect())
            .unwrap_or_default();
        let looks = raw
            .get("variant_set")
            .and_then(Value::as_array)
            .map(|v| v.iter().filter_map(Value::as_str).map(str::to_string).collect())
            .unwrap_or_default();
        let pair = |v: Option<&Value>| -> Option<[String; 2]> {
            let v = v?;
            Some([v.get("L")?.as_str()?.to_string(), v.get("R")?.as_str()?.to_string()])
        };
        let variants = raw.get("variants");
        ModelMeta {
            key: key.to_string(),
            clips,
            default_weapon: raw.pointer("/weapon/default").and_then(Value::as_str).map(str::to_string),
            fist_nodes: pair(variants.and_then(|v| v.get("fist"))),
            open_nodes: pair(variants.and_then(|v| v.get("open"))),
            height: raw.get("height_m").and_then(Value::as_f64).map(|h| h as f32),
            variants: looks,
            bounds,
            sockets,
            raw,
        }
    }
}

/// `brax_idle@loop` → `idle`; `clinker_move@loop` → `move`.
pub fn short_clip_name<'a>(key: &str, full: &'a str) -> &'a str {
    let s = full.strip_suffix("@loop").unwrap_or(full);
    s.strip_prefix(key).and_then(|r| r.strip_prefix('_')).unwrap_or(s)
}

/// One clip in an asset's animation graph.
#[derive(Clone, Debug)]
pub struct AnimClip {
    pub node: AnimationNodeIndex,
    pub duration: f32,
    pub meta: ClipMeta,
}

/// Every clip of one asset in one shared graph.
#[derive(Clone, Debug)]
pub struct ClipLib {
    pub graph: Handle<AnimationGraph>,
    pub clips: HashMap<String, AnimClip>,
    /// Some clip plays on the upper layer (the lower-body mask group is filled on first spawn).
    pub layered: bool,
}

/// A loaded model, ready to spawn.
#[derive(Debug)]
pub struct Model {
    pub kind: ModelKind,
    pub key: String,
    pub meta: ModelMeta,
    pub gltf: Handle<Gltf>,
    pub scene: Handle<WorldAsset>,
    pub anim: Option<ClipLib>,
}

impl Model {
    pub fn clip(&self, name: &str) -> Option<&AnimClip> {
        self.anim.as_ref()?.clips.get(name)
    }
}

enum Entry {
    /// No file (or `--greybox`): the greybox stays.
    Missing,
    Loading {
        meta: Box<ModelMeta>,
        gltf: Handle<Gltf>,
    },
    Ready(Arc<Model>),
    Failed,
}

/// Every model the client has asked for, by kind and key.
#[derive(Resource)]
pub struct Models {
    root: PathBuf,
    /// `--greybox`: QA the greybox look (no file is ever loaded).
    pub greybox: bool,
    entries: HashMap<(ModelKind, String), Entry>,
}

impl Models {
    pub fn new(root: PathBuf, greybox: bool) -> Self {
        Models { root, greybox, entries: HashMap::new() }
    }

    /// The asset root models load from.
    pub fn root(&self) -> &PathBuf {
        &self.root
    }

    /// Asset path of a key's GLB (relative to the asset root).
    pub fn asset_path(kind: ModelKind, key: &str) -> String {
        format!("models/{}/{key}.glb", kind.dir())
    }

    /// Does a file exist for this key (and is the greybox not forced)?
    pub fn exists(&self, kind: ModelKind, key: &str) -> bool {
        !self.greybox && self.root.join(Self::asset_path(kind, key)).is_file()
    }

    /// The model once loaded; starts the load on the first call. `None` while loading and for
    /// keys without a model (see [`Models::missing`]).
    pub fn get(&mut self, kind: ModelKind, key: &str, server: &AssetServer) -> Option<Arc<Model>> {
        let id = (kind, key.to_string());
        if !self.entries.contains_key(&id) {
            let entry = self.start(kind, key, server);
            self.entries.insert(id.clone(), entry);
        }
        match self.entries.get(&id) {
            Some(Entry::Ready(m)) => Some(m.clone()),
            _ => None,
        }
    }

    /// Will this key never have a model this session (no file, a failed load, `--greybox`)?
    pub fn missing(&self, kind: ModelKind, key: &str) -> bool {
        matches!(self.entries.get(&(kind, key.to_string())), Some(Entry::Missing | Entry::Failed))
    }

    /// The looks of a key (its sidecar's `variant_set`, files that exist), starting every load:
    /// `[key]` for a key with one look, empty for a key without a model.
    pub fn looks(&mut self, kind: ModelKind, key: &str, server: &AssetServer) -> Vec<String> {
        self.get(kind, key, server);
        let set = match self.entries.get(&(kind, key.to_string())) {
            Some(Entry::Loading { meta, .. }) => meta.variants.clone(),
            Some(Entry::Ready(m)) => m.meta.variants.clone(),
            _ => return Vec::new(),
        };
        let mut looks: Vec<String> = set.into_iter().filter(|k| self.exists(kind, k)).collect();
        if looks.is_empty() {
            looks.push(key.to_string());
        }
        for k in &looks {
            self.get(kind, k, server);
        }
        looks
    }

    fn start(&self, kind: ModelKind, key: &str, server: &AssetServer) -> Entry {
        if !self.exists(kind, key) {
            return Entry::Missing;
        }
        let path = Self::asset_path(kind, key);
        let meta_path = self.root.join(format!("models/{}/{key}.meta.json", kind.dir()));
        let raw = std::fs::read_to_string(&meta_path)
            .ok()
            .and_then(|s| match serde_json::from_str::<Value>(&s) {
                Ok(v) => Some(v),
                Err(e) => {
                    warn!("model {path}: bad sidecar {}: {e}", meta_path.display());
                    None
                }
            })
            .unwrap_or(Value::Null);
        info!("model {path}: loading");
        Entry::Loading { meta: Box::new(ModelMeta::parse(key, raw)), gltf: server.load(path) }
    }
}

/// Finish loads: build each asset's animation graph once its clips are in.
fn prepare_models(
    mut models: ResMut<Models>,
    server: Res<AssetServer>,
    gltfs: Res<Assets<Gltf>>,
    clips: Res<Assets<AnimationClip>>,
    mut graphs: ResMut<Assets<AnimationGraph>>,
) {
    if !models.entries.values().any(|e| matches!(e, Entry::Loading { .. })) {
        return;
    }
    for ((kind, key), entry) in models.entries.iter_mut() {
        let Entry::Loading { meta, gltf } = entry else { continue };
        if server.load_state(gltf.id()).is_failed() || server.recursive_dependency_load_state(gltf.id()).is_failed() {
            warn!("model {}: failed to load, keeping the greybox", Models::asset_path(*kind, key));
            *entry = Entry::Failed;
            continue;
        }
        if !server.is_loaded_with_dependencies(gltf.id()) {
            continue;
        }
        let Some(asset) = gltfs.get(&*gltf) else { continue };
        let Some(scene) = asset.default_scene.clone().or_else(|| asset.scenes.first().cloned()) else {
            warn!("model {}: no scene", Models::asset_path(*kind, key));
            *entry = Entry::Failed;
            continue;
        };
        let anim = (!asset.named_animations.is_empty()).then(|| {
            let mut graph = AnimationGraph::new();
            let base = graph.add_blend(1.0, graph.root);
            let mut lib = HashMap::new();
            let mut layered = false;
            let mut names: Vec<_> = asset.named_animations.iter().collect();
            names.sort_by(|a, b| a.0.cmp(b.0));
            for (full, handle) in names {
                let short = short_clip_name(key, full).to_string();
                let mut m = meta.clips.get(&short).cloned().unwrap_or_default();
                m.looping |= full.ends_with("@loop");
                let node = if m.upper {
                    layered = true;
                    graph.add_clip_with_mask(handle.clone(), 1 << LOWER_BODY_GROUP, 1.0, graph.root)
                } else {
                    graph.add_clip(handle.clone(), 1.0, base)
                };
                let duration = clips.get(handle).map_or(1.0, AnimationClip::duration);
                lib.insert(short, AnimClip { node, duration, meta: m });
            }
            ClipLib { graph: graphs.add(graph), clips: lib, layered }
        });
        let n = anim.as_ref().map_or(0, |a| a.clips.len());
        info!("model {}: ready ({n} clips)", Models::asset_path(*kind, key));
        let (meta, gltf) = (std::mem::take(&mut **meta), gltf.clone());
        *entry = Entry::Ready(Arc::new(Model { kind: *kind, key: key.clone(), meta, gltf, scene, anim }));
    }
}

// ───────────────────────────── materials ─────────────────────────────

/// How a glTF surface is painted.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Skin {
    /// A hero in slot n: rim in the player's colour.
    Hero(u8),
    /// A downed hero: the Soul-Tether wraith (translucent, glowing in the player's colour).
    Ghost(u8),
    /// A hero's weapon: a quieter rim in the player's colour.
    Gear(u8),
    /// Enemies: warm red rim, with a tint (hit flash, wind-up blink, status). `hot` pushes the
    /// emissive toward white (the Slag King's Final Pour). `big` (bosses, elites, bodies over 1 m
    /// of radius): a narrow, dim rim (a wide one outlined every plate of a many-part boss like a
    /// neon wireframe), and statuses only recolour that rim, never the painted body.
    Foe { tint: FoeTint, hot: bool, big: bool },
}

impl Skin {
    /// The plain enemy skin.
    pub const FOE: Skin = Skin::Foe { tint: FoeTint::Base, hot: false, big: false };

    /// The plain skin of an enemy, big or not.
    pub fn foe(big: bool) -> Skin {
        Skin::Foe { tint: FoeTint::Base, hot: false, big }
    }
}

/// A tint over an enemy's painted material. A handful per asset, cached like every skin, so a
/// flashing horde swaps between shared handles and keeps batching.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum FoeTint {
    Base,
    /// A swarm hit: white-hot.
    Flash,
    /// An elite or boss hit: a warm lift that keeps the painted read.
    SoftFlash,
    /// The wind-up blink (the engine's red telegraph on the body).
    Warn,
    Frozen,
    Stunned,
    /// Status bit n (burn, shock, void, plague, bleed, …).
    Status(u8),
}

/// Toon materials made from glTF materials, per (source, skin), and the heroes' ink hulls.
#[derive(Resource, Default)]
pub struct SkinCache {
    toons: HashMap<(AssetId<StandardMaterial>, Skin), Handle<ToonMaterial>>,
    /// The dark ink hull every hero and weapon shares, and each slot's halo hull.
    ink: Option<Handle<InkHull>>,
    halos: [Option<Handle<InkHull>>; 4],
}

/// Width (m) of a hero's ink contour: about 2 px at the default zoom (22 m of view over 900 px).
pub const INK_WIDTH: f32 = 0.05;
/// Width (m) of the halo around the ink, in the player's colour: about 1 px beyond it.
pub const HALO_WIDTH: f32 = 0.078;
/// How far (m) the halo hull sits behind the ink hull (so the ink stays on top of it).
const HALO_PUSH: f32 = 0.35;
/// The contour's ink (a warm near-black, the greybox hulls' family).
const HULL_INK: &str = "#140A10";

impl SkinCache {
    pub fn get(
        &mut self,
        source: &Handle<StandardMaterial>,
        skin: Skin,
        stds: &Assets<StandardMaterial>,
        toons: &mut Assets<ToonMaterial>,
        pal: &Palette,
    ) -> Option<Handle<ToonMaterial>> {
        let key = (source.id(), skin);
        if let Some(h) = self.toons.get(&key) {
            return Some(h.clone());
        }
        let std = stds.get(source)?;
        let h = toons.add(skin_material(std, skin, pal));
        self.toons.insert(key, h.clone());
        Some(h)
    }

    /// The (ink, halo) hull materials of a hero in `slot`.
    pub fn hulls(
        &mut self,
        slot: u8,
        hulls: &mut Assets<InkHull>,
        pal: &Palette,
    ) -> (Handle<InkHull>, Handle<InkHull>) {
        let ink = self.ink.get_or_insert_with(|| hulls.add(InkHull::new(hex(HULL_INK), INK_WIDTH, 0.0))).clone();
        let halo = self.halos[slot as usize % 4]
            .get_or_insert_with(|| hulls.add(InkHull::new(hdr(pal.player(slot), 1.5), HALO_WIDTH, HALO_PUSH)))
            .clone();
        (ink, halo)
    }
}

/// The material stores and caches a glTF skin swap needs.
#[derive(SystemParam)]
pub struct SkinPaint<'w> {
    pub stds: Res<'w, Assets<StandardMaterial>>,
    pub toons: ResMut<'w, Assets<ToonMaterial>>,
    pub hulls: ResMut<'w, Assets<InkHull>>,
    pub cache: ResMut<'w, SkinCache>,
    pub pal: Res<'w, Palette>,
}

/// A glTF material in the game's toon look.
fn skin_material(std: &StandardMaterial, skin: Skin, pal: &Palette) -> ToonMaterial {
    let mut base = std.clone();
    // Painted textures carry their own value; the toon ramp does the lighting.
    base.perceptual_roughness = base.perceptual_roughness.max(0.7);
    base.metallic = base.metallic.min(0.2);
    match skin {
        Skin::Hero(slot) => {
            // The ink hull (`spawn_hulls`) closes the silhouette; the painted ink edge darkens the
            // grazing faces inside it. The rim is the player's colour pushed toward white: a pure
            // P1 gold vanished into Brax's embers and Valdris's gilt, a pale gold-white edge
            // lifts any painted body off the warm Cinder ground.
            let style = ToonStyle {
                rim: hdr(mix(pal.player(slot), Color::WHITE, 0.45), 2.6),
                rim_strength: 1.3,
                rim_width: 0.45,
                ink_width: 0.16,
                ink: 0.55,
                lift: 0.4,
                ..ToonStyle::hero(pal.player(slot))
            };
            toon_from_standard(base, &style)
        }
        Skin::Gear(slot) => {
            let style = ToonStyle {
                rim_strength: 0.5,
                rim_width: 0.26,
                ink_width: 0.14,
                ink: 0.5,
                lift: 0.3,
                ..ToonStyle::hero(pal.player(slot))
            };
            toon_from_standard(base, &style)
        }
        Skin::Ghost(slot) => {
            let c = pal.player(slot);
            base.base_color = base.base_color.with_alpha(0.38);
            base.alpha_mode = AlphaMode::Blend;
            let l = hdr(c, 0.45).to_linear();
            base.emissive = LinearRgba::rgb(l.red, l.green, l.blue) + base.emissive * 0.5;
            toon_from_standard(base, &ToonStyle::hero(c))
        }
        Skin::Foe { tint, hot, big } => {
            if hot {
                // The Final Pour: every glow runs hotter and whiter (the white crown, the core).
                base.emissive =
                    LinearRgba::rgb(base.emissive.red * 2.2, base.emissive.green * 2.1, base.emissive.blue * 1.9)
                        + LinearRgba::rgb(0.05, 0.04, 0.03);
            }
            let tone = |c: Color| {
                let l = c.to_linear();
                LinearRgba::rgb(l.red, l.green, l.blue)
            };
            let mul = |base: &mut StandardMaterial, k: LinearRgba| {
                let c = base.base_color.to_linear();
                base.base_color = Color::linear_rgba(c.red * k.red, c.green * k.green, c.blue * k.blue, c.alpha);
            };
            let mut style = ToonStyle { ink_width: 0.12, ink: 0.5, ..ToonStyle::foe() };
            if big {
                style.rim = hdr(hex(FOE_RIM_BIG), 1.2);
                style.rim_width = 0.15;
            }
            // A status on a big body: its painted colours stay, only the rim takes the status
            // colour (the status itself shows as motes at its hit centre, `vfx.rs`).
            let accent = |style: &mut ToonStyle, c: Color| {
                style.rim = hdr(c, 1.8);
                style.rim_strength = 0.6;
                style.rim_width = 0.15;
            };
            match tint {
                FoeTint::Base => {}
                FoeTint::Flash => {
                    // The whole body goes white-hot for a frame or two (the painted glow map would
                    // only light the cracks).
                    mul(&mut base, LinearRgba::rgb(1.6, 1.5, 1.4));
                    base.emissive_texture = None;
                    base.emissive = LinearRgba::rgb(1.6, 1.35, 1.05);
                    style.rim_strength = 1.4;
                }
                FoeTint::SoftFlash => {
                    mul(&mut base, LinearRgba::rgb(1.35, 1.25, 1.12));
                    base.emissive = base.emissive * 1.7 + LinearRgba::rgb(0.06, 0.04, 0.02);
                    style.rim_strength = 1.3;
                }
                FoeTint::Warn => {
                    // The wind-up blink heats the body toward molten orange (multiplying it by the
                    // danger red turned a cinderling's maw salmon pink); the rim carries the red.
                    let hot = tone(hex(WARN_GLOW));
                    mul(&mut base, LinearRgba::rgb(1.12, 1.0, 0.88));
                    base.emissive = base.emissive * 1.4 + hot * if big { 0.18 } else { 0.4 };
                    style.rim = hdr(pal.danger, if big { 1.8 } else { 2.6 });
                }
                FoeTint::Frozen if big => accent(&mut style, hex(FROST)),
                FoeTint::Frozen => {
                    mul(&mut base, LinearRgba::rgb(0.75, 0.95, 1.35));
                    base.emissive = base.emissive * 0.35 + LinearRgba::rgb(0.02, 0.05, 0.08);
                    style.rim = hdr(hex(FROST), 2.2);
                }
                FoeTint::Stunned if big => accent(&mut style, hex(STUN)),
                FoeTint::Stunned => {
                    mul(&mut base, LinearRgba::rgb(1.3, 1.2, 0.8));
                    style.rim = hdr(hex(STUN), 2.2);
                }
                FoeTint::Status(bit) if big => accent(&mut style, status_color(bit)),
                FoeTint::Status(bit) => {
                    let s = tone(status_color(bit));
                    mul(&mut base, LinearRgba::rgb(0.55 + s.red * 0.7, 0.55 + s.green * 0.7, 0.55 + s.blue * 0.7));
                    base.emissive = base.emissive + s * 0.12;
                    style.rim = hdr(status_color(bit), 2.2);
                }
            }
            toon_from_standard(base, &style)
        }
    }
}

/// A big foe's base rim: the warm red, dimmer and narrower than the horde's.
const FOE_RIM_BIG: &str = "#FF6A44";
/// The wind-up heat on a body (molten orange).
const WARN_GLOW: &str = "#FFB050";
const FROST: &str = "#BFE8FF";
const STUN: &str = "#FFE27A";

// ───────────────────────────── instances ─────────────────────────────

/// A spawned model: its asset and how it is painted. Put on the entity carrying the
/// `WorldAssetRoot`; [`ModelParts`] appears once the instance is ready.
#[derive(Component)]
pub struct ModelInstance {
    pub model: Arc<Model>,
    pub skin: Skin,
}

/// What a ready instance is made of.
#[derive(Component, Debug, Default)]
pub struct ModelParts {
    /// The entity carrying the `AnimationPlayer` (and the [`Animator`]).
    pub player: Option<Entity>,
    /// Named nodes (bones, sockets, weapon nodes) by name.
    pub nodes: HashMap<String, Entity>,
    /// Mesh entities and their glTF material.
    pub meshes: Vec<(Entity, Handle<StandardMaterial>)>,
    /// The skin the meshes wear now.
    pub skin: Option<Skin>,
}

impl ModelParts {
    pub fn node(&self, name: &str) -> Option<Entity> {
        self.nodes.get(name).copied()
    }
}

/// Paint every mesh of a ready instance with `skin` (nothing to do when it already wears it).
pub fn reskin(
    commands: &mut Commands,
    parts: &mut ModelParts,
    skin: Skin,
    cache: &mut SkinCache,
    stds: &Assets<StandardMaterial>,
    toons: &mut Assets<ToonMaterial>,
    pal: &Palette,
) {
    if parts.skin == Some(skin) {
        return;
    }
    parts.skin = Some(skin);
    for (e, source) in &parts.meshes {
        if let Some(toon) = cache.get(source, skin, stds, toons, pal) {
            commands.entity(*e).insert(MeshMaterial3d(toon));
        }
    }
}

/// Spawn a model instance under `parent`, hidden until its materials are swapped and its first
/// pose is set.
pub fn spawn_model(commands: &mut Commands, parent: Entity, model: &Arc<Model>, skin: Skin, tf: Transform) -> Entity {
    commands
        .spawn((
            WorldAssetRoot(model.scene.clone()),
            ModelInstance { model: model.clone(), skin },
            tf,
            Visibility::Hidden,
            ChildOf(parent),
        ))
        .id()
}

/// A weapon instance and the hero model it belongs to.
#[derive(Component)]
pub struct WeaponOf(pub Entity);

/// A hero model's weapon: what the rig wants and what is attached.
#[derive(Component, Debug, Default)]
pub struct HeroGear {
    pub slot: u8,
    /// The equipped chassis (set by the rig every frame).
    pub want: Option<String>,
    /// The chassis whose model is attached (or being attached).
    pub attached: Option<String>,
    pub weapon: Option<Entity>,
    /// A gauntlet pair's left piece, re-parented to `weapon_L`.
    pub offhand: Option<Entity>,
    /// The chassis has no model: the rig keeps its greybox gun.
    pub greybox_gun: bool,
    /// Projectile / strike origin of the attached weapon.
    pub muzzle: Option<Entity>,
    /// Fist and open meshes of a gauntlet pair, (L, R).
    pub fist: [Option<Entity>; 2],
    pub open: [Option<Entity>; 2],
    /// Which hands show the open variant now.
    pub hands_open: [bool; 2],
    /// Downed: hero and weapon wear the ghost skin.
    pub ghost: bool,
}

/// Instances whose graph already has its lower-body mask group.
#[derive(Resource, Default)]
struct MaskedGraphs(HashSet<AssetId<AnimationGraph>>);

#[allow(clippy::too_many_arguments)]
fn on_instance_ready(
    ev: On<WorldInstanceReady>,
    mut commands: Commands,
    instances: Query<(&ModelInstance, Option<&WeaponOf>)>,
    children: Query<&Children>,
    names: Query<&Name>,
    std_meshes: Query<(&MeshMaterial3d<StandardMaterial>, &Mesh3d, Option<&SkinnedMesh>)>,
    targets: Query<(&AnimationTargetId, Option<&ChildOf>)>,
    mut players: Query<&mut AnimationPlayer>,
    hero_parts: Query<&ModelParts>,
    mut gears: Query<&mut HeroGear>,
    mut paint: SkinPaint,
    mut graphs: ResMut<Assets<AnimationGraph>>,
    mut masked: ResMut<MaskedGraphs>,
) {
    let root = ev.entity;
    let Ok((inst, weapon_of)) = instances.get(root) else { return };
    let mut parts = ModelParts { skin: Some(inst.skin), ..default() };
    for e in children.iter_descendants(root) {
        if let Ok(name) = names.get(e) {
            parts.nodes.entry(name.as_str().to_string()).or_insert(e);
        }
        if players.contains(e) && parts.player.is_none() {
            parts.player = Some(e);
        }
        if let Ok((m, _, _)) = std_meshes.get(e) {
            parts.meshes.push((e, m.0.clone()));
        }
    }
    let SkinPaint { stds, toons, hulls, cache, pal } = &mut paint;
    for (e, source) in &parts.meshes {
        if let Some(toon) = cache.get(source, inst.skin, stds, toons, pal) {
            commands.entity(*e).remove::<MeshMaterial3d<StandardMaterial>>().insert(MeshMaterial3d(toon));
        }
    }
    // Heroes and their weapons wear the ink contour (and the halo in the player's colour).
    if let Skin::Hero(slot) | Skin::Gear(slot) = inst.skin {
        let (ink, halo) = cache.hulls(slot, hulls, pal);
        for (e, _) in &parts.meshes {
            let Ok((_, mesh, skinned)) = std_meshes.get(*e) else { continue };
            for m in [&ink, &halo] {
                // A child of the mesh: it shows and hides with it (the gauntlets' fist / open
                // swap), and a rigid part inherits its transform (a skinned one follows its joints).
                let mut hull = commands.spawn((
                    Mesh3d(mesh.0.clone()),
                    MeshMaterial3d(m.clone()),
                    Transform::IDENTITY,
                    NotShadowCaster,
                    NotShadowReceiver,
                    NoFrustumCulling,
                    ChildOf(*e),
                ));
                if let Some(s) = skinned {
                    hull.insert(s.clone());
                }
            }
        }
    }
    if let (Some(lib), Some(player_e)) = (inst.model.anim.as_ref(), parts.player) {
        if lib.layered && masked.0.insert(lib.graph.id()) {
            let lower = lower_body_targets(root, &children, &targets, &names);
            if let Some(mut graph) = graphs.get_mut(&lib.graph) {
                for id in lower {
                    graph.add_target_to_mask_group(id, LOWER_BODY_GROUP);
                }
            }
        }
        let mut animator = Animator::new(inst.model.clone());
        if let Ok(mut player) = players.get_mut(player_e) {
            let first = ["idle_combat", "idle", "move"].into_iter().find(|c| lib.clips.contains_key(*c));
            if let Some(first) = first {
                animator.set_base(&mut player, first, 1.0, 0.0, false);
            }
        }
        commands.entity(player_e).insert((AnimationGraphHandle(lib.graph.clone()), animator));
    }
    if let Some(WeaponOf(hero)) = weapon_of
        && let Ok(mut gear) = gears.get_mut(*hero)
        && gear.weapon == Some(root)
    {
        let meta = &inst.model.meta;
        let weapon_l = hero_parts.get(*hero).ok().and_then(|p| p.node("weapon_L"));
        if let (Some(off), Some(socket)) = (parts.node("offhand"), weapon_l) {
            commands.entity(off).insert((ChildOf(socket), Transform::IDENTITY));
            gear.offhand = Some(off);
        }
        let find = |names: &Option<[String; 2]>| -> [Option<Entity>; 2] {
            names.as_ref().map_or([None, None], |[l, r]| [parts.node(l), parts.node(r)])
        };
        gear.fist = find(&meta.fist_nodes);
        gear.open = find(&meta.open_nodes);
        for e in gear.open.iter().flatten() {
            commands.entity(*e).insert(Visibility::Hidden);
        }
        gear.hands_open = [false, false];
        gear.muzzle = parts.node("muzzle");
    }
    commands.entity(root).insert((parts, Visibility::Inherited));
}

/// Attach, swap and detach hero weapons as the equipped chassis changes.
fn attach_weapons(
    mut commands: Commands,
    mut models: ResMut<Models>,
    server: Res<AssetServer>,
    mut heroes: Query<(Entity, &mut HeroGear, &ModelParts)>,
) {
    for (hero, mut gear, parts) in &mut heroes {
        if gear.want == gear.attached && (gear.weapon.is_some() || gear.greybox_gun || gear.want.is_none()) {
            continue;
        }
        let Some(want) = gear.want.clone() else {
            detach(&mut commands, &mut gear);
            gear.attached = None;
            continue;
        };
        if gear.attached.as_deref() != Some(want.as_str()) {
            detach(&mut commands, &mut gear);
            gear.attached = Some(want.clone());
            gear.greybox_gun = false;
        }
        match models.get(ModelKind::Weapon, &want, &server) {
            Some(model) => {
                let Some(socket) = parts.node("weapon_R") else {
                    gear.greybox_gun = true;
                    continue;
                };
                let slot = gear.slot;
                let e = spawn_model(&mut commands, socket, &model, Skin::Gear(slot), Transform::IDENTITY);
                commands.entity(e).insert(WeaponOf(hero));
                gear.weapon = Some(e);
            }
            None if models.missing(ModelKind::Weapon, &want) => gear.greybox_gun = true,
            None => {}
        }
    }
}

fn detach(commands: &mut Commands, gear: &mut HeroGear) {
    for e in [gear.weapon.take(), gear.offhand.take()].into_iter().flatten() {
        commands.entity(e).despawn();
    }
    gear.muzzle = None;
    gear.fist = [None, None];
    gear.open = [None, None];
}

/// Swap hero and weapon meshes between their normal and ghost skins, and show the gauntlet
/// variant each hand wants.
fn dress_heroes(
    mut commands: Commands,
    mut gears: Query<(&HeroGear, &ModelInstance, &mut ModelParts), Changed<HeroGear>>,
    mut weapons: Query<&mut ModelParts, Without<HeroGear>>,
    stds: Res<Assets<StandardMaterial>>,
    mut toons: ResMut<Assets<ToonMaterial>>,
    mut cache: ResMut<SkinCache>,
    pal: Res<Palette>,
) {
    for (gear, inst, mut parts) in &mut gears {
        let (body, kit) = if gear.ghost {
            (Skin::Ghost(gear.slot), Skin::Ghost(gear.slot))
        } else {
            (inst.skin, Skin::Gear(gear.slot))
        };
        let mut dress = |parts: &mut ModelParts, skin: Skin| {
            if parts.skin == Some(skin) {
                return;
            }
            parts.skin = Some(skin);
            for (e, source) in &parts.meshes {
                if let Some(toon) = cache.get(source, skin, &stds, &mut toons, &pal) {
                    commands.entity(*e).insert(MeshMaterial3d(toon));
                }
            }
        };
        dress(&mut parts, body);
        for e in [gear.weapon, gear.offhand].into_iter().flatten() {
            if let Ok(mut wp) = weapons.get_mut(e) {
                dress(&mut wp, kit);
            }
        }
        for side in 0..2 {
            let open = gear.hands_open[side];
            if let Some(e) = gear.fist[side] {
                commands.entity(e).insert(if open { Visibility::Hidden } else { Visibility::Inherited });
            }
            if let Some(e) = gear.open[side] {
                commands.entity(e).insert(if open { Visibility::Inherited } else { Visibility::Hidden });
            }
        }
    }
}

/// Is `--greybox` on the command line (or `GODFORGE_GREYBOX` set)?
fn greybox_requested() -> bool {
    std::env::args().any(|a| a == "--greybox") || std::env::var("GODFORGE_GREYBOX").is_ok_and(|v| v != "0")
}

pub fn build(app: &mut App) {
    let root = gf_engine::client::find_asset_dir();
    let greybox = greybox_requested();
    info!("models: asset root {}{}", root.display(), if greybox { " (--greybox: models off)" } else { "" });
    app.insert_resource(Models::new(root, greybox))
        .init_resource::<SkinCache>()
        .init_resource::<MaskedGraphs>()
        .add_observer(on_instance_ready)
        .add_systems(Update, prepare_models.in_set(ClientSet::Net))
        .add_systems(Update, (attach_weapons, dress_heroes).chain().in_set(ClientSet::Presentation));
}
