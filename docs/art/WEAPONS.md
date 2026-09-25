# GODFORGE: the weapon contract

Every chassis in `content/sheets/chassis.csv` ships as **one weapon model**. The weapon attaches to
the hand socket of the hero master skeleton, so any hero can wield any chassis. There is no human
artist. Weapons are built from code with `tools/blender/gf_assets` (Blender 5.2, headless), and the
user gives the final visual approval. The worked example is
`tools/blender/gf_assets/weapons/sunspike_shotgun.py`; copy it to start a new weapon.

The numbers on this page also live in `tools/blender/gf_assets/gfa_spec.py`, which the builder and the
validator read. If you change one, change the other.

## 1. What ships

| File | What |
|---|---|
| `assets/models/weapons/<key>.glb` | glTF binary, +Y up, uncompressed (no Draco or meshopt: bevy_gltf 0.20 cannot load them), textures embedded |
| `assets/models/weapons/<key>.meta.json` | sidecar: `kind, key, tier, tris, textures, sockets, clips, skeleton, status` plus bounds, sha256, source and validation |
| `art/weapons/<key>/` | the art pack: `source/<key>.blend`, `textures/`, `reports/<key>_review.png`, `status.json`, `README.md` |

`<key>` is the chassis key (`ChassisDef.key`). The GLB has this node tree:

```text
<key>                 root node = the GRIP FRAME (identity transform)
  <key>_mesh          the whole weapon: one mesh, one material (base colour + emissive)
  grip_R              main-hand palm centre (= the origin)
  grip_L              off-hand palm centre (two-handed, gauntlet pair, dual)
  muzzle              where shots / beams / strikes leave the weapon
  glow_core           optional: centre of the main glow (charge fill, point light)
  offhand             dual weapons only: the off-hand mesh, its origin on grip_L
```

A build is final only when the user approves it. Until then, meta.json says
`"status": "ai_final_pending_user_approval"` and the pack's `status.json` has stage `2_user_approval`
set to `pending_human`.

## 2. Axes and the grip frame

**The grip frame.** In Blender (Z up, 1 unit = 1 m) the weapon is authored so that:

* the **origin** is the palm centre of the main (right) hand on the grip;
* **+Y** runs along the barrel, i.e. the aim or strike direction;
* **+Z** is up, the weapon's top. For fist weapons it points out of the back of the hand, as in Brax's
  `s2_weapon.py` frame. For other weapons it is the side the back of the hand faces in the neutral hold;
* **+X** is the weapon's right (= Y × Z).

How the frame converts on its way into the game:

| | forward (barrel) | up | right |
|---|---|---|---|
| Blender grip frame | +Y | +Z | +X |
| glTF / Bevy local (exported with +Y up: `(x, y, z) -> (x, z, -y)`) | **-Z** | +Y | +X |
| Engine convention (`palette.rs` `yaw()`: meshes whose forward is world -Z; sim +y = world -Z) | -Z | +Y | +X |

A weapon therefore needs **no correction rotation**. It is an identity-transform child of whatever
node already turns with the aim.

Creatures follow a different rule: they face Blender -Y, which becomes glTF +Z (the glTF "front"). The
client turns them with `yaw(angle) * Quat::from_rotation_y(PI)`; see ENEMIES.md section 2. A weapon's +Y
is a local grip axis, not a world facing. When a hero who faces -Y points a gun forward, the gun's +Y
points along world -Y.

## 3. Sockets

Sockets are empties parented to the root and named exactly as below; `gfa_validate.py` checks them.
Each one uses the grip-frame orientation (+Y forward, +Z up) unless the table says otherwise.

| Socket | Required for | Position | Notes |
|---|---|---|---|
| `grip_R` | every weapon | the origin, identity | explicit, so client code can always look it up by name |
| `grip_L` | `two_handed`, `gauntlet_pair`, dual weapons | off-hand palm centre (pump, foregrip, second pistol, left gauntlet) | the left-hand IK target |
| `muzzle` | every ranged weapon; for melee, the strike point | bore exit on the barrel axis, +Y = the shot direction | projectile spawn and muzzle VFX; beams start here |
| `glow_core` | optional | centre of the main glow | charge-fill VFX, point light, heat pulse |
| `muzzle_2` | optional | second barrel | multi-barrel or dual fire alternation |
| `eject` | optional | casing / steam vent | +Y = the ejection direction |
| `offhand` | dual weapons only | an off-hand mesh node whose origin sits on `grip_L` | the client re-parents it to the left-hand socket with an identity transform |

## 4. Scale

Heroes are 2.2 m tall (2.0-2.3 m) and fill 6-8 % of the screen. The game camera is orthographic
with a 55° pitch and a 22-28 m view height, so at 1080p a metre is **39-49 px**. Weapons are
exaggerated about 1.2-1.4× past real-world size so that the silhouette survives.

| Class | Length | At 49 px/m |
|---|---|---|
| pistol, orb, disc, whip handle (one-handed) | 0.35-0.55 m | 17-27 px |
| SMG, carbine, javelin bundle | 0.6-0.85 m | 30-42 px |
| shotgun, launcher, sprayer (two-handed) | 0.9-1.15 m | 44-56 px |
| rifle, bow, harpoon | 1.2-1.6 m | 59-78 px |
| rail, lance, greatbow | 1.5-2.1 m | 74-103 px |
| heavy (cannon, mortar, hammer) | 1.0-1.6 m, with the front mass ≥ 0.25 m thick | 49-78 px |

The weapon's big shape, not its detail, must say what the chassis does. Before a weapon is
committed, check its silhouette at 1x in the in-game review render.

## 5. Silhouette language per family

The family comes from the chassis `tags`. When a chassis has several tags, the first one in this list
wins: melee > heavy/splash > beam > charge > spread > precise/pierce > chain > ricochet > rapid.

| Family (tags) | Verb | Shape rules |
|---|---|---|
| **heavy / splash** | THE LUMP | top-heavy; the biggest bore in the arsenal; a drum, chamber or maw that is ≥ 1/3 of the length; short relative to its thickness (about 4:1); a wide, round muzzle |
| **rapid** | THE STREAM | long and lean, forward-swept; many small repeated elements (vents, fins, a belt or drum): the repetition reads as rate of fire; a small muzzle |
| **precise / pierce** | THE NEEDLE | the longest, thinnest line (≥ 10:1); a scope or sight blade; one sharp point at the muzzle; almost nothing sticks out sideways |
| **charge** | THE DRAW | visible stored tension: bow limbs, capacitor rings, a draw handle, curves under load; a `glow_core` that visibly fills |
| **spread** | THE FAN | short, with a front that flares or fans out (crown, bell, fanned barrels); the muzzle is ≥ 1.5× wider than the body |
| **melee** | THE HEAD | the mass sits at the striking end (hammer head, gauntlet block); a short grip; blunt, oversized forms |
| **beam** | THE EMITTER | a lens, prism or nozzle at the front and a feed (tank, bellows, cables) at the back; long parallel lines along the body |
| **chain** | THE CONDUCTOR | forked prongs, coils or zig-zag conductors at the tip; the lash or arc path reads as a line |
| **ricochet** | THE DISC | round, flat discs, coins, curved blades; orbiting or stacked round parts |

Secondary tags add one accent and never change the family verb: storm (coils), void (a dark hollow
core), homing (a seeker eye or strings), time (a dial or gnomon), pull (barbs or a reel), ramp (a crank
or flywheel).

Every chassis in `content/sheets/chassis.csv` today:

| Chassis | Tier | Family | Brief |
|---|---|---|---|
| **colossus_cannon** | two_handed | heavy | **built** (`art/weapons/colossus_cannon/`): **arm-mounted**, after Valdris's concept. A plated sleeve over the right forearm, with the fist on an inner handle (`grip_R`); an octagonal shell-drum breech with top clamps and an under-bracket; a stepped muzzle collar whose shell-burst ring is glowing slots and ports around an ember bore. `grip_L` is a side handle on the drum's left. The hold needs the forearm along -Y inside the sleeve |
| **thundercoil_launcher** | two_handed | heavy (storm) | **built** (`art/weapons/thundercoil_launcher/`): slender and elegant per Selene's brief, so the lump is ONE storm-glass orb (0.20 m) in the breech between the hands: a plasma globe with crackle veins, set in brass calyx cups. A copper coil pack on the neck and a tapering induction coil on the barrel; a round emitter muzzle (copper halo, three thick conductor prongs with glowing electrode tips, glowing bore; 0.23 m across); a smoked-bone swan-neck skeleton stock (a mid value, so the orb and muzzle lead at 1x) with a bronze crescent-moon butt. Storm glow only in the emissive (about 18 % of the surface). `glow_core` = the orb centre |
| **serpent_smg** | one_handed | rapid | **built** (`art/weapons/serpent_smg/`): one serpent is the gun. A bone-rattle tail on the receiver; four tight diamond-back coils around the bronze receiver (the stripe rhythm); a lean neck along a dark barrel with four glowing needle quills; the viper head is the muzzle (jaws open, bone fangs, slit-pupil eyes, a glowing mouth spitting the needle barrel). A bronze drum with engraved scales and a coiled-tail spiral on its faces sits in front of the grip. `glow_core` = the throat |
| **godsbane_rifle** | two_handed | precise (pierce) | **built** (`art/weapons/godsbane_rifle/`): the NEEDLE at 1.60 m, the longest line so far. A god's femur for a stock: the butt is the bone's double knuckle, with a carved gold god-eye with a glowing slit iris, and hairline cracks. A dark engraved iron receiver sits under a cut Kinetic-cream crystal scope in gold claw rings: triangular facets in three painted values with a darker core and no glow, so the muzzle stays the brightest point. An octagonal barrel is framed by two gilded side rails and a gilded top rib with a sight blade, with three large engraved sigils between the bands (forked stave, god-eye, fang). A faceted gold crown with glowing channels and a glowing bore pupil, and a bone fang under it as the one sharp point. `glow_core` = the crystal, `eject` = the right-side port |
| **wraith_bow** | two_handed | charge (pierce, void) | **built** (`art/weapons/wraith_bow/`): a winged recurve of pale wraith-wood and dark iron at half draw, canted 72° about the aim so that the feathered limbs face the 55° camera; a pale ghost-lilac string (painted, not lit), a nocked hex-bolt whose broadhead has a painted light/shadow split along its ridge, a void eye on the riser. Only the broadhead, the eye and the outermost feather tips glow (about 6 % of the atlas), so bloom stays clear of player violet. `grip_R` = the right palm on the string's nocking point (the drawing hand), `grip_L` = the left palm on the riser grip, `muzzle` = the arrow rest, `glow_core` = the bolt head |
| **sunspike_shotgun** | two_handed | spread | **built**: a blunderbuss bell crowned with ten sun-rays |
| anvil_gauntlets | gauntlet_pair | melee | owned by Brax's agent (`art/weapons/anvil_gauntlets/`) |
| longstrider_rail | two_handed | charge / precise | a rail twice the hero's arm span; capacitor rings along it |
| coinshooter | two_handed (dual) | ricochet | two pistols with coin magazines; the second one is the `offhand` node |
| pendulum_repeater | two_handed | rapid (ramp) | a crank flywheel and a swinging pendulum hammer |
| bellowfire_projector | two_handed | beam | a bellows tank at the back and a forge nozzle at the front |
| gravemaw_mortar | two_handed | heavy | a squat maw-shaped tube with teeth; lobbed shells |
| stormlash | one_handed | chain | a handle and a coiled lightning lash; `muzzle` = the coil tip |
| seraph_lance | two_handed | beam / precise | a spear-length radiant emitter with a prism tip |
| tidecaller_harpoon | two_handed | charge (pull) | a harpoon gun with a reel; a barbed head in the muzzle |
| orrery_discs | one_handed | ricochet | a wrist orrery: stacked planetary blade-discs on rings |
| huntmother_javelins | one_handed | (kinetic blade) | a barbed javelin in hand plus a bundle on the forearm |
| chorus_harp | one_handed | (homing) | a lyre-harp with glowing strings |
| plaguebloom_sprayer | two_handed | beam | a flower-bulb tank and a petal nozzle |
| dawnbreaker_carbine | two_handed | (radiant slug) | a compact carbine with a sunrise halo sight |
| titanfall_hammer | two_handed | melee / heavy | an anvil-sized head on a short haft; `muzzle` = the centre of the striking face |
| voidheart_singularity | two_handed | charge (void) | a caged void heart held in both hands |
| echoing_greatbow | two_handed | charge / spread | a great bow with three nocked arrows (the fan shows in the arrows) |
| epochal_sundial | one_handed | (time) | a sundial disc whose gnomon is a blade |

The tier column is a proposal for the budget class. The weapon agent confirms it in the pack
README.

## 6. Budgets, material, textures

| Tier (`gfa_spec.BUDGETS`) | Triangles | Texture |
|---|---|---|
| `weapon_one_handed` | 1,000-2,500 | 512-1024 px |
| `weapon_two_handed` (and heavy, and dual) | 2,000-4,000 | 1024 px |
| `weapon_gauntlet_pair` | 4,000-8,000 | 1024 px |

* **One material:** a base-colour texture (sRGB) plus an emissive texture (sRGB, black where nothing
  glows). Roughness is 0.85, metallic 0, single-sided. The engine wraps it in its toon material
  (`materials.rs` `toon_from_standard`), which adds the posterised ramp, the rim light, the ink edge
  and a faint brush noise. **Never bake lighting direction** into the colour.
* **Painting** (`gfa_paint.py`): flat value planes per zone, cavity darks and contact shadows in the
  zone's shadow hue, brushy broken highlights on convex edges, low-frequency brush noise only, painted
  line decals (runes, carvings). Emission lives in its own texture. It is authored at strength 1.0,
  and the engine scales it.
* **Colour:** use the warm metals of the player's arsenal (bone-brass, bronze, dark iron, dark wood) plus
  the chassis' element hue from `palette.rs` `element_color`. Kinetic `#F4E3C1`, Flame `#FF7A1A`, Storm
  `#3FD8FF`, Void `#A45CFF`, Plague `#86E03A`, Radiant `#FFE27A`. Glows use the element hue. The enemy
  telegraph red-white never appears on a weapon.
* **Value rhythm:** alternate dark and light masses along the weapon, and put the brightest value
  (the glow) where the shot comes out.

## 7. How Bevy attaches a weapon

The art track only produces files. Wiring them into the client belongs to the engine agent, in
`crates/gf_client`. The contract for that work:

1. **Now (greybox heroes).** `scene.rs` `spawn_rig` makes an aim `pivot` (`Transform (0, 1.05, 0)`,
   turned every frame with `yaw(aim)`) whose greybox gun points along -Z. Spawn
   `SceneRoot(assets.load("models/weapons/<key>.glb#Scene0"))` as a child of `pivot`. Use
   `Transform::from_xyz(r * 0.75, 0.0, -0.12)` with an **identity rotation**, then hide the brass cube
   and the muzzle sphere. The node named `muzzle` gives the projectile and VFX origin. When the file
   is missing, keep the greybox (ARCHITECTURE §9).
2. **With GF_Hero_v1.** The weapon scene becomes an identity child of the **`weapon_socket_R`** bone
   entity. `grip_L` (world transform) is the left-hand IK target, and `offhand` is re-parented to
   `weapon_socket_L`. For the identity to hold, the socket's glTF local frame has to equal the grip
   frame: -Z along the aim, +Y up, +X to the weapon's right. glTF keeps Blender's **bone-local** axes
   as they are (checked on GF_Swarm_v1 exports). So in Blender the rig author makes `weapon_socket_R`
   point straight up (bone +Y = up) in the aiming hold, with its local **+Z pointing back** along the
   aim line. If the socket bone instead runs along the aim (bone +Y = aim, +Z = up), the client adds a
   fixed `Quat::from_rotation_x(FRAC_PI_2)` on the weapon child. Record whichever choice is made in
   ART_PIPELINE §5.
3. Recoil, aim offsets and the kick pivot (the palm = the origin) stay procedural (ARCHITECTURE §9).

## 8. Build workflow

```text
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/weapons/<key>.py -- [--size 1024] [--no-review]
python tools/blender/gf_assets/gfa_validate.py assets/models/weapons/<key>.glb     (stdlib only; exit 1 on errors)
```

One build runs everything in about 40 s on the CPU: geometry → UVs → Cycles CPU bakes → painting →
`.blend` → GLB + meta.json + validation (exit 1 on failure) → review renders and contact sheet →
`status.json`. The review uses Cycles on the CPU and Workbench only; never EEVEE, because the GPU is
shared.

**The review sheet** (`art/weapons/<key>/reports/<key>_review.png`, < 2 MB) contains:

* a six-view turnaround with the final textures in the engine-like toon preview;
* the in-game camera: 55° pitch, 22 m view height, 1080p pixel size, the weapon held by a 2.2 m
  mannequin, two aim directions, shown at 1x and 3x;
* fitted silhouettes and game-size silhouettes;
* both textures, the palette and the metrics.

Look at it yourself, and iterate until the silhouette reads at 1x and the surface looks painted, not
noisy.

**Commit** your own paths only: the build script, `art/weapons/<key>/` (README, status.json, source
`.blend`, textures, reports; `work/` is ignored by the pack's `.gitignore`) and
`assets/models/weapons/<key>.glb` + `.meta.json`. `.glb`, `.blend` and `art/**/textures/**/*.png` go
through Git LFS.

## 9. Checklist

- [ ] The family verb reads in the 1x in-game silhouette, and so does the tier size.
- [ ] Grip frame: `grip_R` at the origin, `muzzle` on the barrel axis in front, `grip_L` where the off-hand goes.
- [ ] Triangles and texture size are inside the tier budget. There is one material with base colour + emissive.
- [ ] No baked light direction, no grunge; the brightest value is at the muzzle / glow.
- [ ] The glow uses the element hue; there is no red-white telegraph colour.
- [ ] `gfa_validate.py` prints OK; meta.json has `status: ai_final_pending_user_approval`.
- [ ] The pack README records the brief, the decisions, the metrics and how to rebuild.
