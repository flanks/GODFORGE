//! `SimServer`: owns the authoritative ECS world and the host side of the session. One call to
//! [`SimServer::tick`] = poll network → apply commands → step `SimTick` → stream snapshots.

use crate::components::*;
use crate::director::StressMode;
use crate::resources::*;
use crate::{SimTick, build_schedule, players, run, snapshot};
use gf_content::ContentDb;
use gf_content::schema::Phase;
use gf_core::scaling::{compile_enemy_tuning, party_scaling};
use gf_engine::prelude::*;
use gf_net::{NetServer, ServerConfig, ServerTransport, SessionEvent};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

#[derive(Clone, Debug)]
pub struct SimConfig {
    pub seed: u64,
    pub phase: Phase,
    pub chaos_tier: u8,
    /// Snapshot every N ticks (1 = 60 Hz for loopback, 3 = 20 Hz for remote clients).
    pub snapshot_every: u8,
    pub max_players: usize,
    pub allow_join_in_progress: bool,
    /// Chaos stress scene: hold this many enemies alive (§20.7).
    pub stress_enemies: Option<u32>,
}

impl Default for SimConfig {
    fn default() -> Self {
        Self {
            seed: 0x60DF_0E6E,
            phase: Phase::P1,
            chaos_tier: 0,
            snapshot_every: 1,
            max_players: 4,
            allow_join_in_progress: true,
            stress_enemies: None,
        }
    }
}

/// Rolling per-tick timing (host performance budget telemetry).
#[derive(Clone, Debug, Default)]
pub struct ServerStats {
    pub ticks: u64,
    pub last_tick_us: u64,
    pub max_tick_us: u64,
    pub total_tick_us: u64,
    pub last_snapshot_bytes: usize,
    pub max_snapshot_bytes: usize,
    pub max_entities: usize,
    pub max_enemies: usize,
    samples: Vec<u32>,
}

impl ServerStats {
    fn record(&mut self, us: u64) {
        self.ticks += 1;
        self.last_tick_us = us;
        self.max_tick_us = self.max_tick_us.max(us);
        self.total_tick_us += us;
        if self.samples.len() < 200_000 {
            self.samples.push(us as u32);
        }
    }

    pub fn mean_tick_ms(&self) -> f64 {
        self.total_tick_us as f64 / self.ticks.max(1) as f64 / 1000.0
    }

    /// Percentile tick time in milliseconds (0..=100).
    pub fn percentile_ms(&self, p: f64) -> f64 {
        if self.samples.is_empty() {
            return 0.0;
        }
        let mut s = self.samples.clone();
        s.sort_unstable();
        let i = ((p / 100.0) * (s.len() - 1) as f64).round() as usize;
        s[i] as f64 / 1000.0
    }
}

pub struct SimServer {
    app: App,
    net: NetServer<Box<dyn ServerTransport>>,
    cfg: SimConfig,
    pub stats: ServerStats,
}

impl SimServer {
    pub fn new(content: Arc<ContentDb>, cfg: SimConfig, transport: Box<dyn ServerTransport>) -> Self {
        let net = NetServer::new(
            transport,
            ServerConfig {
                content_hash: content.hash,
                tick_hz: gf_core::SIM_HZ as u16,
                snapshot_every: cfg.snapshot_every.max(1),
                seed: cfg.seed,
                max_players: cfg.max_players,
                allow_join_in_progress: cfg.allow_join_in_progress,
            },
        );
        let mut app = App::new();
        let tuning =
            compile_enemy_tuning(&party_scaling(&content.party_scaling, 1), &content.chaos_tiers, cfg.chaos_tier);
        app.insert_resource(Content(content))
            .insert_resource(SimSettings { seed: cfg.seed, phase: cfg.phase, chaos_tier: cfg.chaos_tier })
            .insert_resource(SimClock {
                tick: 0,
                dt: gf_core::SIM_DT,
                scale: 1.0,
                time: 0.0,
                freeze: 0.0,
                freeze_resets_cooldowns: false,
                reset_cooldowns: false,
            })
            .insert_resource(Rngs::new(cfg.seed))
            .insert_resource(NetIds::default())
            .insert_resource(Events::default())
            .insert_resource(DamageQueue::default())
            .insert_resource(PlayerHits::default())
            .insert_resource(Kills::default())
            .insert_resource(ArenaRes::default())
            .insert_resource(Grid::default())
            .insert_resource(Tuning { enemy: tuning, party: 1 })
            .insert_resource(Overdrive::default())
            .insert_resource(TeamBoons::default())
            .insert_resource(RunState::default())
            .insert_resource(Encounter::default())
            .insert_resource(StressMode(cfg.stress_enemies));
        build_schedule(&mut app);
        Self { app, net, cfg, stats: ServerStats::default() }
    }

    pub fn world(&self) -> &World {
        self.app.world()
    }

    pub fn world_mut(&mut self) -> &mut World {
        self.app.world_mut()
    }

    pub fn config(&self) -> &SimConfig {
        &self.cfg
    }

    fn retune_party(&mut self) {
        let world = self.app.world_mut();
        let party = world.query::<&Player>().iter(world).count().max(1) as u8;
        let db = world.resource::<Content>().0.clone();
        let tier = world.resource::<SimSettings>().chaos_tier;
        let enemy = compile_enemy_tuning(&party_scaling(&db.party_scaling, party), &db.chaos_tiers, tier);
        world.insert_resource(Tuning { enemy, party });
    }

    fn handle_session(&mut self, events: Vec<SessionEvent>) {
        for ev in events {
            match ev {
                SessionEvent::Joined { slot, name, loadout } => {
                    let world = self.app.world_mut();
                    if !world.resource::<RunState>().started {
                        run::start_run(world);
                        self.net.set_started(true);
                    }
                    players::spawn_player(self.app.world_mut(), slot, &name, loadout);
                    self.retune_party();
                }
                SessionEvent::Left { slot } => {
                    let world = self.app.world_mut();
                    let leaving: Vec<Entity> = world
                        .query::<(Entity, &Player)>()
                        .iter(world)
                        .filter(|(_, p)| p.slot == slot)
                        .map(|(e, _)| e)
                        .collect();
                    let blades: Vec<Entity> = world
                        .query::<(Entity, &Blade)>()
                        .iter(world)
                        .filter(|(_, b)| leaving.contains(&b.owner))
                        .map(|(e, _)| e)
                        .collect();
                    for e in leaving.into_iter().chain(blades) {
                        world.despawn(e);
                    }
                    self.retune_party();
                }
            }
        }
    }

    /// One authoritative tick.
    pub fn tick(&mut self) {
        let started = Instant::now();
        let events = self.net.poll();
        self.handle_session(events);

        // Commands → player inputs.
        let world = self.app.world_mut();
        let slots: Vec<(Entity, u8)> =
            world.query::<(Entity, &Player)>().iter(world).map(|(e, p)| (e, p.slot)).collect();
        for (entity, slot) in slots {
            if let Some(cmd) = self.net.next_command(slot)
                && let Some(mut input) = self.app.world_mut().get_mut::<PlayerInput>(entity)
            {
                input.cmd = cmd;
                input.has_input = true;
            }
        }

        self.app.world_mut().run_schedule(SimTick);

        // State → snapshots.
        let world = self.app.world_mut();
        let run = snapshot::run_view(world);
        let players = snapshot::player_views(world);
        let entities = snapshot::entity_views(world);
        let privates = snapshot::private_views(world);
        let events = std::mem::take(&mut world.resource_mut::<Events>().0);
        let tick = world.resource::<SimClock>().tick;
        self.stats.max_entities = self.stats.max_entities.max(entities.len());
        let enemies = entities.iter().filter(|e| matches!(e.kind, gf_net::EntityKind::Enemy { .. })).count();
        self.stats.max_enemies = self.stats.max_enemies.max(enemies);
        self.net.broadcast(
            tick,
            &run,
            &players,
            &mut |slot| privates.iter().find(|(s, _)| *s == slot).map(|(_, p)| p.clone()).unwrap_or_default(),
            entities,
            &events,
        );
        if self.net.last_bytes_sent > 0 {
            let per = self.net.last_bytes_sent / self.net.player_count().max(1);
            self.stats.last_snapshot_bytes = per;
            self.stats.max_snapshot_bytes = self.stats.max_snapshot_bytes.max(per);
        }
        self.stats.record(started.elapsed().as_micros() as u64);
    }

    pub fn run_phase(&self) -> gf_net::RunPhase {
        self.app.world().resource::<RunState>().phase
    }

    pub fn player_count(&self) -> usize {
        self.net.player_count()
    }

    /// Run in real time on the current thread until `stop` is set (listen-server thread).
    pub fn run_realtime(mut self, stop: Arc<AtomicBool>) {
        let dt = Duration::from_secs_f64(1.0 / gf_core::SIM_HZ as f64);
        let mut next = Instant::now();
        while !stop.load(Ordering::Relaxed) {
            self.tick();
            next += dt;
            let now = Instant::now();
            if next > now {
                std::thread::sleep(next - now);
            } else if now - next > dt * 10 {
                next = now; // fell far behind (debugger / hitch): don't spiral
            }
        }
    }

    /// Spawn the server on its own thread; returns a stop flag and the join handle.
    pub fn spawn_thread(
        content: Arc<ContentDb>,
        cfg: SimConfig,
        transport: Box<dyn ServerTransport>,
    ) -> (Arc<AtomicBool>, std::thread::JoinHandle<()>) {
        let stop = Arc::new(AtomicBool::new(false));
        let flag = stop.clone();
        let handle = std::thread::Builder::new()
            .name("godforge-host".into())
            .spawn(move || SimServer::new(content, cfg, transport).run_realtime(flag))
            .expect("spawn host thread");
        (stop, handle)
    }
}
