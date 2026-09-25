//! Elemental Synergy Combos: element A from one source meets element B from a *different* source
//! on the same enemy within a short window → a named detonation ("SYNERGY" banner + kill feed).
//!
//! Echo drones and turrets are their own sources, so solo players reach synergies through their
//! Echo; a data flag also allows same-source synergies (at reduced power) in solo runs.

use crate::damage::DamageType;
use crate::ids::{SourceId, SynergyId};
use crate::status::StatusKind;
use serde::{Deserialize, Serialize};

/// What a synergy does when it fires.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum SynergyEffect {
    /// Explosion around the target (damage = mult × the triggering hit).
    Burst {
        radius: f32,
        damage_mult: f32,
        element: DamageType,
        #[serde(default)]
        status: Option<StatusKind>,
    },
    /// Chain to nearby enemies pulling them together.
    GravityChain { jumps: u8, range: f32, damage_mult: f32, pull: f32 },
    /// Heal allies near the target (Purge / Radiant combos).
    AllyHeal { radius: f32, amount: f32, damage_mult: f32 },
    /// Leave a hazard field.
    Field { radius: f32, duration: f32, dps_mult: f32, element: DamageType, slow: f32 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SynergyRule {
    pub id: SynergyId,
    pub a: DamageType,
    pub b: DamageType,
    pub effect: SynergyEffect,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct SynergyTuning {
    /// Seconds an element "mark" lingers on an enemy.
    pub window: f32,
    /// Per-enemy cooldown after a synergy fires.
    pub cooldown: f32,
    /// Allow same-source synergies when the party has exactly one player.
    pub solo_self_synergy: bool,
    /// Damage multiplier applied to same-source (solo) synergies.
    pub solo_power: f32,
}

impl Default for SynergyTuning {
    fn default() -> Self {
        Self { window: 2.5, cooldown: 1.5, solo_self_synergy: true, solo_power: 0.5 }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct ElementMark {
    pub element: DamageType,
    pub source: SourceId,
    pub remaining: f32,
}

/// Recent element hits on one enemy (tiny fixed buffer, no allocation).
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct ElementMarks {
    pub marks: [Option<ElementMark>; 3],
    pub cooldown: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SynergyTrigger {
    pub synergy: SynergyId,
    /// Source whose hit completed the combo (gets kill-feed credit alongside `partner`).
    pub trigger_source: SourceId,
    pub partner: SourceId,
    /// 1.0 for true co-op combos, `solo_power` for same-source solo combos.
    pub power: f32,
}

impl ElementMarks {
    pub fn tick(&mut self, dt: f32) {
        self.cooldown = (self.cooldown - dt).max(0.0);
        for m in self.marks.iter_mut() {
            if let Some(mark) = m {
                mark.remaining -= dt;
                if mark.remaining <= 0.0 {
                    *m = None;
                }
            }
        }
    }

    fn record(&mut self, element: DamageType, source: SourceId, window: f32) {
        // Refresh an existing (element, source) mark or take the stalest slot.
        if let Some(m) = self.marks.iter_mut().flatten().find(|m| m.element == element && m.source == source) {
            m.remaining = window;
            return;
        }
        let slot = self.marks.iter().position(|m| m.is_none()).unwrap_or_else(|| {
            self.marks
                .iter()
                .enumerate()
                .min_by(|(_, a), (_, b)| {
                    let ra = a.map_or(0.0, |m| m.remaining);
                    let rb = b.map_or(0.0, |m| m.remaining);
                    ra.total_cmp(&rb)
                })
                .map(|(i, _)| i)
                .unwrap_or(0)
        });
        self.marks[slot] = Some(ElementMark { element, source, remaining: window });
    }

    /// Register a hit of `element` from `source`; returns a synergy if one fires.
    pub fn on_hit(
        &mut self,
        element: DamageType,
        source: SourceId,
        rules: &[SynergyRule],
        tuning: &SynergyTuning,
        party_size: u8,
    ) -> Option<SynergyTrigger> {
        if self.cooldown <= 0.0 {
            let solo = party_size <= 1 && tuning.solo_self_synergy;
            let mut found: Option<(usize, SynergyTrigger)> = None;
            'outer: for (i, mark) in self.marks.iter().enumerate() {
                let Some(mark) = mark else { continue };
                if mark.element == element {
                    continue;
                }
                let distinct = mark.source != source;
                if !distinct && !solo {
                    continue;
                }
                for rule in rules {
                    let pair =
                        (rule.a == mark.element && rule.b == element) || (rule.b == mark.element && rule.a == element);
                    if pair {
                        found = Some((
                            i,
                            SynergyTrigger {
                                synergy: rule.id,
                                trigger_source: source,
                                partner: mark.source,
                                power: if distinct { 1.0 } else { tuning.solo_power },
                            },
                        ));
                        break 'outer;
                    }
                }
            }
            if let Some((i, trig)) = found {
                self.marks[i] = None;
                self.cooldown = tuning.cooldown;
                return Some(trig);
            }
        }
        self.record(element, source, tuning.window);
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rules() -> Vec<SynergyRule> {
        vec![SynergyRule {
            id: SynergyId(0),
            a: DamageType::Plague,
            b: DamageType::Flame,
            effect: SynergyEffect::Burst {
                radius: 3.0,
                damage_mult: 2.0,
                element: DamageType::Flame,
                status: Some(StatusKind::Burn),
            },
        }]
    }

    #[test]
    fn co_op_combo_fires() {
        let mut m = ElementMarks::default();
        let t = SynergyTuning::default();
        assert!(m.on_hit(DamageType::Plague, SourceId::player(0), &rules(), &t, 2).is_none());
        let trig = m.on_hit(DamageType::Flame, SourceId::player(1), &rules(), &t, 2).expect("Blightburn");
        assert_eq!(trig.synergy, SynergyId(0));
        assert_eq!(trig.partner, SourceId::player(0));
        assert_eq!(trig.power, 1.0);
        // Cooldown blocks an immediate re-trigger.
        m.on_hit(DamageType::Plague, SourceId::player(0), &rules(), &t, 2);
        assert!(m.on_hit(DamageType::Flame, SourceId::player(1), &rules(), &t, 2).is_none());
    }

    #[test]
    fn same_source_needs_solo() {
        let t = SynergyTuning::default();
        let mut m = ElementMarks::default();
        m.on_hit(DamageType::Plague, SourceId::player(0), &rules(), &t, 2);
        assert!(
            m.on_hit(DamageType::Flame, SourceId::player(0), &rules(), &t, 2).is_none(),
            "co-op requires distinct sources"
        );
        let mut solo = ElementMarks::default();
        solo.on_hit(DamageType::Plague, SourceId::player(0), &rules(), &t, 1);
        let trig = solo.on_hit(DamageType::Flame, SourceId::player(0), &rules(), &t, 1).expect("solo self-synergy");
        assert_eq!(trig.power, t.solo_power);
    }

    #[test]
    fn echo_counts_as_a_partner() {
        let t = SynergyTuning::default();
        let mut m = ElementMarks::default();
        m.on_hit(DamageType::Plague, SourceId::echo(0), &rules(), &t, 1);
        let trig = m.on_hit(DamageType::Flame, SourceId::player(0), &rules(), &t, 1).unwrap();
        assert_eq!(trig.power, 1.0);
    }

    #[test]
    fn marks_expire() {
        let t = SynergyTuning::default();
        let mut m = ElementMarks::default();
        m.on_hit(DamageType::Plague, SourceId::player(0), &rules(), &t, 2);
        m.tick(t.window + 0.1);
        assert!(m.on_hit(DamageType::Flame, SourceId::player(1), &rules(), &t, 2).is_none());
    }
}
