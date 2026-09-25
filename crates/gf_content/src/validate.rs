//! Content validation. Every cross-reference, every sanity bound, and the EA scope targets (§15).
//! Errors fail `ContentDb::load_dir` and CI; warnings are reported by `gf_tools validate`.

use crate::db::{ContentDb, Keyed};
use crate::schema::*;
use gf_core::aim::AimMode;
use gf_core::forge::Slot;
use gf_core::modifier::Modifier;
use std::collections::{BTreeSet, HashMap};
use std::fmt;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Severity {
    Warning,
    Error,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Issue {
    pub severity: Severity,
    pub table: &'static str,
    pub key: String,
    pub message: String,
}

impl fmt::Display for Issue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let sev = match self.severity {
            Severity::Error => "error",
            Severity::Warning => "warning",
        };
        write!(f, "{sev}: {}[{}]: {}", self.table, self.key, self.message)
    }
}

struct Report(Vec<Issue>);

impl Report {
    fn err(&mut self, table: &'static str, key: &str, msg: impl Into<String>) {
        self.0.push(Issue { severity: Severity::Error, table, key: key.to_string(), message: msg.into() });
    }
    fn warn(&mut self, table: &'static str, key: &str, msg: impl Into<String>) {
        self.0.push(Issue { severity: Severity::Warning, table, key: key.to_string(), message: msg.into() });
    }
}

fn valid_key(k: &str) -> bool {
    !k.is_empty() && k.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

/// `#RRGGBB` hex colors only.
pub fn parse_hex_color(s: &str) -> Option<[u8; 3]> {
    let h = s.strip_prefix('#')?;
    if h.len() != 6 {
        return None;
    }
    let v = u32::from_str_radix(h, 16).ok()?;
    Some([(v >> 16) as u8, (v >> 8) as u8, v as u8])
}

fn check_keys<'a, T: Keyed + 'a>(r: &mut Report, table: &'static str, rows: impl Iterator<Item = &'a T>) {
    for row in rows {
        if !valid_key(row.key()) {
            r.err(table, row.key(), "keys must be lower_snake_case ascii");
        }
    }
}

fn finite_positive(v: f32) -> bool {
    v.is_finite() && v > 0.0
}

/// Modifiers that make sense in each forge slot.
fn slot_allows(slot: Slot, m: &Modifier) -> bool {
    use Modifier::*;
    match slot {
        // Cores own element & projectile identity; orbiting blades are a Mechanism.
        Slot::Core => !matches!(m, Orbit { .. }),
        // Sigils are god-soul passives: anything goes.
        Slot::Sigil => true,
        // Mechanisms and Relics never change element (that is the Core's job).
        Slot::Mechanism | Slot::Relic => !matches!(m, Element(_)),
    }
}

pub fn validate(db: &ContentDb) -> Vec<Issue> {
    let mut r = Report(Vec::new());

    // ── keys ──
    check_keys(&mut r, "gods", db.gods.iter());
    check_keys(&mut r, "characters", db.characters.iter());
    check_keys(&mut r, "chassis", db.chassis.iter());
    check_keys(&mut r, "parts", db.parts.iter());
    check_keys(&mut r, "boons", db.boons.iter());
    check_keys(&mut r, "recipes", db.recipes.iter());
    check_keys(&mut r, "synergies", db.synergies.iter());
    check_keys(&mut r, "enemies", db.enemies.iter());
    check_keys(&mut r, "bosses", db.bosses.iter());
    check_keys(&mut r, "rooms", db.rooms.iter());
    check_keys(&mut r, "biomes", db.biomes.iter());
    check_keys(&mut r, "altar", db.altar.iter());
    check_keys(&mut r, "trees", db.trees.iter());
    check_keys(&mut r, "achievements", db.achievements.iter());
    check_keys(&mut r, "barks", db.barks.iter());

    // ── game tuning ──
    for (i, c) in db.game.player_colors.iter().enumerate() {
        if parse_hex_color(c).is_none() {
            r.err("game", &format!("player_colors[{i}]"), format!("`{c}` is not #RRGGBB"));
        }
    }
    if parse_hex_color(&db.game.telegraph_color).is_none() {
        r.err("game", "telegraph_color", "not #RRGGBB");
    }
    if db.game.anvil.hold_time <= 0.0 || db.game.anvil.radius <= 0.0 {
        r.err("game", "anvil", "hold_time and radius must be positive");
    }
    if db.game.revive.downed_duration + db.game.revive.reforge_delay > 30.0 + 1e-3 {
        r.err("game", "revive", "no player may be out of the fight longer than 30 s (§10)");
    }

    // ── aim modes: exactly one per mode; the balance contract ──
    for mode in AimMode::ALL {
        let n = db.aim_modes.iter().filter(|p| p.mode == mode).count();
        if n != 1 {
            r.err("aim_modes", mode.name(), format!("expected exactly one row, found {n}"));
        }
    }
    if let Some(auto) = db.aim_modes.iter().find(|p| p.mode == AimMode::Auto) {
        if !(0.8..=0.95).contains(&auto.damage_mult) {
            r.warn("aim_modes", "AUTO", "balance contract: AUTO damage tax should be ~10%");
        }
        if !auto.auto_fire {
            r.err("aim_modes", "AUTO", "AUTO must auto-fire");
        }
    }
    if let Some(manual) = db.aim_modes.iter().find(|p| p.mode == AimMode::Manual)
        && (manual.magnetism_strength > 0.0 || manual.target_selection)
    {
        r.err("aim_modes", "MANUAL", "MANUAL must have zero magnetism and no target selection");
    }

    // ── party scaling ──
    let mut players: Vec<u8> = db.party_scaling.iter().map(|p| p.players).collect();
    players.sort_unstable();
    if players != [1, 2, 3, 4] {
        r.err("party_scaling", "players", format!("need rows for 1..=4 players, found {players:?}"));
    }
    for w in db.party_scaling.windows(2) {
        if w[1].enemy_hp < w[0].enemy_hp || w[1].enemy_count < w[0].enemy_count {
            r.err("party_scaling", &w[1].players.to_string(), "scaling must not decrease with party size");
        }
    }

    // ── chaos tiers: contiguous 1..=N ──
    for (i, t) in db.chaos_tiers.iter().enumerate() {
        if t.tier as usize != i + 1 {
            r.err("chaos_tiers", &t.tier.to_string(), "tiers must be contiguous starting at 1, in order");
        }
        if t.mods.is_empty() {
            r.err("chaos_tiers", &t.tier.to_string(), "a tier must add at least one mutator");
        }
    }

    // ── gods ──
    for g in db.gods.iter() {
        for c in [&g.color, &g.color_secondary] {
            if parse_hex_color(c).is_none() {
                r.err("gods", &g.key, format!("color `{c}` is not #RRGGBB"));
            }
        }
    }

    // ── chassis ──
    for c in db.chassis.iter() {
        let s = &c.stats;
        if !finite_positive(s.damage) || !finite_positive(s.fire_rate) || !finite_positive(s.range) {
            r.err("chassis", &c.key, "damage, fire_rate and range must be positive");
        }
        if s.speed < 0.0 || s.projectiles == 0 {
            r.err("chassis", &c.key, "speed must be ≥ 0 and projectiles ≥ 1");
        }
        if s.fire == gf_core::weapon::FireKind::Charge && s.charge_time <= 0.0 {
            r.err("chassis", &c.key, "charge chassis need a charge_time");
        }
        if !(0.0..=1.0).contains(&s.crit_chance) {
            r.err("chassis", &c.key, "crit_chance must be within 0..=1");
        }
    }

    // ── parts ──
    for p in db.parts.iter() {
        if p.mods.is_empty() {
            r.err("parts", &p.key, "a part must have at least one modifier");
        }
        for m in &p.mods {
            if !slot_allows(p.slot, m) {
                r.err("parts", &p.key, format!("{:?} slot cannot carry {:?}", p.slot, m));
            }
        }
        if p.slot == Slot::Core && !p.mods.iter().any(|m| matches!(m, Modifier::Element(_))) {
            r.err("parts", &p.key, "Cores define element identity: add an Element(..) modifier");
        }
        if p.slot == Slot::Sigil {
            match &p.god {
                Some(g) if db.gods.id(g).is_some() => {}
                Some(g) => r.err("parts", &p.key, format!("unknown god `{g}`")),
                None => r.err("parts", &p.key, "Sigils carry a god-soul: set `god`"),
            }
        } else if p.god.as_ref().is_some_and(|g| db.gods.id(g).is_none()) {
            r.err("parts", &p.key, "unknown god");
        }
        if !finite_positive(p.weight) {
            r.err("parts", &p.key, "weight must be positive");
        }
    }

    // ── characters & kits ──
    for c in db.characters.iter() {
        if db.chassis.id(&c.signature_chassis).is_none() {
            r.err("characters", &c.key, format!("unknown signature chassis `{}`", c.signature_chassis));
        }
        for s in &c.sigils {
            match db.parts.by_key(s) {
                Some(p) if p.slot == Slot::Sigil => {}
                Some(_) => r.err("characters", &c.key, format!("`{s}` is not a Sigil")),
                None => r.err("characters", &c.key, format!("unknown sigil `{s}`")),
            }
        }
        if parse_hex_color(&c.color).is_none() {
            r.err("characters", &c.key, "color is not #RRGGBB");
        }
        if !finite_positive(c.stats.max_hp) || !finite_positive(c.stats.move_speed) {
            r.err("characters", &c.key, "max_hp and move_speed must be positive");
        }
    }
    for k in &db.unknown_kits {
        r.err("kits", k, "kit for unknown character");
    }
    for (i, kit) in db.kits.iter().enumerate() {
        let Some(kit) = kit else { continue };
        let key = &db.characters.get(i as u16).key;
        for (slot, a) in [("active1", &kit.active1), ("active2", &kit.active2)] {
            if a.cooldown <= 0.0 {
                r.err("kits", key, format!("{slot} needs a positive cooldown"));
            }
            if a.steps.is_empty() {
                r.err("kits", key, format!("{slot} has no steps"));
            }
        }
        if kit.ultimate.steps.is_empty() {
            r.err("kits", key, "ultimate has no steps");
        }
    }

    // ── boons ──
    let mut legendaries: HashMap<&str, usize> = HashMap::new();
    for b in db.boons.iter() {
        for g in &b.gods {
            if db.gods.id(g).is_none() {
                r.err("boons", &b.key, format!("unknown god `{g}`"));
            }
        }
        match b.kind {
            BoonKind::Standard | BoonKind::Legendary if b.gods.len() != 1 => {
                r.err("boons", &b.key, "standard/legendary boons belong to exactly one god")
            }
            BoonKind::Duo => {
                if b.gods.len() != 2 || b.gods[0] == b.gods[1] {
                    r.err("boons", &b.key, "duo boons need two distinct gods");
                }
                for g in &b.gods {
                    if !b.requires.iter().any(|req| matches!(req, BoonReq::FromGod { god, .. } if god == g)) {
                        r.err("boons", &b.key, format!("duo boon must require a boon from `{g}`"));
                    }
                }
            }
            BoonKind::Team if b.gods.len() > 1 => r.err("boons", &b.key, "team boons have at most one god"),
            _ => {}
        }
        if b.kind == BoonKind::Legendary
            && let Some(g) = b.gods.first()
        {
            *legendaries.entry(g.as_str()).or_default() += 1;
        }
        for req in &b.requires {
            match req {
                BoonReq::FromGod { god, count } => {
                    if db.gods.id(god).is_none() {
                        r.err("boons", &b.key, format!("requires unknown god `{god}`"));
                    }
                    if *count == 0 {
                        r.err("boons", &b.key, "FromGod count must be ≥ 1");
                    }
                }
                BoonReq::Boon(k) => {
                    if db.boons.id(k).is_none() {
                        r.err("boons", &b.key, format!("requires unknown boon `{k}`"));
                    }
                }
            }
        }
        if b.mods.is_empty() {
            r.err("boons", &b.key, "a boon must have at least one modifier");
        }
    }
    for g in db.gods.iter() {
        let n = legendaries.get(g.key.as_str()).copied().unwrap_or(0);
        if n > 1 {
            r.err("boons", &g.key, format!("one Legendary per god at launch, found {n}"));
        } else if n == 0 && !db.boons.is_empty() {
            r.warn("boons", &g.key, "god has no Legendary boon yet");
        }
    }

    // ── recipes ──
    let mut recipe_sets: HashMap<String, &str> = HashMap::new();
    for (i, rec) in db.recipes.enumerate() {
        if rec.ingredients.len() < 2 {
            r.err("recipes", &rec.key, "a named combo needs at least two ingredients");
        }
        if db.recipe_ingredients[i as usize].len() != rec.ingredients.len() {
            for ing in &rec.ingredients {
                match ing {
                    IngredientKey::Chassis(k) if db.chassis.id(k).is_none() => {
                        r.err("recipes", &rec.key, format!("unknown chassis `{k}`"))
                    }
                    IngredientKey::Part(k) if db.parts.id(k).is_none() => {
                        r.err("recipes", &rec.key, format!("unknown part `{k}`"))
                    }
                    _ => {}
                }
            }
        }
        // Two parts in the same slot can never be equipped together.
        let mut slots = BTreeSet::new();
        for ing in &rec.ingredients {
            if let IngredientKey::Part(k) = ing
                && let Some(p) = db.parts.by_key(k)
                && !slots.insert(p.slot)
            {
                r.err("recipes", &rec.key, format!("two ingredients share the {:?} slot — unbuildable", p.slot));
            }
        }
        let mut sig: Vec<String> = rec.ingredients.iter().map(|i| format!("{i:?}")).collect();
        sig.sort();
        if let Some(other) = recipe_sets.insert(sig.join("+"), &rec.key) {
            r.err("recipes", &rec.key, format!("same ingredients as `{other}`"));
        }
    }

    // ── synergies ──
    let mut pairs = BTreeSet::new();
    for s in db.synergies.iter() {
        if s.a == s.b {
            r.err("synergies", &s.key, "a synergy pairs two different elements");
        }
        let pair = if s.a <= s.b { (s.a, s.b) } else { (s.b, s.a) };
        if !pairs.insert(pair) {
            r.err("synergies", &s.key, "duplicate element pair");
        }
    }

    // ── enemies & bosses ──
    for e in db.enemies.iter() {
        if e.biome != "any" && db.biomes.id(&e.biome).is_none() {
            r.err("enemies", &e.key, format!("unknown biome `{}`", e.biome));
        }
        if !finite_positive(e.hp) || e.speed < 0.0 || !finite_positive(e.radius) {
            r.err("enemies", &e.key, "hp and radius must be positive, speed ≥ 0");
        }
        if parse_hex_color(&e.color).is_none() {
            r.err("enemies", &e.key, "color is not #RRGGBB");
        }
        if e.pack.0 == 0 || e.pack.0 > e.pack.1 {
            r.err("enemies", &e.key, "pack range must be 1 ≤ min ≤ max");
        }
        match &e.behavior {
            EnemyBehavior::Boss { script } => {
                if db.bosses.id(script).is_none() {
                    r.err("enemies", &e.key, format!("unknown boss script `{script}`"));
                }
                if !matches!(e.class, EnemyClass::MiniBoss | EnemyClass::Boss) {
                    r.err("enemies", &e.key, "only mini-bosses and bosses run boss scripts");
                }
            }
            EnemyBehavior::Charger { windup, .. }
            | EnemyBehavior::Lobber { windup, .. }
            | EnemyBehavior::Caster { windup, .. }
                if *windup < 0.3 =>
            {
                r.err("enemies", &e.key, "telegraph windup must be ≥ 0.3 s — no invisible damage (§5)");
            }
            _ => {}
        }
    }
    for b in db.bosses.iter() {
        if b.phases.is_empty() {
            r.err("bosses", &b.key, "a boss needs at least one phase");
        }
        let mut last = f32::INFINITY;
        for p in &b.phases {
            if p.below > last {
                r.err("bosses", &b.key, "phases must be ordered by descending HP threshold");
            }
            last = p.below;
            if p.attacks.is_empty() {
                r.err("bosses", &b.key, format!("phase `{}` has no attacks", p.name));
            }
            for a in &p.attacks {
                let windup = match a {
                    BossAttack::Strike { windup, .. }
                    | BossAttack::SlamTrail { windup, .. }
                    | BossAttack::Pools { windup, .. } => Some(*windup),
                    _ => None,
                };
                if windup.is_some_and(|w| w < 0.4) {
                    r.err("bosses", &b.key, "boss telegraphs must wind up ≥ 0.4 s");
                }
                if let BossAttack::Summon { enemy, .. } = a
                    && db.enemies.id(enemy).is_none()
                {
                    r.err("bosses", &b.key, format!("summons unknown enemy `{enemy}`"));
                }
            }
        }
    }

    // ── rooms ──
    for room in db.rooms.iter() {
        if db.biomes.id(&room.biome).is_none() {
            r.err("rooms", &room.key, format!("unknown biome `{}`", room.biome));
        }
        let arena = gf_core::movement::Arena { half_extents: room.half_extents, obstacles: room.obstacles.clone() };
        if !arena.in_bounds(room.player_spawn) || room.obstacles.iter().any(|o| o.contains(room.player_spawn, 0.5)) {
            r.err("rooms", &room.key, "player_spawn must be inside the arena and clear of obstacles");
        }
        if room.kind == RoomKind::Anvil && room.anvil.is_none() {
            r.err("rooms", &room.key, "anvil rooms need an anvil position");
        }
        if let Some(a) = room.anvil
            && !arena.in_bounds(a)
        {
            r.err("rooms", &room.key, "anvil outside the arena");
        }
        if room.kind != RoomKind::Boss && room.exits.is_empty() {
            r.err("rooms", &room.key, "non-boss rooms need at least one exit");
        }
        if room.spawn_zones.is_empty() {
            r.err("rooms", &room.key, "rooms need at least one spawn zone");
        }
        for f in &room.encounter.fixed {
            if db.enemies.id(f).is_none() {
                r.err("rooms", &room.key, format!("fixed spawn of unknown enemy `{f}`"));
            }
        }
    }

    // ── biomes ──
    for b in db.biomes.iter() {
        for c in &b.palette {
            if parse_hex_color(c).is_none() {
                r.err("biomes", &b.key, format!("palette color `{c}` is not #RRGGBB"));
            }
        }
        let class_of = |k: &str| db.enemies.by_key(k).map(|e| e.class);
        for w in &b.swarm {
            match class_of(&w.key) {
                Some(EnemyClass::Swarm) => {}
                Some(c) => r.err("biomes", &b.key, format!("`{}` in swarm pool is {c:?}", w.key)),
                None => r.err("biomes", &b.key, format!("unknown enemy `{}`", w.key)),
            }
        }
        for w in &b.elites {
            match class_of(&w.key) {
                Some(EnemyClass::Elite) => {}
                Some(c) => r.err("biomes", &b.key, format!("`{}` in elite pool is {c:?}", w.key)),
                None => r.err("biomes", &b.key, format!("unknown enemy `{}`", w.key)),
            }
        }
        for m in &b.minibosses {
            if class_of(m) != Some(EnemyClass::MiniBoss) {
                r.err("biomes", &b.key, format!("`{m}` is not a mini-boss"));
            }
        }
        if class_of(&b.boss) != Some(EnemyClass::Boss) {
            r.err("biomes", &b.key, format!("`{}` is not a boss", b.boss));
        }
        for step in &b.sequence {
            let kind = match step {
                RunStep::Door => RoomKind::Combat,
                RunStep::Fixed(k) => *k,
            };
            if !db.rooms.iter().any(|room| room.biome == b.key && room.kind == kind) {
                r.err("biomes", &b.key, format!("sequence needs a {kind:?} room but the biome has none"));
            }
        }
        if b.sequence.contains(&RunStep::Door)
            && !db.rooms.iter().any(|room| room.biome == b.key && room.kind == RoomKind::Anvil)
        {
            r.err("biomes", &b.key, "door rooms can lead to anvils: the biome needs an Anvil room");
        }
    }

    // ── meta ──
    for n in db.altar.iter() {
        for req in &n.requires {
            if db.altar.id(req).is_none() {
                r.err("altar", &n.key, format!("requires unknown node `{req}`"));
            }
        }
        if let AltarEffect::Unlock(k) = &n.effect
            && db.chassis.id(k).is_none()
            && db.parts.id(k).is_none()
            && db.characters.id(k).is_none()
        {
            r.err("altar", &n.key, format!("unlocks unknown content `{k}`"));
        }
    }
    for n in db.trees.iter() {
        if db.characters.id(&n.character).is_none() {
            r.err("trees", &n.key, format!("unknown character `{}`", n.character));
        }
        for req in &n.requires {
            if db.trees.id(req).is_none() {
                r.err("trees", &n.key, format!("requires unknown node `{req}`"));
            }
        }
        if let Some(u) = &n.unlock
            && db.parts.id(u).is_none()
        {
            r.err("trees", &n.key, format!("unlocks unknown part `{u}`"));
        }
    }
    for b in db.barks.iter() {
        let hub = ["smithshade", "vessa", "hound9"];
        if !hub.contains(&b.speaker.as_str()) && db.characters.id(&b.speaker).is_none() {
            r.err("barks", &b.key, format!("unknown speaker `{}`", b.speaker));
        }
    }

    // ── EA scope targets (§15) — warnings until met ──
    let targets: [(&str, usize, usize); 9] = [
        ("characters", db.characters.iter().filter(|c| c.phase <= Phase::EA).count(), 8),
        ("chassis", db.chassis.iter().filter(|c| c.phase <= Phase::EA).count(), 16),
        ("parts", db.parts.iter().filter(|p| p.phase <= Phase::EA).count(), 120),
        ("boons", db.boons.iter().filter(|b| b.kind != BoonKind::Duo && b.phase <= Phase::EA).count(), 100),
        ("duo boons", db.boons.iter().filter(|b| b.kind == BoonKind::Duo && b.phase <= Phase::EA).count(), 16),
        ("synergies", db.synergies.len(), 12),
        ("chaos tiers", db.chaos_tiers.len(), 20),
        ("achievements", db.achievements.iter().filter(|a| a.phase <= Phase::EA).count(), 80),
        ("biomes", db.biomes.iter().filter(|b| b.phase <= Phase::EA).count(), 3),
    ];
    for (what, have, want) in targets {
        if have < want {
            r.warn("scope", what, format!("EA target is {want}, content has {have}"));
        }
    }

    r.0.sort_by(|a, b| b.severity.cmp(&a.severity).then(a.table.cmp(b.table)).then(a.key.cmp(&b.key)));
    r.0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_colors() {
        assert_eq!(parse_hex_color("#FFD24A"), Some([0xFF, 0xD2, 0x4A]));
        assert_eq!(parse_hex_color("FFD24A"), None);
        assert_eq!(parse_hex_color("#FFF"), None);
        assert_eq!(parse_hex_color("#GGGGGG"), None);
    }

    #[test]
    fn keys() {
        assert!(valid_key("colossus_cannon"));
        assert!(!valid_key("Colossus"));
        assert!(!valid_key("a-b"));
        assert!(!valid_key(""));
    }
}
