//! `gf-content` — the GODFORGE content pipeline CLI.
//!
//! ```text
//! gf-content import            # sheets → assets/content/generated/*.ron (validated)
//! gf-content import --check    # CI: fail if generated files are stale or content is invalid
//! gf-content validate [--strict]   # full report incl. EA-scope warnings (no files written)
//! gf-content audit [--write]   # 100-hour audit (§11.5 / acceptance #7)
//! gf-content preview-room <template> <seed> <out.png> [--ron]  # top-down PNG (+ RoomDef dump)
//! gf-content preview-sheet <out.png> --biome KEY --seeds N  # contact sheet: templates × seeds
//! gf-content layout-stats [--biome KEY] [--seeds N]         # density / flow readout per kind
//! ```

mod audit;
mod preview;
mod sheets;

use gf_content::{CONTENT_FILES, ContentDb, ContentSources, RoomKind, Severity};
use std::path::PathBuf;
use std::process::ExitCode;

struct Paths {
    sheets: PathBuf,
    content: PathBuf,
    docs: PathBuf,
}

fn workspace_root() -> PathBuf {
    // tools/gf_tools → workspace root
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn paths() -> Paths {
    let root = std::env::var("GODFORGE_ROOT").map(PathBuf::from).unwrap_or_else(|_| workspace_root());
    Paths { sheets: root.join("content/sheets"), content: root.join("assets/content"), docs: root.join("docs") }
}

/// Hand-authored files straight from disk + generated files freshly converted from the sheets.
fn sources_from_sheets(p: &Paths) -> Result<(ContentSources, Vec<(&'static str, String)>), Vec<String>> {
    let generated = sheets::convert_all(&p.sheets)?;
    let mut src = ContentSources::default();
    for f in CONTENT_FILES {
        if f.starts_with("generated/") {
            continue;
        }
        match std::fs::read_to_string(p.content.join(f)) {
            Ok(t) => {
                src.files.insert((*f).to_string(), t);
            }
            Err(e) => return Err(vec![format!("{}: {e}", p.content.join(f).display())]),
        }
    }
    for (name, text) in &generated {
        src.files.insert((*name).to_string(), text.clone());
    }
    Ok((src, generated))
}

fn print_errors(errors: &[String]) {
    for e in errors {
        eprintln!("error: {e}");
    }
    eprintln!("\n{} error(s)", errors.len());
}

fn load(p: &Paths) -> Result<(ContentDb, Vec<(&'static str, String)>), ExitCode> {
    let (src, generated) = match sources_from_sheets(p) {
        Ok(v) => v,
        Err(errors) => {
            print_errors(&errors);
            return Err(ExitCode::FAILURE);
        }
    };
    match ContentDb::from_sources(&src) {
        Ok(db) => Ok((db, generated)),
        Err(e) => {
            eprintln!("error: {e}");
            Err(ExitCode::FAILURE)
        }
    }
}

fn report(db: &ContentDb, strict: bool) -> bool {
    let issues = db.validate();
    let errors = issues.iter().filter(|i| i.severity == Severity::Error).count();
    let warnings = issues.len() - errors;
    for i in &issues {
        if i.severity == Severity::Error {
            eprintln!("{i}");
        } else {
            println!("{i}");
        }
    }
    println!("\ncontent hash {:016x}", db.hash);
    for (what, n) in db.counts() {
        println!("  {what:<22} {n}");
    }
    println!("\n{errors} error(s), {warnings} warning(s)");
    errors == 0 && (!strict || warnings == 0)
}

fn cmd_import(p: &Paths, check: bool) -> ExitCode {
    let (db, generated) = match load(p) {
        Ok(v) => v,
        Err(code) => return code,
    };
    if !report(&db, false) {
        return ExitCode::FAILURE;
    }
    let mut stale = Vec::new();
    for (name, text) in &generated {
        let path = p.content.join(name);
        let current = std::fs::read_to_string(&path).unwrap_or_default().replace('\r', "");
        if current != *text {
            if check {
                stale.push(name.to_string());
            } else {
                if let Some(parent) = path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                if let Err(e) = std::fs::write(&path, text) {
                    eprintln!("error: writing {}: {e}", path.display());
                    return ExitCode::FAILURE;
                }
                println!("wrote {}", path.display());
            }
        }
    }
    if !stale.is_empty() {
        eprintln!("\nstale generated content (run `cargo run -p gf_tools -- import`):");
        for s in stale {
            eprintln!("  {s}");
        }
        return ExitCode::FAILURE;
    }
    println!("{}", if check { "generated content is up to date" } else { "import complete" });
    ExitCode::SUCCESS
}

fn cmd_validate(p: &Paths, strict: bool) -> ExitCode {
    match load(p) {
        Ok((db, _)) => {
            if report(&db, strict) {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            }
        }
        Err(code) => code,
    }
}

fn cmd_audit(p: &Paths, write: bool) -> ExitCode {
    let (db, _) = match load(p) {
        Ok(v) => v,
        Err(code) => return code,
    };
    let text = audit::render(&audit::run(&db));
    println!("{text}");
    if write {
        let path = p.docs.join("HUNDRED_HOUR_AUDIT.md");
        if let Err(e) = std::fs::write(&path, &text) {
            eprintln!("error: writing {}: {e}", path.display());
            return ExitCode::FAILURE;
        }
        println!("wrote {}", path.display());
    }
    ExitCode::SUCCESS
}

fn usage() -> ExitCode {
    eprintln!(
        "usage: gf-content <import [--check] | validate [--strict] | audit [--write]\n\
         \x20                 | preview-room <template> <seed> <out.png> [--scale PX] [--ron]\n\
         \x20                 | preview-sheet <out.png> [--biome KEY] [--templates a,b] [--kinds combat,elite,anvil,treasure]\n\
         \x20                                [--seeds N] [--seed0 S] [--scale PX]\n\
         \x20                 | layout-stats [--biome KEY] [--seeds N]>"
    );
    ExitCode::FAILURE
}

/// Value after `--name` in `args`.
fn opt<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).map(String::as_str)
}

fn with_db(p: &Paths, f: impl FnOnce(&ContentDb) -> Result<(), String>) -> ExitCode {
    let db = match ContentDb::load_dir(&p.content) {
        Ok(db) => db,
        Err(e) => {
            eprintln!("error: {e}");
            return ExitCode::FAILURE;
        }
    };
    match f(&db) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("error: {e}");
            ExitCode::FAILURE
        }
    }
}

fn parse_kind(s: &str) -> Option<RoomKind> {
    match s.to_ascii_lowercase().as_str() {
        "combat" => Some(RoomKind::Combat),
        "elite" => Some(RoomKind::Elite),
        "anvil" => Some(RoomKind::Anvil),
        "treasure" => Some(RoomKind::Treasure),
        "miniboss" => Some(RoomKind::MiniBoss),
        "boss" => Some(RoomKind::Boss),
        _ => None,
    }
}

fn cmd_preview_room(p: &Paths, args: &[String]) -> ExitCode {
    let (Some(key), Some(seed), Some(out)) =
        (args.get(1), args.get(2).and_then(|s| s.parse::<u32>().ok()), args.get(3))
    else {
        return usage();
    };
    let scale = opt(args, "--scale").and_then(|s| s.parse().ok()).unwrap_or(10.0);
    let ron = args.iter().any(|a| a == "--ron");
    with_db(p, |db| preview::preview_room(db, key, seed, &PathBuf::from(out), scale, ron))
}

fn cmd_preview_sheet(p: &Paths, args: &[String]) -> ExitCode {
    let Some(out) = args.get(1).filter(|a| !a.starts_with("--")) else {
        return usage();
    };
    let list = |name: &str| -> Vec<String> {
        opt(args, name).map(|s| s.split(',').map(|k| k.trim().to_string()).collect()).unwrap_or_default()
    };
    let o = preview::SheetOptions {
        biome: opt(args, "--biome").map(str::to_string),
        templates: list("--templates"),
        kinds: list("--kinds").iter().filter_map(|k| parse_kind(k)).collect(),
        seeds: opt(args, "--seeds").and_then(|s| s.parse().ok()).unwrap_or(4).max(1),
        seed0: opt(args, "--seed0").and_then(|s| s.parse().ok()).unwrap_or(1).max(1),
        scale: opt(args, "--scale").and_then(|s| s.parse().ok()).unwrap_or(5.0),
    };
    with_db(p, |db| preview::preview_sheet(db, &o, &PathBuf::from(out)))
}

fn cmd_layout_stats(p: &Paths, args: &[String]) -> ExitCode {
    let seeds = opt(args, "--seeds").and_then(|s| s.parse().ok()).unwrap_or(40);
    with_db(p, |db| preview::layout_stats(db, opt(args, "--biome"), seeds))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let p = paths();
    let flag = |f: &str| args.iter().any(|a| a == f);
    match args.first().map(String::as_str) {
        Some("import") => cmd_import(&p, flag("--check")),
        Some("validate") => cmd_validate(&p, flag("--strict")),
        Some("audit") => cmd_audit(&p, flag("--write")),
        Some("preview-room") => cmd_preview_room(&p, &args),
        Some("preview-sheet") => cmd_preview_sheet(&p, &args),
        Some("layout-stats") => cmd_layout_stats(&p, &args),
        _ => usage(),
    }
}
