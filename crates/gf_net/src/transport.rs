//! Transports. The protocol tolerates loss everywhere (redundant inputs, reliable-over-unreliable
//! actions, acked delta baselines), so a transport only needs to move datagrams.
//!
//! - [`loopback`]: in-process channels with optional simulated latency / jitter / loss. The host's
//!   own player always connects through this — same code path as a remote client.
//! - [`udp`]: plain UDP for LAN play and non-Steam test builds.
//! - Steam Datagram Relay (steamworks-rs `NetworkingSockets`) implements the same two traits; its
//!   `Channel::Reliable` maps to `k_nSteamNetworkingSend_Reliable` (see docs/ARCHITECTURE.md).

use std::time::{Duration, Instant};

pub type PeerId = u32;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Channel {
    Unreliable,
    Reliable,
}

#[derive(Debug, PartialEq, Eq)]
pub enum ServerIncoming {
    Connected(PeerId),
    Message(PeerId, Vec<u8>),
    Disconnected(PeerId),
}

pub trait ServerTransport: Send {
    fn send(&mut self, to: PeerId, channel: Channel, data: &[u8]);
    fn poll(&mut self) -> Option<ServerIncoming>;
}

pub trait ClientTransport: Send {
    fn send(&mut self, channel: Channel, data: &[u8]);
    fn poll(&mut self) -> Option<Vec<u8>>;
}

impl ServerTransport for Box<dyn ServerTransport> {
    fn send(&mut self, to: PeerId, channel: Channel, data: &[u8]) {
        (**self).send(to, channel, data)
    }
    fn poll(&mut self) -> Option<ServerIncoming> {
        (**self).poll()
    }
}

impl ClientTransport for Box<dyn ClientTransport> {
    fn send(&mut self, channel: Channel, data: &[u8]) {
        (**self).send(channel, data)
    }
    fn poll(&mut self) -> Option<Vec<u8>> {
        (**self).poll()
    }
}

/// Simulated network conditions (applied on send).
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct NetConditions {
    pub latency: Duration,
    pub jitter: Duration,
    /// Drop probability for unreliable packets (0..1).
    pub loss: f32,
    pub seed: u64,
}

impl NetConditions {
    pub fn ideal() -> Self {
        Self::default()
    }

    /// One-way `rtt_ms / 2` delay with the given jitter and loss.
    pub fn rtt(rtt_ms: u64, jitter_ms: u64, loss: f32) -> Self {
        Self {
            latency: Duration::from_millis(rtt_ms / 2),
            jitter: Duration::from_millis(jitter_ms),
            loss,
            seed: 0x5EED,
        }
    }
}

/// Queue that releases packets once their simulated delivery time has passed.
#[derive(Debug)]
struct DelayQueue<T> {
    items: Vec<(Instant, u64, T)>,
    order: u64,
    cond: NetConditions,
    rng: gf_core::rng::GfRng,
}

impl<T> DelayQueue<T> {
    fn new(cond: NetConditions) -> Self {
        Self { items: Vec::new(), order: 0, cond, rng: gf_core::rng::GfRng::new(cond.seed ^ 0xA11CE) }
    }

    /// Returns `false` if the packet was dropped.
    fn push(&mut self, channel: Channel, item: T) -> bool {
        if channel == Channel::Unreliable && self.rng.chance(self.cond.loss) {
            return false;
        }
        let jitter = if self.cond.jitter.is_zero() { Duration::ZERO } else { self.cond.jitter.mul_f32(self.rng.f32()) };
        let mut at = Instant::now() + self.cond.latency + jitter;
        // Reliable traffic is ordered: never deliver before an earlier reliable packet.
        if channel == Channel::Reliable
            && let Some(last) = self.items.iter().map(|(t, _, _)| *t).max()
            && at < last
        {
            at = last;
        }
        self.order += 1;
        self.items.push((at, self.order, item));
        true
    }

    fn pop_ready(&mut self) -> Option<T> {
        let now = Instant::now();
        let idx = self
            .items
            .iter()
            .enumerate()
            .filter(|(_, (t, _, _))| *t <= now)
            .min_by_key(|(_, (t, o, _))| (*t, *o))
            .map(|(i, _)| i)?;
        Some(self.items.swap_remove(idx).2)
    }
}

pub mod loopback {
    //! In-process transport. `listener()` returns the host end and a cloneable connector.

    use super::*;
    use crossbeam_channel::{Receiver, Sender, unbounded};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicU32, Ordering};

    enum Up {
        Connect(PeerId, Sender<(Channel, Vec<u8>)>),
        Data(PeerId, Channel, Vec<u8>),
        Disconnect(PeerId),
    }

    pub struct LoopbackServer {
        rx: Receiver<Up>,
        peers: std::collections::HashMap<PeerId, Sender<(Channel, Vec<u8>)>>,
        inbox: DelayQueue<ServerIncoming>,
    }

    #[derive(Clone)]
    pub struct LoopbackConnector {
        tx: Sender<Up>,
        next: Arc<AtomicU32>,
        cond: NetConditions,
    }

    pub struct LoopbackClient {
        id: PeerId,
        tx: Sender<Up>,
        rx: Receiver<(Channel, Vec<u8>)>,
        inbox: DelayQueue<Vec<u8>>,
    }

    pub fn listener(cond: NetConditions) -> (LoopbackServer, LoopbackConnector) {
        let (tx, rx) = unbounded();
        (
            LoopbackServer { rx, peers: Default::default(), inbox: DelayQueue::new(cond) },
            LoopbackConnector { tx, next: Arc::new(AtomicU32::new(1)), cond },
        )
    }

    impl LoopbackConnector {
        pub fn connect(&self) -> LoopbackClient {
            let id = self.next.fetch_add(1, Ordering::Relaxed);
            let (down_tx, down_rx) = unbounded();
            let _ = self.tx.send(Up::Connect(id, down_tx));
            let mut cond = self.cond;
            cond.seed ^= id as u64 * 0x9E37;
            LoopbackClient { id, tx: self.tx.clone(), rx: down_rx, inbox: DelayQueue::new(cond) }
        }
    }

    impl LoopbackClient {
        pub fn peer_id(&self) -> PeerId {
            self.id
        }
    }

    impl Drop for LoopbackClient {
        fn drop(&mut self) {
            let _ = self.tx.send(Up::Disconnect(self.id));
        }
    }

    impl ServerTransport for LoopbackServer {
        fn send(&mut self, to: PeerId, channel: Channel, data: &[u8]) {
            if let Some(tx) = self.peers.get(&to) {
                let _ = tx.send((channel, data.to_vec()));
            }
        }

        fn poll(&mut self) -> Option<ServerIncoming> {
            while let Ok(up) = self.rx.try_recv() {
                match up {
                    Up::Connect(id, tx) => {
                        self.peers.insert(id, tx);
                        self.inbox.push(Channel::Reliable, ServerIncoming::Connected(id));
                    }
                    Up::Data(id, ch, d) => {
                        self.inbox.push(ch, ServerIncoming::Message(id, d));
                    }
                    Up::Disconnect(id) => {
                        self.peers.remove(&id);
                        self.inbox.push(Channel::Reliable, ServerIncoming::Disconnected(id));
                    }
                }
            }
            self.inbox.pop_ready()
        }
    }

    impl ClientTransport for LoopbackClient {
        fn send(&mut self, channel: Channel, data: &[u8]) {
            let _ = self.tx.send(Up::Data(self.id, channel, data.to_vec()));
        }

        fn poll(&mut self) -> Option<Vec<u8>> {
            while let Ok((ch, d)) = self.rx.try_recv() {
                self.inbox.push(ch, d);
            }
            self.inbox.pop_ready()
        }
    }
}

pub mod udp {
    //! Plain UDP for LAN / non-Steam builds. Datagrams above ~60 KB are dropped (Steam SDR
    //! fragments large messages; LAN MTU fragmentation handles the rest).

    use super::*;
    use std::collections::HashMap;
    use std::net::{SocketAddr, ToSocketAddrs, UdpSocket};

    const MAX_DATAGRAM: usize = 60 * 1024;
    const TIMEOUT: Duration = Duration::from_secs(5);

    pub struct UdpServer {
        socket: UdpSocket,
        by_addr: HashMap<SocketAddr, PeerId>,
        by_id: HashMap<PeerId, (SocketAddr, Instant)>,
        next: PeerId,
        pending: std::collections::VecDeque<ServerIncoming>,
        buf: Vec<u8>,
    }

    impl UdpServer {
        pub fn bind(addr: impl ToSocketAddrs) -> std::io::Result<Self> {
            let socket = UdpSocket::bind(addr)?;
            socket.set_nonblocking(true)?;
            Ok(Self {
                socket,
                by_addr: HashMap::new(),
                by_id: HashMap::new(),
                next: 1,
                pending: Default::default(),
                buf: vec![0; 65536],
            })
        }

        pub fn local_addr(&self) -> std::io::Result<SocketAddr> {
            self.socket.local_addr()
        }
    }

    impl ServerTransport for UdpServer {
        fn send(&mut self, to: PeerId, _channel: Channel, data: &[u8]) {
            if data.len() > MAX_DATAGRAM {
                return;
            }
            if let Some((addr, _)) = self.by_id.get(&to) {
                let _ = self.socket.send_to(data, addr);
            }
        }

        fn poll(&mut self) -> Option<ServerIncoming> {
            loop {
                match self.socket.recv_from(&mut self.buf) {
                    Ok((n, addr)) => {
                        let id = match self.by_addr.get(&addr) {
                            Some(id) => *id,
                            None => {
                                let id = self.next;
                                self.next += 1;
                                self.by_addr.insert(addr, id);
                                self.pending.push_back(ServerIncoming::Connected(id));
                                id
                            }
                        };
                        self.by_id.insert(id, (addr, Instant::now()));
                        self.pending.push_back(ServerIncoming::Message(id, self.buf[..n].to_vec()));
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                    Err(_) => break,
                }
            }
            let now = Instant::now();
            let stale: Vec<PeerId> =
                self.by_id.iter().filter(|(_, (_, t))| now.duration_since(*t) > TIMEOUT).map(|(id, _)| *id).collect();
            for id in stale {
                if let Some((addr, _)) = self.by_id.remove(&id) {
                    self.by_addr.remove(&addr);
                }
                self.pending.push_back(ServerIncoming::Disconnected(id));
            }
            self.pending.pop_front()
        }
    }

    pub struct UdpClient {
        socket: UdpSocket,
        buf: Vec<u8>,
    }

    impl UdpClient {
        pub fn connect(server: impl ToSocketAddrs) -> std::io::Result<Self> {
            let socket = UdpSocket::bind("0.0.0.0:0")?;
            socket.connect(server)?;
            socket.set_nonblocking(true)?;
            Ok(Self { socket, buf: vec![0; 65536] })
        }
    }

    impl ClientTransport for UdpClient {
        fn send(&mut self, _channel: Channel, data: &[u8]) {
            if data.len() <= MAX_DATAGRAM {
                let _ = self.socket.send(data);
            }
        }

        fn poll(&mut self) -> Option<Vec<u8>> {
            match self.socket.recv(&mut self.buf) {
                Ok(n) => Some(self.buf[..n].to_vec()),
                Err(_) => None,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loopback_ideal_delivers_in_order() {
        let (mut server, conn) = loopback::listener(NetConditions::ideal());
        let mut client = conn.connect();
        let id = client.peer_id();
        client.send(Channel::Unreliable, b"hello");
        client.send(Channel::Unreliable, b"world");
        assert_eq!(server.poll(), Some(ServerIncoming::Connected(id)));
        assert_eq!(server.poll(), Some(ServerIncoming::Message(id, b"hello".to_vec())));
        assert_eq!(server.poll(), Some(ServerIncoming::Message(id, b"world".to_vec())));
        assert_eq!(server.poll(), None);
        server.send(id, Channel::Reliable, b"snap");
        assert_eq!(client.poll(), Some(b"snap".to_vec()));
        drop(client);
        assert_eq!(server.poll(), Some(ServerIncoming::Disconnected(id)));
    }

    #[test]
    fn loopback_latency_holds_packets() {
        let (mut server, conn) = loopback::listener(NetConditions::rtt(60, 0, 0.0));
        let mut client = conn.connect();
        client.send(Channel::Unreliable, b"x");
        assert_eq!(server.poll(), None, "not yet delivered");
        std::thread::sleep(Duration::from_millis(45));
        assert!(matches!(server.poll(), Some(ServerIncoming::Connected(_))));
        assert!(matches!(server.poll(), Some(ServerIncoming::Message(_, _))));
    }

    #[test]
    fn loopback_loss_drops_only_unreliable() {
        let mut cond = NetConditions::ideal();
        cond.loss = 1.0;
        let (mut server, conn) = loopback::listener(cond);
        let mut client = conn.connect();
        client.send(Channel::Unreliable, b"lost");
        client.send(Channel::Reliable, b"kept");
        assert!(matches!(server.poll(), Some(ServerIncoming::Connected(_))));
        assert!(matches!(server.poll(), Some(ServerIncoming::Message(_, d)) if d == b"kept"));
        assert_eq!(server.poll(), None);
    }

    #[test]
    fn udp_round_trip_on_localhost() {
        let mut server = udp::UdpServer::bind("127.0.0.1:0").unwrap();
        let addr = server.local_addr().unwrap();
        let mut client = udp::UdpClient::connect(addr).unwrap();
        client.send(Channel::Unreliable, b"ping");
        let mut got = Vec::new();
        for _ in 0..100 {
            while let Some(ev) = server.poll() {
                got.push(ev);
            }
            if got.len() >= 2 {
                break;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        let id = match &got[0] {
            ServerIncoming::Connected(id) => *id,
            other => panic!("{other:?}"),
        };
        assert_eq!(got[1], ServerIncoming::Message(id, b"ping".to_vec()));
        server.send(id, Channel::Unreliable, b"pong");
        let mut reply = None;
        for _ in 0..100 {
            reply = client.poll();
            if reply.is_some() {
                break;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        assert_eq!(reply, Some(b"pong".to_vec()));
    }
}
