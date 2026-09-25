//! Anvil stations (§6): interact to light → hold-the-anvil wave (progress only while a player
//! stands in the ring) → the anvil runs hot and grants forge charges → spent.
//! Forge actions are validated and applied host-side through `gf_core::forge`.
//!
//! Charges are per anvil (OPEN_WORLD.md §5.3): a Hot anvil grants `charges_per_anvil` to each
//! living player who stands within `radius + 1` of it (once per player per anvil) and records
//! itself in their `Arsenal.charges_from`. Going Spent takes charges only from the players whose
//! charges it granted, so on a biome map one anvil cooling never empties a partner's wallet at
//! another. A biome map's anvil also carries a `Poi`; `poi::poi_update` turns its lifecycle into
//! Seals, the breaker and completion.

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
    mut anvils: Query<(Entity, &Pos, &mut AnvilStation)>,
    mut players: Query<(&Player, &Pos, &PlayerInput, &Life, &mut Arsenal)>,
) {
    let dt = clock.gdt();
    let t = &content.game.anvil;
    let mut focus = false;
    for (entity, pos, mut anvil) in &mut anvils {
        let inside: Vec<bool> =
            players.iter().map(|(_, p, _, life, _)| life.state.is_alive() && p.0.distance(pos.0) <= t.radius).collect();
        match anvil.state {
            AnvilState::Dormant => {
                let lit =
                    players.iter().zip(&inside).any(|((_, _, input, ..), inside)| *inside && input.new.interact > 0);
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
                    anvil.granted = 0;
                    events.0.push(GameEvent::AnvilHot);
                }
            }
            AnvilState::Hot => {
                anvil.forge_left -= dt;
                // Forge focus: everyone at the anvil with the forge open slows time (solo = focus).
                let all_forging = players.iter().zip(&inside).all(|((_, _, input, life, _), inside)| {
                    !life.state.is_alive() || (*inside && input.cmd.forge_open)
                });
                focus |= all_forging && inside.iter().any(|i| *i);
                if anvil.forge_left <= 0.0 {
                    anvil.state = AnvilState::Spent;
                    // Only the charges this anvil granted burn out with it.
                    for (.., mut arsenal) in &mut players {
                        if arsenal.charges_from == Some(entity) {
                            arsenal.wallet.charges = 0;
                            arsenal.charges_from = None;
                        }
                    }
                }
            }
            AnvilState::Spent => {}
        }
        // A Hot anvil (including the tick it lit up) grants its charges to each living player who
        // comes within `radius + 1`, once per player.
        if anvil.state == AnvilState::Hot {
            let reach = t.radius + 1.0;
            for (player, p, _, life, mut arsenal) in &mut players {
                let bit = 1u8 << (player.slot & 7);
                if anvil.granted & bit == 0 && life.state.is_alive() && p.0.distance(pos.0) <= reach {
                    anvil.granted |= bit;
                    arsenal.wallet.charges = content.game.forge.charges_per_anvil;
                    arsenal.charges_from = Some(entity);
                }
            }
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
