//! `--ui-shot forge|boon|end|defeat|help|doors` (UI_STYLE §11.11): force a panel open over the live
//! game with sample data drawn from the current content, for screenshots. The sample only feeds
//! the panels (the HUD and the host keep the real run). QA only; never reachable in normal play.

use super::PanelWorld;
use crate::ClientConfig;
use crate::input::Settings;
use crate::net::Link;
use gf_content::ContentDb;
use gf_core::forge::{ForgeWallet, PartBag, PartInstance, Slot, WeaponBuild};
use gf_core::ids::{ChassisId, NetId, PartId};
use gf_core::rarity::Rarity;
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{
    AnvilState, AnvilView, BoonOffer, DoorReward, EntityFlags, EntityKind, EntityView, GateView, RunPhase, StageView,
    WorldSnapshot,
};

/// Which panel a QA screenshot forces open.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) enum Shot {
    #[default]
    None,
    Forge,
    Boon,
    End,
    Defeat,
    Help,
    Doors,
}

impl Shot {
    fn parse(s: Option<&str>) -> Self {
        match s {
            Some("forge") => Shot::Forge,
            Some("boon" | "boons") => Shot::Boon,
            Some("end" | "victory") => Shot::End,
            Some("defeat") => Shot::Defeat,
            Some("help") => Shot::Help,
            Some("doors") => Shot::Doors,
            _ => Shot::None,
        }
    }
}

pub(super) fn build(app: &mut App) {
    let shot = Shot::parse(app.world().resource::<ClientConfig>().ui_shot.as_deref());
    app.world_mut().resource_mut::<PanelWorld>().shot = shot;
}

/// Rebuild the sample world from the live one each frame (QA only).
pub(super) fn fill(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    mut pw: ResMut<PanelWorld>,
    mut settings: ResMut<Settings>,
) {
    let shot = pw.shot;
    if shot == Shot::None {
        return;
    }
    if shot == Shot::Help {
        if !settings.help {
            settings.help = true;
        }
        return;
    }
    let Some(live) = link.latest.as_deref() else { return };
    let db = &cfg.content;
    let mut w = live.clone();
    match shot {
        Shot::Forge => forge(db, &mut w, link.slot),
        Shot::Boon => boons(db, &mut w, link.slot),
        Shot::End => end(db, &mut w, true),
        Shot::Defeat => end(db, &mut w, false),
        Shot::Doors => doors(db, &mut w),
        Shot::None | Shot::Help => {}
    }
    pw.qa = Some(w);
}

fn part(db: &ContentDb, key: &str, rarity: Rarity, uid: u32) -> Option<PartInstance> {
    db.parts.id(key).map(|id| PartInstance { uid, part: PartId(id), rarity })
}

/// A sample build: `parts` fill Core, Mechanism and Relic; the Sigil stays as it was.
fn sample_build(
    db: &ContentDb,
    chassis: &str,
    keep: &WeaponBuild,
    parts: [(&str, Rarity); 3],
    uid: u32,
) -> WeaponBuild {
    let mut b = WeaponBuild::new(db.chassis.id(chassis).map_or(keep.chassis, ChassisId));
    for (i, (s, (key, r))) in [Slot::Core, Slot::Mechanism, Slot::Relic].into_iter().zip(parts).enumerate() {
        b.set(s, part(db, key, r, uid + i as u32));
    }
    b.set(Slot::Sigil, keep.get(Slot::Sigil));
    b
}

fn forge(db: &ContentDb, w: &mut WorldSnapshot, me: Option<u8>) {
    let Some(p) = w.players.iter_mut().find(|p| Some(p.slot) == me) else { return };
    let mut b = sample_build(
        db,
        "colossus_cannon",
        &p.weapon,
        [("stormcore", Rarity::Rare), ("mech_ricochet", Rarity::Epic), ("relic_nyctian_eye", Rarity::Rare)],
        901,
    );
    if b.get(Slot::Sigil).is_none() {
        b.set(Slot::Sigil, part(db, "sigil_anvilheart", Rarity::Godforged, 904));
    }
    p.weapon = b;
    let mut bag = PartBag::with_capacity(db.game.forge.bag_capacity.max(8));
    for (i, (key, r)) in [
        ("relic_doomstack", Rarity::Epic),
        ("relic_volatile_heart", Rarity::Godforged),
        ("stormcore", Rarity::Rare),
        ("mech_multishot", Rarity::Rare),
        ("embercore", Rarity::Rare),
        ("relic_vampire", Rarity::Common),
    ]
    .into_iter()
    .enumerate()
    {
        if let Some(it) = part(db, key, r, 911 + i as u32) {
            let _ = bag.push(it);
        }
    }
    w.private.bag = bag;
    w.private.wallet = ForgeWallet { godshards: 56, charges: 2, free_actions: 0 };
    w.private.at_anvil = true;
    w.private.anvil =
        Some(AnvilView { id: NetId(0), state: AnvilState::Hot, progress: 1.0, time_left: 19.0, contested: false });
}

fn boons(db: &ContentDb, w: &mut WorldSnapshot, me: Option<u8>) {
    let offer: Vec<BoonOffer> = [
        ("zephyros_stormbrand", Rarity::Common),
        ("zephyros_leaping_arc", Rarity::Rare),
        ("silent_thunder", Rarity::Epic),
    ]
    .into_iter()
    .filter_map(|(k, rarity)| db.boons.id(k).map(|boon| BoonOffer { boon, rarity }))
    .collect();
    let leaping = db.boons.id("zephyros_leaping_arc");
    if let Some(p) = w.players.iter_mut().find(|p| Some(p.slot) == me) {
        p.boons = leaping.into_iter().collect();
    }
    w.private.boon_offer = offer;
    w.private.boon_rerolls = 1;
    w.private.boon_queue = 1;
}

/// The first `n` Standard boons of a god.
fn boons_of(db: &ContentDb, god: &str, n: usize) -> Vec<u16> {
    db.boons
        .enumerate()
        .filter(|(_, b)| b.gods.first().is_some_and(|g| g == god) && b.kind == gf_content::BoonKind::Standard)
        .map(|(i, _)| i)
        .take(n)
        .collect()
}

fn end(db: &ContentDb, w: &mut WorldSnapshot, victory: bool) {
    w.run.phase = if victory { RunPhase::Victory } else { RunPhase::Defeat };
    w.run.kills = if victory { 4812 } else { 2977 };
    w.run.time = if victory { 1308.0 } else { 941.0 };
    w.run.ember = if victory { 312 } else { 148 };
    w.run.stage = Some(StageView {
        seals: if victory { 7 } else { 4 },
        required: 7,
        warlord: victory,
        gate: GateView::Open,
        time: w.run.time,
        threat: 0,
        surge: None,
        objectives: if victory { 11 } else { 6 },
        forced: false,
    });
    let kills = [1904, 1320, 1011, 577];
    let damage = [382_400.0, 265_300.0, 201_900.0, 151_200.0];
    let builds: [(&str, [(&str, Rarity); 3]); 4] = [
        (
            "colossus_cannon",
            [("stormcore", Rarity::Rare), ("mech_ricochet", Rarity::Epic), ("relic_doomstack", Rarity::Epic)],
        ),
        (
            "stormlash",
            [("stormcore", Rarity::Epic), ("mech_multishot", Rarity::Rare), ("relic_volatile_heart", Rarity::Rare)],
        ),
        (
            "wraith_bow",
            [("voidcore", Rarity::Rare), ("mech_homing_shards", Rarity::Common), ("relic_nyctian_eye", Rarity::Epic)],
        ),
        (
            "sunspike_shotgun",
            [("embercore", Rarity::Rare), ("mech_ricochet", Rarity::Rare), ("relic_vampire", Rarity::Common)],
        ),
    ];
    let gods = [["pyra", "zephyros"], ["zephyros", "nyctia"], ["nyctia", "pyra"], ["pyra", "zephyros"]];
    for (i, p) in w.players.iter_mut().enumerate().take(4) {
        p.kills = kills[i];
        p.damage = damage[i];
        let (chassis, parts) = builds[i];
        p.weapon = sample_build(db, chassis, &p.weapon, parts, 1000 + i as u32 * 10);
        let mut b = boons_of(db, gods[i][0], 2);
        b.extend(boons_of(db, gods[i][1], 1 + (i % 2)));
        p.boons = b;
    }
}

fn doors(db: &ContentDb, w: &mut WorldSnapshot) {
    w.run.phase = RunPhase::Cleared;
    w.entities.retain(|e| !matches!(e.kind, EntityKind::Door { .. }));
    let pyra = db.god_id("pyra").map_or(0, |g| g.0);
    for (i, reward) in
        [DoorReward::PartCache, DoorReward::Boon { god: pyra }, DoorReward::Anvil].into_iter().enumerate()
    {
        w.entities.push(EntityView {
            id: NetId(900_000 + i as u32),
            kind: EntityKind::Door { reward, index: i as u8 },
            pos: QPos::from_vec2(Vec2::new(-6.0 + 6.0 * i as f32, 12.0)),
            motion: None,
            facing: 0,
            hp: 0,
            flags: EntityFlags::empty(),
            status: 0,
        });
    }
}
