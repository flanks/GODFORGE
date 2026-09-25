//! # gf_sim — the authoritative simulation
//!
//! A headless Bevy ECS world stepped at a fixed 60 Hz by [`server::SimServer`]. Clients (including
//! the host's own player, over loopback) send commands through `gf_net`; the sim applies them,
//! steps, and streams delta snapshots back. Systems run single-threaded in a fixed order so a
//! seed + input log replays bit-identically (weekly seeds, server-validated leaderboards).
//!
//! All rules come from `gf_core`; all numbers come from `gf_content`.

pub mod abilities;
pub mod anvil;
pub mod boons;
pub mod bot;
pub mod components;
pub mod damage;
pub mod director;
pub mod enemies;
pub mod players;
pub mod projectiles;
pub mod resources;
pub mod run;
pub mod server;
pub mod snapshot;
pub mod spatial;
pub mod weapons;

use gf_engine::prelude::*;

pub use server::{SimConfig, SimServer};

/// The simulation tick schedule (run manually by `SimServer`, never by a Bevy runner).
#[derive(ScheduleLabel, Debug, Clone, PartialEq, Eq, Hash)]
pub struct SimTick;

/// Tick phases, strictly ordered.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub enum SimSet {
    Input,
    Players,
    Enemies,
    Spatial,
    Weapons,
    Combat,
    Damage,
    World,
    Cleanup,
}

/// Register every simulation system on the `SimTick` schedule.
pub fn build_schedule(app: &mut App) {
    let mut schedule = gf_engine::deterministic_schedule(SimTick);
    schedule.configure_sets(
        (
            SimSet::Input,
            SimSet::Players,
            SimSet::Enemies,
            SimSet::Spatial,
            SimSet::Weapons,
            SimSet::Combat,
            SimSet::Damage,
            SimSet::World,
            SimSet::Cleanup,
        )
            .chain(),
    );
    schedule
        .add_systems((players::apply_inputs, players::trigger_overdrive, players::pings).chain().in_set(SimSet::Input));
    schedule.add_systems(
        (
            players::player_movement,
            abilities::update_kits,
            abilities::cast_abilities,
            players::recompile_players,
            players::sync_blades,
        )
            .chain()
            .in_set(SimSet::Players),
    );
    schedule.add_systems((enemies::enemy_ai, enemies::boss_ai, enemies::enemy_motion).chain().in_set(SimSet::Enemies));
    schedule.add_systems(enemies::rebuild_grid.in_set(SimSet::Spatial));
    schedule.add_systems(
        (weapons::aim_and_fire, weapons::update_turrets, weapons::update_blades).chain().in_set(SimSet::Weapons),
    );
    schedule.add_systems(
        (
            projectiles::move_projectiles,
            projectiles::move_enemy_shots,
            projectiles::update_hazards,
            enemies::update_telegraphs,
            enemies::contact_damage,
            projectiles::update_barricades,
            damage::tick_statuses,
        )
            .chain()
            .in_set(SimSet::Combat),
    );
    schedule.add_systems(
        (damage::resolve_damage, damage::resolve_player_hits, damage::process_kills).chain().in_set(SimSet::Damage),
    );
    schedule.add_systems(
        (
            players::collect_pickups,
            anvil::anvil_update,
            anvil::forge_actions,
            boons::boon_actions,
            director::run_director,
            players::life_update,
            run::room_flow,
            run::door_choice,
            run::room_transition,
        )
            .chain()
            .in_set(SimSet::World),
    );
    schedule.add_systems((run::cleanup_expired, run::advance_clock).chain().in_set(SimSet::Cleanup));
    app.add_schedule(schedule);
}
