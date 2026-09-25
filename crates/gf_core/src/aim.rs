//! One aim abstraction, three policies.
//!
//! Every player, every tick, runs the same pipeline:
//! **target selection → aim solution → trigger decision**. AUTO / ASSISTED / MANUAL differ only in
//! the [`AimModeParams`] they feed it (authored in `aim_modes.ron`). Per-weapon quirks — charge
//! weapons "charge-to-lock then release" in AUTO, beams sweep between targets — are driven by the
//! weapon's [`FireKind`], never by forking weapon code per mode.

use crate::ids::NetId;
use crate::math::{angle_between, lead_point, nlerp_dir, turn_toward};
use crate::weapon::FireKind;
use glam::Vec2;
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum AimMode {
    /// Auto-fire at valid targets; player drives movement, actives and ult. Accessibility floor.
    Auto,
    /// Manual fire with magnetism, lead prediction and soft lock. Recommended default.
    #[default]
    Assisted,
    /// Raw aim, zero magnetism, precision zones and Deadeye. Skill ceiling.
    Manual,
}

impl AimMode {
    pub const ALL: [AimMode; 3] = [AimMode::Auto, AimMode::Assisted, AimMode::Manual];

    pub const fn name(self) -> &'static str {
        match self {
            AimMode::Auto => "AUTO",
            AimMode::Assisted => "ASSISTED",
            AimMode::Manual => "MANUAL",
        }
    }

    pub const fn next(self) -> AimMode {
        match self {
            AimMode::Auto => AimMode::Assisted,
            AimMode::Assisted => AimMode::Manual,
            AimMode::Manual => AimMode::Auto,
        }
    }
}

/// AUTO target-priority bias. Co-op pings override every bias.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
pub enum TargetBias {
    /// Elites > low-HP > nearest.
    #[default]
    Balanced,
    Nearest,
    Strongest,
    LowestHp,
    /// Only engage pinged targets and elites while any exist (focus-fire discipline).
    Pinned,
}

impl TargetBias {
    pub const ALL: [TargetBias; 5] =
        [TargetBias::Balanced, TargetBias::Nearest, TargetBias::Strongest, TargetBias::LowestHp, TargetBias::Pinned];

    pub const fn next(self) -> TargetBias {
        match self {
            TargetBias::Balanced => TargetBias::Nearest,
            TargetBias::Nearest => TargetBias::Strongest,
            TargetBias::Strongest => TargetBias::LowestHp,
            TargetBias::LowestHp => TargetBias::Pinned,
            TargetBias::Pinned => TargetBias::Balanced,
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            TargetBias::Balanced => "Balanced",
            TargetBias::Nearest => "Nearest",
            TargetBias::Strongest => "Strongest",
            TargetBias::LowestHp => "Lowest HP",
            TargetBias::Pinned => "Pinned",
        }
    }
}

/// Per-mode tuning (the balance contract lives in data).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AimModeParams {
    pub mode: AimMode,
    /// Damage multiplier (AUTO pays a ~10% tax for perfect uptime).
    pub damage_mult: f32,
    /// Fires automatically whenever a valid target is in range.
    pub auto_fire: bool,
    /// Chooses targets (AUTO: whole range; ASSISTED: inside the magnetism cone).
    pub target_selection: bool,
    /// ASSISTED: half-angle of the magnetism cone in degrees.
    pub magnetism_cone_deg: f32,
    /// ASSISTED: 0..1 pull of the aim toward the target's lead point.
    pub magnetism_strength: f32,
    /// ASSISTED: within this many degrees the aim soft-locks exactly onto the lead point.
    pub lock_threshold_deg: f32,
    pub lead_prediction: bool,
    /// AUTO: acquire targets within weapon range × this.
    pub acquire_range_mult: f32,
    /// Score advantage a new target needs before AUTO switches off its current lock.
    pub lock_hysteresis: f32,
    /// Degrees/second a beam sweeps toward its next target in AUTO.
    pub beam_sweep_deg_per_s: f32,
    /// MANUAL: precision hits and Deadeye are enabled.
    pub precision_enabled: bool,
    pub precision_crit_bonus: f32,
    pub deadeye_per_hit: f32,
    pub deadeye_max: f32,
    /// Seconds without a precision hit before Deadeye resets.
    pub deadeye_timeout: f32,
}

impl AimModeParams {
    /// Shipped defaults (mirrors `assets/content/aim_modes.ron`).
    pub fn defaults(mode: AimMode) -> Self {
        let base = Self {
            mode,
            damage_mult: 1.0,
            auto_fire: false,
            target_selection: false,
            magnetism_cone_deg: 0.0,
            magnetism_strength: 0.0,
            lock_threshold_deg: 0.0,
            lead_prediction: false,
            acquire_range_mult: 1.0,
            lock_hysteresis: 25.0,
            beam_sweep_deg_per_s: 240.0,
            precision_enabled: false,
            precision_crit_bonus: 0.0,
            deadeye_per_hit: 0.0,
            deadeye_max: 0.0,
            deadeye_timeout: 2.5,
        };
        match mode {
            AimMode::Auto => Self {
                damage_mult: 0.9,
                auto_fire: true,
                target_selection: true,
                lead_prediction: true,
                acquire_range_mult: 0.95,
                ..base
            },
            AimMode::Assisted => Self {
                target_selection: true,
                magnetism_cone_deg: 16.0,
                magnetism_strength: 0.65,
                lock_threshold_deg: 5.0,
                lead_prediction: true,
                ..base
            },
            AimMode::Manual => Self {
                precision_enabled: true,
                precision_crit_bonus: 0.25,
                deadeye_per_hit: 0.02,
                deadeye_max: 0.20,
                ..base
            },
        }
    }
}

/// A potential target as seen by the aim system.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TargetCandidate {
    pub id: NetId,
    pub pos: Vec2,
    pub vel: Vec2,
    pub radius: f32,
    pub hp: f32,
    pub hp_frac: f32,
    pub elite: bool,
    pub boss: bool,
    pub pinged: bool,
}

/// Raw per-tick player intent relevant to aiming.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AimInput {
    pub origin: Vec2,
    /// Raw aim direction from mouse/stick (zero if none).
    pub raw_aim: Vec2,
    /// Movement direction, used as AUTO's idle facing.
    pub move_dir: Vec2,
    pub fire_held: bool,
    /// AUTO: the fire button becomes "force-target next" (edge-triggered).
    pub force_next: bool,
    pub bias: TargetBias,
}

/// What the aim system needs to know about the equipped weapon.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AimWeapon {
    pub range: f32,
    /// 0 for hitscan-like (beam/melee).
    pub projectile_speed: f32,
    pub fire: FireKind,
    /// Current charge progress 0..=1 for charge weapons (fed back from the weapon system).
    pub charge: f32,
}

/// Persistent per-player aim state.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct AimState {
    pub locked: Option<NetId>,
    pub cycle: u32,
    pub last_dir: Vec2,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct AimSolution {
    /// Unit aim direction.
    pub dir: Vec2,
    pub target: Option<NetId>,
    /// Desired trigger state this tick (the weapon system turns trigger edges into
    /// fire/charge/release).
    pub trigger: bool,
}

fn priority_score(c: &TargetCandidate, origin: Vec2, bias: TargetBias) -> f32 {
    let dist = c.pos.distance(origin);
    let ping = if c.pinged { 1000.0 } else { 0.0 };
    let elite = if c.elite || c.boss { 1.0 } else { 0.0 };
    let missing = (1.0 - c.hp_frac).clamp(0.0, 1.0);
    ping + match bias {
        TargetBias::Balanced | TargetBias::Pinned => elite * 120.0 + missing * 60.0 - dist * 4.0,
        TargetBias::Nearest => -dist * 10.0,
        TargetBias::Strongest => (c.hp / (c.hp + 150.0)) * 150.0 + elite * 40.0 - dist * 2.0,
        TargetBias::LowestHp => missing * 100.0 - c.hp.min(1000.0) * 0.05 - dist * 2.0,
    }
}

fn aim_point(origin: Vec2, c: &TargetCandidate, weapon: &AimWeapon, lead: bool) -> Vec2 {
    if lead && weapon.projectile_speed > 0.0 {
        lead_point(origin, c.pos, c.vel, weapon.projectile_speed).unwrap_or(c.pos)
    } else {
        c.pos
    }
}

/// Run the targeting pipeline for one player for one tick.
pub fn solve(
    params: &AimModeParams,
    input: &AimInput,
    weapon: &AimWeapon,
    candidates: &[TargetCandidate],
    state: &mut AimState,
    dt: f32,
) -> AimSolution {
    let raw = input.raw_aim.try_normalize();
    let fallback_dir =
        raw.or_else(|| state.last_dir.try_normalize()).or_else(|| input.move_dir.try_normalize()).unwrap_or(Vec2::X);

    let solution = match params.mode {
        AimMode::Manual => {
            state.locked = None;
            AimSolution { dir: fallback_dir, target: None, trigger: input.fire_held }
        }
        AimMode::Assisted => solve_assisted(params, input, weapon, candidates, state, fallback_dir),
        AimMode::Auto => solve_auto(params, input, weapon, candidates, state, fallback_dir, dt),
    };
    state.last_dir = solution.dir;
    solution
}

fn solve_assisted(
    params: &AimModeParams,
    input: &AimInput,
    weapon: &AimWeapon,
    candidates: &[TargetCandidate],
    state: &mut AimState,
    raw_dir: Vec2,
) -> AimSolution {
    let cone = params.magnetism_cone_deg.to_radians();
    let range = weapon.range;
    let best = candidates
        .iter()
        .filter(|c| c.pos.distance_squared(input.origin) <= range * range)
        .filter_map(|c| {
            let ang = angle_between(raw_dir, c.pos - input.origin);
            (ang <= cone).then_some((c, ang))
        })
        .min_by(|(a, aa), (b, ab)| {
            // Prefer the most on-crosshair target; distance breaks near-ties.
            let sa = aa.to_degrees() * 3.0 + a.pos.distance(input.origin) * 0.5 - if a.pinged { 50.0 } else { 0.0 };
            let sb = ab.to_degrees() * 3.0 + b.pos.distance(input.origin) * 0.5 - if b.pinged { 50.0 } else { 0.0 };
            sa.total_cmp(&sb)
        });

    match best {
        Some((c, ang)) if params.target_selection => {
            let point = aim_point(input.origin, c, weapon, params.lead_prediction);
            let lead_dir = (point - input.origin).try_normalize().unwrap_or(raw_dir);
            let dir = if ang <= params.lock_threshold_deg.to_radians() {
                lead_dir
            } else {
                let falloff = 1.0 - (ang / cone.max(1e-4));
                nlerp_dir(raw_dir, lead_dir, params.magnetism_strength * falloff)
            };
            state.locked = Some(c.id);
            AimSolution { dir, target: Some(c.id), trigger: input.fire_held }
        }
        _ => {
            state.locked = None;
            AimSolution { dir: raw_dir, target: None, trigger: input.fire_held }
        }
    }
}

fn solve_auto(
    params: &AimModeParams,
    input: &AimInput,
    weapon: &AimWeapon,
    candidates: &[TargetCandidate],
    state: &mut AimState,
    idle_dir: Vec2,
    dt: f32,
) -> AimSolution {
    let range = weapon.range * params.acquire_range_mult;
    let any_pinged = candidates.iter().any(|c| c.pinged);
    let mut valid: Vec<(&TargetCandidate, f32)> = candidates
        .iter()
        .filter(|c| c.pos.distance_squared(input.origin) <= range * range)
        .filter(|c| input.bias != TargetBias::Pinned || !any_pinged || c.pinged || c.elite || c.boss)
        .map(|c| (c, priority_score(c, input.origin, input.bias)))
        .collect();

    if valid.is_empty() {
        state.locked = None;
        return AimSolution { dir: idle_dir, target: None, trigger: false };
    }
    // Deterministic order: score desc, then id.
    valid.sort_by(|(a, sa), (b, sb)| sb.total_cmp(sa).then(a.id.cmp(&b.id)));

    let chosen = if input.force_next {
        state.cycle = state.cycle.wrapping_add(1);
        valid[(state.cycle as usize) % valid.len()].0
    } else {
        let best = valid[0];
        match state.locked.and_then(|id| valid.iter().find(|(c, _)| c.id == id)) {
            // A pinged target always wins over a non-pinged lock.
            Some((current, score))
                if (current.pinged || !best.0.pinged) && *score + params.lock_hysteresis >= best.1 =>
            {
                *current
            }
            _ => best.0,
        }
    };
    state.locked = Some(chosen.id);

    let point = aim_point(input.origin, chosen, weapon, params.lead_prediction);
    let target_dir = (point - input.origin).try_normalize().unwrap_or(idle_dir);
    let fire = weapon.fire;
    let dir = if fire == FireKind::Beam {
        // Beams sweep toward the next target instead of snapping.
        let from = state.last_dir.try_normalize().unwrap_or(target_dir);
        turn_toward(from, target_dir, params.beam_sweep_deg_per_s.to_radians() * dt)
    } else {
        target_dir
    };
    let trigger = match fire {
        // Charge-to-lock then release: hold while charging, drop the trigger once full.
        FireKind::Charge => weapon.charge < 1.0,
        _ => params.auto_fire,
    };
    AimSolution { dir, target: Some(chosen.id), trigger }
}

/// Manual-mode precision check: did the projectile's line pass through the target's core?
/// `travel_dir` is the projectile's unit direction at impact.
pub fn is_precision_hit(
    projectile_pos: Vec2,
    travel_dir: Vec2,
    target_pos: Vec2,
    target_radius: f32,
    zone_frac: f32,
) -> bool {
    let to_target = target_pos - projectile_pos;
    let impact_parameter = travel_dir.normalize_or_zero().perp_dot(to_target).abs();
    impact_parameter <= target_radius * zone_frac
}

/// Deadeye: consecutive precision hits build a damage multiplier (Manual only).
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Deadeye {
    pub stacks: u8,
    pub since_precision: f32,
}

impl Deadeye {
    pub fn on_precision_hit(&mut self, params: &AimModeParams) {
        if !params.precision_enabled || params.deadeye_per_hit <= 0.0 {
            return;
        }
        let cap = (params.deadeye_max / params.deadeye_per_hit).round() as u8;
        self.stacks = (self.stacks + 1).min(cap);
        self.since_precision = 0.0;
    }

    /// A shot that hit nothing costs a stack.
    pub fn on_miss(&mut self) {
        self.stacks = self.stacks.saturating_sub(1);
    }

    pub fn tick(&mut self, dt: f32, params: &AimModeParams) {
        self.since_precision += dt;
        if self.since_precision > params.deadeye_timeout {
            self.stacks = 0;
        }
    }

    pub fn mult(&self, params: &AimModeParams) -> f32 {
        if !params.precision_enabled {
            return 1.0;
        }
        1.0 + (self.stacks as f32 * params.deadeye_per_hit).min(params.deadeye_max)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cand(id: u32, x: f32, y: f32) -> TargetCandidate {
        TargetCandidate {
            id: NetId(id),
            pos: Vec2::new(x, y),
            vel: Vec2::ZERO,
            radius: 0.5,
            hp: 30.0,
            hp_frac: 1.0,
            elite: false,
            boss: false,
            pinged: false,
        }
    }

    fn input(raw: Vec2) -> AimInput {
        AimInput {
            origin: Vec2::ZERO,
            raw_aim: raw,
            move_dir: Vec2::ZERO,
            fire_held: false,
            force_next: false,
            bias: TargetBias::Balanced,
        }
    }

    fn gun() -> AimWeapon {
        AimWeapon { range: 12.0, projectile_speed: 20.0, fire: FireKind::Auto, charge: 0.0 }
    }

    #[test]
    fn auto_fires_only_with_targets() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut st = AimState::default();
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[], &mut st, 1.0 / 60.0);
        assert!(!s.trigger);
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[cand(1, 5.0, 0.0)], &mut st, 1.0 / 60.0);
        assert!(s.trigger);
        assert_eq!(s.target, Some(NetId(1)));
        assert!((s.dir - Vec2::X).length() < 1e-4);
    }

    #[test]
    fn auto_ignores_out_of_range() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut st = AimState::default();
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[cand(1, 50.0, 0.0)], &mut st, 1.0 / 60.0);
        assert!(!s.trigger);
        assert_eq!(s.target, None);
    }

    #[test]
    fn balanced_prefers_elites_over_nearer_swarm() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut st = AimState::default();
        let mut elite = cand(2, 9.0, 0.0);
        elite.elite = true;
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[cand(1, 2.0, 0.0), elite], &mut st, 0.016);
        assert_eq!(s.target, Some(NetId(2)));
    }

    #[test]
    fn biases_change_priority() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let near = cand(1, 2.0, 0.0);
        let mut hurt = cand(2, 8.0, 0.0);
        hurt.hp_frac = 0.1;
        hurt.hp = 3.0;
        let mut i = input(Vec2::ZERO);
        i.bias = TargetBias::Nearest;
        let s = solve(&p, &i, &gun(), &[near, hurt], &mut AimState::default(), 0.016);
        assert_eq!(s.target, Some(NetId(1)));
        i.bias = TargetBias::LowestHp;
        let s = solve(&p, &i, &gun(), &[near, hurt], &mut AimState::default(), 0.016);
        assert_eq!(s.target, Some(NetId(2)));
    }

    #[test]
    fn ping_overrides_every_bias() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut elite = cand(1, 3.0, 0.0);
        elite.elite = true;
        let mut pinged = cand(2, 10.0, 0.0);
        pinged.pinged = true;
        for bias in TargetBias::ALL {
            let mut i = input(Vec2::ZERO);
            i.bias = bias;
            let s = solve(&p, &i, &gun(), &[elite, pinged], &mut AimState::default(), 0.016);
            assert_eq!(s.target, Some(NetId(2)), "{bias:?}");
        }
    }

    #[test]
    fn lock_is_sticky_until_a_much_better_target() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut st = AimState::default();
        let a = cand(1, 5.0, 0.0);
        let b = cand(2, 5.5, 0.0);
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[a, b], &mut st, 0.016);
        assert_eq!(s.target, Some(NetId(1)));
        // b moves slightly closer: not enough to beat hysteresis.
        let b2 = cand(2, 4.5, 0.0);
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[a, b2], &mut st, 0.016);
        assert_eq!(s.target, Some(NetId(1)));
    }

    #[test]
    fn force_next_cycles() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut st = AimState::default();
        let cs = [cand(1, 3.0, 0.0), cand(2, 6.0, 0.0), cand(3, 9.0, 0.0)];
        let mut i = input(Vec2::ZERO);
        let first = solve(&p, &i, &gun(), &cs, &mut st, 0.016).target;
        i.force_next = true;
        let second = solve(&p, &i, &gun(), &cs, &mut st, 0.016).target;
        assert_ne!(first, second);
    }

    #[test]
    fn auto_leads_moving_targets() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut c = cand(1, 10.0, 0.0);
        c.vel = Vec2::new(0.0, 5.0);
        let s = solve(&p, &input(Vec2::ZERO), &gun(), &[c], &mut AimState::default(), 0.016);
        assert!(s.dir.y > 0.05, "aims ahead of the target");
    }

    #[test]
    fn auto_charge_weapons_release_when_full() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut w = gun();
        w.fire = FireKind::Charge;
        w.charge = 0.5;
        let s = solve(&p, &input(Vec2::ZERO), &w, &[cand(1, 5.0, 0.0)], &mut AimState::default(), 0.016);
        assert!(s.trigger, "keeps charging");
        w.charge = 1.0;
        let s = solve(&p, &input(Vec2::ZERO), &w, &[cand(1, 5.0, 0.0)], &mut AimState::default(), 0.016);
        assert!(!s.trigger, "drops trigger to release");
    }

    #[test]
    fn auto_beams_sweep() {
        let p = AimModeParams::defaults(AimMode::Auto);
        let mut w = gun();
        w.fire = FireKind::Beam;
        let mut st = AimState { last_dir: Vec2::X, ..Default::default() };
        let s = solve(&p, &input(Vec2::ZERO), &w, &[cand(1, 0.0, 5.0)], &mut st, 0.1);
        let turned = angle_between(Vec2::X, s.dir).to_degrees();
        assert!((turned - 24.0).abs() < 0.5, "240°/s × 0.1 s, got {turned}");
    }

    #[test]
    fn assisted_magnetizes_within_cone_only() {
        let p = AimModeParams::defaults(AimMode::Assisted);
        let mut i = input(Vec2::from_angle(8f32.to_radians()));
        i.fire_held = true;
        let s = solve(&p, &i, &gun(), &[cand(1, 6.0, 0.0)], &mut AimState::default(), 0.016);
        assert_eq!(s.target, Some(NetId(1)));
        assert!(angle_between(s.dir, Vec2::X) < 8f32.to_radians(), "pulled toward target");
        assert!(s.trigger);
        // Outside the cone: raw aim untouched.
        let i2 = input(Vec2::Y);
        let s2 = solve(&p, &i2, &gun(), &[cand(1, 6.0, 0.0)], &mut AimState::default(), 0.016);
        assert_eq!(s2.target, None);
        assert!((s2.dir - Vec2::Y).length() < 1e-5);
        assert!(!s2.trigger, "assisted never auto-fires");
    }

    #[test]
    fn assisted_soft_locks_inside_threshold() {
        let p = AimModeParams::defaults(AimMode::Assisted);
        let i = input(Vec2::from_angle(2f32.to_radians()));
        let s = solve(&p, &i, &gun(), &[cand(1, 6.0, 0.0)], &mut AimState::default(), 0.016);
        assert!((s.dir - Vec2::X).length() < 1e-4);
    }

    #[test]
    fn manual_is_raw() {
        let p = AimModeParams::defaults(AimMode::Manual);
        let mut i = input(Vec2::new(1.0, 0.2));
        i.fire_held = true;
        let s = solve(&p, &i, &gun(), &[cand(1, 6.0, 0.0)], &mut AimState::default(), 0.016);
        assert_eq!(s.target, None);
        assert!((s.dir - Vec2::new(1.0, 0.2).normalize()).length() < 1e-5);
        assert!(s.trigger);
    }

    #[test]
    fn precision_uses_impact_parameter() {
        // Straight through the middle.
        assert!(is_precision_hit(Vec2::new(-0.5, 0.0), Vec2::X, Vec2::ZERO, 0.5, 0.45));
        // Grazing hit.
        assert!(!is_precision_hit(Vec2::new(-0.5, 0.4), Vec2::X, Vec2::ZERO, 0.5, 0.45));
    }

    #[test]
    fn deadeye_builds_caps_and_resets() {
        let p = AimModeParams::defaults(AimMode::Manual);
        let mut d = Deadeye::default();
        for _ in 0..50 {
            d.on_precision_hit(&p);
        }
        assert!((d.mult(&p) - 1.2).abs() < 1e-5);
        d.on_miss();
        assert!((d.mult(&p) - 1.18).abs() < 1e-5);
        d.tick(3.0, &p);
        assert_eq!(d.stacks, 0);
        // Deadeye does nothing outside Manual.
        let auto = AimModeParams::defaults(AimMode::Auto);
        let mut d2 = Deadeye::default();
        d2.on_precision_hit(&auto);
        assert_eq!(d2.mult(&auto), 1.0);
    }

    #[test]
    fn balance_contract_in_defaults() {
        let auto = AimModeParams::defaults(AimMode::Auto);
        let manual = AimModeParams::defaults(AimMode::Manual);
        assert!((auto.damage_mult - 0.9).abs() < 1e-6, "~10% AUTO tax");
        assert_eq!(manual.damage_mult, 1.0);
        assert!((manual.deadeye_max - 0.2).abs() < 1e-6, "Deadeye caps at +20%");
    }
}
