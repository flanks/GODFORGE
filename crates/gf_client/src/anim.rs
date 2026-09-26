//! Skeletal animation over the authoritative snapshot (docs/art/GF_HERO_SKELETON.md §8).
//!
//! * [`Animator`] sits on each glTF instance's `AnimationPlayer` and plays that asset's shared graph
//!   (`models::ClipLib`) in two layers:
//!   - **base**: one full-body clip at a time (locomotion, idles, stances, full one-shots), cross-faded
//!     by weight inside the graph's base blend node;
//!   - **upper**: one-shots (and a held loop) on `spine_01` and its children, the lower body masked out
//!     (the clip contract's "mask spine_01"). Each is blended against the base with the weight
//!     `a / (1 − a)`, so a fade `a` of 1 means the upper body is the clip's, 0 the base's.
//! * [`HeroAnim`] is the hero state machine: locomotion from the ground velocity relative to the
//!   facing (run / strafe / backpedal / walk at `speed / design_speed`), idles by combat state, the
//!   dash, the kit clips on `GameEvent::Ability`, strikes and shots, hits, the ping, death →
//!   downed → revive / reforge, the forge hammer while the forge is open, and victory.
//!
//! Everything here reads replicated state and cosmetic events; nothing feeds back into the sim.
//! `--anim-log` logs every clip change (the QA clip-state log).

use crate::input::InputState;
use crate::models::{HeroGear, Model, ModelParts};
use crate::net::{Link, Prediction};
use crate::palette::yaw;
use crate::scene::Visual;
use crate::{ClientConfig, ClientSet};
use gf_core::aim::AimMode;
use gf_core::revive::LifeState;
use gf_core::weapon::FireKind;
use gf_engine::bevy::animation::{AnimationTargetId, RepeatAnimation, graph::AnimationNodeIndex};
use gf_engine::prelude::*;
use gf_net::quant::u16_to_dir;
use gf_net::{EntityKind, GameEvent, PlayerFlags, PlayerView, RunPhase};
use std::collections::VecDeque;
use std::f32::consts::{PI, TAU};
use std::sync::Arc;

/// Upper-layer fades (s).
const UPPER_FADE_IN: f32 = 0.06;
const UPPER_FADE_OUT: f32 = 0.12;
/// Base cross-fades (s).
const FADE_LOCO: f32 = 0.18;
const FADE_ONESHOT: f32 = 0.1;
/// Below this ground speed (m/s) a hero stands.
const STAND_SPEED: f32 = 0.6;
/// Shortest time (s) a gait plays before another replaces it.
const GAIT_DWELL: f32 = 0.14;
/// "In combat" lasts this long after a shot, a strike or a hit (s).
const COMBAT_LINGER: f32 = 2.5;
/// An enemy this close (m) keeps a hero in the combat stance.
const COMBAT_RANGE: f32 = 13.0;
/// Out of combat this long (s): the signature idle.
const SIGNATURE_AFTER: f32 = 6.0;

/// The mask group lower-body targets of an instance go in: every animation target that is neither
/// `spine_01` nor below it.
pub fn lower_body_targets(
    root: Entity,
    children: &Query<&Children>,
    targets: &Query<(&AnimationTargetId, Option<&ChildOf>)>,
    names: &Query<&Name>,
) -> Vec<AnimationTargetId> {
    let mut out = Vec::new();
    for e in children.iter_descendants(root) {
        let Ok((id, _)) = targets.get(e) else { continue };
        let mut cur = e;
        let mut upper = false;
        loop {
            if names.get(cur).is_ok_and(|n| n.as_str() == "spine_01") {
                upper = true;
                break;
            }
            match targets.get(cur) {
                Ok((_, Some(parent))) => cur = parent.parent(),
                _ => break,
            }
        }
        if !upper {
            out.push(*id);
        }
    }
    out
}

// ───────────────────────────── animator ─────────────────────────────

#[derive(Debug)]
struct Track {
    node: AnimationNodeIndex,
    weight: f32,
    main: bool,
    /// Weight change per second.
    rate: f32,
}

#[derive(Debug)]
struct Upper {
    name: String,
    node: AnimationNodeIndex,
    /// Fade 0..1 (1 = the upper body is this clip's).
    alpha: f32,
    looping: bool,
    stopping: bool,
    duration: f32,
    speed: f32,
}

/// Plays one asset's clips on its `AnimationPlayer`: a cross-faded base layer and upper-body
/// one-shots. Lives on the player entity.
#[derive(Component)]
pub struct Animator {
    model: Arc<Model>,
    base: Vec<Track>,
    upper: Vec<Upper>,
    base_name: String,
    upper_loop: Option<String>,
}

impl Animator {
    pub fn new(model: Arc<Model>) -> Self {
        Animator { model, base: Vec::new(), upper: Vec::new(), base_name: String::new(), upper_loop: None }
    }

    pub fn has(&self, name: &str) -> bool {
        self.model.clip(name).is_some()
    }

    /// The base clip playing (short name).
    pub fn base_name(&self) -> &str {
        &self.base_name
    }

    /// Seconds into the main base clip.
    pub fn base_time(&self, player: &AnimationPlayer) -> f32 {
        let Some(t) = self.base.iter().find(|t| t.main) else { return 0.0 };
        player.animation(t.node).map_or(0.0, |a| a.seek_time())
    }

    /// Play `name` as the full-body clip, cross-fading over `fade` s. A different clip, or
    /// `restart`, starts it from `seek` s; the same clip only takes the new speed.
    pub fn set_base(&mut self, player: &mut AnimationPlayer, name: &str, speed: f32, fade: f32, restart: bool) -> bool {
        self.set_base_at(player, name, speed, fade, restart, 0.0)
    }

    pub fn set_base_at(
        &mut self,
        player: &mut AnimationPlayer,
        name: &str,
        speed: f32,
        fade: f32,
        restart: bool,
        seek: f32,
    ) -> bool {
        let Some(clip) = self.model.clip(name) else { return false };
        if clip.meta.upper {
            return false;
        }
        let (node, looping) = (clip.node, clip.meta.looping);
        if self.base_name == name && !restart {
            if let Some(a) = player.animation_mut(node) {
                a.set_speed(speed);
            }
            return true;
        }
        let rate = 1.0 / fade.max(1.0e-3);
        for t in &mut self.base {
            t.main = false;
            t.rate = rate;
        }
        let fresh = match self.base.iter_mut().find(|t| t.node == node) {
            Some(t) => {
                t.main = true;
                restart || !player.is_playing_animation(node)
            }
            None => {
                self.base.push(Track { node, weight: 0.0, main: true, rate });
                true
            }
        };
        let a = if fresh { player.start(node) } else { player.play(node) };
        a.set_speed(speed);
        if looping {
            a.repeat();
        } else {
            a.set_repeat(RepeatAnimation::Never);
        }
        if fresh && seek > 0.0 {
            a.set_seek_time(seek);
        }
        if fade <= 0.0 {
            for t in &mut self.base {
                t.weight = if t.main { 1.0 } else { 0.0 };
            }
        }
        self.base_name = name.to_string();
        true
    }

    /// Play an upper-layer one-shot over the base (restarting it if it already plays).
    pub fn play_upper(&mut self, player: &mut AnimationPlayer, name: &str, speed: f32) -> bool {
        let Some(clip) = self.model.clip(name) else { return false };
        if !clip.meta.upper {
            return false;
        }
        let (node, duration, looping) = (clip.node, clip.duration, clip.meta.looping);
        match self.upper.iter_mut().find(|u| u.node == node) {
            Some(u) => {
                u.stopping = false;
                u.speed = speed;
            }
            None => self.upper.push(Upper {
                name: name.to_string(),
                node,
                alpha: 0.0,
                looping,
                stopping: false,
                duration,
                speed,
            }),
        }
        let a = player.start(node);
        a.set_speed(speed);
        if looping {
            a.repeat();
        } else {
            a.set_repeat(RepeatAnimation::Never);
        }
        true
    }

    /// Seconds an upper clip has played (None when it does not play).
    pub fn upper_time(&self, player: &AnimationPlayer, name: &str) -> Option<f32> {
        let u = self.upper.iter().find(|u| u.name == name && !u.stopping)?;
        player.animation(u.node).map(|a| a.seek_time())
    }

    /// Hold an upper-layer loop (a charge) until `None`.
    pub fn set_upper_loop(&mut self, player: &mut AnimationPlayer, name: Option<&str>) {
        if self.upper_loop.as_deref() == name {
            return;
        }
        if let Some(old) = self.upper_loop.take() {
            for u in self.upper.iter_mut().filter(|u| u.name == old) {
                u.stopping = true;
            }
        }
        if let Some(n) = name
            && self.play_upper(player, n, 1.0)
        {
            self.upper_loop = Some(n.to_string());
        }
    }

    /// Fade every upper clip out (a full-body clip takes over).
    pub fn clear_upper(&mut self) {
        for u in &mut self.upper {
            u.stopping = true;
        }
        self.upper_loop = None;
    }

    /// Is an upper clip (other than a held loop) showing?
    pub fn upper_busy(&self) -> bool {
        self.upper.iter().any(|u| !u.stopping && !u.looping)
    }

    /// Advance the fades and push the weights to the player.
    pub fn tick(&mut self, player: &mut AnimationPlayer, dt: f32) {
        for t in &mut self.base {
            t.weight = if t.main { (t.weight + dt * t.rate).min(1.0) } else { t.weight - dt * t.rate };
        }
        self.base.retain(|t| {
            let keep = t.main || t.weight > 0.0;
            if !keep {
                player.stop(t.node);
            }
            keep
        });
        let only = self.base.len() == 1;
        for t in &mut self.base {
            if only {
                t.weight = 1.0;
            }
            if let Some(a) = player.animation_mut(t.node) {
                a.set_weight(t.weight.max(1.0e-4));
            }
        }
        for u in &mut self.upper {
            let Some(a) = player.animation(u.node) else {
                u.alpha = 0.0;
                u.stopping = true;
                continue;
            };
            if u.stopping {
                u.alpha -= dt / UPPER_FADE_OUT;
            } else {
                u.alpha = (u.alpha + dt / UPPER_FADE_IN).min(1.0);
                if !u.looping {
                    let left = (u.duration - a.seek_time()) / u.speed.max(0.05);
                    u.alpha = u.alpha.min((left / UPPER_FADE_OUT).max(0.0));
                    if a.is_finished() {
                        u.alpha = 0.0;
                    }
                }
            }
        }
        self.upper.retain(|u| {
            let keep = u.alpha > 0.0;
            if !keep {
                player.stop(u.node);
            }
            keep
        });
        for u in &self.upper {
            let a = u.alpha.clamp(0.0, 0.999);
            if let Some(active) = player.animation_mut(u.node) {
                active.set_weight((a / (1.0 - a)).max(1.0e-4));
            }
        }
    }

    /// Which hands show a gauntlet pair's open variant, from the clip in charge of the arms.
    pub fn hands_open(&self, player: &AnimationPlayer) -> Option<[bool; 2]> {
        let (name, node) = match self.upper.iter().rev().find(|u| !u.stopping && u.alpha > 0.5) {
            Some(u) => (u.name.as_str(), u.node),
            None => {
                let t = self.base.iter().find(|t| t.main)?;
                (self.base_name.as_str(), t.node)
            }
        };
        let hands = self.model.clip(name)?.meta.hands.as_ref()?;
        let t = player.animation(node)?.seek_time();
        Some([hands[0].open_at(t), hands[1].open_at(t)])
    }
}

/// Fades advance once per frame for every animator (heroes and anything else using one).
fn tick_animators(time: Res<Time>, mut q: Query<(&mut Animator, &mut AnimationPlayer)>) {
    let dt = time.delta_secs();
    for (mut an, mut player) in &mut q {
        an.tick(&mut player, dt);
    }
}

// ───────────────────────────── heroes ─────────────────────────────

/// A full-body clip that overrides locomotion for a while.
#[derive(Clone, Debug)]
struct OneShot {
    clip: &'static str,
    /// Play for this long (s); a clip longer than that is cut, a loop repeats.
    length: f32,
    /// Start this far into the clip (s).
    seek: f32,
    /// Hold the last frame instead of ending (death, victory).
    hold: bool,
    /// No strikes / shots layer over it (kit moves, the dash).
    exclusive: bool,
    /// Face this sim angle while it plays.
    face: Option<f32>,
    /// Face the ground velocity while it plays (a charge goes where the sim sends it).
    face_travel: bool,
    speed: f32,
    /// Moving after this long (s) hands the body back to locomotion (the sim never roots a cast,
    /// so a long clip would otherwise slide).
    cancel_after: Option<f32>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Life {
    Alive,
    Downed,
    Reforging,
}

impl Life {
    fn of(l: &LifeState) -> Life {
        match l {
            LifeState::Alive => Life::Alive,
            LifeState::Downed { .. } => Life::Downed,
            LifeState::Reforging { .. } => Life::Reforging,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Gait {
    Walk,
    Run,
    StrafeLeft,
    StrafeRight,
    Backpedal,
}

impl Gait {
    fn clip(self) -> &'static str {
        match self {
            Gait::Walk => "walk",
            Gait::Run => "run",
            Gait::StrafeLeft => "strafe_left",
            Gait::StrafeRight => "strafe_right",
            Gait::Backpedal => "backpedal",
        }
    }

    /// The gait for moving `rel` radians off the facing (positive = to the hero's left), with
    /// 10° of hysteresis around the current one.
    fn pick(rel: f32, current: Option<Gait>) -> Gait {
        let a = rel.abs().to_degrees();
        let side = if rel > 0.0 { Gait::StrafeLeft } else { Gait::StrafeRight };
        let slack = 10.0;
        match current {
            Some(Gait::Run | Gait::Walk) if a < 45.0 + slack => return Gait::Run,
            Some(Gait::Backpedal) if a > 135.0 - slack => return Gait::Backpedal,
            Some(g @ (Gait::StrafeLeft | Gait::StrafeRight))
                if g == side && (45.0 - slack..135.0 + slack).contains(&a) =>
            {
                return g;
            }
            _ => {}
        }
        if a <= 45.0 {
            Gait::Run
        } else if a < 135.0 {
            side
        } else {
            Gait::Backpedal
        }
    }
}

/// What a hero's kit abilities play (`GameEvent::Ability { which }`: 0 = active 1, 1 = active 2,
/// 2 = ultimate). Heroes without a table only use the shared clips.
#[derive(Clone, Copy, Debug)]
enum KitMove {
    None,
    /// A full-body clip on cast; `from` = the event the sim's motion starts on (the clip starts
    /// there, so the anticipation does not lag the leap); moving after `cancel` s ends it.
    Strike {
        clip: &'static str,
        from: Option<&'static str>,
        cancel: f32,
    },
    /// A charge: the loop for `time` s along the aim, then the brake.
    Rush {
        run: &'static str,
        end: &'static str,
        time: f32,
    },
}

#[derive(Clone, Copy, Debug)]
struct KitClips {
    moves: [KitMove; 3],
    /// `PlayerFlags::STANCE`: enter, loop (replaces idle and locomotion), exit, per-shot clip.
    stance: Option<[&'static str; 4]>,
    /// `PlayerFlags::AVATAR` (the ultimate's buff): start, the loop that replaces `idle_combat`.
    avatar: Option<[&'static str; 2]>,
    /// A pound layered every `every` s during the avatar, its event `at` s into the clip lining up
    /// with the sim's pulse (first pulse half an interval after the cast).
    pound: Option<(&'static str, f32)>,
}

fn kit_clips(key: &str) -> KitClips {
    match key {
        "brax" => KitClips {
            // Cinder Uppercut: Nova on `launch` (f10), the slam's geysers on `slam` (f25).
            moves: [
                KitMove::Strike { clip: "uppercut", from: None, cancel: 0.95 },
                KitMove::Rush { run: "furnace_rush", end: "furnace_rush_end", time: 0.4 },
                KitMove::None,
            ],
            stance: None,
            avatar: Some(["meltdown_start", "meltdown"]),
            pound: None,
        },
        "valdris" => KitClips {
            // Bulwark Slam: the 0.45 s leap runs `launch` (f8) → `land` (f21).
            moves: [
                KitMove::Strike { clip: "bulwark_slam", from: Some("launch"), cancel: 0.6 },
                KitMove::None,
                KitMove::None,
            ],
            stance: Some(["siege_stance_enter", "siege_stance", "siege_stance_exit", "siege_fire"]),
            avatar: Some(["mountainfall_start", "mountainfall"]),
            pound: Some(("mountainfall_pound", 1.1)),
        },
        _ => KitClips { moves: [KitMove::None; 3], stance: None, avatar: None, pound: None },
    }
}

/// The per-hero state machine. On the hero model entity, beside its `HeroGear`.
#[derive(Component)]
pub struct HeroAnim {
    pub slot: u8,
    key: String,
    kit: KitClips,
    /// Rendered facing (sim angle), eased toward the aim.
    facing: Option<f32>,
    queue: VecDeque<OneShot>,
    /// The playing one-shot and when it started (s).
    current: Option<(OneShot, f32)>,
    life: Life,
    gait: Option<Gait>,
    gait_since: f32,
    last_combat: f32,
    idle_since: f32,
    strikes: u32,
    last_strike: f32,
    last_hit: f32,
    last_tick: u32,
    dashing: bool,
    stance: bool,
    avatar: bool,
    next_pound: f32,
    victory: bool,
    /// Last logged base clip (the `--anim-log` clip-state log).
    logged: String,
}

impl HeroAnim {
    pub fn new(slot: u8, key: &str) -> Self {
        HeroAnim {
            slot,
            key: key.to_string(),
            kit: kit_clips(key),
            facing: None,
            queue: VecDeque::new(),
            current: None,
            life: Life::Alive,
            gait: None,
            gait_since: 0.0,
            last_combat: -100.0,
            idle_since: 0.0,
            strikes: 0,
            last_strike: -100.0,
            last_hit: -100.0,
            last_tick: 0,
            dashing: false,
            stance: false,
            avatar: false,
            next_pound: f32::INFINITY,
            victory: false,
            logged: String::new(),
        }
    }

    fn push(&mut self, an: &Animator, shot: OneShot) {
        if an.has(shot.clip) {
            self.queue.push_back(shot);
        }
    }

    /// Replace whatever plays and is queued with `shot`.
    fn interrupt(&mut self, an: &Animator, shot: OneShot) {
        if an.has(shot.clip) {
            self.queue.clear();
            self.queue.push_back(shot);
            self.current = None;
        }
    }

    fn exclusive(&self) -> bool {
        self.current.as_ref().is_some_and(|(s, _)| s.exclusive) || self.dashing
    }

    /// The clip-state log's line for an upper-layer clip.
    fn log_event(&self, on: bool, clip: &str) {
        if on {
            info!("anim P{} {}: + {clip} (upper)", self.slot + 1, self.key);
        }
    }
}

fn clip_len(an: &Animator, clip: &str) -> f32 {
    an.model.clip(clip).map_or(0.5, |c| c.duration)
}

fn shot(an: &Animator, clip: &'static str) -> OneShot {
    OneShot {
        clip,
        length: clip_len(an, clip),
        seek: 0.0,
        hold: false,
        exclusive: false,
        face: None,
        face_travel: false,
        speed: 1.0,
        cancel_after: Some(0.25),
    }
}

fn wrap(a: f32) -> f32 {
    (a + PI).rem_euclid(TAU) - PI
}

/// `--anim-log`: log every clip change.
#[derive(Resource)]
pub struct AnimLog(pub bool);

/// `--anim-gallery`: QA. The local hero ignores the sim and plays every clip of its model in name
/// order, [`GALLERY_PERIOD`] s each, facing the camera three-quarters (pose review from the game
/// camera, next to the art review sheets). Upper-layer clips play over `idle_combat`. `--anim-gallery N`
/// starts at the N-th clip.
#[derive(Resource)]
pub struct AnimGallery(pub Option<usize>);

/// Seconds each clip plays in the gallery.
pub const GALLERY_PERIOD: f32 = 2.5;

/// The gallery's layering checks after the clip list (Brax strikes instead of shooting).
const GALLERY_LAYERED: [(&str, &str); 4] =
    [("run", "fire_light"), ("strafe_left", "fire_light"), ("backpedal", "hit_light"), ("run", "ping")];

fn gallery_step(
    ha: &mut HeroAnim,
    an: &mut Animator,
    ap: &mut AnimationPlayer,
    tf: &mut Transform,
    now: f32,
    from: usize,
) {
    let Some(lib) = an.model.anim.as_ref() else { return };
    let mut names: Vec<String> = lib.clips.keys().cloned().collect();
    names.sort();
    // Then the layering: upper-body clips over locomotion (`base+upper`).
    for (base, upper) in GALLERY_LAYERED {
        let upper = if ha.key == "brax" { upper.replace("fire_light", "jab_r") } else { upper.to_string() };
        if lib.clips.contains_key(base) && lib.clips.contains_key(&upper) {
            names.push(format!("{base}+{upper}"));
        }
    }
    let entry = names[(from + (now / GALLERY_PERIOD) as usize) % names.len()].clone();
    if ha.logged != entry {
        let (base, name) = match entry.split_once('+') {
            Some((b, u)) => (Some(b.to_string()), u.to_string()),
            None => (None, entry.clone()),
        };
        let Some(clip) = lib.clips.get(&name) else { return };
        let (upper, node, looping) = (clip.meta.upper, clip.node, clip.meta.looping);
        // A one-shot holds its key pose: its first event (the hit, the launch), else 40 % in.
        let key = clip.meta.events.iter().map(|(_, t)| *t).reduce(f32::min).unwrap_or(clip.duration * 0.4);
        info!(
            "anim gallery P{} {}: {entry}{}{} at {now:.1}s",
            ha.slot + 1,
            ha.key,
            if upper { " (upper)" } else { "" },
            if looping { String::new() } else { format!(", held at {key:.2}s") },
        );
        an.clear_upper();
        if upper {
            an.set_base(ap, base.as_deref().unwrap_or("idle_combat"), 1.0, 0.1, false);
            an.play_upper(ap, &name, 1.0);
        } else {
            an.set_base(ap, &name, 1.0, 0.1, true);
        }
        if !looping && let Some(a) = ap.animation_mut(node) {
            a.set_seek_time(key).pause();
        }
        ha.logged = entry;
    }
    // Facing down-right, toward the lens.
    tf.rotation = yaw(-PI / 3.0) * Quat::from_rotation_y(PI);
}

#[allow(clippy::too_many_arguments)]
fn drive_heroes(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    pred: Res<Prediction>,
    input: Res<InputState>,
    log: Res<AnimLog>,
    gallery: Res<AnimGallery>,
    visuals: Query<&Visual>,
    mut heroes: Query<(&mut HeroAnim, &ModelParts, &mut HeroGear, &mut Transform)>,
    mut animators: Query<(&mut Animator, &mut AnimationPlayer)>,
) {
    let Some(world) = link.latest.as_deref() else { return };
    let now = time.elapsed_secs();
    let dt = time.delta_secs();
    for (mut ha, parts, mut gear, mut tf) in &mut heroes {
        let Some(p) = world.players.iter().find(|p| p.slot == ha.slot) else { continue };
        let Some((mut an, mut ap)) = parts.player.and_then(|e| animators.get_mut(e).ok()) else { continue };
        let (ha, an, ap) = (&mut *ha, &mut *an, &mut *ap);
        let is_me = link.slot == Some(p.slot);
        if let Some(from) = gallery.0.filter(|_| is_me) {
            gallery_step(ha, an, ap, &mut tf, now, from);
            continue;
        }
        let mover = match (is_me, pred.state) {
            (true, Some(s)) => s,
            _ => p.mover,
        };
        let aim_dir = if is_me && input.aim_mode == AimMode::Manual { input.aim_dir } else { u16_to_dir(p.aim) };
        let aim = aim_dir.y.atan2(aim_dir.x);
        let speed = mover.vel.length();
        let heading = mover.vel.y.atan2(mover.vel.x);
        let chassis = cfg.content.chassis.try_get(p.weapon.chassis.0);
        let fire = chassis.map_or(FireKind::Auto, |c| c.stats.fire);
        let fire_rate = chassis.map_or(2.0, |c| c.stats.fire_rate);

        // ── life ──
        let life = Life::of(&p.life);
        if life != ha.life {
            let next = match (ha.life, life) {
                // `death` plays through, then the wraith drift (`downed@loop`) takes over.
                (_, Life::Downed) => Some(OneShot { exclusive: true, cancel_after: None, ..shot(an, "death") }),
                (Life::Downed, Life::Alive) => Some(OneShot { exclusive: true, ..shot(an, "revive") }),
                (Life::Reforging, Life::Alive) => {
                    Some(OneShot { exclusive: true, cancel_after: Some(0.6), ..shot(an, "reforge_in") })
                }
                _ => None,
            };
            if let Some(s) = next {
                an.clear_upper();
                ha.interrupt(an, s);
            }
            ha.life = life;
        }
        let ghost = life == Life::Downed;
        if gear.ghost != ghost {
            gear.ghost = ghost;
        }
        if life == Life::Reforging {
            ha.queue.clear();
            ha.current = None;
            continue;
        }
        let alive = life == Life::Alive;

        // ── events ──
        for ev in &link.fresh_events {
            match *ev {
                GameEvent::Shot { slot, .. } if slot == ha.slot && fire != FireKind::Melee => {
                    ha.last_combat = now;
                    if alive && !ha.exclusive() {
                        fire_clip(ha, an, ap, p, fire, fire_rate, now, log.0);
                    }
                }
                GameEvent::PlayerHurt { slot, amount } if slot == ha.slot && alive => {
                    ha.last_combat = now;
                    let heavy = f32::from(amount) >= 0.1 * p.max_hp.max(1.0);
                    if heavy && !ha.exclusive() && ha.current.is_none() && now - ha.last_hit > 1.2 {
                        ha.last_hit = now;
                        an.clear_upper();
                        let s = OneShot { cancel_after: Some(0.35), ..shot(an, "hit_heavy") };
                        ha.interrupt(an, s);
                    } else if now - ha.last_hit > 0.45 && !an.upper_busy() && !ha.exclusive() {
                        ha.last_hit = now;
                        an.play_upper(ap, "hit_light", 1.0);
                        ha.log_event(log.0, "hit_light");
                    }
                }
                GameEvent::Ping { slot, .. } if slot == ha.slot && alive && !ha.exclusive() => {
                    an.play_upper(ap, "ping", 1.0);
                    ha.log_event(log.0, "ping");
                }
                GameEvent::ArmorBreak { slot } if slot == ha.slot && alive => {
                    an.play_upper(ap, "armor_break", 1.0);
                    ha.log_event(log.0, "armor_break");
                }
                GameEvent::PoiStarted { slot, .. }
                    if slot == ha.slot && alive && ha.current.is_none() && speed < 1.0 =>
                {
                    let s = shot(an, "interact");
                    ha.push(an, s);
                }
                GameEvent::Ability { slot, which, .. } if slot == ha.slot && alive => {
                    ha.last_combat = now;
                    match ha.kit.moves.get(which as usize).copied().unwrap_or(KitMove::None) {
                        KitMove::None => {}
                        KitMove::Strike { clip, from, cancel } => {
                            let seek = from.and_then(|e| an.model.clip(clip)?.meta.event(e)).unwrap_or(0.0);
                            let s = OneShot {
                                seek,
                                length: clip_len(an, clip) - seek,
                                exclusive: true,
                                face: Some(aim),
                                cancel_after: Some(cancel),
                                ..shot(an, clip)
                            };
                            an.clear_upper();
                            ha.interrupt(an, s);
                        }
                        KitMove::Rush { run, end, time } => {
                            let dir = aim;
                            let s = OneShot {
                                length: time,
                                exclusive: true,
                                face: Some(dir),
                                face_travel: true,
                                cancel_after: None,
                                ..shot(an, run)
                            };
                            an.clear_upper();
                            ha.interrupt(an, s);
                            let e =
                                OneShot { exclusive: true, face: Some(dir), cancel_after: Some(0.2), ..shot(an, end) };
                            ha.push(an, e);
                        }
                    }
                }
                _ => {}
            }
        }
        // Melee strikes carry no Shot event: a snapshot with the swing flag set is one strike.
        if fire == FireKind::Melee && p.firing && world.tick != ha.last_tick {
            ha.last_combat = now;
            if alive && !ha.exclusive() {
                fire_clip(ha, an, ap, p, fire, fire_rate, now, log.0);
            }
        }
        ha.last_tick = world.tick;
        // A charge chassis holds its charge pose; a beam holds the brace while it burns.
        let hold = match fire {
            FireKind::Charge if p.charge > 0.05 => Some("fire_charge"),
            FireKind::Beam if p.beam.is_some() => Some("fire_charge"),
            _ => None,
        };
        an.set_upper_loop(ap, if ha.exclusive() || !alive { None } else { hold });

        // ── kit flags ──
        let stance = p.flags.contains(PlayerFlags::STANCE);
        if stance != ha.stance {
            ha.stance = stance;
            if let Some([enter, _, exit, _]) = ha.kit.stance
                && alive
            {
                let s = if stance {
                    OneShot { exclusive: true, cancel_after: None, ..shot(an, enter) }
                } else {
                    shot(an, exit)
                };
                an.clear_upper();
                ha.interrupt(an, s);
            }
        }
        let avatar = p.flags.contains(PlayerFlags::AVATAR);
        if avatar != ha.avatar {
            ha.avatar = avatar;
            ha.next_pound = f32::INFINITY;
            if avatar && alive {
                if let Some([start, _]) = ha.kit.avatar {
                    let s = OneShot { exclusive: true, cancel_after: Some(0.5), ..shot(an, start) };
                    an.clear_upper();
                    ha.interrupt(an, s);
                }
                if let Some((clip, every)) = ha.kit.pound {
                    // The sim's first pulse comes half an interval after the cast.
                    let at = an.model.clip(clip).and_then(|c| c.meta.event("pound")).unwrap_or(0.5);
                    ha.next_pound = now + every * 0.5 - at;
                }
            }
        }
        if avatar && let Some((clip, every)) = ha.kit.pound {
            while now >= ha.next_pound {
                ha.next_pound += every;
                if alive && !ha.exclusive() {
                    an.play_upper(ap, clip, 1.0);
                    ha.log_event(log.0, clip);
                }
            }
        }
        let victory = world.run.phase == RunPhase::Victory;
        if victory && !ha.victory && alive {
            let s = OneShot { hold: true, exclusive: true, cancel_after: None, ..shot(an, "victory") };
            an.clear_upper();
            ha.interrupt(an, s);
        }
        ha.victory = victory;

        // ── dash ──
        let dashing = mover.dash_left > 0.0 && alive;
        if dashing && !ha.dashing {
            an.clear_upper();
            ha.queue.clear();
            ha.current = None;
            ha.dashing = an.set_base(ap, "dash", 1.0, 0.05, true);
        } else if !dashing && ha.dashing {
            ha.dashing = false;
            if speed < STAND_SPEED * 2.0 {
                let s = shot(an, "dash_recover");
                ha.interrupt(an, s);
            }
        }

        // ── one-shots ──
        if let Some((s, start)) = &ha.current {
            let t = now - start;
            let done = t >= s.length / s.speed.max(0.05);
            let moved = s.cancel_after.is_some_and(|c| t >= c && speed > STAND_SPEED * 2.0);
            let over = s.hold && ((s.clip == "victory" && !victory) || (s.clip == "death" && life != Life::Downed));
            if (done && !s.hold) || moved || over {
                ha.current = None;
            }
        }
        if ha.current.is_none()
            && let Some(next) = ha.queue.pop_front()
        {
            an.set_base_at(ap, next.clip, next.speed, FADE_ONESHOT, true, next.seek);
            ha.current = Some((next, now));
        }

        // ── base ──
        let moving = speed > if ha.gait.is_some() { STAND_SPEED * 0.6 } else { STAND_SPEED };
        let mut facing = aim;
        let mut idle = false;
        let (clip, rate): (&str, f32) = if ha.dashing {
            if mover.dash_dir.length_squared() > 0.0 {
                facing = mover.dash_dir.y.atan2(mover.dash_dir.x);
            }
            ("dash", 1.0)
        } else if let Some((s, _)) = &ha.current {
            if s.face_travel && speed > p.move_speed * 1.2 {
                facing = heading;
            } else if let Some(f) = s.face {
                facing = f;
            }
            (s.clip, s.speed)
        } else if life == Life::Downed {
            if moving {
                facing = heading;
            }
            ("downed", 1.0)
        } else if let Some([_, hold, _, _]) = ha.kit.stance.filter(|_| stance) {
            (hold, 1.0)
        } else if p.forge_open && !moving && an.has("forge_hammer") {
            ("forge_hammer", 1.0)
        } else if moving {
            let rel = wrap(heading - ha.facing.unwrap_or(aim));
            let mut gait = Gait::pick(rel, ha.gait);
            // Walk below ~55 % of move speed, with a band so a speed ramp does not flicker.
            let walk_below = if ha.gait == Some(Gait::Walk) { 0.62 } else { 0.5 };
            if gait == Gait::Run && speed < walk_below * p.move_speed {
                gait = Gait::Walk;
            }
            // A gait holds for a moment: bots and sticks jitter across the sector edges.
            match ha.gait {
                Some(g) if g != gait && now - ha.gait_since < GAIT_DWELL => gait = g,
                Some(g) if g == gait => {}
                _ => ha.gait_since = now,
            }
            ha.gait = Some(gait);
            let design = an.model.clip(gait.clip()).and_then(|c| c.meta.design_speed).unwrap_or(p.move_speed.max(1.0));
            // A scaled avatar strides longer: its feet plant at the scaled design speed.
            (gait.clip(), (speed / (design * p.scale.max(0.2))).clamp(0.35, 2.5))
        } else {
            ha.gait = None;
            idle = true;
            let near = visuals.iter().any(|v| {
                matches!(v.kind, EntityKind::Enemy { .. })
                    && v.shown.distance_squared(p.mover.pos) < COMBAT_RANGE * COMBAT_RANGE
            });
            let combat = near || now - ha.last_combat < COMBAT_LINGER;
            if combat {
                ha.idle_since = now;
            }
            match ha.kit.avatar.filter(|_| avatar) {
                Some([_, loop_clip]) => (loop_clip, 1.0),
                None if combat => ("idle_combat", 1.0),
                None if now - ha.idle_since > SIGNATURE_AFTER && an.has("idle_signature") => ("idle_signature", 1.0),
                None => ("idle", 1.0),
            }
        };
        if !idle {
            ha.idle_since = now;
        }
        if ha.current.is_none() && !ha.dashing {
            let fade = if an.base_name() == "dash" { 0.12 } else { FADE_LOCO };
            an.set_base(ap, clip, rate, fade, false);
        }
        if log.0 && ha.logged != an.base_name() {
            info!(
                "anim P{} {}: {} -> {} (speed {:.1} m/s, {:?}{}{}{})",
                ha.slot + 1,
                ha.key,
                if ha.logged.is_empty() { "-" } else { ha.logged.as_str() },
                an.base_name(),
                speed,
                life,
                if stance { ", stance" } else { "" },
                if avatar { ", avatar" } else { "" },
                if p.forge_open { ", forge open" } else { "" },
            );
            ha.logged = an.base_name().to_string();
        }

        // ── facing ──
        let f = ha.facing.get_or_insert(facing);
        let k = if ha.dashing { 30.0 } else { 14.0 };
        *f = wrap(*f + wrap(facing - *f) * (1.0 - (-k * dt).exp()));
        tf.rotation = yaw(*f) * Quat::from_rotation_y(PI);

        // ── gauntlet variants ──
        if let Some(open) = an.hands_open(ap)
            && gear.hands_open != open
        {
            gear.hands_open = open;
        }
    }
}

/// Play the clip for one shot or strike over the base.
fn fire_clip(
    ha: &mut HeroAnim,
    an: &mut Animator,
    ap: &mut AnimationPlayer,
    p: &PlayerView,
    fire: FireKind,
    fire_rate: f32,
    now: f32,
    log: bool,
) {
    let stance = ha.kit.stance.filter(|_| p.flags.contains(PlayerFlags::STANCE));
    let clip: &str = if let Some([_, _, _, siege]) = stance {
        siege
    } else if fire == FireKind::Melee && an.has("jab_l") && an.has("jab_r") {
        // A held string: left, right, and every third strike a hook.
        if now - ha.last_strike > 1.0 {
            ha.strikes = 0;
        }
        let n = ha.strikes;
        ha.strikes += 1;
        if n % 3 == 2 && an.has("hook") {
            "hook"
        } else if n.is_multiple_of(3) {
            "jab_l"
        } else {
            "jab_r"
        }
    } else if matches!(fire, FireKind::Charge) || fire_rate < 1.0 {
        "fire_heavy"
    } else {
        "fire_light"
    };
    ha.last_strike = now;
    // Fast guns re-fire before the clip ends: let the thrust finish its first half.
    if let Some(t) = an.upper_time(ap, clip)
        && fire != FireKind::Melee
        && t < clip_len(an, clip) * 0.5
    {
        return;
    }
    let speed = if fire == FireKind::Melee { (fire_rate / 3.0).clamp(1.0, 1.6) } else { 1.0 };
    if an.play_upper(ap, clip, speed) || an.play_upper(ap, "fire_light", 1.0) {
        ha.log_event(log, clip);
    }
}

/// `--anim-gallery [N]`: the clip to start from.
fn gallery_start() -> usize {
    let args: Vec<String> = std::env::args().collect();
    let arg =
        args.iter().position(|a| a == "--anim-gallery").and_then(|i| args.get(i + 1)).and_then(|v| v.parse().ok());
    arg.or_else(|| std::env::var("GODFORGE_ANIM_GALLERY").ok()?.parse().ok()).unwrap_or(0)
}

pub fn build(app: &mut App) {
    let flag = |arg: &str, env: &str| std::env::args().any(|a| a == arg) || std::env::var(env).is_ok_and(|v| v != "0");
    app.insert_resource(AnimLog(flag("--anim-log", "GODFORGE_ANIM_LOG")))
        .insert_resource(AnimGallery(flag("--anim-gallery", "GODFORGE_ANIM_GALLERY").then(gallery_start)))
        .add_systems(Update, (drive_heroes, tick_animators).chain().in_set(ClientSet::Presentation));
}
