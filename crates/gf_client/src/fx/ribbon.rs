//! Ribbons: projectile trails, beams, tethers and loot beams. A ribbon is a tapered strip built
//! every frame from a short position history (a ring buffer), widest at the head, eroding from
//! the tail (VFX_STYLE §2 "Ribbon", §21.4).
//!
//! Sources: an entity (read from its `GlobalTransform` after transform propagation, so the trail
//! never lags the body), an analytic straight flight (`pos0 + vel × t`, no history needed), or
//! points the caller moves by hand (beams, tethers).

use super::Layer;
use super::library::{Ramp, Strip};
use super::mesh::{CamBasis, LayerBuf};
use gf_engine::prelude::*;

/// History samples per ribbon.
pub const HISTORY: usize = 24;

/// How a ribbon's cross-section faces.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Facing {
    /// Turned to the camera about its own axis (trails, beams, tethers).
    Camera,
    /// Flat on the floor (dust ribbons, ground trails).
    Ground,
}

/// Where a ribbon's head is.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Source {
    /// An entity's world translation plus an offset.
    Entity(Entity, Vec3),
    /// A straight flight: `from + vel × (t − t0)`, with gravity (lobs).
    Linear { from: Vec3, vel: Vec3, gravity: f32, t0: f32 },
    /// Moved by the caller ([`super::Fx::ribbon_to`]).
    Manual,
}

/// The look of a ribbon.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RibbonStyle {
    pub strip: Strip,
    pub ramp: Ramp,
    /// Width at the head (metres).
    pub width: f32,
    /// Tail width as a fraction of the head's.
    pub taper: f32,
    /// Longest visible length (metres).
    pub max_len: f32,
    /// Oldest visible sample (seconds).
    pub max_age: f32,
    pub facing: Facing,
    pub gain: f32,
    pub alpha: f32,
    pub layer: Layer,
    /// Tileable strips: metres per repeat of the texture (0 = stretch once, tail to head).
    pub tile: f32,
    /// Tileable strips: scroll speed along the ribbon (m/s, toward the head).
    pub scroll: f32,
    /// Seconds for the tail to catch the head once the source is gone.
    pub fade: f32,
    /// Baseline erosion (dry-brush break-up of the tail while alive).
    pub erode: f32,
    /// Pull toward the camera (metres).
    pub pull: f32,
}

impl RibbonStyle {
    pub const fn new(strip: Strip, ramp: Ramp, width: f32, max_len: f32) -> RibbonStyle {
        RibbonStyle {
            strip,
            ramp,
            width,
            taper: 0.35,
            max_len,
            max_age: 0.5,
            facing: Facing::Camera,
            gain: 1.0,
            alpha: 1.0,
            layer: Layer::Main,
            tile: 0.0,
            scroll: 0.0,
            fade: 0.18,
            erode: 0.12,
            pull: 0.3,
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Sample {
    pos: Vec3,
    time: f32,
}

/// A live ribbon.
#[derive(Clone, Debug)]
pub struct Ribbon {
    pub style: RibbonStyle,
    pub source: Source,
    pub cap: f32,
    /// Alpha multiplier from ownership and tier.
    pub own_alpha: f32,
    /// Keep only the head fraction (allies' trails in the Reduced tier keep their head third).
    pub keep: f32,
    samples: [Sample; HISTORY],
    /// Index of the newest sample.
    newest: usize,
    count: usize,
    head: Vec3,
    detached: Option<f32>,
    /// Refreshed this frame (immediate-mode beams fade when their caller stops).
    pub(crate) touched: bool,
    pub(crate) immediate: bool,
    /// Fixed polyline for beams and tethers (from tail to head), instead of the history.
    pub(crate) line: Option<(Vec3, Vec3)>,
    /// Identifies an immediate-mode line across frames.
    pub(crate) line_key: Option<u32>,
    /// Detach at this time (pillars, timed tethers).
    pub(crate) expires: Option<f32>,
    born: f32,
}

impl Ribbon {
    pub fn new(style: RibbonStyle, source: Source, head: Vec3, now: f32) -> Ribbon {
        let mut r = Ribbon {
            style,
            source,
            cap: 3.2,
            own_alpha: 1.0,
            keep: 1.0,
            samples: [Sample::default(); HISTORY],
            newest: 0,
            count: 0,
            head,
            detached: None,
            touched: true,
            immediate: false,
            line: None,
            line_key: None,
            expires: None,
            born: now,
        };
        // An entity's position is unknown until the first step reads it.
        if !matches!(source, Source::Entity(..)) {
            r.push(head, now);
        }
        r
    }

    fn push(&mut self, pos: Vec3, time: f32) {
        self.newest = (self.newest + 1) % HISTORY;
        self.samples[self.newest] = Sample { pos, time };
        self.count = (self.count + 1).min(HISTORY);
    }

    /// Move the head (manual ribbons).
    pub fn move_to(&mut self, pos: Vec3) {
        self.head = pos;
    }

    /// Stop following: the tail catches up with the head and erodes away.
    pub fn detach(&mut self, now: f32) {
        if self.detached.is_none() {
            self.detached = Some(now);
        }
    }

    pub fn is_detached(&self) -> bool {
        self.detached.is_some()
    }

    /// Advance: sample the head, drop old samples. `entity_pos` is the source entity's position
    /// (`Some(None)` when it is gone). Returns false once fully faded.
    pub(crate) fn step(&mut self, now: f32, entity_pos: Option<Option<Vec3>>) -> bool {
        if self.expires.is_some_and(|t| now >= t) {
            self.detach(now);
        }
        if self.detached.is_none() {
            match self.source {
                Source::Entity(_, offset) => match entity_pos {
                    Some(Some(p)) => self.head = p + offset,
                    _ => self.detach(now),
                },
                Source::Linear { from, vel, gravity, t0 } => {
                    let t = now - t0;
                    self.head = from + vel * t - Vec3::Y * (0.5 * gravity * t * t);
                }
                Source::Manual => {}
            }
        }
        if self.count == 0 {
            if self.detached.is_some() {
                return false;
            }
            self.push(self.head, now);
        }
        if let Some(at) = self.detached {
            if now - at >= self.style.fade {
                return false;
            }
        } else if self.line.is_none() {
            // A new sample every ~2 frames or 0.25 m, whichever first; the head itself is live.
            let last = self.samples[self.newest];
            if (self.head - last.pos).length_squared() > 0.0625 || now - last.time > 0.033 {
                self.push(self.head, now);
            }
        }
        true
    }

    /// Visible polyline from the head backward (at most `HISTORY + 1` points), cut to the
    /// ribbon's length and age.
    fn polyline(&self, now: f32, out: &mut Vec<Vec3>) {
        out.clear();
        if let Some((a, b)) = self.line {
            out.push(b);
            out.push(a);
            return;
        }
        let fade_k = self.detached.map_or(0.0, |at| ((now - at) / self.style.fade.max(1e-3)).clamp(0.0, 1.0));
        let max_len = self.style.max_len * (1.0 - fade_k) * self.keep;
        let oldest = now - self.style.max_age * (1.0 - fade_k);
        out.push(self.head);
        let mut len = 0.0;
        let mut prev = self.head;
        for i in 0..self.count {
            let s = self.samples[(self.newest + HISTORY - i) % HISTORY];
            if (s.pos - prev).length_squared() < 1e-8 {
                continue;
            }
            let seg = (s.pos - prev).length();
            // Cut at the age limit (interpolated) or the length limit.
            let mut p = s.pos;
            let mut stop = false;
            if s.time < oldest {
                // Where along this segment the age limit falls (by time).
                let prev_time = if i == 0 { now } else { self.samples[(self.newest + HISTORY - i + 1) % HISTORY].time };
                let span = (prev_time - s.time).max(1e-4);
                let f = ((prev_time - oldest) / span).clamp(0.0, 1.0);
                p = prev.lerp(s.pos, f);
                stop = true;
            }
            let seg_p = if stop { (p - prev).length() } else { seg };
            if len + seg_p > max_len {
                let f = ((max_len - len) / seg_p.max(1e-4)).clamp(0.0, 1.0);
                out.push(prev.lerp(p, f));
                return;
            }
            len += seg_p;
            out.push(p);
            prev = p;
            if stop || out.len() > HISTORY {
                return;
            }
        }
    }

    /// Expand into strip triangles.
    pub(crate) fn emit(&self, buf: &mut LayerBuf, cam: &CamBasis, now: f32, scratch: &mut Vec<Vec3>) {
        self.polyline(now, scratch);
        if scratch.len() < 2 {
            return;
        }
        let st = &self.style;
        let fade_k = self.detached.map_or(0.0, |at| ((now - at) / st.fade.max(1e-3)).clamp(0.0, 1.0));
        let immediate_fade = if self.immediate && !self.touched { 0.0 } else { 1.0 };
        let alpha = st.alpha * self.own_alpha * immediate_fade;
        if alpha <= 1e-3 {
            return;
        }
        // Cumulative distance from the head.
        let mut dist = [0.0f32; HISTORY + 2];
        let mut d = 0.0;
        for (i, w) in scratch.windows(2).enumerate().take(HISTORY + 1) {
            d += (w[1] - w[0]).length();
            dist[i + 1] = d;
        }
        let total = d.max(1e-4);
        if total < 0.02 {
            return;
        }
        let erode = st.erode + (1.0 - st.erode) * fade_k;
        let tint = [alpha, st.gain, self.cap, st.ramp.v()];
        let fx = [erode, -1.0, 0.0, 1.0];
        let age = now - self.born;
        let base = buf.begin_strip();
        // Walk from the tail (u = 0) to the head (u = 1).
        let n = scratch.len();
        for j in (0..n).rev() {
            let p = scratch[j];
            let from_head = dist[j];
            let k = 1.0 - from_head / total; // 0 tail … 1 head
            let tangent = if j + 1 < n { p - scratch[j + 1] } else { scratch[j.saturating_sub(1)] - p };
            let tangent = tangent.normalize_or(cam.right);
            let side = match st.facing {
                Facing::Camera => tangent.cross(cam.fwd).normalize_or(cam.up),
                Facing::Ground => tangent.cross(Vec3::Y).normalize_or(Vec3::X),
            };
            let width = st.width * (st.taper + (1.0 - st.taper) * k);
            let u = if st.tile > 0.0 { (total - from_head) / st.tile - age * st.scroll / st.tile } else { k };
            let center = p + cam.back * st.pull;
            let half = side * width * 0.5;
            buf.strip_pair(&st.strip, center - half, center + half, u, tint, fx, [(total - from_head) * 0.35, 0.0]);
        }
        buf.end_strip(base);
    }
}
