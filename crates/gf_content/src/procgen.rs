//! Procedural arenas: every run composes fresh layouts from the run seed, so no two runs share a
//! map (§9 "procedural room composition"). Arenas are sized for horde play: open NIMRODS-scale
//! fields where the camera follows you and the swarm pours in from off-screen, broken up by ruins
//! that create lanes and chokepoints instead of corridors.
//!
//! **Deterministic across machines.** The host replicates only a 32-bit seed per room and every
//! client and bot rebuilds the identical layout. Geometry is fed exclusively by integer RNG output
//! and IEEE-exact arithmetic (+ − × ÷, no trigonometry), and every coordinate is quantized to
//! 1/8 unit, so a Windows host and a Linux client always agree.
//!
//! Authored templates still matter: a template supplies the room kind, biome, encounter tuning
//! and decor style; boss and mini-boss arenas stay hand-built (seed 0).

use crate::db::ContentDb;
use crate::schema::*;
use gf_core::movement::Obstacle;
use gf_core::rng::GfRng;
use glam::Vec2;

/// Rooms of these kinds are generated; the rest use their authored template verbatim.
pub fn is_generated_kind(kind: RoomKind) -> bool {
    matches!(kind, RoomKind::Combat | RoomKind::Elite | RoomKind::Anvil | RoomKind::Treasure)
}

/// The layout the host and every client use for `template` + `seed` (seed 0 = authored as-is).
pub fn resolve_room(db: &ContentDb, template: u16, seed: u32) -> RoomDef {
    let Some(t) = db.rooms.try_get(template).or_else(|| db.rooms.try_get(0)) else {
        return RoomDef::placeholder();
    };
    if seed == 0 || !is_generated_kind(t.kind) { t.clone() } else { generate(t, seed) }
}

/// Mix the run seed and the room counter into a non-zero room seed.
pub fn room_seed(run_seed: u64, serial: u32) -> u32 {
    let mut z = run_seed ^ (serial as u64 + 1).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^= z >> 31;
    (z as u32) | 1
}

fn key_hash(s: &str) -> u64 {
    s.bytes().fold(0xcbf2_9ce4_8422_2325u64, |h, b| (h ^ b as u64).wrapping_mul(0x0000_0100_0000_01b3))
}

#[inline]
fn q(v: f32) -> f32 {
    (v * 8.0).round() / 8.0
}

#[inline]
fn qv(v: Vec2) -> Vec2 {
    Vec2::new(q(v.x), q(v.y))
}

/// Conservative bounding circle of an obstacle.
fn bounds(o: &Obstacle) -> (Vec2, f32) {
    match *o {
        Obstacle::Circle { center, radius } => (center, radius),
        Obstacle::Box { center, half } => (center, half.length()),
    }
}

/// Clear floor kept between features so the horde flows and players can always kite.
const LANE: f32 = 2.8;
/// Clear margin inside the arena rim.
const RIM: f32 = 3.0;

fn fits(o: &Obstacle, half: Vec2, keep: &[(Vec2, f32)], placed: &[Obstacle]) -> bool {
    let (c, r) = bounds(o);
    let (ex, ey) = match *o {
        Obstacle::Circle { radius, .. } => (radius, radius),
        Obstacle::Box { half, .. } => (half.x, half.y),
    };
    if c.x.abs() + ex > half.x - RIM || c.y.abs() + ey > half.y - RIM {
        return false;
    }
    if keep.iter().any(|(k, kr)| c.distance(*k) < r + kr) {
        return false;
    }
    placed.iter().all(|p| {
        let (pc, pr) = bounds(p);
        c.distance(pc) >= r + pr + LANE
    })
}

/// Generate a layout from a template. Pure and deterministic in (`template`, `seed`).
pub fn generate(t: &RoomDef, seed: u32) -> RoomDef {
    let mut rng = GfRng::new(seed as u64 ^ key_hash(&t.key).rotate_left(17));
    let (hx, hy) = match t.kind {
        RoomKind::Combat | RoomKind::Elite => (rng.range_f32(40.0, 52.0), rng.range_f32(27.0, 34.0)),
        RoomKind::Anvil => (rng.range_f32(30.0, 36.0), rng.range_f32(21.0, 25.0)),
        _ => (rng.range_f32(24.0, 30.0), rng.range_f32(17.0, 21.0)),
    };
    let half = qv(Vec2::new(hx, hy));
    let player_spawn = qv(Vec2::new(0.0, -half.y + 6.0));
    let gate_y = half.y - 1.5;
    let spread = rng.range_f32(0.36, 0.48);
    let exits = vec![
        qv(Vec2::new(-half.x * spread, gate_y)),
        qv(Vec2::new(0.0, gate_y)),
        qv(Vec2::new(half.x * spread, gate_y)),
    ];
    let anvil = (t.kind == RoomKind::Anvil).then_some(Vec2::ZERO);

    // Keep-out: the entrance, the central plaza (mosaic / anvil) and the gates.
    let plaza = if anvil.is_some() { 9.0 } else { 7.5 };
    let mut keep: Vec<(Vec2, f32)> = vec![(player_spawn, 7.0), (Vec2::ZERO, plaza)];
    keep.extend(exits.iter().map(|e| (*e, 5.0)));

    // ── ruins ──
    let density = match t.kind {
        RoomKind::Treasure => 260.0,
        RoomKind::Anvil => 190.0,
        _ => 150.0,
    };
    let target = ((half.x * half.y * 4.0) / density) as usize;
    let mut obstacles: Vec<Obstacle> = Vec::new();
    let mut decor: Vec<Decor> = Vec::new();
    let mut attempts = 0;
    while obstacles.len() < target && attempts < target * 40 {
        attempts += 1;
        let at = Vec2::new(
            rng.range_f32(-half.x + RIM + 2.0, half.x - RIM - 2.0),
            rng.range_f32(-half.y + RIM + 2.0, half.y - RIM - 2.0),
        );
        let roll = rng.f32();
        let group: Vec<(Obstacle, Option<Decor>)> = if roll < 0.3 {
            // Colonnade fragment: a row of standing pillars (lanes between them are too tight for
            // heroes but the swarm squeezes through: a natural chokepoint).
            let n = rng.range_u32(3, 6);
            let r = q(rng.range_f32(0.7, 1.05));
            let gap = rng.range_f32(3.4, 4.4);
            let horizontal = rng.chance(0.6);
            let height = q(rng.range_f32(3.5, 6.0));
            (0..n)
                .map(|i| {
                    let o = (i as f32 - (n - 1) as f32 * 0.5) * gap;
                    let c = qv(if horizontal { at + Vec2::new(o, 0.0) } else { at + Vec2::new(0.0, o) });
                    // Some pillars are broken stumps.
                    let h = if rng.chance(0.3) { q(height * rng.range_f32(0.25, 0.5)) } else { height };
                    (Obstacle::Circle { center: c, radius: r }, Some(Decor::Pillar { at: c, radius: r, height: h }))
                })
                .collect()
        } else if roll < 0.58 {
            // Ruined wall run.
            let len = rng.range_f32(2.5, 6.5);
            let th = rng.range_f32(0.6, 0.95);
            let h = if rng.chance(0.5) { Vec2::new(len, th) } else { Vec2::new(th, len) };
            vec![(Obstacle::Box { center: qv(at), half: qv(h) }, None)]
        } else if roll < 0.84 {
            // Boulder / rubble mound.
            vec![(Obstacle::Circle { center: qv(at), radius: q(rng.range_f32(1.3, 2.6)) }, None)]
        } else {
            // Plinth or toppled altar.
            let s = rng.range_f32(1.5, 2.7);
            let h = Vec2::new(s, s * rng.range_f32(0.65, 1.0));
            vec![(Obstacle::Box { center: qv(at), half: qv(h) }, None)]
        };
        if group.iter().all(|(o, _)| fits(o, half, &keep, &obstacles)) {
            for (o, d) in group {
                obstacles.push(o);
                decor.extend(d);
            }
        }
    }

    // ── set dressing (visual only) ──
    let clear_of = |p: Vec2, r: f32, obstacles: &[Obstacle]| {
        obstacles.iter().all(|o| {
            let (c, cr) = bounds(o);
            p.distance(c) >= cr + r
        })
    };
    // Braziers frame the plaza and the gates; more burn out in the ruins.
    for (sx, sy) in [(-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)] {
        decor.push(Decor::Brazier { at: qv(Vec2::new(sx * (plaza + 1.5), sy * (plaza * 0.72))) });
    }
    for e in &exits {
        decor.push(Decor::Brazier { at: qv(*e + Vec2::new(-3.2, -1.0)) });
        decor.push(Decor::Brazier { at: qv(*e + Vec2::new(3.2, -1.0)) });
    }
    let braziers = rng.range_u32(5, 10);
    for _ in 0..braziers * 6 {
        if decor.iter().filter(|d| matches!(d, Decor::Brazier { .. })).count() >= 10 + braziers as usize {
            break;
        }
        let p = qv(Vec2::new(rng.range_f32(-half.x + 3.0, half.x - 3.0), rng.range_f32(-half.y + 3.0, half.y - 3.0)));
        if clear_of(p, 1.5, &obstacles) && keep.iter().all(|(k, kr)| p.distance(*k) >= *kr * 0.8) {
            decor.push(Decor::Brazier { at: p });
        }
    }
    // Lava cracks: jagged polylines wandering across the floor.
    let cracks = rng.range_u32(6, 12);
    for _ in 0..cracks {
        let mut p = Vec2::new(rng.range_f32(-half.x + 2.0, half.x - 2.0), rng.range_f32(-half.y + 2.0, half.y - 2.0));
        let mut dir = Vec2::new(rng.range_f32(-1.0, 1.0), rng.range_f32(-1.0, 1.0));
        let width = q(rng.range_f32(0.25, 0.6));
        for _ in 0..rng.range_u32(2, 5) {
            dir = (dir + Vec2::new(rng.range_f32(-0.7, 0.7), rng.range_f32(-0.7, 0.7))).normalize_or(Vec2::X);
            let len = rng.range_f32(2.5, 6.0);
            let next = (p + dir * len).clamp(-half + Vec2::splat(1.0), half - Vec2::splat(1.0));
            decor.push(Decor::LavaCrack { from: qv(p), to: qv(next), width });
            p = next;
        }
    }
    for _ in 0..rng.range_u32(2, 5) {
        let p = qv(Vec2::new(rng.range_f32(-half.x + 4.0, half.x - 4.0), rng.range_f32(-half.y + 4.0, half.y - 4.0)));
        if clear_of(p, 2.0, &obstacles) {
            decor.push(Decor::BrokenAnvil { at: p, scale: q(rng.range_f32(0.8, 1.4)) });
        }
    }

    // ── encounter: bigger fields hold bigger hordes ──
    let mut encounter = t.encounter.clone();
    if matches!(t.kind, RoomKind::Combat | RoomKind::Elite) {
        encounter.budget *= 1.35;
        encounter.duration *= 1.15;
        encounter.rate_start *= 1.3;
        encounter.rate_end *= 1.3;
        encounter.max_alive = ((encounter.max_alive as f32) * 1.4).min(360.0) as u32;
    }
    // The swarm arrives from just off-screen around the party, with some pouring over the rim.
    let spawn_zones = vec![
        SpawnZone::Around { min: 23.0, max: 31.0 },
        SpawnZone::Around { min: 23.0, max: 31.0 },
        SpawnZone::Edges { margin: 1.5 },
    ];

    RoomDef {
        key: format!("{}~{seed:08x}", t.key),
        biome: t.biome.clone(),
        kind: t.kind,
        phase: t.phase,
        half_extents: half,
        obstacles,
        player_spawn,
        anvil,
        exits,
        spawn_zones,
        encounter,
        decor,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn template(kind: RoomKind) -> RoomDef {
        RoomDef { key: "test_room".into(), kind, ..RoomDef::placeholder() }
    }

    #[test]
    fn same_seed_same_room_different_seed_different_room() {
        let t = template(RoomKind::Combat);
        assert_eq!(generate(&t, 42), generate(&t, 42));
        assert_ne!(generate(&t, 42).obstacles, generate(&t, 43).obstacles);
    }

    #[test]
    fn arenas_are_horde_sized_and_open() {
        for seed in 1..60u32 {
            let r = generate(&template(RoomKind::Combat), seed);
            assert!(r.half_extents.x >= 40.0 && r.half_extents.y >= 27.0, "{:?}", r.half_extents);
            assert!(r.obstacles.len() >= 15, "seed {seed}: only {} features", r.obstacles.len());
            for o in &r.obstacles {
                let (c, rad) = bounds(o);
                // Entrance, plaza and gates stay clear.
                assert!(c.distance(r.player_spawn) >= rad + 7.0 - 1e-3, "seed {seed}: spawn blocked");
                assert!(c.length() >= rad + 7.5 - 1e-3, "seed {seed}: plaza blocked");
                for e in &r.exits {
                    assert!(c.distance(*e) >= rad + 5.0 - 1e-3, "seed {seed}: gate blocked");
                }
                // Inside the rim.
                assert!(c.x.abs() < r.half_extents.x && c.y.abs() < r.half_extents.y);
            }
        }
    }

    #[test]
    fn coordinates_are_quantized_for_cross_platform_agreement() {
        let r = generate(&template(RoomKind::Anvil), 7);
        assert_eq!(r.anvil, Some(Vec2::ZERO));
        for o in &r.obstacles {
            let (c, rad) = bounds(o);
            for v in [c.x, c.y] {
                assert_eq!(v * 8.0, (v * 8.0).round(), "{v} not on the 1/8 grid");
            }
            if let Obstacle::Circle { .. } = o {
                assert_eq!(rad * 8.0, (rad * 8.0).round());
            }
        }
    }

    #[test]
    fn room_seeds_are_nonzero_and_vary() {
        let a: Vec<u32> = (0..32).map(|i| room_seed(7, i)).collect();
        assert!(a.iter().all(|s| *s != 0));
        let mut b = a.clone();
        b.sort_unstable();
        b.dedup();
        assert_eq!(a.len(), b.len());
    }
}
