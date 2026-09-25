//! Entity-level delta compression against a client-acknowledged baseline.
//!
//! Both lists are sorted by `NetId`. Entities identical to the baseline are omitted; entities
//! missing from the new list are sent as removals. Straight-flying projectiles, pickups, doors and
//! telegraphs are therefore free after their first snapshot (see `Motion`).

use crate::protocol::EntityView;
use gf_core::ids::NetId;
use std::cmp::Ordering;

/// Compute `(changed, removed)` turning `baseline` into `current`.
pub fn diff(baseline: &[EntityView], current: &[EntityView]) -> (Vec<EntityView>, Vec<NetId>) {
    debug_assert!(is_sorted(baseline) && is_sorted(current));
    let mut changed = Vec::new();
    let mut removed = Vec::new();
    let (mut i, mut j) = (0, 0);
    while i < baseline.len() || j < current.len() {
        match (baseline.get(i), current.get(j)) {
            (Some(b), Some(c)) => match b.id.cmp(&c.id) {
                Ordering::Less => {
                    removed.push(b.id);
                    i += 1;
                }
                Ordering::Greater => {
                    changed.push(*c);
                    j += 1;
                }
                Ordering::Equal => {
                    if b != c {
                        changed.push(*c);
                    }
                    i += 1;
                    j += 1;
                }
            },
            (Some(b), None) => {
                removed.push(b.id);
                i += 1;
            }
            (None, Some(c)) => {
                changed.push(*c);
                j += 1;
            }
            (None, None) => break,
        }
    }
    (changed, removed)
}

/// Reconstruct the full entity list from a baseline and a delta.
pub fn apply(baseline: &[EntityView], changed: &[EntityView], removed: &[NetId]) -> Vec<EntityView> {
    let mut out = Vec::with_capacity(baseline.len() + changed.len());
    let (mut i, mut j) = (0, 0);
    let is_removed = |id: NetId| removed.binary_search(&id).is_ok();
    while i < baseline.len() || j < changed.len() {
        match (baseline.get(i), changed.get(j)) {
            (Some(b), Some(c)) => match b.id.cmp(&c.id) {
                Ordering::Less => {
                    if !is_removed(b.id) {
                        out.push(*b);
                    }
                    i += 1;
                }
                Ordering::Greater => {
                    out.push(*c);
                    j += 1;
                }
                Ordering::Equal => {
                    out.push(*c);
                    i += 1;
                    j += 1;
                }
            },
            (Some(b), None) => {
                if !is_removed(b.id) {
                    out.push(*b);
                }
                i += 1;
            }
            (None, Some(c)) => {
                out.push(*c);
                j += 1;
            }
            (None, None) => break,
        }
    }
    out
}

fn is_sorted(v: &[EntityView]) -> bool {
    v.windows(2).all(|w| w[0].id < w[1].id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::{EntityFlags, EntityKind};
    use crate::quant::QPos;

    fn e(id: u32, x: i16) -> EntityView {
        EntityView {
            id: NetId(id),
            kind: EntityKind::Enemy { def: 0 },
            pos: QPos(x, 0),
            motion: None,
            facing: 0,
            hp: 255,
            flags: EntityFlags::empty(),
            status: 0,
        }
    }

    #[test]
    fn round_trip() {
        let base = vec![e(1, 0), e(2, 0), e(4, 0), e(7, 0)];
        let cur = vec![e(2, 5), e(3, 0), e(4, 0), e(9, 1)];
        let (changed, removed) = diff(&base, &cur);
        assert_eq!(changed.iter().map(|c| c.id.0).collect::<Vec<_>>(), vec![2, 3, 9]);
        assert_eq!(removed, vec![NetId(1), NetId(7)]);
        assert_eq!(apply(&base, &changed, &removed), cur);
    }

    #[test]
    fn empty_cases() {
        let cur = vec![e(1, 0), e(2, 0)];
        let (c, r) = diff(&[], &cur);
        assert_eq!(apply(&[], &c, &r), cur);
        let (c, r) = diff(&cur, &[]);
        assert!(c.is_empty());
        assert_eq!(apply(&cur, &c, &r), vec![]);
        let (c, r) = diff(&cur, &cur);
        assert!(c.is_empty() && r.is_empty(), "unchanged world costs nothing");
    }
}
