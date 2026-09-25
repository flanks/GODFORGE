//! The content that ships must load and validate. CI runs this on every push.

use gf_content::{ContentDb, Phase, Severity, find_content_dir};
use gf_core::forge::Slot;

fn db() -> ContentDb {
    ContentDb::load_dir(&find_content_dir()).unwrap_or_else(|e| panic!("shipped content is invalid: {e}"))
}

#[test]
fn shipped_content_validates() {
    let db = db();
    let errors: Vec<_> = db.validate().into_iter().filter(|i| i.severity == Severity::Error).collect();
    assert!(errors.is_empty(), "{errors:#?}");
}

#[test]
fn p0_slice_has_its_forge_loop() {
    // Roadmap P0: 1 character (Valdris), 1 chassis × 5 parts, 10 enemies, 1 room set.
    let db = db();
    let valdris = db.characters.by_key("valdris").expect("Valdris");
    assert_eq!(valdris.phase, Phase::P0);
    assert!(db.kit(gf_core::ids::CharacterId(db.characters.id("valdris").unwrap())).is_some());
    let p0_parts = db.parts.iter().filter(|p| p.phase == Phase::P0 && p.slot != Slot::Sigil).count();
    assert!(p0_parts >= 5, "P0 needs ≥5 forge parts, has {p0_parts}");
    let p0_enemies = db.enemies.iter().filter(|e| e.phase == Phase::P0).count();
    assert!(p0_enemies >= 9, "P0 needs ~10 enemies, has {p0_enemies}");
    assert!(db.rooms.iter().any(|r| r.phase == Phase::P0 && r.anvil.is_some()), "P0 needs an anvil room");
}

#[test]
fn every_playable_kit_uses_its_signature_chassis() {
    let db = db();
    for (_, c) in db.playable_characters() {
        assert!(db.chassis.id(&c.signature_chassis).is_some(), "{}", c.key);
    }
}

#[test]
fn content_hash_is_stable_across_loads() {
    assert_eq!(db().hash, db().hash);
}
