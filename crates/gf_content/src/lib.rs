//! # gf_content — data-driven everything
//!
//! No weapon, part, boon, enemy, room or character stat is hardcoded. Designers edit spreadsheets
//! (`content/sheets/*.csv`) and a few hand-authored RON files; `gf_tools import` turns sheets into
//! `assets/content/generated/*.ron`; this crate loads everything into a [`ContentDb`], resolves
//! string keys to compact ids and validates every cross-reference.

pub mod db;
pub mod schema;
pub mod validate;

pub use db::{CONTENT_FILES, ContentDb, ContentSources, Keyed, Table, ron_options};
pub use schema::*;
pub use validate::{Issue, Severity};

use std::path::PathBuf;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ContentError {
    #[error("reading {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
    #[error("parsing {path}: {message}")]
    Parse { path: PathBuf, message: String },
    #[error("duplicate key `{key}` in {table}")]
    DuplicateKey { table: &'static str, key: String },
    #[error("content failed validation with {} error(s):\n{}", .0.len(), .0.iter().map(|i| format!("  - {i}")).collect::<Vec<_>>().join("\n"))]
    Invalid(Vec<Issue>),
}

/// Default content directory relative to the workspace root.
pub const DEFAULT_CONTENT_DIR: &str = "assets/content";

/// Locate the content directory: `$GODFORGE_CONTENT`, then `./assets/content`, then relative to
/// the executable (packaged builds), then relative to this crate (tests / `cargo run`).
pub fn find_content_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("GODFORGE_CONTENT") {
        return PathBuf::from(dir);
    }
    let cwd = PathBuf::from(DEFAULT_CONTENT_DIR);
    if cwd.join("game.ron").exists() {
        return cwd;
    }
    if let Ok(exe) = std::env::current_exe()
        && let Some(dir) = exe.parent()
    {
        let packaged = dir.join(DEFAULT_CONTENT_DIR);
        if packaged.join("game.ron").exists() {
            return packaged;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").join(DEFAULT_CONTENT_DIR)
}
