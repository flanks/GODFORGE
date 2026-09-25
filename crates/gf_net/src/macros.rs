//! Tiny bitflags implementation (avoids a dependency for two flag sets).

#[macro_export]
macro_rules! bitflags_lite {
    ($(#[$m:meta])* pub struct $name:ident: $t:ty { $($(#[$fm:meta])* const $f:ident = $v:expr;)* }) => {
        $(#[$m])*
        #[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
        pub struct $name(pub $t);
        #[allow(dead_code)]
        impl $name {
            $($(#[$fm])* pub const $f: $name = $name($v);)*
            pub const fn empty() -> Self { $name(0) }
            pub const fn contains(self, other: $name) -> bool { self.0 & other.0 == other.0 }
            pub fn set(&mut self, other: $name, on: bool) {
                if on { self.0 |= other.0 } else { self.0 &= !other.0 }
            }
        }
        impl core::ops::BitOr for $name {
            type Output = $name;
            fn bitor(self, rhs: $name) -> $name { $name(self.0 | rhs.0) }
        }
        impl core::ops::BitOrAssign for $name {
            fn bitor_assign(&mut self, rhs: $name) { self.0 |= rhs.0 }
        }
    };
}
