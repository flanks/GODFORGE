//! Part rarity: Common → Rare → Epic → Godforged (gold).

use crate::rng::GfRng;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, Default)]
pub enum Rarity {
    #[default]
    Common,
    Rare,
    Epic,
    Godforged,
}

impl Rarity {
    pub const COUNT: usize = 4;
    pub const ALL: [Rarity; 4] = [Rarity::Common, Rarity::Rare, Rarity::Epic, Rarity::Godforged];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn next(self) -> Option<Rarity> {
        match self {
            Rarity::Common => Some(Rarity::Rare),
            Rarity::Rare => Some(Rarity::Epic),
            Rarity::Epic => Some(Rarity::Godforged),
            Rarity::Godforged => None,
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            Rarity::Common => "Common",
            Rarity::Rare => "Rare",
            Rarity::Epic => "Epic",
            Rarity::Godforged => "Godforged",
        }
    }
}

/// Rarity tuning, authored in `rarities.ron`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RarityTable {
    /// Effect magnitude multiplier per rarity (see `Modifier::scaled`).
    pub magnitude: [f32; 4],
    /// Base drop weights per rarity.
    pub drop_weight: [f32; 4],
    /// Godshards returned when salvaging a part of each rarity.
    pub salvage_shards: [u32; 4],
}

impl Default for RarityTable {
    fn default() -> Self {
        Self { magnitude: [1.0, 1.3, 1.65, 2.1], drop_weight: [60.0, 28.0, 10.0, 2.0], salvage_shards: [2, 5, 12, 30] }
    }
}

impl RarityTable {
    #[inline]
    pub fn magnitude(&self, r: Rarity) -> f32 {
        self.magnitude[r.index()]
    }

    /// Roll a rarity. `luck` (0 = neutral) shifts weight from Common toward higher tiers:
    /// each point of luck multiplies tier *n* weight by `(1 + luck)^n`.
    pub fn roll(&self, rng: &mut GfRng, luck: f32) -> Rarity {
        let boost = (1.0 + luck.max(-0.9)).max(0.1);
        let mut w = self.drop_weight;
        for (i, weight) in w.iter_mut().enumerate() {
            *weight *= boost.powi(i as i32);
        }
        rng.weighted_index(&w).and_then(|i| Rarity::ALL.get(i).copied()).unwrap_or(Rarity::Common)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn next_chain() {
        assert_eq!(Rarity::Common.next(), Some(Rarity::Rare));
        assert_eq!(Rarity::Godforged.next(), None);
        assert!(Rarity::Epic > Rarity::Rare);
    }

    #[test]
    fn luck_shifts_distribution() {
        let table = RarityTable::default();
        let count_high = |luck: f32| {
            let mut rng = GfRng::new(11);
            (0..20_000).filter(|_| table.roll(&mut rng, luck) >= Rarity::Epic).count()
        };
        let neutral = count_high(0.0);
        let lucky = count_high(1.0);
        assert!(lucky > neutral * 2, "luck should materially raise Epic+ rate ({neutral} → {lucky})");
        // ~12% Epic+ at neutral luck.
        assert!((1800..3000).contains(&neutral), "{neutral}");
    }
}
