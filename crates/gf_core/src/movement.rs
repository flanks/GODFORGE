//! Shared player movement. The host simulation and client-side prediction call the *same*
//! [`step_mover`] so a replayed input history reproduces the authoritative position exactly.

use glam::Vec2;
use serde::{Deserialize, Serialize};

/// Static arena geometry for a room: an axis-aligned play area plus obstacles.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Arena {
    pub half_extents: Vec2,
    pub obstacles: Vec<Obstacle>,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum Obstacle {
    Circle { center: Vec2, radius: f32 },
    Box { center: Vec2, half: Vec2 },
}

impl Obstacle {
    /// Push a circle out of this obstacle. Returns the corrected center.
    pub fn push_out(&self, p: Vec2, r: f32) -> Vec2 {
        match *self {
            Obstacle::Circle { center, radius } => {
                let d = p - center;
                let min = radius + r;
                let len_sq = d.length_squared();
                if len_sq >= min * min {
                    return p;
                }
                let len = len_sq.sqrt();
                let n = if len > 1e-5 { d / len } else { Vec2::X };
                center + n * min
            }
            Obstacle::Box { center, half } => {
                let local = p - center;
                let clamped = local.clamp(-half, half);
                let d = local - clamped;
                let len_sq = d.length_squared();
                if len_sq > 1e-10 {
                    if len_sq >= r * r {
                        return p;
                    }
                    let len = len_sq.sqrt();
                    return center + clamped + d / len * r;
                }
                // Center is inside the box: exit along the shallowest axis.
                let pen_x = half.x - local.x.abs();
                let pen_y = half.y - local.y.abs();
                if pen_x < pen_y {
                    Vec2::new(center.x + local.x.signum() * (half.x + r), p.y)
                } else {
                    Vec2::new(p.x, center.y + local.y.signum() * (half.y + r))
                }
            }
        }
    }

    pub fn contains(&self, p: Vec2, r: f32) -> bool {
        self.push_out(p, r) != p
    }
}

impl Arena {
    pub fn rect(half_extents: Vec2) -> Self {
        Self { half_extents, obstacles: Vec::new() }
    }

    /// Resolve a circle against bounds and obstacles (two passes handle most corner cases).
    pub fn resolve(&self, mut p: Vec2, r: f32) -> Vec2 {
        for _ in 0..2 {
            for o in &self.obstacles {
                p = o.push_out(p, r);
            }
            p = p.clamp(-self.half_extents + Vec2::splat(r), self.half_extents - Vec2::splat(r));
        }
        p
    }

    /// Does a segment hit any obstacle? (Coarse sampling; used for projectile blocking.)
    pub fn segment_blocked(&self, a: Vec2, b: Vec2, r: f32) -> bool {
        let steps = ((b - a).length() / 0.25).ceil().max(1.0) as usize;
        (0..=steps).any(|i| {
            let p = a.lerp(b, i as f32 / steps as f32);
            self.obstacles.iter().any(|o| o.contains(p, r))
        })
    }

    pub fn in_bounds(&self, p: Vec2) -> bool {
        p.x.abs() <= self.half_extents.x && p.y.abs() <= self.half_extents.y
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct MoveTuning {
    pub dash_speed: f32,
    pub dash_time: f32,
    pub dash_iframes: f32,
    /// Fraction of move speed while downed (wraith drift).
    pub wraith_speed: f32,
    /// How quickly velocity approaches the target (1/s). High = snappy.
    pub accel: f32,
}

impl Default for MoveTuning {
    fn default() -> Self {
        Self { dash_speed: 22.0, dash_time: 0.16, dash_iframes: 0.2, wraith_speed: 0.45, accel: 30.0 }
    }
}

/// Predicted/authoritative mover state.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct MoverState {
    pub pos: Vec2,
    pub vel: Vec2,
    pub dash_left: f32,
    pub dash_dir: Vec2,
    pub dash_charges: u8,
    pub dash_recharge_left: f32,
    pub iframes: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MoveInput {
    pub dir: Vec2,
    /// Edge-triggered dash request.
    pub dash: bool,
    pub speed: f32,
    pub max_dash_charges: u8,
    pub dash_recharge: f32,
    /// Rooted / stance / stunned.
    pub can_move: bool,
    pub can_dash: bool,
    pub wraith: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct MoveEvents {
    pub dashed: bool,
}

pub fn step_mover(
    s: &mut MoverState,
    input: &MoveInput,
    t: &MoveTuning,
    dt: f32,
    arena: &Arena,
    radius: f32,
) -> MoveEvents {
    let mut ev = MoveEvents::default();

    // Dash recharge (one charge at a time).
    if s.dash_charges < input.max_dash_charges {
        s.dash_recharge_left -= dt;
        if s.dash_recharge_left <= 0.0 {
            s.dash_charges += 1;
            s.dash_recharge_left = if s.dash_charges < input.max_dash_charges { input.dash_recharge } else { 0.0 };
        }
    } else {
        s.dash_charges = input.max_dash_charges;
        s.dash_recharge_left = 0.0;
    }
    s.iframes = (s.iframes - dt).max(0.0);

    let dir = input.dir.clamp_length_max(1.0);
    if input.dash && input.can_dash && !input.wraith && s.dash_charges > 0 && s.dash_left <= 0.0 {
        let d = dir.try_normalize().or_else(|| s.vel.try_normalize()).unwrap_or(Vec2::X);
        s.dash_dir = d;
        s.dash_left = t.dash_time;
        s.iframes = s.iframes.max(t.dash_iframes);
        if s.dash_charges == input.max_dash_charges {
            s.dash_recharge_left = input.dash_recharge;
        }
        s.dash_charges -= 1;
        ev.dashed = true;
    }

    if s.dash_left > 0.0 {
        s.dash_left -= dt;
        s.vel = s.dash_dir * t.dash_speed;
    } else if input.can_move {
        let speed = if input.wraith { input.speed * t.wraith_speed } else { input.speed };
        let target = dir * speed;
        let k = 1.0 - (-t.accel * dt).exp();
        s.vel += (target - s.vel) * k;
    } else {
        s.vel = Vec2::ZERO;
    }

    s.pos = arena.resolve(s.pos + s.vel * dt, radius);
    ev
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input(dir: Vec2) -> MoveInput {
        MoveInput {
            dir,
            dash: false,
            speed: 6.0,
            max_dash_charges: 2,
            dash_recharge: 1.0,
            can_move: true,
            can_dash: true,
            wraith: false,
        }
    }

    #[test]
    fn walks_and_stops() {
        let arena = Arena::rect(Vec2::splat(50.0));
        let mut s = MoverState { dash_charges: 2, ..Default::default() };
        for _ in 0..60 {
            step_mover(&mut s, &input(Vec2::X), &MoveTuning::default(), 1.0 / 60.0, &arena, 0.5);
        }
        assert!(s.pos.x > 5.0 && s.pos.x < 6.0, "{}", s.pos.x);
        for _ in 0..60 {
            step_mover(&mut s, &input(Vec2::ZERO), &MoveTuning::default(), 1.0 / 60.0, &arena, 0.5);
        }
        assert!(s.vel.length() < 0.01);
    }

    #[test]
    fn dash_consumes_charges_and_recharges() {
        let arena = Arena::rect(Vec2::splat(50.0));
        let t = MoveTuning::default();
        let mut s = MoverState { dash_charges: 2, ..Default::default() };
        let mut i = input(Vec2::Y);
        i.dash = true;
        assert!(step_mover(&mut s, &i, &t, 1.0 / 60.0, &arena, 0.5).dashed);
        assert_eq!(s.dash_charges, 1);
        assert!(s.iframes > 0.0);
        // Can't chain while mid-dash.
        assert!(!step_mover(&mut s, &i, &t, 1.0 / 60.0, &arena, 0.5).dashed);
        i.dash = false;
        for _ in 0..70 {
            step_mover(&mut s, &i, &t, 1.0 / 60.0, &arena, 0.5);
        }
        assert_eq!(s.dash_charges, 2);
    }

    #[test]
    fn arena_blocks() {
        let mut arena = Arena::rect(Vec2::splat(10.0));
        arena.obstacles.push(Obstacle::Circle { center: Vec2::new(3.0, 0.0), radius: 1.0 });
        arena.obstacles.push(Obstacle::Box { center: Vec2::new(-3.0, 0.0), half: Vec2::splat(1.0) });
        let p = arena.resolve(Vec2::new(2.5, 0.0), 0.5);
        assert!((p - Vec2::new(1.5, 0.0)).length() < 1e-4);
        let q = arena.resolve(Vec2::new(-2.2, 0.1), 0.5);
        assert!(q.x >= -1.5 - 1e-4, "{q}");
        let r = arena.resolve(Vec2::new(40.0, -40.0), 0.5);
        assert_eq!(r, Vec2::new(9.5, -9.5));
        assert!(arena.segment_blocked(Vec2::new(0.0, 0.0), Vec2::new(6.0, 0.0), 0.1));
        assert!(!arena.segment_blocked(Vec2::new(0.0, 5.0), Vec2::new(6.0, 5.0), 0.1));
    }

    #[test]
    fn deterministic_replay() {
        // Prediction relies on bit-identical replays.
        let arena = Arena::rect(Vec2::splat(20.0));
        let t = MoveTuning::default();
        let inputs: Vec<MoveInput> = (0..120)
            .map(|i| {
                let mut m = input(crate::math::from_angle(i as f32 * 0.1));
                m.dash = i % 37 == 0;
                m
            })
            .collect();
        let run = || {
            let mut s = MoverState { dash_charges: 2, ..Default::default() };
            for i in &inputs {
                step_mover(&mut s, i, &t, 1.0 / 60.0, &arena, 0.5);
            }
            s
        };
        assert_eq!(run(), run());
    }
}
