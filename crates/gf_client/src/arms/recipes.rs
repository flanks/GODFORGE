//! Weapon recipes (VFX_STYLE §6-11): muzzle flashes per chassis, charge cues, beams, melee
//! smears, hit punctuation per element and style, layered explosions, chain bolts, enemy shot
//! impacts. Pure functions on [`Fx`]: the live systems (`arms/mod.rs`) and the weapon gallery
//! (`arms/gallery.rs`) call the same code.

use crate::fx::api::{F, Smear, hit_star};
use crate::fx::{Arc, Class, Curve, Decal, Fx, Glyph, Hit, HitKind, Layer, Mote, Owner, Pip, Play, Profile, Ramp};
use crate::fx::{RibbonStyle, Strip, Sweep, seq, strip, value};
use gf_core::damage::DamageType;
use gf_core::weapon::{FireKind, ProjectileStyle};
use gf_engine::prelude::*;
use std::f32::consts::{FRAC_PI_2, PI, TAU};

/// What the arms module knows about one player's weapon: the chassis and its compiled profile
/// (chassis mods plus equipped parts), enough to pick every recipe.
#[derive(Clone, Debug, PartialEq)]
pub struct Look {
    pub key: String,
    pub fire: FireKind,
    pub style: ProjectileStyle,
    pub element: DamageType,
    /// Shots per second as compiled; `base_rate` is the chassis' own (the melee cadence).
    pub rate: f32,
    pub base_rate: f32,
    pub range: f32,
    pub speed: f32,
    pub spread: f32,
    pub projectiles: u8,
    pub knockback: f32,
    pub pierce: u8,
    pub ricochet: bool,
    pub fork: bool,
    pub chain: bool,
    pub homing: bool,
    /// Splash or explode radius (0 = none).
    pub splash: f32,
    pub beam_width: f32,
    pub charge_time: f32,
}

impl Look {
    pub fn ramp(&self) -> Ramp {
        Ramp::of(self.element)
    }

    /// A stand-in for a chassis the content does not know (greybox bots, tests).
    pub fn fallback() -> Look {
        Look {
            key: String::new(),
            fire: FireKind::Auto,
            style: ProjectileStyle::Bolt,
            element: DamageType::Kinetic,
            rate: 3.0,
            base_rate: 3.0,
            range: 12.0,
            speed: 24.0,
            spread: 3.0,
            projectiles: 1,
            knockback: 0.5,
            pierce: 0,
            ricochet: false,
            fork: false,
            chain: false,
            homing: false,
            splash: 0.0,
            beam_width: 0.5,
            charge_time: 0.0,
        }
    }
}

/// A world direction from a sim-plane one.
pub fn d3(d: Vec2) -> Vec3 {
    Vec3::new(d.x, 0.0, -d.y)
}

/// The side of a flat direction (to its right, seen from above).
fn side_of(dir: Vec3) -> Vec3 {
    dir.cross(Vec3::Y).normalize_or(Vec3::X)
}

/// The painted smear strip of an element (VFX_STYLE §7.4).
pub fn smear_strip(ramp: Ramp) -> Strip {
    match ramp {
        Ramp::Flame => strip::FLAME_SMEAR,
        Ramp::Void => strip::VOID_SMEAR,
        Ramp::Storm => strip::STORM_SMEAR,
        _ => strip::MELEE_HEAVY,
    }
}

// ───────────────────────────── small shapes ─────────────────────────────

/// The f0 white core of a flash: a hot 4-point star for 2 frames.
fn core_star(fx: &mut Fx, at: Vec3, r: f32, ramp: Ramp, owner: Owner) {
    let rot = fx.range(-0.3, 0.3);
    fx.sprite(seq::STAR4.nth(0), at)
        .radius(r)
        .ramp(ramp)
        .value(value::HOT)
        .rot(rot)
        .life(2.0 * F)
        .erode(1.0, 0.0)
        .pull(0.6)
        .layer(Layer::Front)
        .owner(owner)
        .emit();
}

/// A directional flash quad (petal fans, spikes, rails) from `at` along `dir`, `len` long.
#[allow(clippy::too_many_arguments)]
fn flash(fx: &mut Fx, s: crate::fx::Seq, at: Vec3, dir: Vec3, len: f32, ramp: Ramp, frames: f32, owner: Owner) {
    let aspect = s.sheet.cell_aspect();
    let roll = fx.range(-0.26, 0.26);
    fx.sprite(s, at)
        .size2(len, len / aspect)
        .toward(dir)
        .rot(roll)
        .ramp(ramp)
        .play(Play::Life)
        .life(frames * F)
        .erode(0.5, 0.8)
        .pull(0.5)
        .layer(Layer::Front)
        .owner(owner)
        .emit();
}

/// A soft puff that hangs where it is born and lifts (trail smoke, exhaust, wisps).
pub fn puff(fx: &mut Fx, at: Vec3, r: f32, ramp: Ramp, life: f32, owner: Owner) {
    let col = (fx.rand() * 8.0) as u16;
    let rot = fx.rand() * TAU;
    let rise = fx.range(0.4, 0.9);
    fx.sprite(seq::SMOKE.in_column(col), at)
        .radius(r)
        .vel(Vec3::Y * rise)
        .drag(2.0)
        .rot(rot)
        .ramp(ramp)
        .play(Play::Life)
        .life(life)
        .scale(Curve::new(0.55, 1.1, 1.3, 0.4))
        .cool(0.45)
        .erode(0.3, 1.0)
        .layer(Layer::Back)
        .class(Class::Smoke)
        .owner(owner)
        .emit();
}

/// A ring of puffs blown outward from a point (the cannon's smoke ring, a recoil puff).
fn puff_ring(fx: &mut Fx, at: Vec3, n: u32, r: f32, speed: f32, ramp: Ramp, owner: Owner) {
    for a in fx.around(n) {
        let d = Vec3::new(a.cos(), 0.15, a.sin());
        let col = (fx.rand() * 8.0) as u16;
        let life = fx.range(0.3, 0.42);
        fx.sprite(seq::SMOKE.in_column(col), at + d * 0.15)
            .radius(r)
            .vel(d * speed + Vec3::Y * 0.5)
            .drag(4.0)
            .ramp(ramp)
            .play(Play::Life)
            .life(life)
            .scale(Curve::new(0.5, 1.0, 1.2, 0.4))
            .cool(0.45)
            .erode(0.3, 1.0)
            .layer(Layer::Back)
            .class(Class::Smoke)
            .owner(owner)
            .emit();
    }
}

/// Ink drag lines: short dark streaks trailing a body knocked along `dir`.
fn drag_lines(fx: &mut Fx, at: Vec3, dir: Vec3, n: u32, body: f32, owner: Owner) {
    let side = side_of(dir);
    for i in 0..n {
        let off = side * ((i as f32 - (n as f32 - 1.0) * 0.5) * (0.22 + body * 0.2)) + Vec3::Y * fx.range(-0.2, 0.3);
        let len = fx.range(0.7, 1.2) + body * 0.4;
        fx.sprite(seq::MUZZLE_SPIKE.nth(1), at - dir * (body * 0.6 + len * 0.3) + off)
            .size2(len, len * 0.28)
            .toward(dir)
            .ramp(Ramp::Mono)
            .value(value::INK)
            .life(8.0 * F)
            .erode(0.3, 1.0)
            .pull(0.4)
            .layer(Layer::Back)
            .class(Class::Secondary)
            .owner(owner)
            .emit();
    }
}

/// The element's signature secondary on a hit (VFX_STYLE §4): embers, a micro-bolt, hex motes
/// spiralling in, droplets, glints, brass chips.
pub fn element_secondary(fx: &mut Fx, at: Vec3, dir: Vec3, ramp: Ramp, n: u32, owner: Owner) {
    match ramp {
        Ramp::Flame => {
            fx.embers(at, n.max(1), 0.3, owner);
            let h = fx.range(0.45, 0.7);
            fx.sprite(seq::FLAME_LICKS, at - Vec3::Y * 0.2)
                .size(h)
                .ramp(Ramp::Flame)
                .life(9.0 * F)
                .scale(Curve::new(0.4, 1.0, 0.7, 0.3))
                .erode(0.5, 1.0)
                .pull(0.5)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        Ramp::Storm => {
            for _ in 0..n.clamp(1, 2) {
                let d = fx.rand_dir() + Vec3::Y * fx.range(-0.3, 0.5);
                let len = fx.range(0.5, 0.95);
                fx.bolt(at, at + d.normalize_or(Vec3::X) * len, Ramp::Storm, 0.28, 4.0 * F, owner);
            }
        }
        Ramp::Void => {
            for _ in 0..(n + 1) {
                let d = fx.rand_dir() + Vec3::Y * fx.range(-0.2, 0.6);
                let from = at + d.normalize_or(Vec3::X) * fx.range(0.6, 0.9);
                let spin = fx.range(-9.0, 9.0);
                fx.sprite(Mote::Hex.seq(), from)
                    .size(0.16)
                    .ramp(Ramp::Void)
                    .gain(1.3)
                    .path(at, None, 0.15)
                    .spin(spin)
                    .life(0.22)
                    .erode(0.9, 0.6)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        Ramp::Plague => {
            for _ in 0..(n + 1) {
                let d = fx.rand_dir();
                let v = d * fx.range(1.5, 3.0) + dir * 1.5 + Vec3::Y * fx.range(2.0, 3.5);
                let variant = (fx.rand() * 4.0) as u16;
                fx.sprite(seq::TEARDROP.nth(variant), at)
                    .size(0.22)
                    .ramp(Ramp::Plague)
                    .vel(v)
                    .gravity(14.0)
                    .streak(0.07)
                    .life(0.45)
                    .erode(0.6, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        Ramp::Radiant => {
            for i in 0..n.max(1) {
                let off = fx.rand_dir() * 0.3;
                fx.sprite(seq::GLINT.nth(i as u16 % 4), at + off)
                    .size(0.26)
                    .ramp(Ramp::Radiant)
                    .gain(1.3)
                    .vel(Vec3::Y * 0.9)
                    .life(0.3)
                    .erode(0.7, 1.0)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        _ => {}
    }
}

// ───────────────────────────── muzzle flashes (§7-8) ─────────────────────────────

/// One shot leaving a weapon.
#[derive(Clone, Copy, Debug)]
pub struct Shot<'a> {
    pub look: &'a Look,
    /// The muzzle socket (or the greybox gun's tip).
    pub at: Vec3,
    /// The hero's feet.
    pub feet: Vec3,
    /// Aim (flat, unit).
    pub dir: Vec3,
    pub owner: Owner,
    /// Charge at release (0..1; 0 for non-charge weapons).
    pub charge: f32,
    /// Shots fired so far (alternation, ramps).
    pub n: u32,
    /// Seconds since the previous shot (the Pendulum's ramp).
    pub since: f32,
}

/// The muzzle flash of a chassis (VFX_STYLE §8): the family shape, rotated per shot, 2-4 frames,
/// plus the chassis' extras. Charge weapons scale it 0.6× - 1.4× with the charge.
pub fn muzzle(fx: &mut Fx, s: &Shot) {
    let Shot { look, at, feet, dir, owner, charge, n, since } = *s;
    let ramp = look.ramp();
    let side = side_of(dir);
    let k = if look.fire == FireKind::Charge { 0.6 + 0.8 * charge.clamp(0.0, 1.0) } else { 1.0 };
    let alt = if n.is_multiple_of(2) { 1.0 } else { -1.0 };
    let light = |fx: &mut Fx, power: f32| fx.light(at, ramp.light(), 25_000.0 * power, 3.5, 0.08, owner);
    match look.key.as_str() {
        "colossus_cannon" => {
            core_star(fx, at, 0.3, ramp, owner);
            flash(fx, seq::PETAL_FORWARD_FAN, at, dir, 1.35, ramp, 4.0, owner);
            puff_ring(fx, at + dir * 0.35, 5, 0.34, 2.6, Ramp::Dust, owner);
            puff(fx, feet + Vec3::Y * 0.15 - dir * 0.3, 0.45, Ramp::Dust, 0.45, owner);
            light(fx, 3.0);
        }
        "thundercoil_launcher" => {
            core_star(fx, at, 0.25, ramp, owner);
            flash(fx, seq::PETAL_CROSS, at, dir, 0.9, ramp, 4.0, owner);
            for i in 0..2 {
                let o = side * (if i == 0 { 0.12 } else { -0.12 });
                fx.bolt(at - dir * 0.7 + o, at + o * 0.5, Ramp::Storm, 0.22, 6.0 * F, owner);
            }
            light(fx, 1.5);
        }
        "serpent_smg" => {
            let s2 = seq::MUZZLE_FLICKER3.nth((n % 4) as u16);
            flash(fx, s2, at, dir, 0.5, ramp, 3.0, owner);
            // A brass sliver casing kicked out of the ejector.
            let v = side * fx.range(2.0, 3.0) + Vec3::Y * fx.range(1.5, 2.5) - dir * 0.6;
            let spin = fx.range(-20.0, 20.0);
            fx.sprite(seq::SHARD.nth(2), at - dir * 0.35)
                .size(0.1)
                .vel(v)
                .gravity(16.0)
                .spin(spin)
                .bounce(0.3)
                .ramp(Ramp::GodworksGold)
                .life(0.45)
                .erode(0.8, 1.0)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
            light(fx, 0.5);
        }
        "godsbane_rifle" | "dawnbreaker_carbine" => {
            core_star(fx, at, 0.22, ramp, owner);
            if look.key == "dawnbreaker_carbine" {
                flash(fx, seq::RADIANT_CROSS_FLARE, at, dir, 0.8, ramp, 4.0, owner);
                fx.sprite(seq::RADIANT_HALO_ARCS, at + Vec3::Y * 0.25 - dir * 0.2)
                    .radius(0.22)
                    .ramp(Ramp::Radiant)
                    .play(Play::Life)
                    .life(8.0 * F)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            } else {
                flash(fx, seq::MUZZLE_SPIKE, at, dir, 1.4, ramp, 4.0, owner);
                for sgn in [1.0, -1.0] {
                    let d = (dir + side * 0.9 * sgn).normalize();
                    flash(fx, seq::MUZZLE_SPIKE, at, d, 0.45, ramp, 3.0, owner);
                }
                // The pressure wave: two thin cone lines.
                for sgn in [1.0, -1.0] {
                    let d = (dir + side * 0.35 * sgn).normalize();
                    fx.slash(at + d * 0.9, d, 1.1, ramp, owner);
                }
                puff(fx, at + dir * 0.3, 0.22, Ramp::Dust, 0.5, owner);
            }
            light(fx, 1.5);
        }
        "wraith_bow" | "echoing_greatbow" => {
            // No flash: the string snaps across the limbs (three echoes on the greatbow).
            let snaps = if look.key == "echoing_greatbow" { 3 } else { 1 };
            for i in 0..snaps {
                string_snap(fx, at - dir * 0.15, dir, ramp, k, i as f32 * 2.0 * F, owner);
            }
            let wisps = if look.key == "echoing_greatbow" { 3 } else { 2 };
            for i in 0..wisps {
                let fan = (i as f32 - (wisps as f32 - 1.0) * 0.5) * 0.6;
                let v = (side * fan + dir * 0.4 + Vec3::Y * 0.5) * 1.6;
                let wisp_ramp = if look.element == DamageType::Void { Ramp::Void } else { Ramp::Kinetic };
                fx.sprite(Mote::Hex.seq(), at)
                    .size(0.2)
                    .ramp(wisp_ramp)
                    .vel(v)
                    .drag(2.5)
                    .life(0.45)
                    .erode(0.5, 1.0)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            if charge > 0.95 {
                core_star(fx, at, 0.35, ramp, owner);
            }
            light(fx, k);
        }
        "sunspike_shotgun" => {
            core_star(fx, at, 0.35, ramp, owner);
            flash(fx, seq::PETAL_SUNBURST, at - dir * 0.2, dir, 2.6, ramp, 4.0, owner);
            // Straight rays along the pellet lines.
            let half = look.spread.to_radians() * 0.5;
            let rays = look.projectiles.clamp(3, 9);
            for i in 0..rays {
                let a = -half + 2.0 * half * i as f32 / (rays - 1) as f32;
                let d = Quat::from_rotation_y(a) * dir;
                let len = fx.range(1.4, 2.2);
                fx.sprite(seq::MUZZLE_SPIKE.nth(1), at)
                    .size2(len, len * 0.22)
                    .toward(d)
                    .ramp(Ramp::Radiant)
                    .value(value::HOT)
                    .life(3.0 * F)
                    .erode(0.3, 1.0)
                    .pull(0.5)
                    .layer(Layer::Front)
                    .owner(owner)
                    .emit();
            }
            light(fx, 3.0);
        }
        "longstrider_rail" => {
            core_star(fx, at, 0.3 * k, ramp, owner);
            flash(fx, seq::MUZZLE_RAIL, at, dir, 2.0 * k, ramp, 4.0, owner);
            flash(fx, seq::MUZZLE_SPIKE, at, dir, 1.3 * k, Ramp::Radiant, 3.0, owner);
            // Capacitor rings go dark in sequence along the barrel.
            for i in 0..3 {
                fx.sprite(seq::BODY_CHARGE_RING.nth(3), at - dir * (0.25 + i as f32 * 0.28))
                    .size(0.42)
                    .ramp(Ramp::Storm)
                    .life((6.0 + i as f32 * 4.0) * F)
                    .alpha_curve(Curve::new(1.0, 1.0, 0.0, 0.5))
                    .erode(0.5, 1.0)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            puff(fx, feet + Vec3::Y * 0.15 - dir * 0.3, 0.4, Ramp::Dust, 0.45, owner);
            light(fx, 2.0 * k);
        }
        "coinshooter" => {
            let o = side * 0.22 * alt;
            flash(fx, seq::PETAL_CROSS, at + o, dir, 0.6, Ramp::Radiant, 3.0, owner);
            if n.is_multiple_of(3) {
                // A flipped coin glint spins off the magazine.
                let v = Vec3::Y * 3.2 + side * alt * 0.8;
                fx.sprite(seq::COIN, at + o - dir * 0.2)
                    .size(0.22)
                    .vel(v)
                    .gravity(12.0)
                    .ramp(Ramp::Radiant)
                    .play(Play::Fps(30.0))
                    .life(0.45)
                    .erode(0.8, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            light(fx, 0.6);
        }
        "pendulum_repeater" => {
            // Petals grow 2 → 4 with the ramp; at the top the flywheel throws sparks.
            let rate = 1.0 / since.max(0.05);
            let ramp01 = ((rate / look.base_rate.max(0.1) - 1.0) / 1.8).clamp(0.0, 1.0);
            let s2 = if ramp01 > 0.5 { seq::PETAL_CROSS } else { seq::MUZZLE_FLICKER3 };
            flash(fx, s2, at, dir, 0.55 + 0.4 * ramp01, ramp, 3.0, owner);
            if ramp01 > 0.85 {
                fx.sparks(at - dir * 0.4 + Vec3::Y * 0.1, -dir, 2, 3.5, Ramp::GodworksGold, owner);
            }
            light(fx, 0.5 + ramp01);
        }
        "gravemaw_mortar" => {
            let up = (dir + Vec3::Y * 1.2).normalize();
            core_star(fx, at, 0.35, ramp, owner);
            flash(fx, seq::PETAL_FORWARD_FAN, at, up, 1.3, ramp, 4.0, owner);
            fx.sparks(at, up, 4, 5.0, Ramp::GodworksEmber, owner);
            for i in 0..4 {
                let lift = Vec3::Y * (0.2 + i as f32 * 0.35);
                puff(fx, at + lift, 0.3 + i as f32 * 0.06, Ramp::Mono, 0.55 + i as f32 * 0.08, owner);
            }
            light(fx, 2.5);
        }
        "stormlash" => {
            // A whip-crack: a thin S-curve smear off the coil tip, then the bolt.
            let mut sm = Smear::new(at - dir * 0.4 - side * alt * 0.9, dir + side * alt * 0.6, 2.0, ramp, owner);
            sm.strip = strip::WHIP;
            sm.width = 0.35;
            sm.sweep = 1.1 * alt;
            sm.life = 6.0 * F;
            sm.gain = 1.3;
            fx.smear(sm);
            core_star(fx, at + dir * 0.4, 0.3, ramp, owner);
            light(fx, 1.0);
        }
        "tidecaller_harpoon" => {
            for _ in 0..5 {
                let v = (dir * 3.5 + fx.rand_dir() * 1.2 + Vec3::Y * fx.range(0.8, 2.0)) * k;
                let variant = (fx.rand() * 4.0) as u16;
                fx.sprite(seq::TEARDROP.nth(variant), at)
                    .size(0.18)
                    .ramp(Ramp::Plague)
                    .vel(v)
                    .gravity(12.0)
                    .streak(0.06)
                    .life(0.4)
                    .erode(0.6, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            flash(fx, seq::PETAL_FORWARD_FAN, at, dir, 0.7 * k, ramp, 3.0, owner);
            light(fx, k);
        }
        "orrery_discs" => {
            // A circular spin smear around the launched disc, a planetary ring glint at the wrist.
            let mut a = Arc::new(strip::SPIN_DISC, at + dir * 0.3, 0.55, 0.3, 8.0 * F);
            a.start = fx.rand() * TAU;
            a.sweep = 1.6 * PI * alt;
            a.sweep_anim = Sweep::Swing { lead: 0.35, retract: 0.5 };
            a.profile = Profile::Crescent { peak: 0.8 };
            a.ramp = ramp;
            a.gain = 1.2;
            a.erode = Vec2::new(0.4, 1.0);
            a.segments = 20;
            a.pull = 0.5;
            a.layer = Layer::Front;
            fx.arc(a, owner, Class::Core);
            fx.sprite(Glyph::Hexagram.seq(), at - dir * 0.3)
                .size(0.4)
                .ramp(ramp)
                .life(8.0 * F)
                .erode(0.4, 1.0)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
            light(fx, 0.8);
        }
        "huntmother_javelins" => {
            // The overhand throw: a vertical smear at the hand, a feather-like dust puff.
            let mut sm = Smear::new(at - dir * 0.6 + Vec3::Y * 0.3, dir, 1.3, ramp, owner);
            sm.strip = strip::DASH_DRYBRUSH;
            sm.width = 0.45;
            sm.sweep = 1.6;
            sm.tilt = FRAC_PI_2;
            sm.life = 8.0 * F;
            fx.smear(sm);
            puff(fx, feet + Vec3::Y * 0.2, 0.35, Ramp::Dust, 0.4, owner);
            light(fx, 0.6);
        }
        "chorus_harp" => {
            // A string pluck: three thin parallel lines vibrate, a note pops out.
            for i in 0..3 {
                let o = side * ((i as f32 - 1.0) * 0.14);
                fx.sprite(seq::MUZZLE_RAIL.nth(1), at + o - dir * 0.3)
                    .size2(0.9, 0.3)
                    .toward(dir)
                    .ramp(Ramp::Radiant)
                    .play(Play::Frame(0))
                    .life(6.0 * F)
                    .erode(0.4, 1.0)
                    .pull(0.5)
                    .layer(Layer::Front)
                    .owner(owner)
                    .emit();
            }
            fx.sprite(Pip::Note.seq(), at + Vec3::Y * 0.2)
                .size(0.35)
                .ramp(Ramp::Radiant)
                .vel(Vec3::Y * 1.2 + dir * 0.5)
                .life(0.35)
                .erode(0.6, 1.0)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
            light(fx, 0.6);
        }
        "voidheart_singularity" => {
            // An inward star: the points aim at the core, then flip out.
            fx.sprite(seq::PETAL_INWARD_STAR, at)
                .radius(0.55 * k)
                .ramp(Ramp::Void)
                .play(Play::Life)
                .life(6.0 * F)
                .erode(0.6, 1.0)
                .pull(0.5)
                .ink_backed()
                .layer(Layer::Front)
                .owner(owner)
                .emit();
            for a in fx.around(4) {
                let o = Vec3::new(a.cos(), 0.6 * a.sin(), a.sin()) * 0.35;
                fx.sprite(seq::GLINT.nth(1), at + o)
                    .size(0.2)
                    .ramp(Ramp::Void)
                    .gain(1.3)
                    .delay(a / TAU * 4.0 * F)
                    .life(5.0 * F)
                    .layer(Layer::Front)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
            light(fx, k);
        }
        "epochal_sundial" => {
            // The gnomon sweeps a clock-hand smear through 30 degrees; a pale dial arc.
            let mut sm = Smear::new(at - dir * 0.2, dir, 1.2, Ramp::Time, owner);
            sm.strip = strip::SLASH_THIN;
            sm.width = 0.18;
            sm.sweep = 30f32.to_radians() * alt;
            sm.life = 7.0 * F;
            sm.gain = 1.3;
            fx.smear(sm);
            fx.ring(feet, 0.4, 0.9, 12.0 * F, strip::TICK_RING, Ramp::Time, owner);
            flash(fx, seq::PETAL_CROSS, at, dir, 0.5, ramp, 3.0, owner);
            light(fx, 0.6);
        }
        _ => generic_muzzle(fx, s),
    }
}

/// The family default for any chassis without its own flash.
fn generic_muzzle(fx: &mut Fx, s: &Shot) {
    use ProjectileStyle as S;
    let look = s.look;
    match look.style {
        S::Fist => {}
        S::Arrow => string_snap(fx, s.at, s.dir, look.ramp(), 1.0, 0.0, s.owner),
        style => fx.muzzle(style, look.element, s.at, s.dir, s.owner),
    }
}

/// A bow's string snapping forward across the limbs: a thin vertical smear.
fn string_snap(fx: &mut Fx, at: Vec3, dir: Vec3, ramp: Ramp, k: f32, delay: f32, owner: Owner) {
    // A shallow crescent across the aim, bulging forward (the string snapping straight).
    let r = 0.9 * k.max(0.7);
    let sweep = 1.1;
    let pivot = at - dir * (r * 0.8);
    let mut a = Arc::new(strip::SLASH_THIN, pivot, r, 0.22 * k.max(0.7), 5.0 * F);
    a.basis = Quat::from_rotation_arc(Vec3::NEG_Z, dir) * Quat::from_rotation_z(FRAC_PI_2 * 0.8);
    a.start = -sweep * 0.5;
    a.sweep = sweep;
    a.sweep_anim = Sweep::Swing { lead: 0.25, retract: 0.45 };
    a.profile = Profile::Crescent { peak: 0.5 };
    a.ramp = ramp;
    a.gain = 1.4;
    a.erode = Vec2::new(0.4, 1.0);
    a.segments = 14;
    a.pull = 0.6;
    a.layer = Layer::Front;
    a.age = -delay;
    fx.arc(a, owner, Class::Core);
}

// ───────────────────────────── charge (§7.2) ─────────────────────────────

/// The charge cue for one frame (immediate mode): motes are the caller's; this draws the core in
/// three steps, the broken ring tightening from 1.3 m to 0.35 m, the full-charge glint and the
/// 4 Hz pulse, and the chassis' own gauges.
#[allow(clippy::too_many_arguments)]
pub fn charge_cue(
    fx: &mut Fx,
    look: &Look,
    at: Vec3,
    dir: Vec3,
    charge: f32,
    full_for: Option<f32>,
    t: f32,
    owner: Owner,
) {
    let ramp = look.ramp();
    let c = charge.clamp(0.0, 1.0);
    let full = full_for.is_some();
    let stage = if full { 2 } else { ((c * 3.0) as u16).min(2) };
    let pulse = if full { 1.0 + 0.16 * (t * 4.0 * TAU).sin() } else { 1.0 };
    let core = (0.3 + 0.45 * c) * pulse;
    fx.sprite(seq::BODY_CHARGE_CORE.nth(stage), at)
        .size(core)
        .ramp(ramp)
        .gain(1.0 + 0.5 * c)
        .play(Play::Frame(0))
        .pull(0.6)
        .layer(Layer::Front)
        .owner(owner)
        .now();
    // The ring: 1.3 m → 0.35 m radius, its gap turning.
    let ring_r = 1.3 + (0.35 - 1.3) * c;
    let flash_white = full_for.is_some_and(|f| f < 2.0 * F);
    let ring_stage = if flash_white { 3 } else { stage.min(2) };
    let spin = t * if full { 5.0 } else { 2.0 + 4.0 * c };
    let mut ring = fx
        .sprite(seq::BODY_CHARGE_RING.nth(ring_stage), at)
        .size(ring_r * 2.2 * pulse)
        .ramp(ramp)
        .rot(spin)
        .gain(1.0 + 0.4 * c)
        .play(Play::Frame(0))
        .pull(0.6)
        .layer(Layer::Front)
        .owner(owner);
    if flash_white {
        ring = ring.value(value::HOT);
    }
    ring.now();
    if let Some(f) = full_for
        && f < 3.0 * F
    {
        fx.sprite(seq::STAR4.nth(0), at)
            .radius(0.55)
            .ramp(ramp)
            .value(value::HOT)
            .play(Play::Frame(0))
            .pull(0.7)
            .layer(Layer::Top)
            .owner(owner)
            .now();
    }
    let side = side_of(dir);
    match look.key.as_str() {
        "longstrider_rail" => {
            // Capacitor rings light one by one along the barrel.
            for i in 0..3 {
                let lit = c > (i as f32 + 1.0) / 3.0 - 0.01;
                let mut s = fx
                    .sprite(seq::BODY_CHARGE_RING.nth(if lit { 2 } else { 0 }), at - dir * (0.25 + i as f32 * 0.28))
                    .size(0.4)
                    .ramp(Ramp::Storm)
                    .play(Play::Frame(0))
                    .pull(0.5)
                    .layer(Layer::Front)
                    .owner(owner);
                if !lit {
                    s = s.value(value::DEEP);
                }
                s.now();
            }
        }
        "voidheart_singularity" => {
            // The cage bars: four void glints orbiting the core, tighter as it fills.
            for i in 0..4 {
                let a = t * 3.0 + i as f32 * FRAC_PI_2;
                let r = 0.55 - 0.25 * c;
                let o = side * a.cos() * r + Vec3::Y * a.sin() * r * 0.8;
                fx.sprite(seq::GLINT.nth(1), at + o)
                    .size(0.18 + 0.1 * c)
                    .ramp(Ramp::Void)
                    .gain(1.3)
                    .play(Play::Frame(0))
                    .pull(0.6)
                    .layer(Layer::Front)
                    .owner(owner)
                    .now();
            }
        }
        "wraith_bow" | "echoing_greatbow" | "tidecaller_harpoon" => {
            // The drawn string: a bright line bending back as it fills.
            let pull_back = 0.1 + 0.35 * c;
            for sgn in [1.0, -1.0] {
                let tip = at + side * 0.45 * sgn + dir * 0.1;
                let nock = at - dir * pull_back;
                let d = tip - nock;
                fx.sprite(seq::MUZZLE_RAIL.nth(1), nock)
                    .size2(d.length(), 0.14)
                    .toward(d)
                    .ramp(ramp)
                    .gain(1.2)
                    .play(Play::Frame(0))
                    .pull(0.6)
                    .layer(Layer::Front)
                    .owner(owner)
                    .now();
            }
        }
        _ => {}
    }
}

/// One mote gathering into the charge (VFX_STYLE §7.2): from ~1.2 m out, spiralling in.
pub fn charge_mote(fx: &mut Fx, look: &Look, at: Vec3, owner: Owner) {
    let d = (fx.rand_dir() + Vec3::Y * fx.range(-0.3, 0.8)).normalize_or(Vec3::X);
    let from = at + d * fx.range(0.9, 1.4);
    let s = match look.element {
        DamageType::Void => Mote::Hex.seq(),
        DamageType::Plague => Mote::Spore.seq(),
        DamageType::Flame => Mote::Ember.seq(),
        _ => seq::GLINT.nth(0),
    };
    let spin = fx.range(-8.0, 8.0);
    fx.sprite(s, from)
        .size(0.2)
        .ramp(look.ramp())
        .gain(1.3)
        .path(at, None, fx_height(d))
        .spin(spin)
        .life(0.3)
        .erode(0.95, 0.5)
        .layer(Layer::Front)
        .class(Class::Secondary)
        .owner(owner)
        .emit();
}

fn fx_height(d: Vec3) -> f32 {
    0.25 * d.x.signum()
}

// ───────────────────────────── beams (§7.3) ─────────────────────────────

/// A beam for one frame: `key` identifies it (the player slot), `acc` carries the emitters'
/// accumulated time between frames.
#[allow(clippy::too_many_arguments)]
pub fn beam(
    fx: &mut Fx,
    key: u32,
    look: &Look,
    from: Vec3,
    dir: Vec3,
    len: f32,
    width: f32,
    t: f32,
    dt: f32,
    acc: &mut [f32; 3],
    owner: Owner,
) {
    let ramp = look.ramp();
    let to = from + dir * len;
    let side = side_of(dir);
    let line_key = 0x4100_0000 + key * 4;
    match look.key.as_str() {
        "bellowfire_projector" => {
            // A breath, not a laser: a flame core and a widening cone of rolling tongues.
            let core = RibbonStyle {
                tile: 1.6,
                scroll: 9.0,
                taper: 1.0,
                erode: 0.0,
                fade: 0.12,
                ..RibbonStyle::new(strip::FLAME_TRAIL, Ramp::Flame, width * 0.55, 1e4)
            };
            fx.immediate_line(line_key, from, from + dir * len * 0.8, core, owner);
            let pump = (t * 2.8).fract() < 0.18;
            acc[0] += dt * if pump { 70.0 } else { 38.0 };
            while acc[0] >= 1.0 {
                acc[0] -= 1.0;
                let life = fx.range(0.26, 0.36);
                let lateral = side * fx.range(-1.0, 1.0) * width * 0.75 / life;
                let v = dir * (len / life) * fx.range(0.8, 1.0) + lateral;
                let s = [seq::FLAME_MEDIUM, seq::FLAME_CLUMP, seq::FLAME_CLUMP][(fx.rand() * 3.0) as usize % 3];
                let h = fx.range(0.8, 1.1) * width;
                fx.sprite(s, from + dir * 0.2 - Vec3::Y * 0.3)
                    .size(h)
                    .vel(v)
                    .drag(1.2)
                    .ramp(Ramp::Flame)
                    .gain(if pump { 1.5 } else { 1.1 })
                    .life(life)
                    .scale(Curve::new(0.35, 1.3, 2.1, 0.5))
                    .erode(0.55, 1.0)
                    .pull(0.3)
                    .class(Class::Core)
                    .owner(owner)
                    .emit();
            }
            acc[1] += dt * 12.0;
            while acc[1] >= 1.0 {
                acc[1] -= 1.0;
                // Fire-lit smoke rolling inside the cone, and puffs out of the bellows.
                let s = fx.range(0.3, 0.9) * len;
                let o = side * fx.range(-0.5, 0.5) * width * (0.5 + s / len);
                puff(fx, from + dir * s + o, width * (0.35 + 0.35 * s / len), Ramp::Flame, 0.4, owner);
                if fx.rand() < 0.35 {
                    puff(fx, from - dir * 0.55 + Vec3::Y * 0.2, 0.3, Ramp::Mono, 0.5, owner);
                }
            }
            acc[2] += dt * 10.0;
            while acc[2] >= 1.0 {
                acc[2] -= 1.0;
                fx.embers(to - dir * 0.8, 1, width * 0.8, owner);
            }
            fx.light(to - dir * 1.5 + Vec3::Y * 0.3, Ramp::Flame.light(), 60_000.0, 5.0, 0.05, owner);
        }
        "seraph_lance" => {
            // A hard straight ray: halo arcs slide along it, a cross flares at the prism.
            fx.beam(key, from, to, width, Ramp::Radiant, owner);
            for i in 0..3 {
                let s = ((t * 9.0 + i as f32 * len / 3.0) % len).max(0.3);
                let frame = ((t * 20.0) as u16 + i) % 8;
                fx.sprite(seq::RADIANT_HALO_ARCS.nth(frame), from + dir * s)
                    .radius(width * 1.1)
                    .ramp(Ramp::Radiant)
                    .rot(FRAC_PI_2 * (i % 2) as f32)
                    .play(Play::Frame(0))
                    .pull(0.5)
                    .layer(Layer::Front)
                    .owner(owner)
                    .now();
            }
            let snap = ((t * 6.0) as u32 % 2) as f32 * FRAC_PI_2 * 0.5;
            fx.sprite(seq::RADIANT_CROSS_FLARE.nth(((t * 30.0) as u16) % 4), from)
                .radius(0.55)
                .ramp(Ramp::Radiant)
                .rot(snap)
                .play(Play::Frame(0))
                .pull(0.6)
                .layer(Layer::Front)
                .owner(owner)
                .now();
            acc[0] += dt * 4.0;
            while acc[0] >= 1.0 {
                acc[0] -= 1.0;
                let rot = ((t * 6.0) as u32 % 8) as f32 * PI / 8.0;
                fx.decal_seq(Glyph::Hexagram.seq(), to, 0.8, rot, Ramp::Radiant, 0.6, owner);
            }
            fx.light(to + Vec3::Y * 0.3, Ramp::Radiant.light(), 50_000.0, 4.0, 0.05, owner);
        }
        "plaguebloom_sprayer" => {
            // A fog cone of globules: a sickly mist band marks the true width.
            let mist = RibbonStyle {
                tile: 2.0,
                scroll: 4.0,
                taper: 0.25,
                erode: 0.35,
                fade: 0.15,
                alpha: 0.22,
                ..RibbonStyle::new(strip::DRIP_TRAIL, Ramp::Plague, width * 1.2, 1e4)
            };
            fx.immediate_line(line_key, from, to, mist, owner);
            fx.sprite(seq::PETAL_FORWARD_FAN.nth(((t * 20.0) as u16) % 4), from)
                .size2(0.9, 0.9)
                .toward(dir)
                .ramp(Ramp::Plague)
                .play(Play::Frame(0))
                .pull(0.5)
                .layer(Layer::Front)
                .owner(owner)
                .now();
            acc[0] += dt * 42.0;
            while acc[0] >= 1.0 {
                acc[0] -= 1.0;
                let life = fx.range(0.35, 0.5);
                let v = dir * (len / life) * fx.range(0.55, 1.0) + side * fx.range(-1.0, 1.0) * width * 1.8;
                let sz = fx.range(0.35, 0.7);
                fx.sprite(seq::PLAGUE_BUBBLE, from + dir * 0.3)
                    .size(sz)
                    .vel(v)
                    .drag(1.5)
                    .ramp(Ramp::Plague)
                    .play(Play::Life)
                    .life(life)
                    .scale(Curve::new(0.5, 1.0, 1.3, 0.5))
                    .erode(0.7, 1.0)
                    .owner(owner)
                    .emit();
            }
            acc[1] += dt * 6.0;
            while acc[1] >= 1.0 {
                acc[1] -= 1.0;
                let at = from + dir * fx.range(1.0, len) + side * fx.range(-0.5, 0.5) * width;
                let drift = side * fx.range(-0.6, 0.6) + Vec3::Y * 0.3;
                fx.sprite(seq::PLAGUE_SPORES, at)
                    .size(0.45)
                    .vel(drift)
                    .ramp(Ramp::Plague)
                    .life(0.7)
                    .erode(0.5, 1.0)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        _ => {
            // The generic four-part beam (core, body, contact star) plus the element's edge licks.
            fx.beam(key, from, to, width, ramp, owner);
            acc[0] += dt * 14.0;
            while acc[0] >= 1.0 {
                acc[0] -= 1.0;
                let s = fx.range(0.4, len);
                let edge = if fx.rand() < 0.5 { 1.0 } else { -1.0 };
                let at = from + dir * s + side * edge * width * 0.45;
                element_secondary(fx, at, side * edge, ramp, 1, owner);
            }
        }
    }
}

// ───────────────────────────── melee (§7.4) ─────────────────────────────

/// One melee strike.
#[derive(Clone, Copy, Debug)]
pub struct Strike<'a> {
    pub look: &'a Look,
    pub feet: Vec3,
    pub dir: Vec3,
    /// Strikes so far (0-based): alternation and the finisher every third.
    pub n: u32,
    pub owner: Owner,
    /// The striking fist or the hammer face, when the model has one.
    pub fist: Option<Vec3>,
}

/// A melee strike (VFX_STYLE §7.4): a knuckle glint, a crescent smear in the fist's plane that
/// alternates left and right, and every third strike a finisher (thicker, full reach, speed
/// streaks, a shock front at the reach and a dust puff). The Titanfall Hammer swings overhead.
pub fn strike(fx: &mut Fx, s: &Strike) {
    let Strike { look, feet, dir, n, owner, fist } = *s;
    let ramp = look.ramp();
    let side = side_of(dir);
    let sign = if n.is_multiple_of(2) { 1.0 } else { -1.0 };
    let reach = look.range.max(1.5);
    let half = look.spread.to_radians().clamp(0.3, 1.2);
    let hand = fist.unwrap_or(feet + Vec3::Y * 1.0 + dir * 0.4 - side * 0.25 * sign);
    // Anticipation: a glint on the knuckles or the hammer face.
    let rot = fx.range(0.0, 1.0);
    fx.sprite(seq::GLINT.nth(0), hand)
        .size(0.55)
        .ramp(ramp)
        .value(value::HOT)
        .rot(rot)
        .life(4.0 * F)
        .erode(0.5, 1.0)
        .pull(0.6)
        .layer(Layer::Front)
        .owner(owner)
        .emit();
    if look.key == "titanfall_hammer" {
        // A tall overhead smear in the vertical plane, drawn down onto the strike point.
        let mut sm = Smear::new(feet + Vec3::Y * 1.3 - dir * 0.2, dir, reach * 0.85, ramp, owner);
        sm.strip = smear_strip(ramp);
        sm.width = reach * 0.4;
        sm.sweep = 2.3;
        sm.tilt = FRAC_PI_2 * sign;
        sm.life = 12.0 * F;
        sm.gain = 1.2;
        fx.smear(sm);
        let hit = feet + dir * reach * 0.7;
        fx.sprite(seq::STAR9.nth(1), hit + Vec3::Y * 0.3)
            .radius(1.0)
            .ramp(ramp)
            .delay(5.0 * F)
            .life(8.0 * F)
            .play(Play::Life)
            .erode(0.5, 1.0)
            .ink_backed()
            .owner(owner)
            .emit();
        fx.decal(Decal::CrackStarA, hit, 1.5, ramp, 2.0, owner);
        fx.shards(hit + Vec3::Y * 0.3, 6, 5.5, Ramp::Dust, 0.22, owner);
        fx.light(hit + Vec3::Y * 0.6, ramp.light(), 180_000.0, 6.0, 0.2, owner);
        return;
    }
    let finisher = n % 3 == 2;
    let (r, width, life) = if finisher { (reach, reach * 0.5, 11.0 * F) } else { (reach * 0.66, reach * 0.3, 9.0 * F) };
    let mut sm = Smear::new(feet + Vec3::Y * 0.95 - dir * 0.15, dir, r, ramp, owner);
    sm.strip = smear_strip(ramp);
    sm.width = width;
    sm.sweep = (2.0 * half).min(2.0) * sign * if finisher { 1.2 } else { 1.0 };
    // Jabs and hooks swing in a slightly tilted plane (the fist's), the finisher flat and wide.
    sm.tilt = if finisher { 0.0 } else { 0.35 * sign };
    sm.life = life;
    sm.gain = if finisher { 1.35 } else { 1.15 };
    fx.smear(sm);
    if ramp == Ramp::Flame {
        let at = feet + Vec3::Y * 0.9 + dir * r * 0.7;
        fx.embers(at, 3, r * 0.3, owner);
    }
    if finisher {
        // Speed streaks down the aim line, a shock front at the reach, a dust puff at the feet.
        for i in 0..3 {
            let o = side * ((i as f32 - 1.0) * 0.35) + Vec3::Y * (0.8 + 0.15 * i as f32);
            let len = reach * fx.range(0.7, 0.95);
            fx.sprite(seq::MUZZLE_SPIKE.nth(1), feet + o + dir * 0.3)
                .size2(len, len * 0.18)
                .toward(dir)
                .ramp(ramp)
                .value(value::HOT)
                .delay(i as f32 * F)
                .life(6.0 * F)
                .erode(0.3, 1.0)
                .pull(0.4)
                .layer(Layer::Front)
                .owner(owner)
                .emit();
        }
        fx.ring(feet + dir * reach * 0.8, 0.3, 1.3, 10.0 * F, strip::SHOCK_FRONT, ramp, owner);
        puff(fx, feet + Vec3::Y * 0.15 - dir * 0.2, 0.5, Ramp::Dust, 0.5, owner);
        fx.light(feet + dir * reach * 0.6 + Vec3::Y * 0.8, ramp.light(), 90_000.0, 5.0, 0.15, owner);
    }
}

// ───────────────────────────── hits (§9-10) ─────────────────────────────

/// A weapon hit to punctuate.
#[derive(Clone, Copy, Debug)]
pub struct Contact<'a> {
    /// Where on the body (the model's hit centre).
    pub at: Vec3,
    /// Travel of what hit (flat, unit; zero when unknown).
    pub dir: Vec3,
    pub ramp: Ramp,
    pub owner: Owner,
    pub body: f32,
    pub crit: bool,
    pub precision: bool,
    /// The weapon that hit (None: an ability, a hazard, a turret, the unknown).
    pub look: Option<&'a Look>,
    /// Plated elites give a glancing spark.
    pub plated: bool,
    /// Several hits in 0.08 s on one target: only the secondaries play.
    pub repeat: bool,
}

/// Hit punctuation (VFX_STYLE §10) with the weapon's own accent (§6 "Impact accent", §9).
pub fn contact(fx: &mut Fx, c: &Contact) {
    use ProjectileStyle as S;
    let Contact { at, dir, ramp, owner, body, crit, precision, look, plated, repeat } = *c;
    let style = look.map(|l| l.style);
    let fire = look.map_or(FireKind::Auto, |l| l.fire);
    let melee = fire == FireKind::Melee;
    let beam = fire == FireKind::Beam;
    let mine = owner == Owner::Mine;
    if !repeat {
        let size = match style {
            _ if crit => 0.5,
            _ if melee => 0.55 + body * 0.1,
            Some(S::Needle | S::Pellet) => 0.24 + body * 0.08,
            Some(S::Slug | S::Arrow) => 0.36 + body * 0.1,
            _ if beam => 0.26 + body * 0.06,
            _ => 0.32 + body * 0.12,
        };
        let kind = match (mine, crit, precision) {
            (true, _, true) => HitKind::Precision,
            (true, true, _) => HitKind::Crit,
            _ if melee => HitKind::Heavy,
            _ => HitKind::Plain,
        };
        fx.impact(Hit::new(at, ramp, size, owner).kind(kind).dir(dir).body(body));
        if kind == HitKind::Precision || kind == HitKind::Crit {
            // The element's star still shows under the punctuation.
            fx.impact(Hit::new(at, ramp, size * 0.8, owner).dir(dir).body(body));
        }
    }
    let travel = if dir.length_squared() > 1e-4 { dir } else { Vec3::ZERO };
    if melee && !repeat {
        // Knocked back: ink drag lines behind the body, the element's secondary.
        drag_lines(fx, at, travel, 3, body, owner);
        element_secondary(fx, at, travel, ramp, 2, owner);
        return;
    }
    if repeat {
        return;
    }
    let pull = body + 0.2;
    match style {
        Some(S::Slug) => {
            // A directional spike star: one long spike along the travel.
            fx.sprite(seq::MUZZLE_SPIKE.nth(0), at)
                .size2(1.3, 0.65)
                .toward(if travel == Vec3::ZERO { Vec3::X } else { travel })
                .ramp(ramp)
                .play(Play::Frame(0))
                .life(4.0 * F)
                .erode(0.3, 1.0)
                .pull(pull)
                .layer(Layer::Front)
                .owner(owner)
                .emit();
        }
        Some(S::Needle) => {
            // A 4-point tick spark kicked back at the shooter.
            fx.sprite(seq::STAR4.nth(2), at - travel * 0.2)
                .radius(0.14)
                .ramp(ramp)
                .value(value::LIGHT)
                .vel(-travel * 3.0 + Vec3::Y * 1.0)
                .life(4.0 * F)
                .pull(pull)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        Some(S::Pellet) => {
            fx.sprite(seq::GLINT.nth(0), at + Vec3::Y * 0.1)
                .size(0.4)
                .ramp(ramp)
                .gain(1.3)
                .life(4.0 * F)
                .pull(pull)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
        Some(S::Coin) => {
            // The coin "ting": a bright 4-point glint and a bounce spark.
            fx.sprite(seq::STAR4.nth(1), at + Vec3::Y * 0.2)
                .radius(0.3)
                .ramp(Ramp::Radiant)
                .value(value::HOT)
                .life(4.0 * F)
                .pull(pull)
                .layer(Layer::Front)
                .owner(owner)
                .emit();
            fx.sparks(at, -travel, 2, 5.0, Ramp::Radiant, owner);
        }
        Some(S::Shard) => {
            fx.shards(at, 4, 4.5, ramp, 0.14, owner);
        }
        Some(S::Blade) if look.is_some_and(|l| l.key == "orrery_discs") => {
            // A disc cuts a slash through the body.
            let d = Quat::from_rotation_y(0.5) * if travel == Vec3::ZERO { Vec3::X } else { travel };
            fx.slash(at, d, 1.2 + body, ramp, owner);
        }
        _ => {}
    }
    // Pierce: an exit wound on the far side, sparks out of the back (§9).
    if look.is_some_and(|l| l.pierce > 0)
        && travel != Vec3::ZERO
        && matches!(style, Some(S::Slug | S::Arrow | S::Blade))
    {
        let exit = at + travel * (body * 0.8 + 0.1);
        fx.slash(exit, travel, 0.8 + body * 0.8, ramp, owner);
        fx.sparks(exit, -travel, 4, 6.0, ramp, owner);
    }
    element_secondary(fx, at, travel, ramp, 1, owner);
    if plated {
        // A glancing, element-agnostic spark skipping off the plates.
        let skip = side_of(if travel == Vec3::ZERO { Vec3::X } else { travel });
        fx.sparks(at, skip, 3, 7.0, Ramp::Mono, owner);
    }
}

// ───────────────────────────── explosions (§11) ─────────────────────────────

/// What made an explosion, when the arms module can tell (the event carries only the element).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum Blast {
    #[default]
    Plain,
    /// A shell or an iron globe: extra smoke crown and shrapnel.
    Shell,
    /// A thrown or dropped boulder: rock debris and a crater.
    Boulder,
    /// The Voidheart's collapse.
    Singularity,
    /// A hammer strike's splash: a ground crack star.
    Hammer,
    /// The Sundial's orb: a clock glyph.
    Dial,
}

/// The layered burst at the true radius with the element's set dressing (VFX_STYLE §11).
pub fn explosion(fx: &mut Fx, ramp: Ramp, at: Vec3, radius: f32, blast: Blast, owner: Owner) {
    let r = radius.max(0.3);
    let ground = Vec3::new(at.x, 0.0, at.z);
    // Void implodes first: an inward star on an ink core for 4 frames.
    if ramp == Ramp::Void {
        fx.sprite(seq::PETAL_INWARD_STAR, ground + Vec3::Y * 0.6)
            .radius(r * 0.9)
            .ramp(Ramp::Void)
            .play(Play::Life)
            .life(5.0 * F)
            .erode(0.7, 1.0)
            .ink_backed()
            .layer(Layer::Front)
            .owner(owner)
            .emit();
    }
    fx.burst(ramp, at, r, owner);
    match ramp {
        Ramp::Flame => {
            // Tongues lick up round the rim, never out of the middle (a hero may stand in it).
            let seqs = [seq::FLAME_NARROW, seq::FLAME_MEDIUM, seq::FLAME_LICKS];
            let n = (2.0 + r * 1.2).min(6.0) as u32;
            for a in fx.around(n) {
                let off = Vec3::new(a.cos(), 0.0, a.sin()) * r * fx.range(0.75, 1.0);
                let s = seqs[(fx.rand() * 3.0) as usize % 3];
                let h = (0.4 + r * 0.25) * fx.range(0.8, 1.15);
                let life = fx.range(0.3, 0.42);
                fx.sprite(s, ground + off + Vec3::Y * 0.02)
                    .size(h)
                    .ramp(Ramp::Flame)
                    .life(life)
                    .scale(Curve::new(0.3, 1.0, 0.5, 0.2))
                    .erode(0.5, 1.0)
                    .pull(0.2)
                    .class(Class::Secondary)
                    .owner(owner)
                    .emit();
            }
        }
        Ramp::Radiant => {
            fx.sprite(seq::RADIANT_RAY_FAN, ground + Vec3::Y * 0.5)
                .radius(r * 1.1)
                .ramp(Ramp::Radiant)
                .play(Play::Life)
                .life(10.0 * F)
                .erode(0.6, 1.0)
                .layer(Layer::Front)
                .owner(owner)
                .emit();
            let rot = fx.rand() * TAU;
            let glyph = if blast == Blast::Dial { Glyph::ClockDial } else { Glyph::SunWheel };
            fx.decal_seq(glyph.seq(), ground, r * 0.75, rot, Ramp::Radiant, 1.5, owner);
        }
        Ramp::Void => {
            fx.decal_seq(seq::VOID_SWIRL, ground, r * 0.8, 0.0, Ramp::Void, 1.0, owner);
        }
        Ramp::Plague => {
            fx.sprite(seq::PLAGUE_SPLAT, ground + Vec3::Y * 0.4)
                .radius(r * 0.8)
                .ramp(Ramp::Plague)
                .play(Play::Life)
                .life(12.0 * F)
                .erode(0.6, 1.0)
                .owner(owner)
                .emit();
        }
        _ => {}
    }
    match blast {
        Blast::Shell => {
            // A thicker smoke crown lit from inside, lifting off by frame 20 (§20.3).
            for a in fx.around(5) {
                let off = Vec3::new(a.cos(), 0.0, a.sin()) * r * 0.45;
                puff(fx, ground + off + Vec3::Y * 0.4, r * 0.38, Ramp::Kinetic, 0.6, owner);
            }
        }
        Blast::Boulder => {
            fx.shards(ground + Vec3::Y * 0.5, 7, 6.0, Ramp::Dust, 0.3, owner);
            fx.decal(Decal::Crater, ground, r * 0.9, Ramp::Kinetic, 3.0, owner);
        }
        Blast::Singularity => {
            fx.ring(ground, r * 1.3, r * 0.2, 14.0 * F, strip::ACCENT_RING, Ramp::Void, owner);
        }
        Blast::Hammer => {
            fx.decal(Decal::CrackStarB, ground, r * 1.1, ramp, 2.5, owner);
        }
        Blast::Dial | Blast::Plain => {}
    }
}

// ───────────────────────────── chains (§9 "Chain") ─────────────────────────────

/// An ink-sheathed bolt hopping between two nodes (VFX_STYLE §9): a star and light at the node,
/// the previous shape lingering as a dim ghost for 2 frames.
pub fn chain(fx: &mut Fx, a: Vec3, b: Vec3, ramp: Ramp, owner: Owner) {
    let d = b - a;
    let len = d.length();
    if len < 0.1 {
        return;
    }
    let k = (fx.rand() * 5.0) as u16;
    // The ink sheath, wider, under the bright bolt.
    fx.sprite(seq::BOLT.frames_from(k, 2), a)
        .size2(len, 1.0)
        .toward(d)
        .ramp(ramp)
        .value(value::INK)
        .alpha(0.85)
        .play(Play::Fps(30.0))
        .life(7.0 * F)
        .erode(0.4, 1.0)
        .pull(0.5)
        .layer(Layer::Main)
        .owner(owner)
        .emit();
    fx.bolt(a, b, ramp, 0.62, 8.0 * F, owner);
    // The ghost of the previous strobe shape.
    fx.sprite(seq::BOLT.frames_from((k + 3) % 6, 1), a)
        .size2(len, 0.45)
        .toward(d)
        .ramp(ramp)
        .alpha(0.4)
        .delay(2.0 * F)
        .life(3.0 * F)
        .pull(0.6)
        .layer(Layer::Front)
        .class(Class::Secondary)
        .owner(owner)
        .emit();
    fx.sprite(hit_star(ramp), b)
        .radius(0.4)
        .ramp(ramp)
        .play(Play::Life)
        .life(6.0 * F)
        .erode(0.5, 1.0)
        .pull(0.5)
        .ink_backed()
        .owner(owner)
        .emit();
    fx.sparks(b, d / len, 2, 4.5, ramp, owner);
    fx.light(b, ramp.light(), 40_000.0, 4.0, 0.12, owner);
}

// ───────────────────────────── enemy shots (§15.2) ─────────────────────────────

/// A 3-frame star where an enemy shot leaves its caster (magenta, never an element).
pub fn enemy_spawn_flash(fx: &mut Fx, at: Vec3, r: f32) {
    fx.sprite(seq::STAR5, at)
        .radius(0.28 + r * 0.8)
        .ramp(Ramp::EnemyShot)
        .play(Play::Life)
        .life(4.0 * F)
        .erode(0.6, 1.0)
        .pull(0.4)
        .layer(Layer::Danger)
        .class(Class::Danger)
        .owner(Owner::Enemy)
        .emit();
}

/// An enemy shot landing (a player, a barricade) or running out: a small magenta star.
pub fn enemy_impact(fx: &mut Fx, at: Vec3, dir: Vec3, landed: bool) {
    let r = if landed { 0.5 } else { 0.25 };
    let rot = fx.range(-0.4, 0.4);
    fx.sprite(seq::STAR5, at)
        .radius(r)
        .ramp(Ramp::EnemyShot)
        .rot(rot)
        .play(Play::Life)
        .life(if landed { 6.0 } else { 4.0 } * F)
        .erode(0.5, 1.0)
        .pull(0.6)
        .ink_backed()
        .layer(Layer::Danger)
        .class(Class::Danger)
        .owner(Owner::Enemy)
        .emit();
    if landed {
        fx.sparks(at, dir, 3, 4.5, Ramp::EnemyShot, Owner::Enemy);
    }
}
