//! End-to-end session tests over the loopback transport: handshake, inputs, delta snapshots,
//! reliable actions under packet loss, and rejection paths.

use gf_core::forge::{ForgeAction, Slot};
use gf_core::ids::NetId;
use gf_net::quant::QPos;
use gf_net::transport::loopback;
use gf_net::*;

fn cfg(hash: u64) -> ServerConfig {
    ServerConfig {
        content_hash: hash,
        tick_hz: 60,
        snapshot_every: 1,
        remote_snapshot_every: 3,
        seed: 7,
        max_players: 4,
        allow_join_in_progress: true,
    }
}

fn enemy(id: u32, x: i16) -> EntityView {
    EntityView {
        id: NetId(id),
        kind: EntityKind::Enemy { def: 1 },
        pos: QPos(x, 0),
        motion: None,
        facing: 0,
        hp: 255,
        flags: EntityFlags::empty(),
        status: 0,
    }
}

fn connect<T: ServerTransport>(server: &mut NetServer<T>, client: &mut NetClient<loopback::LoopbackClient>) -> u8 {
    for _ in 0..10 {
        client.poll();
        server.poll();
        for ev in client.poll() {
            if let ClientEvent::Welcome { slot, .. } = ev {
                return slot;
            }
        }
    }
    panic!("no welcome");
}

fn tick_world<T: ServerTransport>(server: &mut NetServer<T>, tick: u32, entities: Vec<EntityView>) {
    server.broadcast(tick, &RunView::default(), &[], &mut |_| PrivateView::default(), entities, &[]);
}

#[test]
fn handshake_inputs_and_delta_snapshots() {
    let (lt, conn) = loopback::listener(NetConditions::ideal());
    let mut server = NetServer::new(lt, cfg(42));
    let mut client = NetClient::new(conn.connect(), "Valdris-main", Loadout::default(), 42);
    let slot = connect(&mut server, &mut client);
    assert_eq!(slot, 0);

    // Inputs flow in order.
    for i in 0..3 {
        client.send_command(PlayerCommand { fire: i % 2 == 0, ..Default::default() });
    }
    server.poll();
    let seqs: Vec<u32> = (0..3).map(|_| server.next_command(0).unwrap().seq).collect();
    assert_eq!(seqs, vec![1, 2, 3]);
    // Starved buffer repeats the last command.
    assert_eq!(server.next_command(0).unwrap().seq, 3);

    // Snapshot 1: full.
    tick_world(&mut server, 1, vec![enemy(1, 0), enemy(2, 0)]);
    let snaps: Vec<_> = client
        .poll()
        .into_iter()
        .filter_map(|e| match e {
            ClientEvent::Snapshot(s) => Some(s),
            _ => None,
        })
        .collect();
    assert_eq!(snaps.len(), 1);
    assert_eq!(snaps[0].entities.len(), 2);
    assert_eq!(snaps[0].ack_seq, 3);

    // Client acks tick 1 → snapshot 2 is a delta.
    client.send_command(PlayerCommand::default());
    server.poll();
    tick_world(&mut server, 2, vec![enemy(2, 50), enemy(3, 0)]);
    let world = client
        .poll()
        .into_iter()
        .find_map(|e| match e {
            ClientEvent::Snapshot(s) => Some(s),
            _ => None,
        })
        .unwrap();
    assert_eq!(world.entities, vec![enemy(2, 50), enemy(3, 0)]);
}

#[test]
fn actions_arrive_exactly_once_despite_loss() {
    let mut cond = NetConditions::ideal();
    cond.loss = 0.5;
    cond.seed = 99;
    let (lt, conn) = loopback::listener(cond);
    let mut server = NetServer::new(lt, cfg(1));
    let mut client = NetClient::new(conn.connect(), "p", Loadout::default(), 1);
    // Handshake is reliable-by-retry.
    let mut slot = None;
    for _ in 0..200 {
        for ev in client.poll() {
            if let ClientEvent::Welcome { slot: s, .. } = ev {
                slot = Some(s);
            }
        }
        server.poll();
        std::thread::sleep(std::time::Duration::from_millis(2));
        if slot.is_some() {
            break;
        }
    }
    let slot = slot.expect("connected despite loss");

    client.queue_action(PlayerAction::Forge(ForgeAction::Reroll { slot: Slot::Core }));
    client.queue_action(PlayerAction::ChooseDoor(1));
    let mut applied = Vec::new();
    for tick in 1..400u32 {
        client.send_command(PlayerCommand::default());
        server.poll();
        if let Some(cmd) = server.next_command(slot)
            && let Some((_, a)) = cmd.action
        {
            applied.push(a);
        }
        tick_world(&mut server, tick, vec![]);
        client.poll();
        if client.pending_actions() == 0 {
            break;
        }
    }
    assert_eq!(
        applied,
        vec![PlayerAction::Forge(ForgeAction::Reroll { slot: Slot::Core }), PlayerAction::ChooseDoor(1)],
        "each action applied exactly once, in order"
    );
    assert_eq!(client.pending_actions(), 0, "client saw the acks");
}

#[test]
fn rejects_content_mismatch_and_full_sessions() {
    let (lt, conn) = loopback::listener(NetConditions::ideal());
    let mut server = NetServer::new(lt, ServerConfig { max_players: 1, ..cfg(5) });
    let mut wrong = NetClient::new(conn.connect(), "modded", Loadout::default(), 6);
    for _ in 0..3 {
        wrong.poll();
        server.poll();
    }
    wrong.poll();
    assert_eq!(wrong.is_rejected(), Some(RejectReason::ContentMismatch { host: 5 }));

    let mut first = NetClient::new(conn.connect(), "a", Loadout::default(), 5);
    connect(&mut server, &mut first);
    let mut second = NetClient::new(conn.connect(), "b", Loadout::default(), 5);
    for _ in 0..3 {
        second.poll();
        server.poll();
    }
    second.poll();
    assert_eq!(second.is_rejected(), Some(RejectReason::Full));
}

#[test]
fn leaving_frees_the_slot() {
    let (lt, conn) = loopback::listener(NetConditions::ideal());
    let mut server = NetServer::new(lt, cfg(5));
    let mut a = NetClient::new(conn.connect(), "a", Loadout::default(), 5);
    assert_eq!(connect(&mut server, &mut a), 0);
    drop(a);
    let events = server.poll();
    assert_eq!(events, vec![SessionEvent::Left { slot: 0 }]);
    let mut b = NetClient::new(conn.connect(), "b", Loadout::default(), 5);
    assert_eq!(connect(&mut server, &mut b), 0);
}

#[test]
fn messages_round_trip_through_postcard() {
    let msg = ClientMsg::Hello {
        protocol: PROTOCOL_VERSION,
        content_hash: 9,
        name: "Selene".into(),
        loadout: Loadout { character: 1, chassis: 2, sigil: Some(3) },
        nonce: 77,
    };
    assert_eq!(decode::<ClientMsg>(&encode(&msg)).unwrap(), msg);
    assert!(decode::<ClientMsg>(&[0xFF, 0xFF, 0xFF]).is_err(), "garbage never panics");
}

#[test]
fn remote_peers_stream_at_20hz_without_losing_events() {
    // A loopback with simulated latency stands in for a remote link (1 ms each way).
    let (lt, conn) = loopback::listener(NetConditions::rtt(2, 0, 0.0));
    let mut server = NetServer::new(lt, cfg(9));
    let mut client = NetClient::new(conn.connect(), "remote", Loadout::default(), 9);
    let mut every = 0;
    for _ in 0..500 {
        client.poll();
        server.poll();
        std::thread::sleep(std::time::Duration::from_millis(1));
        for ev in client.poll() {
            if let ClientEvent::Welcome { snapshot_every, .. } = ev {
                every = snapshot_every;
            }
        }
        if every != 0 {
            break;
        }
    }
    assert_eq!(every, 3, "remote peers get the remote rate");

    // One cosmetic event per tick; snapshots only go out every third tick.
    for tick in 1..=30u32 {
        let events = [GameEvent::PlayerHurt { slot: 0, amount: tick as u16 }];
        server.broadcast(tick, &RunView::default(), &[], &mut |_| PrivateView::default(), vec![enemy(1, 0)], &events);
    }
    // The simulated link delays delivery, so keep polling until everything has landed.
    let mut ticks = Vec::new();
    let mut amounts = Vec::new();
    for _ in 0..100 {
        for ev in client.poll() {
            if let ClientEvent::Snapshot(s) = ev {
                ticks.push(s.tick);
                amounts.extend(s.events.iter().filter_map(|e| match e {
                    GameEvent::PlayerHurt { amount, .. } => Some(*amount),
                    _ => None,
                }));
            }
        }
        if ticks.len() >= 10 {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(1));
    }
    assert_eq!(ticks, (1..=10).map(|i| i * 3).collect::<Vec<u32>>());
    assert_eq!(amounts, (1..=30).collect::<Vec<u16>>(), "every event arrives, in order");
}

#[test]
fn the_host_player_streams_at_full_rate() {
    let (lt, conn) = loopback::listener(NetConditions::ideal());
    let mut server = NetServer::new(lt, cfg(10));
    let mut client = NetClient::new(conn.connect(), "host", Loadout::default(), 10);
    connect(&mut server, &mut client);
    for tick in 1..=6u32 {
        tick_world(&mut server, tick, vec![enemy(1, tick as i16)]);
    }
    let snaps = client.poll().into_iter().filter(|e| matches!(e, ClientEvent::Snapshot(_))).count();
    assert_eq!(snaps, 6);
}
