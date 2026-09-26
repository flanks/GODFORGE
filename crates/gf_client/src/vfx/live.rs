//! Per-frame combat presentation that outlives its event: ability auras (Siege Stance's taunt
//! pulse, Mountainfall's heat column and ground pounds, Meltdown's molten fists, Bullet Ballet's
//! afterimages, the Hunt's reticles, the Sabbath's fountains, the Heist's glints), Stolen Second's
//! freeze, zone ambience, loot beams, the revive tether and the downed wraith's embers
//! (VFX_STYLE §14, §16-18).
//!
//! [`CastLog`] remembers recent casts and synergies, so fields, landings and follow-up bursts can
//! be told apart from generic ones.

use super::kit::{self, Hero};
use super::zone::ZoneFx;
use crate::ClientConfig;
use crate::camera::w3;
use crate::fx::api::F;
use crate::fx::{Fx, Owner, Ramp, RibbonStyle, seq, strip};
use crate::net::Link;
use crate::scene::{SceneIndex, Visual};
use gf_core::revive::LifeState;
use gf_engine::prelude::*;
use gf_net::quant::u16_to_dir;
use gf_net::{EntityKind, PickupKind, PlayerFlags};

/// A recent kit cast.
#[derive(Clone, Debug)]
pub struct CastRec {
    pub t: f32,
    pub slot: u8,
    pub hero: Hero,
    pub which: u8,
    /// Where the caster stood (sim plane).
    pub at: Vec2,
    pub aim: Vec2,
}

/// A recent synergy.
#[derive(Clone, Debug)]
pub struct SynRec {
    pub t: f32,
    pub key: String,
    pub at: Vec2,
    pub owner: Owner,
}

/// Recent casts and synergies (12 s), plus the effects that run on after them.
#[derive(Resource, Default)]
pub struct CastLog {
    pub casts: Vec<CastRec>,
    pub synergies: Vec<SynRec>,
    /// Stolen Second: (VFX freeze ends at, Epoch's feet, owner).
    pub freeze: Option<(f32, Vec3, Owner)>,
}

impl CastLog {
    pub fn record(&mut self, rec: CastRec) {
        let now = rec.t;
        self.casts.retain(|c| now - c.t < 12.0);
        self.casts.push(rec);
    }

    pub fn record_synergy(&mut self, rec: SynRec) {
        let now = rec.t;
        self.synergies.retain(|s| now - s.t < 2.0);
        self.synergies.push(rec);
    }

    /// The latest cast of `hero`'s `which` by `slot` within `within` seconds.
    pub fn active(&self, slot: u8, hero: Hero, which: u8, now: f32, within: f32) -> Option<&CastRec> {
        self.casts.iter().rev().find(|c| c.slot == slot && c.hero == hero && c.which == which && now - c.t <= within)
    }

    /// The latest cast of `hero`'s `which` by anyone within `within` seconds.
    pub fn any(&self, hero: Hero, which: u8, now: f32, within: f32) -> Option<&CastRec> {
        self.casts.iter().rev().find(|c| c.hero == hero && c.which == which && now - c.t <= within)
    }
}

/// Per-slot aura state.
#[derive(Default)]
pub struct Auras {
    avatar: [bool; 4],
    pulse: [f32; 4],
    /// Mountainfall: the cast time the pounds count from, and the pounds played.
    pounds: [(f32, u32); 4],
    last_pos: [Option<Vec3>; 4],
    hunt: f32,
    sabbath: f32,
    beams: f32,
}

/// The hero of a player from their character.
pub fn hero_of(cfg: &ClientConfig, character: u16) -> Hero {
    cfg.content.characters.try_get(character).map_or(Hero::Other, |c| Hero::from_key(&c.key))
}

/// A loot ramp for a part rarity.
fn rarity_ramp(r: gf_core::rarity::Rarity) -> Ramp {
    use gf_core::rarity::Rarity as R;
    match r {
        R::Common => Ramp::Mono,
        R::Rare => Ramp::Storm,
        R::Epic => Ramp::Void,
        R::Godforged => Ramp::ZoneGold,
    }
}

#[allow(clippy::too_many_arguments)]
pub fn auras(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    index: Res<SceneIndex>,
    mut log: ResMut<CastLog>,
    visuals: Query<&Visual>,
    mut zones: Query<(&Visual, &mut ZoneFx)>,
    globals: Query<&GlobalTransform>,
    mut fx: Fx,
    mut st: Local<Auras>,
) {
    let dt = time.delta_secs();
    let now = time.elapsed_secs();
    if dt <= 0.0 {
        return;
    }
    // Stolen Second: the VFX clock nearly stops, then snaps back with a gold tick.
    if let Some((end, at, owner)) = log.freeze {
        if now < end {
            fx.store.time_scale = 0.06;
        } else {
            fx.store.time_scale = 1.0;
            log.freeze = None;
            kit::time_resume(&mut fx, at, owner);
        }
    }
    let Some(world) = link.latest.clone() else { return };
    let me = link.slot;
    let every = |fx: &mut Fx, rate: f32| fx.rand() < rate * dt;
    let enemies = || visuals.iter().filter(|v| matches!(v.kind, EntityKind::Enemy { .. }));
    st.hunt -= dt;
    st.sabbath -= dt;
    st.beams -= dt;
    let hunt_tick = st.hunt <= 0.0;
    if hunt_tick {
        st.hunt = 0.9;
    }
    let sabbath_tick = st.sabbath <= 0.0;
    if sabbath_tick {
        st.sabbath = 0.5;
    }
    for p in &world.players {
        let s = (p.slot % 4) as usize;
        let hero = hero_of(&cfg, p.character);
        let owner = Owner::of_slot(p.slot, me);
        let entity = index.players.get(s).copied().flatten();
        let at = entity.and_then(|e| globals.get(e).ok()).map_or(w3(p.mover.pos, 0.0), |g| g.translation().with_y(0.0));
        let aim = w3(u16_to_dir(p.aim), 0.0).normalize_or(Vec3::NEG_Z);
        let side = aim.cross(Vec3::Y).normalize_or(Vec3::X);
        let moved = st.last_pos[s].map_or(0.0, |l| l.distance(at) / dt);
        st.last_pos[s] = Some(at);
        let avatar = p.flags.contains(PlayerFlags::AVATAR);
        // ── Downed: the wraith sheds slow gold embers; a reviver holds a braided tether ──
        if let LifeState::Downed { progress, .. } = p.life {
            if every(&mut fx, 2.0) {
                let off = fx.rand_dir() * 0.3;
                fx.sprite(crate::fx::Mote::Ember.seq(), at + off + Vec3::Y * 1.2)
                    .size(0.16)
                    .vel(Vec3::Y * 0.6)
                    .ramp(Ramp::ZoneGold)
                    .life(1.2)
                    .erode(0.6, 1.0)
                    .owner(Owner::World)
                    .emit();
            }
            if progress > 0.0
                && let Some(r) = world
                    .players
                    .iter()
                    .filter(|q| q.slot != p.slot && q.life.is_alive())
                    .min_by(|a, b| a.mover.pos.distance(p.mover.pos).total_cmp(&b.mover.pos.distance(p.mover.pos)))
                && r.mover.pos.distance(p.mover.pos) < 4.5
            {
                let from = w3(r.mover.pos, 1.1);
                let to = at + Vec3::Y * 1.1;
                let rowner = Owner::of_slot(r.slot, me);
                fx.tether(p.slot as u32, from, to, 0.34, Ramp::ZoneGold, Owner::World);
                if every(&mut fx, 7.0) {
                    fx.sprite(seq::GLINT.nth(1), from)
                        .size(0.28)
                        .ramp(Ramp::ZoneGold)
                        .path(to, None, 0.4)
                        .life(0.45)
                        .owner(rowner)
                        .emit();
                }
                // The progress fills along the tether.
                let fill = from.lerp(to, progress.clamp(0.0, 1.0));
                fx.sprite(seq::GLINT.nth(0), fill)
                    .size(0.5)
                    .ramp(Ramp::Heal)
                    .gain(1.3)
                    .life(F * 1.5)
                    .erode(1.0, 0.0)
                    .owner(Owner::World)
                    .emit();
            }
            continue;
        }
        // ── Overdrive: gold glints rise round every player ──
        if p.flags.contains(PlayerFlags::OVERDRIVE) && every(&mut fx, 5.0) {
            let off = fx.rand_dir() * 0.6;
            fx.sprite(seq::GLINT.nth(2), at + off + Vec3::Y * 0.4)
                .size(0.3)
                .vel(Vec3::Y * 1.6)
                .ramp(Ramp::ZoneGold)
                .life(0.6)
                .owner(owner)
                .emit();
        }
        match hero {
            Hero::Valdris => {
                // Siege Stance: the gold taunt pulse, once a second, on the ground.
                if p.flags.contains(PlayerFlags::STANCE) {
                    st.pulse[s] -= dt;
                    if st.pulse[s] <= 0.0 {
                        st.pulse[s] = 1.0;
                        fx.ring(at, 0.6, 3.6, 0.6, strip::ACCENT_RING, Ramp::ZoneGold, owner);
                    }
                }
                if avatar {
                    // The forge-heat column behind him, embers climbing.
                    let base = at - aim * 0.7;
                    let style = RibbonStyle {
                        tile: 6.0,
                        scroll: 3.0,
                        taper: 0.6,
                        erode: 0.0,
                        fade: 0.3,
                        alpha: 0.55,
                        ..RibbonStyle::new(strip::LOOT_BEAM, Ramp::Flame, 1.5, 1e4)
                    };
                    fx.immediate_line(0x4100_0000 + s as u32, base + Vec3::Y * 0.1, base + Vec3::Y * 5.5, style, owner);
                    if every(&mut fx, 14.0) {
                        let off = fx.rand_dir() * 0.9;
                        fx.embers(at + off + Vec3::Y * 0.6, 1, 0.2, owner);
                    }
                    // The ground pound every 1.1 s from the cast (first at 0.55 s).
                    if let Some(c) = log.active(p.slot, Hero::Valdris, 2, now, 8.2) {
                        if st.pounds[s].0 != c.t {
                            st.pounds[s] = (c.t, 0);
                        }
                        let next = c.t + 0.55 + st.pounds[s].1 as f32 * 1.1;
                        if now >= next {
                            st.pounds[s].1 += 1;
                            kit::mountain_pound(&mut fx, at, 4.5, owner);
                        }
                    }
                }
            }
            Hero::Brax => {
                if avatar {
                    // Molten fists: flame licks stream back off both hands.
                    for k in [-1.0, 1.0] {
                        if every(&mut fx, 18.0) {
                            let hand = at + side * k * 0.55 + Vec3::Y * 1.15 + aim * 0.25;
                            let v = -aim * 2.2 + Vec3::Y * 1.2;
                            fx.sprite(seq::FLAME_LICKS, hand)
                                .size(0.6)
                                .vel(v)
                                .drag(2.0)
                                .ramp(Ramp::Flame)
                                .gain(1.3)
                                .life(0.28)
                                .erode(0.5, 1.0)
                                .pull(0.5)
                                .owner(owner)
                                .emit();
                        }
                    }
                    if every(&mut fx, 8.0) {
                        let off = fx.rand_dir() * 0.5;
                        fx.embers(at + off + Vec3::Y * 1.4, 1, 0.1, owner);
                    }
                }
                // Furnace Rush: an ember wake behind him.
                if log.active(p.slot, Hero::Brax, 1, now, 0.45).is_some() && every(&mut fx, 40.0) {
                    fx.embers(at + Vec3::Y * 0.3, 1, 0.5, owner);
                    if every(&mut fx, 20.0) {
                        let h = fx.range(0.7, 1.1);
                        fx.sprite(seq::FLAME_MEDIUM, at)
                            .size(h)
                            .ramp(Ramp::Flame)
                            .life(0.4)
                            .erode(0.6, 1.0)
                            .owner(owner)
                            .emit();
                    }
                }
            }
            Hero::Kael => {
                // Bullet Ballet: every dash leaves an ink afterimage that fades over 12 frames.
                if p.flags.contains(PlayerFlags::INFINITE_DASH) && moved > 11.0 && every(&mut fx, 30.0) {
                    fx.sprite(seq::SMOKE.in_column(2), at + Vec3::Y * 1.0)
                        .radius(0.55)
                        .ramp(Ramp::Void)
                        .value(crate::fx::value::INK)
                        .life(12.0 * F)
                        .play(crate::fx::Play::Life)
                        .erode(0.2, 1.0)
                        .owner(owner)
                        .emit();
                }
            }
            Hero::Selene => {
                // Static Charge: micro-arcs crackle round her feet as the meter fills.
                if p.passive_meter > 0.25 && every(&mut fx, 4.0 * p.passive_meter) {
                    let a = at + fx.rand_dir() * 0.5 + Vec3::Y * 0.1;
                    let b = a + fx.rand_dir() * 0.7 + Vec3::Y * 0.3;
                    fx.bolt(a, b, Ramp::Storm, 0.25, 4.0 * F, owner);
                }
            }
            Hero::Ossian => {
                // Rain of the Hunt: gold reticles pulse on every marked enemy in reach.
                if hunt_tick && log.active(p.slot, Hero::Ossian, 2, now, 5.0).is_some() {
                    let from = at;
                    for v in enemies()
                        .filter(|v| v.status & (1 << 5) != 0 && w3(v.shown, 0.0).distance(from) < 18.0)
                        .take(20)
                    {
                        kit::mark_reticle(&mut fx, w3(v.shown, v.hit_height + 0.9), owner);
                    }
                }
            }
            Hero::Thessaly => {
                // Sabbath of Sparks: the turrets throw spark fountains.
                if sabbath_tick && log.active(p.slot, Hero::Thessaly, 2, now, 8.0).is_some() {
                    for v in visuals
                        .iter()
                        .filter(|v| matches!(v.kind, EntityKind::Turret { owner: o } if o % 4 == p.slot % 4))
                    {
                        kit::turret_fountain(&mut fx, w3(v.shown, 0.0), owner);
                    }
                }
            }
            Hero::Mirren => {
                // Snatch: gold speed lines on her for the buff; Grand Heist: loot glints.
                if log.active(p.slot, Hero::Mirren, 1, now, 4.0).is_some() && every(&mut fx, 10.0) {
                    let off = side * fx.range(-0.4, 0.4) + Vec3::Y * fx.range(0.4, 1.6);
                    fx.sprite(seq::SPARK.nth(3), at + off)
                        .size(0.26)
                        .vel(-aim * 9.0)
                        .streak(0.06)
                        .ramp(Ramp::ZoneGold)
                        .life(0.2)
                        .owner(owner)
                        .emit();
                }
                if log.active(p.slot, Hero::Mirren, 2, now, 6.0).is_some() && every(&mut fx, 6.0) {
                    let off = fx.rand_dir() * 0.7;
                    fx.sprite(seq::GLINT.nth(0), at + off + Vec3::Y * 0.8)
                        .size(0.34)
                        .vel(Vec3::Y * 1.2)
                        .ramp(Ramp::ZoneGold)
                        .life(0.5)
                        .owner(owner)
                        .emit();
                }
            }
            _ => {}
        }
        // An avatar ending: the heat column collapses into cooling embers.
        if st.avatar[s] && !avatar {
            fx.embers(at + Vec3::Y * 1.2, 20, 0.9, owner);
            fx.smoke(at + Vec3::Y * 0.8, 4, 0.7, Ramp::Dust, owner);
        }
        st.avatar[s] = avatar;
    }
    // ── Zones: rim tongues, storm strikes, geysers, bubbles, motes ──
    for (v, mut z) in &mut zones {
        let at = w3(v.shown, 0.0);
        let needs_targets = matches!(z.look, kit::ZoneLook::Firestorm | kit::ZoneLook::Verdict) && z.strike - dt <= 0.0;
        let inside: Vec<Vec3> = if needs_targets {
            enemies().filter(|e| e.shown.distance(v.shown) <= z.radius).take(24).map(|e| w3(e.shown, 0.0)).collect()
        } else {
            Vec::new()
        };
        let (look, ramp, radius, owner, seed) = (z.look, z.ramp, z.radius, z.owner, z.seed);
        let mut strike = z.strike;
        kit::zone_tick(&mut fx, look, ramp, at, radius, owner, dt, v.age, seed, &mut strike, &inside);
        z.strike = strike;
    }
    // ── Loot beams: tall, thin, gently wobbling; never dropped by the tier ──
    let beam_glints = st.beams <= 0.0;
    if beam_glints {
        st.beams = 0.4;
    }
    for v in &visuals {
        let EntityKind::Pickup { kind: PickupKind::Part { rarity }, owner } = v.kind else { continue };
        let mine = owner.is_none() || owner == me;
        if !mine || rarity < gf_core::rarity::Rarity::Rare {
            continue;
        }
        let ramp = rarity_ramp(rarity);
        let epic = rarity >= gf_core::rarity::Rarity::Epic;
        let base = w3(v.shown, 0.05);
        let wob = Vec3::new((now * 1.3 + v.id.0 as f32).sin(), 0.0, (now * 1.1).cos()) * 0.12;
        let style = RibbonStyle {
            tile: 2.5,
            scroll: 1.6,
            taper: 0.5,
            erode: 0.0,
            fade: 0.2,
            gain: 1.3,
            ..RibbonStyle::new(strip::LOOT_BEAM, ramp, if epic { 0.8 } else { 0.5 }, 1e4)
        };
        fx.immediate_line(0x4000_0000 | (v.id.0 & 0x00FF_FFFF), base, base + Vec3::Y * 5.0 + wob, style, Owner::World);
        if beam_glints {
            let off = fx.rand_dir() * 0.15;
            fx.sprite(seq::GLINT.nth(1), base + off + Vec3::Y * 0.6)
                .size(0.3)
                .vel(Vec3::Y * 2.2)
                .ramp(ramp)
                .life(1.2)
                .erode(0.8, 1.0)
                .owner(Owner::World)
                .emit();
            if rarity == gf_core::rarity::Rarity::Godforged && fx.rand() < 0.34 {
                fx.sprite(seq::RADIANT_SUNBURST, base)
                    .radius(1.1)
                    .ground()
                    .ramp(Ramp::ZoneGold)
                    .life(1.4)
                    .alpha(0.7)
                    .owner(Owner::World)
                    .emit();
            }
        }
    }
}
