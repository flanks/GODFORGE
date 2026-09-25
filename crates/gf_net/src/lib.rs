//! # gf_net — host-authoritative netcode
//!
//! - [`protocol`]: commands up, delta snapshots down, cosmetic events alongside.
//! - [`delta`]: entity-level delta against the client's acknowledged baseline.
//! - [`transport`]: loopback (with simulated latency/jitter/loss) and UDP; Steam SDR plugs into the
//!   same traits.
//! - [`server`] / [`client`]: session management on each side.
//!
//! Engine-agnostic (no Bevy): the same code runs in the headless host, in tests and in the client.

#[macro_use]
mod macros;

pub mod client;
pub mod delta;
pub mod protocol;
pub mod quant;
pub mod server;
pub mod transport;

pub use client::{ClientEvent, NetClient};
pub use protocol::*;
pub use server::{NetServer, ServerConfig, SessionEvent};
pub use transport::{Channel, ClientTransport, NetConditions, PeerId, ServerIncoming, ServerTransport};

use serde::Serialize;
use serde::de::DeserializeOwned;

/// Serialize a message for the wire (postcard: compact varint encoding).
pub fn encode<T: Serialize>(msg: &T) -> Vec<u8> {
    postcard::to_allocvec(msg).expect("protocol types always serialize")
}

/// Deserialize a message; malformed input is an error, never a panic.
pub fn decode<T: DeserializeOwned>(bytes: &[u8]) -> Result<T, postcard::Error> {
    postcard::from_bytes(bytes)
}
