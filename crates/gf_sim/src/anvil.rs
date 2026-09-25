//! Anvil stations (§6): interact to light → hold-the-anvil wave (progress only while a player
//! stands in the ring) → the anvil runs hot and every player gets forge charges → spent.
//! Forge actions are validated and applied host-side through `gf_core::forge`.

use crate::components::*;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::schema::Phase;
use gf_core::forge::{ForgeAction, ForgeError, PartCatalog, Slot, apply_action};
use gf_core::ids::PartId;
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::{AnvilState, GameEvent, PlayerAction};

/// Content-backed catalog for forge rerolls.
pub struct SimCatalog<'a> {
    pub db: &'a ContentDb,
    pub phase: Phase,
    pub rng: &'a mut GfRng,
}

impl PartCatalog for SimCatalog<'_> {
    fn slot_of(&self, part: PartId) -> Option<Slot> {
        self.db.part_slot(part)
    }

    fn reroll_pick(&mut self, slot: Slot, exclude: PartId) -> Option<PartId> {
        let pool: Vec<(PartId, f32)> = self
            .db
            .parts_for_slot(slot, self.phase)
            .filter(|(id, _)| *id != exclude)
            .map(|(id, p)| (id, p.weight))
            .collect();
        let weights: Vec<f32> = pool.iter().map(|(_, w)| *w).collect();
        self.rng.weighted_index(&weights).map(|i| pool[i].0)
    }

    fn salvage_value(&self, rarity: Rarity) -> u32 {
        self.db.game.rarity.salvage_shards[rarity.index()]
    }
}

pub fn anvil_update(
    mut clock: ResMut<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    mut events: ResMut<Events>,
    mut anvils: Query<(&Pos, &mut AnvilStation)>,
    mut players: Query<(&Pos, &PlayerInput, &Life, &mut Arsenal), With<Player>>,
) {
    let dt = clock.gdt();
    let t = &content.game.anvil;
    let mut focus = false;
    for (pos, mut anvil) in &mut anvils {
        let inside: Vec<bool> =
            players.iter().map(|(p, _, life, _)| life.state.is_alive() && p.0.distance(pos.0) <= t.radius).collect();
        match anvil.state {
            AnvilState::Dormant => {
                let lit =
                    players.iter().zip(&inside).any(|((_, input, _, _), inside)| *inside && input.new.interact > 0);
                if lit {
                    anvil.state = AnvilState::Kindling;
                    events.0.push(GameEvent::AnvilLit);
                }
            }
            AnvilState::Kindling => {
                anvil.contested = !inside.iter().any(|i| *i);
                if !anvil.contested {
                    anvil.progress += dt / (t.hold_time * tuning.enemy.anvil_hold_time).max(1.0);
                }
                if anvil.progress >= 1.0 {
                    anvil.progress = 1.0;
                    anvil.state = AnvilState::Hot;
                    anvil.forge_left = t.forge_window;
                    for (.., mut arsenal) in &mut players {
                        arsenal.wallet.charges = content.game.forge.charges_per_anvil;
                    }
                    events.0.push(GameEvent::AnvilHot);
                }
            }
            AnvilState::Hot => {
                anvil.forge_left -= dt;
                // Forge focus: everyone at the anvil with the forge open slows time (solo = focus).
                let all_forging = players
                    .iter()
                    .zip(&inside)
                    .all(|((_, input, life, _), inside)| !life.state.is_alive() || (*inside && input.cmd.forge_open));
                focus |= all_forging && inside.iter().any(|i| *i);
                if anvil.forge_left <= 0.0 {
                    anvil.state = AnvilState::Spent;
                    for (.., mut arsenal) in &mut players {
                        arsenal.wallet.charges = 0;
                    }
                }
            }
            AnvilState::Spent => {}
        }
    }
    clock.scale = if focus { t.forge_focus_time_scale } else { 1.0 };
}

/// Is this player standing at a hot anvil?
pub fn at_hot_anvil(anvils: &[(Vec2, AnvilState)], pos: Vec2, radius: f32) -> bool {
    anvils.iter().any(|(p, s)| *s == AnvilState::Hot && p.distance(pos) <= radius + 1.0)
}

pub fn forge_actions(
    content: Res<Content>,
    settings: Res<SimSettings>,
    mut rngs: ResMut<Rngs>,
    mut events: ResMut<Events>,
    anvils: Query<(&Pos, &AnvilStation)>,
    mut players: Query<(&Player, &Pos, &PlayerInput, &mut Arsenal, &mut Kit, &mut RunStats)>,
) {
    let hot: Vec<(Vec2, AnvilState)> = anvils.iter().map(|(p, a)| (p.0, a.state)).collect();
    let radius = content.game.anvil.radius;
    for (player, pos, input, mut arsenal, mut kit, mut stats) in &mut players {
        let Some((_, PlayerAction::Forge(action))) = input.cmd.action else { continue };
        let needs_anvil = !matches!(action, ForgeAction::Salvage { .. });
        if needs_anvil && !at_hot_anvil(&hot, pos.0, radius) {
            events.0.push(GameEvent::ForgeFailed { slot: player.slot, error: ForgeError::NotAtAnvil });
            continue;
        }
        let a = &mut *arsenal;
        let mut catalog = SimCatalog { db: &content, phase: settings.phase, rng: &mut rngs.loot };
        match apply_action(
            action,
            &mut a.build,
            &mut a.bag,
            &mut a.wallet,
            &content.game.forge,
            &mut catalog,
            &mut a.next_uid,
        ) {
            Ok(outcome) => {
                kit.dirty = true;
                stats.forge_actions += 1;
                events.0.push(GameEvent::Forged { slot: player.slot, outcome });
            }
            Err(error) => events.0.push(GameEvent::ForgeFailed { slot: player.slot, error }),
        }
    }
}
