//! Difficulty: party-size scaling (1–4 players) and Trials of the Forge (Chaos Tiers 1–20).

use serde::{Deserialize, Serialize};

/// One row of the party scaling table (`party_scaling.ron`).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct PartyScaling {
    pub players: u8,
    pub enemy_hp: f32,
    pub enemy_count: f32,
    pub boss_hp: f32,
    pub loot: f32,
}

impl PartyScaling {
    pub const SOLO: PartyScaling =
        PartyScaling { players: 1, enemy_hp: 1.0, enemy_count: 1.0, boss_hp: 1.0, loot: 1.0 };
}

/// Look up the row for `players`, clamping to the table's range.
pub fn party_scaling(rows: &[PartyScaling], players: u8) -> PartyScaling {
    if let Some(r) = rows.iter().find(|r| r.players == players) {
        return *r;
    }
    rows.iter().min_by_key(|r| (r.players as i32 - players as i32).abs()).copied().unwrap_or(PartyScaling::SOLO)
}

/// Chaos Tier mutators. Tiers are cumulative: tier N applies every tier 1..=N.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum ChaosMod {
    EnemyHp(f32),
    EnemyDamage(f32),
    EnemySpeed(f32),
    SpawnRate(f32),
    EnemyCount(f32),
    /// Additive elite chance (0.05 = +5 pp).
    EliteChance(f32),
    /// Enemies burst on death after `fuse` seconds (telegraphed).
    VolatileDeaths {
        chance: f32,
        radius: f32,
        damage: f32,
        fuse: f32,
    },
    /// Elites spawn with a shield worth this fraction of max HP.
    ShieldedElites(f32),
    HealingReceived(f32),
    /// × anvil hold duration.
    AnvilHoldTime(f32),
    BossHp(f32),
    /// Enemy projectiles/telegraphs resolve faster (× windup).
    TelegraphSpeed(f32),
    PlayerDashCharges(i8),
    /// + fraction of bonus Ember for the run.
    EmberBonus(f32),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ChaosTierDef {
    pub tier: u8,
    pub name: String,
    #[serde(default)]
    pub desc: String,
    pub mods: Vec<ChaosMod>,
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Volatile {
    pub chance: f32,
    pub radius: f32,
    pub damage: f32,
    pub fuse: f32,
}

/// Everything the spawn director and enemy systems multiply by.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct EnemyTuning {
    pub hp: f32,
    pub boss_hp: f32,
    pub damage: f32,
    pub speed: f32,
    pub count: f32,
    pub spawn_rate: f32,
    pub elite_chance_add: f32,
    pub volatile: Option<Volatile>,
    pub elite_shield: f32,
    pub healing_received: f32,
    pub anvil_hold_time: f32,
    pub telegraph_time: f32,
    pub loot: f32,
    pub ember_mult: f32,
    pub player_dash_charges: i8,
}

pub fn compile_enemy_tuning(party: &PartyScaling, tiers: &[ChaosTierDef], active_tier: u8) -> EnemyTuning {
    let mut t = EnemyTuning {
        hp: party.enemy_hp,
        boss_hp: party.boss_hp,
        damage: 1.0,
        speed: 1.0,
        count: party.enemy_count,
        spawn_rate: 1.0,
        elite_chance_add: 0.0,
        volatile: None,
        elite_shield: 0.0,
        healing_received: 1.0,
        anvil_hold_time: 1.0,
        telegraph_time: 1.0,
        loot: party.loot,
        ember_mult: 1.0,
        player_dash_charges: 0,
    };
    let mut sorted: Vec<&ChaosTierDef> = tiers.iter().filter(|d| d.tier >= 1 && d.tier <= active_tier).collect();
    sorted.sort_by_key(|d| d.tier);
    for def in sorted {
        for m in &def.mods {
            match *m {
                ChaosMod::EnemyHp(x) => t.hp *= x,
                ChaosMod::EnemyDamage(x) => t.damage *= x,
                ChaosMod::EnemySpeed(x) => t.speed *= x,
                ChaosMod::SpawnRate(x) => t.spawn_rate *= x,
                ChaosMod::EnemyCount(x) => t.count *= x,
                ChaosMod::EliteChance(x) => t.elite_chance_add += x,
                ChaosMod::VolatileDeaths { chance, radius, damage, fuse } => {
                    t.volatile = Some(match t.volatile {
                        Some(v) => Volatile {
                            chance: (v.chance + chance).min(1.0),
                            radius: v.radius.max(radius),
                            damage: v.damage.max(damage),
                            fuse: v.fuse.min(fuse),
                        },
                        None => Volatile { chance, radius, damage, fuse },
                    })
                }
                ChaosMod::ShieldedElites(x) => t.elite_shield += x,
                ChaosMod::HealingReceived(x) => t.healing_received *= x,
                ChaosMod::AnvilHoldTime(x) => t.anvil_hold_time *= x,
                ChaosMod::BossHp(x) => t.boss_hp *= x,
                ChaosMod::TelegraphSpeed(x) => t.telegraph_time *= x,
                ChaosMod::PlayerDashCharges(n) => t.player_dash_charges += n,
                ChaosMod::EmberBonus(x) => t.ember_mult += x,
            }
        }
    }
    t.speed = t.speed.clamp(0.5, 2.0);
    t.telegraph_time = t.telegraph_time.clamp(0.4, 2.0);
    t
}

#[cfg(test)]
mod tests {
    use super::*;

    fn table() -> Vec<PartyScaling> {
        vec![
            PartyScaling { players: 1, enemy_hp: 1.0, enemy_count: 1.0, boss_hp: 1.0, loot: 1.0 },
            PartyScaling { players: 2, enemy_hp: 1.6, enemy_count: 1.5, boss_hp: 1.7, loot: 1.35 },
            PartyScaling { players: 3, enemy_hp: 2.1, enemy_count: 1.9, boss_hp: 2.3, loot: 1.6 },
            PartyScaling { players: 4, enemy_hp: 2.5, enemy_count: 2.3, boss_hp: 2.8, loot: 1.85 },
        ]
    }

    #[test]
    fn lookup_and_clamp() {
        assert_eq!(party_scaling(&table(), 3).enemy_hp, 2.1);
        assert_eq!(party_scaling(&table(), 7).players, 4);
        assert_eq!(party_scaling(&[], 2), PartyScaling::SOLO);
    }

    #[test]
    fn chaos_tiers_are_cumulative() {
        let tiers = vec![
            ChaosTierDef { tier: 1, name: "Swift".into(), desc: String::new(), mods: vec![ChaosMod::EnemySpeed(1.1)] },
            ChaosTierDef {
                tier: 2,
                name: "Hardened".into(),
                desc: String::new(),
                mods: vec![ChaosMod::EnemyHp(1.2), ChaosMod::EmberBonus(0.1)],
            },
            ChaosTierDef {
                tier: 3,
                name: "Volatile".into(),
                desc: String::new(),
                mods: vec![ChaosMod::VolatileDeaths { chance: 0.2, radius: 1.5, damage: 10.0, fuse: 0.8 }],
            },
        ];
        let party = party_scaling(&table(), 2);
        let t0 = compile_enemy_tuning(&party, &tiers, 0);
        assert_eq!(t0.speed, 1.0);
        assert_eq!(t0.hp, 1.6);
        let t2 = compile_enemy_tuning(&party, &tiers, 2);
        assert!((t2.speed - 1.1).abs() < 1e-5);
        assert!((t2.hp - 1.92).abs() < 1e-5);
        assert!((t2.ember_mult - 1.1).abs() < 1e-5);
        assert!(t2.volatile.is_none());
        let t3 = compile_enemy_tuning(&party, &tiers, 3);
        assert!(t3.volatile.is_some());
    }
}
