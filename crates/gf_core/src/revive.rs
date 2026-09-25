//! Soul-Tether revive: downed players become wraiths for up to 20 s; an ally standing inside tether
//! range for 3 s *uninterrupted* revives them (the reviver gains a shield). If nobody comes, the
//! Forge reforges them after a short delay — no player is out of the fight longer than 30 s.
//! The run is lost only when no player is left standing.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct ReviveTuning {
    pub downed_duration: f32,
    pub revive_time: f32,
    pub tether_range: f32,
    pub revive_hp_frac: f32,
    pub reviver_shield: f32,
    /// After the wraith window expires, seconds until the Forge reforges the player.
    pub reforge_delay: f32,
    pub reforge_hp_frac: f32,
    /// Solo-only self-revives per run ("Rekindle").
    pub solo_rekindles: u8,
    pub rekindle_delay: f32,
}

impl Default for ReviveTuning {
    fn default() -> Self {
        Self {
            downed_duration: 20.0,
            revive_time: 3.0,
            tether_range: 3.5,
            revive_hp_frac: 0.4,
            reviver_shield: 40.0,
            reforge_delay: 10.0,
            reforge_hp_frac: 0.5,
            solo_rekindles: 1,
            rekindle_delay: 2.0,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub enum LifeState {
    #[default]
    Alive,
    /// Wraith state: can drift slowly, cannot fire.
    Downed { remaining: f32, progress: f32 },
    /// Waiting for the Forge to reforge them (co-op) or a Rekindle (solo).
    Reforging { remaining: f32 },
}

impl LifeState {
    pub fn is_alive(&self) -> bool {
        matches!(self, LifeState::Alive)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LifeEvent {
    None,
    /// Revived by an ally (reviver gets a shield).
    Revived,
    /// Wraith window ran out; now reforging.
    StartedReforge,
    /// Back in the fight via the Forge / Rekindle.
    Reforged,
}

/// Step one player's life state.
/// - `allies_tethering`: number of *alive* allies within tether range this tick.
pub fn step_life(state: &mut LifeState, dt: f32, allies_tethering: u32, t: &ReviveTuning) -> LifeEvent {
    match state {
        LifeState::Alive => LifeEvent::None,
        LifeState::Downed { remaining, progress } => {
            if allies_tethering > 0 {
                // More allies revive a little faster.
                *progress += dt * (1.0 + 0.25 * (allies_tethering - 1) as f32);
                if *progress >= t.revive_time {
                    *state = LifeState::Alive;
                    return LifeEvent::Revived;
                }
            } else {
                // Tether must be uninterrupted.
                *progress = 0.0;
            }
            *remaining -= dt;
            if *remaining <= 0.0 {
                *state = LifeState::Reforging { remaining: t.reforge_delay };
                return LifeEvent::StartedReforge;
            }
            LifeEvent::None
        }
        LifeState::Reforging { remaining } => {
            *remaining -= dt;
            if *remaining <= 0.0 {
                *state = LifeState::Alive;
                return LifeEvent::Reforged;
            }
            LifeEvent::None
        }
    }
}

/// What happens when a player's HP hits zero.
pub fn on_downed(party_size: u8, rekindles_left: &mut u8, t: &ReviveTuning) -> LifeState {
    if party_size <= 1 {
        if *rekindles_left > 0 {
            *rekindles_left -= 1;
            LifeState::Reforging { remaining: t.rekindle_delay }
        } else {
            // Solo with no Rekindle: a downed state nobody can tether is a wipe.
            LifeState::Downed { remaining: 0.0, progress: 0.0 }
        }
    } else {
        LifeState::Downed { remaining: t.downed_duration, progress: 0.0 }
    }
}

/// Team wipe: nobody left standing.
pub fn is_wipe<'a>(states: impl IntoIterator<Item = &'a LifeState>) -> bool {
    let mut any = false;
    for s in states {
        any = true;
        if s.is_alive() {
            return false;
        }
    }
    any
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tether_revives_after_uninterrupted_time() {
        let t = ReviveTuning::default();
        let mut s = on_downed(2, &mut 0, &t);
        for _ in 0..(2.0 / 0.1) as usize {
            assert_eq!(step_life(&mut s, 0.1, 1, &t), LifeEvent::None);
        }
        // Interruption resets progress.
        step_life(&mut s, 0.1, 0, &t);
        let LifeState::Downed { progress, .. } = s else { panic!() };
        assert_eq!(progress, 0.0);
        let mut ev = LifeEvent::None;
        for _ in 0..40 {
            ev = step_life(&mut s, 0.1, 1, &t);
            if ev != LifeEvent::None {
                break;
            }
        }
        assert_eq!(ev, LifeEvent::Revived);
        assert!(s.is_alive());
    }

    #[test]
    fn nobody_out_longer_than_30s() {
        let t = ReviveTuning::default();
        let mut s = on_downed(3, &mut 0, &t);
        let mut elapsed = 0.0;
        while !s.is_alive() {
            step_life(&mut s, 0.1, 0, &t);
            elapsed += 0.1;
            assert!(elapsed <= 30.2, "out of the fight too long");
        }
        assert!(elapsed >= 29.8);
    }

    #[test]
    fn solo_rekindle_then_wipe() {
        let t = ReviveTuning::default();
        let mut rekindles = 1;
        let s = on_downed(1, &mut rekindles, &t);
        assert!(matches!(s, LifeState::Reforging { .. }));
        assert_eq!(rekindles, 0);
        let s2 = on_downed(1, &mut rekindles, &t);
        assert!(is_wipe([&s2]));
    }

    #[test]
    fn wipe_detection() {
        assert!(!is_wipe([&LifeState::Alive, &LifeState::Reforging { remaining: 1.0 }]));
        assert!(is_wipe([
            &LifeState::Downed { remaining: 5.0, progress: 0.0 },
            &LifeState::Reforging { remaining: 1.0 }
        ]));
        assert!(!is_wipe(std::iter::empty::<&LifeState>()));
    }
}
