//! Client-side session: handshake with retry, redundant input sending, reliable actions, and
//! snapshot reconstruction from deltas.

use crate::delta;
use crate::protocol::*;
use crate::transport::{Channel, ClientTransport};
use crate::{decode, encode};
use std::collections::VecDeque;
use std::time::{Duration, Instant};

const HELLO_RETRY: Duration = Duration::from_millis(250);
const HISTORY: usize = 64;

#[derive(Clone, Debug, PartialEq)]
pub enum ClientEvent {
    Welcome { slot: u8, tick_hz: u16, snapshot_every: u8, seed: u64 },
    Rejected(RejectReason),
    Snapshot(Box<WorldSnapshot>),
    Roster(Vec<RosterEntry>),
}

#[derive(Clone, Debug, PartialEq)]
enum State {
    Connecting { last_hello: Option<Instant> },
    Connected { slot: u8 },
    Rejected(RejectReason),
}

pub struct NetClient<T: ClientTransport> {
    transport: T,
    name: String,
    loadout: Loadout,
    content_hash: u64,
    nonce: u32,
    state: State,
    history: VecDeque<(u32, Vec<EntityView>)>,
    sent: VecDeque<PlayerCommand>,
    next_seq: u32,
    actions: VecDeque<(u16, PlayerAction)>,
    next_action: u16,
    latest_tick: u32,
    /// Bytes received in the last `poll` (bandwidth telemetry).
    pub last_bytes_received: usize,
}

impl<T: ClientTransport> NetClient<T> {
    pub fn new(transport: T, name: impl Into<String>, loadout: Loadout, content_hash: u64) -> Self {
        let nonce =
            (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.subsec_nanos())) | 1;
        Self {
            transport,
            name: name.into(),
            loadout,
            content_hash,
            nonce,
            state: State::Connecting { last_hello: None },
            history: VecDeque::new(),
            sent: VecDeque::new(),
            next_seq: 1,
            actions: VecDeque::new(),
            next_action: 1,
            latest_tick: 0,
            last_bytes_received: 0,
        }
    }

    pub fn slot(&self) -> Option<u8> {
        match self.state {
            State::Connected { slot } => Some(slot),
            _ => None,
        }
    }

    pub fn is_rejected(&self) -> Option<RejectReason> {
        match self.state {
            State::Rejected(r) => Some(r),
            _ => None,
        }
    }

    /// Commands sent but not yet acknowledged by a snapshot (for prediction replay).
    pub fn unacked_commands(&self, ack_seq: u32) -> impl Iterator<Item = &PlayerCommand> {
        self.sent.iter().filter(move |c| c.seq > ack_seq)
    }

    /// Queue a must-happen-once action (forge, door choice, boon pick).
    pub fn queue_action(&mut self, action: PlayerAction) {
        let id = self.next_action;
        self.next_action = self.next_action.wrapping_add(1).max(1);
        self.actions.push_back((id, action));
    }

    pub fn pending_actions(&self) -> usize {
        self.actions.len()
    }

    fn say_hello(&mut self) {
        let hello = ClientMsg::Hello {
            protocol: PROTOCOL_VERSION,
            content_hash: self.content_hash,
            name: self.name.clone(),
            loadout: self.loadout,
            nonce: self.nonce,
        };
        self.transport.send(Channel::Reliable, &encode(&hello));
    }

    /// Process incoming traffic; resend the handshake while connecting.
    pub fn poll(&mut self) -> Vec<ClientEvent> {
        let mut out = Vec::new();
        self.last_bytes_received = 0;
        if let State::Connecting { last_hello } = self.state
            && last_hello.is_none_or(|t| t.elapsed() >= HELLO_RETRY)
        {
            self.say_hello();
            self.state = State::Connecting { last_hello: Some(Instant::now()) };
        }
        while let Some(bytes) = self.transport.poll() {
            self.last_bytes_received += bytes.len();
            let Ok(msg) = decode::<ServerMsg>(&bytes) else { continue };
            match msg {
                ServerMsg::Welcome { slot, nonce, tick, tick_hz, snapshot_every, seed } => {
                    if nonce != self.nonce {
                        continue;
                    }
                    if matches!(self.state, State::Connecting { .. }) {
                        self.state = State::Connected { slot };
                        self.latest_tick = tick;
                        out.push(ClientEvent::Welcome { slot, tick_hz, snapshot_every, seed });
                    }
                }
                ServerMsg::Reject { nonce, reason } => {
                    if nonce == self.nonce && matches!(self.state, State::Connecting { .. }) {
                        self.state = State::Rejected(reason);
                        out.push(ClientEvent::Rejected(reason));
                    }
                }
                ServerMsg::Roster(r) => out.push(ClientEvent::Roster(r)),
                ServerMsg::Snapshot(packet) => {
                    if let Some(world) = self.reconstruct(*packet) {
                        out.push(ClientEvent::Snapshot(Box::new(world)));
                    }
                }
            }
        }
        out
    }

    fn reconstruct(&mut self, p: SnapshotPacket) -> Option<WorldSnapshot> {
        if p.tick <= self.latest_tick && !self.history.is_empty() {
            return None; // stale / reordered
        }
        let entities = match p.baseline {
            None => {
                let mut e = p.changed;
                e.sort_by_key(|x| x.id);
                e
            }
            Some(b) => {
                let (_, base) = self.history.iter().find(|(t, _)| *t == b)?;
                delta::apply(base, &p.changed, &p.removed)
            }
        };
        // Drop acknowledged actions and commands.
        while self.actions.front().is_some_and(|(id, _)| {
            let d = p.ack_action.wrapping_sub(*id);
            d < u16::MAX / 2
        }) {
            self.actions.pop_front();
        }
        while self.sent.front().is_some_and(|c| c.seq <= p.ack_seq) && self.sent.len() > 1 {
            self.sent.pop_front();
        }
        self.latest_tick = p.tick;
        self.history.push_back((p.tick, entities.clone()));
        while self.history.len() > HISTORY {
            self.history.pop_front();
        }
        Some(WorldSnapshot {
            tick: p.tick,
            ack_seq: p.ack_seq,
            run: p.run,
            players: p.players,
            private: p.private,
            entities,
            events: p.events,
        })
    }

    /// Stamp, remember and send one tick's command (with redundancy and the oldest pending action).
    /// Returns the command as sent (with its `seq`).
    pub fn send_command(&mut self, mut cmd: PlayerCommand) -> PlayerCommand {
        cmd.seq = self.next_seq;
        self.next_seq += 1;
        cmd.action = self.actions.front().copied();
        self.sent.push_back(cmd);
        while self.sent.len() > 256 {
            self.sent.pop_front();
        }
        if matches!(self.state, State::Connected { .. }) {
            let n = self.sent.len();
            let commands: Vec<PlayerCommand> =
                self.sent.iter().skip(n.saturating_sub(INPUT_REDUNDANCY)).copied().collect();
            let frame = InputFrame { ack_tick: self.latest_tick, commands };
            self.transport.send(Channel::Unreliable, &encode(&ClientMsg::Input(frame)));
        }
        cmd
    }

    pub fn leave(&mut self) {
        self.transport.send(Channel::Reliable, &encode(&ClientMsg::Leave));
    }
}
