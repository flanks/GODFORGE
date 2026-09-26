//! Lane A set pieces (docs/art/VFX_STYLE.md §10.4, §12-19): every kit ability, the 12 synergies,
//! faction deaths, elite and boss hit feedback, telegraph resolve punches, zone ambience, team
//! moments and the forge. Pure recipes on the batched engine ([`Fx`]): no entities, no state. The
//! event routing lives in `vfx.rs`, the per-frame auras in [`super::live`], the painted zone
//! shader in [`super::zone`].

use crate::fx::api::{F, Fx, Smear, burst_seq, painted_ramp};
use crate::fx::{Arc, Class, Curve, Decal, Glyph, Layer, Mote, Owner, Pip, Play, Profile, Ramp, RibbonStyle, Sweep};
use crate::fx::{seq, strip, value};
use gf_engine::prelude::*;
use std::f32::consts::{FRAC_PI_2, PI, TAU};

/// Status mote kinds past the sim's status bits.
pub const FROZEN: u8 = 100;
pub const STUNNED: u8 = 101;

/// The playable heroes with a kit (`assets/content/kits.ron`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Default)]
pub enum Hero {
    Valdris,
    Selene,
    Kael,
    Thessaly,
    Brax,
    Ossian,
    Mirren,
    Epoch,
    #[default]
    Other,
}

impl Hero {
    pub fn from_key(key: &str) -> Hero {
        match key {
            "valdris" => Hero::Valdris,
            "selene" => Hero::Selene,
            "kael" => Hero::Kael,
            "thessaly" => Hero::Thessaly,
            "brax" => Hero::Brax,
            "ossian" => Hero::Ossian,
            "mirren" => Hero::Mirren,
            "epoch" => Hero::Epoch,
            _ => Hero::Other,
        }
    }

    /// The hero's signature element ramp (their ability paint).
    pub fn ramp(self) -> Ramp {
        match self {
            Hero::Valdris => Ramp::Kinetic,
            Hero::Selene => Ramp::Storm,
            Hero::Kael | Hero::Thessaly => Ramp::Void,
            Hero::Brax => Ramp::Flame,
            Hero::Ossian => Ramp::Radiant,
            Hero::Mirren => Ramp::ZoneGold,
            Hero::Epoch => Ramp::Time,
            Hero::Other => Ramp::Kinetic,
        }
    }
}

/// Who cast an ability, from where, aiming where.
#[derive(Clone, Copy, Debug)]
pub struct Caster {
    pub slot: u8,
    pub hero: Hero,
    /// Feet (ground height).
    pub at: Vec3,
    /// Unit aim in the ground plane.
    pub aim: Vec3,
    pub owner: Owner,
    pub entity: Option<Entity>,
}

impl Caster {
    fn chest(&self) -> Vec3 {
        self.at + Vec3::Y * 1.1
    }

    fn side(&self) -> Vec3 {
        self.aim.cross(Vec3::Y).normalize_or(Vec3::X)
    }
}

fn ground(at: Vec3) -> Vec3 {
    Vec3::new(at.x, 0.0, at.z)
}

/// Rotate a ground direction about world up.
fn turn(d: Vec3, radians: f32) -> Vec3 {
    Quat::from_rotation_y(radians) * d
}

/// A ribbon on a straight (or lobbed) flight that stops after `time` and erodes away (a linear
/// ribbon otherwise flies on forever).
#[allow(clippy::too_many_arguments)]
pub fn flight(fx: &mut Fx, from: Vec3, vel: Vec3, gravity: f32, style: RibbonStyle, time: f32, owner: Owner) {
    if let Some(id) = fx.trail_linear(from, vel, gravity, style, owner) {
        let now = fx.store.time;
        if let Some(r) = fx.store.ribbon_mut(id) {
            r.expires = Some(now + time.max(F));
        }
    }
}

// ───────────────────────────── status ─────────────────────────────

/// One status mote off a body (VFX_STYLE §12.3): burn embers rise, shock arcs jump, curse hexes
/// drip, plague spores drift, bleed drips fall dark crimson, frost flakes sink, stun glints, mark
/// glints.
pub fn status_mote(fx: &mut Fx, kind: u8, at: Vec3, d: Vec3, owner: Owner) {
    let r = fx.rand();
    match kind {
        0 => {
            fx.sprite(Mote::Ember.seq(), at)
                .size(0.2 + 0.08 * r)
                .vel(d * 0.4 + Vec3::Y * (1.4 + r))
                .gravity(-1.5)
                .drag(1.0)
                .ramp(Ramp::Flame)
                .gain(1.4)
                .life(0.7)
                .erode(0.6, 1.0)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        1 => {
            let first = (r * 6.0) as u16;
            fx.sprite(seq::BOLT.frames_from(first.min(6), 2), at)
                .size2(0.8, 0.28)
                .toward(d + Vec3::Y * (r - 0.5))
                .ramp(Ramp::Storm)
                .play(Play::Fps(30.0))
                .life(5.0 * F)
                .erode(0.5, 1.0)
                .pull(0.5)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        2 => {
            fx.sprite(Mote::Hex.seq(), at)
                .size(0.2)
                .vel(-Vec3::Y * 0.5 + d * 0.2)
                .gravity(2.0)
                .ramp(Ramp::Void)
                .life(0.8)
                .spin(3.0)
                .erode(0.6, 1.0)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        3 => {
            fx.sprite(Mote::Spore.seq(), at)
                .size(0.24)
                .vel(d * 0.7 + Vec3::Y * 0.3)
                .drag(0.8)
                .ramp(Ramp::Plague)
                .life(1.0)
                .erode(0.6, 1.0)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        4 => {
            let v = (r * 4.0) as u16;
            fx.sprite(seq::TEARDROP.nth(v), at)
                .size(0.26)
                .vel(d * 0.6 - Vec3::Y * 0.5)
                .gravity(9.0)
                .streak(0.05)
                .ramp(Ramp::Bleed)
                .play(Play::Frame(0))
                .life(0.5)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        FROZEN => {
            fx.sprite(Mote::Hex.seq(), at)
                .size(0.16)
                .vel(d * 0.3 - Vec3::Y * 0.2)
                .gravity(1.2)
                .spin(2.0)
                .ramp(Ramp::Time)
                .life(0.9)
                .erode(0.6, 1.0)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        STUNNED => {
            fx.sprite(seq::STAR4.nth(1), at + Vec3::Y * 0.4)
                .size(0.34)
                .ramp(Ramp::Radiant)
                .spin(6.0)
                .life(0.3)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        _ => {
            fx.sprite(seq::GLINT.nth(1), at)
                .size(0.3)
                .ramp(Ramp::ZoneGold)
                .vel(Vec3::Y * 0.6)
                .life(0.4)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
    }
}

// ───────────────────────────── shared beats ─────────────────────────────

/// A white impact frame at an arbitrary time (the engine's own is immediate).
fn late_frame(fx: &mut Fx, at: Vec3, radius: f32, delay: f32, owner: Owner) {
    let rot = fx.rand() * TAU;
    fx.sprite(seq::STAR9.nth(0), at)
        .radius(radius)
        .ramp(Ramp::Mono)
        .value(value::HOT)
        .rot(rot)
        .life(2.0 * F)
        .delay(delay)
        .erode(1.0, 0.0)
        .pull(1.2)
        .ink_backed_by(1.35, 0.14)
        .layer(Layer::Top)
        .class(Class::Accent)
        .owner(owner)
        .emit();
}

/// A vertical smear in the plane of `dir` (uppercuts, leaps, slams): positive sweep swings up.
#[allow(clippy::too_many_arguments)]
fn vertical_smear(
    fx: &mut Fx,
    pivot: Vec3,
    dir: Vec3,
    reach: f32,
    sweep: f32,
    strip: crate::fx::Strip,
    ramp: Ramp,
    life: f32,
    owner: Owner,
) {
    let mut s = Smear::new(pivot, dir, reach, ramp, owner);
    s.width = reach * 0.5;
    s.sweep = sweep;
    s.tilt = FRAC_PI_2;
    s.strip = strip;
    s.life = life;
    s.gain = 1.3;
    fx.smear(s);
}

/// A spiral of one element winding into a point over `life`, facing the camera.
#[allow(clippy::too_many_arguments)]
fn wind_in(fx: &mut Fx, c: Vec3, from: f32, to: f32, start: f32, turns: f32, ramp: Ramp, life: f32, owner: Owner) {
    let mut a = Arc::new(strip::SLASH_THIN, c, from, from * 0.22, life);
    a.basis = Quat::from_rotation_arc(Vec3::Y, fx.store.cam.back);
    a.radius = Curve::new(from, (from + to) * 0.5, to, 0.5);
    a.width = Curve::new(from * 0.26, from * 0.2, to * 0.4, 0.5);
    a.start = start;
    a.sweep = turns * TAU;
    a.sweep_anim = Sweep::Swing { lead: 0.55, retract: 0.62 };
    a.profile = Profile::Crescent { peak: 0.7 };
    a.ramp = ramp;
    a.gain = 1.5;
    a.erode = Vec2::new(0.6, 1.0);
    a.segments = 28;
    a.pull = 1.0;
    a.layer = Layer::Front;
    fx.arc(a, owner, Class::Core);
}

/// Mark reticles over bodies (Kael's fan, Ossian's comet and hunt).
pub fn mark_reticle(fx: &mut Fx, at: Vec3, owner: Owner) {
    fx.sprite(Glyph::Mark.seq(), at)
        .size(1.0)
        .ramp(Ramp::ZoneGold)
        .spin(1.5)
        .scale(Curve::new(1.6, 1.0, 1.0, 0.2))
        .life(0.8)
        .erode(0.7, 1.0)
        .layer(Layer::Front)
        .owner(owner)
        .emit();
}

/// Spinning coins thrown up and out (Mirren).
pub fn coins(fx: &mut Fx, at: Vec3, n: u32, speed: f32, owner: Owner) {
    for _ in 0..n {
        let d = fx.rand_dir();
        let up = fx.range(4.0, 7.0);
        let s = fx.range(0.5, 1.0) * speed;
        let life = fx.range(0.8, 1.2);
        let sz = fx.range(0.26, 0.36);
        fx.sprite(seq::COIN, at + Vec3::Y * 0.6)
            .size(sz)
            .vel(d * s + Vec3::Y * up)
            .gravity(16.0)
            .bounce(0.3)
            .ramp(Ramp::ZoneGold)
            .gain(1.3)
            .life(life)
            .erode(0.8, 1.0)
            .layer(Layer::Front)
            .class(Class::Secondary)
            .owner(owner)
            .emit();
    }
}

// ───────────────────────────── abilities ─────────────────────────────

/// The cast beat of a kit ability (`GameEvent::Ability`): 0 = active 1, 1 = active 2, 2 = ult.
/// `targets` are enemy body centres near the caster (marks, reticles).
pub fn ability(fx: &mut Fx, c: &Caster, which: u8, targets: &[Vec3]) {
    let o = c.owner;
    let at = ground(c.at);
    match (c.hero, which) {
        // Valdris: Bulwark Slam (the leap; the landing is `bulwark_landing`).
        (Hero::Valdris, 0) => {
            fx.smoke(at + Vec3::Y * 0.2, 5, 0.7, Ramp::Dust, o);
            fx.ring(at, 0.3, 1.8, 12.0 * F, strip::SHOCK_FRONT, Ramp::Dust, o);
            vertical_smear(
                fx,
                at + Vec3::Y * 0.6,
                c.aim,
                1.8,
                110f32.to_radians(),
                strip::DASH_DRYBRUSH,
                Ramp::Kinetic,
                10.0 * F,
                o,
            );
            fx.sparks(at + Vec3::Y * 0.3, -Vec3::Y, 6, 6.0, Ramp::Kinetic, o);
        }
        // Siege Stance: three anchor spikes punch into the ground with dust; the gold taunt pulse
        // runs in `live` while the stance holds.
        (Hero::Valdris, 1) => {
            for k in 0..3 {
                let d = turn(c.aim, k as f32 * TAU / 3.0 + PI / 3.0);
                let p = at + d * 0.85;
                fx.sprite(seq::SHARD.nth(k * 3), p + Vec3::Y * 0.35)
                    .size(0.95)
                    .rot(PI + fx_tilt(d))
                    .ramp(Ramp::Kinetic)
                    .value(value::DEEP)
                    .scale(Curve::new(1.6, 1.0, 1.0, 0.05))
                    .life(6.0)
                    .erode(0.92, 1.0)
                    .pull(0.2)
                    .owner(o)
                    .emit();
                fx.smoke(p, 2, 0.45, Ramp::Dust, o);
                fx.decal(Decal::CrackStarB, p, 0.7, Ramp::Kinetic, 5.0, o);
            }
            fx.ring(at, 0.4, 3.0, 16.0 * F, strip::ACCENT_RING, Ramp::ZoneGold, o);
            fx.impact_frame(c.chest(), 0.7, 0.5, o);
        }
        // Mountainfall: the avatar rises (auras and pounds in `live`).
        (Hero::Valdris, 2) => {
            fx.impact_frame(at + Vec3::Y * 1.6, 2.0, 0.6, o);
            fx.pillar(at, 9.0, 1.8, Ramp::Flame, 1.2, Owner::World);
            fx.dust_wall(at, 0.5, 4.5, 1.0, 30.0 * F, Ramp::Dust, o);
            fx.ring(at, 0.5, 4.5, 16.0 * F, strip::SHOCK_FRONT, Ramp::ZoneGold, o);
            fx.embers(at + Vec3::Y * 0.4, 22, 1.4, o);
            fx.shards(at + Vec3::Y * 0.3, 8, 6.0, Ramp::Dust, 0.3, o);
            fx.light(at + Vec3::Y * 2.0, Ramp::Flame.light(), 500_000.0, 10.0, 0.6, o);
        }
        // Selene: Arc Nova (the hops arrive as Arc events: bolts with node stars).
        (Hero::Selene, 0) => {
            fx.sprite(seq::STAR4, c.chest())
                .radius(1.3)
                .ramp(Ramp::Storm)
                .play(Play::Life)
                .life(8.0 * F)
                .pull(0.8)
                .ink_backed()
                .layer(Layer::Front)
                .owner(o)
                .emit();
            fx.ring(at, 0.4, 2.4, 10.0 * F, strip::TICK_RING, Ramp::Storm, o);
            fx.light(c.chest(), Ramp::Storm.light(), 120_000.0, 6.0, 0.2, o);
        }
        // Blink: the silhouette breaks into hex sparks (the arrival strike is `blink_arrive`).
        (Hero::Selene, 1) => {
            for _ in 0..20 {
                let d = fx.rand_dir();
                let up = fx.range(-0.6, 1.4);
                let s = fx.range(3.0, 7.0);
                let h = fx.range(0.3, 1.8);
                fx.sprite(Mote::Hex.seq(), at + Vec3::Y * h)
                    .size(0.22)
                    .vel(d * s + Vec3::Y * up)
                    .drag(3.0)
                    .spin(8.0)
                    .ramp(Ramp::Storm)
                    .gain(1.3)
                    .life(0.45)
                    .erode(0.5, 1.0)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(o)
                    .emit();
            }
            fx.sprite(seq::STAR4.nth(2), c.chest()).radius(0.8).ramp(Ramp::Storm).life(4.0 * F).owner(o).emit();
        }
        // Heaven's Verdict: she calls the storm (the storm itself is the zone).
        (Hero::Selene, 2) => {
            fx.bolt(c.chest(), c.chest() + Vec3::Y * 9.0, Ramp::Storm, 0.9, 10.0 * F, o);
            fx.sprite(seq::STAR4, c.chest() + Vec3::Y * 0.6)
                .radius(1.1)
                .ramp(Ramp::Storm)
                .life(6.0 * F)
                .ink_backed()
                .owner(o)
                .emit();
            fx.light(c.chest(), Ramp::Storm.light(), 200_000.0, 8.0, 0.3, o);
        }
        // Kael: Fan of Blades — 7 knife streaks and a cone smear across the 70° cone.
        (Hero::Kael, 0) => {
            let from = c.at + Vec3::Y * 1.0;
            for k in 0..7 {
                let a = (k as f32 / 6.0 - 0.5) * 70f32.to_radians();
                let jitter = fx.range(-0.04, 0.04);
                let d = turn(c.aim, a + jitter);
                fx.sprite(seq::BODY_SMALL.nth(0), from)
                    .size2(0.95, 0.26)
                    .toward(d)
                    .vel(d * 34.0)
                    .ramp(Ramp::Void)
                    .gain(1.3)
                    .life(0.19)
                    .erode(0.8, 1.0)
                    .layer(Layer::Front)
                    .owner(o)
                    .emit();
                let style = RibbonStyle {
                    taper: 0.4,
                    max_age: 0.12,
                    ..RibbonStyle::new(strip::GHOST_SMEAR, Ramp::Void, 0.5, 1.6)
                };
                flight(fx, from, d * 34.0, 0.0, style, 0.19, o);
            }
            for (reach, w) in [(3.2, 1.3), (6.3, 1.7)] {
                let mut s = Smear::new(c.at + Vec3::Y * 0.9, c.aim, reach, Ramp::Void, o);
                s.width = w;
                s.sweep = 72f32.to_radians();
                s.strip = strip::VOID_SMEAR;
                s.life = 10.0 * F;
                fx.smear(s);
            }
            fx.sprite(seq::PETAL_FORWARD_FAN, from)
                .size2(2.2, 2.2 / seq::PETAL_FORWARD_FAN.sheet.cell_aspect())
                .toward(c.aim)
                .ramp(Ramp::Void)
                .play(Play::Life)
                .life(5.0 * F)
                .layer(Layer::Front)
                .owner(o)
                .emit();
            for t in targets {
                let d = (*t - c.at).with_y(0.0);
                let dist = d.length();
                if dist < 7.0 && dist > 0.1 && d.normalize().dot(c.aim) > (35f32.to_radians()).cos() {
                    mark_reticle(fx, *t + Vec3::Y * 0.9, o);
                }
            }
        }
        // Shadow Roll: an ink roll crescent and three afterimages down the roll.
        (Hero::Kael, 1) => {
            let mut s = Smear::new(at + Vec3::Y * 0.6, c.aim, 1.4, Ramp::Void, o);
            s.width = 0.9;
            s.sweep = 220f32.to_radians();
            s.tilt = FRAC_PI_2;
            s.strip = strip::DASH_DRYBRUSH;
            s.life = 14.0 * F;
            fx.smear(s);
            for k in 0..3 {
                let p = at + c.aim * (k as f32 * 1.6 + 0.6) + Vec3::Y * 0.9;
                fx.sprite(seq::SMOKE.in_column(2), p)
                    .radius(0.55)
                    .ramp(Ramp::Void)
                    .value(value::INK)
                    .delay(k as f32 * 0.06)
                    .life(12.0 * F)
                    .play(Play::Life)
                    .erode(0.2, 1.0)
                    .owner(o)
                    .emit();
            }
            for k in 0..3 {
                fx.sprite(Mote::Hex.seq(), c.chest() + Vec3::Y * 0.9 + c.side() * (k as f32 - 1.0) * 0.3)
                    .size(0.22)
                    .ramp(Ramp::Void)
                    .gain(1.4)
                    .life(1.2)
                    .erode(0.8, 1.0)
                    .layer(Layer::Front)
                    .owner(o)
                    .emit();
            }
        }
        // Bullet Ballet: an ink burst and two spectral pistols floating beside him.
        (Hero::Kael, 2) => {
            fx.burst(Ramp::Void, at, 1.4, o);
            if let Some(e) = c.entity {
                for side in [-1.0, 1.0] {
                    fx.sprite(Mote::Hex.seq(), c.side() * side * 0.75 + Vec3::Y * 1.3)
                        .size(0.42)
                        .follow(e)
                        .ramp(Ramp::Void)
                        .gain(1.3)
                        .spin(2.5 * side)
                        .life(6.0)
                        .erode(0.95, 1.0)
                        .layer(Layer::Front)
                        .owner(o)
                        .emit();
                }
            }
        }
        // Thessaly: Forge Turret (the turret's rise is `turret_rise`).
        (Hero::Thessaly, 0) => {
            fx.decal_seq(Glyph::Curse.seq(), at, 1.0, 0.0, Ramp::Void, 0.8, o);
            fx.sparks(c.chest(), Vec3::ZERO, 5, 4.0, Ramp::Kinetic, o);
        }
        (Hero::Thessaly, 1) => {
            fx.sprite(Glyph::BindingHex.seq(), c.chest() + Vec3::Y * 0.5)
                .size(1.1)
                .ramp(Ramp::Void)
                .life(0.5)
                .erode(0.6, 1.0)
                .owner(o)
                .emit();
        }
        // Sabbath of Sparks: a spark fan from her; the turrets throw fountains in `live`.
        (Hero::Thessaly, 2) => {
            fx.sprite(seq::SPARKFX_RADIAL_BURST, c.chest()).size(3.2).ramp(Ramp::Void).owner(o).emit();
            fx.ring(at, 0.4, 4.0, 18.0 * F, strip::SHOCK_FRONT, Ramp::ZoneGold, o);
            fx.impact_frame(c.chest(), 1.0, 0.5, o);
        }
        // Brax: Cinder Uppercut is claimed from its Nova (`uppercut`).
        (Hero::Brax, 0) => {}
        // Furnace Rush: a wide flame smear forward (the wake rides along in `live`).
        (Hero::Brax, 1) => {
            let mut s = Smear::new(c.at + Vec3::Y * 0.9, c.aim, 1.9, Ramp::Flame, o);
            s.width = 1.3;
            s.sweep = 130f32.to_radians();
            s.strip = strip::FLAME_SMEAR;
            s.life = 10.0 * F;
            s.gain = 1.3;
            fx.smear(s);
            fx.smoke(at + Vec3::Y * 0.2, 4, 0.6, Ramp::Dust, o);
        }
        // Meltdown: the furnace opens.
        (Hero::Brax, 2) => {
            fx.impact_frame(c.chest(), 1.6, 0.6, o);
            fx.burst(Ramp::Flame, at, 2.2, o);
            fx.pillar(at, 7.0, 1.4, Ramp::Flame, 0.9, Owner::World);
            fx.tongues(at, 10, 1.4, 1.5, 0.6, o);
        }
        // Ossian: Piercing Comet is claimed from its Line arc (`comet`).
        (Hero::Ossian, 0) => {
            let mut a = Arc::new(strip::TICK_RING, c.chest() + c.aim * 0.6, 1.4, 0.3, 8.0 * F);
            a.basis = Quat::from_rotation_arc(Vec3::Y, fx.store.cam.back);
            a.radius = Curve::new(1.4, 0.7, 0.2, 0.6);
            a.repeats = 4.0;
            a.ramp = Ramp::Radiant;
            a.gain = 1.4;
            a.pull = 0.8;
            a.layer = Layer::Front;
            fx.arc(a, o, Class::Core);
        }
        // Skyhook Mortar: the launch (the lob and landing ride the ally telegraph).
        (Hero::Ossian, 1) => {
            fx.sprite(seq::PETAL_FORWARD_FAN, c.chest())
                .size2(1.6, 1.6 / seq::PETAL_FORWARD_FAN.sheet.cell_aspect())
                .toward(c.aim + Vec3::Y * 1.2)
                .ramp(Ramp::Kinetic)
                .play(Play::Life)
                .life(5.0 * F)
                .layer(Layer::Front)
                .owner(o)
                .emit();
            fx.smoke(c.chest(), 3, 0.4, Ramp::Dust, o);
        }
        // Rain of the Hunt: a gold ray fan and reticles on every marked body in reach.
        (Hero::Ossian, 2) => {
            fx.sprite(seq::RADIANT_RAY_FAN, c.chest()).size(3.2).ramp(Ramp::Radiant).ink_backed().owner(o).emit();
            fx.decal_seq(Glyph::Mark.seq(), at, 1.4, 0.0, Ramp::ZoneGold, 1.2, o);
            for t in targets.iter().take(24) {
                mark_reticle(fx, *t + Vec3::Y * 0.9, o);
            }
        }
        // Mirren: Gilded Decoy (the decoy itself is the zone).
        (Hero::Mirren, 0) => {
            fx.sprite(seq::GLINT.nth(0), c.chest()).size(0.8).ramp(Ramp::ZoneGold).life(6.0 * F).owner(o).emit();
            coins(fx, c.at, 3, 3.0, o);
        }
        // Snatch is claimed from its Blink arc (`snatch`).
        (Hero::Mirren, 1) => {}
        // Grand Heist: a coin fountain and a gold ring.
        (Hero::Mirren, 2) => {
            coins(fx, c.at, 14, 4.0, o);
            fx.ring(at, 0.4, 3.4, 18.0 * F, strip::ACCENT_RING, Ramp::ZoneGold, o);
            fx.sprite(seq::RADIANT_CROSS_FLARE, c.chest())
                .radius(1.1)
                .ramp(Ramp::ZoneGold)
                .ink_backed()
                .owner(o)
                .emit();
        }
        // Epoch: Still Field (the bubble is the zone).
        (Hero::Epoch, 0) => {
            fx.decal_seq(Glyph::ClockDial.seq(), at, 1.0, 0.0, Ramp::Time, 1.0, o);
        }
        // Rewind Wounds: a counter-clockwise clock hand sweeps round her, damage motes rise back.
        (Hero::Epoch, 1) => {
            let mut s = Smear::new(at + Vec3::Y * 0.05, c.aim, 1.7, Ramp::Time, o);
            s.width = 0.55;
            s.sweep = 330f32.to_radians();
            s.strip = strip::WHIP;
            s.life = 28.0 * F;
            fx.smear(s);
            fx.decal_seq(Glyph::ClockDial.seq(), at, 1.3, 0.0, Ramp::Time, 1.2, o);
            for k in 0..10 {
                let d = fx.rand_dir();
                let r = fx.range(0.6, 1.6);
                let h = fx.range(0.8, 1.4);
                let from = at + d * r + Vec3::Y * 0.05;
                let b = fx
                    .sprite(seq::TEARDROP.nth(k % 4), from)
                    .size(0.28)
                    .ramp(Ramp::Bleed)
                    .gain(1.4)
                    .play(Play::Frame(0))
                    .delay(k as f32 * 0.04)
                    .life(0.55)
                    .erode(0.9, 0.6)
                    .layer(Layer::Front)
                    .owner(o);
                let b = match c.entity {
                    Some(e) => b.path(Vec3::Y * h, Some(e), 0.6),
                    None => b.path(c.at + Vec3::Y * h, None, 0.6),
                };
                b.emit();
            }
        }
        // Stolen Second: the clock stops (the freeze and the resume shock front are in `live`).
        (Hero::Epoch, 2) => {
            fx.decal_seq(Glyph::ClockDial.seq(), at, 2.6, 0.0, Ramp::Time, 2.2, o);
            fx.ring(at, 0.5, 16.0, 0.9, strip::TICK_RING, Ramp::Time, o);
            fx.impact_frame(c.chest(), 1.4, 0.5, Owner::World);
        }
        _ => {
            fx.ring(at, 0.4, 2.8, 20.0 * F, strip::SHOCK_FRONT, Ramp::ZoneGold, o);
            fx.smoke(at + Vec3::Y * 0.2, 4, 0.6, Ramp::Dust, o);
        }
    }
}

/// A shard sprite points "up" by default; lean it a little with its direction for variety.
fn fx_tilt(d: Vec3) -> f32 {
    d.x.atan2(d.z) * 0.08
}

/// Bulwark Slam's landing: a heavy downward smear, a ground-crack star, a dust wall at exactly
/// the stun radius, debris, and stun stars over the stunned.
pub fn bulwark_landing(fx: &mut Fx, at: Vec3, radius: f32, aim: Vec3, owner: Owner, stunned: &[Vec3]) {
    let g = ground(at);
    fx.impact_frame(g + Vec3::Y * 0.9, 1.7, 0.6, owner);
    vertical_smear(
        fx,
        g + Vec3::Y * 2.0,
        aim,
        2.3,
        -135f32.to_radians(),
        strip::MELEE_HEAVY,
        Ramp::Kinetic,
        11.0 * F,
        owner,
    );
    let rot = fx.rand() * TAU;
    fx.decal_seq(Decal::CrackStarA.seq(), g, radius * 0.9, rot, Ramp::Kinetic, 3.0, owner);
    fx.decal(Decal::Crater, g, radius * 0.32, Ramp::Dust, 3.0, owner);
    fx.dust_wall(g, radius * 0.4, radius, 0.9, 26.0 * F, Ramp::Dust, owner);
    fx.ring(g, radius * 0.3, radius, 12.0 * F, strip::SHOCK_FRONT, Ramp::Kinetic, owner);
    fx.shards(g + Vec3::Y * 0.3, 10, 7.0, Ramp::Dust, 0.3, owner);
    fx.smoke(g + Vec3::Y * 0.2, 6, 0.9, Ramp::Dust, owner);
    fx.light(g + Vec3::Y * 1.0, Ramp::Kinetic.light(), 260_000.0, 9.0, 0.3, owner);
    for p in stunned.iter().take(16) {
        fx.sprite(Pip::Stun.seq(), *p + Vec3::Y * 0.7)
            .size(0.55)
            .ramp(Ramp::Radiant)
            .spin(5.0)
            .life(1.2)
            .erode(0.85, 1.0)
            .layer(Layer::Front)
            .owner(owner)
            .emit();
    }
}

/// One Mountainfall ground pound: molten gashes out to the true 4.5 m, a gold-lit dust wall on
/// the shock front, a crater, rock debris.
pub fn mountain_pound(fx: &mut Fx, at: Vec3, radius: f32, owner: Owner) {
    let g = ground(at);
    let rot = fx.rand() * TAU;
    fx.decal_seq(Decal::MoltenGashes.seq(), g, radius, rot, Ramp::Flame, 1.5, owner);
    fx.decal(Decal::Crater, g, 1.3, Ramp::Dust, 2.0, owner);
    fx.dust_wall(g, radius * 0.25, radius, 0.8, 24.0 * F, Ramp::GodworksGold, owner);
    fx.ring(g, radius * 0.2, radius, 12.0 * F, strip::SHOCK_FRONT, Ramp::Kinetic, owner);
    fx.shards(g + Vec3::Y * 0.4, 8, 6.5, Ramp::Dust, 0.34, owner);
    fx.impact_frame(g + Vec3::Y * 0.7, 1.4, 0.4, owner);
    fx.light(g + Vec3::Y * 0.8, Ramp::Flame.light(), 300_000.0, 9.0, 0.35, owner);
}

/// Cinder Uppercut: an upward smear in the vertical plane, launch dust, sparks thrown up.
pub fn uppercut(fx: &mut Fx, at: Vec3, aim: Vec3, radius: f32, owner: Owner) {
    let g = ground(at);
    vertical_smear(
        fx,
        g + Vec3::Y * 0.2 + aim * 0.4,
        aim,
        2.5,
        150f32.to_radians(),
        strip::FLAME_SMEAR,
        Ramp::Flame,
        11.0 * F,
        owner,
    );
    fx.impact_frame(g + Vec3::Y * 1.3, 1.2, 0.5, owner);
    fx.dust_wall(g, 0.4, radius, 0.5, 18.0 * F, Ramp::Dust, owner);
    fx.smoke(g + Vec3::Y * 0.2, 5, 0.7, Ramp::Dust, owner);
    fx.sparks(g + Vec3::Y * 0.5, -Vec3::Y, 10, 9.0, Ramp::Flame, owner);
    fx.embers(g + Vec3::Y * 0.3, 8, radius * 0.5, owner);
    fx.light(g + Vec3::Y * 1.2, Ramp::Flame.light(), 180_000.0, 7.0, 0.3, owner);
}

/// Meltdown's strike shockwave: a crescent of flame tongues and dust running forward to the
/// explode radius, instead of a round burst.
pub fn meltdown_wave(fx: &mut Fx, from: Vec3, at: Vec3, radius: f32, owner: Owner) {
    let g = ground(at);
    let d = (g - ground(from)).normalize_or(Vec3::NEG_Z);
    let mut s =
        Smear::new(ground(from) + Vec3::Y * 0.5, d, g.distance(ground(from)) + radius * 0.7, Ramp::Flame, owner);
    s.width = radius * 0.8;
    s.sweep = 95f32.to_radians();
    s.strip = strip::FLAME_SMEAR;
    s.life = 12.0 * F;
    s.gain = 1.3;
    fx.smear(s);
    for k in 0..6 {
        let a = (k as f32 / 5.0 - 0.5) * 90f32.to_radians();
        let p = g + turn(d, a) * radius * 0.7;
        let h = fx.range(0.8, 1.2);
        fx.sprite(seq::FLAME_MEDIUM, p)
            .size(h)
            .ramp(Ramp::Flame)
            .delay(k as f32 * 0.015)
            .life(0.4)
            .scale(Curve::new(0.3, 1.0, 0.5, 0.2))
            .erode(0.6, 1.0)
            .pull(0.3)
            .owner(owner)
            .emit();
    }
    fx.sprite(burst_seq(Ramp::Flame), g + Vec3::Y * 0.25)
        .radius(radius * 0.7)
        .ramp(Ramp::Flame)
        .erode(0.7, 0.8)
        .owner(owner)
        .emit();
    fx.smoke(g + Vec3::Y * 0.3, 2, 0.6, Ramp::Dust, owner);
    fx.embers(g + Vec3::Y * 0.4, 4, radius * 0.4, owner);
}

/// Selene's Blink arrival: a bolt strikes where she lands; the storm line along the path.
pub fn blink_arrive(fx: &mut Fx, from: Vec3, to: Vec3, owner: Owner) {
    let (a, b) = (ground(from), ground(to));
    fx.bolt(b + Vec3::Y * 7.5, b + Vec3::Y * 0.1, Ramp::Storm, 1.0, 8.0 * F, owner);
    fx.bolt(a + Vec3::Y * 0.15, b + Vec3::Y * 0.15, Ramp::Storm, 0.45, 10.0 * F, owner);
    fx.sprite(seq::STAR4, b + Vec3::Y * 0.3)
        .radius(1.0)
        .ramp(Ramp::Storm)
        .play(Play::Life)
        .life(6.0 * F)
        .ink_backed()
        .owner(owner)
        .emit();
    let n = (a.distance(b) / 2.2).ceil().max(1.0) as u32;
    for k in 0..=n {
        let p = a.lerp(b, k as f32 / n as f32);
        let v = (fx.rand() * 4.0) as u16;
        let rot = fx.rand() * TAU;
        fx.decal_seq(seq::STORM_LICHTENBERG.nth(v), p, 0.9, rot, Ramp::Storm, 1.6, owner);
    }
    fx.light(b + Vec3::Y, Ramp::Storm.light(), 160_000.0, 7.0, 0.25, owner);
}

/// Piercing Comet: a comet head races down the line in 6 frames, a white-gold core line, Mark
/// reticles on everything pierced (the straight scar is a zone ghost).
pub fn comet(fx: &mut Fx, from: Vec3, to: Vec3, owner: Owner, pierced: &[Vec3]) {
    let a = ground(from) + Vec3::Y * 1.0;
    let b = ground(to) + Vec3::Y * 1.0;
    let vel = (b - a) / (6.0 * F);
    fx.sprite(seq::RADIANT_CROSS_FLARE, a)
        .size(1.8)
        .vel(vel)
        .ramp(Ramp::Radiant)
        .gain(1.5)
        .life(6.0 * F)
        .layer(Layer::Front)
        .owner(owner)
        .emit();
    let core = RibbonStyle { taper: 0.25, max_age: 0.35, ..RibbonStyle::new(strip::TRACER, Ramp::Radiant, 1.2, 30.0) };
    flight(fx, a, vel, 0.0, core, 6.0 * F, owner);
    let beam =
        RibbonStyle { taper: 0.5, max_age: 0.22, ..RibbonStyle::new(strip::BEAM_CORE, Ramp::Radiant, 0.6, 30.0) };
    flight(fx, a, vel, 0.0, beam, 6.0 * F, owner);
    fx.sprite(seq::STAR4, b)
        .radius(0.9)
        .ramp(Ramp::Radiant)
        .delay(6.0 * F)
        .life(6.0 * F)
        .ink_backed()
        .owner(owner)
        .emit();
    for p in pierced.iter().take(20) {
        mark_reticle(fx, *p + Vec3::Y * 0.9, owner);
    }
    fx.light(a, Ramp::Radiant.light(), 150_000.0, 6.0, 0.2, owner);
}

/// Snatch: a gold silhouette streak to the elite and a slash on arrival.
pub fn snatch(fx: &mut Fx, from: Vec3, to: Vec3, owner: Owner) {
    let a = ground(from) + Vec3::Y * 1.0;
    let b = ground(to) + Vec3::Y * 1.0;
    let style =
        RibbonStyle { taper: 0.3, max_age: 0.3, ..RibbonStyle::new(strip::GHOST_SMEAR, Ramp::ZoneGold, 1.4, 20.0) };
    flight(fx, a, (b - a) / (5.0 * F), 0.0, style, 5.0 * F, owner);
    let d = (b - a).normalize_or(Vec3::X);
    fx.slash(b, turn(d, FRAC_PI_2 * 0.7), 2.6, Ramp::ZoneGold, owner);
    fx.sprite(seq::STAR4, b)
        .radius(0.7)
        .ramp(Ramp::ZoneGold)
        .value(value::HOT)
        .life(4.0 * F)
        .ink_backed()
        .owner(owner)
        .emit();
}

/// The Skyhook shell arcing to its landing zone over `time` seconds (a visible lob).
pub fn mortar_lob(fx: &mut Fx, from: Vec3, to: Vec3, time: f32, owner: Owner) {
    let t = time.max(0.2);
    let g = 22.0;
    let a = ground(from) + Vec3::Y * 1.4;
    let b = ground(to) + Vec3::Y * 0.2;
    let horiz = (b - a).with_y(0.0) / t;
    let vy = ((b.y - a.y) + 0.5 * g * t * t) / t;
    let vel = horiz + Vec3::Y * vy;
    fx.sprite(seq::BODY_SMALL.nth(3), a)
        .size(0.9)
        .vel(vel)
        .gravity(g)
        .streak(0.02)
        .ramp(Ramp::Kinetic)
        .gain(1.3)
        .life(t)
        .erode(1.0, 0.0)
        .layer(Layer::Front)
        .owner(owner)
        .emit();
    let smoke = RibbonStyle { taper: 0.6, max_age: 0.4, ..RibbonStyle::new(strip::SMOKE_TRAIL, Ramp::Dust, 0.9, 3.0) };
    // The trail ends when the shell lands (the ribbon follows the flight analytically).
    flight(fx, a, vel, g, smoke, t, owner);
}

/// The mortar's bomblets: 5 small charges scatter from the landing and pop in the flame field.
pub fn bomblets(fx: &mut Fx, at: Vec3, radius: f32, owner: Owner) {
    let g = ground(at);
    for k in 0..5 {
        let d = turn(Vec3::X, k as f32 * TAU / 5.0 + fx.range(-0.3, 0.3));
        let dist = fx.range(0.5, 0.95) * radius;
        let t = fx.range(0.35, 0.5);
        let vel = d * dist / t + Vec3::Y * (0.5 * 16.0 * t);
        fx.sprite(seq::SHARD.nth(k), g + Vec3::Y * 0.4)
            .size(0.3)
            .vel(vel)
            .gravity(16.0)
            .spin(12.0)
            .ramp(Ramp::Kinetic)
            .life(t)
            .owner(owner)
            .emit();
        let land = g + d * dist;
        fx.sprite(burst_seq(Ramp::Flame), land + Vec3::Y * 0.2)
            .radius(0.9)
            .ramp(Ramp::Flame)
            .delay(t)
            .erode(0.7, 0.8)
            .owner(owner)
            .emit();
    }
}

/// Gilded Decoy's end: a coin fountain.
pub fn decoy_pop(fx: &mut Fx, at: Vec3, owner: Owner) {
    coins(fx, at, 16, 4.5, owner);
    fx.sprite(seq::RADIANT_CROSS_FLARE, ground(at) + Vec3::Y * 1.0)
        .radius(1.3)
        .ramp(Ramp::ZoneGold)
        .ink_backed()
        .owner(owner)
        .emit();
}

/// Stolen Second's resume: a gold "tick" shock front rolling out from Epoch.
pub fn time_resume(fx: &mut Fx, at: Vec3, owner: Owner) {
    let g = ground(at);
    fx.ring(g, 0.5, 14.0, 0.8, strip::TICK_RING, Ramp::ZoneGold, owner);
    fx.ring(g, 0.5, 12.0, 0.6, strip::SHOCK_FRONT, Ramp::ZoneGold, owner);
    fx.sprite(Glyph::ClockDial.seq(), g + Vec3::Y * 1.6)
        .size(1.6)
        .ramp(Ramp::ZoneGold)
        .life(0.4)
        .erode(0.4, 1.0)
        .owner(owner)
        .emit();
}

// ───────────────────────────── synergies ─────────────────────────────

/// A synergy set piece (VFX_STYLE §13). `ea`/`eb` are the two elements' ramps, `radius` the
/// burst radius when the synergy bursts, `hops` the chain segments when it chains, `targets`
/// enemy body centres near the trigger point, `allies` the players inside (Purge heals).
#[allow(clippy::too_many_arguments)]
pub fn synergy(
    fx: &mut Fx,
    key: &str,
    at: Vec3,
    ea: Ramp,
    eb: Ramp,
    radius: Option<f32>,
    hops: &[(Vec3, Vec3)],
    targets: &[Vec3],
    allies: &[Entity],
    owner: Owner,
) {
    let g = ground(at);
    let c = g + Vec3::Y * 0.9;
    // The trigger beat: a spiral of each element winds into the target and snaps white.
    let start = fx.rand() * TAU;
    wind_in(fx, c, 2.6, 0.25, start, 0.9, ea, 7.0 * F, owner);
    wind_in(fx, c, 2.6, 0.25, start + PI, 0.9, eb, 7.0 * F, owner);
    late_frame(fx, c, 1.0, 6.0 * F, owner);
    let r = radius.unwrap_or(3.0);
    let inside = |p: &&Vec3| ground(**p).distance(g) <= r + 0.5;
    match key {
        "blightburn" => {
            // Green sacs bloat for 4 frames, then ignite into a green-cored flame burst.
            for p in targets.iter().filter(inside).take(10) {
                fx.sprite(seq::PLAGUE_BUBBLE, *p)
                    .size(0.9)
                    .ramp(Ramp::Plague)
                    .play(Play::Life)
                    .life(5.0 * F)
                    .owner(owner)
                    .emit();
            }
            fx.burst(Ramp::Flame, g, r, owner);
            fx.sprite(seq::PLAGUE_SPLAT, g + Vec3::Y * 0.6)
                .radius(r * 0.5)
                .ramp(Ramp::Plague)
                .delay(3.0 * F)
                .owner(owner)
                .emit();
            for _ in 0..10 {
                let d = fx.rand_dir();
                let s = fx.range(2.0, 5.0);
                fx.sprite(Mote::Spore.seq(), g + Vec3::Y * 1.2)
                    .size(0.24)
                    .vel(d * s + Vec3::Y * 3.0)
                    .gravity(6.0)
                    .ramp(Ramp::Flame)
                    .gain(1.3)
                    .life(0.8)
                    .erode(0.6, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            fx.decal(Decal::RotScar, g, r * 0.8, Ramp::Plague, 3.0, owner);
        }
        "gravity_chain" => {
            fx.decal_seq(seq::VOID_SWIRL.nth(0), g, 1.6, 0.0, Ramp::Void, 1.0, owner);
            for (a, b) in hops {
                let (a, b) = (*a + Vec3::Y * 0.9, *b + Vec3::Y * 0.9);
                // An ink sheath under a violet bolt.
                let len = a.distance(b);
                fx.sprite(seq::BOLT.frames_from(3, 2), a)
                    .size2(len, 1.3)
                    .toward(b - a)
                    .ramp(Ramp::Void)
                    .value(value::INK)
                    .play(Play::Fps(30.0))
                    .life(10.0 * F)
                    .erode(0.5, 1.0)
                    .layer(Layer::Main)
                    .owner(owner)
                    .emit();
                fx.bolt(a, b, Ramp::Void, 0.8, 10.0 * F, owner);
                fx.sprite(seq::PETAL_INWARD_STAR, b)
                    .radius(0.9)
                    .ramp(Ramp::Void)
                    .play(Play::Life)
                    .life(8.0 * F)
                    .ink_backed()
                    .owner(owner)
                    .emit();
                // Drag lines toward the origin.
                let d = (g - ground(b)).normalize_or(Vec3::X);
                fx.slash(b - Vec3::Y * 0.5 + d * 0.8, d, 1.8, Ramp::Void, owner);
            }
        }
        "firestorm" => {
            fx.burst(Ramp::Storm, g, 1.2, owner);
            fx.tongues(g, 14, r, 1.1, 0.5, owner);
        }
        "collapsing_star" => {
            // An orange flare sucked into a black point, a white-violet pop, a violet shock front,
            // ember sparks falling inward.
            fx.sprite(seq::BURST_FLAME.nth(3), c)
                .radius(r * 0.6)
                .ramp(Ramp::Flame)
                .scale(Curve::new(1.0, 0.6, 0.05, 0.5))
                .life(6.0 * F)
                .erode(1.0, 0.0)
                .owner(owner)
                .emit();
            fx.sprite(seq::PETAL_INWARD_STAR, c)
                .radius(r * 0.5)
                .ramp(Ramp::Void)
                .value(value::INK)
                .play(Play::Life)
                .life(6.0 * F)
                .owner(owner)
                .emit();
            fx.sprite(seq::STAR9.nth(0), c)
                .radius(r * 0.55)
                .ramp(Ramp::Void)
                .value(value::HOT)
                .delay(6.0 * F)
                .life(2.0 * F)
                .erode(1.0, 0.0)
                .layer(Layer::Top)
                .ink_backed_by(1.35, 0.14)
                .owner(owner)
                .emit();
            fx.sprite(burst_seq(Ramp::Void), g + Vec3::Y * 0.25)
                .radius(r)
                .ramp(Ramp::Void)
                .delay(6.0 * F)
                .erode(0.75, 0.8)
                .owner(owner)
                .emit();
            fx.ring(g, r * 0.3, r, 14.0 * F, strip::SHOCK_FRONT, Ramp::Void, owner);
            for _ in 0..10 {
                let d = fx.rand_dir();
                let p = g + d * r * 0.9 + Vec3::Y * fx.range(0.4, 1.4);
                fx.sprite(seq::SPARK.nth(2), p)
                    .size(0.2)
                    .vel(-d * 5.0 - Vec3::Y * 1.0)
                    .streak(0.06)
                    .ramp(Ramp::Flame)
                    .delay(8.0 * F)
                    .life(0.35)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            fx.decal(Decal::InkStainB, g, r * 0.7, Ramp::Void, 2.5, owner);
        }
        "solar_flare" => {
            fx.sprite(seq::RADIANT_SUNBURST, g + Vec3::Y * 0.04)
                .radius(r)
                .ground()
                .ramp(Ramp::Radiant)
                .life(0.9)
                .alpha_curve(Curve::new(1.0, 0.9, 0.0, 0.5))
                .erode(0.5, 1.0)
                .owner(owner)
                .emit();
            fx.burst(Ramp::Radiant, g, r, owner);
            // Three solar prominences: flame loops arcing out and back.
            for k in 0..3 {
                let d = turn(Vec3::X, k as f32 * TAU / 3.0 + start);
                let mut a = Arc::new(strip::FLAME_SMEAR, g + d * r * 0.35 + Vec3::Y * 0.2, r * 0.45, 0.5, 18.0 * F);
                a.basis = Quat::from_rotation_arc(Vec3::NEG_Z, d) * Quat::from_rotation_z(FRAC_PI_2);
                a.start = -PI * 0.5;
                a.sweep = PI;
                a.sweep_anim = Sweep::Swing { lead: 0.4, retract: 0.6 };
                a.profile = Profile::Crescent { peak: 0.6 };
                a.ramp = Ramp::Flame;
                a.gain = 1.4;
                a.erode = Vec2::new(0.5, 1.0);
                a.segments = 20;
                a.pull = 0.4;
                fx.arc(a, owner, Class::Core);
            }
            for p in targets.iter().filter(inside).take(12) {
                mark_reticle(fx, *p + Vec3::Y * 0.9, owner);
            }
        }
        "toxic_conduit" => {
            for _ in 0..5 {
                let d = fx.rand_dir();
                let len = fx.range(0.6, 1.0) * r;
                let end = g + d * len + Vec3::Y * 0.4;
                fx.bolt(c, end, Ramp::Plague, 0.6, 9.0 * F, owner);
                let v = (fx.rand() * 4.0) as u16;
                fx.sprite(seq::TEARDROP.nth(v), end)
                    .size(0.34)
                    .vel(d * 2.0 + Vec3::Y * 2.5)
                    .gravity(12.0)
                    .streak(0.06)
                    .ramp(Ramp::Plague)
                    .play(Play::Frame(0))
                    .life(0.5)
                    .owner(owner)
                    .emit();
            }
            fx.burst(Ramp::Plague, g, r, owner);
            for _ in 0..4 {
                let off = fx.rand_dir() * fx.range(0.3, 0.8) * r;
                fx.sprite(seq::PLAGUE_SPORES, g + off + Vec3::Y * 0.6)
                    .radius(0.9)
                    .ramp(Ramp::Plague)
                    .life(1.2)
                    .erode(0.6, 1.0)
                    .class(Class::Smoke)
                    .owner(owner)
                    .emit();
            }
            for p in targets.iter().filter(inside).take(10) {
                fx.sprite(Glyph::Curse.seq(), *p + Vec3::Y * 1.2)
                    .size(0.8)
                    .ramp(Ramp::Void)
                    .life(0.9)
                    .erode(0.7, 1.0)
                    .owner(owner)
                    .emit();
            }
        }
        "judgment_bolt" => {
            let mut nodes: Vec<Vec3> = hops.iter().map(|h| h.1).collect();
            if nodes.is_empty() {
                nodes.push(g);
            }
            for (a, b) in hops {
                // Law, not jagged: a straight segmented gold-white line.
                let (a, b) = (*a + Vec3::Y * 0.9, *b + Vec3::Y * 0.9);
                let style = RibbonStyle {
                    taper: 0.2,
                    max_age: 0.25,
                    ..RibbonStyle::new(strip::BEAM_CORE, Ramp::Radiant, 0.7, 30.0)
                };
                flight(fx, a, (b - a) / (3.0 * F), 0.0, style, 3.0 * F, owner);
            }
            for (k, b) in nodes.iter().enumerate() {
                let b = ground(*b);
                fx.pillar(b, 8.0, 0.8, Ramp::Radiant, 0.35, owner);
                fx.sprite(seq::RADIANT_CROSS_FLARE, b + Vec3::Y * 0.9)
                    .radius(1.0)
                    .ramp(Ramp::Radiant)
                    .delay(k as f32 * 2.0 * F)
                    .ink_backed()
                    .owner(owner)
                    .emit();
                fx.decal_seq(Glyph::Hexagram.seq(), b, 1.1, 0.0, Ramp::Radiant, 1.5, owner);
            }
        }
        "entropy_bloom" => {
            fx.sprite(seq::PETAL_INWARD_STAR, c)
                .radius(r * 0.5)
                .ramp(Ramp::Void)
                .value(value::INK)
                .play(Play::Life)
                .life(8.0 * F)
                .owner(owner)
                .emit();
            fx.sprite(seq::PLAGUE_SPLAT, c).radius(r * 0.4).ramp(Ramp::Plague).delay(3.0 * F).owner(owner).emit();
        }
        "eclipse" => {
            // A black disc slides over a gold disc: only the corona is bright, held 8 frames.
            fx.sprite(seq::RADIANT_HALO_ARCS, c + Vec3::Y * 0.6)
                .radius(r * 0.55)
                .ramp(Ramp::Radiant)
                .gain(1.4)
                .life(14.0 * F)
                .play(Play::Life)
                .owner(owner)
                .emit();
            let right = fx.store.cam.right;
            fx.sprite(seq::BODY_CHARGE_CORE.nth(0), c + Vec3::Y * 0.6 + right * 0.5)
                .radius(r * 0.36)
                .vel(-right * 3.0)
                .ramp(Ramp::Void)
                .value(value::INK)
                .life(14.0 * F)
                .erode(0.8, 1.0)
                .pull(0.9)
                .layer(Layer::Front)
                .owner(owner)
                .emit();
            fx.sprite(burst_seq(Ramp::Void), g + Vec3::Y * 0.25)
                .radius(r)
                .ramp(Ramp::Void)
                .delay(8.0 * F)
                .erode(0.75, 0.8)
                .owner(owner)
                .emit();
            fx.ring(g, r * 0.3, r, 16.0 * F, strip::SHOCK_FRONT, Ramp::Void, owner);
            fx.light(c, Ramp::Radiant.light(), 160_000.0, 8.0, 0.3, owner);
            for p in targets.iter().filter(inside).take(10) {
                fx.sprite(Glyph::Curse.seq(), *p + Vec3::Y * 1.2)
                    .size(0.8)
                    .ramp(Ramp::Void)
                    .delay(8.0 * F)
                    .life(0.9)
                    .erode(0.7, 1.0)
                    .owner(owner)
                    .emit();
            }
        }
        "purge" => {
            let rr = radius.unwrap_or(6.0);
            // Gold rain falls in the radius.
            for k in 0..28 {
                let off = fx.rand_dir() * rr * fx.rand().sqrt();
                let h = fx.range(4.0, 6.0);
                fx.sprite(seq::SPARK.nth(k % 8), g + off + Vec3::Y * h)
                    .size(0.3)
                    .vel(Vec3::new(0.0, -14.0, 0.0))
                    .streak(0.05)
                    .ramp(Ramp::Radiant)
                    .gain(1.3)
                    .delay(k as f32 * 0.025)
                    .life(0.34)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            fx.ring(g, 0.5, rr, 20.0 * F, strip::ACCENT_RING, Ramp::Heal, owner);
            for p in targets.iter().filter(|p| ground(**p).distance(g) <= rr).take(12) {
                fx.sprite(Mote::Spore.seq(), *p + Vec3::Y * 0.8)
                    .size(0.3)
                    .vel(Vec3::Y * 2.0)
                    .ramp(Ramp::Plague)
                    .life(0.3)
                    .owner(owner)
                    .emit();
                fx.sparks(*p + Vec3::Y * 1.0, -Vec3::Y, 3, 4.0, Ramp::Radiant, owner);
            }
            for e in allies {
                fx.motes(c, *e, 2, Ramp::Heal, owner);
            }
        }
        "shrapnel_blaze" => {
            // A fan of molten brass shards with fire trails.
            for k in 0..10 {
                let d = turn(Vec3::X, k as f32 * TAU / 10.0 + fx.range(-0.2, 0.2));
                let v = d * fx.range(10.0, 14.0) + Vec3::Y * fx.range(1.0, 3.0);
                let from = g + Vec3::Y * 0.7;
                fx.sprite(seq::SHARD.nth(k % 8), from)
                    .size(0.32)
                    .vel(v)
                    .gravity(8.0)
                    .spin(14.0)
                    .ramp(Ramp::Kinetic)
                    .value(value::LIGHT)
                    .life(r / 12.0)
                    .layer(Layer::Front)
                    .owner(owner)
                    .emit();
                let style = RibbonStyle {
                    taper: 0.5,
                    max_age: 0.18,
                    ..RibbonStyle::new(strip::FLAME_TRAIL, Ramp::Flame, 0.5, 1.4)
                };
                flight(fx, from, v, 8.0, style, r / 12.0, owner);
            }
            fx.burst(Ramp::Kinetic, g, r, owner);
            for p in targets.iter().filter(inside).take(10) {
                status_mote(fx, 4, *p + Vec3::Y * 0.8, Vec3::X * 0.2, owner);
            }
        }
        "railshock" => {
            for (a, b) in hops {
                let (a, b) = (*a + Vec3::Y * 0.8, *b + Vec3::Y * 0.8);
                let style = RibbonStyle {
                    taper: 0.1,
                    max_age: 0.4,
                    ..RibbonStyle::new(strip::TRACER, Ramp::Kinetic, 0.55, 30.0)
                };
                flight(fx, a, (b - a) / (2.0 * F), 0.0, style, 2.0 * F, owner);
                fx.bolt(a, b, Ramp::Storm, 0.4, 12.0 * F, owner);
                // Magnetized shards snap toward the node.
                for _ in 0..3 {
                    let off = fx.rand_dir() * 1.2 + Vec3::Y * fx.range(-0.3, 0.6);
                    fx.sprite(seq::SHARD.nth(1), b + off)
                        .size(0.26)
                        .ramp(Ramp::Kinetic)
                        .path(b, None, 0.2)
                        .life(0.2)
                        .layer(Layer::Front)
                        .owner(owner)
                        .emit();
                }
                fx.sprite(seq::STAR4, b).radius(0.6).ramp(Ramp::Storm).life(5.0 * F).ink_backed().owner(owner).emit();
            }
        }
        _ => {
            fx.burst(eb, g, r, owner);
        }
    }
    fx.ring(g, 0.5, r, 20.0 * F, strip::ACCENT_RING, Ramp::ZoneGold, owner);
}

// ───────────────────────────── deaths and hits ─────────────────────────────

/// The faction secondaries of a kill (VFX_STYLE §15.3): Unmade ichor teardrops and a black-teal
/// puff; Godworks cold-gold sparks, porcelain shards and dead-ember smoke.
pub fn death_extras(fx: &mut Fx, ramp: Ramp, at: Vec3, radius: f32, owner: Owner) {
    let g = ground(at);
    match ramp {
        Ramp::Unmade => {
            for _ in 0..4 {
                let d = fx.rand_dir();
                let v = d * fx.range(2.0, 4.5) + Vec3::Y * fx.range(3.0, 5.0);
                let k = (fx.rand() * 4.0) as u16;
                fx.sprite(seq::TEARDROP.nth(k), g + Vec3::Y * (0.4 + radius * 0.4))
                    .size(0.3)
                    .vel(v)
                    .gravity(14.0)
                    .streak(0.06)
                    .ramp(Ramp::Unmade)
                    .play(Play::Frame(0))
                    .life(0.55)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            fx.smoke(g + Vec3::Y * 0.3, 1, 0.4 + radius * 0.3, Ramp::Unmade, owner);
        }
        Ramp::GodworksGold | Ramp::GodworksEmber => {
            fx.sparks(g + Vec3::Y * (0.4 + radius * 0.3), Vec3::ZERO, 5, 5.0, Ramp::GodworksGold, owner);
            fx.shards(g + Vec3::Y * 0.5, 2, 4.0, Ramp::Mono, 0.18, owner);
            fx.smoke(g + Vec3::Y * 0.3, 2, 0.4 + radius * 0.3, Ramp::GodworksEmber, owner);
        }
        _ => {}
    }
}

/// A boss death set piece: three staggered faction bursts, a 4-frame impact frame, a shock front
/// across the arena, a pillar of faction light and heavy debris.
pub fn boss_death(fx: &mut Fx, ramp: Ramp, at: Vec3, radius: f32) {
    let g = ground(at);
    let o = Owner::World;
    fx.impact_frame(g + Vec3::Y * (1.0 + radius * 0.5), radius * 1.4, radius, o);
    late_frame(fx, g + Vec3::Y * (1.0 + radius * 0.5), radius * 1.2, 2.0 * F, o);
    for k in 0..3 {
        let off = fx.rand_dir() * radius * 0.5 + Vec3::Y * (0.5 + k as f32 * 0.4);
        fx.sprite(burst_seq(ramp), g + off)
            .radius(radius * (1.0 + k as f32 * 0.3))
            .ramp(painted_ramp(burst_seq(ramp), ramp))
            .delay(k as f32 * 8.0 * F)
            .erode(0.75, 0.8)
            .owner(o)
            .emit();
    }
    fx.ring(g, radius, radius + 9.0, 0.9, strip::SHOCK_FRONT, Ramp::Mono, o);
    fx.dust_wall(g, radius, radius + 5.0, 1.2, 0.7, Ramp::Dust, o);
    fx.pillar(g, 12.0, radius * 1.2, ramp, 1.4, o);
    fx.shards(g + Vec3::Y * radius, 12, 8.0, ramp, 0.4, o);
    fx.smoke(g + Vec3::Y * 0.5, 8, radius, Ramp::Dust, o);
    fx.light(g + Vec3::Y * 2.0, ramp.light(), 800_000.0, radius * 4.0 + 8.0, 1.0, o);
}

/// A glancing spark off a plated elite: element-agnostic grey-white, skipping off the surface.
pub fn glance(fx: &mut Fx, at: Vec3, travel: Vec3, owner: Owner) {
    let side = travel.cross(Vec3::Y).normalize_or(Vec3::X);
    let d = if fx.rand() < 0.5 { side } else { -side };
    fx.sparks(at, -d, 4, 8.0, Ramp::Mono, owner);
    fx.sprite(seq::STAR4.nth(1), at)
        .radius(0.3)
        .ramp(Ramp::Mono)
        .value(value::LIGHT)
        .life(3.0 * F)
        .ink_backed()
        .layer(Layer::Front)
        .owner(owner)
        .emit();
}

/// A hex ripple over a shielded body.
pub fn shield_ripple(fx: &mut Fx, center: Vec3, radius: f32, ramp: Ramp, owner: Owner) {
    let mut a = Arc::new(strip::HEX_BAND, center, radius * 1.1, radius * 0.35, 9.0 * F);
    a.basis = Quat::from_rotation_arc(Vec3::Y, fx.store.cam.back);
    a.radius = Curve::new(radius * 0.9, radius * 1.15, radius * 1.25, 0.4);
    a.repeats = (radius * 3.0).clamp(3.0, 10.0);
    a.ramp = ramp;
    a.gain = 1.2;
    a.pull = radius + 0.2;
    a.erode = Vec2::new(0.3, 1.0);
    a.layer = Layer::Front;
    fx.arc(a, owner, Class::Core);
}

/// Hex shards when a shield breaks (a shield flag dropping).
pub fn shield_break(fx: &mut Fx, center: Vec3, radius: f32, ramp: Ramp) {
    fx.shards(center, 8, 6.0, ramp, 0.26, Owner::World);
    shield_ripple(fx, center, radius * 1.2, ramp, Owner::World);
}

// ───────────────────────────── telegraph resolve ─────────────────────────────

/// The resolve punch of an enemy telegraph (VFX_STYLE §15.1): in the attacker's faction style,
/// inside the telegraph's shape, ≤ 10 frames. `dir` is the telegraph's forward (ground).
pub fn telegraph_punch(fx: &mut Fx, shape: gf_content::TelegraphShape, at: Vec3, dir: Vec3, ramp: Ramp) {
    use gf_content::TelegraphShape as T;
    let o = Owner::Enemy;
    let g = ground(at);
    match shape {
        T::Circle { radius } => {
            fx.sprite(burst_seq(ramp), g + Vec3::Y * 0.2)
                .radius(radius * 0.85)
                .ramp(painted_ramp(burst_seq(ramp), ramp))
                .play(Play::Life)
                .life(14.0 * F)
                .erode(0.6, 0.9)
                .owner(o)
                .emit();
            fx.ring(g, radius * 0.4, radius, 9.0 * F, strip::SHOCK_FRONT, ramp, o);
            fx.smoke(g + Vec3::Y * 0.2, 2, (radius * 0.4).min(1.2), Ramp::Dust, o);
            fx.decal(Decal::CrackStarB, g, radius * 0.7, ramp, 1.5, o);
        }
        T::Line { length, width } => {
            let d = dir.normalize_or(Vec3::NEG_Z);
            let style = RibbonStyle {
                taper: 0.6,
                max_age: 0.16,
                ..RibbonStyle::new(strip::BEAM_BODY, ramp, width.max(0.6), 40.0)
            };
            flight(fx, g + Vec3::Y * 0.5, d * length / (4.0 * F), 0.0, style, 4.0 * F, o);
            let n = (length / 2.5).ceil().clamp(1.0, 8.0) as u32;
            for k in 0..n {
                let p = g + d * length * ((k as f32 + 0.5) / n as f32);
                fx.smoke(p + Vec3::Y * 0.2, 1, (width * 0.4).clamp(0.3, 0.9), Ramp::Dust, o);
            }
            fx.sparks(g + d * length + Vec3::Y * 0.4, -d, 5, 6.0, ramp, o);
        }
        T::Cone { range, angle_deg } => {
            let mut s = Smear::new(g + Vec3::Y * 0.5, dir, range, ramp, o);
            s.width = range * 0.45;
            s.sweep = angle_deg.to_radians().min(TAU * 0.95);
            s.strip = strip::MELEE_HEAVY;
            s.life = 10.0 * F;
            fx.smear(s);
            fx.smoke(g + dir * range * 0.5 + Vec3::Y * 0.2, 2, 0.7, Ramp::Dust, o);
        }
        T::Ring { inner, outer } => {
            fx.dust_wall(g, inner.max(outer * 0.6), outer, 0.5, 12.0 * F, Ramp::Dust, o);
            for _ in 0..6 {
                let d = fx.rand_dir();
                let p = g + d * (inner + outer) * 0.5 + Vec3::Y * 0.3;
                fx.sparks(p, Vec3::ZERO, 2, 5.0, ramp, o);
            }
        }
    }
}

// ───────────────────────────── zones ─────────────────────────────

/// What a zone looks like (its painted mode in `zone.wesl` plus its ambience here).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ZoneLook {
    Well,
    Field,
    Pool,
    Puddle,
    Trail,
    Ground,
    Firestorm,
    EntropyBloom,
    Verdict,
    BindingHex,
    StillField,
    Decoy,
    Geysers,
    Mortar,
}

impl ZoneLook {
    /// The shader mode.
    pub fn mode(self) -> f32 {
        self as u8 as f32
    }

    /// Set pieces carry more presence than a generic player zone.
    pub fn set_piece(self) -> bool {
        matches!(
            self,
            ZoneLook::Firestorm
                | ZoneLook::EntropyBloom
                | ZoneLook::Verdict
                | ZoneLook::BindingHex
                | ZoneLook::StillField
                | ZoneLook::Decoy
                | ZoneLook::Geysers
        )
    }
}

/// The beat when a zone opens.
pub fn zone_open(fx: &mut Fx, look: ZoneLook, at: Vec3, radius: f32, ramp: Ramp, owner: Owner, inside: &[Vec3]) {
    let g = ground(at);
    match look {
        ZoneLook::Verdict => {
            fx.bolt(g + Vec3::Y * 10.0, g + Vec3::Y * 0.2, Ramp::Storm, 1.3, 10.0 * F, owner);
            fx.sprite(seq::STAR4, g + Vec3::Y * 0.5)
                .radius(1.6)
                .ramp(Ramp::Storm)
                .play(Play::Life)
                .life(8.0 * F)
                .ink_backed()
                .owner(owner)
                .emit();
            fx.smoke(g + Vec3::Y * 0.4, 6, radius * 0.3, Ramp::Mono, owner);
            fx.light(g + Vec3::Y * 2.0, Ramp::Storm.light(), 300_000.0, 12.0, 0.4, owner);
        }
        ZoneLook::BindingHex => {
            fx.ring(g, radius * 1.25, radius, 10.0 * F, strip::HEX_BAND, Ramp::ZoneGold, owner);
            for p in inside.iter().take(12) {
                for k in 0..3 {
                    let off = turn(Vec3::X, k as f32 * TAU / 3.0) * 0.35;
                    fx.sprite(seq::FLAME_LICKS, ground(*p) + off)
                        .size(1.4)
                        .ramp(Ramp::Void)
                        .value(value::INK)
                        .delay(k as f32 * 0.03)
                        .life(1.2)
                        .scale(Curve::new(0.3, 1.0, 0.8, 0.15))
                        .erode(0.7, 1.0)
                        .pull(0.2)
                        .owner(owner)
                        .emit();
                }
                fx.sprite(Glyph::RootChain.seq(), *p + Vec3::Y * 0.6)
                    .size(0.9)
                    .ramp(Ramp::Plague)
                    .life(1.0)
                    .erode(0.7, 1.0)
                    .layer(Layer::Front)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::StillField => {
            fx.ring(g, radius * 1.2, radius, 12.0 * F, strip::TICK_RING, Ramp::Time, owner);
        }
        ZoneLook::Geysers => {
            // The slam: the ground cracks and five geysers erupt.
            fx.decal(Decal::CrackStarA, g, radius, Ramp::Flame, 3.0, owner);
            fx.tongues(g, 8, radius * 0.8, 2.0, 0.35, owner);
            fx.light(g + Vec3::Y, Ramp::Flame.light(), 150_000.0, 7.0, 0.4, owner);
        }
        ZoneLook::Decoy => {
            fx.sprite(seq::RADIANT_CROSS_FLARE, g + Vec3::Y * 1.0)
                .radius(1.0)
                .ramp(Ramp::ZoneGold)
                .ink_backed()
                .owner(owner)
                .emit();
            fx.smoke(g + Vec3::Y * 0.2, 3, 0.5, Ramp::Dust, owner);
        }
        ZoneLook::Firestorm => {
            fx.tongues(g, 12, radius * 0.95, 1.1, 0.45, owner);
        }
        ZoneLook::Mortar | ZoneLook::Ground => {
            fx.tongues(g, 6, radius * 0.8, 1.0, 0.45, owner);
        }
        ZoneLook::EntropyBloom => {
            fx.sprite(seq::PETAL_INWARD_STAR, g + Vec3::Y * 0.5)
                .radius(radius * 0.4)
                .ramp(ramp)
                .value(value::INK)
                .play(Play::Life)
                .life(8.0 * F)
                .owner(owner)
                .emit();
        }
        _ => {}
    }
}

/// Per-frame ambience of a live zone: rim tongues, strikes from a storm eye, geysers, bubbles,
/// motes. `k` is a per-zone random stream in 0..1 draws, `dt` the frame time, `age` the zone's
/// age, `seed` a stable per-zone value, `inside` enemy body centres inside the zone.
#[allow(clippy::too_many_arguments)]
pub fn zone_tick(
    fx: &mut Fx,
    look: ZoneLook,
    element: Ramp,
    at: Vec3,
    radius: f32,
    owner: Owner,
    dt: f32,
    age: f32,
    seed: f32,
    strike: &mut f32,
    inside: &[Vec3],
) {
    let g = ground(at);
    let every = |fx: &mut Fx, rate: f32| fx.rand() < rate * dt;
    let rim_point = |fx: &mut Fx, k: f32| {
        let d = fx.rand_dir();
        g + d * radius * fx.range(k, 1.0)
    };
    let lean = |fx: &Fx, p: Vec3| {
        // Tongues lean with the swirl: the tangent's screen-right component.
        let r = (p - g).with_y(0.0);
        let tangent = Vec3::new(-r.z, 0.0, r.x).normalize_or_zero();
        -tangent.dot(fx.store.cam.right) * 0.35
    };
    *strike -= dt;
    match look {
        ZoneLook::Firestorm => {
            // A dense rim of low flame tongues leaning with the swirl.
            let n = (radius * 14.0 * dt + fx.rand()) as u32;
            for _ in 0..n {
                let p = rim_point(fx, 0.86);
                let rot = lean(fx, p);
                let s = [seq::FLAME_NARROW, seq::FLAME_MEDIUM][(fx.rand() * 2.0) as usize % 2];
                let h = fx.range(0.7, 1.1);
                fx.sprite(s, p)
                    .size(h)
                    .rot(rot)
                    .ramp(Ramp::Flame)
                    .life(0.42)
                    .scale(Curve::new(0.3, 1.0, 0.6, 0.2))
                    .erode(0.6, 1.0)
                    .pull(0.25)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            if *strike <= 0.0 {
                *strike = 0.3;
                let target = pick(fx, inside, g, radius * 0.8);
                fx.bolt(g + Vec3::Y * 3.2, target + Vec3::Y * 0.4, Ramp::Storm, 0.7, 6.0 * F, owner);
                fx.sprite(seq::STAR4.nth(2), target + Vec3::Y * 0.3)
                    .radius(0.6)
                    .ramp(Ramp::Storm)
                    .life(4.0 * F)
                    .ink_backed()
                    .owner(owner)
                    .emit();
                fx.light(target + Vec3::Y, Ramp::Storm.light(), 50_000.0, 5.0, 0.12, owner);
            }
            if every(fx, 12.0) {
                let p = rim_point(fx, 0.2);
                fx.embers(p, 1, 0.2, owner);
            }
        }
        ZoneLook::Verdict => {
            if *strike <= 0.0 {
                *strike = 0.35;
                let target = pick(fx, inside, g, radius * 0.85);
                fx.bolt(g + Vec3::Y * 4.5, target + Vec3::Y * 0.4, Ramp::Storm, 0.8, 6.0 * F, owner);
                fx.sprite(seq::STAR4.nth(2), target + Vec3::Y * 0.3)
                    .radius(0.7)
                    .ramp(Ramp::Storm)
                    .life(4.0 * F)
                    .ink_backed()
                    .owner(owner)
                    .emit();
                let v = (fx.rand() * 4.0) as u16;
                let rot = fx.rand() * TAU;
                fx.decal_seq(seq::STORM_LICHTENBERG.nth(v), target, 0.9, rot, Ramp::Storm, 1.0, owner);
            }
            if every(fx, 5.0) {
                let p = rim_point(fx, 0.8);
                fx.smoke(p + Vec3::Y * 0.3, 1, 0.8, Ramp::Mono, owner);
            }
        }
        ZoneLook::Geysers => {
            // Five geysers at stable spots: tall tongues pumping for the field's life.
            for k in 0..5 {
                let a = seed * TAU + k as f32 * TAU / 5.0;
                let rr = radius * (0.35 + 0.45 * ((seed * 7.0 + k as f32 * 0.37).fract()));
                let p = g + Vec3::new(a.cos(), 0.0, a.sin()) * rr;
                if every(fx, 12.0) {
                    let h = fx.range(1.6, 2.4) * if age < 0.3 { 1.3 } else { 1.0 };
                    fx.sprite(seq::FLAME_NARROW, p)
                        .size(h)
                        .ramp(Ramp::Flame)
                        .gain(1.2)
                        .life(0.45)
                        .scale(Curve::new(0.4, 1.0, 0.7, 0.2))
                        .erode(0.6, 1.0)
                        .pull(0.3)
                        .owner(owner)
                        .emit();
                }
                if every(fx, 3.0) {
                    fx.embers(p + Vec3::Y * 0.5, 1, 0.1, owner);
                }
            }
        }
        ZoneLook::Mortar | ZoneLook::Ground => {
            if every(fx, 4.0 * radius) {
                let p = rim_point(fx, 0.0);
                let h = fx.range(0.5, 0.9);
                fx.sprite(seq::FLAME_MEDIUM, p)
                    .size(h)
                    .ramp(element)
                    .life(0.45)
                    .scale(Curve::new(0.3, 1.0, 0.5, 0.2))
                    .erode(0.6, 1.0)
                    .pull(0.25)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            if every(fx, 4.0) {
                let p = rim_point(fx, 0.0);
                fx.embers(p, 1, 0.1, owner);
            }
        }
        ZoneLook::Decoy => {
            // A shimmering gold clone: stacked gold tongues in a figure's height, and the taunt
            // pulse every second.
            if every(fx, 14.0) {
                let off = fx.rand_dir() * 0.2;
                let h = fx.range(1.6, 2.1);
                fx.sprite(seq::FLAME_NARROW, g + off)
                    .size(h)
                    .ramp(Ramp::ZoneGold)
                    .gain(1.1)
                    .life(0.3)
                    .scale(Curve::new(0.8, 1.0, 0.8, 0.5))
                    .erode(0.5, 1.0)
                    .pull(0.3)
                    .owner(owner)
                    .emit();
            }
            if *strike <= 0.0 {
                *strike = 1.0;
                fx.ring(g, 0.4, 2.6, 0.7, strip::ACCENT_RING, Ramp::ZoneGold, owner);
            }
        }
        ZoneLook::BindingHex => {
            if every(fx, 5.0) {
                let p = rim_point(fx, 0.85);
                fx.sprite(seq::FLAME_LICKS, p)
                    .size(0.8)
                    .ramp(Ramp::Void)
                    .value(value::INK)
                    .life(0.5)
                    .erode(0.6, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            if every(fx, 3.0) {
                let p = rim_point(fx, 0.2);
                fx.sprite(seq::GLINT.nth(2), p + Vec3::Y * 0.4)
                    .size(0.3)
                    .vel(Vec3::Y * 0.8)
                    .ramp(Ramp::Plague)
                    .life(0.6)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::StillField => {
            if every(fx, 4.0) {
                let p = rim_point(fx, 0.1);
                fx.sprite(seq::GLINT.nth(3), p + Vec3::Y * 0.8)
                    .size(0.3)
                    .vel(Vec3::Y * 0.15)
                    .ramp(Ramp::Time)
                    .life(1.2)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::EntropyBloom => {
            if every(fx, 5.0) {
                let p = rim_point(fx, 0.1);
                let drift = fx.rand_dir() * 0.3 + Vec3::Y * 0.1;
                fx.sprite(Mote::Spore.seq(), p + Vec3::Y * 0.4)
                    .size(0.26)
                    .vel(drift)
                    .ramp(Ramp::Plague)
                    .life(1.4)
                    .erode(0.7, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::Well => {
            if every(fx, 8.0) {
                let d = fx.rand_dir();
                fx.sprite(Mote::Hex.seq(), g + d * radius * 0.95 + Vec3::Y * 0.3)
                    .size(0.22)
                    .ramp(element)
                    .path(g + Vec3::Y * 0.2, None, 0.2)
                    .life(0.8)
                    .spin(6.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::Pool | ZoneLook::Puddle => {
            if every(fx, 1.2 * radius) {
                let p = rim_point(fx, 0.0);
                fx.sprite(seq::PLAGUE_BUBBLE, p)
                    .size(0.5)
                    .ramp(element)
                    .life(0.55)
                    .play(Play::Life)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::Trail => {
            if element == Ramp::Flame && every(fx, 3.0) {
                let p = rim_point(fx, 0.0);
                fx.sprite(seq::FLAME_LICKS, p)
                    .size(0.6)
                    .ramp(Ramp::Flame)
                    .life(0.4)
                    .erode(0.6, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        ZoneLook::Field => match element {
            Ramp::Flame => {
                if every(fx, 3.0 * radius) {
                    let p = rim_point(fx, 0.0);
                    let h = fx.range(0.5, 0.9);
                    fx.sprite(seq::FLAME_MEDIUM, p)
                        .size(h)
                        .ramp(Ramp::Flame)
                        .life(0.45)
                        .scale(Curve::new(0.3, 1.0, 0.5, 0.2))
                        .erode(0.6, 1.0)
                        .class(Class::Secondary)
                        .owner(owner)
                        .emit();
                }
            }
            Ramp::Storm => {
                if every(fx, 5.0) {
                    let a = rim_point(fx, 0.0) + Vec3::Y * 0.1;
                    let b = a + fx.rand_dir() * 1.2;
                    fx.bolt(a, b, Ramp::Storm, 0.35, 4.0 * F, owner);
                }
            }
            Ramp::Plague => {
                if every(fx, 1.5 * radius) {
                    let p = rim_point(fx, 0.0);
                    fx.sprite(seq::PLAGUE_BUBBLE, p)
                        .size(0.5)
                        .ramp(Ramp::Plague)
                        .life(0.55)
                        .play(Play::Life)
                        .class(Class::Secondary)
                        .owner(owner)
                        .emit();
                }
            }
            Ramp::Void => {
                if every(fx, 6.0) {
                    let d = fx.rand_dir();
                    fx.sprite(Mote::Hex.seq(), g + d * radius * 0.9 + Vec3::Y * 0.3)
                        .size(0.2)
                        .ramp(Ramp::Void)
                        .path(g + Vec3::Y * 0.2, None, 0.2)
                        .life(0.9)
                        .spin(5.0)
                        .class(Class::Secondary)
                        .owner(owner)
                        .emit();
                }
            }
            Ramp::Radiant => {
                if every(fx, 5.0) {
                    let p = rim_point(fx, 0.0);
                    fx.sprite(seq::GLINT.nth(0), p + Vec3::Y * 0.3)
                        .size(0.3)
                        .vel(Vec3::Y * 0.7)
                        .ramp(Ramp::Radiant)
                        .life(0.6)
                        .class(Class::Secondary)
                        .owner(owner)
                        .emit();
                }
            }
            _ => {
                if every(fx, 1.5) {
                    let p = rim_point(fx, 0.6);
                    fx.smoke(p + Vec3::Y * 0.1, 1, 0.5, Ramp::Dust, owner);
                }
            }
        },
    }
}

/// A random target inside a zone: a body when there is one, else a point.
fn pick(fx: &mut Fx, inside: &[Vec3], g: Vec3, radius: f32) -> Vec3 {
    if !inside.is_empty() {
        let i = (fx.rand() * inside.len() as f32) as usize % inside.len();
        return ground(inside[i]);
    }
    let d = fx.rand_dir();
    g + d * radius * fx.rand().sqrt()
}

// ───────────────────────────── world pieces ─────────────────────────────

/// A forge barricade rising: a molten seam along its line, sparks, dust.
pub fn barricade_rise(fx: &mut Fx, at: Vec3, along: Vec3, half: f32, owner: Owner) {
    let g = ground(at);
    let n = (half / 0.8).ceil().max(1.0) as i32;
    for k in -n..=n {
        let p = g + along * (k as f32 / n as f32) * half;
        let rot = along.x.atan2(-along.z) + fx.range(-0.2, 0.2);
        fx.decal_seq(Decal::MoltenGashes.seq(), p, 0.7, rot, Ramp::Flame, 2.0, owner);
    }
    for k in [-0.7, 0.0, 0.7] {
        let p = g + along * half * k + Vec3::Y * 0.3;
        fx.sprite(seq::SPARKFX_SHOWER, p).size(1.8).ramp(Ramp::Kinetic).owner(owner).emit();
        fx.smoke(p, 1, 0.5, Ramp::Dust, owner);
    }
    fx.light(g + Vec3::Y, Ramp::Flame.light(), 80_000.0, 5.0, 0.3, owner);
}

/// A forge turret rising in sparks.
pub fn turret_rise(fx: &mut Fx, at: Vec3, owner: Owner) {
    let g = ground(at);
    fx.sprite(seq::SPARKFX_SHOWER, g + Vec3::Y * 0.4).size(2.2).ramp(Ramp::Kinetic).owner(owner).emit();
    fx.smoke(g + Vec3::Y * 0.2, 3, 0.5, Ramp::Dust, owner);
    fx.ring(g, 0.2, 1.2, 12.0 * F, strip::SHOCK_FRONT, Ramp::Kinetic, owner);
}

/// A turret's spark fountain (Sabbath of Sparks).
pub fn turret_fountain(fx: &mut Fx, at: Vec3, owner: Owner) {
    fx.sprite(seq::SPARKFX_SHOWER, ground(at) + Vec3::Y * 0.9).size(1.6).ramp(Ramp::Void).owner(owner).emit();
}

/// The forge's hammer strike (Forged / RecipeDiscovered).
pub fn forge_strike(fx: &mut Fx, at: Vec3, recipe: bool, owner: Owner) {
    let g = ground(at);
    fx.impact_frame(g + Vec3::Y * 1.2, 0.9, 0.5, owner);
    fx.sprite(seq::SPARKFX_SHOWER, g + Vec3::Y * 1.2).size(2.6).ramp(Ramp::Flame).owner(owner).emit();
    fx.embers(g + Vec3::Y * 0.8, 12, 0.4, owner);
    fx.light(g + Vec3::Y * 1.4, Ramp::Flame.light(), 120_000.0, 6.0, 0.25, owner);
    if recipe {
        fx.sprite(seq::RADIANT_SUNBURST, g + Vec3::Y * 0.05)
            .radius(2.2)
            .ground()
            .ramp(Ramp::ZoneGold)
            .life(1.2)
            .alpha_curve(Curve::new(1.0, 0.8, 0.0, 0.5))
            .owner(owner)
            .emit();
        fx.sprite(seq::RADIANT_RAY_FAN, g + Vec3::Y * 2.4).size(3.0).ramp(Ramp::Radiant).owner(owner).emit();
    }
}
