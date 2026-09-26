//! Light flashes: a small pool of point lights (no shadows) lent to the brightest live requests.
//! Impacts, muzzle flashes and bursts spill real light on the painted floor and the toon-lit
//! bodies around them (VFX_STYLE §11 layer 1 "light spill"). Only your own effects and the
//! world's (anvil, bosses) ask for one; allies' never do (§20.2).

use gf_engine::prelude::*;

/// Pooled point lights: the clustered forward renderer stays cheap at this count.
pub const POOL: usize = 8;

/// A requested flash.
#[derive(Clone, Copy, Debug)]
pub struct Flash {
    pub pos: Vec3,
    pub follow: Option<Entity>,
    pub color: Color,
    /// Peak intensity (lumens).
    pub intensity: f32,
    pub range: f32,
    pub age: f32,
    pub life: f32,
    /// Fraction of the life spent rising to the peak (fast in, slow out).
    pub attack: f32,
    pub(crate) world: Vec3,
}

impl Flash {
    pub fn new(pos: Vec3, color: Color, intensity: f32, range: f32, life: f32) -> Flash {
        Flash { pos, follow: None, color, intensity, range, age: 0.0, life, attack: 0.08, world: pos }
    }

    pub fn current(&self) -> f32 {
        let k = (self.age / self.life.max(1e-4)).clamp(0.0, 1.0);
        let e = if k < self.attack {
            k / self.attack.max(1e-4)
        } else {
            (1.0 - (k - self.attack) / (1.0 - self.attack)).powi(2)
        };
        self.intensity * e
    }
}

/// The pooled light entities.
#[derive(Component)]
pub struct PooledLight(pub usize);

/// The pool, disjoint from the camera and the layer draws.
pub type LightPool<'w, 's> = Query<
    'w,
    's,
    (&'static PooledLight, &'static mut PointLight, &'static mut Transform, &'static mut Visibility),
    (Without<crate::camera::MainCamera>, Without<super::mesh::FxLayerDraw>),
>;

pub(super) fn spawn_pool(mut commands: Commands) {
    for i in 0..POOL {
        commands.spawn((
            Name::new(format!("fx light {i}")),
            PooledLight(i),
            PointLight { intensity: 0.0, range: 6.0, radius: 0.2, shadow_maps_enabled: false, ..default() },
            Transform::default(),
            Visibility::Hidden,
        ));
    }
}

/// Lend the pool to the brightest flashes this frame.
pub(super) fn assign(flashes: &[Flash], lights: &mut LightPool) {
    let mut order: [(f32, usize); 64] = [(0.0, 0); 64];
    let mut n = 0;
    for (i, f) in flashes.iter().enumerate() {
        let v = f.current();
        if v > 1.0 {
            if n < order.len() {
                order[n] = (v, i);
                n += 1;
            } else if let Some(min) = order.iter_mut().min_by(|a, b| a.0.total_cmp(&b.0))
                && min.0 < v
            {
                *min = (v, i);
            }
        }
    }
    let best = &mut order[..n];
    best.sort_unstable_by(|a, b| b.0.total_cmp(&a.0));
    for (slot, mut light, mut tf, mut vis) in lights.iter_mut() {
        match best.get(slot.0) {
            Some(&(v, i)) => {
                let f = &flashes[i];
                light.intensity = v;
                light.color = f.color;
                light.range = f.range;
                tf.translation = f.world;
                if *vis != Visibility::Inherited {
                    *vis = Visibility::Inherited;
                }
            }
            None => {
                if *vis != Visibility::Hidden {
                    *vis = Visibility::Hidden;
                    light.intensity = 0.0;
                }
            }
        }
    }
}
