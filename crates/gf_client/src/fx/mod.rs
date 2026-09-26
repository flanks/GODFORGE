//! # fx — the combat VFX engine (docs/art/VFX_STYLE.md §21)
//!
//! Painterly, ink-backed effects built from the packed asset library in `assets/vfx/`, drawn in a
//! handful of batched draws instead of one entity per mote:
//!
//! * **Particles** ([`particle`]): instanced flipbook quads — billboards, ground decals,
//!   velocity-stretched sparks and axis quads (muzzle flashes, lightning strips) — simulated in a
//!   flat store and expanded into one dynamic mesh per (sheet, [`Layer`]).
//! * **Ribbons** ([`ribbon`]): trails that follow an entity, an analytic flight or a hand-moved
//!   head; beams, tethers and loot beams.
//! * **Arcs** ([`arc`]): crescent smears and slashes that sweep then erode, shockwave rings, dust
//!   walls — generated strips with a scrolling brush-noise dissolve.
//! * **Decals**: ground paint in a ring buffer ([`MAX_DECALS`], oldest recycled first).
//! * **Light flashes** ([`light`]): a pool of point lights lent to the brightest requests.
//! * **Budget**: the readability tiers of `game.ron` (Full → Reduced → Silhouette) and the ally
//!   alpha decide what each owner may spawn ([`Owner`], [`Class`], VFX_STYLE §20).
//!
//! Effect code talks to it through the [`Fx`] system parameter (see [`api`]). `--vfx-gallery`
//! plays every primitive in a labelled grid for art review; `--vfx-bench` holds 2000 particles,
//! 200 trails and 50 smears on screen for frame-time checks.
//!
//! One shader (`fx.wesl`) serves every layer: the atlas's packed shape / value / erosion channels
//! go through a ramp row, so one painted flipbook serves every element and owner.

pub mod api;
pub mod arc;
pub mod attach;
pub mod body;
pub mod gallery;
pub mod library;
pub mod light;
pub mod material;
pub mod mesh;
pub mod particle;
pub mod ribbon;
pub mod textures;

pub use api::{Fx, Hit, HitKind, RibbonId, SpriteBuilder};
pub use arc::{Arc, Profile, Sweep};
pub use attach::{FxRing, FxSprite, FxTrail};
pub use body::{BodyMesh, FxBody};
pub use library::{Decal, Glyph, Mote, Pip, Ramp, Seq, Sheet, Strip, seq, strip, value};
pub use particle::{Curve, Orient, Particle, Path, Play};
pub use ribbon::{Facing, RibbonStyle, Source};

use crate::camera::MainCamera;
use gf_content::VfxTier;
use gf_engine::bevy::asset::AssetEventSystems;
use gf_engine::bevy::camera::visibility::VisibilitySystems;
use gf_engine::bevy::transform::TransformSystems;
use gf_engine::client::embedded_asset;
use gf_engine::prelude::*;
use material::FxMaterial;
use mesh::{CamBasis, Layers};
use ribbon::Ribbon;

/// Hard ceiling on live particles whatever the tier (danger and core shapes may exceed the tier
/// cap up to here).
pub const MAX_PARTICLES: usize = 6000;
/// Ground decals alive at once; the oldest is recycled first.
pub const MAX_DECALS: usize = 256;
/// Live arcs (smears, rings) at once.
pub const MAX_ARCS: usize = 512;
/// Live ribbons at once.
pub const MAX_RIBBONS: usize = 640;
/// Draw order of enemy telegraphs: above every VFX layer (VFX_STYLE §21.3).
pub const TELEGRAPH_BIAS: f32 = 1000.0;

/// Draw-order classes (VFX_STYLE §21.3). Each (sheet, layer) is one draw; layers composite in
/// this order, whatever the positions of their effects.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Default)]
pub enum Layer {
    /// Paint on the floor (scorch, stains, glyph decals): under the scene's own ground marks.
    Decal,
    /// Ground VFX (dust, cracks, swirls, rings on the floor): under shadows and player rings.
    Ground,
    /// Behind the main shapes: ink backings, the back half of a smoke crown.
    Back,
    /// The main shapes: bursts, stars, smears, trails, bodies.
    #[default]
    Main,
    /// In front: sparks, glints, the front of a smoke crown.
    Front,
    /// Impact frames: the white star over its ink star, 1-2 frames.
    Top,
    /// Enemy danger shapes (enemy shots): above every player effect, under telegraphs.
    Danger,
}

impl Layer {
    pub const COUNT: usize = 7;
    pub const ALL: [Layer; Layer::COUNT] =
        [Layer::Decal, Layer::Ground, Layer::Back, Layer::Main, Layer::Front, Layer::Top, Layer::Danger];

    /// Material depth bias. Scene transparents sort by their own view depth (±30 around the
    /// focus); every VFX layer sorts at the focus plus its bias.
    pub fn bias(self) -> f32 {
        match self {
            Layer::Decal => -160.0,
            Layer::Ground => -100.0,
            Layer::Back => 100.0,
            Layer::Main => 200.0,
            Layer::Front => 300.0,
            Layer::Top => 400.0,
            Layer::Danger => 900.0,
        }
    }

    /// The layer an ink backing goes in (one step behind its body).
    pub fn behind(self) -> Layer {
        match self {
            Layer::Main => Layer::Back,
            Layer::Front => Layer::Main,
            Layer::Top => Layer::Front,
            other => other,
        }
    }
}

/// Who an effect belongs to, from the local player's point of view (VFX_STYLE §20.2).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Default)]
pub enum Owner {
    /// Yours: full alpha, light spill, impact frames.
    #[default]
    Mine,
    /// A teammate's: `vfx.ally_effect_alpha`, capped gain, no spill, no impact frame.
    Ally,
    /// The horde's: full alpha, never tier-dropped when it carries danger.
    Enemy,
    /// The world's (anvil, loot, bosses, UI-side marks).
    World,
}

impl Owner {
    /// From a sim damage source (`< 12` = a player's, `source % 4` = the slot) and the local slot.
    pub fn of_source(source: u8, me: Option<u8>) -> Owner {
        if source < 12 { Self::of_slot(source % 4, me) } else { Owner::Enemy }
    }

    pub fn of_slot(slot: u8, me: Option<u8>) -> Owner {
        if Some(slot) == me || me.is_none() { Owner::Mine } else { Owner::Ally }
    }
}

/// What a part of an effect is, for the budget (VFX_STYLE §20.1: what drops first).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Class {
    /// Danger and gameplay-critical marks (enemy shots, loot beams, revive tethers): never dropped.
    Danger,
    /// The shape that carries the read: flash, body, impact star, blast.
    Core,
    /// Sparks, embers, glints.
    Secondary,
    /// Smoke puffs and dust (overdraw-heavy).
    Smoke,
    /// Scorch, stain and crack decals.
    Decal,
    /// Impact frames and light spill: your own only.
    Accent,
    /// Trails.
    Trail,
}

/// What the budget grants one spawn.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Grant {
    /// Multiply counts of repeated parts by this.
    pub count: f32,
    pub life: f32,
    pub alpha: f32,
    pub size: f32,
    /// HDR gain ceiling.
    pub cap: f32,
}

impl Grant {
    pub const FULL: Grant = Grant { count: 1.0, life: 1.0, alpha: 1.0, size: 1.0, cap: 3.2 };

    /// Scale a count (at least `min` when the grant is not zero).
    pub fn n(&self, n: u32) -> u32 {
        (n as f32 * self.count).round() as u32
    }
}

/// Live counters (the tier input, `--fps` logs and the gallery overlay).
#[derive(Clone, Copy, Debug, Default)]
pub struct FxStats {
    pub particles: u32,
    pub decals: u32,
    pub ribbons: u32,
    pub arcs: u32,
    pub lights: u32,
    pub draws: u32,
    pub vertices: u32,
    /// CPU time of the last simulate + build + upload (ms).
    pub build_ms: f32,
}

/// Everything alive, pooled: particles and decals in flat vectors (swap-remove, no allocation at
/// steady state), ribbons in generation-checked slots, arcs and flashes in flat vectors.
#[derive(Resource)]
pub struct FxStore {
    pub(crate) particles: Vec<Particle>,
    pub(crate) decals: Vec<Particle>,
    pub(crate) ribbons: Vec<RibbonSlot>,
    pub(crate) free_ribbons: Vec<u32>,
    pub(crate) arcs: Vec<Arc>,
    pub(crate) flashes: Vec<light::Flash>,
    /// Drawn for one frame, then dropped (`SpriteBuilder::now`, `Fx::arc_now`).
    pub(crate) instant: Vec<Particle>,
    pub(crate) instant_arcs: Vec<Arc>,
    /// The readability tier (set from `VfxState` every frame).
    pub tier: VfxTier,
    /// Particle cap per tier (`game.ron vfx.particles`).
    pub caps: [u32; 3],
    pub ally_alpha: f32,
    /// The VFX clock (seconds, scaled by `time_scale`).
    pub time: f32,
    /// VFX time multiplier (Epoch's Still Field 0.4, Stolen Second 0).
    pub time_scale: f32,
    /// Everything drawn at 0 age (QA captures of frame 0).
    pub frozen: bool,
    pub stats: FxStats,
    /// VFX clock of the last impact frame (they never come closer than 0.25 s).
    pub(crate) last_impact_frame: f32,
    pub(crate) rng: u32,
    /// The camera basis of the last build (recipes that aim at the camera use it).
    pub cam: CamBasis,
}

pub(crate) struct RibbonSlot {
    pub(crate) generation: u32,
    pub(crate) ribbon: Option<Ribbon>,
}

impl Default for FxStore {
    fn default() -> Self {
        FxStore {
            particles: Vec::with_capacity(2048),
            decals: Vec::with_capacity(MAX_DECALS),
            ribbons: Vec::with_capacity(256),
            free_ribbons: Vec::new(),
            arcs: Vec::with_capacity(64),
            flashes: Vec::with_capacity(32),
            instant: Vec::with_capacity(64),
            instant_arcs: Vec::with_capacity(16),
            tier: VfxTier::Full,
            caps: [1600, 700, 200],
            ally_alpha: 0.55,
            time: 0.0,
            time_scale: 1.0,
            frozen: false,
            stats: FxStats::default(),
            last_impact_frame: -1.0,
            rng: 0x9E37_79B9,
            cam: CamBasis::default(),
        }
    }
}

impl FxStore {
    /// A float in 0..1 (xorshift).
    pub fn rand(&mut self) -> f32 {
        self.rng ^= self.rng << 13;
        self.rng ^= self.rng >> 17;
        self.rng ^= self.rng << 5;
        (self.rng >> 8) as f32 / (1u32 << 24) as f32
    }

    /// A float in `lo..hi`.
    pub fn range(&mut self, lo: f32, hi: f32) -> f32 {
        lo + (hi - lo) * self.rand()
    }

    /// Live load for the tier choice: ribbons and arcs count as effects, particles at a quarter
    /// (they are batched: one quad costs far less than one entity did).
    pub fn load(&self) -> u32 {
        self.stats.ribbons + self.stats.arcs + self.stats.particles / 4
    }

    /// What the budget grants `owner`'s `class` part at the current tier (None = skip it).
    pub fn grant(&self, owner: Owner, class: Class) -> Option<Grant> {
        use VfxTier::{Full, Reduced, Silhouette};
        let tier = self.tier;
        let full = self.particles.len() >= self.caps[tier as usize] as usize;
        let ally = owner == Owner::Ally;
        let mut g = Grant::FULL;
        if ally {
            g.alpha = if tier == Silhouette { 0.4 } else { self.ally_alpha };
            g.cap = 1.6;
            if tier == Silhouette {
                g.size = 0.7;
            }
        }
        match class {
            Class::Danger => return Some(Grant { cap: 3.2, ..Grant::FULL }),
            Class::Core => {}
            Class::Secondary => {
                if full {
                    return None;
                }
                g.count = match (tier, ally) {
                    (Full, _) => 1.0,
                    (Reduced, false) => 0.5,
                    (Reduced, true) => 0.25,
                    (Silhouette, false) => 0.25,
                    (Silhouette, true) => return None,
                };
            }
            Class::Smoke => {
                if full {
                    return None;
                }
                match tier {
                    Full => {}
                    Reduced => {
                        g.count = if ally { 0.25 } else { 0.5 };
                        g.life = 0.6;
                    }
                    Silhouette => return None,
                }
            }
            Class::Decal => match tier {
                Full => {}
                Reduced => g.life = 0.34,
                Silhouette => return None,
            },
            Class::Accent => {
                if ally || owner == Owner::Enemy {
                    return None;
                }
            }
            Class::Trail => match (tier, ally) {
                (Full, _) | (Reduced, false) => {}
                (Reduced, true) => g.life = 0.34,
                (Silhouette, false) => g.life = 0.5,
                (Silhouette, true) => return None,
            },
        }
        Some(g)
    }

    pub(crate) fn push_particle(&mut self, p: Particle) {
        if self.particles.len() < MAX_PARTICLES {
            self.particles.push(p);
        }
    }

    pub(crate) fn push_decal(&mut self, p: Particle) {
        if self.decals.len() >= MAX_DECALS {
            // Recycle the most-faded decal.
            if let Some((i, _)) = self.decals.iter().enumerate().max_by(|a, b| a.1.k().total_cmp(&b.1.k())) {
                self.decals.swap_remove(i);
            }
        }
        self.decals.push(p);
    }

    pub(crate) fn push_arc(&mut self, a: Arc) {
        if self.arcs.len() < MAX_ARCS {
            self.arcs.push(a);
        }
    }

    pub(crate) fn push_ribbon(&mut self, r: Ribbon) -> Option<RibbonId> {
        if let Some(i) = self.free_ribbons.pop() {
            let slot = &mut self.ribbons[i as usize];
            slot.generation = slot.generation.wrapping_add(1);
            slot.ribbon = Some(r);
            return Some(RibbonId { index: i, generation: slot.generation });
        }
        if self.ribbons.len() >= MAX_RIBBONS {
            return None;
        }
        self.ribbons.push(RibbonSlot { generation: 0, ribbon: Some(r) });
        Some(RibbonId { index: self.ribbons.len() as u32 - 1, generation: 0 })
    }

    pub(crate) fn ribbon_mut(&mut self, id: RibbonId) -> Option<&mut Ribbon> {
        let slot = self.ribbons.get_mut(id.index as usize)?;
        if slot.generation != id.generation {
            return None;
        }
        slot.ribbon.as_mut()
    }

    /// Drop everything (a new run, a room change).
    pub fn clear(&mut self) {
        self.particles.clear();
        self.decals.clear();
        self.arcs.clear();
        self.flashes.clear();
        self.instant.clear();
        self.instant_arcs.clear();
        for (i, slot) in self.ribbons.iter_mut().enumerate() {
            if slot.ribbon.take().is_some() {
                self.free_ribbons.push(i as u32);
            }
        }
    }
}

pub fn build(app: &mut App) {
    embedded_asset!(app, "fx.wesl");
    embedded_asset!(app, "body.wesl");
    body::register(app);
    app.add_plugins((MaterialPlugin::<FxMaterial>::default(), MaterialPlugin::<body::FxBodyMaterial>::default()))
        .init_resource::<FxStore>()
        .init_resource::<Layers>()
        .init_resource::<body::FxBodies>()
        .add_systems(Startup, (textures::load, light::spawn_pool, body::load))
        .add_systems(Update, (clear_on_room_change, body::update.in_set(crate::ClientSet::Presentation)))
        .add_systems(
            PostUpdate,
            (attach::start_trails, step, draw)
                .chain()
                .after(TransformSystems::Propagate)
                .before(AssetEventSystems)
                .before(VisibilitySystems::VisibilityPropagate),
        );
    gallery::build(app);
}

/// Advance every live effect by the (scaled) frame time.
fn step(time: Res<Time>, mut store: ResMut<FxStore>, globals: Query<&GlobalTransform>) {
    let started = std::time::Instant::now();
    let dt = if store.frozen { 0.0 } else { time.delta_secs().min(0.1) * store.time_scale };
    store.time += dt;
    let now = store.time;
    let pos_of = |e: Option<Entity>| e.map(|e| globals.get(e).ok().map(|g| g.translation()));
    let store = &mut *store;
    let mut i = 0;
    while i < store.particles.len() {
        let p = &mut store.particles[i];
        let follow = pos_of(p.follow.or(p.path.and_then(|path| path.target)));
        if p.step(dt, follow) {
            i += 1;
        } else {
            store.particles.swap_remove(i);
        }
    }
    let mut i = 0;
    while i < store.decals.len() {
        if store.decals[i].step(dt, None) {
            i += 1;
        } else {
            store.decals.swap_remove(i);
        }
    }
    let mut i = 0;
    while i < store.arcs.len() {
        let a = &mut store.arcs[i];
        let follow = pos_of(a.follow);
        if a.step(dt, follow) {
            i += 1;
        } else {
            store.arcs.swap_remove(i);
        }
    }
    let mut ribbons = 0;
    for (idx, slot) in store.ribbons.iter_mut().enumerate() {
        let Some(r) = slot.ribbon.as_mut() else { continue };
        let entity_pos = match r.source {
            Source::Entity(e, _) => Some(globals.get(e).ok().map(|g| g.translation())),
            _ => None,
        };
        if r.immediate && !r.touched {
            r.detach(now);
        }
        if r.step(now, entity_pos) {
            ribbons += 1;
        } else {
            slot.ribbon = None;
            store.free_ribbons.push(idx as u32);
        }
    }
    let mut i = 0;
    while i < store.flashes.len() {
        let f = &mut store.flashes[i];
        f.age += dt;
        if let Some(e) = f.follow
            && let Ok(g) = globals.get(e)
        {
            f.world = g.translation() + f.pos;
        }
        if f.age < f.life {
            i += 1;
        } else {
            store.flashes.swap_remove(i);
        }
    }
    store.stats.particles = store.particles.len() as u32;
    store.stats.decals = store.decals.len() as u32;
    store.stats.ribbons = ribbons;
    store.stats.arcs = store.arcs.len() as u32;
    store.stats.build_ms = started.elapsed().as_secs_f32() * 1000.0;
}

/// Build and upload the layer meshes; lend the light pool.
#[allow(clippy::too_many_arguments)]
fn draw(
    mut commands: Commands,
    time: Res<Time>,
    mut store: ResMut<FxStore>,
    mut layers: ResMut<Layers>,
    textures: Option<Res<textures::FxTextures>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<FxMaterial>>,
    cameras: Query<&Transform, With<MainCamera>>,
    mut visibility: mesh::LayerVisibility,
    mut lights: light::LightPool,
    mut sprites: Query<(&GlobalTransform, &mut attach::FxSprite)>,
    mut rings: Query<(&GlobalTransform, &mut attach::FxRing)>,
    index: Res<crate::scene::SceneIndex>,
    globals: Query<&GlobalTransform>,
    mut scratch: Local<(Vec<(u32, f32, u32)>, Vec<Vec3>)>,
) {
    let Some(textures) = textures else { return };
    let started = std::time::Instant::now();
    let cam = cameras.single().map(CamBasis::from_transform).unwrap_or_default();
    let store = &mut *store;
    store.cam = cam;
    layers.clear();
    // Particles and decals: back to front inside each (sheet, layer).
    let (order, points) = &mut *scratch;
    order.clear();
    for (i, p) in store.particles.iter().enumerate() {
        let key = Layers::index(p.seq.sheet, p.layer) as u32;
        order.push((key, -cam.depth(p.world), i as u32));
    }
    order.sort_unstable_by(|a, b| a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)));
    for &(key, _, i) in order.iter() {
        store.particles[i as usize].emit(&mut layers.slots[key as usize].buf, &cam);
    }
    for d in &store.decals {
        d.emit(layers.buf(d.seq.sheet, d.layer), &cam);
    }
    for a in &store.arcs {
        a.emit(layers.buf(a.strip.sheet, a.layer), &cam);
    }
    for p in store.instant.drain(..) {
        p.emit(layers.buf(p.seq.sheet, p.layer), &cam);
    }
    for a in store.instant_arcs.drain(..) {
        a.emit(layers.buf(a.strip.sheet, a.layer), &cam);
    }
    let now = store.time;
    for slot in &mut store.ribbons {
        let Some(r) = slot.ribbon.as_mut() else { continue };
        r.emit(layers.buf(r.style.strip.sheet, r.style.layer), &cam, now, points);
        // Immediate-mode ribbons must be refreshed every frame.
        r.touched = false;
    }
    let dt = if store.frozen { 0.0 } else { time.delta_secs().min(0.1) * store.time_scale };
    attach::emit_sprites(store, &mut layers, &mut sprites, dt);
    attach::emit_rings(store, &mut layers, &mut rings, dt);
    let (draws, verts) =
        mesh::upload(&mut commands, &mut layers, &textures, &mut meshes, &mut materials, &mut visibility, &cam);
    light::assign(&store.flashes, &mut lights);
    // Heroes an effect must never hide: the four player rigs' torsos.
    let mut heroes = [Vec4::ZERO; material::REVEAL_SLOTS];
    for (slot, e) in index.players.iter().enumerate().take(material::REVEAL_SLOTS) {
        if let Some(g) = e.and_then(|e| globals.get(e).ok()) {
            heroes[slot] = (g.translation() + Vec3::Y * 1.0).extend(1.0);
        }
    }
    mesh::update_reveal(&layers, &mut materials, &cam, &heroes);
    store.stats.draws = draws;
    store.stats.vertices = verts;
    store.stats.lights = store.flashes.len().min(light::POOL) as u32;
    store.stats.build_ms += started.elapsed().as_secs_f32() * 1000.0;
}

/// A new room or a new session starts with a clean slate (no stains or trails from the last one).
fn clear_on_room_change(room: Res<crate::net::CurrentRoom>, mut store: ResMut<FxStore>, mut seen: Local<u32>) {
    if room.generation != *seen {
        *seen = room.generation;
        store.clear();
    }
}
