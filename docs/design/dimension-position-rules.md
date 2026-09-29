# Position Rules Validation

`dimension_position_rules` seats named dimensions at named slots and lets the greedy search only the slots that are left. A rule is a tier 3 user preference: it shapes a *search*, so the greedy folds honor it and explicitly-named orders (`predefined_orders`, set mode) do not. The rules are still validated in every mode, so a typo fails the run whatever the mode.

For how to drive it, see [Dimension Position Rules](../advanced/dimension-position-rules.md).

## Positions are 0-based, against the storage order

`position` counts from **0**, so `3` is the fourth slot. `"first"` and `"last"` are accepted as names for the end slots.

Positions count against the cube's **storage** order (`get_storage_dimension_order()`), never the presentation order shown in Architect. See [The Order Frame](order-frame.md#the-storage-order-is-the-frame).

The separate `optimize_position` field counts from **1**. Both match their own long-standing documentation, so neither is a defect, but a config that uses both fields must convert between them. `"first"` and `"last"` mean the same thing in both.

## Validation fails fast, and reports everything at once

Rules are validated against the cube's storage order as soon as it has been read, before any reorder is sent. Every problem is reported, not just the first, so a config is fixed in one pass:

| Problem | Reported as |
|---|---|
| Rule is not an object, or lacks `dimension` or `position` | must have a `dimension` and a `position` |
| Dimension is not in the cube | `'<name>'` is not a dimension of this cube |
| Two rules on one dimension | already has a rule at `dimension_position_rules[<i>]` |
| Two rules on one position | position `<n>` is already taken by `dimension_position_rules[<i>]` |
| Dimension is also in `dimensions_to_exclude` | one says leave it where it is, the other says move it to a specific slot |
| Position names no slot (`"middle"`, `2.7`) | names no slot: use a 0-based integer, or `"first"` or `"last"` |
| Position is out of range | out of range for a `<n>`-dimension cube (`0`-`<n-1>`) |
| Position is the right number, wrong type (`"3"`, `3.0`) | position must be an integer: write `3`, not `"3"` |
| Rule moves the locked dimension off the last slot | `'<name>'` has string elements and is locked to position `<n>` |
| Rule gives the locked slot to another dimension | position `<n>` holds `'<locked>'`, which has string elements and never moves |

The last two distinctions are deliberate. A value that plainly names a slot but carries the wrong JSON type is told which number to write, because reporting `"3"` as an unreadable position (at a value the user can see is a number) reads as an accusation of a typo. A value that genuinely names no slot is told that it names no slot.

The two locked-slot collisions are reported here, at startup, rather than being discovered as a zero-result run.

## A rule that cannot be resolved seats nothing

A rule naming an unknown dimension or an unreadable position resolves to no slot. It must not silently reserve one: a slot reserved on behalf of a rule nobody could read narrows the search to fewer orders (possibly zero) while the run still reports success. Resolution and validation are therefore separate: resolution seats only the rules that name a real dimension and a real slot, and validation turns every rule it passed over into an error.

Where two rules conflict, resolution keeps the first so the frame stays deterministic, while validation reports the conflict.

## Pre-application

Rules are applied to the starting order, not merely checked against candidates:

1. Each ruled dimension is **seated** at the slot its rule names.
2. The remaining dimensions keep their relative storage-order sequence in the slots that are left.
3. That **pre-applied order** (not the cube's current order) is where the greedy search begins.
4. A ruled dimension is immovable and its slot is never a sweep target, exactly as for the locked dimension and for `dimensions_to_exclude`. The search runs over the remaining positions.

`admits()` still refuses any candidate that violates a rule, and the refusal is logged at DEBUG. With pre-application in place the search does not generate one, so that check is a backstop that states the invariant rather than the mechanism that enforces it.

## Guarantees

- Every malformed rule is an error at startup, named by its index in the config, before any reorder is sent.
- A rule that is not enforceable never constrains the search.
- The search starts from the layout the rules describe.
- A ruled dimension is never moved by the search, and its slot is never swept.
- The result count reflects only orders that were actually evaluated.
