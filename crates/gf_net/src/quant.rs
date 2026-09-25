//! Quantization for the wire. Arena coordinates fit comfortably in ±256 world units.

use glam::Vec2;
use serde::{Deserialize, Serialize};

/// Position quantized to 1/128 world unit (±256 units range).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct QPos(pub i16, pub i16);

const POS_SCALE: f32 = 128.0;

impl QPos {
    pub fn from_vec2(v: Vec2) -> Self {
        let q = |x: f32| (x * POS_SCALE).round().clamp(i16::MIN as f32, i16::MAX as f32) as i16;
        QPos(q(v.x), q(v.y))
    }

    pub fn to_vec2(self) -> Vec2 {
        Vec2::new(self.0 as f32 / POS_SCALE, self.1 as f32 / POS_SCALE)
    }
}

/// Velocity quantized to 1/64 unit/s (±512 units/s).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct QVel(pub i16, pub i16);

const VEL_SCALE: f32 = 64.0;

impl QVel {
    pub fn from_vec2(v: Vec2) -> Self {
        let q = |x: f32| (x * VEL_SCALE).round().clamp(i16::MIN as f32, i16::MAX as f32) as i16;
        QVel(q(v.x), q(v.y))
    }

    pub fn to_vec2(self) -> Vec2 {
        Vec2::new(self.0 as f32 / VEL_SCALE, self.1 as f32 / VEL_SCALE)
    }
}

/// Direction as a 16-bit angle.
pub fn angle_to_u16(dir: Vec2) -> u16 {
    if dir.length_squared() < 1e-12 {
        return 0;
    }
    let a = dir.y.atan2(dir.x).rem_euclid(std::f32::consts::TAU);
    ((a / std::f32::consts::TAU) * 65536.0).round() as u32 as u16
}

pub fn u16_to_dir(a: u16) -> Vec2 {
    let rad = a as f32 / 65536.0 * std::f32::consts::TAU;
    Vec2::new(rad.cos(), rad.sin())
}

/// Direction as an 8-bit angle (facing, cosmetic).
pub fn angle_to_u8(dir: Vec2) -> u8 {
    (angle_to_u16(dir) >> 8) as u8
}

pub fn u8_to_dir(a: u8) -> Vec2 {
    u16_to_dir((a as u16) << 8)
}

/// Unit fraction 0..=1 → u8.
pub fn frac_to_u8(f: f32) -> u8 {
    (f.clamp(0.0, 1.0) * 255.0).round() as u8
}

pub fn u8_to_frac(v: u8) -> f32 {
    v as f32 / 255.0
}

/// Stick/move vector (length ≤ 1) → two i8.
pub fn stick_to_i8(v: Vec2) -> (i8, i8) {
    let v = v.clamp_length_max(1.0);
    ((v.x * 127.0).round() as i8, (v.y * 127.0).round() as i8)
}

pub fn i8_to_stick(v: (i8, i8)) -> Vec2 {
    Vec2::new(v.0 as f32 / 127.0, v.1 as f32 / 127.0).clamp_length_max(1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pos_round_trip_precision() {
        let v = Vec2::new(-23.456, 17.891);
        assert!((QPos::from_vec2(v).to_vec2() - v).length() < 0.01);
        // Saturates instead of wrapping.
        assert_eq!(QPos::from_vec2(Vec2::splat(1e6)).0, i16::MAX);
    }

    #[test]
    fn angles_round_trip() {
        for i in 0..64 {
            let d = gf_core::math::from_angle(i as f32 * 0.1);
            let back = u16_to_dir(angle_to_u16(d));
            assert!((back - d).length() < 1e-3);
        }
        assert_eq!(angle_to_u16(Vec2::ZERO), 0);
    }

    #[test]
    fn sticks_clamp() {
        let (x, y) = stick_to_i8(Vec2::new(3.0, 0.0));
        assert_eq!((x, y), (127, 0));
        assert!((i8_to_stick((127, 127)).length() - 1.0).abs() < 1e-5);
    }
}
