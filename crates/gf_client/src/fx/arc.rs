//! Arc strips: melee smears and slashes (a crescent whose head sweeps across the strike, then
//! whose tail erodes), shockwave rings, dust walls and crowns. Generated in Rust as strips of
//! `segments` cross-sections (VFX_STYLE §2 "Smear", "Ring"; §7.4; §11).
//!
//! Geometry lives in a local frame: +Y is the plane normal, −Z is "forward" (angle 0), and
//! positive angles turn counter-clockwise seen from +Y. Rotate the frame (`basis`) to aim a smear
//! or to tilt it into an overhead swing.

use super::Layer;
use super::library::{Ramp, Strip};
use super::mesh::{CamBasis, LayerBuf};
use super::particle::Curve;
use gf_engine::prelude::*;

/// The cross-section of an arc strip.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Profile {
    /// A band of constant width lying in the plane (`v` = 0 inner … 1 outer).
    Band,
    /// A crescent: zero at the tail, thickest at `peak`, rounded at the head (smears).
    Crescent { peak: f32 },
    /// A wall standing on the plane (`v` = 0 foot … 1 top), flaring outward by `flare` at the top.
    Wall { flare: f32 },
}

/// How the visible part of the arc evolves.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Sweep {
    /// The whole arc is visible for the whole life.
    Static,
    /// The head sweeps from the start to the end in the first `lead` of the life, the body holds,
    /// and from `retract` on the tail chases the head (smears: f0-2 lead, f3-5 hold, f6-8 erode).
    Swing { lead: f32, retract: f32 },
}

/// A live arc strip.
#[derive(Clone, Copy, Debug)]
pub struct Arc {
    pub center: Vec3,
    /// Ride along with this entity (its translation + `center` as an offset).
    pub follow: Option<Entity>,
    pub basis: Quat,
    /// Outer radius over normalized age.
    pub radius: Curve,
    /// Band width (or wall height) over normalized age.
    pub width: Curve,
    /// Tail angle (radians from forward).
    pub start: f32,
    /// Signed sweep from the tail to the head (radians; positive = counter-clockwise).
    pub sweep: f32,
    pub sweep_anim: Sweep,
    pub profile: Profile,
    pub strip: Strip,
    pub ramp: Ramp,
    pub gain: f32,
    pub cap: f32,
    pub alpha: Curve,
    /// Texture repeats along the arc (tileable strips: gaps of a broken ring).
    pub repeats: f32,
    /// Spin of the texture along the arc (repeats per second).
    pub spin: f32,
    pub age: f32,
    pub life: f32,
    /// Erosion starts at normalized age `x` and reaches `y` at the end.
    pub erode: Vec2,
    pub segments: u16,
    pub pull: f32,
    pub layer: Layer,
    pub(crate) world: Vec3,
}

impl Arc {
    pub fn new(strip: Strip, center: Vec3, radius: f32, width: f32, life: f32) -> Arc {
        Arc {
            center,
            follow: None,
            basis: Quat::IDENTITY,
            radius: Curve::flat(radius),
            width: Curve::flat(width),
            start: 0.0,
            sweep: std::f32::consts::TAU,
            sweep_anim: Sweep::Static,
            profile: Profile::Band,
            strip,
            ramp: Ramp::Kinetic,
            gain: 1.0,
            cap: 3.2,
            alpha: Curve::ONE,
            repeats: 1.0,
            spin: 0.0,
            age: 0.0,
            life,
            erode: Vec2::new(0.5, 1.0),
            segments: 32,
            pull: 0.2,
            layer: Layer::Main,
            world: center,
        }
    }

    #[inline]
    pub fn k(&self) -> f32 {
        (self.age / self.life.max(1e-4)).clamp(0.0, 1.0)
    }

    pub(crate) fn step(&mut self, dt: f32, follow_pos: Option<Option<Vec3>>) -> bool {
        self.age += dt;
        self.world = match follow_pos {
            Some(Some(p)) => p + self.center,
            Some(None) => {
                self.follow = None;
                self.center = self.world;
                self.world
            }
            None => self.center,
        };
        self.age < self.life
    }

    pub(crate) fn emit(&self, buf: &mut LayerBuf, cam: &CamBasis) {
        let k = self.k();
        let alpha = self.alpha.at(k);
        let r_out = self.radius.at(k);
        let width = self.width.at(k);
        if alpha <= 1e-3 || r_out <= 1e-3 {
            return;
        }
        let (tail_f, head_f) = match self.sweep_anim {
            Sweep::Static => (0.0, 1.0),
            Sweep::Swing { lead, retract } => {
                let h = (k / lead.max(1e-3)).min(1.0);
                let h = 1.0 - (1.0 - h) * (1.0 - h);
                let t = if k > retract { ((k - retract) / (1.0 - retract).max(1e-3)).powf(1.4) * 0.9 } else { 0.0 };
                (t.min(h), h)
            }
        };
        if head_f - tail_f < 1e-3 {
            return;
        }
        let a_tail = self.start + self.sweep * tail_f;
        let a_head = self.start + self.sweep * head_f;
        let erode =
            if k > self.erode.x { (k - self.erode.x) / (1.0 - self.erode.x).max(1e-4) * self.erode.y } else { 0.0 };
        let tint = [alpha, self.gain, self.cap, self.ramp.v()];
        let fx = [erode, -1.0, 0.0, 1.0];
        let n = self.segments.max(2) as usize;
        let up = self.basis * Vec3::Y;
        let center = self.world + cam.back * self.pull;
        let spin = self.age * self.spin;
        let base = buf.begin_strip();
        for i in 0..=n {
            let u = i as f32 / n as f32;
            let a = a_tail + (a_head - a_tail) * u;
            let dir = self.basis * Vec3::new(-a.sin(), 0.0, -a.cos());
            let (inner, outer) = match self.profile {
                Profile::Band => (center + dir * (r_out - width).max(0.0), center + dir * r_out),
                Profile::Crescent { peak } => {
                    // The shape of the stroke over the *visible* arc: thin tail, thick at `peak`,
                    // rounded head (tools/vfx/sheets.py `warp_arc`).
                    let w = if u < peak {
                        (u / peak * std::f32::consts::FRAC_PI_2).sin().powf(1.3)
                    } else {
                        (1.0 - ((u - peak) / (1.0 - peak)).powi(2)).max(0.0).sqrt()
                    };
                    let w = (w * width).max(width * 0.03);
                    (center + dir * (r_out - w), center + dir * r_out)
                }
                Profile::Wall { flare } => (center + dir * r_out, center + dir * (r_out + flare) + up * width),
            };
            let tex_u = if self.strip.tileable { u * self.repeats * (head_f - tail_f) + spin } else { u };
            // The brush noise scrolls along the stroke as it ages.
            buf.strip_pair(&self.strip, inner, outer, tex_u, tint, fx, [a * r_out * 0.35 - self.age * 1.5, 0.0]);
        }
        buf.end_strip(base);
    }
}
