# The greedy measures every candidate at every slot it visits

Supersedes [ADR-0002](0002-cardinality-pruning-keyed-to-optimization-metric.md).

## Context

ADR-0002 let the greedy skip candidates on **cardinality** (leaf count). At a back slot it tested only the dimensions within τ = 4× of the largest unplaced leaf count; at a front slot, only those within τ of the smallest. Fast mode went further. It seeded a leaf-count-ascending order and refined only the dimensions that had a neighbor within τ. The premise was that a dimension with many more leaves than another belongs after it.

That premise is about size. What decides the last slot is **density**: the last storage dimension is the one TM1 indexes deepest, and the best one to put there is the dimension with data in nearly every cell. A dense dimension can be small. Months is the usual case: a few dozen leaves, filled for every product and plant.

A production planning cube at a customer showed the cost. The same 12-dimension cube runs on five instances. On every greedy run on every instance, the last slot was offered only the two dimensions with the largest leaf counts (a SKU dimension and a cost-component dimension). The months dimension was never tried there. The four instances where both were measured:

| Instance | Pruned greedy (best found) | Months last (the order 1.x found) |
|---|---|---|
| A | −2% | −78% |
| B | −31% | −77% |
| C | −18% | −74% |
| D | −18% | −75% |

The 1.x greedy has no pruning: it tests every dimension at every slot it visits. Its fast mode tests every dimension in the last slot and in the first slot. On this cube it found the months-last order, and applying that order on each instance confirmed the saving. A 2.0 search that misses by that much is a regression from 1.x, whatever it saves in reorders.

## Decision

**The greedy measures every candidate.** `MainExecutor` runs one outside-in search: the last slot, the first, the second-to-last, the second, and so on, stopping at the midpoint of the full storage order. At each slot it visits, every dimension not yet placed is swapped in and measured. The slot keeps the winner, ranked as before: RAM on the back half; query time on the front half when views are set, else process time when processes are set, else RAM.

**Fast mode is 1.x's fast mode.** It runs the same walk and stops after its first two free slots, which are the last free slot and the first free slot.

**Leaf counts no longer steer the measured search.** τ, the frontiers, pinning, the seed and the refinement passes are removed, along with the Fold A / Fold B split. Leaf counts remain where nothing is measured: scan's suggested order and Optimize DB's one-shot heuristic.

**Everything ADR-0004 decided still holds.** The order frame still decides admissibility. The locked slot, excluded dimensions and pinned dimensions still reserve their slots, which the walk passes over. Position rules are still pre-applied, and the pre-applied order is measured first when it differs from the original. The front/back split still comes from the full storage order (`search.midpoint`).

## Considered alternatives

- **Keep pruning, but widen τ.** Rejected. No single ratio separates size from density. A wider τ only moves the threshold a small dense dimension has to cross, and months-sized dimensions sit far below any useful one.
- **Exempt only the last slot from pruning.** Rejected. It fixes this cube, but the same argument applies at the first slot and wherever density, not size, decides. The 1.x rule is simple, its cost is predictable, and it is what customers already trusted.
- **Estimate density and prune on that.** Rejected for now. A density estimate costs server reads per dimension and is itself a heuristic. Measurement is the arbiter the tool exists to provide.

## Consequences

- Runs take more reorders, and the count is known before the run starts. A cube with *n* free dimensions measures *(n−1) + (n−2) + …* over the slots it visits: 65 orders for 12 dimensions, 21 in Fast mode. The run logs the planned slots and the count, and progress reads `Iteration k of N`.
- No placement in the greedy is a guess. Every winning dimension won a measurement against every alternative still available.
- Checkpoints written by the pruning builds do not resume. Their fingerprint covered the τ constants, and their executor state was `fold_a_state` / `fold_b_state`; the search now keeps `greedy_state`.
- The remaining greedy cost lever is Fast mode. Position and Dimension optimization are unchanged.
