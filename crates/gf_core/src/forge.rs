//! THE FORGE — weapon = 1 Chassis + 4 Slots (Core, Mechanism, Relic, Sigil).
//!
//! Anvil actions (swap/equip, fuse, reroll, salvage) are pure functions over a build, a part bag
//! and a wallet so the host sim, the forge UI preview and tests share one implementation.
//! Named combos ("recipes") are detected here and feed the codex.

use crate::damage::DamageType;
use crate::ids::{ChassisId, PartId, RecipeId};
use crate::rarity::Rarity;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Slot {
    Core,
    Mechanism,
    Relic,
    Sigil,
}

impl Slot {
    pub const COUNT: usize = 4;
    pub const ALL: [Slot; 4] = [Slot::Core, Slot::Mechanism, Slot::Relic, Slot::Sigil];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn name(self) -> &'static str {
        match self {
            Slot::Core => "Core",
            Slot::Mechanism => "Mechanism",
            Slot::Relic => "Relic",
            Slot::Sigil => "Sigil",
        }
    }
}

/// One concrete part the player owns. `uid` is unique per run per player.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct PartInstance {
    pub uid: u32,
    pub part: PartId,
    pub rarity: Rarity,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct WeaponBuild {
    pub chassis: ChassisId,
    pub slots: [Option<PartInstance>; Slot::COUNT],
}

impl WeaponBuild {
    pub fn new(chassis: ChassisId) -> Self {
        Self { chassis, slots: [None; Slot::COUNT] }
    }

    #[inline]
    pub fn get(&self, slot: Slot) -> Option<PartInstance> {
        self.slots[slot.index()]
    }

    /// Put `part` in `slot`, returning what was there.
    pub fn set(&mut self, slot: Slot, part: Option<PartInstance>) -> Option<PartInstance> {
        std::mem::replace(&mut self.slots[slot.index()], part)
    }

    /// Equipped parts in canonical slot order (the order modifiers are compiled in).
    pub fn equipped(&self) -> impl Iterator<Item = (Slot, PartInstance)> + '_ {
        Slot::ALL.iter().filter_map(move |s| self.slots[s.index()].map(|p| (*s, p)))
    }

    pub fn filled_slots(&self) -> usize {
        self.slots.iter().filter(|s| s.is_some()).count()
    }
}

/// Parts carried but not equipped.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct PartBag {
    pub items: Vec<PartInstance>,
    pub capacity: u8,
}

impl PartBag {
    pub fn with_capacity(capacity: u8) -> Self {
        Self { items: Vec::new(), capacity }
    }

    pub fn is_full(&self) -> bool {
        self.items.len() >= self.capacity as usize
    }

    pub fn find(&self, uid: u32) -> Option<&PartInstance> {
        self.items.iter().find(|p| p.uid == uid)
    }

    pub fn take(&mut self, uid: u32) -> Option<PartInstance> {
        let i = self.items.iter().position(|p| p.uid == uid)?;
        Some(self.items.remove(i))
    }

    /// Add a part; returns it back if the bag is full.
    pub fn push(&mut self, part: PartInstance) -> Result<(), PartInstance> {
        if self.is_full() {
            Err(part)
        } else {
            self.items.push(part);
            Ok(())
        }
    }
}

/// Per-player run resources spent at anvils.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ForgeWallet {
    pub godshards: u32,
    /// Fuse/reroll actions left at the current anvil.
    pub charges: u8,
    /// Mirren's Grand Heist: next anvil actions cost nothing.
    pub free_actions: u8,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ForgeRules {
    pub reroll_cost: u32,
    pub fuse_cost: u32,
    pub charges_per_anvil: u8,
    /// Slots that cannot be changed mid-run (Sigils are chosen pre-run).
    pub locked_slots: Vec<Slot>,
    pub bag_capacity: u8,
}

impl Default for ForgeRules {
    fn default() -> Self {
        Self { reroll_cost: 6, fuse_cost: 0, charges_per_anvil: 3, locked_slots: vec![Slot::Sigil], bag_capacity: 8 }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ForgeAction {
    /// Equip a bag part into its slot; the displaced part returns to the bag. Free.
    Equip { uid: u32 },
    /// Fuse a bag part into the equipped part of the same slot: rarity +1. Costs a charge.
    Fuse { uid: u32 },
    /// Reroll the equipped part of `slot` into another part of the same slot and rarity.
    /// Costs a charge and godshards.
    Reroll { slot: Slot },
    /// Break a bag part down into godshards. Free.
    Salvage { uid: u32 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ForgeOutcome {
    Equipped { slot: Slot, part: PartInstance, displaced: Option<PartInstance> },
    Fused { slot: Slot, part: PartInstance },
    Rerolled { slot: Slot, from: PartId, part: PartInstance },
    Salvaged { shards: u32 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Error, Serialize, Deserialize)]
pub enum ForgeError {
    #[error("no such part in the bag")]
    NotInBag,
    #[error("you must stand at a hot anvil")]
    NotAtAnvil,
    #[error("the {0:?} slot is locked during a run")]
    SlotLocked(Slot),
    #[error("nothing equipped in the {0:?} slot")]
    EmptySlot(Slot),
    #[error("part belongs in the {part:?} slot, not {target:?}")]
    SlotMismatch { part: Slot, target: Slot },
    #[error("already Godforged")]
    MaxRarity,
    #[error("no forge charges left at this anvil")]
    NoCharges,
    #[error("need {need} godshards, have {have}")]
    NotEnoughShards { need: u32, have: u32 },
    #[error("bag is full")]
    BagFull,
    #[error("no reroll candidates for that slot")]
    NoCandidates,
}

/// Lookups the forge needs from content.
pub trait PartCatalog {
    fn slot_of(&self, part: PartId) -> Option<Slot>;
    /// Pick a different part for a reroll (deterministic given the caller's RNG state).
    fn reroll_pick(&mut self, slot: Slot, exclude: PartId) -> Option<PartId>;
    fn salvage_value(&self, rarity: Rarity) -> u32;
}

fn spend_charge(wallet: &mut ForgeWallet, shards: u32) -> Result<(), ForgeError> {
    if wallet.free_actions > 0 {
        wallet.free_actions -= 1;
        return Ok(());
    }
    if wallet.charges == 0 {
        return Err(ForgeError::NoCharges);
    }
    if wallet.godshards < shards {
        return Err(ForgeError::NotEnoughShards { need: shards, have: wallet.godshards });
    }
    wallet.charges -= 1;
    wallet.godshards -= shards;
    Ok(())
}

/// Apply an anvil action. On error nothing is modified.
pub fn apply_action(
    action: ForgeAction,
    build: &mut WeaponBuild,
    bag: &mut PartBag,
    wallet: &mut ForgeWallet,
    rules: &ForgeRules,
    catalog: &mut dyn PartCatalog,
    next_uid: &mut u32,
) -> Result<ForgeOutcome, ForgeError> {
    match action {
        ForgeAction::Equip { uid } => {
            let part = *bag.find(uid).ok_or(ForgeError::NotInBag)?;
            let slot = catalog.slot_of(part.part).ok_or(ForgeError::NotInBag)?;
            if rules.locked_slots.contains(&slot) {
                return Err(ForgeError::SlotLocked(slot));
            }
            bag.take(uid);
            let displaced = build.set(slot, Some(part));
            if let Some(d) = displaced {
                // The displaced part always fits: we just freed a bag space.
                let _ = bag.push(d);
            }
            Ok(ForgeOutcome::Equipped { slot, part, displaced })
        }
        ForgeAction::Fuse { uid } => {
            let donor = *bag.find(uid).ok_or(ForgeError::NotInBag)?;
            let slot = catalog.slot_of(donor.part).ok_or(ForgeError::NotInBag)?;
            if rules.locked_slots.contains(&slot) {
                return Err(ForgeError::SlotLocked(slot));
            }
            let equipped = build.get(slot).ok_or(ForgeError::EmptySlot(slot))?;
            let target = equipped.rarity.max(donor.rarity).next().ok_or(ForgeError::MaxRarity)?;
            spend_charge(wallet, rules.fuse_cost)?;
            bag.take(uid);
            let fused = PartInstance { rarity: target, ..equipped };
            build.set(slot, Some(fused));
            Ok(ForgeOutcome::Fused { slot, part: fused })
        }
        ForgeAction::Reroll { slot } => {
            if rules.locked_slots.contains(&slot) {
                return Err(ForgeError::SlotLocked(slot));
            }
            let equipped = build.get(slot).ok_or(ForgeError::EmptySlot(slot))?;
            // Validate affordability before consuming RNG or charges.
            if wallet.free_actions == 0 {
                if wallet.charges == 0 {
                    return Err(ForgeError::NoCharges);
                }
                if wallet.godshards < rules.reroll_cost {
                    return Err(ForgeError::NotEnoughShards { need: rules.reroll_cost, have: wallet.godshards });
                }
            }
            let new_part = catalog.reroll_pick(slot, equipped.part).ok_or(ForgeError::NoCandidates)?;
            spend_charge(wallet, rules.reroll_cost)?;
            *next_uid += 1;
            let rerolled = PartInstance { uid: *next_uid, part: new_part, rarity: equipped.rarity };
            build.set(slot, Some(rerolled));
            Ok(ForgeOutcome::Rerolled { slot, from: equipped.part, part: rerolled })
        }
        ForgeAction::Salvage { uid } => {
            let part = bag.take(uid).ok_or(ForgeError::NotInBag)?;
            let shards = catalog.salvage_value(part.rarity);
            wallet.godshards += shards;
            Ok(ForgeOutcome::Salvaged { shards })
        }
    }
}

/// Recipe ingredient (resolved from content keys by `gf_content`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Ingredient {
    Chassis(ChassisId),
    Part(PartId),
    Element(DamageType),
}

/// Does `build` (whose compiled element is `element`) satisfy every ingredient?
pub fn recipe_satisfied(ingredients: &[Ingredient], build: &WeaponBuild, element: DamageType) -> bool {
    !ingredients.is_empty()
        && ingredients.iter().all(|ing| match *ing {
            Ingredient::Chassis(c) => build.chassis == c,
            Ingredient::Part(p) => build.slots.iter().flatten().any(|s| s.part == p),
            Ingredient::Element(e) => element == e,
        })
}

/// All recipes satisfied by a build, in table order.
pub fn matching_recipes<'a>(
    recipes: impl IntoIterator<Item = (RecipeId, &'a [Ingredient])>,
    build: &WeaponBuild,
    element: DamageType,
) -> Vec<RecipeId> {
    recipes.into_iter().filter(|(_, ings)| recipe_satisfied(ings, build, element)).map(|(id, _)| id).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Parts 0..=2 are Cores, 3..=5 Mechanisms, 6..=8 Relics, 9 is a Sigil.
    struct Catalog {
        next: u16,
    }
    impl PartCatalog for Catalog {
        fn slot_of(&self, part: PartId) -> Option<Slot> {
            match part.0 {
                0..=2 => Some(Slot::Core),
                3..=5 => Some(Slot::Mechanism),
                6..=8 => Some(Slot::Relic),
                9 => Some(Slot::Sigil),
                _ => None,
            }
        }
        fn reroll_pick(&mut self, slot: Slot, exclude: PartId) -> Option<PartId> {
            let base = match slot {
                Slot::Core => 0,
                Slot::Mechanism => 3,
                Slot::Relic => 6,
                Slot::Sigil => return None,
            };
            for _ in 0..3 {
                self.next = (self.next + 1) % 3;
                let p = PartId(base + self.next);
                if p != exclude {
                    return Some(p);
                }
            }
            None
        }
        fn salvage_value(&self, rarity: Rarity) -> u32 {
            [2, 5, 12, 30][rarity.index()]
        }
    }

    fn setup() -> (WeaponBuild, PartBag, ForgeWallet, ForgeRules, Catalog, u32) {
        let mut build = WeaponBuild::new(ChassisId(0));
        build.set(Slot::Core, Some(PartInstance { uid: 1, part: PartId(0), rarity: Rarity::Common }));
        build.set(Slot::Sigil, Some(PartInstance { uid: 2, part: PartId(9), rarity: Rarity::Rare }));
        let mut bag = PartBag::with_capacity(4);
        bag.push(PartInstance { uid: 3, part: PartId(1), rarity: Rarity::Rare }).unwrap();
        bag.push(PartInstance { uid: 4, part: PartId(3), rarity: Rarity::Common }).unwrap();
        let wallet = ForgeWallet { godshards: 10, charges: 2, free_actions: 0 };
        (build, bag, wallet, ForgeRules::default(), Catalog { next: 0 }, 10)
    }

    #[test]
    fn equip_swaps_into_bag() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        let out =
            apply_action(ForgeAction::Equip { uid: 3 }, &mut build, &mut bag, &mut wallet, &rules, &mut cat, &mut uid)
                .unwrap();
        assert!(matches!(out, ForgeOutcome::Equipped { slot: Slot::Core, displaced: Some(d), .. } if d.uid == 1));
        assert_eq!(build.get(Slot::Core).unwrap().uid, 3);
        assert!(bag.find(1).is_some());
        assert_eq!(wallet.charges, 2, "equip is free");
    }

    #[test]
    fn equip_into_empty_slot() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        apply_action(ForgeAction::Equip { uid: 4 }, &mut build, &mut bag, &mut wallet, &rules, &mut cat, &mut uid)
            .unwrap();
        assert_eq!(build.get(Slot::Mechanism).unwrap().uid, 4);
        assert_eq!(bag.items.len(), 1);
    }

    #[test]
    fn fuse_raises_rarity_past_the_higher_input() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        let out =
            apply_action(ForgeAction::Fuse { uid: 3 }, &mut build, &mut bag, &mut wallet, &rules, &mut cat, &mut uid)
                .unwrap();
        // Common (equipped) + Rare (donor) → Epic, keeping the equipped identity.
        assert!(
            matches!(out, ForgeOutcome::Fused { part, .. } if part.rarity == Rarity::Epic && part.part == PartId(0))
        );
        assert_eq!(wallet.charges, 1);
        assert!(bag.find(3).is_none());
    }

    #[test]
    fn fuse_requires_equipped_slot_and_charges() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        let err =
            apply_action(ForgeAction::Fuse { uid: 4 }, &mut build, &mut bag, &mut wallet, &rules, &mut cat, &mut uid);
        assert_eq!(err, Err(ForgeError::EmptySlot(Slot::Mechanism)));
        wallet.charges = 0;
        let before = (build.clone(), bag.clone(), wallet);
        let err =
            apply_action(ForgeAction::Fuse { uid: 3 }, &mut build, &mut bag, &mut wallet, &rules, &mut cat, &mut uid);
        assert_eq!(err, Err(ForgeError::NoCharges));
        assert_eq!((build, bag, wallet), before, "errors leave state untouched");
    }

    #[test]
    fn godforged_cannot_fuse() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        build.set(Slot::Core, Some(PartInstance { uid: 1, part: PartId(0), rarity: Rarity::Godforged }));
        let err =
            apply_action(ForgeAction::Fuse { uid: 3 }, &mut build, &mut bag, &mut wallet, &rules, &mut cat, &mut uid);
        assert_eq!(err, Err(ForgeError::MaxRarity));
    }

    #[test]
    fn reroll_keeps_rarity_changes_part() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        let out = apply_action(
            ForgeAction::Reroll { slot: Slot::Core },
            &mut build,
            &mut bag,
            &mut wallet,
            &rules,
            &mut cat,
            &mut uid,
        )
        .unwrap();
        let ForgeOutcome::Rerolled { from, part, .. } = out else { panic!() };
        assert_eq!(from, PartId(0));
        assert_ne!(part.part, PartId(0));
        assert_eq!(part.rarity, Rarity::Common);
        assert_eq!(wallet.godshards, 4);
        let err = apply_action(
            ForgeAction::Reroll { slot: Slot::Core },
            &mut build,
            &mut bag,
            &mut wallet,
            &rules,
            &mut cat,
            &mut uid,
        );
        assert_eq!(err, Err(ForgeError::NotEnoughShards { need: 6, have: 4 }));
    }

    #[test]
    fn free_actions_bypass_costs() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        wallet.charges = 0;
        wallet.godshards = 0;
        wallet.free_actions = 1;
        apply_action(
            ForgeAction::Reroll { slot: Slot::Core },
            &mut build,
            &mut bag,
            &mut wallet,
            &rules,
            &mut cat,
            &mut uid,
        )
        .unwrap();
        assert_eq!(wallet.free_actions, 0);
    }

    #[test]
    fn sigil_is_locked_mid_run() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        let err = apply_action(
            ForgeAction::Reroll { slot: Slot::Sigil },
            &mut build,
            &mut bag,
            &mut wallet,
            &rules,
            &mut cat,
            &mut uid,
        );
        assert_eq!(err, Err(ForgeError::SlotLocked(Slot::Sigil)));
    }

    #[test]
    fn salvage_pays_by_rarity() {
        let (mut build, mut bag, mut wallet, rules, mut cat, mut uid) = setup();
        let out = apply_action(
            ForgeAction::Salvage { uid: 3 },
            &mut build,
            &mut bag,
            &mut wallet,
            &rules,
            &mut cat,
            &mut uid,
        )
        .unwrap();
        assert_eq!(out, ForgeOutcome::Salvaged { shards: 5 });
        assert_eq!(wallet.godshards, 15);
    }

    #[test]
    fn recipes_match() {
        let (build, ..) = setup();
        let ings = [Ingredient::Part(PartId(0)), Ingredient::Element(DamageType::Storm)];
        assert!(recipe_satisfied(&ings, &build, DamageType::Storm));
        assert!(!recipe_satisfied(&ings, &build, DamageType::Flame));
        assert!(!recipe_satisfied(&[], &build, DamageType::Storm), "empty recipes never match");
        let recipes = [(RecipeId(0), &ings[..]), (RecipeId(1), &[Ingredient::Chassis(ChassisId(3))][..])];
        assert_eq!(matching_recipes(recipes, &build, DamageType::Storm), vec![RecipeId(0)]);
    }
}
