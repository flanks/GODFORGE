//! Headless bot runs through the real netcode path (loopback): the nightly bot run in miniature.
//! Crash-free play, the forge loop happening, rooms clearing, co-op, stress and determinism.

use gf_content::{ContentDb, Phase, find_content_dir};
use gf_core::aim::AimMode;
use gf_net::{Loadout, NetConditions, RunPhase};
use gf_sim::SimConfig;
use gf_sim::bot::run_headless;
use std::sync::Arc;

fn content() -> Arc<ContentDb> {
    Arc::new(ContentDb::load_dir(&find_content_dir()).expect("content"))
}

fn loadout(db: &ContentDb, character: &str) -> Loadout {
    let id = db.characters.id(character).unwrap();
    let chassis = db.chassis.id(&db.characters.get(id).signature_chassis).unwrap();
    Loadout { character: id, chassis, sigil: None }
}

#[test]
fn solo_valdris_auto_clears_rooms_and_forges() {
    let db = content();
    let cfg = SimConfig { phase: Phase::P1, seed: 11, ..Default::default() };
    let report =
        run_headless(db.clone(), cfg, &[(loadout(&db, "valdris"), AimMode::Auto)], 60 * 60 * 4, NetConditions::ideal());
    assert!(report.kills > 100, "bot should be killing things: {report:#?}");
    assert!(report.depth >= 2, "rooms should clear and doors lead onward: {report:#?}");
    assert!(report.bots[0].parts.len() >= 2, "the forge loop should have equipped parts: {report:#?}");
}

#[test]
fn full_run_is_completable_in_auto_and_manual() {
    // Acceptance #8: the same seed can be completed in AUTO and in MANUAL.
    let db = content();
    for mode in [AimMode::Auto, AimMode::Manual] {
        let cfg = SimConfig { phase: Phase::P1, seed: 7, ..Default::default() };
        let r = run_headless(db.clone(), cfg, &[(loadout(&db, "valdris"), mode)], 60 * 60 * 30, NetConditions::ideal());
        assert_eq!(r.outcome, RunPhase::Victory, "{mode:?}: {r:#?}");
    }
}

#[test]
fn four_player_coop_completes_the_slice() {
    let db = content();
    let cfg = SimConfig { phase: Phase::P1, seed: 3, ..Default::default() };
    let bots: Vec<_> =
        ["valdris", "selene", "kael", "valdris"].iter().map(|c| (loadout(&db, c), AimMode::Auto)).collect();
    let r = run_headless(db, cfg, &bots, 60 * 60 * 30, NetConditions::ideal());
    assert_eq!(r.outcome, RunPhase::Victory, "{r:#?}");
    assert_eq!(r.bots.len(), 4);
    assert!(r.max_enemies > 120, "co-op scaling should raise density: {}", r.max_enemies);
}

#[test]
fn chaos_stress_scene_stays_within_budget() {
    // §20.7: 4 players, 400 enemies, max builds. Host tick must stay far inside 16.7 ms.
    let db = content();
    let cfg = SimConfig { phase: Phase::P1, seed: 1, stress_enemies: Some(400), ..Default::default() };
    let bots: Vec<_> =
        ["valdris", "selene", "kael", "valdris"].iter().map(|c| (loadout(&db, c), AimMode::Auto)).collect();
    let r = run_headless(db, cfg, &bots, 60 * 20, NetConditions::ideal());
    assert!(r.max_enemies >= 400, "{r:#?}");
    // Debug builds are much slower than release; this still catches pathological regressions.
    assert!(r.p99_tick_ms < 16.7, "p99 tick {:.2} ms", r.p99_tick_ms);
}

#[test]
fn same_seed_same_run() {
    // Weekly seeds and server-validated leaderboards need bit-identical replays.
    let db = content();
    let run = || {
        let cfg = SimConfig { phase: Phase::P1, seed: 42, ..Default::default() };
        run_headless(db.clone(), cfg, &[(loadout(&db, "selene"), AimMode::Auto)], 60 * 90, NetConditions::ideal())
    };
    let (a, b) = (run(), run());
    assert_eq!((a.kills, a.depth, a.ticks, a.ember), (b.kills, b.depth, b.ticks, b.ember));
    assert_eq!(a.bots[0].damage, b.bots[0].damage);
}

#[test]
fn survives_lossy_high_latency_links() {
    let db = content();
    let cfg = SimConfig { phase: Phase::P1, seed: 5, ..Default::default() };
    let r = run_headless(
        db.clone(),
        cfg,
        &[(loadout(&db, "kael"), AimMode::Auto)],
        60 * 60,
        NetConditions { loss: 0.1, ..NetConditions::ideal() },
    );
    assert!(r.kills > 20, "{r:#?}");
}
