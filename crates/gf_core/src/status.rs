//! The six status effects: Burn, Shock, Curse, Root, Bleed, Mark.
//!
//! A [`StatusSet`] is a fixed-size array (no allocation) so 400 enemies can carry one each.

use crate::damage::DamageType;
use crate::ids::SourceId;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum StatusKind {
    /// Flame damage over time; stacks intensity.
    Burn,
    /// Builds stacks; at the threshold it discharges Storm damage around the target and stuns it.
    Shock,
    /// Target takes increased damage from every source.
    Curse,
    /// Target cannot move.
    Root,
    /// Kinetic damage over time that ticks harder while the target moves.
    Bleed,
    /// Hits against the target gain crit chance (Kael / Ossian executes key off this).
    Mark,
}

impl StatusKind {
    pub const COUNT: usize = 6;
    pub const ALL: [StatusKind; 6] =
        [StatusKind::Burn, StatusKind::Shock, StatusKind::Curse, StatusKind::Root, StatusKind::Bleed, StatusKind::Mark];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    #[inline]
    pub const fn bit(self) -> u8 {
        1 << (self as u8)
    }

    pub const fn name(self) -> &'static str {
        match self {
            StatusKind::Burn => "Burn",
            StatusKind::Shock => "Shock",
            StatusKind::Curse => "Curse",
            StatusKind::Root => "Root",
            StatusKind::Bleed => "Bleed",
            StatusKind::Mark => "Mark",
        }
    }

    /// The element a status "counts as" for synergy bookkeeping, if any.
    pub const fn element(self) -> Option<DamageType> {
        match self {
            StatusKind::Burn => Some(DamageType::Flame),
            StatusKind::Shock => Some(DamageType::Storm),
            StatusKind::Curse => Some(DamageType::Void),
            StatusKind::Bleed => Some(DamageType::Kinetic),
            StatusKind::Root | StatusKind::Mark => None,
        }
    }
}

/// Status tuning. Authored in `statuses.ron`; defaults mirror the shipped values.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct StatusTuning {
    /// Burn DPS per stack as a fraction of the applying hit's damage.
    pub burn_dps_ratio: f32,
    pub burn_max_stacks: u8,
    pub bleed_dps_ratio: f32,
    pub bleed_moving_mult: f32,
    pub bleed_max_stacks: u8,
    pub shock_threshold: u8,
    /// Discharge damage as a multiple of the stored potency.
    pub shock_discharge_ratio: f32,
    pub shock_radius: f32,
    pub shock_stun: f32,
    pub curse_damage_taken_per_stack: f32,
    pub curse_max_stacks: u8,
    /// Root/Shock-stun duration multiplier applied to elites and bosses.
    pub control_resist_elite: f32,
    pub control_resist_boss: f32,
    pub mark_crit_chance: f32,
}

impl Default for StatusTuning {
    fn default() -> Self {
        Self {
            burn_dps_ratio: 0.25,
            burn_max_stacks: 5,
            bleed_dps_ratio: 0.2,
            bleed_moving_mult: 2.0,
            bleed_max_stacks: 5,
            shock_threshold: 3,
            shock_discharge_ratio: 1.5,
            shock_radius: 3.0,
            shock_stun: 0.35,
            curse_damage_taken_per_stack: 0.08,
            curse_max_stacks: 3,
            control_resist_elite: 0.5,
            control_resist_boss: 0.15,
            mark_crit_chance: 0.2,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct StatusInstance {
    pub stacks: u8,
    pub remaining: f32,
    /// Damage basis for DoTs / discharge (max of recent applications).
    pub potency: f32,
    pub source: SourceId,
}

impl StatusInstance {
    #[inline]
    pub fn active(&self) -> bool {
        self.stacks > 0 && self.remaining > 0.0
    }
}

/// Which "weight class" a target is in for control effects.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum ControlClass {
    #[default]
    Normal,
    Elite,
    Boss,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum ApplyOutcome {
    Applied,
    /// Shock reached its threshold: the caller deals `damage` Storm damage in `radius` and stuns.
    ShockDischarge {
        damage: f32,
        radius: f32,
        stun: f32,
        source: SourceId,
    },
}

/// Damage produced by one status tick.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct StatusTick {
    pub burn: f32,
    pub burn_source: SourceId,
    pub bleed: f32,
    pub bleed_source: SourceId,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct StatusSet {
    pub slots: [StatusInstance; StatusKind::COUNT],
}

impl StatusSet {
    #[inline]
    pub fn get(&self, kind: StatusKind) -> &StatusInstance {
        &self.slots[kind.index()]
    }

    #[inline]
    pub fn active(&self, kind: StatusKind) -> bool {
        self.slots[kind.index()].active()
    }

    #[inline]
    pub fn stacks(&self, kind: StatusKind) -> u8 {
        let s = &self.slots[kind.index()];
        if s.active() { s.stacks } else { 0 }
    }

    /// Bitmask of active statuses (replicated to clients for icons/tints).
    pub fn bits(&self) -> u8 {
        StatusKind::ALL.iter().filter(|k| self.active(**k)).fold(0, |acc, k| acc | k.bit())
    }

    pub fn clear(&mut self) {
        *self = Self::default();
    }

    /// Apply a status. Durations refresh to the longer of old/new, potency keeps the max, stacks
    /// add up to the per-status cap. Control effects are shortened on elites/bosses.
    pub fn apply(
        &mut self,
        kind: StatusKind,
        stacks: u8,
        duration: f32,
        potency: f32,
        source: SourceId,
        class: ControlClass,
        t: &StatusTuning,
    ) -> ApplyOutcome {
        let control_mult = match (kind, class) {
            (StatusKind::Root, ControlClass::Elite) => t.control_resist_elite,
            (StatusKind::Root, ControlClass::Boss) => t.control_resist_boss,
            _ => 1.0,
        };
        let max_stacks = match kind {
            StatusKind::Burn => t.burn_max_stacks,
            StatusKind::Bleed => t.bleed_max_stacks,
            StatusKind::Curse => t.curse_max_stacks,
            StatusKind::Shock => t.shock_threshold,
            StatusKind::Root | StatusKind::Mark => 1,
        }
        .max(1);
        let slot = &mut self.slots[kind.index()];
        if !slot.active() {
            *slot = StatusInstance::default();
        }
        slot.stacks = slot.stacks.saturating_add(stacks.max(1)).min(max_stacks);
        slot.remaining = slot.remaining.max(duration * control_mult);
        slot.potency = slot.potency.max(potency);
        slot.source = source;

        if kind == StatusKind::Shock && slot.stacks >= t.shock_threshold {
            let damage = slot.potency * t.shock_discharge_ratio;
            let stun = t.shock_stun
                * match class {
                    ControlClass::Normal => 1.0,
                    ControlClass::Elite => t.control_resist_elite,
                    ControlClass::Boss => t.control_resist_boss,
                };
            *slot = StatusInstance::default();
            return ApplyOutcome::ShockDischarge { damage, radius: t.shock_radius, stun, source };
        }
        ApplyOutcome::Applied
    }

    /// Advance timers and compute DoT damage for this tick.
    pub fn tick(&mut self, dt: f32, moving: bool, t: &StatusTuning) -> StatusTick {
        let mut out = StatusTick::default();
        let burn = &self.slots[StatusKind::Burn.index()];
        if burn.active() {
            out.burn = burn.potency * t.burn_dps_ratio * burn.stacks as f32 * dt;
            out.burn_source = burn.source;
        }
        let bleed = &self.slots[StatusKind::Bleed.index()];
        if bleed.active() {
            let mult = if moving { t.bleed_moving_mult } else { 1.0 };
            out.bleed = bleed.potency * t.bleed_dps_ratio * bleed.stacks as f32 * mult * dt;
            out.bleed_source = bleed.source;
        }
        for slot in &mut self.slots {
            if slot.stacks > 0 {
                slot.remaining -= dt;
                if slot.remaining <= 0.0 {
                    *slot = StatusInstance::default();
                }
            }
        }
        out
    }

    /// Incoming-damage multiplier from Curse.
    pub fn damage_taken_mult(&self, t: &StatusTuning) -> f32 {
        1.0 + self.stacks(StatusKind::Curse) as f32 * t.curse_damage_taken_per_stack
    }

    /// Crit chance bonus granted to hits against this target (Mark).
    pub fn crit_chance_bonus(&self, t: &StatusTuning) -> f32 {
        if self.active(StatusKind::Mark) { t.mark_crit_chance } else { 0.0 }
    }

    #[inline]
    pub fn rooted(&self) -> bool {
        self.active(StatusKind::Root)
    }

    /// Number of distinct statuses active ("debuffed" checks, Thessaly's Curse Weaver).
    pub fn count_active(&self) -> usize {
        StatusKind::ALL.iter().filter(|k| self.active(**k)).count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t() -> StatusTuning {
        StatusTuning::default()
    }

    #[test]
    fn burn_stacks_and_ticks() {
        let mut s = StatusSet::default();
        let src = SourceId::player(0);
        s.apply(StatusKind::Burn, 2, 3.0, 40.0, src, ControlClass::Normal, &t());
        assert_eq!(s.stacks(StatusKind::Burn), 2);
        let tick = s.tick(1.0, false, &t());
        assert!((tick.burn - 40.0 * 0.25 * 2.0).abs() < 1e-3);
        assert_eq!(tick.burn_source, src);
        s.tick(2.5, false, &t());
        assert!(!s.active(StatusKind::Burn));
    }

    #[test]
    fn stacks_cap() {
        let mut s = StatusSet::default();
        for _ in 0..20 {
            s.apply(StatusKind::Burn, 1, 3.0, 10.0, SourceId::player(0), ControlClass::Normal, &t());
        }
        assert_eq!(s.stacks(StatusKind::Burn), t().burn_max_stacks);
    }

    #[test]
    fn shock_discharges_at_threshold() {
        let mut s = StatusSet::default();
        let src = SourceId::player(1);
        assert_eq!(s.apply(StatusKind::Shock, 1, 2.0, 30.0, src, ControlClass::Normal, &t()), ApplyOutcome::Applied);
        s.apply(StatusKind::Shock, 1, 2.0, 30.0, src, ControlClass::Normal, &t());
        match s.apply(StatusKind::Shock, 1, 2.0, 30.0, src, ControlClass::Normal, &t()) {
            ApplyOutcome::ShockDischarge { damage, .. } => assert!((damage - 45.0).abs() < 1e-3),
            other => panic!("expected discharge, got {other:?}"),
        }
        assert!(!s.active(StatusKind::Shock));
    }

    #[test]
    fn root_is_shorter_on_bosses() {
        let mut s = StatusSet::default();
        s.apply(StatusKind::Root, 1, 2.0, 0.0, SourceId::player(0), ControlClass::Boss, &t());
        assert!((s.get(StatusKind::Root).remaining - 0.3).abs() < 1e-4);
    }

    #[test]
    fn curse_and_mark_modifiers() {
        let mut s = StatusSet::default();
        s.apply(StatusKind::Curse, 2, 3.0, 0.0, SourceId::player(0), ControlClass::Normal, &t());
        s.apply(StatusKind::Mark, 1, 3.0, 0.0, SourceId::player(0), ControlClass::Normal, &t());
        assert!((s.damage_taken_mult(&t()) - 1.16).abs() < 1e-4);
        assert!((s.crit_chance_bonus(&t()) - 0.2).abs() < 1e-4);
        assert_eq!(s.bits(), StatusKind::Curse.bit() | StatusKind::Mark.bit());
        assert_eq!(s.count_active(), 2);
    }

    #[test]
    fn bleed_hurts_more_while_moving() {
        let mut a = StatusSet::default();
        a.apply(StatusKind::Bleed, 1, 5.0, 10.0, SourceId::player(0), ControlClass::Normal, &t());
        let mut b = a.clone();
        let still = a.tick(1.0, false, &t()).bleed;
        let moving = b.tick(1.0, true, &t()).bleed;
        assert!((moving - still * 2.0).abs() < 1e-4);
    }
}
