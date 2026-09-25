# GODFORGE — Vertical Slice (P1)

> §16: *"3 chars, 6 chassis, full forge UI, biome 1 + boss, 2-player co-op netcode, art style target
> locked. Used for publisher pitch / Steam page / Next Fest demo."*
> §20.1: *"Implement the Forge system (chassis + 4 slots + anvil events) before any extra content."*

The build plays the slice with `--phase p1` (the default). Content tagged `P0`/`P1` is in; `EA`/`V1`
rows are authored and validated but gated off. Run `godforge --phase ea` to preview the EA scope.

## 1. Scope and status

| Deliverable | Slice target | Status in this build |
|---|---|---|
| Characters | 3 | **Valdris**, the Anvil-Born (P0): Armor Conversion passive · Bulwark Slam · Siege Stance · ult *Mountainfall*. **Selene**, the Stormcaller: Static Charge · Arc Nova · Blink · ult *Heaven's Verdict*. **Kael**, the Wraithshot: Ghost Step · Fan of Blades · Shadow Roll · ult *Bullet Ballet*. Kits are data (`kits.ron`). |
| Chassis | 6 | Colossus Cannon, Thundercoil Launcher, Serpent SMG, Godsbane Rifle, Wraith Bow, Sunspike Shotgun |
| Parts | — | 38 (6 P0 + 32 P1) across Core / Mechanism / Relic / Sigil. The slice also has 14 named combos. |
| Forge | full UI | Anvil event (dormant → kindling hold-the-ring → hot window → spent), equip / fuse / reroll / salvage, a live DPS-delta preview from the real rules function, named-combo detection, and forge-focus slow-time. |
| Boons | — | 13 slice boons from the pantheon, with offers, rerolls and requirement gating. Duo/Legendary kinds are live in EA content. |
| Biome + boss | Biome 1 + boss | **Cinder Wastes**: 6 swarm types and 3 elites. Mini-boss *The Bellows*, boss *The Slag King* (phased, telegraphed). The path is combat → 3 reward doors → mini-boss → 2 doors → boss, with ≥ 2 anvils guaranteed. |
| Co-op | 2 players | **4 players** over the host-authoritative protocol: loopback host player + UDP remotes, plus bot teammates. Synergies, Team Overdrive, Soul-Tether revive, party scaling. |
| Aim modes | all three | AUTO (−10 % tax), ASSISTED (magnetism), MANUAL (precision + Deadeye up to +20 %). All three are live-switchable on one pipeline. |
| Input | PC + pad + touch | KB/M, gamepad, touch twin-stick and ≥ 44 px buttons. The last-used device wins. |
| Art style | locked | The colour and readability language is locked (§7 of [ARCHITECTURE](ARCHITECTURE.md)). Meshes are greybox primitives until the Blender pipeline delivers. |
| Test rigs | stress + bot run | `--stress 400` and `--bot-run` (both CI gates). Determinism test. Scripted screenshots. |

**Beyond slice scope but already in:** Chaos Tiers 1–20 and the party-scaling tables, the full EA content
set (8 characters, 16 chassis, 120 parts, 100 boons + 16 duos, 3 biomes each with a mini-boss and a boss; see the
[audit](HUNDRED_HOUR_AUDIT.md)), and the join-in-progress netcode path.

**Not in the slice (P2):** Steamworks/SDR glue, the meta hub (Altar of Ember, character trees; both
authored as data), Echo drones, barks/VO, audio, authored art.

## 2. Try it

```sh
cargo run --release                               # solo slice run (Valdris)
cargo run --release -- --character selene --aim manual
cargo run --release -- --bots 3                   # you + 3 bot teammates (4-player co-op)
cargo run --release -- --host 27015               # listen server; friends: --join <ip>:27015
cargo run --release -- --room cinder_anvil_hall   # QA: open in the anvil room
cargo run --release -- --autoplay --bots 3        # attract mode (a bot plays you)
```

Controls: WASD, mouse aim, LMB fire, Space dash, Q/E abilities, R ultimate, V Team Overdrive,
F interact (doors, anvil), Tab forge panel, F1/F2/F3 AUTO/ASSISTED/MANUAL, H help.

## 3. Acceptance criteria (§19) — how this build demonstrates each

| # | Criterion | Evidence / how to check | Status |
|---|---|---|---|
| 1 | Minute 12 shows ≥ 3 distinct weapon-part effects at once, ≥ 55 fps on PC min | The forge compiles parts into one profile, so pierce + fork + chain + explode + orbit all stack; the HUD trait line lists them (e.g. "×5 projectiles · Chain arc ×2 · Explosive"). Host p99 tick is 0.97 ms at 400 enemies. | Sim ✔. The fps gate needs min-spec hardware (P1 exit). |
| 2 | A playtester can explain their build | `weapon::describe` drives the HUD trait line, the forge panel and the end screen: element + behaviours in plain words. | ✔ |
| 3 | 4 strangers: nobody idle > 10 s, revive works, ≥ 1 synergy per run | Soul-Tether caps downtime at 30 s total, with ≤ 3 s revives. 4-bot runs fire synergies continuously ("RAILSHOCK! ×27" in captures). | ✔ with bots. Stranger playtests are pending. |
| 4 | Death at minute 20 feels like progress | Ember accrues per kill, room and victory, and is shown on the end screen. The Altar of Ember and character trees that spend it are authored as data but ship in P2. | Partial |
| 5 | New player finishes run 1 or dies at boss 1 within 25 min | Biome 1 + boss takes 6–7 min for bots. The full EA 3-biome run measured 21.8 min solo and 18.9 min with 4 bots, against a 20–35 min target (humans will run slower than bots). | ✔ (pacing) |
| 6 | Touch prototype clears biome 1 | The touch layer is live and AUTO is the touch default. It needs a device spike. | Built, untested on device |
| 7 | 100-hour audit ≥ 100 h | `gf-content audit` → [HUNDRED_HOUR_AUDIT.md](HUNDRED_HOUR_AUDIT.md). Completionist path estimate ≈ 121 h. | ✔ (estimate) |
| 8 | Attack-mode parity | `godforge --bot-run --aim auto --seed 7` and `--aim manual --seed 7` both finish. AUTO's −10 % tax against MANUAL's Deadeye ceiling is data (`aim_modes.ron`). | ✔ |

## 4. Measured in this build

These are headless bots playing through the real netcode (`godforge --bot-run …`, dev build, this container).

| Run | Outcome | Length | Kills | Peak enemies | Host tick p99 | Max snapshot |
|---|---|---|---|---|---|---|
| Slice, AUTO, seed 7 | Victory, 8 rooms | 6.5 min | 2,057 | 83 | 0.13 ms | 1.4 KB |
| Slice, MANUAL, seed 7 | Victory, 8 rooms | 6.0 min | 1,764 | 80 | 0.12 ms | 1.5 KB |
| Slice, 2 players | Victory, 8 rooms | 6.2 min | 2,622 | 130 | 0.18 ms | 3.8 KB |
| EA, solo | Victory, 24 rooms, 3 biomes | 21.8 min | 7,270 | 119 | 0.16 ms | 1.9 KB |
| EA, 4 players | Victory, 24 rooms, 3 biomes | 18.9 min | 16,430 | 207 | 0.51 ms | 11.5 KB |
| EA, 4 players, 100 ms RTT + 2 % loss, 20 Hz (real time, 5 min box) | 6 rooms cleared, no wipe | 4.8 min | 3,274 | 162 | 1.07 ms | 3.9 KB |
| Chaos stress: 4 players vs 400 enemies | budget held | 2 min | 29,883 | 400 | 0.97 ms | 15.0 KB |

Typical end-of-run bot builds read like the pitch: "Kinetic, Ricochet 4, Fork ×6, Explosive, Doom bursts
every 8 hits, every 4th shot echoes" (Selene), or "Plague, charge shot, ×9 projectiles, Pierce 2, frost
trails, Curse, Lifesteal" (Thessaly).

## 5. Feel checklist (§20.5) — per weapon, before content lock

- [ ] **Impact**: hit flash + squash on the target, spark burst in the element colour, crit/Deadeye numbers bigger and gold/cyan.
- [ ] **Kill feedback**: death burst (elite: gold shockwave), loot beam for Rare+ parts.
- [ ] **Screen juice**: trauma-based shake on big hits, boss phases and downs (toggle **K**).
- [ ] **Sound**: *pending audio pass (P2)*.
- [ ] **Readability at 4P peak**: enemy shots magenta-cored, telegraphs red-white, player zones gold,
      ally effects at 55 % alpha, VFX tier drop at 450/900 live effects.

## 6. Slice exit gates

1. **Fun test**: 10 external playtesters, a post-run micro-survey ("Did this build feel good?"), and
   ≥ 70 % say they want another run.
2. **Perf**: PC-min (GTX 950) at 1080p holds ≥ 55 fps in `--stress 400 --bots 4` with the client attached.
3. **Engine gate (§14)**: if (2) fails, or tooling blocks content, decide on the Unity fallback *now*. Content is
   data, so a port reuses every sheet.
4. **Netcode**: a 4-player WAN session at 100 ms RTT shows no visible rubber-banding. Check with the loopback
   `--rtt 100 --loss 0.02 --minutes 5` bot run first (real time, 20 Hz snapshots), then human sessions.
