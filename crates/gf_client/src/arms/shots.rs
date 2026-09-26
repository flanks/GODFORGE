//! Projectile bodies and trails (VFX_STYLE §6, §9): what every `ProjectileStyle` looks like in
//! flight, dressed onto a carrier entity (a child of the replicated visual, or a gallery
//! stand-in) with the fx attachments, plus the per-frame emitters that ride a shot (shell smoke,
//! orb crackle, coin glints, boulder embers, harpoon rope) and the ricochet bounce spark.

use super::recipes::puff;
use crate::fx::api::{F, trail_style};
use crate::fx::{Arc, BodyMesh, Class, Curve, Fx, FxBody, FxSprite, FxTrail, Glyph, Layer, Mote, Orient, Owner, Pip};
use crate::fx::{Play, Profile, Ramp, RibbonStyle, Sweep, seq, strip, value};
use gf_core::weapon::ProjectileStyle;
use gf_engine::client::NotShadowCaster;
use gf_engine::prelude::*;
use std::f32::consts::TAU;

/// The chassis-specific body of a style (the style alone is shared by several chassis).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum Variant {
    #[default]
    Plain,
    /// Orrery Discs: a spinning disc with a circular smear.
    Disc,
    /// Huntmother Javelins: a barbed shaft.
    Javelin,
    /// Tidecaller Harpoon: a barbed head on a rope back to the thrower.
    Harpoon,
    /// Chorus Harp: a note glyph.
    Note,
    /// Stormlash: a crackling bolt fragment.
    Lash,
    /// Epochal Sundial: an orb with a turning clock dial.
    Dial,
    /// Voidheart Singularity: an event horizon.
    VoidHeart,
    /// Plaguebloom: a bubbling sac.
    Sac,
    /// Gravemaw: an iron ball with molten seams, lobbed.
    Iron,
}

impl Variant {
    pub fn of(style: ProjectileStyle, key: &str, ramp: Ramp) -> Variant {
        use ProjectileStyle as S;
        match (style, key) {
            (S::Blade, "huntmother_javelins") => Variant::Javelin,
            (S::Blade, "tidecaller_harpoon") => Variant::Harpoon,
            (S::Blade, _) => Variant::Disc,
            (S::Arc, "chorus_harp") => Variant::Note,
            (S::Arc, _) => Variant::Lash,
            (S::Orb, "epochal_sundial") => Variant::Dial,
            (S::Globe, _) => match ramp {
                Ramp::Void => Variant::VoidHeart,
                Ramp::Plague => Variant::Sac,
                _ => Variant::Iron,
            },
            _ => Variant::Plain,
        }
    }
}

/// How a shot is dressed.
#[derive(Clone, Copy, Debug)]
pub struct ShotSpec {
    pub style: ProjectileStyle,
    pub variant: Variant,
    pub ramp: Ramp,
    pub owner: Owner,
    /// Sim radius.
    pub radius: f32,
    /// Flight speed (m/s).
    pub speed: f32,
    /// Initial flight direction (world, unit).
    pub heading: Vec3,
    /// 0.8 for fork / split children.
    pub scale: f32,
    /// Charge at release (0..1): a full-charge shot gets a wider, brighter trail.
    pub charged: f32,
    pub homing: bool,
    /// Peak height of a lob (0 = flat).
    pub lob: f32,
    /// Flight range (for the lob arc).
    pub range: f32,
    /// An enemy shot (magenta, danger layer).
    pub enemy: bool,
}

impl ShotSpec {
    pub fn new(style: ProjectileStyle, ramp: Ramp, owner: Owner, radius: f32, speed: f32, heading: Vec3) -> ShotSpec {
        ShotSpec {
            style,
            variant: Variant::Plain,
            ramp,
            owner,
            radius,
            speed,
            heading,
            scale: 1.0,
            charged: 0.0,
            homing: false,
            lob: 0.0,
            range: 12.0,
            enemy: false,
        }
    }

    pub fn enemy(radius: f32, speed: f32, heading: Vec3) -> ShotSpec {
        ShotSpec {
            enemy: true,
            ..ShotSpec::new(ProjectileStyle::Pellet, Ramp::EnemyShot, Owner::Enemy, radius, speed, heading)
        }
    }
}

/// A shot in flight, on its carrier: the emitters' clocks and the bounce detector.
#[derive(Component, Clone, Debug)]
pub struct ShotFx {
    pub spec: ShotSpec,
    /// The owning player's slot (the harpoon's rope).
    pub slot: Option<u8>,
    pub age: f32,
    acc: [f32; 2],
    last: Option<Vec3>,
    pub heading: Vec3,
    /// Flat distance flown (the lob arc).
    flown: f32,
    /// Where the carrier would be without its lob (world).
    pub flat: Vec3,
}

impl ShotFx {
    pub fn new(spec: ShotSpec, slot: Option<u8>) -> ShotFx {
        ShotFx { spec, slot, age: 0.0, acc: [0.0; 2], last: None, heading: spec.heading, flown: 0.0, flat: Vec3::ZERO }
    }
}

/// Marks the child entities that carry a shot's look.
#[derive(Component)]
pub struct Carrier;

fn seeded(mut s: FxSprite, heading: Vec3) -> FxSprite {
    s.heading = heading;
    s
}

fn body(mesh: BodyMesh, spec: &ShotSpec, scale: f32, spin: Vec3) -> FxBody {
    let mut b = FxBody::new(mesh, spec.ramp, spec.owner, scale * spec.scale).spin(spin);
    b.heading = spec.heading;
    b
}

/// A billboard body pointing along the flight.
fn along(s: crate::fx::Seq, h: f32, spec: &ShotSpec) -> FxSprite {
    let sprite = FxSprite {
        orient: Orient::Axis { dir: Vec3::ZERO },
        layer: Layer::Front,
        ..FxSprite::new(s, h * spec.scale, spec.ramp, spec.owner)
    };
    seeded(sprite, spec.heading)
}

fn billboard(s: crate::fx::Seq, h: f32, spec: &ShotSpec) -> FxSprite {
    FxSprite { layer: Layer::Front, ..FxSprite::new(s, h * spec.scale, spec.ramp, spec.owner) }
}

/// The trail of a style, widened for full-charge shots and shrunk for split children.
fn trail(spec: &ShotSpec) -> Option<RibbonStyle> {
    use ProjectileStyle as S;
    let travel = (spec.speed * 0.05).max(0.3);
    let base = match (spec.style, spec.variant) {
        (_, Variant::Javelin) => RibbonStyle { taper: 0.3, ..RibbonStyle::new(strip::DRY_BRUSH, spec.ramp, 0.7, 1.4) },
        (_, Variant::Harpoon) => RibbonStyle { taper: 0.3, ..RibbonStyle::new(strip::DRIP_TRAIL, spec.ramp, 0.7, 1.2) },
        (_, Variant::Disc) => RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::GHOST_SMEAR, spec.ramp, 0.8, 1.2) },
        (_, Variant::Note) => RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::GLINT_TRAIL, spec.ramp, 0.8, 1.6) },
        (_, Variant::Lash) => RibbonStyle { taper: 0.4, ..RibbonStyle::new(strip::TRACER, spec.ramp, 0.4, 0.9) },
        (_, Variant::Dial) => RibbonStyle { taper: 0.6, ..RibbonStyle::new(strip::HELIX, Ramp::Time, 1.0, 1.6) },
        (_, Variant::VoidHeart) => {
            RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::DRIP_TRAIL, Ramp::Void, 1.2, 1.6) }
        }
        (_, Variant::Sac) => RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::DRIP_TRAIL, Ramp::Plague, 1.1, 1.4) },
        (_, Variant::Iron) => {
            RibbonStyle { taper: 0.6, max_age: 0.4, ..RibbonStyle::new(strip::SMOKE_TRAIL, Ramp::Kinetic, 1.2, 2.2) }
        }
        (S::Needle, _) => RibbonStyle { taper: 0.4, ..RibbonStyle::new(strip::NEEDLE_STREAK, spec.ramp, 0.42, 1.2) },
        (S::Pellet, _) => RibbonStyle { taper: 0.4, ..RibbonStyle::new(strip::NEEDLE_STREAK, spec.ramp, 0.38, 0.6) },
        (S::Slug, _) => {
            RibbonStyle { taper: 0.5, erode: 0.03, ..RibbonStyle::new(strip::TRACER, spec.ramp, 0.62, travel.max(1.8)) }
        }
        (S::Fist, _) => RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::DUST_RIBBON, Ramp::Dust, 1.0, 1.4) },
        (S::Arrow, _) => {
            RibbonStyle { taper: 0.35, ..RibbonStyle::new(strip::GHOST_SMEAR, spec.ramp, 0.75, travel.max(1.6)) }
        }
        _ => trail_style(spec.style, spec.ramp, spec.speed)?,
    };
    let k = spec.scale * if spec.charged > 0.9 { 1.25 } else { 1.0 };
    Some(RibbonStyle {
        width: base.width * k,
        max_len: base.max_len * if spec.charged > 0.9 { 1.4 } else { 1.0 },
        gain: base.gain * if spec.charged > 0.9 { 1.3 } else { 1.0 },
        ..base
    })
}

/// Dress `carrier` as a shot in flight: its body (a painted billboard or a packed mesh), its
/// trail, and the accents a modifier adds (a homing seeker glint, a void horizon, a dial).
pub fn dress(commands: &mut Commands, carrier: Entity, spec: &ShotSpec, slot: Option<u8>) {
    use ProjectileStyle as S;
    let mut e = commands.entity(carrier);
    e.insert((Carrier, ShotFx::new(*spec, slot), NotShadowCaster));
    if spec.enemy {
        let sprite = seeded(FxSprite::enemy_shot(spec.radius), spec.heading);
        let streak = RibbonStyle {
            layer: Layer::Danger,
            taper: 0.3,
            ..RibbonStyle::new(strip::NEEDLE_STREAK, Ramp::EnemyShot, 0.42, 0.9)
        };
        e.insert((sprite, FxTrail::new(streak, Owner::Enemy)));
        return;
    }
    let r = spec.radius.max(0.08);
    match (spec.style, spec.variant) {
        (_, Variant::Disc) => {
            e.insert(body(BodyMesh::DiscBlade, spec, 1.3, Vec3::new(0.0, 16.0, 0.0)));
        }
        (_, Variant::Javelin) => {
            e.insert(body(BodyMesh::Javelin, spec, 1.35, Vec3::ZERO));
        }
        (_, Variant::Harpoon) => {
            e.insert(body(BodyMesh::Harpoon, spec, 1.35, Vec3::ZERO));
        }
        (_, Variant::Note) => {
            e.insert(billboard(Pip::Note.seq(), 0.6, spec));
        }
        (_, Variant::Lash) => {
            let mut s = along(seq::BOLT.frames_from(0, 2), 1.0, spec);
            s.size = Vec2::new(1.3, 0.6) * spec.scale;
            s.play = Play::Fps(30.0);
            e.insert(s);
        }
        (S::Needle, _) => {
            e.insert(along(seq::BODY_SMALL.nth(0), 0.85, spec));
        }
        (S::Pellet, _) => {
            e.insert(along(seq::BODY_SMALL.nth(1), 0.7, spec));
        }
        (S::Bolt, _) => {
            e.insert(along(seq::BODY_SMALL.nth(2), 1.0, spec));
        }
        (S::Slug, _) => {
            e.insert(along(seq::BODY_SMALL.nth(3), 1.9, spec));
        }
        (S::Shell, _) => {
            e.insert(body(BodyMesh::Shell, spec, 1.6, Vec3::new(1.6, 0.0, 0.0)));
        }
        (S::Orb, _) => {
            let mut s = billboard(seq::BODY_ORB, (r * 5.0).max(0.95), spec);
            if spec.variant == Variant::Dial {
                s.ramp = Ramp::Radiant;
            }
            e.insert(s);
        }
        (S::Globe, _) => {
            e.insert(billboard(seq::BODY_GLOBE, (r * 4.4).max(1.0), spec));
        }
        (S::Shard, _) => {
            e.insert(body(BodyMesh::Shard, spec, 1.2, Vec3::new(0.0, 0.0, 12.5)));
        }
        (S::Arrow, _) => {
            e.insert(body(BodyMesh::Arrow, spec, 1.45 * if spec.charged > 0.9 { 1.15 } else { 1.0 }, Vec3::ZERO));
        }
        (S::Boulder, _) => {
            let mesh = [BodyMesh::BoulderA, BodyMesh::BoulderB, BodyMesh::BoulderC][(carrier.to_bits() % 3) as usize];
            e.insert(body(mesh, spec, (r / 0.3).clamp(0.8, 2.5), Vec3::new(2.4, 1.1, 0.0)));
        }
        (S::Coin, _) => {
            e.insert(billboard(seq::COIN, 0.6, spec));
        }
        (S::Arc, _) | (S::Blade, _) => {
            e.insert(along(seq::MUZZLE_RAIL, 1.0, spec));
        }
        (S::Fist, _) => {
            e.insert(billboard(seq::GLINT.nth(0), 0.7, spec));
        }
    }
    if let Some(style) = trail(spec) {
        e.insert(FxTrail::new(style, spec.owner));
    }
    // Accents on child quads (the carrier holds one sprite).
    let mut accent = |sprite: FxSprite| {
        commands.spawn((sprite, Transform::default(), Visibility::default(), ChildOf(carrier)));
    };
    match spec.variant {
        Variant::VoidHeart => {
            let mut s = billboard(seq::VOID_SWIRL, (r * 7.0).max(1.6), spec);
            s.layer = Layer::Back;
            s.spin = -3.5;
            s.alpha = 0.85;
            accent(s);
        }
        Variant::Dial => {
            let mut s = billboard(Glyph::ClockDial.seq(), (r * 5.5).max(1.1), spec);
            s.ramp = Ramp::Time;
            s.spin = -1.2;
            s.alpha = 0.8;
            s.layer = Layer::Main;
            accent(s);
        }
        _ => {}
    }
    if spec.homing {
        let mut s = billboard(seq::GLINT.nth(0), 0.45, spec);
        s.spin = 7.0;
        s.gain = 1.4;
        s.pull = 0.5;
        accent(s);
    }
    if spec.charged > 0.9 && matches!(spec.style, S::Arrow | S::Slug) {
        // A full-charge shot carries its own hot glint at the head.
        let mut s = billboard(seq::STAR4.nth(0), 0.55, spec);
        s.value = value::HOT;
        s.spin = 5.0;
        s.pull = 0.5;
        accent(s);
    }
}

/// Advance one shot: the lob arc, the bounce spark, and the style's emitters. `pos` is the
/// carrier's world position this frame; `lob` receives the carrier's height offset.
pub fn tick(fx: &mut Fx, s: &mut ShotFx, pos: Vec3, dt: f32, rope: Option<Vec3>, key: u32) -> f32 {
    use ProjectileStyle as S;
    s.age += dt;
    let spec = s.spec;
    // Heading and the ricochet bounce (a sharp turn between frames; homing turns are gradual).
    if let Some(last) = s.last {
        let d = Vec3::new(pos.x - last.x, 0.0, pos.z - last.z);
        let step = d.length();
        if step > 0.03 {
            let h = d / step;
            s.flown += step;
            if s.age > 3.0 * F && !spec.homing && h.dot(s.heading) < 0.8 && !spec.enemy {
                bounce(fx, pos, h, &spec);
            }
            s.heading = h;
        }
    }
    s.last = Some(pos);
    let owner = spec.owner;
    let ramp = spec.ramp;
    let every = |acc: &mut f32, period: f32| {
        *acc += dt;
        if *acc >= period {
            *acc -= period;
            *acc = acc.min(period);
            true
        } else {
            false
        }
    };
    let back = pos - s.heading * 0.35;
    match (spec.style, spec.variant) {
        (_, Variant::Harpoon) => {
            if let Some(hand) = rope {
                fx.tether(key, hand, pos, 0.28, Ramp::Kinetic, owner);
            }
        }
        (_, Variant::Disc) => {
            // A circular smear around the spinning disc.
            let mut a = Arc::new(strip::SPIN_DISC, pos, 0.62 * spec.scale, 0.34 * spec.scale, 1.0);
            a.start = s.age * 18.0;
            a.sweep = 1.5 * std::f32::consts::PI;
            a.profile = Profile::Crescent { peak: 0.85 };
            a.sweep_anim = Sweep::Static;
            a.ramp = ramp;
            a.gain = 1.15;
            a.erode = Vec2::new(1.0, 0.0);
            a.segments = 20;
            a.pull = 0.3;
            a.layer = Layer::Main;
            fx.arc_now(a, owner, Class::Core);
        }
        (_, Variant::Lash) => {
            if every(&mut s.acc[0], 0.07) {
                crackle(fx, pos, 0.55, ramp, owner);
            }
        }
        (_, Variant::VoidHeart) => {
            if every(&mut s.acc[0], 0.06) {
                // Hex motes spiral into the horizon.
                let d = fx.rand_dir() + Vec3::Y * fx.range(-0.4, 0.6);
                let from = pos + d.normalize_or(Vec3::X) * 1.1;
                let spin = fx.range(-9.0, 9.0);
                fx.sprite(Mote::Hex.seq(), from)
                    .size(0.18)
                    .ramp(Ramp::Void)
                    .gain(1.3)
                    .path(pos, None, 0.3)
                    .spin(spin)
                    .life(0.25)
                    .erode(0.9, 0.6)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        (_, Variant::Sac) => {
            if every(&mut s.acc[0], 0.08) {
                drip(fx, pos - Vec3::Y * 0.3, Ramp::Plague, owner);
            }
        }
        (_, Variant::Iron) => {
            if every(&mut s.acc[0], 0.07) {
                fx.embers(back, 1, 0.2, owner);
            }
            if every(&mut s.acc[1], 0.08) {
                puff(fx, back, 0.28, Ramp::Mono, 0.5, owner);
            }
        }
        (S::Shell, _) => {
            // Ink smoke puffs every 0.06 s that grow and thin with age.
            if every(&mut s.acc[0], 0.06) {
                puff(fx, back, 0.26, Ramp::Kinetic, 0.55, owner);
            }
        }
        (S::Boulder, _) => {
            if every(&mut s.acc[0], 0.07) {
                let off = fx.rand_dir() * 0.2;
                fx.sprite(Mote::Ember.seq(), pos + off)
                    .size(0.16)
                    .vel(Vec3::Y * -1.5)
                    .gravity(8.0)
                    .ramp(Ramp::Flame)
                    .gain(1.4)
                    .life(0.45)
                    .erode(0.6, 1.0)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            if every(&mut s.acc[1], 0.1) {
                puff(fx, back, 0.35, Ramp::Dust, 0.5, owner);
            }
        }
        (S::Orb, _) => {
            if spec.variant == Variant::Dial {
                if every(&mut s.acc[0], 0.12) {
                    let off = fx.rand_dir() * 0.35;
                    fx.sprite(seq::GLINT.nth(1), pos + off)
                        .size(0.22)
                        .ramp(Ramp::Time)
                        .gain(1.3)
                        .vel(Vec3::Y * 0.6)
                        .life(0.3)
                        .erode(0.6, 1.0)
                        .layer(Layer::Front)
                        .class(Class::Secondary)
                        .owner(owner)
                        .emit();
                }
            } else if every(&mut s.acc[0], 0.09) {
                crackle(fx, pos, 0.75, ramp, owner);
            }
        }
        (S::Arrow, _) if ramp == Ramp::Void => {
            // Hex motes peel off the fletching.
            if every(&mut s.acc[0], 0.05) {
                let side = s.heading.cross(Vec3::Y) * fx.range(-1.0, 1.0);
                fx.sprite(Mote::Hex.seq(), back)
                    .size(0.15)
                    .ramp(Ramp::Void)
                    .gain(1.2)
                    .vel(side * 0.9 + Vec3::Y * 0.4)
                    .drag(3.0)
                    .life(0.35)
                    .erode(0.5, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        (S::Coin, _) => {
            // A glint every 6 frames.
            if every(&mut s.acc[0], 6.0 * F) {
                fx.sprite(seq::GLINT.nth(0), pos + Vec3::Y * 0.1)
                    .size(0.35)
                    .ramp(Ramp::Radiant)
                    .gain(1.4)
                    .life(3.0 * F)
                    .pull(0.4)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        (S::Shard, _) => {
            // The lit facet flashes each half-turn.
            if every(&mut s.acc[0], 0.25) {
                fx.sprite(seq::GLINT.nth(2), pos)
                    .size(0.4)
                    .ramp(ramp)
                    .gain(1.4)
                    .life(3.0 * F)
                    .pull(0.4)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        _ => {}
    }
    // The lob: a parabola over the flight range.
    if spec.lob > 0.0 {
        let t = (s.flown / spec.range.max(1.0)).clamp(0.0, 1.0);
        4.0 * spec.lob * t * (1.0 - t)
    } else {
        0.0
    }
}

/// Small crackle licks around a storm body.
fn crackle(fx: &mut Fx, pos: Vec3, r: f32, ramp: Ramp, owner: Owner) {
    let rot = fx.rand() * TAU;
    let off = fx.rand_dir() * 0.15;
    fx.sprite(seq::STORM_CRACKLE, pos + off)
        .radius(r * 0.5)
        .rot(rot)
        .ramp(ramp)
        .play(Play::Life)
        .life(4.0 * F)
        .pull(0.4)
        .layer(Layer::Front)
        .class(Class::Secondary)
        .owner(owner)
        .emit();
}

fn drip(fx: &mut Fx, at: Vec3, ramp: Ramp, owner: Owner) {
    let variant = (fx.rand() * 4.0) as u16;
    fx.sprite(seq::TEARDROP.nth(variant), at)
        .size(0.2)
        .vel(Vec3::Y * -0.5)
        .gravity(10.0)
        .streak(0.06)
        .ramp(ramp)
        .life(0.4)
        .erode(0.6, 1.0)
        .class(Class::Secondary)
        .owner(owner)
        .emit();
}

/// The ricochet bounce (VFX_STYLE §9): a 4-point star and 3 sparks along the new heading; coins
/// "ting" with a bright glint. The trail kinks by itself (it follows the carrier).
fn bounce(fx: &mut Fx, at: Vec3, heading: Vec3, spec: &ShotSpec) {
    let owner = spec.owner;
    fx.sprite(seq::STAR4.nth(1), at)
        .radius(0.35)
        .ramp(spec.ramp)
        .value(value::LIGHT)
        .play(Play::Frame(0))
        .life(4.0 * F)
        .erode(0.4, 1.0)
        .pull(0.5)
        .ink_backed()
        .layer(Layer::Front)
        .owner(owner)
        .emit();
    fx.sparks(at, -heading, 3, 6.0, spec.ramp, owner);
    if spec.style == ProjectileStyle::Coin {
        fx.sprite(seq::GLINT.nth(0), at + Vec3::Y * 0.2)
            .size(0.7)
            .ramp(Ramp::Radiant)
            .value(value::HOT)
            .life(4.0 * F)
            .alpha_curve(Curve::new(1.0, 1.0, 0.0, 0.5))
            .pull(0.5)
            .layer(Layer::Front)
            .owner(owner)
            .emit();
    }
}

/// A shot left the field at `at`: an arrow or javelin sticks in what it hit for 12 frames, an
/// expired shot fizzles.
pub fn stuck_body(commands: &mut Commands, at: Vec3, heading: Vec3, spec: &ShotSpec) {
    use ProjectileStyle as S;
    let mesh = match (spec.style, spec.variant) {
        (_, Variant::Javelin) => BodyMesh::Javelin,
        (S::Arrow, _) => BodyMesh::Arrow,
        (S::Bolt, _) => BodyMesh::Bolt,
        _ => return,
    };
    let mut b = FxBody::new(mesh, spec.ramp, spec.owner, 1.4 * spec.scale);
    b.heading = heading;
    b.last = Some(at);
    let life = if spec.style == S::Bolt { 6.0 * F } else { 12.0 * F };
    commands.spawn((Stuck(life), b, Transform::from_translation(at - heading * 0.2), Visibility::default()));
}

/// A stuck body's remaining life.
#[derive(Component)]
pub struct Stuck(pub f32);

/// The small puff of a shot that ran out of range without a hit.
pub fn fizzle(fx: &mut Fx, at: Vec3, spec: &ShotSpec) {
    if spec.enemy {
        return;
    }
    fx.sprite(seq::STAR4.nth(3), at)
        .radius(0.18)
        .ramp(spec.ramp)
        .life(3.0 * F)
        .erode(0.3, 1.0)
        .class(Class::Secondary)
        .owner(spec.owner)
        .emit();
}
