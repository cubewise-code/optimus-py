# Checkpoints & Resume

OptimusPy persists progress mid-run so a crash, network blip, or `Ctrl+C` doesn't lose hours of benchmarking work.

## When checkpoints are written

A checkpoint is written **before every reorder** (marking that order `submitted`)
and again **after the evaluation fully succeeds** (RAM + views + processes),
which promotes it to `received` and clears the in-flight marker. So the recorded
`completed_results` only ever hold fully-measured orders, and the one order that
was in flight when the connection dropped is preserved separately. The
checkpoint contains:

- The **original** dimension order — the source of truth for the RAM baseline and
  the end-of-run restore (taken from the checkpoint on resume, never re-read from
  a cube that may have been left reordered)
- The original RAM baseline
- The list of completed `PermutationResult` objects (deserialized from disk on resume)
- The single in-flight `pending` order (the one `submitted` but not yet `received`)
- The greedy/executor state (current iteration, target position, tested dimensions in this round)
- A fingerprint of the input config (so a changed config invalidates the checkpoint)

Checkpoints live in `results/` named `checkpoint_{cube}.json` and are schema **v3**.
A pre-v3 checkpoint fails the version check and the run starts fresh (no in-place upgrade).

## Resuming from a checkpoint

Just **re-run the same command**:

```bash
optimuspy optimize my_cube.json
```

OptimusPy detects the checkpoint, validates that:

1. The cube's **dimension set** still matches the checkpoint (same dimensions,
   regardless of order) — every iterating mode leaves the cube physically
   reordered after an interruption, so the live *order* is deliberately **not**
   required to match. Only a genuine schema change (a dimension added, removed,
   or renamed) invalidates the checkpoint.
2. The config fingerprint matches the saved one
3. The checkpoint version, cube, and instance match

If all match, it logs:

```
Resuming from checkpoint — restoring previous progress
Restored 23 completed permutations from checkpoint
```

…and continues from where it left off. Already-completed permutations are not re-evaluated.

### Recovering the in-flight order

If an order was `submitted` but never `received` (the connection dropped between
the reorder and the measurement), OptimusPy recovers it with a **land-check**:

- If the cube's current storage order already equals the pending order, the
  reorder had landed before the drop — OptimusPy takes one absolute RAM read to
  re-anchor the `%` chain, back-calculates the change from the last completed
  order, and runs only the outstanding views/processes (the reorder is **not**
  repeated).
- Otherwise the reorder never landed, so the pending order is re-evaluated
  through the normal path.

Either way the recovered order is marked done, so the executor never re-applies it.

If validation fails (a dimension was added/removed/renamed, or the config was edited), OptimusPy logs a warning and starts fresh.

## Disabling resume

To force a clean start and ignore any existing checkpoint:

```bash
optimuspy optimize my_cube.json --no-resume
```

The existing checkpoint is deleted before the run starts.

## When checkpoints are removed

- On **successful completion** of the optimization run
- On `--no-resume` re-run
- Manually: `rm results/checkpoint_<cube>.json`

## Cancelled and crashed jobs

When you cancel from the [Jobs page](../ui/jobs-page.md) (or the run crashes),
OptimusPy:

1. Stops the current iteration cleanly
2. Restores VMM/VMT
3. **Best-effort** restores the original dimension order — if the connection is
   already gone (the common cause of an interruption) this is a silent no-op; the
   checkpoint still holds the original order, so a resume restores it instead
4. Leaves the last checkpoint in place

Re-launching the same config resumes from the last completed iteration and
recovers the single in-flight order (see above).

## Concurrent runs

There is **no lock file**. If you launch two OptimusPy processes against the same cube, both will read the same checkpoint, race on `update_storage_dimension_order`, and produce undefined results. Don't do this.

The web UI's [JobManager](../ui/jobs-page.md) prevents concurrent jobs **within the same UI process**. Cross-process safety is your responsibility.
