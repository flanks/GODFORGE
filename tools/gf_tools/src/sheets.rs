//! Spreadsheet import: `content/sheets/*.csv` → typed rows → normalized `generated/*.ron`.
//!
//! CSV headers are dotted field paths (`stats.damage`). Each table declares how every column is
//! encoded, so designers get precise errors ("parts.csv row 14, column `mods`: …") and the output
//! is always re-serialized from the typed structs (one canonical formatting, diff-friendly).

use gf_content::ron_options;
use gf_content::schema::*;
use gf_core::scaling::{ChaosTierDef, PartyScaling};
use serde::Serialize;
use serde::de::DeserializeOwned;
use std::fmt::Write as _;
use std::path::Path;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// Quoted string; empty → `""`.
    Str,
    /// Quoted string; empty → field omitted (`None` / default).
    OptStr,
    /// Verbatim RON (numbers, enums, tuples, structs); empty → field omitted (default).
    Raw,
    /// `a; b; c` → `["a", "b", "c"]`.
    StrList,
    /// `X(..); Y(..)` → `[X(..), Y(..)]` (split on top-level `;`).
    RawList,
}

pub struct Column {
    pub header: &'static str,
    pub kind: Kind,
}

const fn c(header: &'static str, kind: Kind) -> Column {
    Column { header, kind }
}

use Kind::*;

pub struct Sheet {
    pub csv: &'static str,
    pub ron: &'static str,
    pub columns: &'static [Column],
    pub convert: fn(&str, &Sheet) -> Result<String, Vec<String>>,
}

pub static SHEETS: &[Sheet] = &[
    Sheet {
        csv: "party_scaling.csv",
        ron: "generated/party_scaling.ron",
        columns: &[c("players", Raw), c("enemy_hp", Raw), c("enemy_count", Raw), c("boss_hp", Raw), c("loot", Raw)],
        convert: convert::<PartyScaling>,
    },
    Sheet {
        csv: "chaos_tiers.csv",
        ron: "generated/chaos_tiers.ron",
        columns: &[c("tier", Raw), c("name", Str), c("mods", RawList), c("desc", Str)],
        convert: convert::<ChaosTierDef>,
    },
    Sheet {
        csv: "gods.csv",
        ron: "generated/gods.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("domain", Str),
            c("color", Str),
            c("color_secondary", Str),
            c("playstyle", Str),
            c("phase", Raw),
        ],
        convert: convert::<GodDef>,
    },
    Sheet {
        csv: "characters.csv",
        ron: "generated/characters.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("title", Str),
            c("role", Str),
            c("phase", Raw),
            c("fantasy", Str),
            c("color", Str),
            c("stats.max_hp", Raw),
            c("stats.move_speed", Raw),
            c("stats.dash_charges", Raw),
            c("stats.dash_recharge", Raw),
            c("stats.radius", Raw),
            c("stats.ult_per_damage", Raw),
            c("signature_chassis", Str),
            c("passive", Str),
            c("active1", Str),
            c("active2", Str),
            c("ultimate", Str),
            c("coop_role", Str),
            c("skins", StrList),
            c("sigils", StrList),
        ],
        convert: convert::<CharacterDef>,
    },
    Sheet {
        csv: "chassis.csv",
        ron: "generated/chassis.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("phase", Raw),
            c("unlock_forge_level", Raw),
            c("stats.fire", Raw),
            c("stats.damage", Raw),
            c("stats.fire_rate", Raw),
            c("stats.projectiles", Raw),
            c("stats.spread_deg", Raw),
            c("stats.speed", Raw),
            c("stats.range", Raw),
            c("stats.radius", Raw),
            c("stats.pierce", Raw),
            c("stats.knockback", Raw),
            c("stats.crit_chance", Raw),
            c("stats.crit_mult", Raw),
            c("stats.charge_time", Raw),
            c("stats.charge_mult", Raw),
            c("stats.splash_radius", Raw),
            c("stats.splash_damage", Raw),
            c("stats.damage_type", Raw),
            c("stats.style", Raw),
            c("stats.precision_zone", Raw),
            c("stats.ramp", Raw),
            c("mods", RawList),
            c("tags", StrList),
            c("desc", Str),
        ],
        convert: convert::<ChassisDef>,
    },
    Sheet {
        csv: "parts.csv",
        ron: "generated/parts.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("slot", Raw),
            c("phase", Raw),
            c("god", OptStr),
            c("weight", Raw),
            c("tags", StrList),
            c("mods", RawList),
            c("desc", Str),
        ],
        convert: convert::<PartDef>,
    },
    Sheet {
        csv: "boons.csv",
        ron: "generated/boons.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("kind", Raw),
            c("gods", StrList),
            c("phase", Raw),
            c("weight", Raw),
            c("requires", RawList),
            c("mods", RawList),
            c("desc", Str),
        ],
        convert: convert::<BoonDef>,
    },
    Sheet {
        csv: "recipes.csv",
        ron: "generated/recipes.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("phase", Raw),
            c("ingredients", RawList),
            c("bonus", RawList),
            c("codex", Str),
        ],
        convert: convert::<RecipeDef>,
    },
    Sheet {
        csv: "synergies.csv",
        ron: "generated/synergies.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("a", Raw),
            c("b", Raw),
            c("phase", Raw),
            c("effect", Raw),
            c("desc", Str),
        ],
        convert: convert::<SynergyDef>,
    },
    Sheet {
        csv: "enemies.csv",
        ron: "generated/enemies.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("biome", Str),
            c("class", Raw),
            c("phase", Raw),
            c("hp", Raw),
            c("speed", Raw),
            c("radius", Raw),
            c("contact_damage", Raw),
            c("mass", Raw),
            c("resist", Raw),
            c("plating", Raw),
            c("shield", Raw),
            c("behavior", Raw),
            c("color", Str),
            c("shape", Raw),
            c("scale", Raw),
            c("pack", Raw),
            c("death_burst", Raw),
            c("desc", Str),
        ],
        convert: convert::<EnemyDef>,
    },
    Sheet {
        csv: "forge_altar.csv",
        ron: "generated/altar.ron",
        columns: &[
            c("key", Str),
            c("tree", Raw),
            c("tier", Raw),
            c("name", Str),
            c("cost", Raw),
            c("requires", StrList),
            c("effect", Raw),
            c("phase", Raw),
            c("desc", Str),
        ],
        convert: convert::<AltarNode>,
    },
    Sheet {
        csv: "character_trees.csv",
        ron: "generated/trees.ron",
        columns: &[
            c("key", Str),
            c("character", Str),
            c("index", Raw),
            c("branch", Str),
            c("name", Str),
            c("cost", Raw),
            c("requires", StrList),
            c("mods", RawList),
            c("unlock", OptStr),
            c("phase", Raw),
            c("desc", Str),
        ],
        convert: convert::<TreeNode>,
    },
    Sheet {
        csv: "achievements.csv",
        ron: "generated/achievements.ron",
        columns: &[
            c("key", Str),
            c("name", Str),
            c("category", Str),
            c("stat", Str),
            c("target", Raw),
            c("phase", Raw),
            c("desc", Str),
        ],
        convert: convert::<AchievementDef>,
    },
    Sheet {
        csv: "barks.csv",
        ron: "generated/barks.ron",
        columns: &[c("key", Str), c("speaker", Str), c("trigger", Str), c("weight", Raw), c("line", Str)],
        convert: convert::<BarkDef>,
    },
];

fn quote(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => {}
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Split on `;` that is not inside quotes or brackets.
pub fn split_top_level(s: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut depth = 0i32;
    let mut in_str = false;
    let mut escaped = false;
    let mut cur = String::new();
    for ch in s.chars() {
        if in_str {
            cur.push(ch);
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_str = false;
            }
            continue;
        }
        match ch {
            '"' => {
                in_str = true;
                cur.push(ch);
            }
            '(' | '[' | '{' => {
                depth += 1;
                cur.push(ch);
            }
            ')' | ']' | '}' => {
                depth -= 1;
                cur.push(ch);
            }
            ';' if depth == 0 => {
                let t = cur.trim();
                if !t.is_empty() {
                    parts.push(t.to_string());
                }
                cur.clear();
            }
            c => cur.push(c),
        }
    }
    let t = cur.trim();
    if !t.is_empty() {
        parts.push(t.to_string());
    }
    parts
}

fn encode(kind: Kind, cell: &str) -> Option<String> {
    let cell = cell.trim();
    match kind {
        Str => Some(quote(cell)),
        OptStr | Raw if cell.is_empty() => None,
        OptStr => Some(quote(cell)),
        Raw => Some(cell.to_string()),
        StrList => {
            let items: Vec<String> = cell.split(';').map(str::trim).filter(|s| !s.is_empty()).map(quote).collect();
            Some(format!("[{}]", items.join(", ")))
        }
        RawList => Some(format!("[{}]", split_top_level(cell).join(", "))),
    }
}

/// A tree of fields assembled from dotted headers, emitted as a RON struct literal.
#[derive(Default)]
struct Node {
    fields: Vec<(String, Field)>,
}

enum Field {
    Leaf(String),
    Branch(Node),
}

impl Node {
    fn insert(&mut self, path: &[&str], value: String) {
        let (head, rest) = (path[0], &path[1..]);
        if rest.is_empty() {
            self.fields.push((head.to_string(), Field::Leaf(value)));
            return;
        }
        if let Some((_, Field::Branch(n))) = self.fields.iter_mut().find(|(k, _)| k == head) {
            n.insert(rest, value);
            return;
        }
        let mut n = Node::default();
        n.insert(rest, value);
        self.fields.push((head.to_string(), Field::Branch(n)));
    }

    fn emit(&self, out: &mut String) {
        out.push('(');
        for (i, (k, f)) in self.fields.iter().enumerate() {
            if i > 0 {
                out.push_str(", ");
            }
            let _ = write!(out, "{k}: ");
            match f {
                Field::Leaf(v) => out.push_str(v),
                Field::Branch(n) => n.emit(out),
            }
        }
        out.push(')');
    }
}

/// Pretty RON used for every generated file.
pub fn pretty() -> ron::ser::PrettyConfig {
    ron::ser::PrettyConfig::new().depth_limit(3).indentor("  ".to_string()).struct_names(false)
}

fn convert<T: DeserializeOwned + Serialize>(csv_text: &str, sheet: &Sheet) -> Result<String, Vec<String>> {
    let mut rdr = csv::ReaderBuilder::new().flexible(false).trim(csv::Trim::None).from_reader(csv_text.as_bytes());
    let headers: Vec<String> = match rdr.headers() {
        Ok(h) => h.iter().map(|s| s.trim().to_string()).collect(),
        Err(e) => return Err(vec![format!("{}: cannot read header: {e}", sheet.csv)]),
    };
    let mut errors = Vec::new();
    for col in sheet.columns {
        if !headers.iter().any(|h| h == col.header) {
            errors.push(format!("{}: missing column `{}`", sheet.csv, col.header));
        }
    }
    for h in &headers {
        if !sheet.columns.iter().any(|c| c.header == h) {
            errors.push(format!("{}: unknown column `{h}`", sheet.csv));
        }
    }
    if !errors.is_empty() {
        return Err(errors);
    }
    let mut rows: Vec<T> = Vec::new();
    for (i, rec) in rdr.records().enumerate() {
        let line = i + 2; // 1-based, after the header
        let rec = match rec {
            Ok(r) => r,
            Err(e) => {
                errors.push(format!("{} row {line}: {e}", sheet.csv));
                continue;
            }
        };
        if rec.iter().all(|c| c.trim().is_empty()) {
            continue;
        }
        let mut node = Node::default();
        for (h, cell) in headers.iter().zip(rec.iter()) {
            let col = sheet.columns.iter().find(|c| c.header == h).expect("validated above");
            if let Some(v) = encode(col.kind, cell) {
                let path: Vec<&str> = h.split('.').collect();
                node.insert(&path, v);
            }
        }
        let mut text = String::new();
        node.emit(&mut text);
        match ron_options().from_str::<T>(&text) {
            Ok(row) => rows.push(row),
            Err(e) => {
                let key = rec.get(headers.iter().position(|h| h == "key").unwrap_or(0)).unwrap_or("?");
                errors.push(format!("{} row {line} (`{key}`): {e}\n      assembled: {text}", sheet.csv));
            }
        }
    }
    if !errors.is_empty() {
        return Err(errors);
    }
    let mut out = String::from("// GENERATED by `gf-content import` from content/sheets/");
    out.push_str(sheet.csv);
    out.push_str(" — edit the sheet, not this file.\n");
    match ron_options().to_string_pretty(&rows, pretty()) {
        Ok(s) => {
            out.push_str(&s);
            out.push('\n');
            Ok(out)
        }
        Err(e) => Err(vec![format!("{}: serialize: {e}", sheet.csv)]),
    }
}

/// Convert every sheet. Returns `(relative ron path, text)` pairs or all errors.
pub fn convert_all(sheets_dir: &Path) -> Result<Vec<(&'static str, String)>, Vec<String>> {
    let mut out = Vec::new();
    let mut errors = Vec::new();
    for sheet in SHEETS {
        let path = sheets_dir.join(sheet.csv);
        let text = match std::fs::read_to_string(&path) {
            Ok(t) => t,
            Err(e) => {
                errors.push(format!("{}: {e}", path.display()));
                continue;
            }
        };
        match (sheet.convert)(&text, sheet) {
            Ok(ron) => out.push((sheet.ron, ron)),
            Err(mut e) => errors.append(&mut e),
        }
    }
    if errors.is_empty() { Ok(out) } else { Err(errors) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_respects_nesting_and_strings() {
        let parts = split_top_level(r#"Damage(1.2); Puddle(radius: 2.0, duration: 3.0, dps: 0.3); X("a;b")"#);
        assert_eq!(parts, vec!["Damage(1.2)", "Puddle(radius: 2.0, duration: 3.0, dps: 0.3)", r#"X("a;b")"#]);
        assert!(split_top_level("  ").is_empty());
    }

    #[test]
    fn converts_a_parts_sheet() {
        let csv = "key,name,slot,phase,god,weight,tags,mods,desc\n\
                   embercore,Embercore,Core,P0,,1.0,fire;bolt,\"Element(Flame); ApplyStatus(status: Burn, chance: 0.35, stacks: 1, duration: 3.0)\",\"Fire \"\"bolts\"\".\"\n";
        let sheet = SHEETS.iter().find(|s| s.csv == "parts.csv").unwrap();
        let ron = (sheet.convert)(csv, sheet).unwrap();
        let parts: Vec<PartDef> =
            ron_options().from_str(ron.lines().skip(1).collect::<Vec<_>>().join("\n").as_str()).unwrap();
        assert_eq!(parts.len(), 1);
        assert_eq!(parts[0].mods.len(), 2);
        assert_eq!(parts[0].tags, vec!["fire", "bolt"]);
        assert_eq!(parts[0].desc, "Fire \"bolts\".");
        assert_eq!(parts[0].god, None);
    }

    #[test]
    fn reports_bad_cells_with_row_numbers() {
        let csv = "key,name,slot,phase,god,weight,tags,mods,desc\nbad,Bad,Core,P0,,1.0,,Damage(,x\n";
        let sheet = SHEETS.iter().find(|s| s.csv == "parts.csv").unwrap();
        let errs = (sheet.convert)(csv, sheet).unwrap_err();
        assert!(errs[0].contains("row 2"), "{errs:?}");
    }

    #[test]
    fn reports_header_mismatch() {
        let csv = "key,name,oops\n";
        let sheet = SHEETS.iter().find(|s| s.csv == "gods.csv").unwrap();
        let errs = (sheet.convert)(csv, sheet).unwrap_err();
        assert!(errs.iter().any(|e| e.contains("unknown column `oops`")));
        assert!(errs.iter().any(|e| e.contains("missing column `domain`")));
    }
}
