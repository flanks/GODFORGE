//! The spawn director: releases each room's enemy budget along a rate ramp, in packs, from spawn
//! zones out of the players' comfort radius. Escalation per room and per biome comes from content
//! (`run.budget_growth_per_room`, …) so minute 15 is beautiful madness (§2.1).

use crate::components::*;
use crate::enemies::spawn_enemy;
use crate::resources::*;
use gf_content::schema::{SpawnZone, WeightedKey};
use gf_core::ids::EnemyId;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::{AnvilState, RunPhase};

/// Stress-test override: keep exactly this many enemies alive (chaos stress scene, §20.7).
#[derive(Resource, Debug, Default, Clone, Copy)]
pub struct StressMode(pub Option<u32>);

fn pick_weighted(
    pool: &[WeightedKey],
    content: &crate::resources::Content,
    phase: gf_content::Phase,
    rng: &mut GfRng,
) -> Option<EnemyId> {
    let usable: Vec<(u16, f32)> = pool
        .iter()
        .filter_map(|w| content.enemies.id(&w.key).map(|id| (id, w.weight)))
        .filter(|(id, _)| content.enemies.get(*id).phase <= phase)
        .collect();
    let weights: Vec<f32> = usable.iter().map(|(_, w)| *w).collect();
    rng.weighted_index(&weights).map(|i| EnemyId(usable[i].0))
}

/// A spawn point from the room's zones, preferring points away from every player.
pub fn spawn_point(zones: &[SpawnZone], half: Vec2, players: &[Vec2], rng: &mut GfRng) -> Vec2 {
    let mut best = Vec2::ZERO;
    let mut best_d = -1.0;
    for _ in 0..8 {
        let zone = rng.pick(zones).copied().unwrap_or(SpawnZone::Edges { margin: 1.0 });
        let p = match zone {
            SpawnZone::Edges { margin } => {
                let h = half - Vec2::splat(margin.max(0.5));
                let perimeter = 4.0 * (h.x + h.y);
                let mut t = rng.range_f32(0.0, perimeter);
                if t < 2.0 * h.x {
                    Vec2::new(-h.x + t, h.y)
                } else {
                    t -= 2.0 * h.x;
                    if t < 2.0 * h.y {
                        Vec2::new(h.x, h.y - t)
                    } else {
                        t -= 2.0 * h.y;
                        if t < 2.0 * h.x { Vec2::new(h.x - t, -h.y) } else { Vec2::new(-h.x, -h.y + (t - 2.0 * h.x)) }
                    }
                }
            }
            SpawnZone::Point { at, radius } => at + rng.unit_vec2() * rng.range_f32(0.0, radius),
        };
        let d = players.iter().map(|q| q.distance(p)).fold(f32::INFINITY, f32::min);
        if d >= 8.0 {
            return p;
        }
        if d > best_d {
            best_d = d;
            best = p;
        }
    }
    best
}

#[allow(clippy::too_many_arguments)]
pub fn run_director(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    settings: Res<SimSettings>,
    tuning: Res<Tuning>,
    run: Res<RunState>,
    stress: Res<StressMode>,
    arena: Res<ArenaRes>,
    mut enc: ResMut<Encounter>,
    mut ids: ResMut<NetIds>,
    mut rngs: ResMut<Rngs>,
    anvils: Query<&AnvilStation>,
    players: Query<(&Pos, &Life), (With<Player>, Without<Enemy>)>,
    mut enemies: Query<(&Enemy, &mut Pos), Without<Player>>,
) {
    enc.alive = enemies.iter().filter(|(e, _)| e.hp > 0.0).count() as u32;
    if !run.started || run.is_over() || run.transition > 0.0 || run.biomes.is_empty() {
        return;
    }
    let room = content.room(run.room);
    let biome = content.biome(run.biomes[run.biome_idx]);
    let player_pos: Vec<Vec2> = players.iter().filter(|(_, l)| l.state.is_alive()).map(|(p, _)| p.0).collect();
    let dt = clock.gdt();

    // Anti-stall: stragglers stuck out of reach for 15 s are brought back into the fight.
    if run.kills != enc.last_kills {
        enc.last_kills = run.kills;
        enc.stall = 0.0;
    } else {
        enc.stall += dt;
    }
    if enc.budget_left <= 0.0 && enc.alive <= 5 && enc.stall > 15.0 && !player_pos.is_empty() {
        enc.stall = 0.0;
        for (_, mut pos) in &mut enemies {
            let anchor = player_pos[0];
            let p = anchor + rngs.director.unit_vec2() * 8.0;
            pos.0 = arena.0.resolve(p, 0.6);
        }
    }

    if let Some(target) = stress.0 {
        let mut n = enc.alive;
        while n < target {
            let Some(def) = pick_weighted(&biome.swarm, &content, settings.phase, &mut rngs.director) else { break };
            let at = spawn_point(&room.spawn_zones, arena.0.half_extents, &player_pos, &mut rngs.director);
            spawn_enemy(&mut commands, &mut ids, &content, &tuning, 1.0, def, at, &mut rngs.director);
            n += 1;
        }
        return;
    }
    if run.phase != RunPhase::Combat || enc.budget_left <= 0.0 {
        return;
    }
    let mut intensity = 1.0;
    if enc.anvil_gated {
        match anvils.iter().next().map(|a| a.state) {
            Some(AnvilState::Kindling) => intensity = content.game.anvil.wave_intensity,
            Some(AnvilState::Hot | AnvilState::Spent) => intensity = 1.0,
            _ => return,
        }
    }
    enc.elapsed += dt;
    let f = (enc.elapsed / enc.duration.max(1.0)).min(1.0);
    let rate = (enc.rate_start + (enc.rate_end - enc.rate_start) * f)
        * tuning.enemy.spawn_rate
        * tuning.enemy.count
        * content.game.run.rate_mult
        * (1.0 + content.game.run.rate_growth_per_room * run.rooms_in_biome as f32)
        * intensity;
    // `rate` is enemy weight per second (swarm = 1, elite = 6): packs spawn when enough accrues.
    enc.accum += rate * dt;
    let max_alive = (enc.max_alive as f32 * tuning.enemy.count) as u32;
    while enc.accum >= 1.0 && enc.alive < max_alive && enc.budget_left > 0.0 {
        let elite = !biome.elites.is_empty() && rngs.director.chance(enc.elite_chance + tuning.enemy.elite_chance_add);
        let pool = if elite { &biome.elites } else { &biome.swarm };
        let Some(def) = pick_weighted(pool, &content, settings.phase, &mut rngs.director) else { break };
        let d = content.enemy(def);
        let cost = if elite { 6.0 } else { 1.0 };
        let base = rngs.director.range_u32(d.pack.0 as u32, d.pack.1 as u32 + 1);
        let n = if elite { 1 } else { ((base as f32) * tuning.enemy.count.sqrt()).round().max(1.0) as u32 };
        let at = spawn_point(&room.spawn_zones, arena.0.half_extents, &player_pos, &mut rngs.director);
        for i in 0..n {
            let offset = gf_core::math::from_angle(i as f32 * 2.39996) * (0.9 * (i as f32).sqrt());
            let p = arena.0.resolve(at + offset, d.radius);
            spawn_enemy(&mut commands, &mut ids, &content, &tuning, enc.hp_mult, def, p, &mut rngs.director);
        }
        enc.alive += n;
        enc.budget_left -= cost * n as f32;
        enc.accum -= cost * n as f32;
    }
    enc.accum = enc.accum.clamp(-12.0, 6.0);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edge_spawns_stay_on_the_perimeter_and_away_from_players() {
        let mut rng = GfRng::new(3);
        let half = Vec2::new(22.0, 15.0);
        for _ in 0..200 {
            let p = spawn_point(&[SpawnZone::Edges { margin: 1.0 }], half, &[Vec2::ZERO], &mut rng);
            let on_x = (p.x.abs() - 21.0).abs() < 1e-3;
            let on_y = (p.y.abs() - 14.0).abs() < 1e-3;
            assert!(on_x || on_y, "{p}");
            assert!(p.length() >= 8.0);
        }
    }
}
