//! The single effect vocabulary of GODFORGE.
//!
//! Parts, Sigils, Boons (incl. Duo/Legendary/Team), character trees, Forge Altar nodes and named
//! recipe bonuses are all *lists of `Modifier`s* in data. Code implements each variant exactly once:
//! weapon variants in [`crate::weapon::compile`], player variants in
//! [`crate::stats::compile_player_stats`], runtime triggers in the simulation. Adding content never
//! requires code; adding a *new kind of effect* adds one variant here.
//!
//! RON syntax examples (as written in `parts.ron` or a spreadsheet `mods` cell):
//! `Damage(1.2)`, `Ricochet(bounces: 2, range: 7.0)`,
//! `ApplyStatus(status: Burn, chance: 0.4, stacks: 1, duration: 3.0)`.

use crate::damage::DamageType;
use crate::status::StatusKind;
use crate::weapon::ProjectileStyle;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum Modifier {
    // ───── weapon scalars (× = multiplier, + = additive) ─────
    /// × weapon damage.
    Damage(f32),
    /// × shots per second.
    FireRate(f32),
    /// × projectile speed.
    ProjectileSpeed(f32),
    /// × weapon range / projectile lifetime.
    Range(f32),
    /// × every area radius the weapon produces (splash, explosions, wells, puddles).
    Area(f32),
    /// × knockback.
    Knockback(f32),
    /// + crit chance (0.05 = +5 percentage points).
    CritChance(f32),
    /// + crit multiplier (0.5 = +50% crit damage).
    CritDamage(f32),
    /// + projectiles per shot (fanned by spread).
    Projectiles(u8),
    /// + spread half-angle in degrees.
    Spread(f32),
    /// + enemies pierced.
    Pierce(u8),
    /// × charge time (charge chassis). Lower is better.
    ChargeTime(f32),

    // ───── identity (Cores) ─────
    /// Converts the weapon's damage type.
    Element(DamageType),
    /// Projectile look (client-side identity only).
    Style(ProjectileStyle),

    // ───── behaviours (Mechanisms / Cores) ─────
    /// Bounce to a new target within `range` after a hit.
    Ricochet {
        bounces: u8,
        range: f32,
    },
    /// Steer toward targets at `turn_rate` degrees/second.
    Homing {
        turn_rate: f32,
    },
    /// On first hit, split into `count` forks spread over `angle` degrees at `damage` × hit.
    Fork {
        count: u8,
        angle: f32,
        damage: f32,
    },
    /// Chain arc to `jumps` further enemies within `range`; each jump deals `falloff` × previous.
    Chain {
        jumps: u8,
        range: f32,
        falloff: f32,
    },
    /// Explode on impact for `damage` × hit in `radius`.
    Explode {
        radius: f32,
        damage: f32,
    },
    /// Impact spawns a gravity well pulling enemies in and dealing `dps` × weapon damage per second.
    GravityWell {
        radius: f32,
        pull: f32,
        duration: f32,
        dps: f32,
    },
    /// Impact leaves a puddle dealing `dps` × weapon damage per second, optionally applying a status.
    Puddle {
        radius: f32,
        duration: f32,
        dps: f32,
        #[serde(default)]
        status: Option<StatusKind>,
    },
    /// Converts the weapon into a sweeping beam of `width`.
    Beam {
        width: f32,
    },
    /// `count` sawblades orbit the wielder at `radius`, `speed` rev/s, dealing `damage` × weapon damage.
    Orbit {
        count: u8,
        radius: f32,
        speed: f32,
        damage: f32,
    },
    /// Projectiles leave a trail that damages (`dps` × weapon damage) and slows (fraction).
    Trail {
        duration: f32,
        dps: f32,
        slow: f32,
    },

    // ───── on-hit ─────
    ApplyStatus {
        status: StatusKind,
        chance: f32,
        stacks: u8,
        duration: f32,
    },
    /// Fraction of damage dealt returned as healing.
    Lifesteal(f32),

    // ───── triggers (Relics / Sigils) ─────
    /// On crit, chance to spawn a turret with this weapon at `power` × damage for `duration` s.
    SpawnTurretOnCrit {
        chance: f32,
        duration: f32,
        power: f32,
    },
    /// Every hit adds a doom stack; at `stacks` it bursts for `burst` × weapon damage.
    Doomstack {
        stacks: u8,
        burst: f32,
    },
    /// Every `every`-th shot fires an echo copy at `damage` × (Sigil: "Every 4th shot echoes").
    EchoShot {
        every: u8,
        damage: f32,
    },
    /// Kills have `chance` to explode for `damage` × weapon damage in `radius`.
    ExplodeOnKill {
        chance: f32,
        radius: f32,
        damage: f32,
    },
    /// Kills have `chance` to drop an extra Godshard.
    ShardsOnKill {
        chance: f32,
    },

    // ───── conditional damage ─────
    /// × damage against enemies at full HP (Ossian's Marked Quarry).
    DamageVsFullHp(f32),
    /// × damage against elites and bosses.
    DamageVsElites(f32),
    /// × damage against enemies afflicted by `status`.
    DamageVsStatus {
        status: StatusKind,
        mult: f32,
    },
    /// × damage while the wielder is below `threshold` HP fraction (Umbra-Rex).
    DamageWhileLowHp {
        threshold: f32,
        mult: f32,
    },
    /// Hits kill non-boss enemies below `threshold` HP fraction.
    Execute {
        threshold: f32,
    },

    // ───── player stats ─────
    /// + max HP.
    MaxHealth(f32),
    /// × move speed.
    MoveSpeed(f32),
    /// + dash charges.
    DashCharges(i8),
    /// × dash recharge time. Lower is better.
    DashRecharge(f32),
    /// × cooldown recovery speed for actives.
    CooldownRate(f32),
    /// × ultimate charge gain.
    UltCharge(f32),
    /// × incoming damage. Lower is better.
    DamageTaken(f32),
    /// + HP regenerated per second.
    Regen(f32),
    /// + shield pool (regenerates after 4 s without taking damage).
    MaxShield(f32),
    /// × pickup magnet radius.
    PickupRadius(f32),
    /// + luck (shifts part rarity rolls).
    Luck(f32),
    /// × active ability damage.
    ActiveDamage(f32),

    // ───── ability hooks ─────
    /// Ultimates leave burning ground ("Ults leave burning ground").
    UltGround {
        radius: f32,
        duration: f32,
        dps: f32,
        element: DamageType,
    },
    /// Dashing releases a nova.
    DashNova {
        radius: f32,
        damage: f32,
        element: DamageType,
        #[serde(default)]
        status: Option<StatusKind>,
    },
}

/// Scale a multiplier so that rarity always *improves* it: beneficial deltas grow by `m`,
/// detrimental trade-offs shrink by `1/m`.
#[inline]
fn scale_mult(x: f32, m: f32, higher_is_better: bool) -> f32 {
    let delta = x - 1.0;
    let beneficial = (delta > 0.0) == higher_is_better;
    if beneficial { 1.0 + delta * m } else { 1.0 + delta / m }
}

/// Scale an additive bonus where positive is good.
#[inline]
fn scale_add(x: f32, m: f32) -> f32 {
    if x >= 0.0 { x * m } else { x / m }
}

/// Scale a count: grows only at meaningful thresholds and never shrinks.
#[inline]
fn scale_count(x: u8, m: f32) -> u8 {
    ((x as f32 * m).floor() as u8).max(x)
}

/// Radii scale with sqrt so *area* scales ~linearly with rarity.
#[inline]
fn scale_radius(r: f32, m: f32) -> f32 {
    r * m.sqrt()
}

/// Durations scale gently.
#[inline]
fn scale_duration(d: f32, m: f32) -> f32 {
    d * (1.0 + (m - 1.0) * 0.5)
}

impl Modifier {
    /// Return this modifier at rarity magnitude `m` (1.0 = Common). Rarity never makes a part worse.
    pub fn scaled(&self, m: f32) -> Modifier {
        use Modifier::*;
        if (m - 1.0).abs() < f32::EPSILON {
            return self.clone();
        }
        match *self {
            Damage(x) => Damage(scale_mult(x, m, true)),
            FireRate(x) => FireRate(scale_mult(x, m, true)),
            ProjectileSpeed(x) => ProjectileSpeed(scale_mult(x, m, true)),
            Range(x) => Range(scale_mult(x, m, true)),
            Area(x) => Area(scale_mult(x, m, true)),
            Knockback(x) => Knockback(scale_mult(x, m, true)),
            CritChance(x) => CritChance(scale_add(x, m)),
            CritDamage(x) => CritDamage(scale_add(x, m)),
            Projectiles(n) => Projectiles(scale_count(n, m)),
            Spread(x) => Spread(x),
            Pierce(n) => Pierce(scale_count(n, m)),
            ChargeTime(x) => ChargeTime(scale_mult(x, m, false)),
            Element(e) => Element(e),
            Style(s) => Style(s),
            Ricochet { bounces, range } => Ricochet { bounces: scale_count(bounces, m), range: scale_radius(range, m) },
            Homing { turn_rate } => Homing { turn_rate: turn_rate * m },
            Fork { count, angle, damage } => Fork { count: scale_count(count, m), angle, damage: damage * m },
            Chain { jumps, range, falloff } => Chain {
                jumps: scale_count(jumps, m),
                range: scale_radius(range, m),
                falloff: (1.0 - (1.0 - falloff) / m).clamp(0.0, 1.0),
            },
            Explode { radius, damage } => Explode { radius: scale_radius(radius, m), damage: damage * m },
            GravityWell { radius, pull, duration, dps } => GravityWell {
                radius: scale_radius(radius, m),
                pull: pull * m.sqrt(),
                duration: scale_duration(duration, m),
                dps: dps * m,
            },
            Puddle { radius, duration, dps, status } => {
                Puddle { radius: scale_radius(radius, m), duration: scale_duration(duration, m), dps: dps * m, status }
            }
            Beam { width } => Beam { width: width * m.sqrt() },
            Orbit { count, radius, speed, damage } => {
                Orbit { count: scale_count(count, m), radius, speed, damage: damage * m }
            }
            Trail { duration, dps, slow } => {
                Trail { duration: scale_duration(duration, m), dps: dps * m, slow: (slow * m.sqrt()).min(0.8) }
            }
            ApplyStatus { status, chance, stacks, duration } => ApplyStatus {
                status,
                chance: (chance * m).min(1.0),
                stacks: scale_count(stacks, m),
                duration: scale_duration(duration, m),
            },
            Lifesteal(x) => Lifesteal(scale_add(x, m)),
            SpawnTurretOnCrit { chance, duration, power } => SpawnTurretOnCrit {
                chance: (chance * m).min(1.0),
                duration: scale_duration(duration, m),
                power: power * m,
            },
            Doomstack { stacks, burst } => Doomstack { stacks, burst: burst * m },
            EchoShot { every, damage } => EchoShot {
                every: ((every as f32 / m.sqrt()).round() as u8).clamp(2, every.max(2)),
                damage: damage * m.sqrt(),
            },
            ExplodeOnKill { chance, radius, damage } => {
                ExplodeOnKill { chance: (chance * m).min(1.0), radius: scale_radius(radius, m), damage: damage * m }
            }
            ShardsOnKill { chance } => ShardsOnKill { chance: (chance * m).min(1.0) },
            DamageVsFullHp(x) => DamageVsFullHp(scale_mult(x, m, true)),
            DamageVsElites(x) => DamageVsElites(scale_mult(x, m, true)),
            DamageVsStatus { status, mult } => DamageVsStatus { status, mult: scale_mult(mult, m, true) },
            DamageWhileLowHp { threshold, mult } => DamageWhileLowHp { threshold, mult: scale_mult(mult, m, true) },
            Execute { threshold } => Execute { threshold: (threshold * m.sqrt()).min(0.5) },
            MaxHealth(x) => MaxHealth(scale_add(x, m)),
            MoveSpeed(x) => MoveSpeed(scale_mult(x, m, true)),
            DashCharges(n) => DashCharges(if n > 0 { scale_count(n as u8, m) as i8 } else { n }),
            DashRecharge(x) => DashRecharge(scale_mult(x, m, false)),
            CooldownRate(x) => CooldownRate(scale_mult(x, m, true)),
            UltCharge(x) => UltCharge(scale_mult(x, m, true)),
            DamageTaken(x) => DamageTaken(scale_mult(x, m, false)),
            Regen(x) => Regen(scale_add(x, m)),
            MaxShield(x) => MaxShield(scale_add(x, m)),
            PickupRadius(x) => PickupRadius(scale_mult(x, m, true)),
            Luck(x) => Luck(scale_add(x, m)),
            ActiveDamage(x) => ActiveDamage(scale_mult(x, m, true)),
            UltGround { radius, duration, dps, element } => UltGround {
                radius: scale_radius(radius, m),
                duration: scale_duration(duration, m),
                dps: dps * m,
                element,
            },
            DashNova { radius, damage, element, status } => {
                DashNova { radius: scale_radius(radius, m), damage: damage * m, element, status }
            }
        }
    }

    /// True for variants that only affect the wielder's stats (not the weapon).
    pub fn is_player_stat(&self) -> bool {
        use Modifier::*;
        matches!(
            self,
            MaxHealth(_)
                | MoveSpeed(_)
                | DashCharges(_)
                | DashRecharge(_)
                | CooldownRate(_)
                | UltCharge(_)
                | DamageTaken(_)
                | Regen(_)
                | MaxShield(_)
                | PickupRadius(_)
                | Luck(_)
                | ActiveDamage(_)
                | UltGround { .. }
                | DashNova { .. }
        )
    }

    /// Short tag used by codex/recipes/UI ("ricochet", "chain", "burn", …).
    pub fn tag(&self) -> &'static str {
        use Modifier::*;
        match self {
            Damage(_) => "damage",
            FireRate(_) => "fire_rate",
            ProjectileSpeed(_) => "velocity",
            Range(_) => "range",
            Area(_) => "area",
            Knockback(_) => "knockback",
            CritChance(_) | CritDamage(_) => "crit",
            Projectiles(_) => "multishot",
            Spread(_) => "spread",
            Pierce(_) => "pierce",
            ChargeTime(_) => "charge",
            Element(_) => "element",
            Style(_) => "style",
            Ricochet { .. } => "ricochet",
            Homing { .. } => "homing",
            Fork { .. } => "fork",
            Chain { .. } => "chain",
            Explode { .. } => "explode",
            GravityWell { .. } => "gravity",
            Puddle { .. } => "puddle",
            Beam { .. } => "beam",
            Orbit { .. } => "orbit",
            Trail { .. } => "trail",
            ApplyStatus { status, .. } => match status {
                StatusKind::Burn => "burn",
                StatusKind::Shock => "shock",
                StatusKind::Curse => "curse",
                StatusKind::Root => "root",
                StatusKind::Bleed => "bleed",
                StatusKind::Mark => "mark",
            },
            Lifesteal(_) => "lifesteal",
            SpawnTurretOnCrit { .. } => "turret",
            Doomstack { .. } => "doom",
            EchoShot { .. } => "echo",
            ExplodeOnKill { .. } => "volatile",
            ShardsOnKill { .. } => "greed",
            DamageVsFullHp(_) | DamageVsElites(_) | DamageVsStatus { .. } | DamageWhileLowHp { .. } => "conditional",
            Execute { .. } => "execute",
            MaxHealth(_) | Regen(_) | MaxShield(_) | DamageTaken(_) => "survival",
            MoveSpeed(_) | DashCharges(_) | DashRecharge(_) => "mobility",
            CooldownRate(_) | UltCharge(_) | ActiveDamage(_) => "ability",
            PickupRadius(_) | Luck(_) => "fortune",
            UltGround { .. } => "ult_ground",
            DashNova { .. } => "dash_nova",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rarity_never_makes_things_worse() {
        // A part with a damage trade-off gets a *smaller* penalty at higher rarity.
        let penalty = Modifier::Damage(0.8).scaled(2.0);
        assert_eq!(penalty, Modifier::Damage(0.9));
        let bonus = Modifier::Damage(1.2).scaled(2.0);
        assert!(matches!(bonus, Modifier::Damage(x) if (x - 1.4).abs() < 1e-5));
        // Lower-is-better stats.
        assert!(matches!(Modifier::DamageTaken(0.9).scaled(2.0), Modifier::DamageTaken(x) if (x - 0.8).abs() < 1e-5));
        assert!(matches!(Modifier::ChargeTime(1.2).scaled(2.0), Modifier::ChargeTime(x) if (x - 1.1).abs() < 1e-5));
    }

    #[test]
    fn counts_step_up_at_thresholds() {
        assert_eq!(Modifier::Projectiles(1).scaled(1.3), Modifier::Projectiles(1));
        assert_eq!(Modifier::Projectiles(1).scaled(2.1), Modifier::Projectiles(2));
        assert_eq!(Modifier::Projectiles(2).scaled(1.65), Modifier::Projectiles(3));
    }

    #[test]
    fn echo_every_gets_more_frequent() {
        match (Modifier::EchoShot { every: 4, damage: 1.0 }).scaled(2.1) {
            Modifier::EchoShot { every, damage } => {
                assert_eq!(every, 3);
                assert!(damage > 1.0);
            }
            _ => unreachable!(),
        }
    }

    #[test]
    fn common_is_identity() {
        let m = Modifier::Chain { jumps: 3, range: 5.0, falloff: 0.7 };
        assert_eq!(m.scaled(1.0), m);
    }

    #[test]
    fn ron_round_trip() {
        let mods = vec![
            Modifier::Damage(1.2),
            Modifier::Ricochet { bounces: 2, range: 7.0 },
            Modifier::ApplyStatus { status: StatusKind::Burn, chance: 0.4, stacks: 1, duration: 3.0 },
            Modifier::Element(DamageType::Storm),
            Modifier::Puddle { radius: 2.0, duration: 3.0, dps: 0.3, status: None },
        ];
        let text = ron::to_string(&mods).unwrap();
        let back: Vec<Modifier> = ron::from_str(&text).unwrap();
        assert_eq!(mods, back);
        // Designer-facing syntax with an omitted optional field parses.
        let m: Modifier = ron::from_str("Puddle(radius: 2.0, duration: 3.0, dps: 0.3)").unwrap();
        assert!(matches!(m, Modifier::Puddle { status: None, .. }));
    }
}
