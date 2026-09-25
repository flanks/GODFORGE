//! The loaded, resolved content database.

use crate::ContentError;
use crate::schema::*;
use crate::validate::{self, Severity};
use gf_core::aim::{AimMode, AimModeParams};
use gf_core::forge::{Ingredient, Slot};
use gf_core::ids::*;
use gf_core::modifier::Modifier;
use gf_core::rarity::Rarity;
use gf_core::scaling::{ChaosTierDef, PartyScaling};
use gf_core::synergy::SynergyRule;
use serde::de::DeserializeOwned;
use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};

/// Rows with a unique string key.
pub trait Keyed {
    fn key(&self) -> &str;
}

macro_rules! keyed {
    ($($t:ty),* $(,)?) => {$(
        impl Keyed for $t {
            fn key(&self) -> &str {
                &self.key
            }
        }
    )*};
}
keyed!(
    GodDef,
    CharacterDef,
    ChassisDef,
    PartDef,
    BoonDef,
    RecipeDef,
    SynergyDef,
    EnemyDef,
    RoomDef,
    BiomeDef,
    AltarNode,
    TreeNode,
    AchievementDef,
    BarkDef,
    BossScript
);

/// A keyed table. Row order is authoring order; a row's position is its compact id.
#[derive(Clone, Debug)]
pub struct Table<T> {
    rows: Vec<T>,
    index: HashMap<String, u16>,
}

impl<T> Default for Table<T> {
    fn default() -> Self {
        Self { rows: Vec::new(), index: HashMap::new() }
    }
}

impl<T: Keyed> Table<T> {
    pub fn new(table: &'static str, rows: Vec<T>) -> Result<Self, ContentError> {
        let mut index = HashMap::with_capacity(rows.len());
        for (i, r) in rows.iter().enumerate() {
            if index.insert(r.key().to_string(), i as u16).is_some() {
                return Err(ContentError::DuplicateKey { table, key: r.key().to_string() });
            }
        }
        Ok(Self { rows, index })
    }

    #[inline]
    pub fn id(&self, key: &str) -> Option<u16> {
        self.index.get(key).copied()
    }

    #[inline]
    pub fn by_key(&self, key: &str) -> Option<&T> {
        self.id(key).map(|i| &self.rows[i as usize])
    }

    #[inline]
    pub fn get(&self, id: u16) -> &T {
        &self.rows[id as usize]
    }

    #[inline]
    pub fn try_get(&self, id: u16) -> Option<&T> {
        self.rows.get(id as usize)
    }

    pub fn len(&self) -> usize {
        self.rows.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rows.is_empty()
    }

    pub fn iter(&self) -> impl Iterator<Item = &T> {
        self.rows.iter()
    }

    /// `(id, row)` pairs.
    pub fn enumerate(&self) -> impl Iterator<Item = (u16, &T)> {
        self.rows.iter().enumerate().map(|(i, r)| (i as u16, r))
    }

    pub fn rows(&self) -> &[T] {
        &self.rows
    }
}

/// Everything the game knows, loaded from `assets/content`.
#[derive(Clone, Debug)]
pub struct ContentDb {
    pub game: GameTuning,
    pub aim_modes: Vec<AimModeParams>,
    pub party_scaling: Vec<PartyScaling>,
    pub chaos_tiers: Vec<ChaosTierDef>,
    pub gods: Table<GodDef>,
    pub characters: Table<CharacterDef>,
    /// Indexed by `CharacterId`; `None` means not yet playable.
    pub kits: Vec<Option<KitDef>>,
    pub chassis: Table<ChassisDef>,
    pub parts: Table<PartDef>,
    pub boons: Table<BoonDef>,
    pub recipes: Table<RecipeDef>,
    pub synergies: Table<SynergyDef>,
    pub enemies: Table<EnemyDef>,
    pub bosses: Table<BossScript>,
    pub rooms: Table<RoomDef>,
    pub biomes: Table<BiomeDef>,
    pub altar: Table<AltarNode>,
    pub trees: Table<TreeNode>,
    pub achievements: Table<AchievementDef>,
    pub barks: Table<BarkDef>,
    /// Resolved recipe ingredients, indexed by `RecipeId`.
    pub recipe_ingredients: Vec<Vec<Ingredient>>,
    /// Resolved synergy rules, indexed by `SynergyId`.
    pub synergy_rules: Vec<SynergyRule>,
    /// `kits.ron` rows naming characters that do not exist (reported by validation).
    pub unknown_kits: Vec<String>,
    /// FNV-1a hash of the normalized content; exchanged in the network handshake.
    pub hash: u64,
}

/// RON options shared by every loader and writer (implicit `Some` keeps authored files terse).
pub fn ron_options() -> ron::Options {
    ron::Options::default().with_default_extension(ron::extensions::Extensions::IMPLICIT_SOME)
}

fn fnv1a(bytes: &[u8], mut h: u64) -> u64 {
    for b in bytes {
        h ^= *b as u64;
        h = h.wrapping_mul(0x0100_0000_01b3);
    }
    h
}

/// The raw text of every content file, keyed by its path relative to the content dir.
/// The game reads these from disk; `gf_tools` builds them in memory straight from the sheets.
#[derive(Clone, Debug, Default)]
pub struct ContentSources {
    pub files: BTreeMap<String, String>,
}

impl ContentSources {
    pub fn read_dir(dir: &Path) -> Result<Self, ContentError> {
        let mut files = BTreeMap::new();
        for f in CONTENT_FILES {
            let path = dir.join(f);
            let text = std::fs::read_to_string(&path).map_err(|source| ContentError::Io { path, source })?;
            files.insert((*f).to_string(), text);
        }
        Ok(Self { files })
    }

    fn get(&self, name: &str) -> Result<&str, ContentError> {
        self.files.get(name).map(String::as_str).ok_or_else(|| ContentError::Io {
            path: PathBuf::from(name),
            source: std::io::Error::new(std::io::ErrorKind::NotFound, "missing content file"),
        })
    }

    fn parse<T: DeserializeOwned>(&self, name: &str) -> Result<T, ContentError> {
        ron_options()
            .from_str(self.get(name)?)
            .map_err(|e| ContentError::Parse { path: PathBuf::from(name), message: e.to_string() })
    }

    /// FNV-1a over file names and line-ending-normalized contents, in `CONTENT_FILES` order.
    pub fn hash(&self) -> u64 {
        let mut hash = 0xcbf2_9ce4_8422_2325u64;
        for f in CONTENT_FILES {
            hash = fnv1a(f.as_bytes(), hash);
            if let Some(text) = self.files.get(*f) {
                let normalized: Vec<u8> = text.bytes().filter(|b| *b != b'\r').collect();
                hash = fnv1a(&normalized, hash);
            }
        }
        hash
    }
}

/// Files that make up a content set, in hashing order.
pub const CONTENT_FILES: &[&str] = &[
    "game.ron",
    "aim_modes.ron",
    "kits.ron",
    "bosses.ron",
    "rooms.ron",
    "biomes.ron",
    "generated/party_scaling.ron",
    "generated/chaos_tiers.ron",
    "generated/gods.ron",
    "generated/characters.ron",
    "generated/chassis.ron",
    "generated/parts.ron",
    "generated/boons.ron",
    "generated/recipes.ron",
    "generated/synergies.ron",
    "generated/enemies.ron",
    "generated/altar.ron",
    "generated/trees.ron",
    "generated/achievements.ron",
    "generated/barks.ron",
];

impl ContentDb {
    /// Load, resolve and validate a content directory. Validation *errors* fail the load;
    /// warnings (e.g. EA content counts not yet met) are returned by [`ContentDb::validate`].
    pub fn load_dir(dir: &Path) -> Result<Self, ContentError> {
        Self::from_sources_validated(&ContentSources::read_dir(dir)?)
    }

    /// Resolve and validate in-memory sources.
    pub fn from_sources_validated(src: &ContentSources) -> Result<Self, ContentError> {
        let db = Self::from_sources(src)?;
        let errors: Vec<_> = db.validate().into_iter().filter(|i| i.severity == Severity::Error).collect();
        if errors.is_empty() { Ok(db) } else { Err(ContentError::Invalid(errors)) }
    }

    /// Resolve without validation (tools use this to report every issue at once).
    pub fn from_sources(src: &ContentSources) -> Result<Self, ContentError> {
        let hash = src.hash();
        let game: GameTuning = src.parse("game.ron")?;
        let aim_modes: Vec<AimModeParams> = src.parse("aim_modes.ron")?;
        let kits_raw: Vec<KitDef> = src.parse("kits.ron")?;
        let bosses = Table::new("bosses", src.parse("bosses.ron")?)?;
        let rooms = Table::new("rooms", src.parse("rooms.ron")?)?;
        let biomes = Table::new("biomes", src.parse("biomes.ron")?)?;
        let party_scaling: Vec<PartyScaling> = src.parse("generated/party_scaling.ron")?;
        let chaos_tiers: Vec<ChaosTierDef> = src.parse("generated/chaos_tiers.ron")?;
        let gods = Table::new("gods", src.parse("generated/gods.ron")?)?;
        let characters: Table<CharacterDef> = Table::new("characters", src.parse("generated/characters.ron")?)?;
        let chassis = Table::new("chassis", src.parse("generated/chassis.ron")?)?;
        let parts: Table<PartDef> = Table::new("parts", src.parse("generated/parts.ron")?)?;
        let boons = Table::new("boons", src.parse("generated/boons.ron")?)?;
        let recipes: Table<RecipeDef> = Table::new("recipes", src.parse("generated/recipes.ron")?)?;
        let synergies: Table<SynergyDef> = Table::new("synergies", src.parse("generated/synergies.ron")?)?;
        let enemies = Table::new("enemies", src.parse("generated/enemies.ron")?)?;
        let altar = Table::new("altar", src.parse("generated/altar.ron")?)?;
        let trees = Table::new("trees", src.parse("generated/trees.ron")?)?;
        let achievements = Table::new("achievements", src.parse("generated/achievements.ron")?)?;
        let barks = Table::new("barks", src.parse("generated/barks.ron")?)?;
        let mut kits: Vec<Option<KitDef>> = vec![None; characters.len()];
        let mut unknown_kits = Vec::new();
        for kit in kits_raw {
            match characters.id(&kit.character) {
                Some(id) => kits[id as usize] = Some(kit),
                None => unknown_kits.push(kit.character),
            }
        }

        let recipe_ingredients = recipes
            .iter()
            .map(|r| {
                r.ingredients
                    .iter()
                    .filter_map(|ing| match ing {
                        IngredientKey::Chassis(k) => chassis.id(k).map(|i| Ingredient::Chassis(ChassisId(i))),
                        IngredientKey::Part(k) => parts.id(k).map(|i| Ingredient::Part(PartId(i))),
                        IngredientKey::Element(e) => Some(Ingredient::Element(*e)),
                    })
                    .collect()
            })
            .collect();
        let synergy_rules = synergies
            .enumerate()
            .map(|(i, s)| SynergyRule { id: SynergyId(i), a: s.a, b: s.b, effect: s.effect.clone() })
            .collect();

        let db = ContentDb {
            game,
            aim_modes,
            party_scaling,
            chaos_tiers,
            gods,
            characters,
            kits,
            chassis,
            parts,
            boons,
            recipes,
            synergies,
            enemies,
            bosses,
            rooms,
            biomes,
            altar,
            trees,
            achievements,
            barks,
            recipe_ingredients,
            synergy_rules,
            unknown_kits,
            hash,
        };
        Ok(db)
    }

    /// Full validation report (errors and warnings).
    pub fn validate(&self) -> Vec<crate::Issue> {
        validate::validate(self)
    }

    // ───── convenience lookups ─────

    pub fn aim_params(&self, mode: AimMode) -> AimModeParams {
        self.aim_modes.iter().find(|p| p.mode == mode).cloned().unwrap_or_else(|| AimModeParams::defaults(mode))
    }

    pub fn character(&self, id: CharacterId) -> &CharacterDef {
        self.characters.get(id.0)
    }

    pub fn kit(&self, id: CharacterId) -> Option<&KitDef> {
        self.kits.get(id.index()).and_then(|k| k.as_ref())
    }

    pub fn playable_characters(&self) -> impl Iterator<Item = (CharacterId, &CharacterDef)> {
        self.characters.enumerate().filter(|(i, _)| self.kits[*i as usize].is_some()).map(|(i, c)| (CharacterId(i), c))
    }

    pub fn chassis_def(&self, id: ChassisId) -> &ChassisDef {
        self.chassis.get(id.0)
    }

    pub fn part(&self, id: PartId) -> &PartDef {
        self.parts.get(id.0)
    }

    pub fn part_slot(&self, id: PartId) -> Option<Slot> {
        self.parts.try_get(id.0).map(|p| p.slot)
    }

    /// A part's modifiers at a rarity (the forge's canonical scaling).
    pub fn part_mods(&self, id: PartId, rarity: Rarity) -> impl Iterator<Item = Modifier> + '_ {
        let m = self.game.rarity.magnitude(rarity);
        self.part(id).mods.iter().map(move |x| x.scaled(m))
    }

    /// Parts of a slot available up to `phase`.
    pub fn parts_for_slot(&self, slot: Slot, phase: Phase) -> impl Iterator<Item = (PartId, &PartDef)> {
        self.parts.enumerate().filter(move |(_, p)| p.slot == slot && p.phase <= phase).map(|(i, p)| (PartId(i), p))
    }

    pub fn enemy(&self, id: EnemyId) -> &EnemyDef {
        self.enemies.get(id.0)
    }

    pub fn room(&self, id: RoomId) -> &RoomDef {
        self.rooms.get(id.0)
    }

    pub fn biome(&self, id: BiomeId) -> &BiomeDef {
        self.biomes.get(id.0)
    }

    pub fn boon(&self, id: BoonId) -> &BoonDef {
        self.boons.get(id.0)
    }

    pub fn god_id(&self, key: &str) -> Option<GodId> {
        self.gods.id(key).map(GodId)
    }

    /// Summary counts for the EA-scope report (§15).
    pub fn counts(&self) -> Vec<(&'static str, usize)> {
        vec![
            ("characters", self.characters.len()),
            ("playable characters", self.playable_characters().count()),
            ("chassis", self.chassis.len()),
            ("parts", self.parts.len()),
            ("boons", self.boons.iter().filter(|b| b.kind != BoonKind::Duo).count()),
            ("duo boons", self.boons.iter().filter(|b| b.kind == BoonKind::Duo).count()),
            ("recipes", self.recipes.len()),
            ("synergies", self.synergies.len()),
            ("enemies", self.enemies.len()),
            ("rooms", self.rooms.len()),
            ("biomes", self.biomes.len()),
            ("chaos tiers", self.chaos_tiers.len()),
            ("altar nodes", self.altar.len()),
            ("tree nodes", self.trees.len()),
            ("achievements", self.achievements.len()),
            ("barks", self.barks.len()),
        ]
    }
}
