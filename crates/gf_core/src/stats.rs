//! Player stat compilation: character base stats + modifiers (boons, sigil, tree, altar, buffs).

use crate::damage::DamageType;
use crate::modifier::Modifier;
use crate::status::StatusKind;
use serde::{Deserialize, Serialize};

/// Per-character base stats, authored in `characters.ron`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CharacterBaseStats {
    pub max_hp: f32,
    pub move_speed: f32,
    #[serde(default = "two")]
    pub dash_charges: u8,
    #[serde(default = "dash_recharge")]
    pub dash_recharge: f32,
    #[serde(default = "radius")]
    pub radius: f32,
    /// Ultimate charge gained per point of damage dealt (the ult needs 1.0).
    #[serde(default = "ult_per_damage")]
    pub ult_per_damage: f32,
}

fn two() -> u8 {
    2
}
fn dash_recharge() -> f32 {
    1.1
}
fn radius() -> f32 {
    0.45
}
fn ult_per_damage() -> f32 {
    1.0 / 2500.0
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct UltGroundFx {
    pub radius: f32,
    pub duration: f32,
    pub dps: f32,
    pub element: DamageType,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct DashNovaFx {
    pub radius: f32,
    pub damage: f32,
    pub element: DamageType,
    pub status: Option<StatusKind>,
}

/// Compiled player stats. Recompiled whenever the modifier set changes.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PlayerStats {
    pub max_hp: f32,
    pub move_speed: f32,
    pub dash_charges: u8,
    pub dash_recharge: f32,
    pub radius: f32,
    pub cooldown_rate: f32,
    pub ult_per_damage: f32,
    pub damage_taken: f32,
    pub regen: f32,
    pub max_shield: f32,
    pub pickup_radius: f32,
    pub luck: f32,
    pub active_damage: f32,
    pub ult_ground: Option<UltGroundFx>,
    pub dash_nova: Option<DashNovaFx>,
}

/// Base pickup magnet radius in world units.
pub const BASE_PICKUP_RADIUS: f32 = 2.5;

pub fn compile_player_stats<'a>(
    base: &CharacterBaseStats,
    mods: impl IntoIterator<Item = &'a Modifier>,
) -> PlayerStats {
    let mut s = PlayerStats {
        max_hp: base.max_hp,
        move_speed: base.move_speed,
        dash_charges: base.dash_charges,
        dash_recharge: base.dash_recharge,
        radius: base.radius,
        cooldown_rate: 1.0,
        ult_per_damage: base.ult_per_damage,
        damage_taken: 1.0,
        regen: 0.0,
        max_shield: 0.0,
        pickup_radius: BASE_PICKUP_RADIUS,
        luck: 0.0,
        active_damage: 1.0,
        ult_ground: None,
        dash_nova: None,
    };
    let mut dash_delta: i32 = 0;
    for m in mods {
        use Modifier::*;
        match *m {
            MaxHealth(x) => s.max_hp += x,
            MoveSpeed(x) => s.move_speed *= x,
            DashCharges(n) => dash_delta += n as i32,
            DashRecharge(x) => s.dash_recharge *= x,
            CooldownRate(x) => s.cooldown_rate *= x,
            UltCharge(x) => s.ult_per_damage *= x,
            DamageTaken(x) => s.damage_taken *= x,
            Regen(x) => s.regen += x,
            MaxShield(x) => s.max_shield += x,
            PickupRadius(x) => s.pickup_radius *= x,
            Luck(x) => s.luck += x,
            ActiveDamage(x) => s.active_damage *= x,
            UltGround { radius, duration, dps, element } => {
                s.ult_ground = Some(match s.ult_ground {
                    Some(g) => UltGroundFx {
                        radius: g.radius.max(radius),
                        duration: g.duration.max(duration),
                        dps: g.dps + dps,
                        element: g.element,
                    },
                    None => UltGroundFx { radius, duration, dps, element },
                })
            }
            DashNova { radius, damage, element, status } => {
                s.dash_nova = Some(match s.dash_nova {
                    Some(n) => DashNovaFx {
                        radius: n.radius.max(radius),
                        damage: n.damage + damage,
                        element: n.element,
                        status: n.status.or(status),
                    },
                    None => DashNovaFx { radius, damage, element, status },
                })
            }
            _ => {}
        }
    }
    s.dash_charges = (base.dash_charges as i32 + dash_delta).clamp(0, 6) as u8;
    s.max_hp = s.max_hp.max(1.0);
    s.move_speed = s.move_speed.clamp(1.0, 30.0);
    s.dash_recharge = s.dash_recharge.max(0.15);
    s.cooldown_rate = s.cooldown_rate.clamp(0.25, 5.0);
    s.damage_taken = s.damage_taken.clamp(0.1, 5.0);
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> CharacterBaseStats {
        CharacterBaseStats {
            max_hp: 200.0,
            move_speed: 6.0,
            dash_charges: 2,
            dash_recharge: 1.0,
            radius: 0.5,
            ult_per_damage: 0.001,
        }
    }

    #[test]
    fn stats_compile() {
        let mods = [
            Modifier::MaxHealth(50.0),
            Modifier::MoveSpeed(1.1),
            Modifier::DashCharges(1),
            Modifier::DamageTaken(0.9),
            Modifier::Damage(5.0), // weapon-only, ignored here
        ];
        let s = compile_player_stats(&base(), &mods);
        assert_eq!(s.max_hp, 250.0);
        assert!((s.move_speed - 6.6).abs() < 1e-4);
        assert_eq!(s.dash_charges, 3);
        assert!((s.damage_taken - 0.9).abs() < 1e-4);
    }

    #[test]
    fn dash_charges_never_underflow() {
        let s = compile_player_stats(&base(), &[Modifier::DashCharges(-5)]);
        assert_eq!(s.dash_charges, 0);
    }
}
