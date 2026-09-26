//! Effects carried by an entity: put a component on a scene entity and the VFX engine draws it
//! for as long as the entity lives. This is how projectile bodies, their trails, enemy shots,
//! charge cores and status pips hook into `scene.rs` without spawning anything themselves:
//!
//! ```ignore
//! commands.entity(projectile).insert((
//!     FxSprite::body(ProjectileStyle::Orb, Ramp::Storm, radius, owner),
//!     FxTrail::new(trail_style(ProjectileStyle::Orb, Ramp::Storm, speed).unwrap(), owner),
//! ));
//! ```

use super::api::{F, Fx};
use super::arc::{Arc, Profile};
use super::library::{Ramp, Seq, Strip, seq, strip};
use super::mesh::Layers;
use super::particle::{Orient, Particle, Play};
use super::ribbon::RibbonStyle;
use super::{Class, FxStore, Layer, Owner, RibbonId};
use gf_core::weapon::ProjectileStyle;
use gf_engine::prelude::*;

/// A flipbook quad drawn on this entity every frame.
#[derive(Component, Clone, Debug)]
pub struct FxSprite {
    pub seq: Seq,
    /// Quad width and height (metres).
    pub size: Vec2,
    pub ramp: Ramp,
    pub gain: f32,
    pub alpha: f32,
    /// Offset from the entity's translation (world axes).
    pub offset: Vec3,
    /// How the quad faces. `Orient::Axis` with a zero direction points `+u` along the entity's
    /// motion (projectile bodies, teardrop enemy shots).
    pub orient: Orient,
    pub layer: Layer,
    pub play: Play,
    pub rot: f32,
    /// Spin (radians per second) in the quad's plane.
    pub spin: f32,
    /// Ramp value override (< 0 = the painted value).
    pub value: f32,
    pub pull: f32,
    pub owner: Owner,
    pub class: Class,
    pub(crate) age: f32,
    pub(crate) last: Option<Vec3>,
    pub(crate) heading: Vec3,
}

impl FxSprite {
    pub fn new(seq: Seq, height: f32, ramp: Ramp, owner: Owner) -> FxSprite {
        FxSprite {
            seq,
            size: Vec2::new(height * seq.sheet.cell_aspect(), height),
            ramp,
            gain: 1.0,
            alpha: 1.0,
            offset: Vec3::ZERO,
            orient: Orient::Billboard,
            layer: Layer::Main,
            play: Play::Painted,
            rot: 0.0,
            spin: 0.0,
            value: -1.0,
            pull: 0.3,
            owner,
            class: Class::Core,
            age: 0.0,
            last: None,
            heading: Vec3::X,
        }
    }

    /// The billboard body of a projectile style (VFX_STYLE §6), `radius` = the sim radius.
    /// Styles the atlas paints as flipbooks (Orb, Globe) or small stills (Needle, Pellet, Bolt,
    /// Slug) point along the flight; mesh styles (Shell, Arrow, Boulder, Coin, Blade) fall back to
    /// the nearest billboard until their meshes are wired.
    pub fn body(style: ProjectileStyle, ramp: Ramp, radius: f32, owner: Owner) -> FxSprite {
        use ProjectileStyle as S;
        let r = radius.max(0.08);
        let along = Orient::Axis { dir: Vec3::ZERO };
        let (seq, h, orient) = match style {
            S::Orb => (seq::BODY_ORB, (r * 5.0).max(0.7), Orient::Billboard),
            S::Globe => (seq::BODY_GLOBE, (r * 4.5).max(0.8), Orient::Billboard),
            S::Needle => (seq::BODY_SMALL.nth(0), (r * 5.0).max(0.65), along),
            S::Pellet | S::Shard => (seq::BODY_SMALL.nth(1), (r * 5.0).max(0.5), along),
            S::Bolt | S::Arrow | S::Blade => (seq::BODY_SMALL.nth(2), (r * 6.5).max(0.8), along),
            S::Slug | S::Shell | S::Boulder => (seq::BODY_SMALL.nth(3), (r * 6.5).max(0.9), along),
            S::Coin => (seq::COIN, (r * 3.6).max(0.5), Orient::Billboard),
            S::Arc => (seq::MUZZLE_RAIL, (r * 6.0).max(1.0), along),
            S::Fist => (seq::GLINT.nth(0), (r * 3.6).max(0.5), Orient::Billboard),
        };
        FxSprite { orient, layer: Layer::Front, ..FxSprite::new(seq, h, ramp, owner) }
    }

    /// The enemy shot teardrop: magenta-cored, stretched 1.6× along its flight, on the danger
    /// layer (above every player effect, under telegraphs).
    pub fn enemy_shot(radius: f32) -> FxSprite {
        let h = (radius * 3.4).max(0.5);
        FxSprite {
            size: Vec2::new(h * 1.6, h),
            orient: Orient::Axis { dir: Vec3::ZERO },
            layer: Layer::Danger,
            class: Class::Danger,
            ..FxSprite::new(seq::BODY_ENEMY_SHOT, h, Ramp::EnemyShot, Owner::Enemy)
        }
    }

    pub fn offset(mut self, o: Vec3) -> Self {
        self.offset = o;
        self
    }

    pub fn layer(mut self, l: Layer) -> Self {
        self.layer = l;
        self
    }
}

/// A trail following this entity; it detaches and erodes away when the entity despawns.
#[derive(Component, Clone, Debug)]
pub struct FxTrail {
    pub style: RibbonStyle,
    pub owner: Owner,
    pub offset: Vec3,
    pub(crate) id: Option<RibbonId>,
}

impl FxTrail {
    pub fn new(style: RibbonStyle, owner: Owner) -> FxTrail {
        FxTrail { style, owner, offset: Vec3::ZERO, id: None }
    }
}

/// A broken ring drawn around this entity every frame: hazard and field hems, the Still Field
/// bubble, charge rings (VFX_STYLE §2 "Ring": always broken and tapered, marking a true radius).
#[derive(Component, Clone, Debug)]
pub struct FxRing {
    pub radius: f32,
    /// Band width (or wall height with `wall`).
    pub width: f32,
    pub strip: Strip,
    pub ramp: Ramp,
    pub gain: f32,
    pub alpha: f32,
    /// Texture repeats around the ring (the gaps of a broken ring).
    pub repeats: f32,
    /// Turns of the texture per second.
    pub spin: f32,
    /// Stand up as a low wall instead of lying on the floor.
    pub wall: bool,
    /// Height above the entity's feet.
    pub height: f32,
    pub layer: Layer,
    pub owner: Owner,
    pub class: Class,
    pub(crate) age: f32,
}

impl FxRing {
    /// A hem on the floor at a true radius: player-side zones are gold, enemy ones use their own
    /// ramp (the red-white enemy hem stays the scene's telegraph language).
    pub fn hem(radius: f32, ramp: Ramp, owner: Owner) -> FxRing {
        FxRing {
            radius,
            width: (radius * 0.08).clamp(0.12, 0.5),
            strip: strip::ACCENT_RING,
            ramp,
            gain: 1.0,
            alpha: 1.0,
            repeats: (radius * 1.4).round().clamp(3.0, 16.0),
            spin: 0.05,
            wall: false,
            height: 0.04,
            layer: Layer::Ground,
            owner,
            class: Class::Core,
            age: 0.0,
        }
    }
}

/// Start the ribbons of newly tagged entities.
pub(super) fn start_trails(mut fx: Fx, mut trails: Query<(Entity, &mut FxTrail), Added<FxTrail>>) {
    for (e, mut t) in &mut trails {
        t.id = fx.trail_for(e, t.offset, t.style, t.owner);
    }
}

/// Emit every attached ring into its layer (called from the layer build).
pub(super) fn emit_rings(
    store: &FxStore,
    layers: &mut Layers,
    rings: &mut Query<(&GlobalTransform, &mut FxRing)>,
    dt: f32,
) {
    let cam = store.cam;
    for (g, mut r) in rings.iter_mut() {
        let Some(grant) = store.grant(r.owner, r.class) else { continue };
        r.age += dt;
        let at = g.translation() + Vec3::Y * r.height;
        let mut a = Arc::new(r.strip, at, r.radius, r.width, r.age + 1.0);
        a.age = r.age;
        a.world = at;
        a.repeats = r.repeats;
        a.spin = r.spin * r.repeats;
        a.ramp = r.ramp;
        a.gain = r.gain;
        a.cap = grant.cap;
        a.alpha = super::Curve::flat(r.alpha * grant.alpha);
        a.erode = Vec2::new(1.0, 0.0);
        a.segments = ((r.radius * 12.0) as u16).clamp(24, 128);
        a.pull = 0.0;
        a.layer = r.layer;
        if r.wall {
            a.profile = Profile::Wall { flare: r.width * 0.3 };
        }
        a.emit(layers.buf(r.strip.sheet, r.layer), &cam);
    }
}

/// Emit every attached sprite into its layer (called from the layer build).
pub(super) fn emit_sprites(
    store: &FxStore,
    layers: &mut Layers,
    sprites: &mut Query<(&GlobalTransform, &mut FxSprite)>,
    dt: f32,
) {
    let cam = store.cam;
    for (g, mut s) in sprites.iter_mut() {
        let Some(grant) = store.grant(s.owner, s.class) else { continue };
        let pos = g.translation() + s.offset;
        s.age += dt;
        if let Some(last) = s.last {
            let d = pos - last;
            if d.length_squared() > 1e-6 {
                s.heading = d.normalize();
            }
        }
        s.last = Some(pos);
        let mut p = Particle::new(s.seq, pos);
        p.world = pos;
        p.size = s.size * grant.size;
        p.ramp = s.ramp;
        p.gain = s.gain;
        p.cap = grant.cap;
        p.alpha = super::Curve::flat(s.alpha * grant.alpha);
        p.orient = match s.orient {
            Orient::Axis { dir } if dir.length_squared() < 1e-6 => Orient::Axis { dir: s.heading },
            o => o,
        };
        p.play = s.play;
        p.age = s.age;
        p.life = s.age + F;
        p.rot = s.rot + s.spin * s.age;
        p.value = s.value;
        p.erode = Vec2::new(1.0, 0.0);
        p.pull = s.pull;
        p.layer = s.layer;
        p.emit(layers.buf(s.seq.sheet, s.layer), &cam);
    }
}
