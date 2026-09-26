//! Weapon VFX (VFX_STYLE §6-11, lane W): every projectile style's body and trail, muzzle flashes
//! per chassis, charge-up cues, beams, melee smears, the modifier reads (pierce, ricochet, fork,
//! homing, chain), layered explosions, hit punctuation per element and enemy shots with their
//! impacts. Drawn by the batched engine in [`crate::fx`]; this module only decides what to draw.
//!
//! * [`recipes`]: the recipes, pure functions on [`Fx`] (shared with the gallery).
//! * [`shots`]: projectile bodies, trails and in-flight emitters on a carrier entity.
//! * [`gallery`]: `--weapon-gallery`, every chassis firing in a labelled grid (QA captures).
//!
//! What a player's weapon looks like comes from its replicated `WeaponBuild`, compiled on the
//! client exactly as the sim compiles it (chassis mods + equipped parts), so a part that adds
//! pierce, ricochet, homing or a beam changes the read.

pub mod gallery;
pub mod recipes;
pub mod shots;

use crate::camera::w3;
use crate::fx::api::F;
use crate::fx::{Arc, BodyMesh, Profile, Sweep, strip};
use crate::fx::{Class, Fx, FxBody, FxRing, FxSprite, Layer, Owner, Play, Ramp, seq};
use crate::input::InputState;
use crate::models::HeroGear;
use crate::net::Link;
use crate::scene::{PlayerRig, SceneIndex, Visual};
use crate::{ClientConfig, ClientSet};
use gf_content::ContentDb;
use gf_core::aim::AimMode;
use gf_core::forge::WeaponBuild;
use gf_core::ids::NetId;
use gf_core::modifier::Modifier;
use gf_core::weapon::{FireKind, compile};
use gf_engine::prelude::*;
use gf_net::quant::u16_to_dir;
use gf_net::{EntityFlags, EntityKind, GameEvent, WorldSnapshot};
use recipes::{Blast, Contact, Look, Shot, Strike, d3};
use shots::{ShotFx, ShotSpec, Stuck, Variant};
use std::collections::HashMap;
use std::f32::consts::PI;

/// Where a player's weapon is this frame.
#[derive(Clone, Copy, Debug)]
pub struct Hand {
    /// The weapon's `muzzle` socket (else the greybox gun's tip).
    pub muzzle: Vec3,
    pub feet: Vec3,
    /// Aim (flat, unit).
    pub dir: Vec3,
    /// A gauntlet pair's fists (L, R).
    pub fists: [Option<Vec3>; 2],
    pub alive: bool,
}

#[derive(Clone, Copy, Debug, Default)]
struct SlotState {
    /// Highest charge of the current draw and when it was last seen.
    peak: f32,
    peak_at: f32,
    /// Charge of the last release (the shot it made gets a wider trail at full charge).
    release: f32,
    release_at: f32,
    full_at: Option<f32>,
    shots: u32,
    last_shot: f32,
    motes: f32,
    swing_next: f32,
    swing_until: f32,
    swings: u32,
    last_tick: u32,
    beam: [f32; 3],
}

/// A shot that left the field (explosion attribution, enemy shot impacts, stuck arrows).
#[derive(Clone, Copy, Debug)]
struct Gone {
    at: Vec3,
    spec: ShotSpec,
    time: f32,
}

/// Per-player weapon looks and the arms module's memory.
#[derive(Resource, Default)]
pub struct Arsenal {
    builds: [Option<WeaponBuild>; 4],
    pub looks: [Option<Look>; 4],
    pub hands: [Option<Hand>; 4],
    slots: [SlotState; 4],
    gone: Vec<Gone>,
    memo: HashMap<Entity, (Vec3, Vec3, ShotSpec)>,
    last_star: HashMap<NetId, f32>,
    splits: Vec<(Vec3, f32)>,
}

/// An orbiting blade (the `Orbit` modifier): its circular smear follows it round its owner.
#[derive(Component)]
struct BladeFx {
    slot: u8,
    ramp: Ramp,
    owner: Owner,
    last: Option<f32>,
    sign: f32,
}

pub fn build(app: &mut App) {
    app.init_resource::<Arsenal>().add_systems(
        Update,
        (refresh, track, events, dress, hold, orbit, unstick)
            .chain()
            .after(crate::vfx::spawn_from_events)
            .in_set(ClientSet::Presentation),
    );
    gallery::build(app);
}

/// Compile a build the way the sim does (chassis mods, then each equipped part at its rarity).
pub fn look_of(db: &ContentDb, build: &WeaponBuild) -> Look {
    let Some(def) = db.chassis.try_get(build.chassis.0) else { return Look::fallback() };
    let mut mods: Vec<Modifier> = def.mods.clone();
    for (_, part) in build.equipped() {
        if db.parts.try_get(part.part.0).is_some() {
            mods.extend(db.part_mods(part.part, part.rarity));
        }
    }
    let p = compile(&def.stats, mods.iter());
    Look {
        key: def.key.clone(),
        fire: p.fire,
        style: p.style,
        element: p.element,
        rate: p.fire_rate,
        base_rate: def.stats.fire_rate,
        range: p.range,
        speed: p.speed,
        spread: p.spread_deg,
        projectiles: p.projectiles,
        knockback: p.knockback,
        pierce: p.pierce,
        ricochet: p.ricochet.is_some(),
        fork: p.fork.is_some(),
        chain: p.chain.is_some(),
        homing: p.homing > 0.0,
        splash: p.splash.or(p.explode).map_or(0.0, |s| s.radius),
        beam_width: p.beam_width.unwrap_or(0.5),
        charge_time: p.charge_time,
    }
}

/// Refresh each player's look (when its build changes) and hand (every frame).
#[allow(clippy::too_many_arguments)]
fn refresh(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    input: Option<Res<InputState>>,
    index: Res<SceneIndex>,
    rigs: Query<&PlayerRig>,
    gears: Query<&HeroGear>,
    globals: Query<&GlobalTransform>,
    mut arsenal: ResMut<Arsenal>,
) {
    let Some(world) = link.latest.as_deref() else { return };
    let arsenal = &mut *arsenal;
    let mut seen = [false; 4];
    for p in &world.players {
        let s = p.slot as usize % 4;
        seen[s] = true;
        if arsenal.builds[s].as_ref() != Some(&p.weapon) {
            arsenal.builds[s] = Some(p.weapon.clone());
            arsenal.looks[s] = Some(look_of(&cfg.content, &p.weapon));
        }
        let manual = link.slot == Some(p.slot) && input.as_ref().is_some_and(|i| i.aim_mode == AimMode::Manual);
        let aim = match (&input, manual) {
            (Some(i), true) => i.aim_dir,
            _ => u16_to_dir(p.aim),
        };
        let dir = d3(aim).normalize_or(Vec3::X);
        let rig = index.players.get(s).copied().flatten().and_then(|e| rigs.get(e).ok());
        let shown = rig.map_or(p.mover.pos, |r| r.shown);
        let feet = w3(shown, p.height);
        let gear = rig.and_then(|r| r.model()).and_then(|m| gears.get(m).ok());
        let muzzle = gear
            .and_then(|g| g.muzzle.filter(|_| !g.greybox_gun))
            .and_then(|m| globals.get(m).ok())
            .map(|g| g.translation())
            .unwrap_or(feet + dir * 1.05 + Vec3::Y * 1.05);
        let fist = |i: usize| gear.and_then(|g| g.fist[i]).and_then(|f| globals.get(f).ok()).map(|g| g.translation());
        arsenal.hands[s] = Some(Hand { muzzle, feet, dir, fists: [fist(0), fist(1)], alive: p.life.is_alive() });
    }
    for (s, seen) in seen.iter().enumerate() {
        if !seen {
            arsenal.hands[s] = None;
        }
    }
}

fn flat(v: Vec3) -> Vec2 {
    Vec2::new(v.x, v.z)
}

/// Shots in flight: emitters, the lob, the bounce, the harpoon rope; and shots that left.
#[allow(clippy::too_many_arguments)]
fn track(
    mut commands: Commands,
    time: Res<Time>,
    link: Res<Link>,
    mut arsenal: ResMut<Arsenal>,
    mut shots: Query<(Entity, &GlobalTransform, &mut ShotFx, &mut Transform)>,
    mut removed: RemovedComponents<ShotFx>,
    visuals: Query<&Visual>,
    mut fx: Fx,
) {
    let dt = time.delta_secs();
    let now = time.elapsed_secs();
    let arsenal = &mut *arsenal;
    for (e, g, mut s, mut tf) in &mut shots {
        let pos = g.translation();
        let rope = s.slot.and_then(|sl| arsenal.hands[sl as usize % 4]).map(|h| h.muzzle);
        let key = 0x4200_0000 | (e.to_bits() as u32 & 0x00FF_FFFF);
        let lob = shots::tick(&mut fx, &mut s, pos, dt, rope, key);
        if s.spec.lob > 0.0 {
            tf.translation.y = lob;
        }
        arsenal.memo.insert(e, (pos, s.heading, s.spec));
    }
    let players: Vec<Vec2> =
        link.latest.as_deref().map(|w| w.players.iter().map(|p| p.mover.pos).collect()).unwrap_or_default();
    for e in removed.read() {
        let Some((at, heading, spec)) = arsenal.memo.remove(&e) else { continue };
        arsenal.gone.push(Gone { at, spec, time: now });
        let p = Vec2::new(at.x, -at.z);
        if spec.enemy {
            let landed = players.iter().any(|q| q.distance(p) < 1.5);
            recipes::enemy_impact(&mut fx, at, heading, landed);
            continue;
        }
        let near =
            visuals.iter().any(|v| matches!(v.kind, EntityKind::Enemy { .. }) && v.shown.distance(p) < v.radius + 0.6);
        if near {
            shots::stuck_body(&mut commands, at, heading, &spec);
        } else {
            shots::fizzle(&mut fx, at, &spec);
        }
    }
    arsenal.gone.retain(|g| now - g.time < 0.3);
    if arsenal.memo.len() > 4096 {
        arsenal.memo.clear();
    }
}

/// Who made an explosion: a shot that just ended there, else a melee weapon's splash in reach.
fn attribute(a: &Arsenal, at: Vec3, me: Option<u8>) -> (Owner, Blast) {
    let d = |g: &Gone| flat(g.at).distance(flat(at));
    if let Some(g) = a.gone.iter().filter(|g| !g.spec.enemy && d(g) < 1.8).min_by(|x, y| d(x).total_cmp(&d(y))) {
        use gf_core::weapon::ProjectileStyle as S;
        let blast = match (g.spec.style, g.spec.variant) {
            (_, Variant::VoidHeart) => Blast::Singularity,
            (_, Variant::Dial) => Blast::Dial,
            (S::Shell, _) | (_, Variant::Iron) => Blast::Shell,
            (S::Boulder, _) => Blast::Boulder,
            _ => Blast::Plain,
        };
        return (g.spec.owner, blast);
    }
    for (s, hand) in a.hands.iter().enumerate() {
        let (Some(h), Some(l)) = (hand, &a.looks[s]) else { continue };
        if l.fire == FireKind::Melee && flat(h.feet).distance(flat(at)) < l.range + 0.8 {
            let blast = if l.key == "titanfall_hammer" { Blast::Hammer } else { Blast::Plain };
            return (Owner::of_slot(s as u8, me), blast);
        }
    }
    (Owner::Mine, Blast::Plain)
}

/// Shots, hits, explosions and chain hops.
#[allow(clippy::too_many_arguments)]
fn events(
    time: Res<Time>,
    link: Res<Link>,
    index: Res<SceneIndex>,
    visuals: Query<&Visual>,
    mut arsenal: ResMut<Arsenal>,
    claims: Res<crate::vfx::EventClaims>,
    mut fx: Fx,
) {
    if link.fresh_events.is_empty() {
        return;
    }
    let Some(world) = link.latest.clone() else { return };
    let me = link.slot;
    let now = time.elapsed_secs();
    let arsenal = &mut *arsenal;
    if arsenal.last_star.len() > 512 {
        arsenal.last_star.retain(|_, t| now - *t < 0.5);
    }
    for (i, ev) in link.fresh_events.iter().enumerate() {
        // Lane A drew this one as part of a synergy or an ability set piece.
        if claims.claimed(i) {
            continue;
        }
        match *ev {
            GameEvent::Shot { slot, dir, .. } => {
                let s = slot as usize % 4;
                let Some(hand) = arsenal.hands[s] else { continue };
                let look = arsenal.looks[s].clone().unwrap_or_else(Look::fallback);
                let st = &mut arsenal.slots[s];
                let charge = if look.fire == FireKind::Charge && now - st.peak_at < 0.35 { st.peak } else { 0.0 };
                st.peak = 0.0;
                st.full_at = None;
                st.release = charge;
                st.release_at = now;
                let since = now - st.last_shot;
                st.last_shot = now;
                let n = st.shots;
                st.shots = st.shots.wrapping_add(1);
                let d = d3(u16_to_dir(dir)).normalize_or(hand.dir);
                let shot = Shot {
                    look: &look,
                    at: hand.muzzle,
                    feet: hand.feet,
                    dir: d,
                    owner: Owner::of_slot(slot, me),
                    charge,
                    n,
                    since,
                };
                recipes::muzzle(&mut fx, &shot);
            }
            GameEvent::Hit { target, crit, precision, element, source, .. } => {
                let Some(v) = index.entity(target).and_then(|e| visuals.get(e).ok()) else { continue };
                let owner = Owner::of_source(source, me);
                let ramp = if owner == Owner::Enemy { Ramp::EnemyShot } else { Ramp::of(element) };
                // Several hits on one target inside 0.08 s share one star (VFX_STYLE §10.1).
                let recent = arsenal.last_star.get(&target).is_some_and(|t| now - *t < 0.08);
                let repeat = recent && !crit && !precision;
                if !repeat {
                    arsenal.last_star.insert(target, now);
                }
                let look = if source < 4 { arsenal.looks[source as usize].as_ref() } else { None };
                let from = if source < 12 { hand_of(&world, source % 4) } else { None };
                let dir = from.map_or(Vec3::ZERO, |f| d3(v.shown - f).normalize_or_zero());
                let contact = Contact {
                    at: w3(v.shown, v.hit_height),
                    dir,
                    ramp,
                    owner,
                    body: v.radius,
                    crit,
                    precision,
                    look,
                    plated: v.flags.contains(EntityFlags::PLATED),
                    repeat,
                };
                recipes::contact(&mut fx, &contact);
            }
            GameEvent::Explosion { pos, radius_q, element } => {
                let at = w3(pos.to_vec2(), 0.0);
                let (owner, blast) = attribute(arsenal, at, me);
                recipes::explosion(&mut fx, Ramp::of(element), at, radius_q as f32 / 32.0, blast, owner);
            }
            GameEvent::Arc { from, to, element } => {
                // No source rides on the event: the chain belongs to the one chain weapon in the
                // party when there is one, else it reads as your own.
                let chains: Vec<usize> =
                    (0..4).filter(|&s| arsenal.looks[s].as_ref().is_some_and(|l| l.chain)).collect();
                let owner = match chains.as_slice() {
                    [s] => Owner::of_slot(*s as u8, me),
                    _ => Owner::Mine,
                };
                let height = |q: gf_net::quant::QPos| {
                    let p = q.to_vec2();
                    visuals
                        .iter()
                        .filter(|v| matches!(v.kind, EntityKind::Enemy { .. }) && v.shown.distance(p) < 0.6)
                        .map(|v| v.hit_height)
                        .next()
                        .unwrap_or(1.0)
                };
                let (a, b) = (w3(from.to_vec2(), height(from)), w3(to.to_vec2(), height(to)));
                recipes::chain(&mut fx, a, b, Ramp::of(element), owner);
            }
            _ => {}
        }
    }
}

fn hand_of(world: &WorldSnapshot, slot: u8) -> Option<Vec2> {
    world.players.iter().find(|p| p.slot == slot).map(|p| p.mover.pos)
}

/// Dress new replicated visuals: projectiles, enemy shots, turrets and orbiting blades.
#[allow(clippy::too_many_arguments)]
fn dress(
    mut commands: Commands,
    time: Res<Time>,
    link: Res<Link>,
    mut arsenal: ResMut<Arsenal>,
    added: Query<(Entity, &Visual), Added<Visual>>,
    mut fx: Fx,
) {
    let me = link.slot;
    let now = time.elapsed_secs();
    let arsenal = &mut *arsenal;
    arsenal.splits.retain(|(_, t)| now - *t < 0.1);
    for (e, v) in &added {
        match v.kind {
            EntityKind::Projectile { style, element, owner, radius_q } => {
                let vel = v.motion.map_or(Vec2::ZERO, |m| m.vel.to_vec2());
                let heading = d3(vel).normalize_or(d3(Vec2::from_angle(v.facing)));
                let slot = (owner < 12).then_some(owner % 4);
                let look = slot.and_then(|s| arsenal.looks[s as usize].clone());
                let ramp = Ramp::of(element);
                let key = look.as_ref().map_or("", |l| l.key.as_str());
                let mut spec = ShotSpec::new(
                    style,
                    ramp,
                    Owner::of_source(owner, me),
                    radius_q as f32 / 32.0,
                    vel.length(),
                    heading,
                );
                spec.variant = Variant::of(style, key, ramp);
                spec.range = look.as_ref().map_or(12.0, |l| l.range);
                spec.homing = look.as_ref().is_some_and(|l| l.homing);
                if spec.variant == Variant::Iron {
                    spec.lob = 1.4;
                }
                let born = w3(v.shown, v.lift);
                if let Some(s) = slot {
                    let st = arsenal.slots[s as usize];
                    if owner < 4 && now - st.release_at < 0.35 {
                        spec.charged = st.release;
                    }
                    // A fork or split child is born away from its owner (VFX_STYLE §9 "Fork").
                    if owner < 8
                        && let Some(h) = arsenal.hands[s as usize]
                        && flat(h.feet).distance(flat(born)) > 2.4
                    {
                        spec.scale = 0.8;
                        if !arsenal.splits.iter().any(|(p, _)| p.distance(born) < 0.6) {
                            arsenal.splits.push((born, now));
                            split_star(&mut fx, born, ramp, spec.owner);
                        }
                    }
                }
                // A turret's shot flashes at the turret.
                if (8..12).contains(&owner) {
                    fx.muzzle(style, element, born + heading * 0.4, heading, spec.owner);
                }
                let carrier = commands.spawn((Transform::default(), Visibility::default(), ChildOf(e))).id();
                shots::dress(&mut commands, carrier, &spec, slot);
            }
            EntityKind::EnemyShot { radius_q } => {
                let vel = v.motion.map_or(Vec2::ZERO, |m| m.vel.to_vec2());
                let heading = d3(vel).normalize_or(d3(Vec2::from_angle(v.facing)));
                let r = (radius_q as f32 / 32.0).max(0.1) * 1.3;
                let spec = ShotSpec::enemy(r, vel.length(), heading);
                recipes::enemy_spawn_flash(&mut fx, w3(v.shown, v.lift), r);
                let carrier = commands.spawn((Transform::default(), Visibility::default(), ChildOf(e))).id();
                shots::dress(&mut commands, carrier, &spec, None);
            }
            EntityKind::Turret { owner } => {
                let o = Owner::of_slot(owner, me);
                commands.entity(e).insert(FxRing::hem(0.62, Ramp::ZoneGold, o));
                let core = FxSprite::new(seq::BODY_CHARGE_CORE.nth(2), 0.4, Ramp::Kinetic, o);
                commands.spawn((
                    FxSprite { play: Play::Frame(0), layer: Layer::Front, ..core },
                    Transform::from_xyz(0.0, 0.72, 0.0),
                    Visibility::default(),
                    ChildOf(e),
                ));
            }
            EntityKind::Blade { owner } => {
                let slot = owner % 4;
                let ramp = arsenal.looks[slot as usize].as_ref().map_or(Ramp::Kinetic, |l| l.ramp());
                let o = Owner::of_slot(slot, me);
                let mut body = FxBody::new(BodyMesh::DiscBlade, ramp, o, 1.2).spin(Vec3::new(0.0, 18.0, 0.0));
                body.align = false;
                commands.spawn((
                    body,
                    BladeFx { slot, ramp, owner: o, last: None, sign: 1.0 },
                    Transform::default(),
                    Visibility::default(),
                    ChildOf(e),
                ));
            }
            _ => {}
        }
    }
}

/// The parent of a fork flashes a split star; its children peel off smaller.
fn split_star(fx: &mut Fx, at: Vec3, ramp: Ramp, owner: Owner) {
    let rot = fx.rand() * PI;
    fx.sprite(seq::PETAL_CROSS, at)
        .radius(0.45)
        .ramp(ramp)
        .rot(rot)
        .play(Play::Life)
        .life(5.0 * F)
        .erode(0.5, 1.0)
        .pull(0.5)
        .ink_backed()
        .layer(Layer::Front)
        .owner(owner)
        .emit();
}

/// Held weapons, every frame: charge cues, beams and the melee cadence.
fn hold(time: Res<Time>, link: Res<Link>, visuals: Query<&Visual>, mut arsenal: ResMut<Arsenal>, mut fx: Fx) {
    let Some(world) = link.latest.as_deref() else { return };
    let now = time.elapsed_secs();
    let dt = time.delta_secs();
    let me = link.slot;
    let arsenal = &mut *arsenal;
    for p in &world.players {
        let s = p.slot as usize % 4;
        let (Some(hand), Some(look)) = (arsenal.hands[s], arsenal.looks[s].as_ref()) else { continue };
        let owner = Owner::of_slot(p.slot, me);
        let st = &mut arsenal.slots[s];
        if !hand.alive {
            st.peak = 0.0;
            st.full_at = None;
            continue;
        }
        match look.fire {
            FireKind::Charge => {
                if p.charge > 0.02 {
                    st.peak = st.peak.max(p.charge);
                    st.peak_at = now;
                    if p.charge >= 0.999 && st.full_at.is_none() {
                        st.full_at = Some(now);
                    }
                    let full_for = st.full_at.map(|f| now - f);
                    recipes::charge_cue(&mut fx, look, hand.muzzle, hand.dir, p.charge, full_for, now, owner);
                    st.motes += dt * 8.0 / look.charge_time.max(0.3);
                    while st.motes >= 1.0 {
                        st.motes -= 1.0;
                        if p.charge < 0.999 {
                            recipes::charge_mote(&mut fx, look, hand.muzzle, owner);
                        }
                    }
                } else {
                    st.full_at = None;
                }
            }
            FireKind::Beam => {
                if let Some(b) = p.beam {
                    let beam = &mut st.beam;
                    recipes::beam(
                        &mut fx,
                        p.slot as u32,
                        look,
                        hand.muzzle,
                        hand.dir,
                        b.len,
                        b.width,
                        now,
                        dt,
                        beam,
                        owner,
                    );
                }
            }
            FireKind::Melee => {
                // Melee strikes carry no Shot event: keep the weapon's cadence while the hero is
                // swinging, the same way the hero's animation does (anim.rs).
                let interval = 1.0 / look.base_rate.max(0.5);
                let flagged = p.firing && world.tick != st.last_tick;
                let landed =
                    link.fresh_events.iter().any(|e| matches!(*e, GameEvent::Hit { source, .. } if source == p.slot));
                let reach = look.range + 0.4;
                let ahead = Vec2::new(hand.dir.x, -hand.dir.z);
                let in_reach = visuals.iter().any(|v| {
                    if !matches!(v.kind, EntityKind::Enemy { .. }) {
                        return false;
                    }
                    let d = v.shown - p.mover.pos;
                    let r = d.length();
                    r < reach + v.radius && (r < 0.5 + v.radius || d.dot(ahead) > 0.5 * r)
                });
                if flagged || landed || in_reach {
                    st.swing_until = now + interval * 1.25;
                }
                let due = if flagged || landed {
                    now >= st.swing_next - interval * 0.5
                } else {
                    now < st.swing_until && now >= st.swing_next
                };
                st.last_tick = world.tick;
                if due {
                    st.swing_next = now + interval;
                    let n = st.swings;
                    st.swings = st.swings.wrapping_add(1);
                    let strike =
                        Strike { look, feet: hand.feet, dir: hand.dir, n, owner, fist: hand.fists[(n % 2) as usize] };
                    recipes::strike(&mut fx, &strike);
                }
            }
            FireKind::Auto => {}
        }
    }
}

/// Orbiting blades: a circular smear trails each round its owner (VFX_STYLE §9 "Orbit").
fn orbit(arsenal: Res<Arsenal>, mut blades: Query<(&GlobalTransform, &mut BladeFx)>, mut fx: Fx) {
    for (g, mut b) in &mut blades {
        let Some(hand) = arsenal.hands[b.slot as usize % 4] else { continue };
        let pos = g.translation();
        let center = Vec3::new(hand.feet.x, pos.y, hand.feet.z);
        let rel = pos - center;
        let r = Vec2::new(rel.x, rel.z).length();
        if r < 0.3 {
            continue;
        }
        let a = (-rel.x).atan2(-rel.z);
        if let Some(last) = b.last {
            let mut da = a - last;
            while da > PI {
                da -= 2.0 * PI;
            }
            while da < -PI {
                da += 2.0 * PI;
            }
            if da.abs() > 1e-3 {
                b.sign = da.signum();
            }
        }
        b.last = Some(a);
        let sweep = 1.2;
        let mut arc = Arc::new(strip::SPIN_DISC, center, r + 0.25, 0.5, 1.0);
        arc.start = a - b.sign * sweep;
        arc.sweep = b.sign * sweep;
        arc.sweep_anim = Sweep::Static;
        arc.profile = Profile::Crescent { peak: 0.85 };
        arc.ramp = b.ramp;
        arc.gain = 1.1;
        arc.erode = Vec2::new(1.0, 0.0);
        arc.segments = 18;
        arc.pull = 0.2;
        arc.layer = Layer::Main;
        fx.arc_now(arc, b.owner, Class::Core);
    }
}

/// Stuck arrows and javelins go after their few frames.
fn unstick(mut commands: Commands, time: Res<Time>, mut q: Query<(Entity, &mut Stuck)>) {
    for (e, mut s) in &mut q {
        s.0 -= time.delta_secs();
        if s.0 <= 0.0 {
            commands.entity(e).despawn();
        }
    }
}
