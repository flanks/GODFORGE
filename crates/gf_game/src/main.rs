//! GODFORGE: The Last Arsenal — game executable.
//!
//! One binary for players, hosts, CI and the test rigs (§20.7). Every mode drives the same
//! authoritative simulation through the same network layer.

use gf_client::{ClientConfig, ClientPlugin, Connect};
use gf_content::{ContentDb, Phase, Severity, find_content_dir};
use gf_core::aim::AimMode;
use gf_engine::prelude::*;
use gf_net::{Loadout, NetConditions, RunPhase};
use gf_sim::SimConfig;
use gf_sim::bot::{RunReport, run_headless};
use std::path::PathBuf;
use std::str::FromStr;
use std::sync::Arc;

const USAGE: &str = "\
GODFORGE: The Last Arsenal

USAGE
  godforge [options]                 solo run (host sim on a thread, loopback netcode)
  godforge --host [port]             listen server: you + up to 3 friends over UDP (default 27015)
  godforge --join <addr:port>        join a host
  godforge --bot-run                 headless: bots play a full run through the real netcode
  godforge --stress [enemies]        headless: 4 bots vs a held enemy count (default 400)

GAME OPTIONS
  --character <key>     valdris, selene, kael (slice); thessaly, brax, ossian, mirren, epoch (EA)
  --chassis <key>       default: the character's signature chassis
  --aim auto|assisted|manual
  --phase p0|p1|ea|v1   content gate (default p1: the vertical slice)
  --chaos <tier>        Chaos Tier 0-20
  --seed <n>            run seed
  --room <key>          QA: open the run in this room (e.g. cinder_anvil_hall)
  --name <name>

CLIENT OPTIONS
  --bots <n>                   add n bot teammates (1-3) to your solo/host session
  --autoplay                   a bot drives your character (attract mode)
  --screenshot <path>          capture after --screenshot-after secs (default 20); repeat --shots N
  --screenshot-after <secs>    --shots <n> --shot-interval <secs>
  --exit-after <secs>
  --window <W>x<H>  --no-vsync  --no-damage-numbers  --no-shake  --no-shadows

HEADLESS OPTIONS
  --bots <n>  --minutes <n>  --rtt <ms>  --loss <0..1>
";

struct Args(Vec<String>);

impl Args {
    fn flag(&self, k: &str) -> bool {
        self.0.iter().any(|a| a == k)
    }

    fn value(&self, k: &str) -> Option<&str> {
        let i = self.0.iter().position(|a| a == k)?;
        self.0.get(i + 1).map(String::as_str).filter(|v| !v.starts_with("--"))
    }

    fn parse<T: FromStr>(&self, k: &str) -> Option<T> {
        self.value(k)?.parse().ok()
    }
}

fn main() {
    let args = Args(std::env::args().skip(1).collect());
    if args.flag("--help") || args.flag("-h") {
        print!("{USAGE}");
        return;
    }
    let content = match ContentDb::load_dir(&find_content_dir()) {
        Ok(db) => Arc::new(db),
        Err(e) => {
            eprintln!("error: content failed to load: {e}");
            std::process::exit(2);
        }
    };
    let errors: Vec<_> = content.validate().into_iter().filter(|i| i.severity == Severity::Error).collect();
    if !errors.is_empty() {
        for e in &errors {
            eprintln!("content error: {e}");
        }
        std::process::exit(2);
    }

    let phase = args.value("--phase").and_then(Phase::parse).unwrap_or(Phase::P1);
    let aim = match args.value("--aim") {
        Some("manual") => AimMode::Manual,
        Some("assisted") => AimMode::Assisted,
        _ => AimMode::Auto,
    };
    let seed = args.parse("--seed").unwrap_or_else(|| {
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(7, |d| d.as_secs())
    });
    let sim = SimConfig {
        seed,
        phase,
        chaos_tier: args.parse("--chaos").unwrap_or(0),
        start_room: args.value("--room").map(str::to_string),
        ..SimConfig::default()
    };
    let playable: Vec<u16> =
        content.playable_characters().filter(|(_, c)| c.phase <= phase).map(|(i, _)| i.0).collect();
    let signature = |character: u16| -> Loadout {
        let key = &content.characters.get(character).signature_chassis;
        Loadout { character, chassis: content.chassis.id(key).expect("validated signature chassis"), sigil: None }
    };
    let loadout = |i: usize| -> Loadout {
        let character = match args.value("--character") {
            Some(key) => content.characters.id(key).unwrap_or_else(|| {
                eprintln!("error: unknown character '{key}'");
                std::process::exit(2);
            }),
            None => playable[i % playable.len().max(1)],
        };
        match args.value("--chassis") {
            Some(key) => Loadout {
                character,
                chassis: content.chassis.id(key).unwrap_or_else(|| {
                    eprintln!("error: unknown chassis '{key}'");
                    std::process::exit(2);
                }),
                sigil: None,
            },
            None => signature(character),
        }
    };

    if args.flag("--bot-run") || args.flag("--stress") {
        let stress = args.flag("--stress").then(|| args.parse("--stress").unwrap_or(400));
        let bots: usize = args.parse("--bots").unwrap_or(if stress.is_some() { 4 } else { 1 });
        let minutes: u32 = args.parse("--minutes").unwrap_or(if stress.is_some() { 2 } else { 40 });
        let net = match args.parse::<u64>("--rtt") {
            Some(rtt) => NetConditions::rtt(rtt, rtt / 10, args.parse("--loss").unwrap_or(0.0)),
            None => NetConditions::ideal(),
        };
        let loadouts: Vec<(Loadout, AimMode)> = (0..bots.clamp(1, 4)).map(|i| (loadout(i), aim)).collect();
        let sim = SimConfig { stress_enemies: stress, ..sim };
        let report = run_headless(content.clone(), sim, &loadouts, minutes * 60 * 60, net);
        // A time-boxed run (explicit --minutes) must make progress without a wipe; a full run
        // must reach victory or defeat.
        let gate = match (stress.is_some(), args.value("--minutes").is_some()) {
            (true, _) => Gate::Budget,
            (false, true) => Gate::Progress,
            (false, false) => Gate::Finish,
        };
        let ok = print_report(&report, gate);
        std::process::exit(if ok { 0 } else { 1 });
    }

    let connect = if let Some(addr) = args.value("--join") {
        Connect::Join(addr.to_string())
    } else if args.flag("--host") {
        Connect::Host(SimConfig { snapshot_every: 1, ..sim }, args.parse("--host").unwrap_or(27015))
    } else {
        Connect::Local(sim)
    };
    let mut screenshots = Vec::new();
    if let Some(path) = args.value("--screenshot") {
        let first: f32 = args.parse("--screenshot-after").unwrap_or(20.0);
        let shots: usize = args.parse("--shots").unwrap_or(1).max(1);
        let every: f32 = args.parse("--shot-interval").unwrap_or(10.0);
        let path = PathBuf::from(path);
        for i in 0..shots {
            let p = if shots == 1 {
                path.clone()
            } else {
                let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("shot");
                let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("png");
                path.with_file_name(format!("{stem}_{i:02}.{ext}"))
            };
            screenshots.push((p, first + every * i as f32));
        }
    }
    let exit_after = args.parse("--exit-after").or_else(|| screenshots.last().map(|(_, t)| t + 3.0));
    let (width, height) = args
        .value("--window")
        .and_then(|v| v.split_once('x'))
        .and_then(|(w, h)| Some((w.parse().ok()?, h.parse().ok()?)))
        .unwrap_or((1600, 900));
    // Bot teammates cycle through the other playable characters.
    let me = loadout(0);
    let teammates: usize =
        if matches!(connect, Connect::Join(_)) { 0 } else { args.parse("--bots").unwrap_or(0).min(3) };
    let others: Vec<u16> = playable.iter().copied().filter(|c| *c != me.character).collect();
    let party = (0..teammates)
        .map(|i| signature(others.get(i % others.len().max(1)).copied().unwrap_or(me.character)))
        .collect();
    let cfg = ClientConfig {
        content: content.clone(),
        name: args.value("--name").unwrap_or("Forgebearer").to_string(),
        loadout: me,
        party,
        aim_mode: aim,
        connect,
        autoplay: args.flag("--autoplay"),
        screenshots,
        exit_after,
        damage_numbers: !args.flag("--no-damage-numbers"),
        screen_shake: if args.flag("--no-shake") { 0.0 } else { 1.0 },
        shadows: !args.flag("--no-shadows"),
    };
    App::new()
        .add_plugins(gf_engine::client::default_plugins(
            "GODFORGE: The Last Arsenal",
            width,
            height,
            !args.flag("--no-vsync"),
        ))
        .add_plugins(ClientPlugin(cfg))
        .run();
}

/// What a headless run must demonstrate beyond the tick budget.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Gate {
    /// Stress scene: only the tick budget.
    Budget,
    /// Time-boxed run: clear at least one room and don't wipe.
    Progress,
    /// Full run: end in victory or defeat (anything else is a stall).
    Finish,
}

/// Print a headless report; returns false when the run breaks a CI gate.
fn print_report(r: &RunReport, gate: Gate) -> bool {
    println!("outcome        {:?}", r.outcome);
    println!("rooms cleared  {} (biome {} reached)", r.depth, r.biome_reached + 1);
    println!("kills          {}", r.kills);
    println!("ember          {}", r.ember);
    println!("sim time       {:.1} min in {:.1} s wall", r.sim_minutes, r.wall_seconds);
    println!("enemies        peak {} (entities {})", r.max_enemies, r.max_entities);
    println!(
        "host tick      mean {:.3} ms · p50 {:.3} · p99 {:.3} · max {:.3} (budget 16.667)",
        r.mean_tick_ms, r.p50_tick_ms, r.p99_tick_ms, r.max_tick_ms
    );
    println!("snapshot       max {} bytes", r.max_snapshot_bytes);
    for room in &r.rooms {
        println!("  room {:<28} {:>6.1}s {:>5} kills", room.room, room.seconds, room.kills);
    }
    for b in &r.bots {
        println!(
            "  P{} {:<10} {:<8} kills {:>5} dmg {:>9.0} dps {:.0}/{:.0} · {} · {}",
            b.slot + 1,
            b.character,
            b.aim_mode.name(),
            b.kills,
            b.damage,
            b.dps.0,
            b.dps.1,
            b.weapon.join(", "),
            b.parts.join(", ")
        );
    }
    let mut ok = true;
    if r.p99_tick_ms > 16.667 {
        eprintln!("FAIL: host p99 tick {:.2} ms exceeds the 60 Hz budget", r.p99_tick_ms);
        ok = false;
    }
    match gate {
        Gate::Finish if !matches!(r.outcome, RunPhase::Victory | RunPhase::Defeat) => {
            eprintln!("FAIL: the run neither ended in victory nor defeat (stall)");
            ok = false;
        }
        Gate::Progress if r.outcome == RunPhase::Defeat || r.depth == 0 => {
            eprintln!("FAIL: time-boxed run wiped or cleared no room ({:?}, depth {})", r.outcome, r.depth);
            ok = false;
        }
        _ => {}
    }
    ok
}
