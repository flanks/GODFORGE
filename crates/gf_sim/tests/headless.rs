//! Headless bot runs through the real netcode path (loopback): the nightly bot run in miniature.
//! Crash-free play, the forge loop happening, rooms clearing, co-op, stress and determinism.

use gf_content::{ContentDb, Phase, RoomKind, find_content_dir, procgen};
use gf_core::aim::AimMode;
use gf_net::transport::loopback;
use gf_net::{ClientEvent, Loadout, NetClient, NetConditions, RunPhase};
use gf_sim::bot::{BotBrain, run_headless};
use gf_sim::resources::{RoomLayout, RunState};
use gf_sim::{SimConfig, SimServer};
use std::collections::BTreeMap;
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

#[test]
fn every_peer_rebuilds_the_hosts_procedural_arenas() {
    // The host replicates only (template, seed) per room; a client or bot rebuilding the layout
    // from the snapshot must get exactly the arena the host simulates, or prediction, bot
    // steering and the rendered walls would disagree with the authoritative sim.
    let db = content();
    let cfg = SimConfig { phase: Phase::P1, seed: 7, ..Default::default() };
    let (listener, connector) = loopback::listener(NetConditions::ideal());
    let mut server = SimServer::new(db.clone(), cfg, Box::new(listener));
    let mut client = NetClient::new(connector.connect(), "bot", loadout(&db, "valdris"), db.hash);
    let mut brain = BotBrain::new(0, AimMode::Auto, 7);
    // serial -> (template, seed, kind) as the client saw it.
    let mut seen: BTreeMap<u32, (u16, u32, RoomKind)> = BTreeMap::new();
    let mut latest = None;
    for _ in 0..60 * 60 * 30 {
        for ev in client.poll() {
            match ev {
                ClientEvent::Welcome { slot, .. } => brain.slot = slot,
                ClientEvent::Snapshot(w) => latest = Some(w),
                _ => {}
            }
        }
        if let Some(w) = latest.as_deref() {
            let run = &w.run;
            let host = server.world().resource::<RunState>();
            // Compare only while the host is still in the room the snapshot describes.
            if run.room_serial == host.room_serial && !seen.contains_key(&run.room_serial) {
                let rebuilt = procgen::resolve_room(&db, run.room, run.room_seed);
                let layout = server.world().resource::<RoomLayout>();
                assert_eq!(*layout.0, rebuilt, "room {} ({}) diverged on the client", run.room_serial, layout.0.key);
                assert_eq!((run.room, run.room_seed), (host.room.0, host.room_seed));
                seen.insert(run.room_serial, (run.room, run.room_seed, rebuilt.kind));
            }
            let (cmd, action) = brain.think(w, &db);
            if let Some(a) = action {
                client.queue_action(a);
            }
            client.send_command(cmd);
        }
        server.tick();
        if matches!(server.run_phase(), RunPhase::Victory | RunPhase::Defeat) {
            break;
        }
    }
    assert!(seen.len() >= 5, "the run should visit several rooms: {seen:?}");
    let generated: Vec<u32> =
        seen.values().filter(|(_, _, kind)| procgen::is_generated_kind(*kind)).map(|(_, seed, _)| *seed).collect();
    assert!(generated.len() >= 3, "{seen:?}");
    assert!(generated.iter().all(|s| *s != 0), "generated rooms need a layout seed: {seen:?}");
    let mut distinct = generated.clone();
    distinct.sort_unstable();
    distinct.dedup();
    assert_eq!(distinct.len(), generated.len(), "no two rooms of a run share a layout: {seen:?}");
    let bosses: Vec<_> = seen.values().filter(|(_, _, k)| matches!(k, RoomKind::Boss | RoomKind::MiniBoss)).collect();
    assert!(!bosses.is_empty(), "the slice ends in a boss room: {seen:?}");
    assert!(bosses.iter().all(|(_, seed, _)| *seed == 0), "hand-built arenas replicate seed 0: {seen:?}");
}

#[test]
fn qa_room_requests_pin_or_generate_layouts() {
    let db = content();
    let gate = db.rooms.id("cinder_gate").expect("slice opening room");
    let start = |room: &str| {
        let cfg = SimConfig { seed: 7, start_room: Some(room.into()), ..Default::default() };
        let (listener, connector) = loopback::listener(NetConditions::ideal());
        let mut server = SimServer::new(db.clone(), cfg, Box::new(listener));
        let mut client = NetClient::new(connector.connect(), "qa", loadout(&db, "valdris"), db.hash);
        for _ in 0..30 {
            client.poll();
            server.tick();
            if server.world().resource::<RunState>().started {
                break;
            }
        }
        let run = server.world().resource::<RunState>();
        assert!(run.started, "the run starts once a player joins");
        (run.room.0, run.room_seed, server.world().resource::<RoomLayout>().0.key.clone())
    };
    let (room, seed, key) = start("cinder_gate");
    assert_eq!(room, gate);
    assert_ne!(seed, 0, "a plain key is laid out from the run seed");
    assert_eq!(start(&key), (room, seed, key.clone()), "a printed layout key reproduces that layout");
    assert_eq!(start("cinder_gate~0"), (gate, 0, "cinder_gate".into()), "~0 is the authored template");
}
