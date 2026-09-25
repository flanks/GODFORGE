//! Compact content ids. Content is authored with string keys; `gf_content` assigns each table row a
//! stable `u16` index at load time (rows are sorted by key, and a content hash is exchanged in the
//! network handshake so host and clients always agree on the mapping).

use serde::{Deserialize, Serialize};

macro_rules! def_id {
    ($(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, Default)]
        pub struct $name(pub u16);

        impl $name {
            /// Row index into the owning content table.
            #[inline]
            pub const fn index(self) -> usize {
                self.0 as usize
            }
        }
    };
}

def_id!(/// A weapon chassis row.
    ChassisId);
def_id!(/// A forge part row (Core / Mechanism / Relic / Sigil).
    PartId);
def_id!(/// A boon row.
    BoonId);
def_id!(/// An enemy archetype row.
    EnemyId);
def_id!(/// A playable Godforged row.
    CharacterId);
def_id!(/// A named combo / recipe row.
    RecipeId);
def_id!(/// An elemental synergy combo row.
    SynergyId);
def_id!(/// A room template row.
    RoomId);
def_id!(/// A god of the shattered pantheon.
    GodId);
def_id!(/// A biome row.
    BiomeId);

/// Replicated entity id, allocated by the host. Never reused within a run.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, Default)]
pub struct NetId(pub u32);

/// Who caused something: players 0..=3, their Echo drones 4..=7, their turrets 8..=11,
/// the environment 254 and enemies 255. Used for synergy "distinct source" checks and kill credit.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub struct SourceId(pub u8);

impl SourceId {
    pub const ENVIRONMENT: SourceId = SourceId(254);
    pub const ENEMY: SourceId = SourceId(255);

    pub const fn player(slot: u8) -> Self {
        SourceId(slot)
    }
    pub const fn echo(slot: u8) -> Self {
        SourceId(4 + slot)
    }
    pub const fn turret(slot: u8) -> Self {
        SourceId(8 + slot)
    }

    /// The player slot this source belongs to (players, their echoes and turrets).
    pub const fn owner_slot(self) -> Option<u8> {
        if self.0 < 12 { Some(self.0 % 4) } else { None }
    }

    pub const fn is_player_side(self) -> bool {
        self.0 < 12
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_ownership() {
        assert_eq!(SourceId::player(2).owner_slot(), Some(2));
        assert_eq!(SourceId::echo(2).owner_slot(), Some(2));
        assert_eq!(SourceId::turret(3).owner_slot(), Some(3));
        assert_eq!(SourceId::ENEMY.owner_slot(), None);
        assert!(!SourceId::ENVIRONMENT.is_player_side());
    }
}
