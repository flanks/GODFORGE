//! Boon doors (§7): 3-choice offers from one god, Duo boons once both gods are held, Legendaries
//! gated on commitment to a god, Team boons in co-op, limited rerolls.

use crate::components::*;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::schema::{BoonKind, BoonReq, Phase};
use gf_core::ids::BoonId;
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::{GameEvent, PlayerAction};

fn requirements_met(db: &ContentDb, owned: &[(BoonId, Rarity)], reqs: &[BoonReq]) -> bool {
    reqs.iter().all(|r| match r {
        BoonReq::FromGod { god, count } => {
            owned.iter().filter(|(b, _)| db.boon(*b).gods.iter().any(|g| g == god)).count() >= *count as usize
        }
        BoonReq::Boon(key) => db.boons.id(key).is_some_and(|id| owned.iter().any(|(b, _)| b.0 == id)),
    })
}

/// Build a 3-choice offer from `god` (Duo boons involving the god are eligible once unlocked).
pub fn make_offer(
    db: &ContentDb,
    phase: Phase,
    rng: &mut GfRng,
    god: u16,
    owned: &[(BoonId, Rarity)],
    party: u8,
    luck: f32,
) -> Vec<(BoonId, Rarity)> {
    let god_key = &db.gods.get(god).key;
    let mut pool: Vec<(BoonId, f32)> = db
        .boons
        .enumerate()
        .filter(|(i, b)| {
            b.phase <= phase
                && !owned.iter().any(|(o, _)| o.0 == *i)
                && match b.kind {
                    BoonKind::Standard | BoonKind::Legendary | BoonKind::Duo => b.gods.iter().any(|g| g == god_key),
                    BoonKind::Team => party >= 2,
                }
                && requirements_met(db, owned, &b.requires)
        })
        .map(|(i, b)| (BoonId(i), b.weight))
        .collect();
    let mut offer = Vec::new();
    while offer.len() < 3 && !pool.is_empty() {
        let weights: Vec<f32> = pool.iter().map(|(_, w)| *w).collect();
        let Some(i) = rng.weighted_index(&weights) else { break };
        let (id, _) = pool.swap_remove(i);
        let rarity = if db.boon(id).kind == BoonKind::Standard {
            db.game.rarity.roll(rng, luck).min(Rarity::Epic)
        } else {
            Rarity::Common
        };
        offer.push((id, rarity));
    }
    offer
}

pub fn boon_actions(
    content: Res<Content>,
    settings: Res<SimSettings>,
    tuning: Res<Tuning>,
    mut rngs: ResMut<Rngs>,
    mut team: ResMut<TeamBoons>,
    mut events: ResMut<Events>,
    mut players: Query<(&Player, &PlayerInput, &mut BoonChoice, &mut Arsenal, &mut Kit, &Stats)>,
) {
    let mut team_changed = false;
    for (player, input, mut choice, mut arsenal, mut kit, stats) in &mut players {
        match input.cmd.action {
            Some((_, PlayerAction::PickBoon(i))) => {
                let Some(&(boon, rarity)) = choice.offer.get(i as usize) else { continue };
                if content.boon(boon).kind == BoonKind::Team {
                    team.0.push((boon, rarity));
                    team_changed = true;
                } else {
                    arsenal.boons.push((boon, rarity));
                }
                choice.offer.clear();
                kit.dirty = true;
                events.0.push(GameEvent::BoonTaken { slot: player.slot, boon: boon.0 });
            }
            Some((_, PlayerAction::RerollBoons)) => {
                if choice.rerolls > 0
                    && !choice.offer.is_empty()
                    && let Some(god) = choice.god
                {
                    choice.rerolls -= 1;
                    choice.offer = make_offer(
                        &content,
                        settings.phase,
                        &mut rngs.boons,
                        god,
                        &arsenal.boons,
                        tuning.party,
                        stats.0.luck,
                    );
                }
            }
            _ => {}
        }
    }
    if team_changed {
        for (.., mut kit, _) in &mut players {
            kit.dirty = true;
        }
    }
}
