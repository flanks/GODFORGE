//! Flipbook particles: billboards, ground quads, velocity streaks and axis quads, simulated in a
//! flat `Vec` (no entity per particle) and expanded into the batched layer meshes every frame.

use super::Layer;
use super::library::{Ramp, Seq};
use super::mesh::{CamBasis, LayerBuf};
use gf_engine::prelude::*;

/// A value over a particle's normalized age: `a` at 0, `b` at `mid`, `c` at 1 (piecewise linear).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Curve {
    pub a: f32,
    pub b: f32,
    pub c: f32,
    pub mid: f32,
}

impl Curve {
    pub const ONE: Curve = Curve { a: 1.0, b: 1.0, c: 1.0, mid: 0.5 };

    pub const fn flat(v: f32) -> Curve {
        Curve { a: v, b: v, c: v, mid: 0.5 }
    }

    /// From `a` to `c` linearly.
    pub const fn line(a: f32, c: f32) -> Curve {
        Curve { a, b: (a + c) * 0.5, c, mid: 0.5 }
    }

    pub const fn new(a: f32, b: f32, c: f32, mid: f32) -> Curve {
        Curve { a, b, c, mid }
    }

    #[inline]
    pub fn at(&self, k: f32) -> f32 {
        if k < self.mid {
            let m = self.mid.max(1e-4);
            self.a + (self.b - self.a) * (k / m)
        } else {
            let m = (1.0 - self.mid).max(1e-4);
            self.b + (self.c - self.b) * ((k - self.mid) / m).min(1.0)
        }
    }
}

/// Which way a particle's quad faces.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Orient {
    /// Faces the camera; `rot` turns it in the screen plane.
    Billboard,
    /// Lies on the floor (decals, swirls, Lichtenberg scorch); `rot` turns it about world up.
    Ground,
    /// Camera-facing, `+u` along the screen-projected velocity, stretched by `speed × stretch`.
    Velocity { stretch: f32 },
    /// Camera-facing about a world axis: `+u` along `dir` (muzzle flashes, bolts, slashes).
    Axis { dir: Vec3 },
}

/// How a flipbook advances.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Play {
    /// The sequence's painted rate (holds the last frame of a one-shot).
    Painted,
    /// A custom rate.
    Fps(f32),
    /// All frames spread over the particle's life.
    Life,
    /// One fixed frame.
    Frame(u16),
}

/// Where a particle travels when it follows a curve instead of its velocity (kill motes, heal
/// motes): a quadratic arc from `from` over a control point `height` above the midpoint to the
/// target, eased in.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Path {
    pub from: Vec3,
    /// The destination (updated from `target` while it lives).
    pub to: Vec3,
    /// Home on this entity's translation plus `offset` while it lives.
    pub target: Option<Entity>,
    pub offset: Vec3,
    pub height: f32,
}

/// One live flipbook quad.
#[derive(Clone, Copy, Debug)]
pub struct Particle {
    /// World position, or the offset from `follow`.
    pub pos: Vec3,
    pub vel: Vec3,
    /// Downward acceleration, m/s² (negative rises: embers, smoke).
    pub gravity: f32,
    /// Velocity damping per second.
    pub drag: f32,
    pub age: f32,
    pub life: f32,
    /// Quad size (width, height) in metres at scale 1.
    pub size: Vec2,
    pub scale: Curve,
    pub alpha: Curve,
    pub rot: f32,
    pub spin: f32,
    pub seq: Seq,
    pub play: Play,
    /// First frame offset (desynchronises looping flipbooks).
    pub phase: f32,
    pub ramp: Ramp,
    pub gain: f32,
    /// Ceiling on the final HDR gain (allies' effects are capped, VFX_STYLE §3.2).
    pub cap: f32,
    /// Ramp value override (< 0 = the painted value): ink backings use `value::INK`.
    pub value: f32,
    /// Cooling: by the end of its life a texel's value drops by `cool × (1.2 − B)` (low-B texels,
    /// the rims and cracks, cool first: smoke rims fade from light to deep, scorch cracks go dark).
    pub cool: f32,
    /// Erosion starts at normalized age `x` and reaches `y` at death.
    pub erode: Vec2,
    /// Edge softness (1 = the painted edge).
    pub soft: f32,
    pub orient: Orient,
    /// Minimum pull toward the camera (metres): keeps a hit star in front of the body it lands on.
    pub pull: f32,
    pub layer: Layer,
    /// Bounce on the floor (y = 0) with this restitution (< 0 = fall through).
    pub bounce: f32,
    pub follow: Option<Entity>,
    pub path: Option<Path>,
    /// Resolved world position this frame.
    pub(crate) world: Vec3,
}

impl Particle {
    pub fn new(seq: Seq, pos: Vec3) -> Particle {
        let life = if seq.fps > 0.0 && !seq.looped { seq.duration() } else { 0.5 };
        Particle {
            pos,
            vel: Vec3::ZERO,
            gravity: 0.0,
            drag: 0.0,
            age: 0.0,
            life,
            size: Vec2::new(seq.sheet.cell_aspect(), 1.0),
            scale: Curve::ONE,
            alpha: Curve::ONE,
            rot: 0.0,
            spin: 0.0,
            seq,
            play: Play::Painted,
            phase: 0.0,
            ramp: Ramp::Kinetic,
            gain: 1.0,
            cap: 3.2,
            value: -1.0,
            cool: 0.0,
            erode: Vec2::new(0.6, 1.0),
            soft: 1.0,
            orient: Orient::Billboard,
            pull: 0.4,
            layer: Layer::Main,
            bounce: -1.0,
            follow: None,
            path: None,
            world: pos,
        }
    }

    /// Normalized age 0..1.
    #[inline]
    pub fn k(&self) -> f32 {
        (self.age / self.life.max(1e-4)).clamp(0.0, 1.0)
    }

    fn frame(&self) -> u16 {
        let n = self.seq.frames.max(1);
        let raw = match self.play {
            Play::Frame(f) => return f.min(n - 1),
            Play::Life => (self.k() * n as f32) as u32,
            Play::Painted => ((self.age + self.phase) * self.seq.fps) as u32,
            Play::Fps(fps) => ((self.age + self.phase) * fps) as u32,
        };
        if self.seq.looped { (raw % n as u32) as u16 } else { raw.min(n as u32 - 1) as u16 }
    }

    /// Step the motion. Returns false once dead.
    pub(crate) fn step(&mut self, dt: f32, follow_pos: Option<Option<Vec3>>) -> bool {
        self.age += dt;
        if self.age >= self.life {
            return false;
        }
        if self.age < 0.0 {
            // Delayed: waiting to appear.
            if let Some(Some(p)) = follow_pos {
                self.world = p + self.pos;
            }
            return true;
        }
        self.rot += self.spin * dt;
        if let Some(path) = self.path.as_mut() {
            if let Some(Some(p)) = follow_pos {
                path.to = p + path.offset;
            }
            // Ease in: slow start, fast arrival (motes "snap" into the killer).
            let k = (self.age / self.life.max(1e-4)).clamp(0.0, 1.0);
            let e = k * k * (3.0 - 2.0 * k) * 0.4 + k * k * 0.6;
            let mid = (path.from + path.to) * 0.5 + Vec3::Y * path.height;
            let a = path.from.lerp(mid, e);
            let b = mid.lerp(path.to, e);
            self.world = a.lerp(b, e);
            return true;
        }
        self.vel.y -= self.gravity * dt;
        if self.drag > 0.0 {
            self.vel *= (1.0 - self.drag * dt).max(0.0);
        }
        self.pos += self.vel * dt;
        if self.bounce >= 0.0 && self.pos.y < 0.03 && self.follow.is_none() {
            self.pos.y = 0.03;
            if self.vel.y < 0.0 {
                self.vel.y = -self.vel.y * self.bounce;
                self.vel.x *= 0.6;
                self.vel.z *= 0.6;
                self.spin *= 0.5;
            }
        }
        self.world = match follow_pos {
            Some(Some(p)) => p + self.pos,
            Some(None) => {
                // The followed entity is gone: stay where it was last seen.
                self.follow = None;
                self.pos = self.world;
                self.world
            }
            None => self.pos,
        };
        true
    }

    /// Expand into one quad of `buf`.
    pub(crate) fn emit(&self, buf: &mut LayerBuf, cam: &CamBasis) {
        if self.age < 0.0 {
            return;
        }
        let k = self.k();
        let s = self.scale.at(k);
        let alpha = self.alpha.at(k);
        if s <= 1e-4 || alpha <= 1e-3 {
            return;
        }
        let frame = self.frame();
        let r = self.seq.uv_rect(frame);
        let mut w = self.size.x * s;
        let h = self.size.y * s;
        let piv = self.seq.pivot;
        // Local extents from the pivot (y up: the texture's v runs down).
        let (x0, x1) = (-piv.x, 1.0 - piv.x);
        let (y0, y1) = (-(1.0 - piv.y), piv.y);
        let (right, up) = match self.orient {
            Orient::Billboard => {
                let (sn, cs) = self.rot.sin_cos();
                (cam.right * cs + cam.up * sn, cam.up * cs - cam.right * sn)
            }
            Orient::Ground => {
                let (sn, cs) = self.rot.sin_cos();
                // Texture up = sim +y = world −z.
                (Vec3::new(cs, 0.0, -sn), Vec3::new(-sn, 0.0, -cs))
            }
            Orient::Velocity { stretch } => {
                let v = self.vel - cam.fwd * self.vel.dot(cam.fwd);
                let len = v.length();
                let dir = if len > 1e-4 { v / len } else { cam.right };
                // The streak grows with speed (pivot at the head: it stretches backward).
                w += len * stretch * s;
                (dir, cam.fwd.cross(dir).normalize_or_zero())
            }
            Orient::Axis { dir } => {
                let d = dir.normalize_or_zero();
                let side = d.cross(cam.fwd);
                let side = if side.length_squared() > 1e-6 { side.normalize() } else { cam.up };
                let (sn, cs) = self.rot.sin_cos();
                (d * cs + side * sn, side * cs - d * sn)
            }
        };
        let (ex, ey) = (right * w, up * h);
        let corners = [
            ex * x0 + ey * y1, // top-left (u0, v0)
            ex * x1 + ey * y1, // top-right
            ex * x1 + ey * y0, // bottom-right
            ex * x0 + ey * y0, // bottom-left
        ];
        let mut center = self.world;
        if !matches!(self.orient, Orient::Ground) {
            // Pull toward the camera (orthographic: the screen position does not move) far enough to
            // clear the floor and the body the effect sits on.
            let low = corners.iter().map(|c| c.y).fold(f32::MAX, f32::min) + center.y;
            let clear = ((0.02 - low) / cam.back.y.max(0.2)).max(0.0);
            center += cam.back * clear.max(self.pull);
        }
        let erode =
            if k > self.erode.x { (k - self.erode.x) / (1.0 - self.erode.x).max(1e-4) * self.erode.y } else { 0.0 };
        let tint = [alpha, self.gain, self.cap, self.ramp.v()];
        let fx = [erode, self.value, self.cool * k, self.soft];
        let uv = [[r.x, r.y], [r.z, r.y], [r.z, r.w], [r.x, r.w]];
        buf.quad([center + corners[0], center + corners[1], center + corners[2], center + corners[3]], uv, tint, fx);
    }
}
