# Optimize DB Mode

Reorder **every cube in an instance** with one simple rule (dimensions ordered by leaf-element count, fewest first), applied once, one cube at a time, within a time limit. A bulk [Set mode](set-mode.md) run, driven by a plan instead of a hand-written order per cube.

!!! warning "This is not the measured optimizer"
    Optimize DB **benchmarks nothing**. No permutation is tested, no view is queried, no process is timed. Each cube gets its dimensions ordered by leaf-element count, fewest first, applied once, and the only evidence of improvement is the percentage `update_storage_dimension_order` reports. For a searched, measured answer on a cube that matters, use [Optimize mode](optimize-mode.md).

For a run step by step, in the UI and on the command line, see the User Guide: [Optimize DB Step by Step](../guide/optimize-db-step-by-step.md).

## When to use

- You are about to start a **model-wide optimization exercise** and want to shrink the footprint first.
- The instance is **dedicated** (a restore of PROD, a sandbox) and can be reordered and restarted without coordinating with users.
- You have an **overnight or weekend window** and want the run to stop by itself.

## The intended workflow

1. **Dry-run** the instructions to get a plan. Read the share of cube memory it reorders and the skip ledger.
2. **Run it overnight** on the dedicated instance. Every cube the run gets to is reordered by leaf-element count, fewest first.
3. **Restart TM1.** The saving is not visible until you do; see [After the run](#after-the-run).
4. **Now run the real exercise.** [Scan mode](scan-mode.md) to pick the cubes that still matter, then [Optimize mode](optimize-mode.md) against a smaller footprint, which makes each benchmark cheaper.

Running the measured optimizer cube by cube across a whole model is a multi-day exercise carried out at full memory footprint. Optimize DB is the quick run that happens first. Smallest-to-largest is not a guaranteed optimal order, but it lands close on most cubes.

## Instructions JSON

Instance-scoped, deliberately **not** the per-cube schema, because `cube`, `views`, `executions` and `output` have no meaning for a whole-instance run.

```json
{
  "instance": "tm1srv01",
  "time_limit_hours": 8.0,
  "order": "asc",
  "exclude_cubes": ["System *", "Cube A"],
  "min_cube_mb": 10.0,
  "string_policy": "skip_any",
  "include_optimized": false,
  "revert_on_regression": true,
  "disable_active_chores": false,
  "max_consecutive_failures": 3
}
```

| Field | Default | Purpose |
|---|---|---|
| `instance` | **required** | Section name in `config/config.ini`. |
| `time_limit_hours` | `8.0` | Time limit, a positive number. Checked **between cubes only**. |
| `order` | `"asc"` | Order the **cubes** are processed in: `asc` smallest-to-largest, `desc` largest-to-smallest. It does not affect the dimension order applied, which is always leaf-element count, fewest first. |
| `exclude_cubes` | `[]` | Cube names to leave alone. Case-insensitive, `*` and `?` wildcards supported. |
| `min_cube_mb` | `10.0` | Cubes below this RAM are skipped. A rebuild on a tiny cube costs more attention than it saves. |
| `string_policy` | `"skip_any"` | `skip_any` skips any cube with string elements; `pin_last` reorders the numeric dimensions and pins the single string dimension last. |
| `include_optimized` | `false` | Also reorder cubes that are already optimized, meaning their storage order differs from their presentation order. Left `false`, they're skipped, because that order was set on purpose (often by [Optimize mode](optimize-mode.md)) and this pass would overwrite it. |
| `revert_on_regression` | `true` | Put a cube back in its original order when the reorder made it use more memory. |
| `disable_active_chores` | `false` | Deactivate the chores that are active **when the run starts**, for the duration of the run. |
| `max_consecutive_failures` | `3` | Abort the run after this many failures in a row. An integer ≥ 1. |

The repository includes [`samples/optimize_db.json`](../examples/optimize_db.json), a realistic overnight configuration. Copy it into your working directory and edit the instance name and exclusions.

## CLI

```bash
# Plan only. Read-only: no reorder, no chore change, no server write.
optimuspy optimize-db instructions.json --dry-run

# Plan, then execute it.
optimuspy optimize-db instructions.json

# Execute a plan that is already on disk.
optimuspy optimize-db --plan results/tm1srv01/optdb_plan_tm1srv01_2026-09-18_22-00-00.json

# Resume an interrupted run, against its original deadline.
optimuspy optimize-db --resume tm1srv01_2026-09-18_22-00-00 --instance tm1srv01

# Recovery: re-activate the chores a crashed run left disabled.
optimuspy optimize-db --restore-chores tm1srv01_2026-09-18_22-00-00 --instance tm1srv01
```

| Option | Description |
|---|---|
| `--dry-run` | Build and print the plan without touching the server. |
| `--plan <path>` | Execute a plan file instead of building one from instructions. |
| `--resume <plan-id>` | Continue an interrupted run. Requires `--instance`. |
| `--restore-chores <plan-id>` | Re-activate the chores a crashed run left disabled. Requires `--instance`. |
| `--instance <name>` | Section name in `config.ini`. Needed for `--resume` and `--restore-chores`, which have no instructions file to read it from. |
| `--config <path>` | Path to the TM1 connection `config.ini` (default `config/config.ini`). |
| `-p`, `--password` | Override the password for the instance. |

The exit code is `0` when the run completed or stopped on the time limit, `1` otherwise.

## Artifacts

Both files land in `results/<instance>/`, keyed by a plan id of `<instance>_<YYYY-MM-DD_HH-MM-SS>`.

| Artifact | Where | What it holds |
|---|---|---|
| **Plan** | `results/<instance>/optdb_plan_<plan_id>.json` | What would run, in what order, with what target order per cube, plus the full skip ledger and a snapshot of the chores that were active when the plan was built. Written by `--dry-run` and by a normal run before anything is touched. |
| **Run** | `results/<instance>/optdb_run_<plan_id>.json` | Live execution state: per-cube status, original order (for revert), pre-reorder RAM, measured `%`, durations, and the chore lifecycle state. Rewritten after every transition, so it doubles as the resume point and the crash-time record of which chores are still disabled. |
| **Console summary** | stdout | The plan table on `--dry-run`, otherwise the run summary when the run ends. |

The plan table lists every cube to reorder with its RAM and target order, then the skip ledger grouped by reason, then the active chores. One thing to bear in mind is that the chore list is the snapshot you review, not the list the run acts on (see [Chores](#chores)). The run summary reports cubes reordered, reverted, skipped, failed and not started, plus the expected saving.

Cube statuses inside the run artifact: `pending`, `in_flight`, `done`, `reverted`, `skipped`, `failed`.

## Skip reasons

The planner is the single authority on what is skipped and why. Every skipped cube is recorded with its RAM, so the plan tells you how much of the model the run will not touch.

| Reason | Meaning |
|---|---|
| `excluded` | Matched an `exclude_cubes` pattern. |
| `empty` | No memory in use. |
| `below_min_ram` | Smaller than `min_cube_mb`. |
| `too_few_dimensions` | Fewer than 3 dimensions, so there is nothing meaningful to reorder. |
| `already_optimized` | The storage order differs from the presentation order, and `include_optimized` is `false`. |
| `string_elements` | Has string elements and `string_policy` is `skip_any`. |
| `multiple_string_dims` | More than one dimension holds strings. TM1 keeps string values in the last dimension, so with two string dimensions there is no safe placement; these need separate analysis. |
| `already_in_target_order` | The storage order already matches the new order (leaf-element count, fewest first). |

!!! warning "`skip_any` can skip a meaningful share of the model"
    The default `string_policy` of `skip_any` excludes every cube that has any string elements, which in a reporting-heavy model can be a large fraction of total RAM. The plan reports exactly how much: check the `string_elements` line of the skip ledger and the share of cube memory the plan reorders before accepting the default. `pin_last` brings the single-string-dimension cubes back into scope. See [The Locked Slot](../concepts/string-element-constraint.md).

## The time limit

The time limit is absolute and anchored to the moment the run started. Before each cube, the run estimates how long that cube will take from **observed throughput** (the median bytes-per-second of the last three completed cubes, scaled to the next cube's RAM) and starts it only if the estimate fits in the time left. A cube whose saving had to be derived after a reconnect is left out of those samples, because its duration includes the reconnect. The first cube of a run always starts, because there is nothing to extrapolate from yet. When the next cube does not fit, the run stops with status `stopped_time_limit`; the cubes it never started stay `pending`.

!!! warning "A run overshoots by the cube it last started"
    The time limit is checked **only between cubes**. TM1 locks the cube while it reorders it (`tm1.ReorderDimensions`), and the reorder has no safe abort, so the run can run past the limit by the duration of whatever cube it last started. That is by design: the time limit exists to stop the run from going on forever, not to guarantee an end time. Size the window with room to spare, especially with `order: "desc"`.

### Choosing `asc` or `desc`

Neither is the right answer by default; the dry-run's share of cube memory is how you choose.

- **`asc` (smallest to largest)** completes more cubes inside the window and keeps peak memory during the rebuilds lower, but it spends the time limit on the cubes that matter least. A time limit that runs out leaves the biggest cubes untouched.
- **`desc` (largest to smallest)** banks the big wins first, so a run cut short still delivers most of the available saving. Each cube is a larger rebuild, so the overshoot at the end is larger and fewer cubes get done.

Run `--dry-run` first: if a handful of cubes carry most of the planned RAM, `desc` gets them done; if the planned memory is spread thinly across many cubes, `asc` gets through more of them.

## Regressions

One simple rule does not suit every cube, and some get worse. When `update_storage_dimension_order` reports a positive percentage (RAM went up) and `revert_on_regression` is `true`, the cube is immediately put back in its original order and recorded as `reverted`. The run summary counts them separately, so you can see how often the rule missed on this model.

With `revert_on_regression: false`, regressions are kept and counted in the totals as-is. If the revert itself fails, the cube stays in the new order, keeps the status `done`, and the failure is recorded on that cube as `revert_error`.

## Failures

A cube whose reorder raises an error is reconnected to and re-checked: `tm1.ReorderDimensions` is atomic, so the cube sits at either the original or the target order. If it landed, the server's own percentage is gone for good, so the saving is derived from an absolute RAM read against the pre-reorder figure and tagged `derived` (a measurement, not the server's arithmetic). If it did not land, the cube is recorded as `failed` and left in its original order.

Failures in a row are counted: `max_consecutive_failures` (default `3`) aborts the run. Any success resets the counter.

## Chores

With `disable_active_chores: true`, the run reads the **live** chore state when it starts, deactivates exactly the chores that are active at that moment (recorded in the run artifact *before* the first deactivation), and re-activates exactly that set when the run ends, even if it fails: on success, time limit, cancellation, or failure.

The plan's `active_chores` list is a snapshot for you to review; it is **not** what the run acts on. A saved plan can be executed days later, and re-activating from a stale snapshot would switch back on a chore an operator had deliberately disabled in the meantime. The authoritative list is `chores.deactivated` in the run artifact: the run only ever re-activates chores it actually turned off, and that is also the list `--restore-chores` uses. (If the live chore state cannot be read at all, the run falls back to the plan's snapshot.)

If the process itself dies, or the instance is gone when the run tries to clean up, the chores stay deactivated and the run artifact is the only route back:

```bash
optimuspy optimize-db --restore-chores <plan-id> --instance tm1srv01
```

The command is idempotent and safe to repeat. The run summary tells you when it is needed: it prints `Chores: STILL DISABLED` with the exact command.

## Resume

Resume exists for the **dropped-connection case**, not as a way to extend a run. It picks up an interrupted run by plan id and **inherits the original time limit**: people come back to work at a fixed hour regardless of what the run did overnight, so resuming at 07:00 an 8-hour run that started at 22:00 has no time left and will stop immediately.

Before continuing, resume re-reads the storage order of every cube the run recorded as finished. Anything the server no longer reflects (an in-memory reorder lost to a hard stop, a manual change since) goes back to `pending` and is redone rather than silently reported as saved.

A cube left as `in_flight` (the cube being reordered when the process died) is reconciled the same way, with one extra step. The `in_flight` marker is written to the run artifact *before* the reorder is sent, so resume knows which cube was being reordered and can work out what happened to it. `tm1.ReorderDimensions` is atomic, so the cube sits at exactly one of two orders:

- **At the target order.** The reorder landed and only the response was lost. The cube is marked `done`, and because the server's percentage went with that response, the saving is derived from an absolute RAM read against the pre-reorder figure the run recorded, and tagged `derived`.
- **Still at the original order.** The reorder never landed. The cube goes back to `pending` and is redone.

A dropped connection mid-run is handled without resume: the run reconnects up to three times with a 30s / 60s / 120s backoff. A server still unreachable after that is treated as down and the run fails.

**From the UI.** The [Optimize DB Page](../ui/optimize-db-page.md) sets the same options under *Run settings*.

- *Build plan* only reads from TM1. It writes the plan file and shows it: the cube memory figures, the cubes to reorder with their new dimension order, the skipped cubes with their reasons, and the active chores.
- *Run plan* asks for confirmation, then runs that plan exactly as shown; nothing is re-planned. It is refused if the run settings were changed after the plan was built.
- While it runs, *Run progress* lists the cubes to reorder, one row per cube with its status (`reordering` for the cube being reordered), RAM change and time taken, and how much of the time limit is left.
- *Stop after current cube* stops the run before the next cube; the cube being reordered always finishes.
- Every run that did not complete is listed under *Previous runs* with a **Resume** button, which does what `--resume <plan-id>` does.
- A run that left chores disabled shows a *Chores still disabled* warning with a **Re-enable chores** button, which does what `--restore-chores <plan-id>` does.

## After the run

!!! warning "The saving is visible only after a TM1 restart"
    `Expected saving` in the run summary is the sum of the per-cube RAM reductions the server reported. It is memory the model will stop occupying **after a restart**, because instance RSS does not drop when a cube is reordered, because the freed memory stays with the process. Restart TM1 before measuring the result or deciding whether the run was worth it.

Then go back to the [Scan](scan-mode.md) → [Optimize](optimize-mode.md) loop on whatever still deserves a measured search.
