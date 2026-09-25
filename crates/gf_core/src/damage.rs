//! Damage model: six damage types, resistances (armor plates are build checks, never walls),
//! crit resolution, and the Manual-mode precision bonus.

use serde::{Deserialize, Serialize};

/// The six damage types. Order is load-bearing (indexes resistances and replication bits).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, Default)]
pub enum DamageType {
    #[default]
    Kinetic,
    Flame,
    Storm,
    Void,
    Plague,
    Radiant,
}

impl DamageType {
    pub const COUNT: usize = 6;
    pub const ALL: [DamageType; 6] = [
        DamageType::Kinetic,
        DamageType::Flame,
        DamageType::Storm,
        DamageType::Void,
        DamageType::Plague,
        DamageType::Radiant,
    ];

    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }

    pub const fn from_index(i: usize) -> Option<Self> {
        if i < Self::COUNT { Some(Self::ALL[i]) } else { None }
    }

    pub const fn name(self) -> &'static str {
        match self {
            DamageType::Kinetic => "Kinetic",
            DamageType::Flame => "Flame",
            DamageType::Storm => "Storm",
            DamageType::Void => "Void",
            DamageType::Plague => "Plague",
            DamageType::Radiant => "Radiant",
        }
    }
}

/// Resistance can never exceed this: plates slow a build down, they never stop it.
pub const MAX_RESIST: f32 = 0.75;

/// Per-type damage reduction fractions (negative = vulnerability).
///
/// Authored as a sparse map, e.g. `resist: {Kinetic: 0.5, Flame: -0.25}`.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(from = "ResistMap", into = "ResistMap")]
pub struct Resistances(pub [f32; 6]);

type ResistMap = std::collections::BTreeMap<DamageType, f32>;

impl From<ResistMap> for Resistances {
    fn from(map: ResistMap) -> Self {
        let mut r = [0.0; 6];
        for (t, v) in map {
            r[t.index()] = v;
        }
        Resistances(r)
    }
}

impl From<Resistances> for ResistMap {
    fn from(r: Resistances) -> Self {
        DamageType::ALL.iter().filter(|t| r.0[t.index()] != 0.0).map(|t| (*t, r.0[t.index()])).collect()
    }
}

impl Resistances {
    pub const NONE: Resistances = Resistances([0.0; 6]);

    #[inline]
    pub fn get(&self, t: DamageType) -> f32 {
        self.0[t.index()].clamp(-1.0, MAX_RESIST)
    }

    pub fn with(mut self, t: DamageType, value: f32) -> Self {
        self.0[t.index()] = value;
        self
    }

    pub fn is_none(&self) -> bool {
        self.0.iter().all(|r| *r == 0.0)
    }
}

/// Armor plates on elites: resist listed types until `plate_hp` damage has been absorbed, then
/// shatter. Kinetic-heavy builds meet Kinetic plates — slower, never stuck.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Plating {
    pub resist: Resistances,
    pub plate_hp: f32,
}

/// Everything that determines one hit's damage number.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HitParams {
    pub base: f32,
    pub damage_type: DamageType,
    pub crit_chance: f32,
    pub crit_mult: f32,
    /// Product of situational multipliers (aim-mode tax, Deadeye, curse, conditionals, buffs).
    pub bonus_mult: f32,
    /// Manual-mode perfect hit ("headshot").
    pub precision: bool,
    /// Extra crit multiplier granted by a precision hit (spec: +25% crit damage).
    pub precision_crit_bonus: f32,
    pub forced_crit: bool,
}

impl HitParams {
    pub fn simple(base: f32, damage_type: DamageType) -> Self {
        Self {
            base,
            damage_type,
            crit_chance: 0.0,
            crit_mult: 1.0,
            bonus_mult: 1.0,
            precision: false,
            precision_crit_bonus: 0.0,
            forced_crit: false,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct HitResult {
    pub amount: f32,
    pub crit: bool,
}

/// Resolve a hit. `roll` is a uniform `[0,1)` sample supplied by the caller's deterministic RNG.
pub fn roll_hit(p: &HitParams, resist: &Resistances, roll: f32) -> HitResult {
    let crit = p.forced_crit || roll < p.crit_chance;
    let mut amount = p.base * p.bonus_mult.max(0.0);
    if crit {
        let mut mult = p.crit_mult.max(1.0);
        if p.precision {
            mult += p.precision_crit_bonus;
        }
        amount *= mult;
    }
    amount *= 1.0 - resist.get(p.damage_type);
    HitResult { amount: amount.max(0.0), crit }
}

/// Expected damage multiplier contributed by crits (used by the forge DPS preview).
#[inline]
pub fn expected_crit_factor(chance: f32, mult: f32) -> f32 {
    1.0 + chance.clamp(0.0, 1.0) * (mult - 1.0).max(0.0)
}

/// Apply plating: returns (damage after plates, remaining plate hp, shattered this hit).
pub fn apply_plating(amount_pre_resist: f32, damage_type: DamageType, plating: &mut Option<Plating>) -> (f32, bool) {
    let Some(plate) = plating else {
        return (amount_pre_resist, false);
    };
    let resist = plate.resist.get(damage_type);
    let after = amount_pre_resist * (1.0 - resist);
    let absorbed = amount_pre_resist - after;
    // Plates wear down from everything that hits them, faster from the damage they block.
    plate.plate_hp -= after * 0.5 + absorbed;
    if plate.plate_hp <= 0.0 {
        *plating = None;
        (after, true)
    } else {
        (after, false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crit_and_resist() {
        let mut p = HitParams::simple(100.0, DamageType::Flame);
        p.crit_chance = 0.5;
        p.crit_mult = 2.5;
        let r = Resistances::NONE.with(DamageType::Flame, 0.2);
        let hit = roll_hit(&p, &r, 0.1);
        assert!(hit.crit);
        assert!((hit.amount - 100.0 * 2.5 * 0.8).abs() < 1e-3);
        let miss = roll_hit(&p, &r, 0.9);
        assert!(!miss.crit);
        assert!((miss.amount - 80.0).abs() < 1e-3);
    }

    #[test]
    fn precision_boosts_crit_only() {
        let mut p = HitParams::simple(100.0, DamageType::Kinetic);
        p.crit_chance = 1.0;
        p.crit_mult = 2.5;
        p.precision = true;
        p.precision_crit_bonus = 0.25;
        let hit = roll_hit(&p, &Resistances::NONE, 0.0);
        assert!((hit.amount - 275.0).abs() < 1e-3);
        p.crit_chance = 0.0;
        let plain = roll_hit(&p, &Resistances::NONE, 0.5);
        assert!((plain.amount - 100.0).abs() < 1e-3);
    }

    #[test]
    fn resist_is_capped_never_a_wall() {
        let r = Resistances::NONE.with(DamageType::Kinetic, 5.0);
        let hit = roll_hit(&HitParams::simple(100.0, DamageType::Kinetic), &r, 0.9);
        assert!((hit.amount - 25.0).abs() < 1e-3);
    }

    #[test]
    fn plates_shatter() {
        let mut plating = Some(Plating { resist: Resistances::NONE.with(DamageType::Kinetic, 0.5), plate_hp: 60.0 });
        let (d, broke) = apply_plating(40.0, DamageType::Kinetic, &mut plating);
        assert!((d - 20.0).abs() < 1e-3);
        assert!(!broke);
        let (_, broke) = apply_plating(40.0, DamageType::Kinetic, &mut plating);
        assert!(broke);
        assert!(plating.is_none());
        let (d, _) = apply_plating(40.0, DamageType::Kinetic, &mut plating);
        assert_eq!(d, 40.0);
    }

    #[test]
    fn resistances_author_as_sparse_maps() {
        let r: Resistances = ron::from_str("{Kinetic: 0.5, Flame: -0.25}").unwrap();
        assert_eq!(r.get(DamageType::Kinetic), 0.5);
        assert_eq!(r.get(DamageType::Flame), -0.25);
        assert_eq!(r.get(DamageType::Void), 0.0);
        assert_eq!(ron::to_string(&Resistances::NONE).unwrap(), "{}");
        let back: Resistances = ron::from_str(&ron::to_string(&r).unwrap()).unwrap();
        assert_eq!(back, r);
    }

    #[test]
    fn expected_crit() {
        assert!((expected_crit_factor(0.05, 2.5) - 1.075).abs() < 1e-5);
        assert_eq!(expected_crit_factor(2.0, 2.0), 2.0);
    }
}
