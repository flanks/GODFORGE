//! Small 2D helpers. The simulation lives on the ground plane (x, z in world space → `Vec2`).

use glam::Vec2;

/// Unit vector for an angle in radians (0 = +X, counter-clockwise).
#[inline]
pub fn from_angle(rad: f32) -> Vec2 {
    Vec2::new(rad.cos(), rad.sin())
}

/// Angle of a vector in radians.
#[inline]
pub fn angle_of(v: Vec2) -> f32 {
    v.y.atan2(v.x)
}

/// Rotate `v` by `rad`.
#[inline]
pub fn rotate(v: Vec2, rad: f32) -> Vec2 {
    let (s, c) = rad.sin_cos();
    Vec2::new(v.x * c - v.y * s, v.x * s + v.y * c)
}

/// Unsigned angle between two directions in radians (0..=PI). Zero vectors count as aligned.
#[inline]
pub fn angle_between(a: Vec2, b: Vec2) -> f32 {
    let (Some(a), Some(b)) = (a.try_normalize(), b.try_normalize()) else {
        return 0.0;
    };
    a.dot(b).clamp(-1.0, 1.0).acos()
}

/// Rotate `from` toward `to` by at most `max_rad`, returning a unit vector.
pub fn turn_toward(from: Vec2, to: Vec2, max_rad: f32) -> Vec2 {
    let (Some(f), Some(t)) = (from.try_normalize(), to.try_normalize()) else {
        return from.normalize_or_zero();
    };
    let ang = angle_between(f, t);
    if ang <= max_rad {
        return t;
    }
    let sign = if f.perp_dot(t) >= 0.0 { 1.0 } else { -1.0 };
    rotate(f, sign * max_rad)
}

/// Normalized lerp between two directions; `t` in 0..=1. Falls back to `b` if they cancel out.
pub fn nlerp_dir(a: Vec2, b: Vec2, t: f32) -> Vec2 {
    let v = a.normalize_or_zero().lerp(b.normalize_or_zero(), t.clamp(0.0, 1.0));
    v.try_normalize().unwrap_or_else(|| b.normalize_or_zero())
}

/// Solve for the direction a projectile of `speed` fired from `shooter` must travel to intercept a
/// target at `target` moving with constant `target_vel`. Returns the aim point, or `None` when the
/// target cannot be caught (falls back to direct aim in callers).
pub fn lead_point(shooter: Vec2, target: Vec2, target_vel: Vec2, speed: f32) -> Option<Vec2> {
    if speed <= 0.0 {
        return None;
    }
    let d = target - shooter;
    let a = target_vel.length_squared() - speed * speed;
    let b = 2.0 * d.dot(target_vel);
    let c = d.length_squared();
    let t = if a.abs() < 1e-6 {
        if b.abs() < 1e-6 {
            return None;
        }
        -c / b
    } else {
        let disc = b * b - 4.0 * a * c;
        if disc < 0.0 {
            return None;
        }
        let sq = disc.sqrt();
        let t1 = (-b - sq) / (2.0 * a);
        let t2 = (-b + sq) / (2.0 * a);
        match (t1 > 0.0, t2 > 0.0) {
            (true, true) => t1.min(t2),
            (true, false) => t1,
            (false, true) => t2,
            _ => return None,
        }
    };
    if t <= 0.0 || !t.is_finite() {
        return None;
    }
    Some(target + target_vel * t)
}

/// Squared distance from point `p` to segment `a`–`b`.
pub fn dist_sq_point_segment(p: Vec2, a: Vec2, b: Vec2) -> f32 {
    let ab = b - a;
    let len_sq = ab.length_squared();
    if len_sq <= f32::EPSILON {
        return p.distance_squared(a);
    }
    let t = ((p - a).dot(ab) / len_sq).clamp(0.0, 1.0);
    p.distance_squared(a + ab * t)
}

/// Is `p` inside a cone at `origin` facing `dir` with half-angle `half_angle` and length `range`?
pub fn in_cone(p: Vec2, origin: Vec2, dir: Vec2, half_angle: f32, range: f32) -> bool {
    let d = p - origin;
    let dist_sq = d.length_squared();
    if dist_sq > range * range {
        return false;
    }
    dist_sq < 1e-8 || angle_between(dir, d) <= half_angle
}

/// Exponential approach helper for frame-rate independent smoothing: returns the lerp factor for
/// a given `rate` (1/s) over `dt`.
#[inline]
pub fn smoothing_factor(rate: f32, dt: f32) -> f32 {
    1.0 - (-rate * dt).exp()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::{FRAC_PI_2, PI};

    #[test]
    fn rotate_and_angles() {
        let v = rotate(Vec2::X, FRAC_PI_2);
        assert!((v - Vec2::Y).length() < 1e-5);
        assert!((angle_between(Vec2::X, -Vec2::X) - PI).abs() < 1e-5);
        assert_eq!(angle_between(Vec2::ZERO, Vec2::X), 0.0);
    }

    #[test]
    fn turn_toward_clamps() {
        let r = turn_toward(Vec2::X, Vec2::Y, 0.1);
        assert!((angle_between(Vec2::X, r) - 0.1).abs() < 1e-4);
        assert!(r.y > 0.0, "turns counter-clockwise toward +Y");
        let r2 = turn_toward(Vec2::X, -Vec2::Y, 0.1);
        assert!(r2.y < 0.0, "turns clockwise toward -Y");
        assert_eq!(turn_toward(Vec2::X, Vec2::Y, 10.0), Vec2::Y);
    }

    #[test]
    fn lead_hits_moving_target() {
        let shooter = Vec2::ZERO;
        let target = Vec2::new(10.0, 0.0);
        let vel = Vec2::new(0.0, 3.0);
        let speed = 20.0;
        let aim = lead_point(shooter, target, vel, speed).expect("interceptable");
        // Time for the bullet to reach the aim point must equal time for the target to get there.
        let t_bullet = aim.length() / speed;
        let t_target = (aim - target).length() / vel.length();
        assert!((t_bullet - t_target).abs() < 1e-3);
    }

    #[test]
    fn lead_fails_for_uncatchable() {
        assert!(lead_point(Vec2::ZERO, Vec2::new(5.0, 0.0), Vec2::new(50.0, 0.0), 10.0).is_none());
    }

    #[test]
    fn segment_distance() {
        let d = dist_sq_point_segment(Vec2::new(0.0, 2.0), Vec2::new(-1.0, 0.0), Vec2::new(1.0, 0.0));
        assert!((d - 4.0).abs() < 1e-5);
        let end = dist_sq_point_segment(Vec2::new(3.0, 0.0), Vec2::new(-1.0, 0.0), Vec2::new(1.0, 0.0));
        assert!((end - 4.0).abs() < 1e-5);
    }

    #[test]
    fn cone_membership() {
        assert!(in_cone(Vec2::new(5.0, 1.0), Vec2::ZERO, Vec2::X, 0.3, 10.0));
        assert!(!in_cone(Vec2::new(5.0, 5.0), Vec2::ZERO, Vec2::X, 0.3, 10.0));
        assert!(!in_cone(Vec2::new(20.0, 0.0), Vec2::ZERO, Vec2::X, 0.3, 10.0));
    }
}
