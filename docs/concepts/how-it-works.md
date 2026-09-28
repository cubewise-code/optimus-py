# How It Works

OptimusPy benchmarks dimension orders by physically reordering the cube on the TM1 server, running queries (and optionally TI processes), measuring RAM and time, and recording the result. This page walks through the full pipeline.

## High-level pipeline

```
1. Capture the original dimension order
2. v11 only: disable TM1's stargate cache (set VMM/VMT to 1,000,000)
3. Evaluate the original order as a baseline
4. Run iterations:
     For each candidate order:
       a. Apply the order to the cube
       b. Run each view N times, clearing the cube cache before each run — record query times
       c. Run each process N times, clearing the cube cache before each run — record process times
       d. Derive RAM from the % change the server returns for the reorder
       e. Save a checkpoint
5. Pick the best order (see "How the best order is chosen" below)
6. Apply best (if update=true) or restore the original
7. v11 only: restore VMM/VMT
8. Generate HTML / CSV / XLSX report
```

RAM is read from the TM1py Metrics service (`cube_memory_used`) once, for the original order, and again only to re-anchor the figures when a run resumes from a checkpoint. Every other RAM figure is derived from the % change the server reports for each reorder.

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

## How the best order is chosen

When multiple views and/or processes are tested, OptimusPy reports a single number per metric using the **median of medians**:

- For each view: take the median of all N executions
- Composite query time: take the median across per-view medians
- Same logic for processes

Median-of-medians is robust against outliers (TM1 servers occasionally have transient spikes from other workloads).

There is no combined score. For each metric that was measured (RAM always, query time if `views` are set, process time if `processes` are set), OptimusPy takes the range between the best and worst value across all tested orders, then:

1. Sets a tolerance of 1% of that range above the best value.
2. Walks the orders in the order they were tested and picks the first one that is within the tolerance on every measured metric. The original order is tested first, so it wins a tie.
3. If no order qualifies, it retries with 2.5%, then 5%.
4. If still no order qualifies, it restores the original order and the log says to pick one manually from the results.

## Cache & VMM/VMT handling

TM1's **stargate views** cache aggregated query results per cube. If the cache is warm, query times reflect cache hits — not the real cost of the dimension order.

OptimusPy:

1. On v11, sets VMM (memory threshold) and VMT (time threshold) to **1,000,000** before benchmarking. This effectively disables stargate caching for the duration.
2. Calls `DebugUtility(125, 0, 0, '<cube>', '', '')` before every view and process execution to clear any residual cache.
3. On v11, restores the original VMM/VMT in the `finally` block.

On v12 the VMM/VMT caps do not exist, so OptimusPy neither changes nor restores them.

[Why VMM/VMT matters → VMM/VMT Handling](vmm-vmt-handling.md)

## Optimization logging

OptimusPy writes to `logs/optimuspy.log` and to stdout at the same time. Two levels are used:

| Level | What it carries | Default |
|---|---|---|
| `INFO` | The run: each order tested, the RAM figure, the locked slot when one is detected, the final report, and a count of how many orders were skipped and why | on |
| `DEBUG` | One line per **skipped** order, naming the reason the order was refused | off — pass `-v` |

```bash
optimuspy optimize config/sales.json -v
```

A run that skips orders says so at INFO, but only as a count:

```
Skipped 6 candidate orders for cube 'Sales' (2 ignored_order, 4 locked_slot)
```

`-v` turns each of those into a line that names the order and the reason:

```
Skipping order — 'Measures' has string elements and is locked to the last position; this order moves it to position 0
Skipping order — order is listed in orders_to_ignore: ['Time', 'Region', 'Product', 'Measures']
```

The reason codes are stable and greppable: `locked_slot`, `ignored_order`, `position_rule`. Use `-v` when an order you expected to be tested does not appear in the results — the skip line is the only place the reason is recorded.

`-v` also preserves the Python traceback when a run fails with a configuration error. Without it you get the message alone, which is the right output for a TI process calling OptimusPy through `ExecuteCommand` but not enough to diagnose an unexpected failure.
