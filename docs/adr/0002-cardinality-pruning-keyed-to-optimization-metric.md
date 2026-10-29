# Cardinality-pruning in the greedy optimizer is keyed to the optimization metric

> **Superseded by [ADR-0005](0005-greedy-measures-every-candidate.md).** Leaf-count pruning was withdrawn: on a real customer cube it kept the dense dimension out of the last slot and left most of the saving unfound. The greedy now measures every candidate at every slot it visits. This record is kept as it was decided.

## Context

The greedy optimizer's cost is dominated by physical reorders (`update_storage_dimension_order`), and reorders that move a high-**cardinality** dimension are the most expensive. To cut that cost, the size-aware greedy uses each dimension's **cardinality** (leaf-element count — a cheap, reorder-free signal) to *prune* which dimensions are test-reordered into each position, and to *pin* confidently-placed dimensions out of the search entirely.

But cardinality only predicts *some* of the things OptimusPy optimizes for. It is a strong prior for **RAM** placement (high-cardinality sparse dimensions compress best toward the back — the basis of `_compute_suggested_order`). It is a weaker prior for **query time** (a query-leading dimension can be any cardinality; `docs/concepts/ram-vs-query-tradeoff.md` notes a small dim early is good for RAM but can be bad for queries that filter on it). It predicts **process duration** not at all — the only KPI is wall-clock, and nothing about a dimension's cardinality forecasts it.

A grounding fact from `executors.py:350-365`: the greedy's **back-half positions are always ranked by RAM**, regardless of config. Only the front half's ranking changes — query time when `views` are set, else process time when `processes` are set, else RAM.

## Decision

Apply cardinality-driven pruning and pinning **only where the ranking metric is something cardinality can predict**:

1. **RAM-ranked positions → prune (and pin).** This always includes the entire back half, plus every position on a RAM-only cube. Strong prior.
2. **Query-ranked front positions (views set) → prune, but with a wider candidate window** than RAM positions. The prior is weaker, so we keep more neighbors in play; the empirical query-time measurement among the survivors still picks the winner, which de-risks the weaker prior.
3. **Process-ranked front positions (processes set, no views) → do not prune.** Cardinality cannot predict process duration, so these positions are searched in full among the non-pinned dimensions. The RAM-ranked back half of the same cube is still pruned and pinned, because the algorithm was already optimizing the back for RAM regardless.

Pinning is fundamentally a RAM/back-placement decision: a pinned dimension is placed at its cardinality-implied slot (back, for the extreme high-cardinality dim) and never test-reordered. It therefore applies whenever the back half is in play — i.e. always — but it never fabricates a placement for a metric cardinality can't predict.

When cardinality gives no signal at all (all dimensions similarly sized — low confidence), pruning switches off and the greedy falls back to exhaustive behavior.

## Considered alternatives

- **Prune everything by cardinality, including process-ranked positions.** Rejected: it would silently bias process-only cubes toward a RAM-optimal layout that has no bearing on process duration, presenting a guessed order as a measured one.
- **Prune RAM-ranked positions only; never prune query positions.** Rejected: it throws away most of the savings whenever `views` are set (the common case), for a risk that empirical measurement among a widened candidate set already covers.
- **Keep process-only cubes fully exhaustive (no pinning either).** Rejected: it forfeits the safe, real savings available on the RAM-ranked back half, where no process prediction is being made. A process-only cube that wants the full speedup can add a view.

## Consequences

- The speedup a cube gets is proportional to how much of its ranking is RAM- or query-driven. RAM-only and query cubes benefit most; process-only cubes benefit only on their back half.
- The optimizer never presents a cardinality-guessed placement as if it were measured for a metric cardinality can't predict.
- Documentation must state plainly that **adding a view unlocks front-half pruning** — it is the user-facing lever for making a slow process-only cube fast.
