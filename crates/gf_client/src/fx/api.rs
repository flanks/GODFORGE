//! The VFX API effect code calls: the [`Fx`] system parameter.
//!
//! Two levels:
//!
//! * **Primitives** — [`Fx::sprite`] (any flipbook quad, with a builder), [`Fx::trail_for`] /
//!   [`Fx::trail_linear`] / [`Fx::ribbon`] (ribbons), [`Fx::beam`] (immediate-mode beams),
//!   [`Fx::arc`] / [`Fx::smear`] / [`Fx::slash`] / [`Fx::ring`] (arc strips), [`Fx::bolt`]
//!   (lightning), [`Fx::decal`], [`Fx::light`], [`Fx::pillar`], [`Fx::tether`].
//! * **Recipes** — the shared VFX_STYLE recipes built from them: [`Fx::impact`] (§10),
//!   [`Fx::burst`] (the layered burst, §11), [`Fx::muzzle`] (§7-8), [`Fx::death`] (§15.3),
//!   [`Fx::motes`] (§12.2), [`Fx::sparks`], [`Fx::smoke`], [`Fx::shards`], [`Fx::embers`].
//!
//! Every spawn names its [`Owner`] and [`Class`]; the budget ([`FxStore::grant`]) applies the
//! readability tier and the ally alpha, so recipes never branch on the tier themselves.
//!
//! ```ignore
//! fn on_hit(mut fx: Fx, ...) {
//!     fx.impact(Hit::new(pos, Ramp::Flame, 0.45, Owner::Mine).kind(HitKind::Crit).dir(travel));
//!     fx.burst(Ramp::Storm, pos, 2.5, Owner::Ally);
//!     fx.sprite(seq::STAR5, pos).radius(0.4).ramp(Ramp::Void).ink_backed().emit();
//! }
//! ```

use super::arc::{Arc, Profile, Sweep};
use super::library::{Decal, Mote, Ramp, Seq, Sheet, Strip, seq, strip, value};
use super::light::Flash;
use super::particle::{Curve, Orient, Particle, Path, Play};
use super::ribbon::{Ribbon, RibbonStyle, Source};
use super::{Class, FxStore, Layer, Owner};
use gf_core::damage::DamageType;
use gf_core::weapon::ProjectileStyle;
use gf_engine::client::SystemParam;
use gf_engine::prelude::*;
use std::f32::consts::{FRAC_PI_2, PI, TAU};

/// A frame at 60 fps (VFX_STYLE timings are in frames).
pub const F: f32 = 1.0 / 60.0;

/// Handle to a live ribbon (generation-checked: a stale handle is ignored).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct RibbonId {
    pub(crate) index: u32,
    pub(crate) generation: u32,
}

/// The VFX system parameter.
#[derive(SystemParam)]
pub struct Fx<'w> {
    pub store: ResMut<'w, FxStore>,
}

/// A particle being configured; nothing spawns until [`SpriteBuilder::emit`].
#[must_use = "a sprite spawns only on .emit()"]
pub struct SpriteBuilder<'a> {
    store: &'a mut FxStore,
    p: Particle,
    owner: Owner,
    class: Class,
    ink: Option<(f32, f32)>,
}

impl<'a> SpriteBuilder<'a> {
    /// Quad height in metres (the width follows the cell's aspect).
    pub fn size(mut self, height: f32) -> Self {
        self.p.size = Vec2::new(height * self.p.seq.sheet.cell_aspect(), height);
        self
    }

    /// Quad width and height in metres.
    pub fn size2(mut self, width: f32, height: f32) -> Self {
        self.p.size = Vec2::new(width, height);
        self
    }

    /// Size the quad so the painted shape covers a gameplay radius (VFX_STYLE §1.5).
    pub fn radius(self, r: f32) -> Self {
        let h = self.p.seq.height_for_radius(r);
        self.size(h)
    }

    pub fn life(mut self, seconds: f32) -> Self {
        self.p.life = seconds.max(F);
        self
    }

    pub fn vel(mut self, v: Vec3) -> Self {
        self.p.vel = v;
        self
    }

    pub fn gravity(mut self, g: f32) -> Self {
        self.p.gravity = g;
        self
    }

    pub fn drag(mut self, d: f32) -> Self {
        self.p.drag = d;
        self
    }

    pub fn rot(mut self, radians: f32) -> Self {
        self.p.rot = radians;
        self
    }

    pub fn spin(mut self, radians_per_s: f32) -> Self {
        self.p.spin = radians_per_s;
        self
    }

    pub fn ramp(mut self, ramp: Ramp) -> Self {
        self.p.ramp = ramp;
        self
    }

    pub fn element(self, e: DamageType) -> Self {
        self.ramp(Ramp::of(e))
    }

    /// HDR gain multiplier on the ramp's band gains.
    pub fn gain(mut self, g: f32) -> Self {
        self.p.gain = g;
        self
    }

    pub fn alpha(mut self, a: f32) -> Self {
        self.p.alpha = Curve::flat(a);
        self
    }

    pub fn alpha_curve(mut self, c: Curve) -> Self {
        self.p.alpha = c;
        self
    }

    pub fn scale(mut self, c: Curve) -> Self {
        self.p.scale = c;
        self
    }

    /// Erosion begins at normalized age `from` and reaches `amount` at death.
    pub fn erode(mut self, from: f32, amount: f32) -> Self {
        self.p.erode = Vec2::new(from, amount);
        self
    }

    pub fn cool(mut self, c: f32) -> Self {
        self.p.cool = c;
        self
    }

    /// Paint the whole shape at one ramp value ([`value::INK`], [`value::HOT`], ...).
    pub fn value(mut self, v: f32) -> Self {
        self.p.value = v;
        self
    }

    pub fn soft(mut self, s: f32) -> Self {
        self.p.soft = s.abs() * self.p.soft.signum();
        self
    }

    /// Draw the whole shape additively (pure light: glints, spill accents); by default only the hot
    /// band adds and the rest blends over.
    pub fn additive(mut self) -> Self {
        self.p.soft = -self.p.soft.abs();
        self
    }

    pub fn orient(mut self, o: Orient) -> Self {
        self.p.orient = o;
        self
    }

    /// Lay the quad on the floor.
    pub fn ground(mut self) -> Self {
        self.p.orient = Orient::Ground;
        if self.p.layer == Layer::Main {
            self.p.layer = Layer::Ground;
        }
        self
    }

    /// Point `+u` along a world direction (muzzle flashes, slashes, bolts).
    pub fn toward(mut self, dir: Vec3) -> Self {
        self.p.orient = Orient::Axis { dir };
        self
    }

    /// Stretch along the velocity (sparks).
    pub fn streak(mut self, stretch: f32) -> Self {
        self.p.orient = Orient::Velocity { stretch };
        self
    }

    pub fn layer(mut self, l: Layer) -> Self {
        self.p.layer = l;
        self
    }

    pub fn pull(mut self, metres: f32) -> Self {
        self.p.pull = metres;
        self
    }

    pub fn bounce(mut self, restitution: f32) -> Self {
        self.p.bounce = restitution;
        self
    }

    /// Ride along with an entity (`at` becomes the offset from it).
    pub fn follow(mut self, e: Entity) -> Self {
        self.p.follow = Some(e);
        self
    }

    /// Fly on an arc to `to` (a point, or `target`'s translation + `to` while it lives).
    pub fn path(mut self, to: Vec3, target: Option<Entity>, height: f32) -> Self {
        self.p.path =
            Some(Path { from: self.p.pos, to, target, offset: if target.is_some() { to } else { Vec3::ZERO }, height });
        self
    }

    pub fn play(mut self, p: Play) -> Self {
        self.p.play = p;
        self
    }

    /// Appear `seconds` later (second beats, staggered sequences).
    pub fn delay(mut self, seconds: f32) -> Self {
        self.p.age = -seconds.max(0.0);
        self
    }

    /// Start a looping flipbook at a random frame.
    pub fn phase(mut self, seconds: f32) -> Self {
        self.p.phase = seconds;
        self
    }

    pub fn owner(mut self, o: Owner) -> Self {
        self.owner = o;
        self
    }

    pub fn class(mut self, c: Class) -> Self {
        self.class = c;
        self
    }

    /// Put the VFX_STYLE ink backing behind it: the same frame at ink, 30 % larger, rotated 6°.
    pub fn ink_backed(mut self) -> Self {
        self.ink = Some((1.3, 0.11));
        self
    }

    pub fn ink_backed_by(mut self, scale: f32, rot: f32) -> Self {
        self.ink = Some((scale, rot));
        self
    }

    /// Spawn it (returns false when the budget skipped it).
    pub fn emit(self) -> bool {
        let SpriteBuilder { store, mut p, owner, class, ink } = self;
        let Some(g) = store.grant(owner, class) else { return false };
        p.alpha = Curve { a: p.alpha.a * g.alpha, b: p.alpha.b * g.alpha, c: p.alpha.c * g.alpha, mid: p.alpha.mid };
        p.cap = p.cap.min(g.cap);
        p.size *= g.size;
        p.life *= g.life;
        p.world = p.pos;
        let decal = class == Class::Decal || p.layer == Layer::Decal;
        if let Some((scale, rot)) = ink {
            let mut back = p;
            back.size *= scale;
            back.rot += rot;
            back.value = value::INK;
            back.alpha = Curve { a: p.alpha.a * 0.95, b: p.alpha.b * 0.95, c: p.alpha.c * 0.95, mid: p.alpha.mid };
            back.layer = p.layer.behind();
            if decal { store.push_decal(back) } else { store.push_particle(back) }
        }
        if decal {
            store.push_decal(p);
        } else {
            store.push_particle(p);
        }
        true
    }
}

/// What kind of hit a hit mark punctuates (VFX_STYLE §10).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum HitKind {
    /// A small ink-backed star in the element style, 4 frames, 2-3 sparks.
    #[default]
    Plain,
    /// A gold anime slash 62° off the travel, a white 4-point star over a rotated ink star, chips.
    Crit,
    /// Manual aim: a cyan-white broken bullseye collapsing onto the point, a glint.
    Precision,
    /// Heavy or splash impact: the impact frame (own only) and light spill.
    Heavy,
}

/// A hit to punctuate.
#[derive(Clone, Copy, Debug)]
pub struct Hit {
    pub at: Vec3,
    /// Travel direction of what hit (zero when unknown).
    pub dir: Vec3,
    pub ramp: Ramp,
    /// Radius of the star (metres).
    pub size: f32,
    pub kind: HitKind,
    pub owner: Owner,
    /// Radius of the body hit: the mark is pulled in front of it.
    pub body: f32,
}

impl Hit {
    pub fn new(at: Vec3, ramp: Ramp, size: f32, owner: Owner) -> Hit {
        Hit { at, dir: Vec3::ZERO, ramp, size, kind: HitKind::Plain, owner, body: 0.5 }
    }

    pub fn kind(mut self, k: HitKind) -> Hit {
        self.kind = k;
        self
    }

    pub fn dir(mut self, d: Vec3) -> Hit {
        self.dir = d;
        self
    }

    pub fn body(mut self, r: f32) -> Hit {
        self.body = r;
        self
    }
}

/// A smear to draw (VFX_STYLE §7.4): a crescent in a plane around `pivot`, sweeping `sweep`
/// radians centred on `dir`.
#[derive(Clone, Copy, Debug)]
pub struct Smear {
    pub pivot: Vec3,
    /// The strike direction (the middle of the sweep), in the ground plane unless `tilt` ≠ 0.
    pub dir: Vec3,
    /// Outer radius (reach).
    pub reach: f32,
    /// Thickest width of the crescent.
    pub width: f32,
    /// Total sweep (radians); the sign picks the swing direction (positive = counter-clockwise).
    pub sweep: f32,
    /// Tilt of the swing plane about the strike direction (0 = flat, ±π/2 = vertical).
    pub tilt: f32,
    pub strip: Strip,
    pub ramp: Ramp,
    pub life: f32,
    pub owner: Owner,
    pub follow: Option<Entity>,
    pub gain: f32,
}

impl Smear {
    pub fn new(pivot: Vec3, dir: Vec3, reach: f32, ramp: Ramp, owner: Owner) -> Smear {
        Smear {
            pivot,
            dir,
            reach,
            width: reach * 0.5,
            sweep: 100f32.to_radians(),
            tilt: 0.0,
            strip: strip::MELEE_HEAVY,
            ramp,
            life: 9.0 * F,
            owner,
            follow: None,
            gain: 1.0,
        }
    }
}

/// The star shape of each element's hit (VFX_STYLE §4).
pub fn hit_star(ramp: Ramp) -> Seq {
    match ramp {
        Ramp::Storm => seq::STAR4,
        Ramp::Flame => seq::STAR7,
        Ramp::Void => seq::PETAL_INWARD_STAR,
        Ramp::Radiant => seq::RADIANT_CROSS_FLARE,
        Ramp::Plague => seq::PLAGUE_SPLAT,
        _ => seq::STAR5,
    }
}

/// The element burst flipbook (the blast, smoke crown and dissipation in one painted sequence).
pub fn burst_seq(ramp: Ramp) -> Seq {
    match ramp {
        Ramp::Flame => seq::BURST_FLAME,
        Ramp::Storm => seq::BURST_STORM,
        Ramp::Void => seq::BURST_VOID,
        Ramp::Plague => seq::BURST_PLAGUE,
        Ramp::Radiant | Ramp::ZoneGold | Ramp::Heal => seq::BURST_RADIANT,
        Ramp::Unmade => seq::BURST_UNMADE,
        Ramp::GodworksGold | Ramp::GodworksEmber => seq::BURST_GODWORKS,
        _ => seq::BURST_KINETIC,
    }
}

/// The faction glow of an enemy by its content key (VFX_STYLE §15.3). The Fallen Godworks rows
/// burn cold gold; everything else is the Unmade's teal ichor until the enemy sheet carries a
/// faction column.
pub fn faction_ramp(enemy_key: &str) -> Ramp {
    const GODWORKS: [&str; 5] = ["forge_warden", "emberwisp", "the_bellows", "ticker", "horologist"];
    if GODWORKS.contains(&enemy_key) { Ramp::GodworksGold } else { Ramp::Unmade }
}

/// The ramp a flipbook sheet was painted for (the burst sheets are one element each).
pub fn painted_ramp(seq: Seq, fallback: Ramp) -> Ramp {
    match seq.sheet {
        Sheet::BurstFlame => Ramp::Flame,
        Sheet::BurstStorm => Ramp::Storm,
        Sheet::BurstVoid => Ramp::Void,
        Sheet::BurstPlague => Ramp::Plague,
        Sheet::BurstRadiant => Ramp::Radiant,
        Sheet::BurstUnmade => Ramp::Unmade,
        Sheet::BurstGodworks => Ramp::GodworksGold,
        Sheet::BurstKinetic => Ramp::Kinetic,
        _ => fallback,
    }
}

/// The trail each projectile style leaves (VFX_STYLE §6), sized to its speed: about three frames
/// of travel.
pub fn trail_style(style: ProjectileStyle, ramp: Ramp, speed: f32) -> Option<RibbonStyle> {
    use ProjectileStyle as S;
    // Widths are the strip's cross-section: the painted stroke fills a third to a half of it.
    let travel = (speed * 0.05).max(0.3);
    let s = match style {
        S::Bolt => RibbonStyle { taper: 0.3, ..RibbonStyle::new(strip::DRY_BRUSH, ramp, 0.84, 0.9) },
        S::Slug => {
            RibbonStyle { taper: 0.55, erode: 0.05, ..RibbonStyle::new(strip::TRACER, ramp, 0.74, travel.max(1.6)) }
        }
        S::Shell => {
            RibbonStyle { taper: 0.6, max_age: 0.45, ..RibbonStyle::new(strip::SMOKE_TRAIL, ramp, 1.28, travel * 2.0) }
        }
        S::Orb => RibbonStyle { taper: 0.7, ..RibbonStyle::new(strip::HELIX, ramp, 1.01, 1.8) },
        S::Globe => RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::DRIP_TRAIL, ramp, 1.08, 1.5) },
        S::Shard => RibbonStyle { taper: 0.5, ..RibbonStyle::new(strip::GLINT_TRAIL, ramp, 0.94, 1.3) },
        S::Arrow => RibbonStyle { taper: 0.35, ..RibbonStyle::new(strip::GHOST_SMEAR, ramp, 1.01, travel.max(1.6)) },
        S::Pellet => RibbonStyle { taper: 0.4, ..RibbonStyle::new(strip::NEEDLE_STREAK, ramp, 0.54, 0.6) },
        S::Boulder => {
            RibbonStyle { taper: 0.5, max_age: 0.5, ..RibbonStyle::new(strip::DUST_RIBBON, Ramp::Dust, 1.62, 2.4) }
        }
        S::Coin => RibbonStyle { taper: 0.6, ..RibbonStyle::new(strip::ZIGZAG, Ramp::Radiant, 0.68, 1.5) },
        S::Needle => RibbonStyle { taper: 0.4, ..RibbonStyle::new(strip::NEEDLE_STREAK, ramp, 0.61, 1.3) },
        S::Blade => RibbonStyle { taper: 0.4, ..RibbonStyle::new(strip::DRY_BRUSH, ramp, 0.81, 1.1) },
        S::Arc | S::Fist => return None,
    };
    Some(s)
}

impl Fx<'_> {
    /// The live store (tier, stats, time scale).
    pub fn store(&mut self) -> &mut FxStore {
        &mut self.store
    }

    pub fn rand(&mut self) -> f32 {
        self.store.rand()
    }

    pub fn range(&mut self, lo: f32, hi: f32) -> f32 {
        self.store.range(lo, hi)
    }

    /// A random unit vector in the ground plane.
    pub fn rand_dir(&mut self) -> Vec3 {
        let a = self.store.rand() * TAU;
        Vec3::new(a.cos(), 0.0, a.sin())
    }

    // ───────────────────────────── primitives ─────────────────────────────

    /// Any flipbook quad. Defaults: camera-facing, [`Layer::Main`], one play of the sequence at its
    /// painted rate, erosion over the last 40 % of the life, owner [`Owner::Mine`], class
    /// [`Class::Core`].
    pub fn sprite(&mut self, seq: Seq, at: Vec3) -> SpriteBuilder<'_> {
        let mut p = Particle::new(seq, at);
        p.ramp = painted_ramp(seq, Ramp::Kinetic);
        let phase = if seq.looped { self.store.rand() * seq.duration() } else { 0.0 };
        p.phase = phase;
        SpriteBuilder { store: &mut self.store, p, owner: Owner::Mine, class: Class::Core, ink: None }
    }

    /// A trail that follows an entity's world position (+ `offset`) until it despawns, then
    /// catches up with its last position and erodes away.
    pub fn trail_for(&mut self, entity: Entity, offset: Vec3, style: RibbonStyle, owner: Owner) -> Option<RibbonId> {
        self.ribbon_with(style, Source::Entity(entity, offset), Vec3::ZERO, owner)
    }

    /// A trail on a straight (or lobbed) flight: `from + vel × t − ½ g t²`. No history needed.
    pub fn trail_linear(
        &mut self,
        from: Vec3,
        vel: Vec3,
        gravity: f32,
        style: RibbonStyle,
        owner: Owner,
    ) -> Option<RibbonId> {
        let t0 = self.store.time;
        self.ribbon_with(style, Source::Linear { from, vel, gravity, t0 }, from, owner)
    }

    /// A ribbon whose head the caller moves ([`Fx::ribbon_to`]) and ends ([`Fx::ribbon_end`]).
    pub fn ribbon(&mut self, at: Vec3, style: RibbonStyle, owner: Owner) -> Option<RibbonId> {
        self.ribbon_with(style, Source::Manual, at, owner)
    }

    fn ribbon_with(&mut self, style: RibbonStyle, source: Source, head: Vec3, owner: Owner) -> Option<RibbonId> {
        let g = self.store.grant(owner, Class::Trail)?;
        let now = self.store.time;
        let mut r = Ribbon::new(style, source, head, now);
        r.own_alpha = g.alpha;
        r.cap = g.cap;
        r.keep = g.life;
        self.store.push_ribbon(r)
    }

    pub fn ribbon_to(&mut self, id: RibbonId, pos: Vec3) {
        if let Some(r) = self.store.ribbon_mut(id) {
            r.move_to(pos);
        }
    }

    /// Stop a ribbon: its tail catches up and erodes.
    pub fn ribbon_end(&mut self, id: RibbonId) {
        let now = self.store.time;
        if let Some(r) = self.store.ribbon_mut(id) {
            r.detach(now);
        }
    }

    /// Is the ribbon still alive?
    pub fn ribbon_alive(&self, id: RibbonId) -> bool {
        self.store.ribbons.get(id.index as usize).is_some_and(|s| s.generation == id.generation && s.ribbon.is_some())
    }

    /// An immediate-mode beam from `from` to `to`: call every frame while it fires (keyed by
    /// `key`, e.g. the player slot); it fades out once the calls stop. Two strips: the body
    /// bands and a white-hot core scrolling along it, plus a flickering contact star.
    pub fn beam(&mut self, key: u32, from: Vec3, to: Vec3, width: f32, ramp: Ramp, owner: Owner) {
        let body = RibbonStyle {
            tile: width * 3.0,
            scroll: 6.0,
            taper: 1.0,
            erode: 0.0,
            fade: 0.12,
            ..RibbonStyle::new(strip::BEAM_BODY, ramp, width, 1e4)
        };
        let core =
            RibbonStyle { strip: strip::BEAM_CORE, width: width * 0.4, scroll: 9.0, layer: Layer::Front, ..body };
        for (slot, style) in [(key * 2, body), (key * 2 + 1, core)] {
            self.immediate_line(slot, from, to, style, owner);
        }
        // The contact burst: a star that swaps shape at 20 Hz.
        let n = (self.store.time * 20.0) as u16;
        if self.store.rand() < 0.5 {
            self.sprite(seq::STAR4.nth(1 + n % 3), to)
                .radius(width * 0.9)
                .ramp(ramp)
                .rot(n as f32 * 1.7)
                .life(2.0 * F)
                .erode(1.0, 0.0)
                .owner(owner)
                .emit();
        }
    }

    /// A straight strip between two points, refreshed every frame by its caller (beams, loot
    /// beams, tethers). `key` identifies it across frames.
    pub fn immediate_line(&mut self, key: u32, from: Vec3, to: Vec3, style: RibbonStyle, owner: Owner) {
        let now = self.store.time;
        let found = self
            .store
            .ribbons
            .iter_mut()
            .find_map(|s| s.ribbon.as_mut().filter(|r| r.immediate && r.line_key == Some(key) && !r.is_detached()));
        if let Some(r) = found {
            r.line = Some((from, to));
            r.style = style;
            r.touched = true;
            return;
        }
        let Some(g) = self.store.grant(owner, Class::Core) else { return };
        let mut r = Ribbon::new(style, Source::Manual, to, now);
        r.own_alpha = g.alpha;
        r.cap = g.cap;
        r.immediate = true;
        r.line_key = Some(key);
        r.line = Some((from, to));
        self.store.push_ribbon(r);
    }

    /// A vertical light pillar (loot beams, revive, boons, the anvil kindling): a tiled strip from
    /// the floor to `height`, living `life` seconds.
    pub fn pillar(&mut self, at: Vec3, height: f32, width: f32, ramp: Ramp, life: f32, owner: Owner) {
        let class = if owner == Owner::World { Class::Danger } else { Class::Core };
        let Some(g) = self.store.grant(owner, class) else { return };
        let now = self.store.time;
        let style = RibbonStyle {
            tile: width * 4.0,
            scroll: 2.0,
            taper: 0.7,
            erode: 0.0,
            fade: (life * 0.4).max(0.15),
            layer: Layer::Main,
            ..RibbonStyle::new(strip::LOOT_BEAM, ramp, width, 1e4)
        };
        let base = Vec3::new(at.x, 0.05, at.z);
        let mut r = Ribbon::new(style, Source::Manual, base + Vec3::Y * height, now);
        r.own_alpha = g.alpha;
        r.cap = g.cap;
        r.line = Some((base, base + Vec3::Y * height));
        r.expires = Some(now + life * 0.6);
        self.store.push_ribbon(r);
    }

    /// A braided tether between two points for `life` seconds (revive, harpoon rope).
    pub fn tether(&mut self, key: u32, from: Vec3, to: Vec3, width: f32, ramp: Ramp, owner: Owner) {
        let style = RibbonStyle {
            tile: 1.4,
            scroll: 1.5,
            taper: 1.0,
            erode: 0.0,
            fade: 0.2,
            ..RibbonStyle::new(strip::TETHER_BRAID, ramp, width, 1e4)
        };
        self.immediate_line(key | 0x8000_0000, from, to, style, owner);
    }

    /// Any arc strip (smears, rings, walls).
    pub fn arc(&mut self, mut a: Arc, owner: Owner, class: Class) -> bool {
        let Some(g) = self.store.grant(owner, class) else { return false };
        a.alpha = Curve { a: a.alpha.a * g.alpha, b: a.alpha.b * g.alpha, c: a.alpha.c * g.alpha, mid: a.alpha.mid };
        a.cap = a.cap.min(g.cap);
        a.life *= g.life;
        a.world = a.center;
        self.store.push_arc(a);
        true
    }

    /// A melee smear (VFX_STYLE §7.4): the blade leads for 3 frames, the body holds, the tail
    /// breaks into dry-brush streaks.
    pub fn smear(&mut self, s: Smear) -> bool {
        let dir = Vec3::new(s.dir.x, 0.0, s.dir.z).normalize_or(Vec3::NEG_Z);
        let yaw = Quat::from_rotation_arc(Vec3::NEG_Z, dir);
        let basis = yaw * Quat::from_rotation_z(s.tilt);
        let mut a = Arc::new(s.strip, s.pivot, s.reach, s.width, s.life);
        a.follow = s.follow;
        a.basis = basis;
        a.start = -s.sweep * 0.5;
        a.sweep = s.sweep;
        a.sweep_anim = Sweep::Swing { lead: 0.3, retract: 0.55 };
        a.profile = Profile::Crescent { peak: 0.72 };
        a.ramp = s.ramp;
        a.gain = s.gain;
        a.erode = Vec2::new(0.25, 1.0);
        a.segments = 24;
        a.pull = 0.4;
        a.layer = Layer::Main;
        self.arc(a, s.owner, Class::Core)
    }

    /// A thin cut across a point (crits, executes, pierce wounds): an almost straight crescent of
    /// length `len` along `dir`, 3-6 frames.
    pub fn slash(&mut self, at: Vec3, dir: Vec3, len: f32, ramp: Ramp, owner: Owner) -> bool {
        let d = dir.normalize_or(Vec3::X);
        // A big radius makes a shallow crescent; the pivot sits off to the side of the cut.
        let r = len * 1.6;
        let sweep = len / r;
        let side = d.cross(Vec3::Y).normalize_or(Vec3::Z);
        let pivot = at + side * r;
        let mut a = Arc::new(strip::SLASH_THIN, pivot, r, len * 0.1, 6.0 * F);
        a.basis = Quat::from_rotation_arc(Vec3::NEG_Z, -side);
        a.start = -sweep * 0.5;
        a.sweep = sweep;
        a.sweep_anim = Sweep::Swing { lead: 0.35, retract: 0.5 };
        a.profile = Profile::Crescent { peak: 0.5 };
        a.ramp = ramp;
        a.gain = 1.3;
        a.erode = Vec2::new(0.4, 1.0);
        a.segments = 12;
        a.pull = 1.0;
        a.layer = Layer::Front;
        self.arc(a, owner, Class::Core)
    }

    /// A shockwave ring on the floor growing from `from` to `to` metres (a broken, tapered band —
    /// never a lone uniform ring, VFX_STYLE §2).
    pub fn ring(&mut self, at: Vec3, from: f32, to: f32, life: f32, band: Strip, ramp: Ramp, owner: Owner) -> bool {
        let mut a = Arc::new(band, Vec3::new(at.x, at.y.max(0.04), at.z), to, (to * 0.3).clamp(0.3, 2.2), life);
        a.radius = Curve::new(from, from + (to - from) * 0.8, to, 0.35);
        a.width = Curve::new(a.width.a * 1.4, a.width.a, a.width.a * 0.4, 0.5);
        a.repeats = (to * 1.2).round().clamp(3.0, 12.0);
        a.start = self.store.rand() * TAU;
        a.segments = ((to * 10.0) as u16).clamp(24, 96);
        a.erode = Vec2::new(0.2, 1.0);
        a.ramp = ramp;
        a.pull = 0.0;
        a.layer = Layer::Ground;
        self.arc(a, owner, Class::Core)
    }

    /// A dust wall riding a shock front out to `to` (VFX_STYLE §11 layer 5).
    pub fn dust_wall(
        &mut self,
        at: Vec3,
        from: f32,
        to: f32,
        height: f32,
        life: f32,
        ramp: Ramp,
        owner: Owner,
    ) -> bool {
        let mut a = Arc::new(strip::DUST_WALL, Vec3::new(at.x, 0.02, at.z), to, height, life);
        a.radius = Curve::new(from, from + (to - from) * 0.85, to, 0.4);
        a.width = Curve::new(height * 0.4, height, height * 0.7, 0.4);
        a.profile = Profile::Wall { flare: height * 0.35 };
        a.repeats = (to * 1.5).round().clamp(3.0, 14.0);
        a.start = self.store.rand() * TAU;
        a.segments = ((to * 10.0) as u16).clamp(24, 96);
        a.erode = Vec2::new(0.3, 1.0);
        a.ramp = ramp;
        a.pull = 0.0;
        a.layer = Layer::Back;
        self.arc(a, owner, Class::Smoke)
    }

    /// A lightning strike between two points (VFX_STYLE §2 "Bolt"): the painted strip stretched
    /// between the nodes, strobing between 2 shapes at 30 Hz, with a thin branch on long hops.
    pub fn bolt(&mut self, from: Vec3, to: Vec3, ramp: Ramp, width: f32, life: f32, owner: Owner) {
        let d = to - from;
        let len = d.length();
        if len < 0.05 {
            return;
        }
        let first = (self.store.rand() * 5.0) as u16;
        self.sprite(seq::BOLT.frames_from(first, 2), from)
            .size2(len, width)
            .toward(d)
            .ramp(ramp)
            .play(Play::Fps(30.0))
            .life(life)
            .gain(1.2)
            .erode(0.5, 1.0)
            .pull(0.6)
            .layer(Layer::Front)
            .owner(owner)
            .emit();
        if len > 3.0 {
            // A branch off the middle, thinner and shorter.
            let t = self.store.range(0.3, 0.6);
            let side = d.cross(Vec3::Y).normalize_or(Vec3::X) * self.store.range(-1.0, 1.0);
            let root = from + d * t;
            let tip = root + (d.normalize() * 0.6 + side).normalize_or(Vec3::X) * len * 0.3;
            self.sprite(seq::BOLT.frames_from(6, 2), root)
                .size2(root.distance(tip), width * 0.6)
                .toward(tip - root)
                .ramp(ramp)
                .play(Play::Fps(30.0))
                .life(life * 0.7)
                .erode(0.4, 1.0)
                .pull(0.6)
                .layer(Layer::Front)
                .owner(owner)
                .class(Class::Secondary)
                .emit();
        }
    }

    /// Ground paint (scorch, stains, cracks) for `life` seconds, fading by erosion.
    pub fn decal(&mut self, decal: Decal, at: Vec3, radius: f32, ramp: Ramp, life: f32, owner: Owner) -> bool {
        let rot = self.store.rand() * TAU;
        self.decal_seq(decal.seq(), at, radius, rot, ramp, life, owner)
    }

    /// Any still or flipbook laid on the floor as a decal.
    #[allow(clippy::too_many_arguments)]
    pub fn decal_seq(
        &mut self,
        seq: Seq,
        at: Vec3,
        radius: f32,
        rot: f32,
        ramp: Ramp,
        life: f32,
        owner: Owner,
    ) -> bool {
        self.sprite(seq, Vec3::new(at.x, 0.03, at.z))
            .radius(radius)
            .rot(rot)
            .ground()
            .layer(Layer::Decal)
            .ramp(ramp)
            .life(life)
            .alpha_curve(Curve::new(0.0, 0.8, 0.8, 0.03))
            .cool(1.2)
            .erode(0.5, 1.0)
            .class(Class::Decal)
            .owner(owner)
            .play(if seq.frames > 1 && seq.fps > 0.0 { Play::Painted } else { Play::Frame(0) })
            .emit()
    }

    /// A point-light flash: fast in, slow out. Only your own and the world's effects spill light.
    pub fn light(&mut self, at: Vec3, color: Color, intensity: f32, range: f32, life: f32, owner: Owner) {
        if !matches!(owner, Owner::Mine | Owner::World) {
            return;
        }
        if self.store.flashes.len() >= 64 {
            return;
        }
        self.store.flashes.push(Flash::new(at, color, intensity, range, life));
    }

    // ───────────────────────────── recipes ─────────────────────────────

    /// Hit punctuation (VFX_STYLE §10).
    pub fn impact(&mut self, hit: Hit) {
        let Hit { at, dir, ramp, size, kind, owner, body } = hit;
        let pull = body + 0.2;
        let rot = self.store.range(-0.4, 0.4);
        match kind {
            HitKind::Plain | HitKind::Heavy => {
                let star = hit_star(ramp);
                self.sprite(star, at)
                    .radius(size)
                    .ramp(ramp)
                    .rot(rot)
                    .life(if kind == HitKind::Heavy { 10.0 * F } else { 6.0 * F })
                    .play(Play::Life)
                    .erode(0.5, 1.0)
                    .pull(pull)
                    .ink_backed()
                    .owner(owner)
                    .emit();
                let n = if kind == HitKind::Heavy { 5 } else { 3 };
                self.sparks(at, dir, n, 5.0, ramp, owner);
                if kind == HitKind::Heavy {
                    self.impact_frame(at, size * 1.6, pull, owner);
                    self.light(at + Vec3::Y * 0.4, ramp.light(), 90_000.0 * size, 4.0 + size * 2.0, 0.22, owner);
                }
            }
            HitKind::Crit => {
                let travel = if dir.length_squared() > 1e-4 { dir } else { self.rand_dir() };
                // The slash crosses the hit 62° off the travel direction.
                let slash = Quat::from_rotation_y(62f32.to_radians()) * travel;
                self.slash(at + Vec3::Y * 0.1, slash, size * 4.5, Ramp::ZoneGold, owner);
                self.sprite(seq::STAR4, at)
                    .radius(size * 1.2)
                    .ramp(Ramp::Radiant)
                    .value(value::HOT)
                    .rot(rot)
                    .life(5.0 * F)
                    .play(Play::Life)
                    .pull(pull)
                    .ink_backed_by(1.35, FRAC_PI_2 * 0.5)
                    .layer(Layer::Front)
                    .owner(owner)
                    .emit();
                self.shards(at, 5, 5.5, Ramp::ZoneGold, 0.16, owner);
                self.impact_frame(at, size * 1.4, pull, owner);
                self.light(at + Vec3::Y * 0.4, Ramp::Radiant.light(), 60_000.0, 4.0, 0.18, owner);
            }
            HitKind::Precision => {
                let mut a = Arc::new(strip::TICK_RING, at, size * 2.4, size * 0.5, 5.0 * F);
                a.basis = Quat::from_rotation_arc(Vec3::Y, self.store.cam.back);
                a.radius = Curve::new(size * 2.4, size * 1.0, size * 0.35, 0.6);
                a.repeats = 4.0;
                a.ramp = Ramp::Storm;
                a.gain = 1.3;
                a.pull = pull;
                a.layer = Layer::Front;
                a.erode = Vec2::new(0.6, 1.0);
                self.arc(a, owner, Class::Core);
                self.sprite(seq::GLINT.nth(0), at)
                    .radius(size * 0.9)
                    .ramp(Ramp::Storm)
                    .life(6.0 * F)
                    .pull(pull)
                    .owner(owner)
                    .emit();
            }
        }
    }

    /// The white impact frame: a hot star over a larger ink star for 2 frames. Your own heavy hits,
    /// crits and kills only (the budget drops it for anyone else).
    pub fn impact_frame(&mut self, at: Vec3, radius: f32, pull: f32, owner: Owner) {
        // No two impact frames inside 0.25 s: the second is dropped (VFX_STYLE §20.3).
        if owner != Owner::World && self.store.time - self.store.last_impact_frame < 0.25 {
            return;
        }
        if self.store.grant(owner, Class::Accent).is_none() {
            return;
        }
        self.store.last_impact_frame = self.store.time;
        let rot = self.store.rand() * TAU;
        self.sprite(seq::STAR9.nth(0), at)
            .radius(radius)
            .ramp(Ramp::Mono)
            .value(value::HOT)
            .rot(rot)
            .life(2.0 * F)
            .erode(1.0, 0.0)
            .pull(pull + 0.3)
            .ink_backed_by(1.35, 0.14)
            .layer(Layer::Top)
            .class(Class::Accent)
            .owner(owner)
            .emit();
    }

    /// The layered burst (VFX_STYLE §11): light spill, impact frame (own), the element's painted
    /// blast and smoke crown, a shock front and dust wall at exactly `radius`, shrapnel, sparks
    /// and the element's scorch.
    pub fn burst(&mut self, ramp: Ramp, at: Vec3, radius: f32, owner: Owner) {
        let r = radius.max(0.3);
        let ground = Vec3::new(at.x, 0.0, at.z);
        let heavy = r >= 1.2;
        // 1. light spill
        self.light(ground + Vec3::Y * (0.6 + r * 0.3), ramp.light(), 140_000.0 * r, r * 2.5 + 2.0, 0.28, owner);
        // 2. impact frame
        if heavy {
            self.impact_frame(ground + Vec3::Y * 0.6, r * 0.9, 0.2, owner);
        }
        // 3-4. the blast and smoke crown (one painted flipbook per element)
        let seq = burst_seq(ramp);
        let rot = self.store.range(-0.15, 0.15);
        self.sprite(seq, ground + Vec3::Y * 0.25)
            .radius(r)
            .ramp(painted_ramp(seq, ramp))
            .rot(rot)
            .erode(0.75, 0.8)
            .pull(0.2)
            .owner(owner)
            .emit();
        // 5. shock front
        self.ring(ground, r * 0.3, r, 10.0 * F, strip::SHOCK_FRONT, ramp, owner);
        if heavy {
            self.dust_wall(ground, r * 0.4, r, (0.25 * r).clamp(0.2, 0.9), 22.0 * F, Ramp::Dust, owner);
        }
        // 6-7. shrapnel and sparks
        let n = (4.0 + r * 2.0) as u32;
        self.shards(ground + Vec3::Y * 0.4, n.min(9), 4.0 + r * 2.0, ramp, 0.14 + r * 0.03, owner);
        self.sparks(ground + Vec3::Y * 0.4, Vec3::ZERO, (6.0 + r * 1.5).min(10.0) as u32, 6.0 + r * 2.5, ramp, owner);
        // 8. the element's lingering mark
        let (decal, dr) = match ramp {
            Ramp::Storm => (None, r),
            Ramp::Void => (Some(Decal::InkStainA), r * 0.7),
            Ramp::Plague => (Some(Decal::PlagueStainA), r * 0.8),
            Ramp::Flame => (Some(Decal::BurnPatch), r * 0.8),
            Ramp::Unmade => (Some(Decal::IchorStainA), r * 0.8),
            _ => (Some(if self.store.rand() < 0.5 { Decal::ScorchA } else { Decal::ScorchB }), r * 0.8),
        };
        match decal {
            Some(d) => {
                self.decal(d, ground, dr, ramp, 3.0, owner);
            }
            None => {
                let v = (self.store.rand() * 4.0) as u16;
                let rot = self.store.rand() * TAU;
                self.decal_seq(seq::STORM_LICHTENBERG.nth(v), ground, dr, rot, Ramp::Storm, 2.0, owner);
            }
        }
        // Element secondaries.
        match ramp {
            Ramp::Flame => self.embers(ground + Vec3::Y * 0.3, (4.0 + r * 2.0) as u32, r * 0.6, owner),
            Ramp::Storm => {
                for _ in 0..3 {
                    let d = self.rand_dir();
                    let len = r * self.store.range(0.8, 1.2);
                    self.bolt(
                        ground + Vec3::Y * 0.5,
                        ground + d * len + Vec3::Y * 0.2,
                        Ramp::Storm,
                        0.45,
                        8.0 * F,
                        owner,
                    );
                }
            }
            Ramp::Plague => {
                for _ in 0..(3.0 + r) as u32 {
                    let d = self.rand_dir();
                    let v = d * self.store.range(2.5, 5.0) + Vec3::Y * self.store.range(3.0, 5.0);
                    let variant = (self.store.rand() * 4.0) as u16;
                    self.sprite(seq::TEARDROP.nth(variant), ground + Vec3::Y * 0.5)
                        .size(0.35)
                        .ramp(Ramp::Plague)
                        .vel(v)
                        .gravity(14.0)
                        .streak(0.08)
                        .life(0.6)
                        .play(Play::Frame(0))
                        .class(Class::Secondary)
                        .owner(owner)
                        .emit();
                }
            }
            _ => {}
        }
    }

    /// The muzzle flash of a shot (VFX_STYLE §7.1, §8): the style's petal / directional shape,
    /// rotated ±15° per shot so a stream never looks stamped, 2-4 frames, a light blink.
    pub fn muzzle(&mut self, style: ProjectileStyle, element: DamageType, at: Vec3, dir: Vec3, owner: Owner) {
        use ProjectileStyle as S;
        let ramp = Ramp::of(element);
        let (seq, len) = match style {
            S::Needle => (seq::MUZZLE_FLICKER3, 0.55),
            S::Slug => (seq::MUZZLE_SPIKE, 1.3),
            S::Shell | S::Boulder | S::Globe => (seq::PETAL_FORWARD_FAN, 1.3),
            S::Pellet => (seq::PETAL_SUNBURST, 1.8),
            S::Orb => (seq::MUZZLE_PETAL_BLOOM, 0.9),
            S::Arrow | S::Bolt | S::Blade => (seq::MUZZLE_FLICKER3, 0.6),
            S::Coin | S::Shard => (seq::PETAL_CROSS, 0.6),
            S::Arc => (seq::MUZZLE_RAIL, 1.0),
            S::Fist => return,
        };
        let roll = self.store.range(-0.26, 0.26);
        let aspect = seq.sheet.cell_aspect();
        let d = if dir.length_squared() > 1e-5 { dir } else { Vec3::NEG_Z };
        self.sprite(seq, at)
            .size2(len, len / aspect)
            .toward(d)
            .rot(roll)
            .ramp(ramp)
            .play(Play::Life)
            .life(if seq.fps >= 60.0 { 4.0 * F } else { 6.0 * F })
            .erode(0.5, 0.8)
            .pull(0.5)
            .layer(Layer::Front)
            .owner(owner)
            .emit();
        if matches!(style, S::Shell | S::Boulder | S::Globe) {
            self.smoke(at + d * 0.4, 3, 0.35, Ramp::Dust, owner);
        }
        self.light(at, ramp.light(), 25_000.0, 3.5, 0.08, owner);
    }

    /// A kill burst in a faction's (or element's) style (VFX_STYLE §15.3): a white flash on an ink
    /// star, the painted death flipbook, shards, droplets and a stain.
    pub fn death(&mut self, ramp: Ramp, at: Vec3, radius: f32, owner: Owner) {
        let r = radius.max(0.35);
        let ground = Vec3::new(at.x, 0.0, at.z);
        if owner == Owner::Mine {
            self.impact_frame(ground + Vec3::Y * (0.4 + r * 0.5), r * 0.7, r, owner);
        }
        let seq = burst_seq(ramp);
        self.sprite(seq, ground + Vec3::Y * 0.2)
            .radius(r * 1.3)
            .ramp(painted_ramp(seq, ramp))
            .erode(0.75, 0.8)
            .pull(0.3)
            .owner(owner)
            .emit();
        self.shards(ground + Vec3::Y * (0.3 + r * 0.4), 5, 4.5, ramp, 0.14 + r * 0.05, owner);
        let stain = match ramp {
            Ramp::Unmade => Decal::IchorStainA,
            Ramp::GodworksGold | Ramp::GodworksEmber => Decal::Soot,
            Ramp::Plague => Decal::PlagueStainB,
            Ramp::Void => Decal::InkStainB,
            _ => Decal::ScorchC,
        };
        self.decal(stain, ground, r * 1.1, ramp, 2.0, owner);
    }

    /// Kill motes: `n` glints arcing from `from` to `target` (+ 1 m) over half a second.
    pub fn motes(&mut self, from: Vec3, target: Entity, n: u32, ramp: Ramp, owner: Owner) {
        for i in 0..n {
            let delay = i as f32 * 0.06;
            let h = self.store.range(2.2, 3.4);
            let start = from + self.rand_dir() * 0.3 + Vec3::Y * 0.6;
            self.sprite(seq::GLINT.nth(i as u16 % 4), start)
                .size(0.34)
                .ramp(ramp)
                .gain(1.3)
                .path(Vec3::Y * 1.0, Some(target), h)
                .life(0.5 + delay)
                .erode(0.95, 0.5)
                .spin(6.0)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
    }

    /// Chunky sparks flying out (along `dir` when given), streaked by their speed, falling with
    /// gravity.
    pub fn sparks(&mut self, at: Vec3, dir: Vec3, n: u32, speed: f32, ramp: Ramp, owner: Owner) {
        let Some(g) = self.store.grant(owner, Class::Secondary) else { return };
        let n = g.n(n).max(1);
        let back = if dir.length_squared() > 1e-4 { -dir.normalize() } else { Vec3::ZERO };
        for _ in 0..n {
            let d = (self.rand_dir() + back * 0.8 + Vec3::Y * self.store.range(0.3, 1.1)).normalize_or(Vec3::Y);
            let v = d * speed * self.store.range(0.5, 1.2);
            let variant = (self.store.rand() * 8.0) as u16;
            let life = self.store.range(0.2, 0.4);
            self.sprite(seq::SPARK.nth(variant), at)
                .size(0.14)
                .vel(v)
                .gravity(12.0)
                .drag(2.5)
                .streak(0.05)
                .ramp(ramp)
                .life(life)
                .erode(0.6, 1.0)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
    }

    /// Shards (kites) flung up and out, tumbling, landing and shrinking away.
    pub fn shards(&mut self, at: Vec3, n: u32, speed: f32, ramp: Ramp, size: f32, owner: Owner) {
        let Some(g) = self.store.grant(owner, Class::Secondary) else { return };
        let n = g.n(n).max(1);
        for _ in 0..n {
            let d = self.rand_dir() + Vec3::Y * self.store.range(0.6, 1.4);
            let variant = (self.store.rand() * 8.0) as u16;
            let spin = self.store.range(-14.0, 14.0);
            let rot = self.store.rand() * TAU;
            let sz = size * self.store.range(0.8, 1.3);
            let v = d * speed * self.store.range(0.6, 1.1);
            let life = self.store.range(0.5, 0.75);
            self.sprite(seq::SHARD.nth(variant), at)
                .size(sz)
                .vel(v)
                .gravity(16.0)
                .bounce(0.25)
                .spin(spin)
                .rot(rot)
                .ramp(ramp)
                .life(life)
                .scale(Curve::new(1.0, 1.0, 0.0, 0.7))
                .erode(0.7, 0.6)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
    }

    /// Ink smoke puffs rising, growing and thinning, rim-lit (VFX_STYLE §2 "Puff").
    pub fn smoke(&mut self, at: Vec3, n: u32, radius: f32, ramp: Ramp, owner: Owner) {
        let Some(g) = self.store.grant(owner, Class::Smoke) else { return };
        let n = g.n(n).max(1);
        for _ in 0..n {
            let col = (self.store.rand() * 8.0) as u16;
            let off = self.rand_dir() * radius * self.store.range(0.2, 0.8);
            let life = self.store.range(0.5, 0.8) * g.life;
            let rr = radius * self.store.range(0.7, 1.1);
            let v = off * 1.5 + Vec3::Y * self.store.range(0.8, 1.6);
            self.sprite(seq::SMOKE.in_column(col), at + off)
                .radius(rr)
                .vel(v)
                .drag(2.0)
                .ramp(ramp)
                .play(Play::Life)
                .life(life)
                .scale(Curve::new(0.6, 1.1, 1.25, 0.4))
                .cool(0.45)
                .erode(0.35, 1.0)
                .layer(Layer::Back)
                .class(Class::Smoke)
                .owner(owner)
                .emit();
        }
    }

    /// Embers: small hot motes that float up, flicker and die (Flame's secondary).
    pub fn embers(&mut self, at: Vec3, n: u32, spread: f32, owner: Owner) {
        let Some(g) = self.store.grant(owner, Class::Secondary) else { return };
        let n = g.n(n).max(1);
        for _ in 0..n {
            let off = self.rand_dir() * spread * self.store.rand();
            let sz = self.store.range(0.12, 0.22);
            let v = off * 0.8 + Vec3::Y * self.store.range(1.5, 3.2);
            let life = self.store.range(0.6, 1.1);
            self.sprite(Mote::Ember.seq(), at + off)
                .size(sz)
                .vel(v)
                .gravity(-1.0)
                .drag(1.2)
                .ramp(Ramp::Flame)
                .gain(1.4)
                .life(life)
                .alpha_curve(Curve::new(1.0, 0.6, 1.0, 0.5))
                .erode(0.6, 1.0)
                .layer(Layer::Front)
                .class(Class::Secondary)
                .owner(owner)
                .emit();
        }
    }

    /// Flame tongues rooted on the floor around a point (burning ground, geysers), rising and
    /// curling for `life` seconds.
    pub fn tongues(&mut self, at: Vec3, n: u32, radius: f32, height: f32, life: f32, owner: Owner) {
        let seqs = [seq::FLAME_NARROW, seq::FLAME_MEDIUM, seq::FLAME_CLUMP];
        for i in 0..n {
            let a = i as f32 / n as f32 * TAU + self.store.range(-0.3, 0.3);
            let off = Vec3::new(a.cos(), 0.0, a.sin()) * radius * self.store.range(0.3, 1.0);
            let s = seqs[(self.store.rand() * 3.0) as usize % 3];
            let h = height * self.store.range(0.7, 1.2);
            let l = life * self.store.range(0.8, 1.1);
            self.sprite(s, Vec3::new(at.x, 0.02, at.z) + off)
                .size(h)
                .ramp(Ramp::Flame)
                .life(l)
                .scale(Curve::new(0.3, 1.0, 0.6, 0.15))
                .erode(0.6, 1.0)
                .pull(0.3)
                .owner(owner)
                .emit();
        }
    }

    /// A spiral of `n` points (radians) evenly around a circle, starting at a random angle.
    pub fn around(&mut self, n: u32) -> impl Iterator<Item = f32> + use<> {
        let start = self.store.rand() * TAU;
        (0..n).map(move |i| start + i as f32 / n.max(1) as f32 * TAU)
    }
}

/// A half-turn, for recipes flipping smears.
pub const HALF_TURN: f32 = PI;
