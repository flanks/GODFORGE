//! The 100-hour audit (§11.5, acceptance criterion #7).
//!
//! Hours are manufactured by combinatorial depth, mastery and live content — so the audit derives
//! them from the *content itself*: currency sinks from the Altar and trees, Ember income from room
//! budgets, codex discovery odds from recipe ingredients and part-pool sizes, and the Chaos ladder
//! from the tier table. Model assumptions are explicit constants, printed with the report, and are
//! meant to be replaced by telemetry (time-to-first-clear, build diversity, % reaching 25/50/100 h).

use gf_content::ContentDb;
use gf_content::schema::*;
use gf_core::forge::Slot;
use std::fmt::Write as _;

/// Average run length in minutes (§4 target).
const RUN_MINUTES: f32 = 25.0;
/// Average fraction of a full run a (mostly losing) run reaches.
const AVG_DEPTH: f32 = 0.7;
/// Runs a new player needs before a first clear, independent of meta power (skill floor).
const MIN_RUNS_FIRST_CLEAR: f32 = 20.0;
/// Learning runs + expected attempts to clear with each additional character.
const RUNS_PER_ADDITIONAL_CLEAR: f32 = 6.5;
/// Share of Altar + tree cost a player buys before "substantially complete".
const META_COMPLETE_FRACTION: f32 = 0.8;
/// Parts a player sees per run (drops + caches + rerolls).
const PARTS_SEEN_PER_RUN: f32 = 11.0;
/// Deliberate pursuit after codex hints (deaths grant recipe hints).
const HINT_BOOST: f32 = 2.5;
/// Mastery levels gained per run with a character.
const MASTERY_LEVELS_PER_RUN: f32 = 1.1;
/// Mastery target and number of characters (§11.5).
const MASTERY_TARGET: f32 = 50.0;
const MASTERY_CHARACTERS: f32 = 4.0;
/// Weekly seeded runs a completionist plays in a year.
const WEEKLY_SEED_RUNS: f32 = 52.0;
/// Extra runs for achievements/skins/relationship logs beyond everything else (as a fraction).
const ACHIEVEMENT_TAIL: f32 = 0.15;

pub struct Milestone {
    pub name: &'static str,
    pub spec_hours: &'static str,
    /// Runs this milestone needs on its own.
    pub runs_alone: f32,
    /// Cumulative runs on a completionist path (milestones overlap).
    pub runs_cumulative: f32,
    pub basis: String,
}

pub struct Audit {
    pub ember_per_run: f32,
    pub build_space: f64,
    pub recipes: usize,
    pub milestones: Vec<Milestone>,
    pub total_hours: f32,
}

fn hours(runs: f32) -> f32 {
    runs * RUN_MINUTES / 60.0
}

fn avg_room_budget(db: &ContentDb) -> f32 {
    let combat: Vec<f32> = db
        .rooms
        .iter()
        .filter(|r| matches!(r.kind, RoomKind::Combat | RoomKind::Elite | RoomKind::Anvil))
        .map(|r| r.encounter.budget)
        .collect();
    let avg = if combat.is_empty() { 60.0 } else { combat.iter().sum::<f32>() / combat.len() as f32 };
    avg * db.game.run.budget_mult
}

fn ember_per_run(db: &ContentDb) -> f32 {
    let rt = &db.game.run;
    let rooms_full: f32 = db.biomes.iter().filter(|b| b.phase <= Phase::EA).map(|b| b.sequence.len() as f32).sum();
    let rooms = (rooms_full * AVG_DEPTH).max(1.0);
    let kills_per_room = avg_room_budget(db) * 0.92;
    let elites_per_room = kills_per_room * 0.05;
    let swarm_kills = rooms * (kills_per_room - elites_per_room);
    let per_kill = swarm_kills * rt.ember_per_kill[0] + rooms * elites_per_room * rt.ember_per_kill[1];
    let bosses = rooms_full * 0.12;
    per_kill + rooms * rt.ember_per_room + bosses * rt.ember_per_kill[2] + 0.3 * rt.ember_victory_bonus
}

/// Probability a specific recipe is assembled incidentally in one run.
fn recipe_probability(db: &ContentDb, rec: &RecipeDef) -> f32 {
    let pool = |slot: Slot| db.parts.iter().filter(|p| p.slot == slot && p.phase <= Phase::EA).count().max(1) as f32;
    let seen = |slot: Slot| 1.0 - (1.0 - 1.0 / pool(slot)).powf(PARTS_SEEN_PER_RUN * 0.3);
    let mut p = 1.0;
    for ing in &rec.ingredients {
        p *= match ing {
            IngredientKey::Chassis(_) => 1.0 / db.chassis.len().max(1) as f32 * 3.0,
            IngredientKey::Part(k) => db.parts.by_key(k).map_or(0.0, |part| seen(part.slot)),
            IngredientKey::Element(e) => {
                let cores = db.parts.iter().filter(|p| {
                    p.slot == Slot::Core
                        && p.mods.iter().any(|m| matches!(m, gf_core::modifier::Modifier::Element(x) if x == e))
                });
                let n = cores.count() as f32;
                1.0 - (1.0 - n / pool(Slot::Core)).powf(PARTS_SEEN_PER_RUN * 0.3)
            }
        };
    }
    (p * HINT_BOOST).min(1.0)
}

/// Runs until the expected discovered fraction reaches `target` (parallel coupon collecting).
fn runs_to_discover(ps: &[f32], target: f32) -> f32 {
    if ps.is_empty() {
        return 0.0;
    }
    let need = target * ps.len() as f32;
    let expected = |t: f32| ps.iter().map(|p| 1.0 - (1.0 - p).powf(t)).sum::<f32>();
    let (mut lo, mut hi) = (0.0f32, 1.0f32);
    while expected(hi) < need && hi < 1e6 {
        hi *= 2.0;
    }
    for _ in 0..60 {
        let mid = 0.5 * (lo + hi);
        if expected(mid) < need { lo = mid } else { hi = mid }
    }
    hi
}

pub fn run(db: &ContentDb) -> Audit {
    let epr = ember_per_run(db);
    let n_chars = db.characters.iter().filter(|c| c.phase <= Phase::EA).count().max(1) as f32;
    let count = |slot: Slot| db.parts.iter().filter(|p| p.slot == slot).count().max(1) as f64;
    // Distinct equipped builds × 4 rarities per slot (sigil fixed per run).
    let build_space = db.chassis.len().max(1) as f64
        * count(Slot::Core)
        * count(Slot::Mechanism)
        * count(Slot::Relic)
        * count(Slot::Sigil)
        * 4f64.powi(3);

    let starter_cost: u32 = db
        .altar
        .iter()
        .filter(|n| n.tier <= 2 && matches!(n.tree, AltarTree::Flesh | AltarTree::Fate))
        .map(|n| n.cost)
        .sum();
    let runs_first = MIN_RUNS_FIRST_CLEAR.max(starter_cost as f32 / epr);
    let runs_all_chars = runs_first + (n_chars - 1.0) * RUNS_PER_ADDITIONAL_CLEAR;
    let meta_cost: u32 = db.altar.iter().map(|n| n.cost).sum::<u32>() + db.trees.iter().map(|n| n.cost).sum::<u32>();
    let runs_meta = META_COMPLETE_FRACTION * meta_cost as f32 / epr;
    let probs: Vec<f32> = db.recipes.iter().map(|r| recipe_probability(db, r)).collect();
    let runs_codex = runs_to_discover(&probs, 0.8);
    let runs_mastery = MASTERY_TARGET * MASTERY_CHARACTERS / MASTERY_LEVELS_PER_RUN;
    let tiers = db.chaos_tiers.len() as f32;
    let runs_chaos: f32 =
        (1..=db.chaos_tiers.len()).map(|t| 1.0 / (0.55 - 0.018 * t as f32).max(0.15)).sum::<f32>() + runs_all_chars;

    let mut milestones: Vec<Milestone> = Vec::new();
    let mut cumulative = 0.0f32;
    fn push(ms: &mut Vec<Milestone>, cum: &mut f32, name: &'static str, spec: &'static str, runs: f32, basis: String) {
        *cum = cum.max(runs);
        ms.push(Milestone { name, spec_hours: spec, runs_alone: runs, runs_cumulative: *cum, basis });
    }
    push(
        &mut milestones,
        &mut cumulative,
        "Onboarding → first full clear",
        "8–12",
        runs_first,
        format!("max({MIN_RUNS_FIRST_CLEAR} skill-floor runs, {starter_cost} Ember of tier-1/2 Flesh+Fate nodes)"),
    );
    push(
        &mut milestones,
        &mut cumulative,
        "Full clears on all EA characters",
        "40–55",
        runs_all_chars,
        format!("+{RUNS_PER_ADDITIONAL_CLEAR} runs × {} more characters", n_chars - 1.0),
    );
    push(
        &mut milestones,
        &mut cumulative,
        "Forge Altar + character trees ≥ 80%",
        "55–75",
        runs_meta,
        format!("{:.0}% of {meta_cost} Ember at {epr:.0} Ember/run", META_COMPLETE_FRACTION * 100.0),
    );
    push(
        &mut milestones,
        &mut cumulative,
        "Codex: named combos ≥ 80%",
        "70–95",
        runs_codex,
        format!("{} recipes, parallel discovery, {PARTS_SEEN_PER_RUN} parts seen/run, hint ×{HINT_BOOST}", probs.len()),
    );
    push(
        &mut milestones,
        &mut cumulative,
        "Mastery 50 on 4+ characters",
        "80–100",
        runs_mastery,
        format!("{MASTERY_TARGET} levels × {MASTERY_CHARACTERS} chars at {MASTERY_LEVELS_PER_RUN} levels/run"),
    );
    let chaos_runs = runs_chaos.max(cumulative) + WEEKLY_SEED_RUNS;
    push(
        &mut milestones,
        &mut cumulative,
        "Chaos Tier ladder + weekly seed climb",
        "100–150",
        chaos_runs,
        format!("{tiers} tiers at falling win rates after the roster clear, + {WEEKLY_SEED_RUNS} weekly seeds"),
    );
    let tail = cumulative * (1.0 + ACHIEVEMENT_TAIL);
    push(
        &mut milestones,
        &mut cumulative,
        "All achievements, logs, skins, leaderboards",
        "150–200+",
        tail,
        format!("{} achievements; +{:.0}% tail over the path above", db.achievements.len(), ACHIEVEMENT_TAIL * 100.0),
    );
    let total_hours = hours(cumulative);
    Audit { ember_per_run: epr, build_space, recipes: db.recipes.len(), milestones, total_hours }
}

pub fn render(a: &Audit) -> String {
    let mut s = String::new();
    let _ = writeln!(s, "# 100-Hour Audit\n");
    let _ = writeln!(
        s,
        "> Generated by `cargo run -p gf_tools -- audit --write` from the current content. \
         Assumptions are constants in `tools/gf_tools/src/audit.rs`; replace them with telemetry as it arrives.\n"
    );
    let _ = writeln!(s, "- Average run: **{RUN_MINUTES} min**; Ember income ≈ **{:.0} / run**", a.ember_per_run);
    let _ = writeln!(s, "- Distinct weapon builds (chassis × slots × rarities): **{:.2e}**", a.build_space);
    let _ = writeln!(s, "- Named combos in the codex: **{}**\n", a.recipes);
    let _ = writeln!(s, "| Journey segment | Spec (h) | Runs alone | Cumulative runs | Cumulative hours | Basis |");
    let _ = writeln!(s, "|---|---|---|---|---|---|");
    for m in &a.milestones {
        let _ = writeln!(
            s,
            "| {} | {} | {:.0} | {:.0} | **{:.0}** | {} |",
            m.name,
            m.spec_hours,
            m.runs_alone,
            m.runs_cumulative,
            hours(m.runs_cumulative),
            m.basis
        );
    }
    let verdict = if a.total_hours >= 100.0 { "PASS" } else { "FAIL" };
    let _ = writeln!(s, "\n**Completionist path: {:.0} h → {verdict}** (requirement: ≥ 100 h, §11.5).", a.total_hours);
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn discovery_model_is_sane() {
        let easy = vec![0.5; 10];
        let hard = vec![0.01; 10];
        assert!(runs_to_discover(&easy, 0.8) < runs_to_discover(&hard, 0.8));
        assert_eq!(runs_to_discover(&[], 0.8), 0.0);
        let t = runs_to_discover(&[0.5], 0.5);
        assert!((t - 1.0).abs() < 0.01, "{t}");
    }
}
