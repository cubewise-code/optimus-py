# How It Works

OptimusPy benchmarks dimension orders by physically reordering the cube on the TM1 server, running queries (and optionally TI processes), measuring RAM and time, and recording the result. This page walks through the full pipeline.

## High-level pipeline

```
1. Capture the original dimension order
2. Disable TM1's stargate cache (set VMM/VMT to 1,000,000)
3. Evaluate the original order as a baseline
4. Run iterations:
     For each candidate order:
       a. Apply the order to the cube
       b. Clear cube cache
       c. Run each view N times — record query times
       d. Run each process N times — record process times
       e. Read RAM from the TM1py Metrics service (`cube_memory_used`), version-agnostic across v11 and v12
       f. Save a checkpoint
5. Pick the best result by composite score
6. Apply best (if update=true) or restore the original
7. Restore VMM/VMT
8. Generate HTML / CSV / XLSX report
```

Steps 2 and 7 are wrapped in a `try/finally` — even if the job fails or is cancelled, VMM/VMT are always restored, and the original dimension order is restored **best-effort** (if the connection has already dropped this is a no-op; the checkpoint retains the original order, so a resume restores it instead).

## The cardinality-aware greedy (two folds)

OptimusPy's greedy is **cardinality-aware**: it uses each dimension's leaf-element
count and a **leaf-count tolerance ratio (τ)** to skip the storage orders that
theory condemns while still measuring the genuinely ambiguous ones. The `fast`
flag selects one of two folds:

- **Thorough (`fast: false`, default)** walks positions outside-in (`N-1, 0,
  N-2, 1, …`) and, at each, tests only the **τ-frontier** of the unplaced
  dimensions — a dimension that dominates all others (e.g. a 50,000-leaf dim) is
  *pinned* to the back in one reorder rather than tested everywhere.
- **Fast (`fast: true`)** seeds from the cardinality-suggested order and then
  coordinate-descent refines only the undecided dimensions across their τ-allowed
  positions (≤ 2 passes).

Pruning is keyed to the ranking metric, so **adding a view unlocks front-half
pruning**. Uniform cubes (nothing decided) degrade gracefully to a full search.

→ Full explanation: [Cardinality-Aware Greedy Optimization](cardinality-aware-greedy.md).

## Composite metrics

When multiple views and/or processes are tested, OptimusPy reports a single number per metric using the **median of medians**:

- For each view: take the median of all N executions
- Composite query time: take the median across per-view medians
- Same logic for processes

Median-of-medians is robust against outliers (TM1 servers occasionally have transient spikes from other workloads).

## Cache & VMM/VMT handling

TM1's **stargate views** cache aggregated query results per cube. If the cache is warm, query times reflect cache hits — not the real cost of the dimension order.

OptimusPy:

1. Sets VMM (memory threshold) and VMT (time threshold) to **1,000,000** before benchmarking. This effectively disables stargate caching for the duration.
2. Calls `DebugUtility(125, 0, 0, '<cube>', '', '')` between iterations to clear any residual cache.
3. Restores the original VMM/VMT in the `finally` block.

[Why VMM/VMT matters → VMM/VMT Handling](vmm-vmt-handling.md)
