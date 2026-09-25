//! Shared Team Overdrive: team damage fills one global meter; any player may trigger it
//! (5 s: +30% fire rate, +1 dash for all, golden crescendo). Timing it is a skill moment.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct OverdriveTuning {
    /// Damage needed to fill the meter (scaled by party size at runtime).
    pub meter_damage: f32,
    pub duration: f32,
    pub fire_rate_bonus: f32,
    pub extra_dashes: u8,
}

impl Default for OverdriveTuning {
    fn default() -> Self {
        Self { meter_damage: 6000.0, duration: 5.0, fire_rate_bonus: 0.3, extra_dashes: 1 }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct TeamOverdrive {
    /// 0..=1
    pub meter: f32,
    /// Seconds of Overdrive remaining (0 = inactive).
    pub active: f32,
    /// Slot of the player who triggered the current Overdrive.
    pub triggered_by: Option<u8>,
}

impl TeamOverdrive {
    /// Feed damage dealt by the team. No gain while active.
    pub fn add_damage(&mut self, damage: f32, party_size: u8, t: &OverdriveTuning) {
        if self.active > 0.0 {
            return;
        }
        let need = t.meter_damage * (1.0 + 0.6 * (party_size.max(1) - 1) as f32);
        self.meter = (self.meter + damage / need.max(1.0)).min(1.0);
    }

    pub fn ready(&self) -> bool {
        self.meter >= 1.0 && self.active <= 0.0
    }

    /// Try to trigger; returns true if Overdrive started.
    pub fn trigger(&mut self, slot: u8, t: &OverdriveTuning) -> bool {
        if !self.ready() {
            return false;
        }
        self.meter = 0.0;
        self.active = t.duration;
        self.triggered_by = Some(slot);
        true
    }

    pub fn tick(&mut self, dt: f32) {
        if self.active > 0.0 {
            self.active = (self.active - dt).max(0.0);
            if self.active == 0.0 {
                self.triggered_by = None;
            }
        }
    }

    pub fn is_active(&self) -> bool {
        self.active > 0.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fill_trigger_expire() {
        let t = OverdriveTuning::default();
        let mut o = TeamOverdrive::default();
        assert!(!o.trigger(0, &t));
        o.add_damage(3000.0, 1, &t);
        assert!((o.meter - 0.5).abs() < 1e-5);
        o.add_damage(99_999.0, 1, &t);
        assert!(o.ready());
        assert!(o.trigger(2, &t));
        assert!(o.is_active());
        assert_eq!(o.triggered_by, Some(2));
        o.add_damage(99_999.0, 1, &t);
        assert_eq!(o.meter, 0.0, "no gain while active");
        o.tick(5.1);
        assert!(!o.is_active());
    }

    #[test]
    fn bigger_parties_need_more_damage() {
        let t = OverdriveTuning::default();
        let mut solo = TeamOverdrive::default();
        let mut quad = TeamOverdrive::default();
        solo.add_damage(1000.0, 1, &t);
        quad.add_damage(1000.0, 4, &t);
        assert!(solo.meter > quad.meter);
    }
}
