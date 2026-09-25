//! Dev harness: `cargo run -p gf_sim --release --example botrun -- --bots 4 --phase ea --minutes 40`

use gf_content::{ContentDb, Phase, find_content_dir};
use gf_core::aim::AimMode;
use gf_net::{Loadout, NetConditions};
use gf_sim::SimConfig;
use gf_sim::bot::run_headless;
use std::sync::Arc;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let get = |k: &str| args.iter().position(|a| a == k).and_then(|i| args.get(i + 1)).cloned();
    let bots: usize = get("--bots").and_then(|v| v.parse().ok()).unwrap_or(1);
    let minutes: u32 = get("--minutes").and_then(|v| v.parse().ok()).unwrap_or(40);
    let seed: u64 = get("--seed").and_then(|v| v.parse().ok()).unwrap_or(7);
    let phase = get("--phase").and_then(|p| Phase::parse(&p)).unwrap_or(Phase::P1);
    let stress: Option<u32> = get("--stress").and_then(|v| v.parse().ok());
    let tier: u8 = get("--chaos").and_then(|v| v.parse().ok()).unwrap_or(0);
    let mode = match get("--aim").as_deref() {
        Some("manual") => AimMode::Manual,
        Some("assisted") => AimMode::Assisted,
        _ => AimMode::Auto,
    };
    let db = Arc::new(ContentDb::load_dir(&find_content_dir()).expect("content"));
    let chars: Vec<u16> = db.playable_characters().filter(|(_, c)| c.phase <= phase).map(|(i, _)| i.0).collect();
    let loadouts: Vec<(Loadout, AimMode)> = (0..bots)
        .map(|i| {
            let character =
                if let Some(c) = get("--character") { db.characters.id(&c).unwrap() } else { chars[i % chars.len()] };
            let chassis = db.chassis.id(&db.characters.get(character).signature_chassis).unwrap();
            (Loadout { character, chassis, sigil: None }, mode)
        })
        .collect();
    let cfg = SimConfig { seed, phase, chaos_tier: tier, stress_enemies: stress, ..Default::default() };
    let report = run_headless(db, cfg, &loadouts, minutes * 60 * 60, NetConditions::ideal());
    println!("{report:#?}");
}
