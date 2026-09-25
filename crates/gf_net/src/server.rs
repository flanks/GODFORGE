//! Host-side session: handshake, per-client jitter buffers, exactly-once actions, per-client delta
//! snapshots against acknowledged baselines.

use crate::delta;
use crate::protocol::*;
use crate::transport::{Channel, PeerId, ServerIncoming, ServerTransport};
use crate::{decode, encode};
use std::collections::VecDeque;

#[derive(Clone, Debug)]
pub struct ServerConfig {
    pub content_hash: u64,
    pub tick_hz: u16,
    /// Snapshot every N ticks for same-machine peers (1 = 60 Hz for the host's own player).
    pub snapshot_every: u8,
    /// Snapshot every N ticks for remote peers (3 = 20 Hz, §14). Cosmetic events accumulate per
    /// client between its snapshots, so a slower stream never drops one.
    pub remote_snapshot_every: u8,
    pub seed: u64,
    pub max_players: usize,
    pub allow_join_in_progress: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SessionEvent {
    Joined { slot: u8, name: String, loadout: Loadout },
    Left { slot: u8 },
}

struct Client {
    peer: PeerId,
    slot: u8,
    name: String,
    loadout: Loadout,
    queue: VecDeque<PlayerCommand>,
    last_seq: u32,
    last_cmd: PlayerCommand,
    ack_tick: Option<u32>,
    last_action: u16,
    /// This client's snapshot interval in ticks.
    every: u8,
    /// Cosmetic events since this client's last snapshot.
    pending_events: Vec<GameEvent>,
}

/// Cosmetic events buffered per client between snapshots (oldest dropped beyond this; they are
/// hit sparks and toasts, never gameplay state).
const MAX_PENDING_EVENTS: usize = 768;

/// Snapshots kept for delta baselines.
const HISTORY: usize = 64;
/// Jitter buffer bounds (commands).
const MAX_QUEUE: usize = 6;
const TRIM_TO: usize = 2;

pub struct NetServer<T: ServerTransport> {
    transport: T,
    cfg: ServerConfig,
    clients: Vec<Client>,
    history: VecDeque<(u32, Vec<EntityView>)>,
    tick: u32,
    started: bool,
    roster_dirty: bool,
    /// Bytes sent in the last `broadcast` (telemetry / bandwidth budget).
    pub last_bytes_sent: usize,
}

impl<T: ServerTransport> NetServer<T> {
    pub fn new(transport: T, cfg: ServerConfig) -> Self {
        Self {
            transport,
            cfg,
            clients: Vec::new(),
            history: VecDeque::new(),
            tick: 0,
            started: false,
            roster_dirty: false,
            last_bytes_sent: 0,
        }
    }

    pub fn config(&self) -> &ServerConfig {
        &self.cfg
    }

    /// Mark the run as started (joins are refused unless `allow_join_in_progress`).
    pub fn set_started(&mut self, started: bool) {
        self.started = started;
    }

    pub fn player_count(&self) -> usize {
        self.clients.len()
    }

    pub fn slots(&self) -> impl Iterator<Item = u8> + '_ {
        self.clients.iter().map(|c| c.slot)
    }

    pub fn loadout(&self, slot: u8) -> Option<(String, Loadout)> {
        self.clients.iter().find(|c| c.slot == slot).map(|c| (c.name.clone(), c.loadout))
    }

    fn free_slot(&self) -> Option<u8> {
        (0..self.cfg.max_players.min(MAX_PLAYERS) as u8).find(|s| !self.clients.iter().any(|c| c.slot == *s))
    }

    fn send(&mut self, peer: PeerId, ch: Channel, msg: &ServerMsg) -> usize {
        let bytes = encode(msg);
        self.transport.send(peer, ch, &bytes);
        bytes.len()
    }

    /// Process all incoming traffic. Call once per tick before simulating.
    pub fn poll(&mut self) -> Vec<SessionEvent> {
        let mut events = Vec::new();
        while let Some(incoming) = self.transport.poll() {
            match incoming {
                ServerIncoming::Connected(_) => {}
                ServerIncoming::Disconnected(peer) => {
                    if let Some(i) = self.clients.iter().position(|c| c.peer == peer) {
                        let c = self.clients.remove(i);
                        events.push(SessionEvent::Left { slot: c.slot });
                        self.roster_dirty = true;
                    }
                }
                ServerIncoming::Message(peer, bytes) => {
                    let Ok(msg) = decode::<ClientMsg>(&bytes) else { continue };
                    self.handle(peer, msg, &mut events);
                }
            }
        }
        if self.roster_dirty {
            self.roster_dirty = false;
            let roster: Vec<RosterEntry> = self
                .clients
                .iter()
                .map(|c| RosterEntry { slot: c.slot, name: c.name.clone(), loadout: c.loadout, connected: true })
                .collect();
            let peers: Vec<PeerId> = self.clients.iter().map(|c| c.peer).collect();
            for p in peers {
                self.send(p, Channel::Reliable, &ServerMsg::Roster(roster.clone()));
            }
        }
        events
    }

    fn handle(&mut self, peer: PeerId, msg: ClientMsg, events: &mut Vec<SessionEvent>) {
        match msg {
            ClientMsg::Hello { protocol, content_hash, name, loadout, nonce } => {
                // Idempotent: a resent Hello from a joined peer just gets the Welcome again.
                if let Some(c) = self.clients.iter().find(|c| c.peer == peer) {
                    let welcome = ServerMsg::Welcome {
                        slot: c.slot,
                        nonce,
                        tick: self.tick,
                        tick_hz: self.cfg.tick_hz,
                        snapshot_every: c.every,
                        seed: self.cfg.seed,
                    };
                    self.send(peer, Channel::Reliable, &welcome);
                    return;
                }
                let reject = if protocol != PROTOCOL_VERSION {
                    Some(RejectReason::ProtocolMismatch { host: PROTOCOL_VERSION })
                } else if content_hash != self.cfg.content_hash {
                    Some(RejectReason::ContentMismatch { host: self.cfg.content_hash })
                } else if self.started && !self.cfg.allow_join_in_progress {
                    Some(RejectReason::RunInProgress)
                } else if self.free_slot().is_none() {
                    Some(RejectReason::Full)
                } else {
                    None
                };
                if let Some(reason) = reject {
                    self.send(peer, Channel::Reliable, &ServerMsg::Reject { nonce, reason });
                    return;
                }
                let slot = self.free_slot().expect("checked above");
                let every = if self.transport.is_local(peer) {
                    self.cfg.snapshot_every
                } else {
                    self.cfg.remote_snapshot_every
                };
                let every = every.max(1);
                self.clients.push(Client {
                    peer,
                    slot,
                    name: name.clone(),
                    loadout,
                    queue: VecDeque::new(),
                    last_seq: 0,
                    last_cmd: PlayerCommand::default(),
                    ack_tick: None,
                    last_action: 0,
                    every,
                    pending_events: Vec::new(),
                });
                self.clients.sort_by_key(|c| c.slot);
                let welcome = ServerMsg::Welcome {
                    slot,
                    nonce,
                    tick: self.tick,
                    tick_hz: self.cfg.tick_hz,
                    snapshot_every: every,
                    seed: self.cfg.seed,
                };
                self.send(peer, Channel::Reliable, &welcome);
                events.push(SessionEvent::Joined { slot, name, loadout });
                self.roster_dirty = true;
            }
            ClientMsg::Input(frame) => {
                let Some(c) = self.clients.iter_mut().find(|c| c.peer == peer) else { return };
                if c.ack_tick.is_none_or(|a| frame.ack_tick > a) {
                    c.ack_tick = Some(frame.ack_tick);
                }
                for cmd in frame.commands {
                    let queued_max = c.queue.back().map_or(c.last_seq, |q| q.seq);
                    if cmd.seq > queued_max {
                        c.queue.push_back(cmd);
                    }
                }
                if c.queue.len() > MAX_QUEUE {
                    // Latency spike recovered: skip ahead. Press counters are cumulative and
                    // actions repeat until acked, so skipping loses no input.
                    while c.queue.len() > TRIM_TO {
                        c.queue.pop_front();
                    }
                }
            }
            ClientMsg::Leave => {
                if let Some(i) = self.clients.iter().position(|c| c.peer == peer) {
                    let c = self.clients.remove(i);
                    events.push(SessionEvent::Left { slot: c.slot });
                    self.roster_dirty = true;
                }
            }
        }
    }

    /// The command to simulate for `slot` this tick. Starved buffers repeat the last command
    /// (held inputs persist, no new presses). Actions are delivered exactly once.
    pub fn next_command(&mut self, slot: u8) -> Option<PlayerCommand> {
        let c = self.clients.iter_mut().find(|c| c.slot == slot)?;
        let mut cmd = match c.queue.pop_front() {
            Some(cmd) => {
                c.last_seq = cmd.seq;
                cmd
            }
            None => c.last_cmd,
        };
        match cmd.action {
            Some((id, _)) if id_newer(id, c.last_action) => c.last_action = id,
            _ => cmd.action = None,
        }
        c.last_cmd = PlayerCommand { action: None, ..cmd };
        Some(cmd)
    }

    /// Send this tick's snapshot to every client that is due (each client has its own rate).
    /// Events are buffered per client and delivered with its next snapshot.
    pub fn broadcast(
        &mut self,
        tick: u32,
        run: &RunView,
        players: &[PlayerView],
        private: &mut dyn FnMut(u8) -> PrivateView,
        mut entities: Vec<EntityView>,
        events: &[GameEvent],
    ) {
        self.tick = tick;
        self.last_bytes_sent = 0;
        for c in &mut self.clients {
            c.pending_events.extend_from_slice(events);
            if c.pending_events.len() > MAX_PENDING_EVENTS {
                let excess = c.pending_events.len() - MAX_PENDING_EVENTS;
                c.pending_events.drain(..excess);
            }
        }
        let targets: Vec<(PeerId, u8, Option<u32>, u32, u16, Vec<GameEvent>)> = self
            .clients
            .iter_mut()
            .filter(|c| tick.is_multiple_of(c.every as u32))
            .map(|c| (c.peer, c.slot, c.ack_tick, c.last_seq, c.last_action, std::mem::take(&mut c.pending_events)))
            .collect();
        if targets.is_empty() {
            return;
        }
        entities.sort_by_key(|e| e.id);
        for (peer, slot, ack, ack_seq, ack_action, events) in targets {
            let base = ack.and_then(|a| self.history.iter().find(|(t, _)| *t == a));
            let (baseline, changed, removed) = match base {
                Some((t, b)) => {
                    let (c, r) = delta::diff(b, &entities);
                    (Some(*t), c, r)
                }
                None => (None, entities.clone(), Vec::new()),
            };
            let packet = SnapshotPacket {
                tick,
                baseline,
                ack_seq,
                ack_action,
                run: run.clone(),
                players: players.to_vec(),
                private: private(slot),
                changed,
                removed,
                events,
            };
            self.last_bytes_sent += self.send(peer, Channel::Unreliable, &ServerMsg::Snapshot(Box::new(packet)));
        }
        self.history.push_back((tick, entities));
        while self.history.len() > HISTORY {
            self.history.pop_front();
        }
    }
}

/// Wrapping comparison for u16 action ids.
fn id_newer(id: u16, last: u16) -> bool {
    let d = id.wrapping_sub(last);
    d != 0 && d < u16::MAX / 2
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn action_ids_wrap() {
        assert!(id_newer(1, 0));
        assert!(!id_newer(0, 0));
        assert!(id_newer(0, u16::MAX));
        assert!(!id_newer(5, 10));
    }
}
