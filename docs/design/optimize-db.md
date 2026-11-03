# The Optimize DB Pass

Optimize DB applies the cardinality heuristic once to every eligible cube in an instance, one cube at a time, under a wall-clock budget. For a leaf-count cube, which is every cube unless told otherwise, **nothing is benchmarked**: no permutation is tested, no query is timed, and the only evidence of improvement is the percentage `update_storage_dimension_order` returns. A cube switched to the last-slot method is the exception; see [Methods](#methods).

It is a bulk `set` pass, not an optimization. That word is reserved for the measured greedy search, which carries evidence a heuristic pass does not.

For how to drive it, see [Optimize DB Mode](../modes/optimize-db.md).

## Why it exists

Running the measured optimizer cube by cube across a whole model is a multi-day exercise carried out at full memory footprint. Applying the heuristic to the entire instance first, then restarting the server, lowers the footprint enough to make the real exercise cheaper afterwards. Smallest-to-largest is not a guaranteed optimal order, but it lands close on most cubes.

## The heuristic

The target order is **leaf-count ascending**, always. The `order` option controls the order cubes are *processed* in, not the order dimensions are placed in.

String-bearing dimensions go to the back, under `string_policy`:

- `skip_any` (default): any cube with a string-bearing dimension is skipped entirely.
- `pin_last`: one string-bearing dimension is placed last and the numeric dimensions are sorted ascending in front of it. More than one string-bearing dimension is always skipped: TM1 keeps string values in the last dimension, so there is no safe placement and the cube needs separate analysis.

This is the dimension-keyed rule, not the [locked slot](order-frame.md#the-locked-slot). On a cube with a shared string-bearing dimension that is not its measure, this pass and the measured greedy recommend different orders.

## Methods

Every queued cube carries a `method`. `leaf_count` is the heuristic above and the default for every cube. `last_slot` replaces it for the cubes named in `last_slot_cubes` (matched like `exclude_cubes`) or switched on the UI's plan table:

- **Why.** Leaf count measures size; the last slot is decided by density. A small dimension with data in nearly every cell, such as months, belongs last, and the heuristic puts it near the front. On a production planning cube at a customer, putting months last saved 74–78%, while searches that only offered the last slot to the largest dimensions found 2–31%. See ADR-0005.
- **What it does.** It hands the cube to the single-cube optimizer as a Position optimization on the last free slot (the one before a string-locked last dimension), with the winner applied. Every dimension is measured there, one reorder each. The rest of the order is left as it was.
- **What it reuses.** That run is an ordinary `optimize` run: it writes its own report and data file and keeps its own checkpoint, keyed by instance and cube. Optimize DB records what it applied, how many orders it measured, the RAM change from the original to the applied order, and the path of the cube's report.
- **Regression.** The original order is one of the measured candidates, so the winner is never worse; `revert_on_regression` does not apply.
- **Failure and resume.** If the optimizer does not finish, it puts the original order back and the cube is marked `failed`; the checkpoint stays. A resumed sweep retries the cube and the optimizer continues from its checkpoint. A cube left `in_flight` by a dead process is requeued rather than reconciled against an order, since its order was still being decided. A stop request ends its sweep after the reorder in progress, restores the original order and leaves the cube `pending`.
- **The plan.** A cube already in leaf-count order is not skipped as `already_in_target_order` when it is a last-slot cube. The leaf-count target is still recorded for every cube, so a cube can be switched back. The UI saves the methods into the plan file when the run starts; a started plan keeps them.

## Planning

The planner is pure (every TM1 read has already happened before it runs), so a plan is reproducible from its inputs. It produces an ordered queue and a **skip ledger**, and every cube that could be inspected is in one or the other; a cube whose storage order cannot be read is logged as a warning and left out of both. The reasons:

| Reason | Meaning |
|---|---|
| `excluded` | Matched an `exclude_cubes` pattern (case-insensitive, `*`/`?` wildcards) |
| `empty` | No memory in use |
| `below_min_ram` | Under `min_cube_mb` |
| `too_few_dimensions` | Fewer than 3 dimensions |
| `already_optimized` | Storage order differs from the presentation order, and `include_optimized` is off |
| `string_elements` | Has string elements, under `skip_any` |
| `multiple_string_dims` | More than one dimension with strings, under `pin_last` (under `skip_any` such a cube is already ledgered as `string_elements`) |
| `already_in_target_order` | The heuristic would change nothing (not applied to a `last_slot` cube) |

The plan also records the **coverage figure** (the share of total model RAM the queued cubes account for) and the chores that were active when it was built. `--dry-run` produces the plan and stops: it performs no reorder and no chore change, so an operator can review it before committing a weekend to the sweep. The one server-side effect on v11 is the Performance Monitor: if it is off, the read switches it on to collect memory figures and off again afterwards, as every memory read does.

## The budget

`time_limit_hours` is checked **only between cubes**. A running `ReorderDimensions` is a blocking server-side rebuild with no safe abort, so a sweep overshoots by the duration of whatever cube it last started.

This is deliberate: the budget exists to stop the sweep running forever, not to guarantee an end time. Whether the next cube fits is extrapolated from observed throughput: the median bytes/second over the last few completed cubes, rather than the single previous sample, so one cube that hit lock contention does not poison the next decision. No ETA is ever produced.

The estimate times one reorder per cube. A `last_slot` cube runs one reorder per dimension, so its duration is never a throughput sample, and the estimate made before it starts covers only one of its reorders. Once started it runs to the end of its sweep, so it can overshoot the budget by many reorders. That is accepted: its duration cannot be known without running it.

The deadline is absolute and anchored to the original start, so resuming an interrupted run does not extend it.

## Derived savings

Normally the saving is the percentage `update_storage_dimension_order` returns. When a dropped connection loses that response, the reorder has still happened or still not happened (`ReorderDimensions` is atomic, so the cube sits at either the original or the target order), but the percentage is gone and is nowhere on the server.

In that case the run reconnects, establishes which order the cube is in, and computes the saving from an absolute `cube_memory_used` read against the pre-reorder figure it recorded. Such values are tagged `derived` in the run artifact, because they are a measurement rather than the server's own arithmetic. Derived cubes are excluded from the throughput samples that feed the budget estimate, since their duration includes the reconnect.

## Regressions and failures

- **Regression.** With `revert_on_regression` (default on), a leaf-count cube whose reported change is positive is put straight back to its original order and marked `reverted`.
- **Consecutive failures.** `max_consecutive_failures` (default 3) aborts the run. A failed cube is re-checked after reconnecting: if the reorder never landed it is recorded as `failed` and left in its original order; if it did land, it counts as done with a derived saving. Either way the sweep continues.
- **Connection loss.** Three reconnection attempts on a 30/60/120-second ladder. A server still unreachable after that is down, and nothing further is attempted against it.

## Chores

With `disable_active_chores`, the run deactivates the chores that are active **at execution time** (read live rather than taken from the plan's snapshot) and records the list *before* the first deactivation call, so a crash mid-loop still leaves a complete record of what may have been turned off.

Only chores this run deactivated are ever re-activated. A chore an operator disabled in the meantime stays disabled. Restoration is idempotent, and `--restore-chores <plan-id>` is the recovery entry point when a process dies with chores still off.

## Artifacts

Three, one job each:

| Artifact | File | Contents |
|---|---|---|
| **plan** | `optdb_plan_<plan_id>.json` | The queue, each cube's method and leaf-count target order, every skip reason, the coverage figure, the active chores at build time |
| **run** | `optdb_run_<plan_id>.json` | Per-cube status and method, original order (so a regression can be reverted), pre-reorder RAM baseline, the reported `%` and whether it was derived, durations, chore lifecycle state; for a last-slot cube, the applied order, the count of orders measured and its report's path |
| **report** | `optdb_report_<plan_id>.html`, and the console summary | Rendered from the plan and the run, with each cube's method and a link to a last-slot cube's own report |

The run artifact is written after every transition, which is what makes it simultaneously the resume point, the final report, and, when the process dies with chores deactivated, the only record of which chores must be re-activated.

## Guarantees

- No leaf-count cube is benchmarked, and no permutation other than its single target order is applied. A last-slot cube applies only orders that swap one dimension into its last free slot.
- Every cube in the instance that could be inspected is either in the queue or in the skip ledger with a reason; one that could not be is logged and left out.
- `--dry-run` reorders nothing and changes no chore.
- A leaf-count cube that regresses is restored to the order it started in; a last-slot cube never ends worse than its measured original.
- A saving that was measured rather than reported is labeled as such.
- Chores are only re-activated if this run deactivated them.
