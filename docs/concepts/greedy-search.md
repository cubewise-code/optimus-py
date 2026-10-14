# The Greedy Search

OptimusPy's default optimizer is an **outside-in greedy**. It places one storage slot at a time, starting at the ends of the order and working toward the middle, and at every slot it measures every dimension that has not been placed yet. Measurement decides every placement. Leaf counts do not.

## The walk

Slots are visited in this order: the last slot, the first slot, the second-to-last, the second, and so on, stopping at the midpoint of the cube's full storage order. On a 6-dimension cube the walk is slot 6, slot 1, slot 5, slot 2.

At each slot:

1. Every dimension not yet placed is swapped into the slot, one at a time, and measured with a real reorder.
2. The dimension already in the slot is not re-measured. The order the search is standing on is its result.
3. The slot keeps the winner, that dimension is taken out of the pool, and the search moves to the next slot.

The ends come first because they matter most. The last slot holds the dimension TM1 indexes deepest, and choosing it well is usually the biggest single saving. The slots in between refine the result.

## Which metric ranks a slot

| Slot | Ranked by |
|---|---|
| Back half (after the midpoint) | RAM, always |
| Front half, with `views` | Query time |
| Front half, with `processes` and no views | Process time |
| Front half, RAM only | RAM |

The midpoint is half the cube's full dimension count. Excluding a dimension or locking the last slot does not move it, so a slot is always ranked by the same metric.

## Fast mode

`"fast": true` (in the UI, **Fast mode (last and first slot only)**) runs the same walk but stops after its first two slots: the last free slot and the first free slot. Those two slots hold most of the saving, at a fraction of the reorders.

## How many reorders

A cube with *n* dimensions, none of them held in place, measures *n − 1* orders at the first slot, *n − 2* at the second, and so on.

| Dimensions (none locked, excluded or pinned) | Fast | Thorough |
|---|---|---|
| 6 | 9 | 14 |
| 8 | 13 | 27 |
| 12 | 21 | 65 |

The run logs the slots it will visit and the number of orders it will measure before it starts, and each progress line reads `Iteration k of N`. A locked, excluded or pinned dimension takes its slot and itself out of the search, so the count drops. An order listed in `orders_to_ignore` is skipped, so a run can finish below N. On a cube where one reorder takes twenty minutes, a 12-dimension thorough run is a day's work. Run Fast first if time is short.

## Why every dimension is measured

Leaf count measures a dimension's size, not its density. The dimension that belongs last is the densest one, the one with data in almost every cell, and it can have very few leaves. Months is the classic case: twelve to a few dozen leaves, filled for every product and plant.

An earlier 2.0 build tried to save reorders by testing only the dimensions with the largest leaf counts in the last slot. On a production planning cube it never tried the months dimension there. That build found 2% to 31% savings on the cube's instances. Putting months last, the order a full search finds, saved 74% to 78% on every one. The search now measures every candidate, as 1.x did. The decision is recorded in the repository's ADR 0005.

Leaf counts are still used where nothing is measured: scan's suggested order, and [Optimize DB](../modes/optimize-db.md), which applies a leaf-count order to every cube in one pass.

## What the search never overrides

- **The locked slot.** If the dimension in the last storage position has string elements, it never moves and its slot is not searched, see [The Locked Slot](string-element-constraint.md). The walk passes over it: the first slot comes first, then the second-to-last.
- **Excluded dimensions** (`dimensions_to_exclude`) stay where they are, and their slots are not searched.
- **Position rules** ([`dimension_position_rules`](../advanced/dimension-position-rules.md)) seat their dimensions before the search starts. If that changes the order, the seated order is measured first and the search starts from it. Their slots are not searched.
- **Ignored orders** (`orders_to_ignore`) are skipped and never measured.

## The cost model

The RAM baseline is read once, for the original order. Every other order's RAM is derived from the `%` change the server returns for its reorder, so every RAM figure in the report comes from a real reorder.

[Position](../modes/position-optimization.md) and [Dimension](../modes/dimension-optimization.md) optimization search a single slot or a single dimension in full, the same way.
