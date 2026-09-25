//! Session link: host thread (solo/listen), transport, snapshot intake, input sending at the sim
//! rate, and client-side prediction + reconciliation of the local player's movement.

use crate::input::InputState;
use crate::{ClientConfig, ClientSet, Connect};
use gf_content::{ContentDb, RoomDef, procgen};
use gf_core::movement::{Arena, MoveInput, MoverState, step_mover};
use gf_engine::prelude::*;
use gf_net::transport::{loopback, udp};
use gf_net::*;
use gf_sim::SimServer;
use std::collections::VecDeque;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

/// The client's view of the session.
#[derive(Resource)]
pub struct Link {
    pub client: NetClient<Box<dyn ClientTransport>>,
    pub slot: Option<u8>,
    pub latest: Option<Arc<WorldSnapshot>>,
    /// Engine time (s) when `latest` arrived.
    pub received_at: f64,
    pub snapshot_every: u8,
    pub roster: Vec<RosterEntry>,
    pub rejected: Option<RejectReason>,
    /// Cosmetic events that arrived this frame.
    pub fresh_events: Vec<GameEvent>,
    pub bytes_per_sec: f32,
    pub host_label: String,
    host: Option<(Arc<AtomicBool>, std::thread::JoinHandle<()>)>,
    bots: Option<(Arc<AtomicBool>, std::thread::JoinHandle<()>)>,
}

impl Link {
    pub fn me(&self) -> Option<&PlayerView> {
        let slot = self.slot?;
        self.latest.as_ref()?.players.iter().find(|p| p.slot == slot)
    }

    /// Fractional server tick to render at (straight-line motion is extrapolated to this).
    pub fn render_tick(&self, now: f64) -> f64 {
        let Some(w) = &self.latest else { return 0.0 };
        let since = ((now - self.received_at) * gf_core::SIM_HZ as f64).clamp(0.0, 6.0);
        w.tick as f64 + since * w.run.time_scale.max(0.05) as f64
    }

    pub fn shutdown(&mut self) {
        self.client.leave();
        if let Some((stop, handle)) = self.bots.take() {
            stop.store(true, Ordering::Relaxed);
            let _ = handle.join();
        }
        if let Some((stop, handle)) = self.host.take() {
            stop.store(true, Ordering::Relaxed);
            let _ = handle.join();
        }
    }
}

impl Drop for Link {
    fn drop(&mut self) {
        for (stop, _) in self.bots.iter().chain(self.host.iter()) {
            stop.store(true, Ordering::Relaxed);
        }
    }
}

/// Start (or restart) a session according to the config.
pub fn start_link(cfg: &ClientConfig) -> Link {
    let content = cfg.content.clone();
    let mut bot_connector = None;
    let (transport, host, label): (Box<dyn ClientTransport>, _, String) = match &cfg.connect {
        Connect::Local(sim) => {
            let (listener, conn) = loopback::listener(NetConditions::ideal());
            let host = SimServer::spawn_thread(content.clone(), sim.clone(), Box::new(listener));
            bot_connector = Some((conn.clone(), sim.seed));
            let label = if cfg.party.is_empty() {
                "solo (local host)".into()
            } else {
                format!("local host + {} bots", cfg.party.len())
            };
            (Box::new(conn.connect()), Some(host), label)
        }
        Connect::Host(sim, port) => {
            let (listener, conn) = loopback::listener(NetConditions::ideal());
            bot_connector = Some((conn.clone(), sim.seed));
            let transport: Box<dyn ServerTransport> = match udp::UdpServer::bind(("0.0.0.0", *port)) {
                Ok(server) => Box::new(CompositeServer::new(Box::new(listener), Box::new(server))),
                Err(e) => {
                    warn!("could not bind UDP port {port}: {e}; hosting locally only");
                    Box::new(listener)
                }
            };
            let mut sim = sim.clone();
            sim.snapshot_every = sim.snapshot_every.max(1);
            let host = SimServer::spawn_thread(content.clone(), sim, transport);
            (Box::new(conn.connect()), Some(host), format!("hosting on UDP :{port}"))
        }
        Connect::Join(addr) => match udp::UdpClient::connect(addr.as_str()) {
            Ok(c) => (Box::new(c), None, format!("joined {addr}")),
            Err(e) => {
                warn!("could not reach {addr}: {e}; falling back to solo");
                let (listener, conn) = loopback::listener(NetConditions::ideal());
                let host = SimServer::spawn_thread(content.clone(), gf_sim::SimConfig::default(), Box::new(listener));
                (Box::new(conn.connect()), Some(host), "solo (join failed)".into())
            }
        },
    };
    // Say hello before the bot teammates do, so the player takes slot 0 (P1 gold).
    let mut client = NetClient::new(transport, cfg.name.clone(), cfg.loadout, content.hash);
    let _ = client.poll();
    let bots = match bot_connector {
        Some((conn, seed)) if !cfg.party.is_empty() => {
            let members = cfg
                .party
                .iter()
                .map(|l| (Box::new(conn.connect()) as Box<dyn ClientTransport>, *l, gf_core::aim::AimMode::Auto))
                .collect();
            Some(gf_sim::bot::spawn_bot_party(content.clone(), members, seed))
        }
        _ => None,
    };
    Link {
        client,
        slot: None,
        latest: None,
        received_at: 0.0,
        snapshot_every: 1,
        roster: Vec::new(),
        rejected: None,
        fresh_events: Vec::new(),
        bytes_per_sec: 0.0,
        host_label: label,
        host,
        bots,
    }
}

/// The current room's layout, rebuilt locally from the replicated template + seed (the host never
/// sends geometry). Updated in [`ClientSet::Net`] before anything reads it this frame.
#[derive(Resource)]
pub struct CurrentRoom {
    /// (room serial, template, seed) the layout was built for.
    key: Option<(u32, u16, u32)>,
    /// Bumped on every layout change (0 = no room yet), so a new session that reuses a serial
    /// still rebuilds.
    pub generation: u32,
    pub def: Arc<RoomDef>,
}

impl Default for CurrentRoom {
    fn default() -> Self {
        Self { key: None, generation: 0, def: Arc::new(RoomDef::placeholder()) }
    }
}

impl CurrentRoom {
    /// Rebuild when the snapshot names a different room. Returns true when the room changed.
    pub fn sync(&mut self, run: &RunView, db: &ContentDb) -> bool {
        let key = (run.room_serial, run.room, run.room_seed);
        if self.key == Some(key) {
            return false;
        }
        self.key = Some(key);
        self.generation += 1;
        self.def = Arc::new(procgen::resolve_room(db, run.room, run.room_seed));
        true
    }
}

/// Client-side prediction of the local player's movement.
#[derive(Resource, Default)]
pub struct Prediction {
    pub state: Option<MoverState>,
    pending: VecDeque<(u32, MoveInput)>,
    /// The room's collision world: replaced whole on a room change, never cloned per tick.
    arena: Arc<Arena>,
    last_presses: Presses,
    /// Visual offset left by corrections, decays to zero (no snapping).
    pub error: Vec2,
    pub corrections: u32,
}

fn move_input(cmd: &PlayerCommand, dash_edge: bool, me: &PlayerView) -> MoveInput {
    MoveInput {
        dir: gf_net::quant::i8_to_stick(cmd.move_dir),
        dash: dash_edge,
        speed: me.move_speed,
        max_dash_charges: me.max_dash,
        dash_recharge: me.dash_recharge,
        can_move: !me.flags.contains(PlayerFlags::STANCE),
        can_dash: !me.flags.contains(PlayerFlags::STANCE),
        wraith: matches!(me.life, gf_core::revive::LifeState::Downed { .. }),
    }
}

pub fn build(app: &mut App) {
    let cfg = app.world().resource::<ClientConfig>().clone();
    app.insert_resource(start_link(&cfg))
        .init_resource::<Prediction>()
        .init_resource::<CurrentRoom>()
        .add_systems(Update, poll_link.in_set(ClientSet::Net))
        .add_systems(FixedUpdate, send_command)
        .add_systems(Last, shutdown_on_exit);
}

fn poll_link(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    mut link: ResMut<Link>,
    mut pred: ResMut<Prediction>,
    mut room: ResMut<CurrentRoom>,
) {
    link.fresh_events.clear();
    let now = time.elapsed_secs_f64();
    let dt = time.delta_secs().max(1e-4);
    let events = link.client.poll();
    let bytes = link.client.last_bytes_received as f32;
    link.bytes_per_sec += (bytes / dt - link.bytes_per_sec) * (1.0 - (-dt * 2.0).exp());
    for ev in events {
        match ev {
            ClientEvent::Welcome { slot, snapshot_every, .. } => {
                link.slot = Some(slot);
                link.snapshot_every = snapshot_every;
                info!("joined as player {}", slot + 1);
            }
            ClientEvent::Rejected(r) => {
                warn!("rejected by host: {r:?}");
                link.rejected = Some(r);
            }
            ClientEvent::Roster(r) => link.roster = r,
            ClientEvent::Snapshot(w) => {
                link.fresh_events.extend(w.events.iter().copied());
                let new_room = room.sync(&w.run, &cfg.content);
                if new_room {
                    pred.arena = Arc::new(room.def.arena());
                }
                if let Some(slot) = link.slot {
                    reconcile(&mut pred, &w, slot, &cfg, new_room);
                }
                link.latest = Some(Arc::new(*w));
                link.received_at = now;
            }
        }
    }
    // Decay the correction offset.
    let k = 1.0 - (-12.0 * dt).exp();
    let e = pred.error;
    pred.error -= e * k;
}

fn reconcile(pred: &mut Prediction, w: &WorldSnapshot, slot: u8, cfg: &ClientConfig, new_room: bool) {
    let Some(me) = w.players.iter().find(|p| p.slot == slot) else {
        pred.state = None;
        return;
    };
    if new_room || pred.state.is_none() {
        pred.pending.clear();
        pred.state = Some(me.mover);
        pred.error = Vec2::ZERO;
        return;
    }
    pred.pending.retain(|(seq, _)| *seq > w.ack_seq);
    let mut state = me.mover;
    let replay =
        !me.flags.contains(PlayerFlags::AIRBORNE) && !matches!(me.life, gf_core::revive::LifeState::Reforging { .. });
    if replay {
        let tuning = cfg.content.game.movement;
        let dt = gf_core::SIM_DT * w.run.time_scale.max(0.05);
        for (_, mi) in &pred.pending {
            step_mover(&mut state, mi, &tuning, dt, &pred.arena, me.radius);
        }
    } else {
        pred.pending.clear();
    }
    if let Some(old) = pred.state {
        let delta = old.pos - state.pos;
        if delta.length() > 0.02 {
            pred.corrections += 1;
        }
        pred.error = (pred.error + delta).clamp_length_max(1.5);
    }
    pred.state = Some(state);
}

fn send_command(
    cfg: Res<ClientConfig>,
    mut link: ResMut<Link>,
    mut input: ResMut<InputState>,
    mut pred: ResMut<Prediction>,
) {
    if link.slot.is_none() {
        return;
    }
    for a in input.actions.drain(..) {
        link.client.queue_action(a);
    }
    let cmd = input.command();
    let sent = link.client.send_command(cmd);
    let dash_edge = sent.presses.dash != pred.last_presses.dash;
    pred.last_presses = sent.presses;
    let Some(me) = link.me().cloned() else { return };
    let time_scale = link.latest.as_ref().map_or(1.0, |w| w.run.time_scale.max(0.05));
    if me.flags.contains(PlayerFlags::AIRBORNE) {
        return;
    }
    let mi = move_input(&sent, dash_edge, &me);
    let pred = &mut *pred;
    if let Some(state) = pred.state.as_mut() {
        step_mover(state, &mi, &cfg.content.game.movement, gf_core::SIM_DT * time_scale, &pred.arena, me.radius);
        pred.pending.push_back((sent.seq, mi));
        while pred.pending.len() > 240 {
            pred.pending.pop_front();
        }
    }
}

fn shutdown_on_exit(mut exits: MessageReader<AppExit>, mut link: ResMut<Link>) {
    if exits.read().next().is_some() {
        link.shutdown();
    }
}
