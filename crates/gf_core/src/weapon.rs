//! Weapon compilation: a chassis stat block plus a flat, canonical-ordered list of modifiers
//! (parts scaled by rarity, sigil, boons, recipe bonuses, temporary buffs) compiles into a
//! [`WeaponProfile`] — the only thing the simulation reads when a weapon fires.
//!
//! Compilation is order-independent for every variant except `Element`/`Style`/`Beam`, where the
//! caller's canonical order (chassis → core → mechanism → relic → sigil → boons) decides.

use crate::damage::{DamageType, expected_crit_factor};
use crate::modifier::Modifier;
use crate::status::{StatusKind, StatusTuning};
use serde::{Deserialize, Serialize};

/// How the trigger behaves.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum FireKind {
    /// Fires at `fire_rate` while the trigger is held.
    #[default]
    Auto,
    /// Hold to charge for `charge_time`, release to fire one shot (damage × `charge_mult` at full).
    Charge,
    /// Continuous beam ticking `fire_rate` times per second along a line.
    Beam,
    /// Short-range cone strikes at `fire_rate` (Anvil Gauntlets).
    Melee,
}

/// Client-side projectile look. Pure presentation; never affects simulation.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum ProjectileStyle {
    #[default]
    Bolt,
    Slug,
    Shell,
    Arc,
    Orb,
    Globe,
    Shard,
    Arrow,
    Pellet,
    Boulder,
    Coin,
    Fist,
    Needle,
    Blade,
}

/// Fire-rate ramp (Pendulum Repeater): rate climbs to `max_mult` × over `time_to_max` seconds of
/// continuous fire.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Ramp {
    pub max_mult: f32,
    pub time_to_max: f32,
}

fn one() -> u8 {
    1
}
fn default_radius() -> f32 {
    0.18
}
fn default_crit_chance() -> f32 {
    0.05
}
fn default_crit_mult() -> f32 {
    2.5
}
fn default_charge_mult() -> f32 {
    2.5
}
fn default_precision_zone() -> f32 {
    0.45
}

/// Chassis stat block, authored per chassis in `chassis.ron` (generated from `chassis.csv`).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ChassisStats {
    pub fire: FireKind,
    pub damage: f32,
    pub fire_rate: f32,
    #[serde(default = "one")]
    pub projectiles: u8,
    #[serde(default)]
    pub spread_deg: f32,
    pub speed: f32,
    pub range: f32,
    #[serde(default = "default_radius")]
    pub radius: f32,
    #[serde(default)]
    pub pierce: u8,
    #[serde(default)]
    pub knockback: f32,
    #[serde(default = "default_crit_chance")]
    pub crit_chance: f32,
    #[serde(default = "default_crit_mult")]
    pub crit_mult: f32,
    #[serde(default)]
    pub charge_time: f32,
    #[serde(default = "default_charge_mult")]
    pub charge_mult: f32,
    /// Built-in splash (Colossus Cannon shells): radius and fraction of hit damage.
    #[serde(default)]
    pub splash_radius: f32,
    #[serde(default)]
    pub splash_damage: f32,
    #[serde(default)]
    pub damage_type: DamageType,
    #[serde(default)]
    pub style: ProjectileStyle,
    /// Manual-mode perfect-hit zone as a fraction of the target radius.
    #[serde(default = "default_precision_zone")]
    pub precision_zone: f32,
    #[serde(default)]
    pub ramp: Option<Ramp>,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Splash {
    pub radius: f32,
    pub damage: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct RicochetFx {
    pub bounces: u8,
    pub range: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct ForkFx {
    pub count: u8,
    pub angle: f32,
    pub damage: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct ChainFx {
    pub jumps: u8,
    pub range: f32,
    pub falloff: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct WellFx {
    pub radius: f32,
    pub pull: f32,
    pub duration: f32,
    pub dps: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct PuddleFx {
    pub radius: f32,
    pub duration: f32,
    pub dps: f32,
    pub status: Option<StatusKind>,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct OrbitFx {
    pub count: u8,
    pub radius: f32,
    pub speed: f32,
    pub damage: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct TrailFx {
    pub duration: f32,
    pub dps: f32,
    pub slow: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct StatusApply {
    pub status: StatusKind,
    pub chance: f32,
    pub stacks: u8,
    pub duration: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct TurretFx {
    pub chance: f32,
    pub duration: f32,
    pub power: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct DoomFx {
    pub stacks: u8,
    pub burst: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct EchoFx {
    pub every: u8,
    pub damage: f32,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct KillBlastFx {
    pub chance: f32,
    pub radius: f32,
    pub damage: f32,
}

/// Everything the simulation needs to fire and resolve a weapon.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct WeaponProfile {
    pub fire: FireKind,
    pub element: DamageType,
    pub style: ProjectileStyle,
    pub damage: f32,
    pub fire_rate: f32,
    pub projectiles: u8,
    pub spread_deg: f32,
    pub speed: f32,
    pub range: f32,
    pub radius: f32,
    pub pierce: u8,
    pub knockback: f32,
    pub crit_chance: f32,
    pub crit_mult: f32,
    pub charge_time: f32,
    pub charge_mult: f32,
    pub precision_zone: f32,
    pub ramp: Option<Ramp>,
    pub area_mult: f32,
    pub splash: Option<Splash>,
    pub ricochet: Option<RicochetFx>,
    /// Homing turn rate in radians/second (0 = none).
    pub homing: f32,
    pub fork: Option<ForkFx>,
    pub chain: Option<ChainFx>,
    pub explode: Option<Splash>,
    pub gravity_well: Option<WellFx>,
    pub puddle: Option<PuddleFx>,
    pub beam_width: Option<f32>,
    pub orbit: Option<OrbitFx>,
    pub trail: Option<TrailFx>,
    pub on_hit: Vec<StatusApply>,
    pub lifesteal: f32,
    pub turret_on_crit: Option<TurretFx>,
    pub doomstack: Option<DoomFx>,
    pub echo_shot: Option<EchoFx>,
    pub explode_on_kill: Option<KillBlastFx>,
    pub shards_on_kill: f32,
    pub vs_full_hp: f32,
    pub vs_elites: f32,
    pub vs_status: Vec<(StatusKind, f32)>,
    pub low_hp: Option<(f32, f32)>,
    pub execute: f32,
}

impl WeaponProfile {
    /// Seconds between shots (or beam ticks).
    #[inline]
    pub fn shot_interval(&self) -> f32 {
        1.0 / self.fire_rate.max(0.01)
    }

    /// Projectile lifetime implied by range and speed.
    #[inline]
    pub fn lifetime(&self) -> f32 {
        if self.speed > 0.0 { self.range / self.speed } else { 0.0 }
    }

    /// Effective fire kind (a Beam mechanism converts any chassis into a beam).
    #[inline]
    pub fn effective_fire(&self) -> FireKind {
        if self.beam_width.is_some() && self.fire != FireKind::Melee { FireKind::Beam } else { self.fire }
    }

    /// Situational multiplier for a hit against a target (conditionals from parts/boons).
    pub fn conditional_mult(
        &self,
        target_full_hp: bool,
        target_elite: bool,
        target_status_bits: u8,
        wielder_hp_frac: f32,
    ) -> f32 {
        let mut m = 1.0;
        if target_full_hp {
            m *= self.vs_full_hp;
        }
        if target_elite {
            m *= self.vs_elites;
        }
        for (status, mult) in &self.vs_status {
            if target_status_bits & status.bit() != 0 {
                m *= *mult;
            }
        }
        if let Some((threshold, mult)) = self.low_hp
            && wielder_hp_frac < threshold
        {
            m *= mult;
        }
        m
    }
}

#[inline]
fn merge_opt<T: Copy>(slot: &mut Option<T>, incoming: T, merge: impl FnOnce(T, T) -> T) {
    *slot = Some(match *slot {
        Some(existing) => merge(existing, incoming),
        None => incoming,
    });
}

/// Compile a chassis and modifiers into a weapon profile.
pub fn compile<'a>(chassis: &ChassisStats, mods: impl IntoIterator<Item = &'a Modifier>) -> WeaponProfile {
    let mut p = WeaponProfile {
        fire: chassis.fire,
        element: chassis.damage_type,
        style: chassis.style,
        damage: chassis.damage,
        fire_rate: chassis.fire_rate,
        projectiles: chassis.projectiles.max(1),
        spread_deg: chassis.spread_deg,
        speed: chassis.speed,
        range: chassis.range,
        radius: chassis.radius,
        pierce: chassis.pierce,
        knockback: chassis.knockback,
        crit_chance: chassis.crit_chance,
        crit_mult: chassis.crit_mult,
        charge_time: chassis.charge_time,
        charge_mult: chassis.charge_mult,
        precision_zone: chassis.precision_zone,
        ramp: chassis.ramp,
        area_mult: 1.0,
        splash: (chassis.splash_radius > 0.0 && chassis.splash_damage > 0.0)
            .then_some(Splash { radius: chassis.splash_radius, damage: chassis.splash_damage }),
        ricochet: None,
        homing: 0.0,
        fork: None,
        chain: None,
        explode: None,
        gravity_well: None,
        puddle: None,
        beam_width: None,
        orbit: None,
        trail: None,
        on_hit: Vec::new(),
        lifesteal: 0.0,
        turret_on_crit: None,
        doomstack: None,
        echo_shot: None,
        explode_on_kill: None,
        shards_on_kill: 0.0,
        vs_full_hp: 1.0,
        vs_elites: 1.0,
        vs_status: Vec::new(),
        low_hp: None,
        execute: 0.0,
    };

    for m in mods {
        use Modifier::*;
        match *m {
            Damage(x) => p.damage *= x,
            FireRate(x) => p.fire_rate *= x,
            ProjectileSpeed(x) => p.speed *= x,
            Range(x) => p.range *= x,
            Area(x) => p.area_mult *= x,
            Knockback(x) => p.knockback *= x,
            CritChance(x) => p.crit_chance += x,
            CritDamage(x) => p.crit_mult += x,
            Projectiles(n) => p.projectiles = p.projectiles.saturating_add(n),
            Spread(x) => p.spread_deg += x,
            Pierce(n) => p.pierce = p.pierce.saturating_add(n),
            ChargeTime(x) => p.charge_time *= x,
            Element(e) => p.element = e,
            Style(s) => p.style = s,
            Ricochet { bounces, range } => merge_opt(&mut p.ricochet, RicochetFx { bounces, range }, |a, b| {
                RicochetFx { bounces: a.bounces.saturating_add(b.bounces), range: a.range.max(b.range) }
            }),
            Homing { turn_rate } => p.homing += turn_rate.to_radians(),
            Fork { count, angle, damage } => merge_opt(&mut p.fork, ForkFx { count, angle, damage }, |a, b| ForkFx {
                count: a.count.saturating_add(b.count),
                angle: a.angle.max(b.angle),
                damage: a.damage.max(b.damage),
            }),
            Chain { jumps, range, falloff } => {
                merge_opt(&mut p.chain, ChainFx { jumps, range, falloff }, |a, b| ChainFx {
                    jumps: a.jumps.saturating_add(b.jumps),
                    range: a.range.max(b.range),
                    falloff: a.falloff.max(b.falloff),
                })
            }
            Explode { radius, damage } => merge_opt(&mut p.explode, Splash { radius, damage }, |a, b| Splash {
                radius: a.radius.max(b.radius),
                damage: a.damage + b.damage,
            }),
            GravityWell { radius, pull, duration, dps } => {
                merge_opt(&mut p.gravity_well, WellFx { radius, pull, duration, dps }, |a, b| WellFx {
                    radius: a.radius.max(b.radius),
                    pull: a.pull + b.pull,
                    duration: a.duration.max(b.duration),
                    dps: a.dps + b.dps,
                })
            }
            Puddle { radius, duration, dps, status } => {
                merge_opt(&mut p.puddle, PuddleFx { radius, duration, dps, status }, |a, b| PuddleFx {
                    radius: a.radius.max(b.radius),
                    duration: a.duration.max(b.duration),
                    dps: a.dps + b.dps,
                    status: a.status.or(b.status),
                })
            }
            Beam { width } => p.beam_width = Some(p.beam_width.map_or(width, |w| w.max(width))),
            Orbit { count, radius, speed, damage } => {
                merge_opt(&mut p.orbit, OrbitFx { count, radius, speed, damage }, |a, b| OrbitFx {
                    count: a.count.saturating_add(b.count),
                    radius: a.radius.max(b.radius),
                    speed: a.speed.max(b.speed),
                    damage: a.damage.max(b.damage),
                })
            }
            Trail { duration, dps, slow } => merge_opt(&mut p.trail, TrailFx { duration, dps, slow }, |a, b| TrailFx {
                duration: a.duration.max(b.duration),
                dps: a.dps + b.dps,
                slow: a.slow.max(b.slow),
            }),
            ApplyStatus { status, chance, stacks, duration } => {
                if let Some(existing) = p.on_hit.iter_mut().find(|s| s.status == status) {
                    // Independent sources combine: 1 - (1-a)(1-b).
                    existing.chance = 1.0 - (1.0 - existing.chance) * (1.0 - chance);
                    existing.stacks = existing.stacks.max(stacks);
                    existing.duration = existing.duration.max(duration);
                } else {
                    p.on_hit.push(StatusApply { status, chance, stacks, duration });
                }
            }
            Lifesteal(x) => p.lifesteal += x,
            SpawnTurretOnCrit { chance, duration, power } => {
                merge_opt(&mut p.turret_on_crit, TurretFx { chance, duration, power }, |a, b| TurretFx {
                    chance: (a.chance + b.chance).min(1.0),
                    duration: a.duration.max(b.duration),
                    power: a.power.max(b.power),
                })
            }
            Doomstack { stacks, burst } => merge_opt(&mut p.doomstack, DoomFx { stacks, burst }, |a, b| DoomFx {
                stacks: a.stacks.min(b.stacks).max(2),
                burst: a.burst + b.burst,
            }),
            EchoShot { every, damage } => merge_opt(&mut p.echo_shot, EchoFx { every, damage }, |a, b| EchoFx {
                every: a.every.min(b.every).max(2),
                damage: a.damage.max(b.damage),
            }),
            ExplodeOnKill { chance, radius, damage } => {
                merge_opt(&mut p.explode_on_kill, KillBlastFx { chance, radius, damage }, |a, b| KillBlastFx {
                    chance: (a.chance + b.chance).min(1.0),
                    radius: a.radius.max(b.radius),
                    damage: a.damage + b.damage,
                })
            }
            ShardsOnKill { chance } => p.shards_on_kill = (p.shards_on_kill + chance).min(1.0),
            DamageVsFullHp(x) => p.vs_full_hp *= x,
            DamageVsElites(x) => p.vs_elites *= x,
            DamageVsStatus { status, mult } => {
                if let Some(e) = p.vs_status.iter_mut().find(|(s, _)| *s == status) {
                    e.1 *= mult;
                } else {
                    p.vs_status.push((status, mult));
                }
            }
            DamageWhileLowHp { threshold, mult } => {
                p.low_hp = Some(match p.low_hp {
                    Some((t, m)) => (t.max(threshold), m * mult),
                    None => (threshold, mult),
                })
            }
            Execute { threshold } => p.execute = p.execute.max(threshold),
            // Player-stat modifiers are compiled by `stats::compile_player_stats`.
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
            | DashNova { .. } => {}
        }
    }

    // Canonical ordering so equal builds compare equal regardless of modifier order.
    p.on_hit.sort_by_key(|s| s.status);
    p.vs_status.sort_by_key(|(s, _)| *s);

    // Sanity clamps: broken-but-fun, never NaN or negative.
    p.damage = p.damage.max(0.0);
    p.fire_rate = p.fire_rate.clamp(0.05, 60.0);
    p.speed = p.speed.max(0.0);
    p.range = p.range.max(0.5);
    p.crit_chance = p.crit_chance.clamp(0.0, 1.0);
    p.crit_mult = p.crit_mult.max(1.0);
    p.charge_time = p.charge_time.max(0.0);
    p.spread_deg = p.spread_deg.clamp(0.0, 180.0);
    p.lifesteal = p.lifesteal.clamp(0.0, 0.5);
    p.projectiles = p.projectiles.min(32);
    p.area_mult = p.area_mult.max(0.1);
    // Area scaling applies to every radius the weapon produces.
    let a = p.area_mult;
    if let Some(s) = &mut p.splash {
        s.radius *= a;
    }
    if let Some(s) = &mut p.explode {
        s.radius *= a;
    }
    if let Some(w) = &mut p.gravity_well {
        w.radius *= a;
    }
    if let Some(pd) = &mut p.puddle {
        pd.radius *= a;
    }
    if let Some(ok) = &mut p.explode_on_kill {
        ok.radius *= a;
    }
    p
}

/// Assumptions for the forge preview's DPS estimate.
#[derive(Clone, Debug, PartialEq)]
pub struct DpsEnv {
    /// Expected number of *additional* enemies near any hit (horde density).
    pub crowd_density: f32,
    pub status: StatusTuning,
}

impl Default for DpsEnv {
    fn default() -> Self {
        Self { crowd_density: 2.5, status: StatusTuning::default() }
    }
}

/// Forge preview numbers ("UI must show resulting DPS/behavior preview before committing").
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct DpsEstimate {
    /// Expected damage of one projectile hit including crits.
    pub per_hit: f32,
    /// Shots (or beam ticks / swings) per second.
    pub shots_per_sec: f32,
    /// Sustained DPS against one target.
    pub single_target: f32,
    /// Sustained DPS against a horde (multi-hit behaviours, AoE).
    pub crowd: f32,
    /// Healing per second from lifesteal at single-target DPS.
    pub sustain: f32,
}

/// Heuristic DPS estimate. Relative accuracy matters (comparing forge options); absolute numbers are
/// validated against the headless bot-run telemetry.
pub fn estimate_dps(p: &WeaponProfile, env: &DpsEnv) -> DpsEstimate {
    let cf = expected_crit_factor(p.crit_chance, p.crit_mult);
    let mut per_hit = p.damage * cf;
    let fire = p.effective_fire();
    let shots_per_sec = match fire {
        FireKind::Charge => 1.0 / (p.charge_time + p.shot_interval()),
        _ => {
            let ramp = p.ramp.map_or(1.0, |r| (1.0 + r.max_mult) * 0.5);
            p.fire_rate * ramp
        }
    };
    if fire == FireKind::Charge {
        per_hit *= p.charge_mult;
    }
    // Fraction of a fan of pellets that lands on a single target.
    let pellet_frac = if p.spread_deg <= 8.0 { 1.0 } else { (8.0 / p.spread_deg).clamp(0.3, 1.0) };
    let pellets_single = 1.0 + (p.projectiles as f32 - 1.0) * pellet_frac;
    let mut single = per_hit * pellets_single * shots_per_sec;

    // Echo shots.
    if let Some(e) = p.echo_shot {
        single *= 1.0 + e.damage / e.every.max(2) as f32;
    }
    // Doom bursts.
    if let Some(d) = p.doomstack {
        single += p.damage * d.burst * (pellets_single * shots_per_sec) / d.stacks.max(1) as f32;
    }
    // Status contributions.
    let hits_per_sec = pellets_single * shots_per_sec;
    let mut dot = 0.0;
    let mut dmg_taken_mult = 1.0;
    for s in &p.on_hit {
        let apply_rate = s.chance.clamp(0.0, 1.0) * hits_per_sec;
        match s.status {
            StatusKind::Burn => {
                let stacks = (apply_rate * s.duration).min(env.status.burn_max_stacks as f32);
                dot += per_hit * env.status.burn_dps_ratio * stacks;
            }
            StatusKind::Bleed => {
                let stacks = (apply_rate * s.duration).min(env.status.bleed_max_stacks as f32);
                dot += per_hit * env.status.bleed_dps_ratio * stacks * 1.3;
            }
            StatusKind::Shock => {
                let per_discharge = per_hit * env.status.shock_discharge_ratio;
                dot += per_discharge * apply_rate * s.stacks.max(1) as f32 / env.status.shock_threshold.max(1) as f32;
            }
            StatusKind::Curse => {
                let stacks = (apply_rate * s.duration).min(env.status.curse_max_stacks as f32);
                dmg_taken_mult *= 1.0 + env.status.curse_damage_taken_per_stack * stacks;
            }
            StatusKind::Mark => {
                let uptime = (apply_rate * s.duration).min(1.0);
                let bonus =
                    expected_crit_factor((p.crit_chance + env.status.mark_crit_chance).min(1.0), p.crit_mult) / cf;
                dmg_taken_mult *= 1.0 + (bonus - 1.0) * uptime;
            }
            StatusKind::Root => {}
        }
    }
    for (_, mult) in &p.vs_status {
        dmg_taken_mult *= 1.0 + (mult - 1.0) * 0.5;
    }
    single = (single + dot) * dmg_taken_mult;

    // Crowd multipliers.
    let density = env.crowd_density.max(0.0);
    let pellets_crowd = p.projectiles as f32;
    let mut crowd_hits = pellets_crowd / pellets_single.max(1.0);
    crowd_hits *= 1.0 + (p.pierce as f32 * 0.6).min(density);
    if let Some(r) = p.ricochet {
        crowd_hits *= 1.0 + (r.bounces as f32 * 0.7).min(density + 1.0);
    }
    let mut crowd = single * crowd_hits;
    if let Some(c) = p.chain {
        let mut jump_total = 0.0;
        let mut f = 1.0;
        for _ in 0..c.jumps.min(density.ceil() as u8 + 2) {
            f *= c.falloff;
            jump_total += f;
        }
        crowd += single * jump_total * 0.85;
    }
    if let Some(fk) = p.fork {
        crowd += single * fk.count as f32 * fk.damage * 0.6;
    }
    let area_targets = |radius: f32| (radius * radius * 0.35 * density).min(density * 2.0 + 1.0);
    for s in [p.splash, p.explode].into_iter().flatten() {
        crowd += per_hit * s.damage * hits_per_sec * area_targets(s.radius);
    }
    if let Some(w) = p.gravity_well {
        crowd += p.damage * w.dps * area_targets(w.radius) * (w.duration * hits_per_sec).min(3.0);
    }
    if let Some(pd) = p.puddle {
        crowd += p.damage * pd.dps * area_targets(pd.radius) * (pd.duration * hits_per_sec).min(3.0);
    }
    if let Some(o) = p.orbit {
        let orbit = p.damage * o.damage * o.count as f32 * 2.0;
        crowd += orbit * density.min(3.0);
        single += orbit * 0.5;
    }
    if let Some(t) = p.trail {
        crowd += p.damage * t.dps * density.min(4.0);
    }
    if let Some(k) = p.explode_on_kill {
        crowd += p.damage * k.damage * k.chance * area_targets(k.radius) * 0.5;
    }
    let crowd = crowd.max(single);
    DpsEstimate { per_hit, shots_per_sec, single_target: single, crowd, sustain: single * p.lifesteal }
}

/// Human-readable behaviour summary for HUD / forge UI / codex ("I had chain-lightning ricochet
/// with vampire" — acceptance criterion #2).
pub fn describe(p: &WeaponProfile) -> Vec<String> {
    let mut out = Vec::new();
    out.push(p.element.name().to_string());
    match p.effective_fire() {
        FireKind::Charge => out.push("Charge shot".into()),
        FireKind::Beam => out.push("Beam".into()),
        FireKind::Melee => out.push("Melee".into()),
        FireKind::Auto => {}
    }
    if p.projectiles > 1 {
        out.push(format!("×{} projectiles", p.projectiles));
    }
    if p.pierce > 0 {
        out.push(format!("Pierce {}", p.pierce));
    }
    if let Some(r) = p.ricochet {
        out.push(format!("Ricochet {}", r.bounces));
    }
    if p.homing > 0.0 {
        out.push("Homing".into());
    }
    if let Some(f) = p.fork {
        out.push(format!("Fork ×{}", f.count));
    }
    if let Some(c) = p.chain {
        out.push(format!("Chain arc ×{}", c.jumps));
    }
    if p.splash.is_some() || p.explode.is_some() {
        out.push("Explosive".into());
    }
    if p.gravity_well.is_some() {
        out.push("Gravity wells".into());
    }
    if p.puddle.is_some() {
        out.push("Puddles".into());
    }
    if let Some(o) = p.orbit {
        out.push(format!("{} orbiting blades", o.count));
    }
    if p.trail.is_some() {
        out.push("Frost trails".into());
    }
    for s in &p.on_hit {
        out.push(format!("{} {:.0}%", s.status.name(), s.chance.min(1.0) * 100.0));
    }
    if p.lifesteal > 0.0 {
        out.push(format!("Lifesteal {:.0}%", p.lifesteal * 100.0));
    }
    if p.turret_on_crit.is_some() {
        out.push("Crits spawn turrets".into());
    }
    if let Some(d) = p.doomstack {
        out.push(format!("Doom bursts every {} hits", d.stacks));
    }
    if let Some(e) = p.echo_shot {
        out.push(format!("Every {}th shot echoes", e.every));
    }
    if p.explode_on_kill.is_some() {
        out.push("Volatile kills".into());
    }
    if p.execute > 0.0 {
        out.push(format!("Execute <{:.0}%", p.execute * 100.0));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    pub(crate) fn cannon() -> ChassisStats {
        ChassisStats {
            fire: FireKind::Auto,
            damage: 30.0,
            fire_rate: 2.0,
            projectiles: 1,
            spread_deg: 2.0,
            speed: 18.0,
            range: 14.0,
            radius: 0.3,
            pierce: 0,
            knockback: 2.0,
            crit_chance: 0.05,
            crit_mult: 2.5,
            charge_time: 0.0,
            charge_mult: 2.5,
            splash_radius: 1.5,
            splash_damage: 0.5,
            damage_type: DamageType::Kinetic,
            style: ProjectileStyle::Shell,
            precision_zone: 0.45,
            ramp: None,
        }
    }

    #[test]
    fn scalars_compose() {
        let mods = [Modifier::Damage(1.5), Modifier::FireRate(1.2), Modifier::CritChance(0.1)];
        let p = compile(&cannon(), &mods);
        assert!((p.damage - 45.0).abs() < 1e-4);
        assert!((p.fire_rate - 2.4).abs() < 1e-4);
        assert!((p.crit_chance - 0.15).abs() < 1e-4);
    }

    #[test]
    fn compile_is_order_independent() {
        let a = [
            Modifier::Damage(1.2),
            Modifier::Ricochet { bounces: 2, range: 6.0 },
            Modifier::Chain { jumps: 3, range: 5.0, falloff: 0.7 },
            Modifier::ApplyStatus { status: StatusKind::Burn, chance: 0.3, stacks: 1, duration: 3.0 },
            Modifier::Ricochet { bounces: 1, range: 8.0 },
            Modifier::ApplyStatus { status: StatusKind::Burn, chance: 0.5, stacks: 2, duration: 2.0 },
            Modifier::FireRate(0.8),
        ];
        let mut b = a.clone();
        b.reverse();
        assert_eq!(compile(&cannon(), &a), compile(&cannon(), &b));
        let p = compile(&cannon(), &a);
        assert_eq!(p.ricochet, Some(RicochetFx { bounces: 3, range: 8.0 }));
        let burn = p.on_hit[0];
        assert!((burn.chance - 0.65).abs() < 1e-4, "1-(0.7*0.5) = 0.65");
        assert_eq!(burn.stacks, 2);
    }

    #[test]
    fn element_follows_canonical_order() {
        let p = compile(&cannon(), &[Modifier::Element(DamageType::Flame)]);
        assert_eq!(p.element, DamageType::Flame);
    }

    #[test]
    fn beam_converts_fire_kind() {
        let p = compile(&cannon(), &[Modifier::Beam { width: 0.5 }]);
        assert_eq!(p.effective_fire(), FireKind::Beam);
    }

    #[test]
    fn area_scales_all_radii() {
        let p = compile(&cannon(), &[Modifier::Area(2.0), Modifier::Explode { radius: 1.0, damage: 0.5 }]);
        assert!((p.splash.unwrap().radius - 3.0).abs() < 1e-4);
        assert!((p.explode.unwrap().radius - 2.0).abs() < 1e-4);
    }

    #[test]
    fn dps_preview_moves_the_right_way() {
        let env = DpsEnv::default();
        let base = estimate_dps(&compile(&cannon(), &[]), &env);
        let more_dmg = estimate_dps(&compile(&cannon(), &[Modifier::Damage(1.2)]), &env);
        assert!((more_dmg.single_target / base.single_target - 1.2).abs() < 1e-3);
        let multishot = estimate_dps(&compile(&cannon(), &[Modifier::Projectiles(2), Modifier::Spread(15.0)]), &env);
        assert!(multishot.crowd > base.crowd);
        let chain = estimate_dps(&compile(&cannon(), &[Modifier::Chain { jumps: 3, range: 5.0, falloff: 0.7 }]), &env);
        assert!(chain.crowd > base.crowd);
        assert!((chain.single_target - base.single_target).abs() < 1e-3);
        let vamp = estimate_dps(&compile(&cannon(), &[Modifier::Lifesteal(0.05)]), &env);
        assert!(vamp.sustain > 0.0);
        let burn = estimate_dps(
            &compile(
                &cannon(),
                &[Modifier::ApplyStatus { status: StatusKind::Burn, chance: 1.0, stacks: 1, duration: 3.0 }],
            ),
            &env,
        );
        assert!(burn.single_target > base.single_target);
        assert!(base.crowd >= base.single_target);
    }

    #[test]
    fn charge_weapons_account_for_charge() {
        let mut rail = cannon();
        rail.fire = FireKind::Charge;
        rail.charge_time = 1.0;
        rail.fire_rate = 2.0;
        let d = estimate_dps(&compile(&rail, &[]), &DpsEnv::default());
        assert!((d.shots_per_sec - 1.0 / 1.5).abs() < 1e-4);
    }

    #[test]
    fn describe_lists_behaviours() {
        let p = compile(
            &cannon(),
            &[
                Modifier::Element(DamageType::Storm),
                Modifier::Chain { jumps: 3, range: 5.0, falloff: 0.7 },
                Modifier::Ricochet { bounces: 2, range: 6.0 },
                Modifier::Lifesteal(0.05),
            ],
        );
        let d = describe(&p);
        assert!(d.contains(&"Storm".to_string()));
        assert!(d.iter().any(|s| s.starts_with("Chain arc")));
        assert!(d.iter().any(|s| s.starts_with("Ricochet")));
        assert!(d.iter().any(|s| s.starts_with("Lifesteal")));
    }

    #[test]
    fn clamps_hold_under_absurd_builds() {
        let mods: Vec<_> = (0..40).map(|_| Modifier::FireRate(3.0)).collect();
        let p = compile(&cannon(), &mods);
        assert!(p.fire_rate <= 60.0);
        let p = compile(&cannon(), &[Modifier::Lifesteal(5.0), Modifier::CritChance(10.0)]);
        assert_eq!(p.lifesteal, 0.5);
        assert_eq!(p.crit_chance, 1.0);
    }
}
