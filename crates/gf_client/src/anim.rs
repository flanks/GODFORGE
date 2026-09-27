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

use crate::camera::{MainCamera, w3};
use crate::input::InputState;
use crate::models::{HeroGear, Model, ModelParts};
use crate::net::{Link, Prediction};
use crate::palette::yaw;
use crate::scene::{AnvilBlocks, Corpse, SceneIndex, Visual};
use crate::{ClientConfig, ClientSet};
use gf_content::EnemyClass;
use gf_core::aim::AimMode;
use gf_core::damage::DamageType;
use gf_core::ids::{NetId, SourceId};
use gf_core::revive::LifeState;
use gf_core::weapon::FireKind;
use gf_engine::bevy::animation::{AnimationTargetId, RepeatAnimation, graph::AnimationNodeIndex};
use gf_engine::client::world_to_screen;
use gf_engine::prelude::*;
use gf_net::quant::u16_to_dir;
use gf_net::{EntityFlags, EntityKind, GameEvent, PlayerFlags, PlayerView, RunPhase, TeleShape};
use std::collections::{HashMap, VecDeque};
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
        self.play_upper_at(player, name, speed, 0.0)
    }

    /// [`Animator::play_upper`] from `seek` s into the clip (a full-body move finishing on the
    /// upper body once the legs are taken: its `<clip>@upper` copy).
    pub fn play_upper_at(&mut self, player: &mut AnimationPlayer, name: &str, speed: f32, seek: f32) -> bool {
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
        if seek > 0.0 {
            a.set_seek_time(seek);
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
    /// Cut short by a dash or by moving on, the move finishes on the upper body (its
    /// `<clip>@upper` copy) so its payoff (the uppercut's slam, the ultimate's clash) still lands.
    tail: bool,
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
    /// An upper-layer cast: the hero keeps moving, shots wait until its arms are free.
    Upper {
        clip: &'static str,
    },
}

/// How long a hero's ultimate loop lasts.
#[derive(Clone, Copy, Debug)]
enum During {
    /// While this replicated flag is up (Meltdown, Mountainfall: `AVATAR`; Bullet Ballet: `INFINITE_DASH`).
    Flag(PlayerFlags),
    /// This long after the ultimate's `GameEvent::Ability` (Heaven's Verdict: the caster wears no flag).
    Cast(f32),
}

/// The ultimate's buff on the body: `start` when it begins, `idle` in place of `idle_combat` while it lasts.
#[derive(Clone, Copy, Debug)]
struct Avatar {
    start: &'static str,
    idle: &'static str,
    during: During,
    /// Every shot while it lasts (Bullet Ballet's twin pistols).
    fire: Option<&'static str>,
    /// Every dash while it lasts (Bullet Ballet's infinite dash: the Ghost Step).
    dash: Option<&'static str>,
}

#[derive(Clone, Copy, Debug)]
struct KitClips {
    moves: [KitMove; 3],
    /// `PlayerFlags::STANCE`: enter, loop (replaces idle and locomotion), exit, per-shot clip.
    stance: Option<[&'static str; 4]>,
    avatar: Option<Avatar>,
    /// A pound layered every `every` s during the avatar, its event `at` s into the clip lining up
    /// with the sim's pulse (first pulse half an interval after the cast).
    pound: Option<(&'static str, f32)>,
    /// The hero's own rapid chassis (key) shoots this clip instead of `fire_light`.
    rapid: Option<(&'static str, &'static str)>,
    /// A dash the passive gave back (a kill in the same snapshot as a charge) plays this instead of `dash`.
    refund_dash: Option<&'static str>,
    /// The passive meter reaching this cap plays this upper clip once.
    meter_full: Option<(&'static str, f32)>,
}

impl KitClips {
    const NONE: KitClips = KitClips {
        moves: [KitMove::None; 3],
        stance: None,
        avatar: None,
        pound: None,
        rapid: None,
        refund_dash: None,
        meter_full: None,
    };
}

fn kit_clips(key: &str) -> KitClips {
    let avatar = |start, idle, during| Some(Avatar { start, idle, during, fire: None, dash: None });
    match key {
        "brax" => KitClips {
            // Cinder Uppercut: Nova on `launch` (f10), the slam's geysers on `slam` (f25).
            moves: [
                KitMove::Strike { clip: "uppercut", from: None, cancel: 0.95 },
                KitMove::Rush { run: "furnace_rush", end: "furnace_rush_end", time: 0.4 },
                KitMove::None,
            ],
            avatar: avatar("meltdown_start", "meltdown", During::Flag(PlayerFlags::AVATAR)),
            ..KitClips::NONE
        },
        "valdris" => KitClips {
            // Bulwark Slam: the 0.45 s leap runs `launch` (f8) → `land` (f21).
            moves: [
                KitMove::Strike { clip: "bulwark_slam", from: Some("launch"), cancel: 0.6 },
                KitMove::None,
                KitMove::None,
            ],
            stance: Some(["siege_stance_enter", "siege_stance", "siege_stance_exit", "siege_fire"]),
            avatar: avatar("mountainfall_start", "mountainfall", During::Flag(PlayerFlags::AVATAR)),
            pound: Some(("mountainfall_pound", 1.1)),
            ..KitClips::NONE
        },
        "kael" => KitClips {
            // Fan of Blades (the Cone resolves on cast) fires on the move; Shadow Roll's 0.22 s Rush
            // runs `roll` (f2) → `land` (f10), then he rises into the aim.
            moves: [
                KitMove::Upper { clip: "fan_of_blades" },
                KitMove::Strike { clip: "shadow_roll", from: Some("roll"), cancel: 0.4 },
                KitMove::None,
            ],
            // Bullet Ballet scales nothing (no AVATAR): its 6 s of infinite dash carry the loop, the
            // twin shots and a Ghost Step on every dash.
            avatar: Some(Avatar {
                start: "bullet_ballet_start",
                idle: "bullet_ballet",
                during: During::Flag(PlayerFlags::INFINITE_DASH),
                fire: Some("fire_twin"),
                dash: Some("ghost_step"),
            }),
            rapid: Some(("serpent_smg", "fire_r")),
            // Ghost Step: a kill may refund a dash charge; that dash is the ghost step.
            refund_dash: Some("ghost_step"),
            ..KitClips::NONE
        },
        "selene" => KitClips {
            // Arc Nova chains on cast, on the move; Blink teleports on cast, so she lands (`blink_in`)
            // where the snapshot already has her.
            moves: [
                KitMove::Upper { clip: "arc_nova" },
                KitMove::Strike { clip: "blink_in", from: None, cancel: 0.2 },
                KitMove::None,
            ],
            // Heaven's Verdict: the storm front lives 8 s (kits.ron); the caster wears no flag.
            avatar: avatar("heavens_verdict_start", "heavens_verdict", During::Cast(8.0)),
            // Static Charge full (+60 %, kits.ron `max_bonus`).
            meter_full: Some(("static_charge", 0.6)),
            ..KitClips::NONE
        },
        _ => KitClips::NONE,
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
    /// The clip of the dash in progress (`dash`, or a Ghost Step) and when it began.
    dash_clip: &'static str,
    dash_start: f32,
    /// A refunded dash charge waits until then (s) to play its Ghost Step.
    ghost_ready: f32,
    dash_charges: u8,
    stance: bool,
    avatar: bool,
    /// A timed ultimate loop (`During::Cast`) lasts until then (s).
    avatar_until: f32,
    /// An upper-layer kit cast holds the arms until then (s): shots wait.
    upper_until: f32,
    meter_full: bool,
    /// This frame's light-shot clip (`fire_light`, or the hero's own rapid chassis clip).
    fire_light: &'static str,
    next_pound: f32,
    victory: bool,
    /// Melee: the next strike of the predicted swing cadence, and until when it runs.
    swing_next: f32,
    swing_until: f32,
    /// Seconds the hero has stood still with the forge open (the hammer waits for 0.3 s).
    forge_hold: f32,
    /// Where the model stands off the sim position (sim metres): out of an anvil's iron.
    offset: Vec2,
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
            dash_clip: "dash",
            dash_start: 0.0,
            ghost_ready: -100.0,
            dash_charges: 0,
            stance: false,
            avatar: false,
            avatar_until: -100.0,
            upper_until: -100.0,
            meter_full: false,
            fire_light: "fire_light",
            next_pound: f32::INFINITY,
            victory: false,
            swing_next: 0.0,
            swing_until: 0.0,
            forge_hold: 0.0,
            offset: Vec2::ZERO,
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
        tail: false,
    }
}

/// A cut one-shot finishes on the upper body from where it was (see [`OneShot::tail`]).
fn finish_on_upper(an: &mut Animator, ap: &mut AnimationPlayer, s: &OneShot, t: f32, log: bool, ha: &HeroAnim) {
    let at = s.seek + t * s.speed;
    let name = format!("{}@upper", s.clip);
    if s.tail && at < clip_len(an, s.clip) - 0.1 && an.play_upper_at(ap, &name, s.speed, at) {
        ha.log_event(log, &name);
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
    let mut names: Vec<String> = lib.clips.keys().filter(|n| !n.contains('@')).cloned().collect();
    names.sort();
    // Then the layering: upper-body clips over locomotion (`base+upper`).
    for (base, upper) in GALLERY_LAYERED {
        let upper = match ha.kit.rapid {
            _ if ha.key == "brax" => upper.replace("fire_light", "jab_r"),
            Some((_, rapid)) => upper.replace("fire_light", rapid),
            None => upper.to_string(),
        };
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
    blocks: Res<AnvilBlocks>,
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
        ha.fire_light = match ha.kit.rapid {
            Some((key, clip)) if chassis.is_some_and(|c| c.key == key) && an.has(clip) => clip,
            _ => "fire_light",
        };

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
                    if which == 2
                        && let Some(Avatar { during: During::Cast(time), .. }) = ha.kit.avatar
                    {
                        ha.avatar_until = now + time;
                    }
                    match ha.kit.moves.get(which as usize).copied().unwrap_or(KitMove::None) {
                        KitMove::None => {}
                        KitMove::Upper { clip } => {
                            an.clear_upper();
                            if an.play_upper(ap, clip, 1.0) {
                                ha.upper_until = now + clip_len(an, clip) * 0.8;
                                ha.log_event(log.0, clip);
                            }
                        }
                        KitMove::Strike { clip, from, cancel } => {
                            let seek = from.and_then(|e| an.model.clip(clip)?.meta.event(e)).unwrap_or(0.0);
                            let s = OneShot {
                                seek,
                                length: clip_len(an, clip) - seek,
                                exclusive: true,
                                face: Some(aim),
                                cancel_after: Some(cancel),
                                tail: true,
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
        // Melee strikes carry no Shot event, and the swing flag is up for a single sim tick
        // (snapshots miss most of them). The client keeps the weapon's cadence while the hero is
        // swinging: a caught flag, a hit of its own or a foe in its reach keeps it going, and the
        // evidence re-phases it.
        if fire == FireKind::Melee {
            let interval = 1.0 / fire_rate.max(0.5);
            let flagged = p.firing && world.tick != ha.last_tick;
            let landed =
                link.fresh_events.iter().any(|e| matches!(*e, GameEvent::Hit { source, .. } if source == ha.slot));
            let reach = chassis.map_or(2.5, |c| c.stats.range) + 0.4;
            let ahead = Vec2::from_angle(aim);
            let in_reach = alive
                && visuals.iter().any(|v| {
                    if !matches!(v.kind, EntityKind::Enemy { .. }) {
                        return false;
                    }
                    let d = v.shown - p.mover.pos;
                    let r = d.length();
                    r < reach + v.radius && (r < 0.5 + v.radius || d.dot(ahead) > 0.5 * r)
                });
            if flagged || landed || in_reach {
                ha.swing_until = now + interval * 1.25;
            }
            let due = if flagged || landed {
                now >= ha.swing_next - interval * 0.5
            } else {
                now < ha.swing_until && now >= ha.swing_next
            };
            if due {
                ha.swing_next = now + interval;
                ha.last_combat = now;
                if alive && !ha.exclusive() {
                    fire_clip(ha, an, ap, p, fire, fire_rate, now, log.0);
                }
            }
        }
        ha.last_tick = world.tick;
        // The passive gave a dash charge back: a kill of this hero's in the snapshot that raised it.
        let charges = p.mover.dash_charges;
        if ha.kit.refund_dash.is_some() && charges > ha.dash_charges {
            let killed = link.fresh_events.iter().any(
                |e| matches!(*e, GameEvent::Kill { source, .. } if SourceId(source).owner_slot() == Some(ha.slot)),
            );
            if killed {
                ha.ghost_ready = now + 3.0;
            }
        }
        ha.dash_charges = charges;
        // The passive meter at its cap (Static Charge): once per fill.
        if let Some((clip, cap)) = ha.kit.meter_full {
            let full = p.passive_meter >= cap - 0.005;
            if full && !ha.meter_full && alive && !ha.exclusive() && an.play_upper(ap, clip, 1.0) {
                ha.upper_until = now + clip_len(an, clip) * 0.8;
                ha.log_event(log.0, clip);
            }
            ha.meter_full = full;
        }
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
        let avatar = match ha.kit.avatar.map(|a| a.during) {
            Some(During::Flag(f)) => p.flags.contains(f),
            Some(During::Cast(_)) => now < ha.avatar_until,
            None => false,
        };
        if avatar != ha.avatar {
            ha.avatar = avatar;
            ha.next_pound = f32::INFINITY;
            if avatar && alive {
                if let Some(Avatar { start, .. }) = ha.kit.avatar {
                    // Held through its payoff (Meltdown's clash, Mountainfall's stomp), then
                    // finished on the upper body if the hero moves on.
                    let payoff =
                        an.model.clip(start).and_then(|c| c.meta.events.iter().map(|(_, t)| *t).reduce(f32::max));
                    let s = OneShot {
                        exclusive: true,
                        cancel_after: Some(payoff.map_or(0.9, |t| t + 0.05)),
                        tail: true,
                        ..shot(an, start)
                    };
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
            if let Some((s, start)) = ha.current.take() {
                finish_on_upper(an, ap, &s, now - start, log.0, ha);
            }
            // A Ghost Step: every dash of the ultimate that grants it, or the one a kill refunded.
            let refunded = now < ha.ghost_ready;
            ha.ghost_ready = -100.0;
            let ghost =
                ha.kit.avatar.filter(|_| ha.avatar).and_then(|a| a.dash).or(ha.kit.refund_dash.filter(|_| refunded));
            ha.dash_clip = ghost.filter(|c| an.has(c)).unwrap_or("dash");
            ha.dash_start = now;
            ha.dashing = an.set_base(ap, ha.dash_clip, 1.0, 0.05, true);
        } else if !dashing && ha.dashing {
            ha.dashing = false;
            if ha.dash_clip != "dash" {
                // The Ghost Step outlasts the sim's dash: it lands as a one-shot of the clip already playing.
                let s = OneShot { cancel_after: Some(0.34), ..shot(an, ha.dash_clip) };
                ha.queue.clear();
                ha.current = Some((s, ha.dash_start));
            } else if speed < STAND_SPEED * 2.0 {
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
                if moved && !done {
                    let s = s.clone();
                    finish_on_upper(an, ap, &s, t, log.0, ha);
                }
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
        // The forge: standing still at an anvil with its window open for a moment.
        let anvil = blocks.nearest(p.mover.pos, 6.0);
        ha.forge_hold = if p.forge_open && anvil.is_some() && speed < 0.6 { ha.forge_hold + dt } else { 0.0 };
        let mut facing = aim;
        let mut idle = false;
        let (clip, rate): (&str, f32) = if ha.dashing {
            if mover.dash_dir.length_squared() > 0.0 {
                facing = mover.dash_dir.y.atan2(mover.dash_dir.x);
            }
            (ha.dash_clip, 1.0)
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
        } else if ha.forge_hold > 0.3 && an.has("forge_hammer") {
            // Hammering the anvil it stands at (the model stands at the iron's edge, below).
            if let Some(c) = anvil {
                let d = c - (p.mover.pos + ha.offset);
                facing = d.y.atan2(d.x);
            }
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
                Some(a) => (a.idle, 1.0),
                None if combat => ("idle_combat", 1.0),
                None if now - ha.idle_since > SIGNATURE_AFTER && an.has("idle_signature") => ("idle_signature", 1.0),
                None => ("idle", 1.0),
            }
        };
        if !idle {
            ha.idle_since = now;
        }
        if ha.current.is_none() && !ha.dashing {
            let fade = if an.base_name() == ha.dash_clip { 0.12 } else { FADE_LOCO };
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

        // ── standing room: the sim walks heroes into an anvil's iron; the model stands at its edge ──
        let want = blocks.push_out(p.mover.pos, p.radius.max(0.35)) - p.mover.pos;
        ha.offset += (want - ha.offset) * (1.0 - (-12.0 * dt).exp());
        let scale = p.scale.max(0.2);
        tf.translation = Vec3::new(ha.offset.x / scale, 0.0, -ha.offset.y / scale);

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
    // An upper-layer kit cast (Fan of Blades, Arc Nova, Static Charge) keeps the arms.
    if now < ha.upper_until {
        return;
    }
    let stance = ha.kit.stance.filter(|_| p.flags.contains(PlayerFlags::STANCE));
    let twin = ha.kit.avatar.filter(|_| ha.avatar).and_then(|a| a.fire).filter(|c| an.has(c));
    let clip: &str = if let Some([_, _, _, siege]) = stance {
        siege
    } else if let Some(twin) = twin {
        twin
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
        ha.fire_light
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

// ───────────────────────────── enemies ─────────────────────────────

/// How an enemy's behaviour reads on its clips (docs/art/ENEMIES.md, each sidecar's clip notes).
#[derive(Clone, Debug)]
enum Brain {
    /// Contact fighters (Chaser, Swarmer): a bite when touching a hero.
    Melee,
    /// `WINDUP` holds the wind-up; `CHARGING` launches with `attack`, then `charge@loop`.
    Charger { windup: f32 },
    /// Lobs at a circle telegraph it casts on a hero: a quick wind-up, then the throw.
    Lobber { radius: f32, range: f32 },
    /// `WINDUP`: wind-up, `channel@loop`, then `attack` with its fire key on the beam's resolve.
    Caster { windup: f32 },
    /// `PRIMED`: wind-up into `primed@loop`; the corpse plays `attack`, the detonation.
    Bomber { fuse: f32 },
    /// Shields its allies every `interval` (`cast`); bashes a hero in reach.
    Support { interval: f32 },
    /// A scripted fight: its `bosses.ron` script and the HP fractions each phase starts below.
    Boss { script: String, phases: Vec<f32> },
}

/// Until when an enemy one-shot plays.
#[derive(Clone, Copy, Debug)]
enum Until {
    /// Real seconds.
    Time(f32),
    /// While any of these flags is up.
    Flag(EntityFlags),
}

/// A clip that overrides an enemy's locomotion for a while.
#[derive(Clone, Debug)]
struct Act {
    clip: String,
    speed: f32,
    seek: f32,
    until: Until,
    /// Nothing else (a hit, a bite, another boss attack) cuts in before this many seconds.
    locked: f32,
    /// Face this sim angle while it plays.
    face: Option<f32>,
}

/// A telegraph, a volley or a wave of adds this enemy set off, read from this frame's fresh
/// entities (the snapshot does not say who cast what; `drive_enemies` matches them by place).
#[derive(Clone, Copy, Debug)]
enum Cue {
    /// A telegraph: its shape, at the caster's feet or not, its wind-up (s), direction (sim
    /// angle), place, and for a boss the script attack it belongs to.
    Tele {
        shape: TeleShape,
        at_self: bool,
        windup: f32,
        dir: f32,
        at: Vec2,
        attack: Option<&'static str>,
    },
    Radial,
    Summon,
}

/// An anvil brute's plates (sidecar `plate_states`): 0 intact, 1 cracked, 2 stripped.
#[derive(Clone, Debug)]
struct Plates {
    state: [u8; 5],
    wear: f32,
    plate_hp: f32,
    /// `plates_break` plays until then (the plates stay cracked for its fling).
    breaking: f32,
    /// Shattered, the fling waits for the wind-up or charge to end.
    pending: bool,
    /// (intact, cracked) joints per plate, found on first use.
    nodes: Option<Vec<(Option<Entity>, Option<Entity>)>>,
}

const PLATE_NAMES: [&str; 5] = ["back", "pauldron", "helm", "cuff_L", "cuff_R"];
const PLATE_CRACK_AT: [f32; 5] = [0.15, 0.35, 0.55, 0.7, 0.85];

/// The per-enemy state machine, on the enemy model entity (beside its `ModelParts`).
#[derive(Component)]
pub struct EnemyAnim {
    /// The `scene::Visual` proxy this model rides.
    visual: Entity,
    id: NetId,
    /// The content key (logs).
    name: String,
    tier: EnemyClass,
    brain: Brain,
    phase: usize,
    phase_known: bool,
    act: Option<(Act, f32)>,
    queue: VecDeque<Act>,
    last_pos: Option<Vec2>,
    speed: f32,
    moving: bool,
    last_hit: f32,
    next_contact: f32,
    next_cast: f32,
    flags: EntityFlags,
    /// `flags` holds a real frame (edges count from the second frame on).
    seen: bool,
    dying: bool,
    frozen: bool,
    /// Off screen: the animation graph is detached (no evaluation at all).
    culled: bool,
    /// Play `spawn` first (a summoned or just-emerged add).
    spawn: bool,
    /// 0..1 per enemy: desyncs a horde's loops and bites.
    seed: f32,
    /// The Slag King's crown: accumulated spin (rad) about `crown_spin`'s +Y.
    crown: f32,
    plates: Option<Plates>,
    logged: String,
}

impl EnemyAnim {
    pub fn new(visual: Entity, id: NetId, def: &gf_content::EnemyDef, db: &gf_content::ContentDb, fresh: bool) -> Self {
        use gf_content::EnemyBehavior as B;
        let brain = match &def.behavior {
            B::Chaser | B::Swarmer { .. } => Brain::Melee,
            B::Charger { windup, .. } => Brain::Charger { windup: *windup },
            B::Lobber { radius, range, .. } => Brain::Lobber { radius: *radius, range: *range },
            B::Caster { windup, .. } => Brain::Caster { windup: *windup },
            B::Bomber { fuse, .. } => Brain::Bomber { fuse: *fuse },
            B::Support { interval, .. } => Brain::Support { interval: *interval },
            B::Boss { script } => Brain::Boss {
                script: script.clone(),
                phases: db
                    .bosses
                    .by_key(script)
                    .map(|s| s.phases.iter().map(|p| p.below).collect())
                    .unwrap_or_default(),
            },
        };
        let seed = ((id.0.wrapping_mul(2_654_435_761) >> 8) & 0xffff) as f32 / 65535.0;
        EnemyAnim {
            visual,
            id,
            name: def.key.clone(),
            tier: def.class,
            brain,
            phase: 0,
            phase_known: false,
            act: None,
            queue: VecDeque::new(),
            last_pos: None,
            speed: 0.0,
            moving: false,
            last_hit: -100.0,
            next_contact: 0.0,
            next_cast: f32::INFINITY,
            flags: EntityFlags::empty(),
            seen: false,
            dying: false,
            frozen: false,
            culled: false,
            spawn: fresh,
            seed,
            crown: 0.0,
            plates: def.plating.as_ref().map(|p| Plates {
                state: [0; 5],
                wear: 0.0,
                plate_hp: p.plate_hp.max(1.0),
                breaking: 0.0,
                pending: false,
                nodes: None,
            }),
            logged: String::new(),
        }
    }

    fn boss(&self) -> bool {
        matches!(self.brain, Brain::Boss { .. })
    }

    /// Logged by `--anim-log`: every elite and boss, and the swarms with a behaviour of their
    /// own (lobs, fuses); not the horde's bites.
    fn loud(&self) -> bool {
        self.tier != EnemyClass::Swarm || matches!(self.brain, Brain::Lobber { .. } | Brain::Bomber { .. })
    }

    /// The clip for `base` in the current phase: `<base>_p2` from the second phase on when the
    /// model has it (docs/art/ENEMIES.md §6), else `<base>`.
    fn resolve(&self, an: &Animator, base: &str) -> Option<String> {
        if self.phase >= 1 {
            let p2 = format!("{base}_p2");
            if an.has(&p2) {
                return Some(p2);
            }
        }
        an.has(base).then(|| base.to_string())
    }

    /// An act for `base` (resolved per phase) played once through at `speed`.
    fn once(&self, an: &Animator, base: &str, speed: f32) -> Option<Act> {
        let clip = self.resolve(an, base)?;
        let len = clip_len(an, &clip);
        Some(Act { clip, speed, seek: 0.0, until: Until::Time(len / speed.max(0.05)), locked: 0.0, face: None })
    }

    /// Replace whatever plays and is queued.
    fn interrupt(&mut self, an: &mut Animator, ap: &mut AnimationPlayer, act: Act, now: f32) {
        self.queue.clear();
        self.begin(an, ap, act, now);
    }

    fn begin(&mut self, an: &mut Animator, ap: &mut AnimationPlayer, act: Act, now: f32) {
        let fade = if self.boss() {
            0.25
        } else if self.tier == EnemyClass::Swarm {
            0.06
        } else {
            0.12
        };
        an.set_base_at(ap, &act.clip, act.speed, fade, true, act.seek);
        self.act = Some((act, now));
    }

    /// Is the current act past its lock (or is there none)?
    fn free(&self, now: f32) -> bool {
        self.act.as_ref().is_none_or(|(a, start)| now - start >= a.locked)
    }

    fn playing(&self, clip: &str) -> bool {
        self.act.as_ref().is_some_and(|(a, _)| a.clip.starts_with(clip))
    }
}

/// Which of a boss script's attacks sets down this telegraph (by shape and size; the snapshot
/// quantizes sizes to 1/32 m), named like its clip: `strike_<shape>`, `slam_trail`, `pools`
/// (docs/art/ENEMIES.md §6: attack clips carry the `bosses.ron` variant's name).
fn boss_telegraph(script: &gf_content::BossScript, shape: TeleShape, at_self: bool) -> Option<&'static str> {
    use gf_content::{BossAttack as A, TelegraphShape as S};
    let near = |a: f32, q: u16| (a - f32::from(q) / 32.0).abs() < 0.06;
    for attack in script.phases.iter().flat_map(|p| &p.attacks) {
        let name = match (attack, shape) {
            (A::Strike { shape: s, at_self: own, .. }, _) => match (*s, shape) {
                (S::Circle { radius }, TeleShape::Circle { r }) if near(radius, r) && *own == at_self => {
                    "strike_circle"
                }
                (S::Ring { inner, outer }, TeleShape::Ring { inner: i, outer: o })
                    if near(inner, i) && near(outer, o) =>
                {
                    "strike_ring"
                }
                (S::Cone { range, .. }, TeleShape::Cone { range: r, .. }) if near(range, r) => "strike_cone",
                (S::Line { length, width }, TeleShape::Line { len, width: w })
                    if near(length, len) && near(width, w) =>
                {
                    "strike_line"
                }
                _ => continue,
            },
            (A::SlamTrail { radius, .. }, TeleShape::Circle { r }) if near(*radius, r) => "slam_trail",
            (A::Pools { radius, .. }, TeleShape::Circle { r }) if near(*radius, r) => "pools",
            _ => continue,
        };
        return Some(name);
    }
    None
}

/// The attack a boss starts this frame, from its cues. A slam trail's circles and a volley of
/// pools arrive over several frames: only the first starts the clip.
fn boss_attack(ea: &EnemyAnim, cues: &[Cue]) -> Option<(String, Cue)> {
    cues.iter().find_map(|cue| match *cue {
        Cue::Tele { attack: Some(name), .. } if !(matches!(name, "slam_trail" | "pools") && ea.playing(name)) => {
            Some((name.to_string(), *cue))
        }
        Cue::Radial => Some(("radial".to_string(), *cue)),
        Cue::Summon => Some(("summon".to_string(), *cue)),
        _ => None,
    })
}

/// The enemy animation LOD (off-screen swarms detach their graph). `GODFORGE_ENEMY_LOD=0` turns it
/// off, to measure what it saves.
#[derive(Resource)]
pub struct EnemyLod(pub bool);

/// Sim angle from `a` to `b`.
fn angle_to(a: Vec2, b: Vec2) -> f32 {
    let d = b - a;
    d.y.atan2(d.x)
}

/// Drives every enemy model from the snapshot: locomotion from the rendered ground speed, the
/// behaviour's wind-ups and attacks from its flags and the telegraphs it casts, hits (throttled),
/// boss phases and attacks, deaths on the corpse proxy. Off-screen swarms detach their graph
/// (the animation LOD).
#[allow(clippy::too_many_arguments)]
fn drive_enemies(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    index: Res<SceneIndex>,
    log: Res<AnimLog>,
    lod: Res<EnemyLod>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut enemies: Query<(&mut EnemyAnim, &ModelParts)>,
    mut visuals: Query<&mut Visual>,
    mut corpses: Query<&mut Corpse>,
    mut animators: Query<(&mut Animator, &mut AnimationPlayer)>,
) {
    let Some(world) = link.latest.as_deref() else { return };
    let now = time.elapsed_secs();
    let dt = time.delta_secs().max(1.0e-4);
    let heroes: Vec<Vec2> = world.players.iter().filter(|p| p.life.is_alive()).map(|p| p.mover.pos).collect();
    let nearest_hero =
        |p: Vec2| heroes.iter().copied().min_by(|a, b| a.distance_squared(p).total_cmp(&b.distance_squared(p)));

    // Who stands where (models only), for matching telegraphs, volleys and adds to their caster.
    struct Body<'a> {
        visual: Entity,
        pos: Vec2,
        radius: f32,
        /// Casts at its own feet (a charge line, a beam, a fuse).
        feet: bool,
        script: Option<&'a gf_content::BossScript>,
        lob: Option<(f32, f32)>,
    }
    let db = &cfg.content;
    let bodies: Vec<Body> = enemies
        .iter()
        .filter(|(ea, _)| !ea.dying)
        .filter_map(|(ea, _)| {
            let v = visuals.get(ea.visual).ok()?;
            Some(Body {
                visual: ea.visual,
                pos: v.pos,
                radius: v.radius,
                feet: matches!(ea.brain, Brain::Charger { .. } | Brain::Caster { .. } | Brain::Bomber { .. }),
                script: match &ea.brain {
                    Brain::Boss { script, .. } => db.bosses.by_key(script),
                    _ => None,
                },
                lob: match ea.brain {
                    Brain::Lobber { radius, range } => Some((radius, range)),
                    _ => None,
                },
            })
        })
        .collect();
    let mut cues: HashMap<Entity, Vec<Cue>> = HashMap::new();
    let (mut shots, mut adds) = (Vec::new(), Vec::new());
    for e in &index.fresh {
        let at = e.pos.to_vec2();
        match e.kind {
            // Heroes' telegraphs (gold) are theirs.
            EntityKind::Telegraph { shape, dir, windup_ticks, .. } if !e.flags.contains(EntityFlags::ALLY) => {
                let near = |b: &&Body| b.pos.distance_squared(at);
                let at_feet = |b: &Body| b.pos.distance(at) < 0.3 + 0.12 * b.radius;
                // At a caster's feet, else a lob of the right size in range, else one of a boss's
                // attacks by its script.
                let own = bodies.iter().filter(|b| b.feet && at_feet(b)).min_by(|a, b| near(a).total_cmp(&near(b)));
                let lob = || match shape {
                    TeleShape::Circle { r } => bodies
                        .iter()
                        .filter(|b| {
                            b.lob.is_some_and(|(radius, range)| {
                                (radius - f32::from(r) / 32.0).abs() < 0.12 && b.pos.distance(at) <= range + 2.0
                            })
                        })
                        .min_by(|a, b| near(a).total_cmp(&near(b))),
                    _ => None,
                };
                let boss = || {
                    bodies
                        .iter()
                        .filter(|b| b.pos.distance(at) < 45.0)
                        .filter_map(|b| Some((b, boss_telegraph(b.script?, shape, at_feet(b))?)))
                        .min_by(|a, b| near(&a.0).total_cmp(&near(&b.0)))
                };
                let (owner, at_self, attack) = if let Some(b) = own {
                    (b.visual, true, None)
                } else if let Some(b) = lob() {
                    (b.visual, false, None)
                } else if let Some((b, name)) = boss() {
                    (b.visual, at_feet(b), Some(name))
                } else {
                    continue;
                };
                let d = u16_to_dir(dir);
                cues.entry(owner).or_default().push(Cue::Tele {
                    shape,
                    at_self,
                    windup: windup_ticks as f32 * gf_core::SIM_DT,
                    dir: d.y.atan2(d.x),
                    at,
                    attack,
                });
            }
            EntityKind::EnemyShot { .. } => shots.push(at),
            EntityKind::Enemy { .. } if !e.flags.contains(EntityFlags::BOSS) => adds.push(at),
            _ => {}
        }
    }
    for b in bodies.iter().filter(|b| b.script.is_some()) {
        let reach = |p: &&Vec2, r: f32| p.distance(b.pos) < b.radius + r;
        if shots.iter().filter(|p| reach(p, 2.5)).count() >= 5 {
            cues.entry(b.visual).or_default().push(Cue::Radial);
        }
        if adds.iter().filter(|p| reach(p, 5.0)).count() >= 2 {
            cues.entry(b.visual).or_default().push(Cue::Summon);
        }
    }
    let mut hits: HashMap<NetId, (f32, DamageType, bool)> = HashMap::new();
    let mut shattered = Vec::new();
    for ev in &link.fresh_events {
        match *ev {
            GameEvent::Hit { target, amount, element, crit, .. } => {
                let h = hits.entry(target).or_insert((0.0, element, false));
                h.0 += f32::from(amount);
                h.2 |= crit;
            }
            GameEvent::PlatesShattered { target } => shattered.push(target),
            _ => {}
        }
    }
    let view = cameras.single().ok().and_then(|(c, t)| Some((c, t, c.logical_viewport_size()?)));
    let on_screen = |p: Vec3, pad: f32| -> bool {
        let Some((cam, tf, size)) = view else { return true };
        world_to_screen(cam, tf, p).is_some_and(|s| {
            s.x > -pad * size.x && s.x < (1.0 + pad) * size.x && s.y > -pad * size.y && s.y < (1.0 + pad) * size.y
        })
    };

    for (mut ea, parts) in &mut enemies {
        let ea = &mut *ea;
        let Some(pe) = parts.player else { continue };
        let Ok((mut an, mut ap)) = animators.get_mut(pe) else { continue };
        let (an, ap) = (&mut *an, &mut *ap);
        let graph = an.model.anim.as_ref().map(|l| l.graph.clone());
        let mut attach = |ea: &mut EnemyAnim, on: bool| {
            if ea.culled == !on {
                return;
            }
            ea.culled = !on;
            match (on, &graph) {
                (true, Some(g)) => {
                    commands.entity(pe).insert(AnimationGraphHandle(g.clone()));
                }
                _ => {
                    commands.entity(pe).remove::<AnimationGraphHandle>();
                }
            }
        };

        // ── death: the corpse plays it ──
        if let Ok(mut corpse) = corpses.get_mut(ea.visual) {
            if !ea.dying {
                ea.dying = true;
                attach(ea, true);
                ap.resume_all();
                ea.queue.clear();
                ea.act = None;
                match ea.resolve(an, corpse.clip) {
                    Some(clip) => {
                        if log.0 && ea.loud() {
                            info!("anim E{} {}: {} -> {clip} (corpse)", ea.id.0, ea.name, an.base_name());
                            ea.logged = clip.clone();
                        }
                        an.set_base(ap, &clip, 1.0, 0.08, true);
                        let linger = match ea.tier {
                            EnemyClass::Swarm => 0.3,
                            EnemyClass::Elite => 1.6,
                            _ => 4.0,
                        };
                        corpse.hold = clip_len(an, &clip) + linger;
                    }
                    None => corpse.hold = 0.0,
                }
            }
            continue;
        }
        let Ok(mut v) = visuals.get_mut(ea.visual) else { continue };

        // ── LOD: an off-screen swarm stops evaluating its skeleton ──
        let swarm = ea.tier == EnemyClass::Swarm;
        attach(ea, !lod.0 || !swarm || on_screen(w3(v.shown, 0.5), 0.12));

        // ── ground speed (from the rendered motion) ──
        let raw = ea.last_pos.map_or(0.0, |l| l.distance(v.shown) / dt);
        ea.last_pos = Some(v.shown);
        ea.speed += (raw.min(30.0) - ea.speed) * (1.0 - (-10.0 * dt).exp());
        ea.moving = if ea.moving { ea.speed > 0.2 } else { ea.speed > 0.45 };

        // ── time freeze: the pose holds ──
        let frozen = v.flags.contains(EntityFlags::FROZEN);
        if frozen != ea.frozen {
            ea.frozen = frozen;
            if frozen {
                ap.pause_all();
            } else {
                ap.resume_all();
            }
        }
        // The first frame only learns the flags (no edges from an empty start).
        let (prev, flags) = (if ea.seen { ea.flags } else { v.flags }, v.flags);
        ea.seen = true;
        ea.flags = flags;
        if frozen {
            continue;
        }
        let rose = |f: EntityFlags| flags.contains(f) && !prev.contains(f);
        let fell = |f: EntityFlags| !flags.contains(f) && prev.contains(f);
        let my_cues = cues.remove(&ea.visual).unwrap_or_default();
        let hero = nearest_hero(v.pos);

        // ── the act in charge ends ──
        if let Some((act, start)) = &ea.act {
            let t = now - start;
            let over = match act.until {
                Until::Time(l) => t >= l,
                Until::Flag(f) => !v.flags.intersects(f) && t > 0.05,
            };
            if over {
                ea.act = None;
            }
        }
        if ea.spawn {
            ea.spawn = false;
            if let Some(a) = ea.once(an, "spawn", 1.0) {
                ea.interrupt(an, ap, Act { locked: 0.25, ..a }, now);
            }
        }

        // ── boss phases ──
        let boss_phase = match &ea.brain {
            Brain::Boss { phases, .. } => Some(phases.iter().rposition(|b| v.hp <= *b + 0.003).unwrap_or(0)),
            _ => None,
        };
        if let Some(idx) = boss_phase {
            if !ea.phase_known {
                ea.phase = idx;
                ea.phase_known = true;
            } else if idx > ea.phase {
                ea.phase = idx;
                let name = if idx >= 2 && an.has("phase3") { "phase3" } else { "phase2" };
                if an.has(name) {
                    let key = an.model.clip(name).and_then(|c| {
                        c.meta.event("burst").or_else(|| c.meta.event("peak")).or_else(|| c.meta.event("crack"))
                    });
                    let len = clip_len(an, name);
                    let act = Act {
                        clip: name.to_string(),
                        speed: 1.0,
                        seek: 0.0,
                        until: Until::Time(len),
                        locked: key.unwrap_or(len * 0.5) + 0.25,
                        face: hero.map(|h| angle_to(v.pos, h)),
                    };
                    ea.interrupt(an, ap, act, now);
                    if log.0 {
                        info!("anim E{} {}: phase {} -> {name}", ea.id.0, ea.name, idx + 1);
                    }
                }
            }
            // The Final Pour burns white; the crown spins (75°/s, 150°/s, twice that in a radial).
            v.hot = ea.phase >= 2 && an.has("phase3");
            let rate = match ea.phase {
                0 => 0.0,
                1 => 75.0f32,
                _ => 150.0,
            }
            .to_radians();
            let boost = if ea.playing("radial") { 2.0 } else { 1.0 };
            ea.crown = (ea.crown + rate * boost * dt).rem_euclid(TAU);
        }

        // ── plates (the anvil brute): wear cracks them in order, the shatter flings them (after
        // a wind-up or a charge: the charge's read comes first) ──
        let busy = flags.intersects(EntityFlags::WINDUP | EntityFlags::CHARGING);
        let mut shatter = false;
        if let Some(pl) = &mut ea.plates {
            if shattered.contains(&v.id) {
                pl.pending = true;
                pl.state = [1; 5];
                pl.breaking = f32::INFINITY;
            }
            if pl.pending && !busy && ea.act.as_ref().is_none_or(|(a, s)| now - s >= a.locked) {
                pl.pending = false;
                shatter = true;
            }
        }
        if let Some(pl) = &mut ea.plates {
            if let Some(&(amount, element, _)) = hits.get(&v.id)
                && flags.contains(EntityFlags::PLATED)
            {
                pl.wear += amount * if element == DamageType::Kinetic { 1.5 } else { 0.5 };
                for (i, at) in PLATE_CRACK_AT.iter().enumerate() {
                    if pl.wear / pl.plate_hp >= *at && pl.state[i] == 0 {
                        pl.state[i] = 1;
                    }
                }
            }
            if shatter {
                pl.state = [1; 5];
                pl.breaking = now + clip_len(an, "plates_break");
            }
            if !flags.contains(EntityFlags::PLATED) && now >= pl.breaking {
                pl.state = [2; 5];
            }
        }
        if shatter && let Some(a) = ea.once(an, "plates_break", 1.0) {
            let locked = clip_len(an, &a.clip) * 0.8;
            ea.interrupt(an, ap, Act { locked, ..a }, now);
        }

        // ── behaviour: wind-ups, attacks, casts ──
        let tele = my_cues.iter().find_map(|c| match *c {
            Cue::Tele { windup, dir, at, at_self, .. } => Some((windup, dir, at, at_self)),
            _ => None,
        });
        match ea.brain.clone() {
            Brain::Charger { windup } => {
                if rose(EntityFlags::WINDUP)
                    && let Some(a) = ea.once(an, "windup", 1.0)
                {
                    let w = tele.map_or(windup, |t| t.0).max(0.1);
                    let len = clip_len(an, &a.clip);
                    let act = Act {
                        speed: (len / w).clamp(0.3, 3.0),
                        until: Until::Flag(EntityFlags::WINDUP),
                        locked: w,
                        face: tele.map(|t| t.1),
                        ..a
                    };
                    ea.interrupt(an, ap, act, now);
                }
                if rose(EntityFlags::CHARGING) {
                    ea.queue.clear();
                    if let Some(a) = ea.once(an, "attack", 1.0) {
                        let locked = clip_len(an, &a.clip);
                        ea.interrupt(an, ap, Act { locked, ..a }, now);
                    }
                    if let Some(c) = ea.resolve(an, "charge") {
                        let speed = 1.0 + 0.3 * ea.seed;
                        ea.queue.push_back(Act {
                            clip: c,
                            speed,
                            seek: 0.0,
                            until: Until::Flag(EntityFlags::CHARGING),
                            locked: 0.5,
                            face: None,
                        });
                    }
                }
            }
            Brain::Caster { windup } => {
                if rose(EntityFlags::WINDUP) {
                    let w = tele.map_or(windup, |t| t.0).max(0.2);
                    let fire = an.model.clip("attack").and_then(|c| c.meta.event("beam_fire")).unwrap_or(0.2);
                    let fire_at = (w - fire).max(0.15);
                    let wl = clip_len(an, "windup");
                    ea.queue.clear();
                    let face = tele.map(|t| t.1);
                    if let Some(a) = ea.once(an, "windup", 1.0) {
                        let (len, speed) = if fire_at < wl { (fire_at, wl / fire_at) } else { (wl, 1.0) };
                        let act = Act { speed, until: Until::Time(len), locked: len, face, ..a };
                        ea.interrupt(an, ap, act, now);
                        if fire_at > wl
                            && let Some(c) = ea.resolve(an, "channel")
                        {
                            let hold = fire_at - wl;
                            ea.queue.push_back(Act {
                                clip: c,
                                speed: 1.0,
                                seek: 0.0,
                                until: Until::Time(hold),
                                locked: hold,
                                face,
                            });
                        }
                    }
                    if let Some(a) = ea.once(an, "attack", 1.0) {
                        let locked = clip_len(an, &a.clip) * 0.6;
                        ea.queue.push_back(Act { locked, face, ..a });
                    }
                }
                // The beam resolves: fire now if the channel ran long (or a stun cut it).
                if fell(EntityFlags::WINDUP) && (ea.playing("windup") || ea.playing("channel")) {
                    ea.queue.retain(|a| a.clip.starts_with("attack"));
                    ea.act = None;
                }
            }
            Brain::Bomber { fuse } => {
                if rose(EntityFlags::PRIMED) {
                    let f = tele.map_or(fuse, |t| t.0).max(0.2);
                    if let Some(a) = ea.once(an, "windup", 1.0) {
                        let len = clip_len(an, &a.clip);
                        let speed = (len / (f * 0.5)).max(1.0);
                        let act = Act { speed, until: Until::Time(len / speed), locked: f, ..a };
                        ea.interrupt(an, ap, act, now);
                    }
                    if let Some(c) = ea.resolve(an, "primed") {
                        ea.queue.push_back(Act {
                            clip: c,
                            speed: 1.0,
                            seek: 0.0,
                            until: Until::Flag(EntityFlags::PRIMED),
                            locked: f,
                            face: None,
                        });
                    }
                }
            }
            Brain::Lobber { .. } => {
                if let Some((w, _, at, false)) = tele
                    && let Some(a) = ea.once(an, "windup", 1.0)
                {
                    // The glob leaves early in the telegraph and flies for the rest of it.
                    let wind = (w * 0.45).clamp(0.25, 0.6);
                    let len = clip_len(an, &a.clip);
                    let face = Some(angle_to(v.pos, at));
                    let act = Act { speed: len / wind, until: Until::Time(wind), locked: wind, face, ..a };
                    ea.interrupt(an, ap, act, now);
                    if let Some(t) = ea.once(an, "attack", 1.0) {
                        let locked = clip_len(an, &t.clip) * 0.5;
                        ea.queue.push_back(Act { locked, face, ..t });
                    }
                }
            }
            Brain::Support { interval } => {
                if ea.next_cast.is_infinite() {
                    ea.next_cast = now + interval * (0.3 + ea.seed);
                }
                // Its own shield rising marks the pulse; between those it keeps the sim's rhythm.
                let pulse =
                    now >= ea.next_cast || (rose(EntityFlags::SHIELDED) && now >= ea.next_cast - interval * 0.5);
                if pulse {
                    ea.next_cast = now + interval;
                    if ea.free(now)
                        && hero.is_some_and(|h| h.distance(v.pos) < 18.0)
                        && let Some(a) = ea.once(an, "cast", 1.0)
                    {
                        let locked = clip_len(an, &a.clip) * 0.7;
                        ea.interrupt(an, ap, Act { locked, ..a }, now);
                    }
                }
            }
            Brain::Boss { .. } => {
                if ea.free(now)
                    && let Some((name, cue)) = boss_attack(ea, &my_cues)
                    && let Some(clip) = ea.resolve(an, &name)
                {
                    let meta = an.model.clip(&clip).map(|c| c.meta.clone()).unwrap_or_default();
                    let len = clip_len(an, &clip);
                    let key = meta
                        .event("impact")
                        .or_else(|| meta.event("release"))
                        .or_else(|| meta.events.iter().map(|(_, t)| *t).reduce(f32::min));
                    let (mut speed, mut seek, mut face) = (1.0, 0.0, hero.map(|h| angle_to(v.pos, h)));
                    match cue {
                        Cue::Tele { windup, dir, shape, .. } => {
                            // The clip's impact lands with the telegraph (pools: the fling comes first).
                            let land = if name == "pools" { windup * 0.6 } else { windup };
                            if let Some(k) = key.filter(|k| *k > 0.05) {
                                speed = (k / land.max(0.1)).clamp(0.6, 1.8);
                            }
                            if matches!(shape, TeleShape::Cone { .. } | TeleShape::Line { .. }) {
                                face = Some(dir);
                            }
                        }
                        // The volley and the adds are already out: start on their key.
                        Cue::Radial | Cue::Summon => {
                            let k = meta.event("release").or_else(|| meta.event("spawn")).unwrap_or(0.0);
                            seek = (k - 0.1).max(0.0);
                        }
                    }
                    let locked = key.map_or(len * 0.5, |k| ((k - seek) / speed).max(0.0) + 0.15);
                    let act = Act { clip, speed, seek, until: Until::Time((len - seek) / speed), locked, face };
                    if log.0 {
                        info!(
                            "anim E{} {}: {} -> {} (attack, phase {}, x{speed:.2})",
                            ea.id.0,
                            ea.name,
                            an.base_name(),
                            act.clip,
                            ea.phase + 1
                        );
                        ea.logged = act.clip.clone();
                    }
                    ea.interrupt(an, ap, act, now);
                }
            }
            Brain::Melee => {}
        }

        // ── a bite or a bash on a hero in reach ──
        let melee = matches!(ea.brain, Brain::Melee | Brain::Support { .. });
        if melee
            && ea.act.is_none()
            && now >= ea.next_contact
            && let Some(h) = hero.filter(|h| h.distance(v.pos) < v.radius + 0.95)
        {
            ea.next_contact = now + 0.8 + 0.7 * ea.seed;
            let face = Some(angle_to(v.pos, h));
            if matches!(ea.brain, Brain::Support { .. })
                && let Some(w) = ea.once(an, "windup", 1.6)
            {
                ea.interrupt(an, ap, Act { face, locked: 0.3, ..w }, now);
                if let Some(a) = ea.once(an, "attack", 1.0) {
                    ea.queue.push_back(Act { face, ..a });
                }
            } else if let Some(a) = ea.once(an, "attack", 1.0 + 0.2 * ea.seed) {
                ea.interrupt(an, ap, Act { face, ..a }, now);
            }
        }

        // ── hit reactions (throttled; bosses only flinch when idle) ──
        if let Some(&(_, _, crit)) = hits.get(&v.id) {
            // A boss takes a stream of hits: only a crit rocks it, now and then (its rim flashes
            // for the rest).
            let gap = match ea.tier {
                EnemyClass::Swarm => 0.45,
                EnemyClass::Elite => 1.1,
                _ if crit => 7.0,
                _ => f32::INFINITY,
            };
            let idle = (ea.act.is_none() || ea.playing("hit")) && ea.queue.is_empty();
            if now - ea.last_hit >= gap
                && idle
                && let Some(a) = ea.once(an, "hit", 1.0)
            {
                ea.last_hit = now;
                ea.interrupt(an, ap, a, now);
            }
        }

        // ── the next queued act, else locomotion ──
        if ea.act.is_none()
            && let Some(next) = ea.queue.pop_front()
        {
            ea.begin(an, ap, next, now);
        }
        v.face_override = match &ea.act {
            Some((a, _)) => a.face,
            // A boss squares up to its target; the rest face where they go.
            None if ea.boss() => hero.map(|h| angle_to(v.pos, h)),
            None => None,
        };
        if ea.act.is_none() {
            let charging = flags.contains(EntityFlags::CHARGING);
            let (clip, rate) = if charging && an.has("charge") {
                ("charge".to_string(), 1.0)
            } else if ea.moving {
                // The move loop covers `move_cycle_m` per cycle: its rate follows the ground speed.
                let clip = ea.resolve(an, "move").unwrap_or_else(|| "move".into());
                let len = clip_len(an, &clip);
                let cycle = an.model.clip(&clip).and_then(|c| c.meta.move_cycle).unwrap_or(len * 3.0);
                let rate = (len * ea.speed / cycle.max(0.05)).clamp(0.3, 3.0);
                (clip, rate)
            } else {
                (ea.resolve(an, "idle").unwrap_or_else(|| "idle".into()), 0.92 + 0.16 * ea.seed)
            };
            let fade = if ea.boss() { 0.35 } else { 0.15 };
            // A horde's loops start at scattered points so it never marches in step.
            let seek = clip_len(an, &clip) * ea.seed;
            an.set_base_at(ap, &clip, rate, fade, false, seek);
        }
        if log.0 && ea.loud() && ea.logged != an.base_name() {
            info!(
                "anim E{} {}: {} -> {} (speed {:.1} m/s, phase {})",
                ea.id.0,
                ea.name,
                if ea.logged.is_empty() { "-" } else { ea.logged.as_str() },
                an.base_name(),
                ea.speed,
                ea.phase + 1
            );
            ea.logged = an.base_name().to_string();
        }
    }
}

/// Pose work the clips leave to the client, after the animation and before transforms propagate:
/// the Slag King's crown spin and the anvil brute's plate states (sidecar `phase_switch`,
/// `plate_states`).
fn pose_enemies(mut q: Query<(&mut EnemyAnim, &ModelParts)>, mut tfs: Query<&mut Transform>) {
    for (mut ea, parts) in &mut q {
        if ea.culled {
            continue;
        }
        if ea.crown != 0.0
            && let Some(j) = parts.node("crown_spin")
            && let Ok(mut tf) = tfs.get_mut(j)
        {
            tf.rotation *= Quat::from_rotation_y(ea.crown);
        }
        let Some(pl) = &mut ea.plates else { continue };
        let nodes = pl.nodes.get_or_insert_with(|| {
            PLATE_NAMES
                .iter()
                .map(|p| (parts.node(&format!("plate_{p}")), parts.node(&format!("plate_{p}_crk"))))
                .collect()
        });
        for (i, (intact, cracked)) in nodes.iter().enumerate() {
            let (a, b) = match pl.state[i] {
                0 => (1.0, 0.001),
                1 => (0.001, 1.0),
                _ => (0.001, 0.001),
            };
            for (e, s) in [(intact, a), (cracked, b)] {
                if let Some(e) = e
                    && let Ok(mut tf) = tfs.get_mut(*e)
                {
                    tf.scale = Vec3::splat(s);
                }
            }
        }
    }
}

// ───────────────────────────── enemy gallery (QA) ─────────────────────────────

/// `--enemy-gallery [N]`: QA. Every enemy look of the run's biome stands in one row 3 m below the
/// local hero (client side only: the sim never sees it), swarms first, then elites, the
/// mini-boss and the boss, facing the camera three-quarters. All play the same clip of
/// [`ENEMY_GALLERY_CLIPS`] for [`GALLERY_PERIOD`] s (one-shots held on their key pose), starting
/// at the N-th; a look without that clip idles. Pin the view with `GF_CAM_AT`, zoom with
/// `GF_QA_ZOOM`.
#[derive(Resource)]
pub struct EnemyGallery {
    pub start: Option<usize>,
    spawned: bool,
    shown: String,
}

/// The clips the enemy gallery steps through (the shared set, then the extras).
const ENEMY_GALLERY_CLIPS: [&str; 16] = [
    "idle",
    "move",
    "windup",
    "attack",
    "hit",
    "death",
    "spawn",
    "primed",
    "charge",
    "plates_break",
    "channel",
    "cast",
    "phase2",
    "idle_p2",
    "radial",
    "summon",
];

/// One look in the enemy gallery.
#[derive(Component)]
struct GalleryItem;

fn enemy_gallery(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    server: Res<AssetServer>,
    mut gallery: ResMut<EnemyGallery>,
    mut models: ResMut<crate::models::Models>,
    items: Query<&ModelParts, With<GalleryItem>>,
    mut animators: Query<(&mut Animator, &mut AnimationPlayer)>,
) {
    let Some(from) = gallery.start else { return };
    let Some(world) = link.latest.as_deref() else { return };
    let Some(me) = link.me() else { return };
    let db = &cfg.content;
    if !gallery.spawned {
        let Some(biome) = db.biomes.try_get(world.run.biome) else { return };
        let mut defs: Vec<&gf_content::EnemyDef> = db.enemies.iter().filter(|d| d.biome == biome.key).collect();
        defs.sort_by_key(|d| d.class.index());
        let mut looks = Vec::new();
        for d in defs {
            for look in models.looks(crate::models::ModelKind::Enemy, &d.key, &server) {
                looks.push(look);
            }
        }
        let ready: Vec<_> =
            looks.iter().filter_map(|k| models.get(crate::models::ModelKind::Enemy, k, &server)).collect();
        if ready.len() < looks.len() {
            return;
        }
        gallery.spawned = true;
        let origin = me.mover.pos + Vec2::new(-4.0, -3.0);
        let root = commands.spawn((Transform::from_translation(w3(origin, 0.0)), Visibility::default())).id();
        let mut x = 0.0;
        for model in &ready {
            let (lo, hi) = model.meta.bounds.unwrap_or((Vec3::splat(-0.5), Vec3::splat(0.5)));
            let half = (hi.x - lo.x).max(hi.z - lo.z) * 0.5;
            x += half;
            let tf = Transform::from_translation(Vec3::new(x, 0.0, 0.0)).with_rotation(Quat::from_rotation_y(-0.55));
            let e = crate::models::spawn_model(&mut commands, root, model, crate::models::Skin::FOE, tf);
            commands.entity(e).insert(GalleryItem);
            info!("enemy gallery: {} at x {:.1} (sim {:.1}, {:.1})", model.key, x, origin.x + x, origin.y);
            x += half + 0.35;
        }
        return;
    }
    let now = time.elapsed_secs();
    let clip = ENEMY_GALLERY_CLIPS[(from + (now / GALLERY_PERIOD) as usize) % ENEMY_GALLERY_CLIPS.len()];
    let fresh = gallery.shown != clip;
    if fresh {
        info!("enemy gallery: {clip} at {now:.1}s");
        gallery.shown = clip.to_string();
    }
    for parts in &items {
        let Some((mut an, mut ap)) = parts.player.and_then(|e| animators.get_mut(e).ok()) else { continue };
        let name = if an.has(clip) { clip } else { "idle" };
        if !fresh && an.base_name() == name {
            continue;
        }
        let Some(c) = an.model.clip(name) else { continue };
        let (node, looping) = (c.node, c.meta.looping);
        let key = c.meta.events.iter().map(|(_, t)| *t).reduce(f32::min).unwrap_or(c.duration * 0.45);
        an.set_base(&mut ap, name, 1.0, 0.1, true);
        if !looping && let Some(a) = ap.animation_mut(node) {
            a.set_seek_time(key).pause();
        }
    }
}

/// `--anim-gallery [N]` / `--enemy-gallery [N]`: the clip to start from.
fn gallery_start(flag: &str, env: &str) -> usize {
    let args: Vec<String> = std::env::args().collect();
    let arg = args.iter().position(|a| a == flag).and_then(|i| args.get(i + 1)).and_then(|v| v.parse().ok());
    arg.or_else(|| std::env::var(env).ok()?.parse().ok()).unwrap_or(0)
}

pub fn build(app: &mut App) {
    let flag = |arg: &str, env: &str| std::env::args().any(|a| a == arg) || std::env::var(env).is_ok_and(|v| v != "0");
    let heroes = flag("--anim-gallery", "GODFORGE_ANIM_GALLERY");
    let enemies = flag("--enemy-gallery", "GODFORGE_ENEMY_GALLERY");
    app.insert_resource(AnimLog(flag("--anim-log", "GODFORGE_ANIM_LOG")))
        .insert_resource(EnemyLod(!std::env::var("GODFORGE_ENEMY_LOD").is_ok_and(|v| v == "0")))
        .insert_resource(AnimGallery(heroes.then(|| gallery_start("--anim-gallery", "GODFORGE_ANIM_GALLERY"))))
        .insert_resource(EnemyGallery {
            start: enemies.then(|| gallery_start("--enemy-gallery", "GODFORGE_ENEMY_GALLERY")),
            spawned: false,
            shown: String::new(),
        })
        .add_systems(
            Update,
            (drive_heroes, drive_enemies, enemy_gallery, tick_animators).chain().in_set(ClientSet::Presentation),
        )
        .add_systems(
            PostUpdate,
            pose_enemies
                .after(gf_engine::bevy::app::AnimationSystems)
                .before(gf_engine::bevy::transform::TransformSystems::Propagate),
        );
}
