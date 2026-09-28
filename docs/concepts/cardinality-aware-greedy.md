# Cardinality-Aware Greedy Optimization

OptimusPy's default optimizer is a **cardinality-aware greedy**. It uses each dimension's leaf-element count to rule out the storage orders that leaf-count theory condemns by a wide margin (so it neither pays their expensive reorders nor wastes iterations on them), while still measuring the orders that are genuinely ambiguous. Measurement stays the arbiter wherever theory is uncertain.

## The problem it solves

Benchmarking a dimension order means physically reordering the cube on the server (`update_storage_dimension_order`) and measuring the result. Two costs hurt on a large, wide cube:

- **Expensive reorders.** A reorder that moves a very high-cardinality dimension (say one with 50,000 leaves) is dramatically more expensive than one that moves a small dimension.
- **Reorder count.** A cardinality-blind greedy tests roughly `N × (N-1)` orders (210 reorders for a 15-dimension cube), and it will happily test a 50,000-leaf dimension in front positions where theory already says it doesn't belong.

A cardinality-aware greedy spends its reorders only where they can change the answer.

## Cardinality: the cheap signal

**Cardinality** is a dimension's number of leaf-level elements. It's cheap to read (no reorder required) and OptimusPy already collects it. It is *not* the same as RAM: a high-cardinality dimension is not necessarily a large memory contributor, because **density/sparsity** matters more, which is exactly why placement is still confirmed by measurement.

The theoretical RAM-optimal storage order runs cardinality **small → large** and density **dense → sparse**, front → back (small-and-dense first, large-and-sparse last). Cardinality is known cheaply; density is not. So cardinality is treated as a *proxy*: trustworthy when two dimensions are far apart, untrustworthy when they are close (density can flip a near-cardinality pair).

## Leaf-count tolerance (τ)

A single **tolerance ratio τ** turns that proxy into a pruning rule over each pair of dimensions X and Y:

- **Decided.** If `leaf(X) / leaf(Y) ≥ τ`, only orders with the larger dimension X *after* the smaller Y are ever tested. The reverse is theory-condemned and skipped (larger ⇒ sparser ⇒ later).
- **Undecided.** If X and Y are within τ of each other, *both* relative orderings are tested. Measurement, our only view of density, picks the winner.

Three properties make this safe:

- **No contradictions.** The "decided-after" relation is a strict partial order (antisymmetric, and transitive for τ > 1), so it can never produce a contradictory cycle.
- **Pinning is emergent.** A 50,000-leaf dimension dominates every other by far more than τ, so at the back-most open position it is the *only* candidate: it is placed once and never test-reordered elsewhere. "Pinning the big dimension to the back" falls straight out of τ; it is not a special case.
- **Graceful degradation.** If every dimension is within τ of its neighbor, nothing is decided and the search degrades to a full exhaustive walk. Uniform cubes are unaffected by construction: there is no cardinality signal to act on, so none is used.

## Pruning is keyed to the ranking metric

Cardinality predicts *some* of what OptimusPy optimizes for, but not all of it. Pruning is therefore applied only where the ranking metric is something cardinality can predict (the reasoning is recorded in the repository's ADR 0002).

A grounding fact: the greedy's **back-half positions are always ranked by RAM**, regardless of config. Only the front half's ranking changes.

| Position ranking | When | τ applied |
|---|---|---|
| **RAM** | all back-half positions; every position on a RAM-only cube | full strength (`τ_ram`), a strong prior |
| **Query time** | front-half positions when `views` are set | looser (`τ_query > τ_ram`), a weaker prior, so more neighbors stay in play and measurement decides |
| **Process time** | front-half positions when only `processes` are set | **not pruned**, because cardinality cannot predict process duration, so the search runs in full |

A process-only cube still prunes and pins its RAM-ranked back half, because that half is optimized for RAM regardless. The practical consequence is that **adding a view unlocks front-half pruning**: it's the user-facing lever for making a slow process-only cube fast.

## The two folds

Both are selected by the `fast` flag, and both reuse the same primitive: sweep a set of candidates, measure, lock the best, continue.

### Thorough: `fast: false` (default)

Walks position indices outside-in (`N-1, 0, N-2, 1, …`, stopping at the middle). At each target position it tests only the **τ-frontier** of the still-unplaced dimensions:

- at a back-most open position, the dimensions within τ of the current maximum cardinality;
- at a front-most open position, those within τ of the current minimum.

It locks the measured winner, recomputes the frontier, and continues. Undecided clusters are measured in full; well-separated dimensions collapse to a single candidate (pinned). The iteration count ranges from about 1 for a pinned dimension up to `≈ N²` only where many dimensions are genuinely near-tied, which is unavoidable, because density is unknown there.

### Fast: `fast: true`

Seed-and-refine, aimed at cutting the reorder *count*:

1. **Seed** from a cardinality-ascending order over the movable dimensions and apply it, in one reorder. The locked slot, excluded dimensions and dimensions pinned by a position rule stay where they are; everything else is sorted by leaf count. A numeric measure is *not* special-cased: it is placed by cardinality like any other dimension (a small measure belongs at the *front* for RAM, because the last slot is best used by the largest dense dimension), and neither is a string-bearing dimension that isn't in the locked slot.
2. **Coordinate-descent refinement.** For each *undecided* dimension (one with a within-τ neighbor), find its best position among only its **τ-allowed positions**, the contiguous span between the dimensions that must sit after it and those that must sit before it. Both the *accept metric* and the *τ used to prune that span* are chosen per dimension by its region (RAM on the back half, query or process on the front), exactly as in the [ranking table](#pruning-is-keyed-to-the-ranking-metric) above, so a query-improving move that would regress RAM at the back is rejected. Decided and pinned dimensions are skipped. Refinement runs largest-cardinality-first, because a larger dimension moves RAM more.
3. **Iterate to stable**, capped at two passes, stopping early if a pass improves nothing.

Because it seeds from a good order and only refines the genuinely undecided dimensions, the fast fold is both quicker and higher quality than a cardinality-blind "test the outer positions only" mode.

## What τ never overrides

- **Manual constraints win.** `dimensions_to_exclude` (keep a dimension fixed) and [`dimension_position_rules`](../advanced/dimension-position-rules.md) are hard constraints layered on top; τ-pruning operates only within the freedom they leave. Excluded dimensions are never moved and nothing is placed on top of them.
- **The locked slot stays put.** If the dimension in the cube's *last storage position* has string elements, that position is locked (TM1's single hard storage-order rule: `CellPutS` and string writes target the last dimension), see [The Locked Slot](string-element-constraint.md). τ never proposes a swap that would move that dimension, and no dimension is ever swept *into* its slot (or an excluded dimension's). A numeric measure carries no such constraint and is free to sit wherever cardinality places it, and so is a string-bearing dimension that is *not* last, which is placed by cardinality like any other.
- **The cost model stays honest.** The RAM baseline is read once (the original order); every other order's RAM is *derived* from the `%` change that each reorder returns. Every RAM figure therefore comes from a real reorder. Pinning saves the *alternatives*: a pinned dimension that isn't already in its slot is still placed by a real reorder, and one that's already there costs nothing.

## Tuning

τ is an internal constant, not user-exposed, because the graceful-degradation behavior and the manual constraints already cover the escape cases. The values, validated against the sample cubes, are `τ_ram = 4×`, `τ_query = 10×`, and a two-pass cap for the fast fold. Standalone [Position](../modes/position-optimization.md) and [Dimension](../modes/dimension-optimization.md) optimization remain exhaustive; τ-pruning is used only by the greedy folds.
