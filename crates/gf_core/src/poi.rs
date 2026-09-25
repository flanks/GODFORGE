//! Points of interest on a biome map (OPEN_WORLD.md §2.3): the objectives a party roams between.
//! Shared by content (quotas, tuning rows, generated sites), the sim (lifecycles) and the wire
//! (`EntityView.status` carries a [`PoiState`]).

use serde::{Deserialize, Serialize};

/// What a POI is. Seals come from Anvils, Lairs, Shrines, Reliquaries, Veins and the Warlord;
/// Springs and Watchfires give none. Every map has exactly one Gate (it is implicit, never a quota).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum PoiKind {
    /// Hold the ring, then forge: the anvil event, one per anvil.
    Anvil,
    /// The biome mini-boss guarding the route to the gate (worth 2 Seals, required).
    Warlord,
    /// A den of biome elites and their pack, idle until woken.
    Lair,
    /// Hold the ring for a boon from the shrine's god.
    Shrine,
    /// Hold the ring for a cache of parts.
    Reliquary,
    /// Hold the ring for godshards to every player.
    Vein,
    /// A healing spring, used once per player.
    Spring,
    /// Touch to reveal the map around it.
    Watchfire,
    /// The Boss Gate: sealed until enough Seals, then the party gathers to enter the boss arena.
    Gate,
}

impl PoiKind {
    pub const COUNT: usize = 9;
    pub const ALL: [PoiKind; 9] = [
        PoiKind::Anvil,
        PoiKind::Warlord,
        PoiKind::Lair,
        PoiKind::Shrine,
        PoiKind::Reliquary,
        PoiKind::Vein,
        PoiKind::Spring,
        PoiKind::Watchfire,
        PoiKind::Gate,
    ];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn name(self) -> &'static str {
        match self {
            PoiKind::Anvil => "Anvil",
            PoiKind::Warlord => "Warlord",
            PoiKind::Lair => "Lair",
            PoiKind::Shrine => "Shrine",
            PoiKind::Reliquary => "Reliquary",
            PoiKind::Vein => "Vein",
            PoiKind::Spring => "Spring",
            PoiKind::Watchfire => "Watchfire",
            PoiKind::Gate => "Gate",
        }
    }

    /// Major POIs take a region's site (at most one per region); the rest take secondary sites
    /// along the roads (§3.3).
    pub const fn is_major(self) -> bool {
        matches!(self, PoiKind::Anvil | PoiKind::Warlord | PoiKind::Lair | PoiKind::Gate)
    }
}

/// Lifecycle state of a POI (§5.3), replicated as `EntityView.status`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[repr(u8)]
pub enum PoiState {
    /// Waiting for a player (unclaimed hold ring, sleeping guards, unused spring, unlit watchfire).
    #[default]
    Dormant,
    /// In progress: a hold ring filling, or its guards awake.
    Active,
    /// An anvil's forge window is open.
    Hot,
    /// Completed (rewards paid, spring used by everyone, watchfire lit).
    Done,
    /// The gate, short of Seals (or the Warlord).
    Sealed,
    /// The gate, open and waiting for the party.
    Open,
    /// The gate's countdown into the boss arena is running.
    Gathering,
}

impl PoiState {
    #[inline]
    pub const fn to_u8(self) -> u8 {
        self as u8
    }

    /// The state a wire byte encodes (unknown values read as `Dormant`).
    pub const fn from_u8(v: u8) -> Self {
        match v {
            1 => PoiState::Active,
            2 => PoiState::Hot,
            3 => PoiState::Done,
            4 => PoiState::Sealed,
            5 => PoiState::Open,
            6 => PoiState::Gathering,
            _ => PoiState::Dormant,
        }
    }
}
