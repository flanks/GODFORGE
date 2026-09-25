//! Simulation components. Positions live on the ground plane (`Vec2`); presentation maps them to 3D.

use gf_content::schema::{Pulse, TelegraphShape};
use gf_core::aim::{AimMode, AimState, Deadeye, TargetBias};
use gf_core::damage::{DamageType, Plating, Resistances};
use gf_core::forge::{PartBag, PartInstance, WeaponBuild};
use gf_core::ids::{BoonId, CharacterId, EnemyId, NetId, RecipeId, SourceId};
use gf_core::modifier::Modifier;
use gf_core::movement::MoverState;
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_core::stats::PlayerStats;
use gf_core::status::{StatusKind, StatusSet};
use gf_core::synergy::ElementMarks;
use gf_core::weapon::WeaponProfile;
use gf_engine::prelude::*;
use gf_net::{AnvilState, DoorReward, HazardKind, PlayerCommand, Presses};
use std::collections::VecDeque;
use std::sync::Arc;

/// Everything clients can see carries a stable network id.
#[derive(Component, Clone, Copy, Debug)]
pub struct Replicated(pub NetId);

#[derive(Component, Clone, Copy, Debug, Default)]
pub struct Pos(pub Vec2);

#[derive(Component, Clone, Copy, Debug, Default)]
pub struct Vel(pub Vec2);

#[derive(Component, Clone, Copy, Debug)]
pub struct Facing(pub Vec2);

/// Which side an effect hurts.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Team {
    Players,
    Enemies,
}

// ───────────────────────────── players ─────────────────────────────

#[derive(Component, Debug)]
pub struct Player {
    pub slot: u8,
    pub character: CharacterId,
    pub name: String,
}

/// Latest command and the edges derived from it this tick.
#[derive(Component, Debug, Default)]
pub struct PlayerInput {
    pub cmd: PlayerCommand,
    pub prev: Presses,
    /// New presses this tick (counts).
    pub new: Presses,
    pub move_dir: Vec2,
    pub aim_dir: Vec2,
    pub aim_point: Vec2,
    pub fire: bool,
    pub has_input: bool,
}

#[derive(Component, Debug)]
pub struct Mover(pub MoverState);

#[derive(Component, Debug)]
pub struct Stats(pub PlayerStats);

#[derive(Component, Debug)]
pub struct Vitals {
    pub hp: f32,
    pub shield: f32,
    /// Seconds until the shield starts regenerating.
    pub shield_delay: f32,
    /// Extra (non-regenerating) shield from revives/abilities.
    pub bonus_shield: f32,
}

#[derive(Component, Debug)]
pub struct Life {
    pub state: LifeState,
    pub rekindles: u8,
}

/// The player's forge state: the weapon build, carried parts, run currencies, boons.
#[derive(Component, Debug)]
pub struct Arsenal {
    pub build: WeaponBuild,
    pub bag: PartBag,
    pub wallet: gf_core::forge::ForgeWallet,
    pub next_uid: u32,
    pub boons: Vec<(BoonId, Rarity)>,
    pub discovered: Vec<RecipeId>,
    pub active_recipes: Vec<RecipeId>,
}

impl Arsenal {
    pub fn alloc_uid(&mut self) -> u32 {
        self.next_uid += 1;
        self.next_uid
    }

    pub fn instance(&mut self, part: gf_core::ids::PartId, rarity: Rarity) -> PartInstance {
        PartInstance { uid: self.alloc_uid(), part, rarity }
    }
}

#[derive(Component, Debug)]
pub struct Gun {
    pub profile: Arc<WeaponProfile>,
    pub cooldown: f32,
    pub ramp_time: f32,
    pub shots: u32,
    pub charge: f32,
    pub prev_trigger: bool,
    pub firing: bool,
    pub beam: Option<(f32, f32)>,
    pub beam_tick: f32,
    /// Next-N-shots modifiers (Shadow Roll).
    pub next_shots: Option<(u8, Vec<Modifier>)>,
    pub melee_swing: f32,
    /// Fire button state last tick (AUTO: a fire press means "force-target next").
    pub fire_button_prev: bool,
}

#[derive(Component, Debug)]
pub struct Aim {
    pub mode: AimMode,
    pub bias: TargetBias,
    pub state: AimState,
    pub deadeye: Deadeye,
    pub dir: Vec2,
    pub target: Option<NetId>,
}

#[derive(Clone, Debug)]
pub struct ActiveBuff {
    pub remaining: f32,
    pub mods: Vec<Modifier>,
    pub root_self: bool,
    pub taunt: bool,
    pub scale: f32,
    pub pulse: Option<Pulse>,
    pub pulse_timer: f32,
    pub infinite_dash: bool,
    /// 0 = active1, 1 = active2, 2 = ultimate, 3 = overdrive, 4 = field.
    pub source: u8,
}

#[derive(Clone, Debug)]
pub enum PassiveState {
    None,
    Armor { armor: f32, break_cd: f32 },
    Static { charge: f32 },
    Ghost { crit: f32 },
}

/// A queued ability step waiting for a leap/rush to land or a delay to pass.
#[derive(Clone, Debug)]
pub struct PendingSteps {
    pub which: u8,
    pub steps: Vec<gf_content::schema::AbilityStep>,
    pub damage_mult: f32,
    pub aim_dir: Vec2,
    pub aim_point: Vec2,
}

#[derive(Clone, Copy, Debug)]
pub struct Airborne {
    pub from: Vec2,
    pub to: Vec2,
    pub t: f32,
    pub total: f32,
}

#[derive(Clone, Debug)]
pub struct Rush {
    pub dir: Vec2,
    pub speed: f32,
    pub remaining: f32,
    pub damage: f32,
    pub element: DamageType,
    pub drag: bool,
    pub hit: Vec<Entity>,
}

#[derive(Component, Debug)]
pub struct Kit {
    pub cooldowns: [f32; 2],
    pub cooldowns_max: [f32; 2],
    pub ult: f32,
    pub buffs: Vec<ActiveBuff>,
    pub pending: Option<PendingSteps>,
    pub airborne: Option<Airborne>,
    pub rush: Option<Rush>,
    pub passive: PassiveState,
    /// Stats / weapon need recompiling.
    pub dirty: bool,
    pub in_field_mods: Vec<Modifier>,
}

impl Kit {
    pub fn scale(&self) -> f32 {
        self.buffs.iter().map(|b| b.scale).fold(1.0, f32::max)
    }
    pub fn rooted(&self) -> bool {
        self.buffs.iter().any(|b| b.root_self)
    }
    pub fn taunting(&self) -> bool {
        self.buffs.iter().any(|b| b.taunt)
    }
    pub fn infinite_dash(&self) -> bool {
        self.buffs.iter().any(|b| b.infinite_dash)
    }
}

#[derive(Component, Debug, Default)]
pub struct RunStats {
    pub kills: u32,
    pub damage: f32,
    pub shards: u32,
    pub forge_actions: u32,
    pub synergies: u32,
    pub precision_hits: u32,
    pub shots: u32,
}

/// Damage taken per tick for Rewind Wounds.
#[derive(Component, Debug, Default)]
pub struct DamageHistory(pub VecDeque<(u32, f32)>);

#[derive(Component, Debug, Default)]
pub struct BoonChoice {
    pub offer: Vec<(BoonId, Rarity)>,
    pub rerolls: u8,
    pub god: Option<u16>,
}

// ───────────────────────────── enemies ─────────────────────────────

#[derive(Component, Debug)]
pub struct Enemy {
    pub def: EnemyId,
    pub class: gf_content::schema::EnemyClass,
    pub hp: f32,
    pub max_hp: f32,
    pub shield: f32,
    pub plating: Option<Plating>,
    pub resist: Resistances,
    pub speed: f32,
    pub radius: f32,
    pub mass: f32,
    pub contact: f32,
    pub damage_mult: f32,
    pub elite: bool,
    pub doom: u8,
    pub stun: f32,
    pub slow: f32,
    pub rooted_by_field: bool,
    pub taunt: Option<(Entity, f32)>,
    pub knock: Vec2,
    pub contact_cd: f32,
    pub volatile: bool,
    pub bonus_drops: bool,
    pub pinged: f32,
    pub last_hit_by: SourceId,
    pub hit_flash: f32,
}

impl Enemy {
    pub fn is_boss_like(&self) -> bool {
        matches!(self.class, gf_content::schema::EnemyClass::MiniBoss | gf_content::schema::EnemyClass::Boss)
    }
    pub fn control_class(&self) -> gf_core::status::ControlClass {
        use gf_core::status::ControlClass;
        match self.class {
            gf_content::schema::EnemyClass::Swarm => ControlClass::Normal,
            gf_content::schema::EnemyClass::Elite => ControlClass::Elite,
            _ => ControlClass::Boss,
        }
    }
}

#[derive(Component, Debug, Default)]
pub struct Statuses(pub StatusSet);

#[derive(Component, Debug, Default)]
pub struct Marks(pub ElementMarks);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum BrainState {
    #[default]
    Approach,
    Windup,
    Charging,
    Recover,
    Primed,
}

#[derive(Component, Debug, Default)]
pub struct Brain {
    pub state: BrainState,
    pub timer: f32,
    pub cooldown: f32,
    pub dir: Vec2,
    pub phase: f32,
    pub hit_players: u8,
}

#[derive(Component, Debug)]
pub struct BossBrain {
    pub script: u16,
    pub phase: usize,
    pub timer: f32,
    pub next_attack: usize,
    /// Delayed telegraph spawns (slam trails).
    pub queue: Vec<(f32, Vec2, f32)>,
}

// ───────────────────────────── combat entities ─────────────────────────────

#[derive(Component, Debug)]
pub struct Projectile {
    pub owner: SourceId,
    pub owner_entity: Option<Entity>,
    pub weapon: Arc<WeaponProfile>,
    pub damage: f32,
    pub dir: Vec2,
    pub speed: f32,
    pub radius: f32,
    pub life: f32,
    pub pierce: u8,
    pub bounces: u8,
    pub forked: bool,
    pub hits: Vec<Entity>,
    pub shot: u32,
    pub any_hit: bool,
    pub trail_timer: f32,
    /// Attacker-side multiplier (aim-mode tax × Deadeye × buffs).
    pub bonus: f32,
    pub crit_bonus: f32,
    pub precision_enabled: bool,
    pub origin: Vec2,
    pub t0: u32,
    pub steered: bool,
}

#[derive(Component, Debug)]
pub struct EnemyShot {
    pub dir: Vec2,
    pub speed: f32,
    pub damage: f32,
    pub radius: f32,
    pub life: f32,
    pub origin: Vec2,
    pub t0: u32,
}

#[derive(Clone, Debug)]
pub enum TeleEffect {
    Damage,
    /// Leave a hazard pool when resolved.
    Pool {
        radius: f32,
        duration: f32,
        dps: f32,
    },
    /// Player mortar: damage + knockback against enemies.
    PlayerNova {
        stun: f32,
        knockback: f32,
        status: Option<(StatusKind, u8, f32)>,
        source: SourceId,
    },
}

#[derive(Component, Debug)]
pub struct Telegraph {
    pub team: Team,
    pub shape: TelegraphShape,
    pub dir: Vec2,
    pub total: f32,
    pub remaining: f32,
    pub damage: f32,
    pub element: DamageType,
    pub start_tick: u32,
    pub effect: TeleEffect,
    pub owner: Option<Entity>,
}

#[derive(Component, Debug)]
pub struct Hazard {
    pub team: Team,
    pub kind: HazardKind,
    pub radius: f32,
    pub remaining: f32,
    /// Damage per second.
    pub dps: f32,
    pub element: DamageType,
    pub status: Option<(StatusKind, u8, f32)>,
    pub slow: f32,
    pub root: bool,
    pub pull: f32,
    pub owner: SourceId,
    pub tick_timer: f32,
    pub ally_mods: Vec<Modifier>,
    pub taunt: bool,
    pub bonus_drops: bool,
    pub vel: Vec2,
    pub origin: Vec2,
    pub t0: u32,
}

#[derive(Component, Debug)]
pub struct Barricade {
    pub half_len: f32,
    pub along: Vec2,
    pub hp: f32,
    pub remaining: f32,
}

#[derive(Component, Debug)]
pub struct Turret {
    pub owner: SourceId,
    pub owner_slot: u8,
    pub weapon: Arc<WeaponProfile>,
    pub power: f32,
    pub remaining: f32,
    pub cooldown: f32,
}

#[derive(Component, Debug)]
pub struct Blade {
    pub owner: Entity,
    pub owner_slot: u8,
    pub index: u8,
    pub count: u8,
    pub radius: f32,
    pub speed: f32,
    pub damage: f32,
    pub hit_cd: Vec<(Entity, f32)>,
}

#[derive(Clone, Copy, Debug)]
pub enum Loot {
    Part(PartInstance),
    Shards(u32),
    Health(f32),
}

#[derive(Component, Debug)]
pub struct Pickup {
    pub loot: Loot,
    /// Personal loot: only this slot can collect (and see) it.
    pub owner: Option<u8>,
    pub life: f32,
}

#[derive(Component, Debug)]
pub struct AnvilStation {
    pub state: AnvilState,
    pub progress: f32,
    pub forge_left: f32,
    pub contested: bool,
}

#[derive(Component, Debug)]
pub struct Door {
    pub reward: DoorReward,
    pub index: u8,
}

/// Room-scoped entities are despawned when the room changes.
#[derive(Component, Debug, Default)]
pub struct RoomScoped;
