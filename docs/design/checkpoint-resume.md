# Checkpoint Format and Recovery

Every iterating mode writes a checkpoint so an interrupted run (a crash, a dropped TM1 connection, a cancel) continues instead of starting over. The machinery is shared: both greedy folds (Thorough and Fast), position optimization, dimension optimization and predefined orders all go through the same evaluation seam and the same checkpoint manager, so all of them inherit it.

For how to drive it, see [Checkpoints & Resume](../advanced/checkpoints-resume.md).

## The v3 schema

A checkpoint records:

| Field | Purpose |
|---|---|
| `version` | `3`. A version mismatch starts fresh; there is no in-place upgrade from v2. |
| `cube_name`, `instance` | Identity checks. |
| `config_fingerprint` | SHA-256 over the JSON config plus the greedy's τ constants and pass cap. A changed config (or a changed τ) invalidates the checkpoint. |
| `executor_type` | Which mode wrote it. |
| `initial_dimension_order` | **The true original order.** The source of truth for the RAM baseline and the end-of-run restore. |
| `last_applied_order` | The order the cube was last put into. |
| `pending` | The single in-flight order (`submitted` but not yet `received`), or nothing. |
| `execution_context` | Accumulated elapsed time (which is what makes the final report reflect total duration across sessions) and the RAM anchor. |
| `original_order_result`, `completed_results` | Measurements already taken. |
| `executor_state` | Per-mode state, kept under its own key so modes cannot collide. |
| `created_at`, `updated_at` | When the checkpoint was first written and last updated. `created_at` survives across resumes. |

Local checkpoints are written atomically (to a temporary file, then renamed), so a crash during the write cannot leave a truncated file. The TM1-blob variant (`--tm1-checkpoint`, for stateless environments) stores the identical payload through the FileService API instead; only the location changes.

## Dimension-set validation

**A checkpoint is validated by the cube's dimension *set*, not by its order.**

This is the requirement that makes resume work at all. Every iterating mode physically reorders the cube on each evaluation, and the original order is restored only on clean completion, so after any real interruption the cube is sitting at the last-applied permutation, not at its original order. Validating by exact order would fail on precisely the runs resume exists to rescue.

Order equality is also not needed for correctness. Reorders are absolute (`update_storage_dimension_order` sets a full order, not a delta) and completed results are keyed by their own order. The only thing that makes the stored orders inapplicable is a **schema** change (a dimension added, removed or renamed), which the set comparison catches.

So a checkpoint is valid when the version, config fingerprint, cube, instance all match **and** `set(stored dimensions) == set(current dimensions)`. A cube left physically reordered by an interruption resumes; a cube left reordered manually between runs also resumes.

## The checkpoint owns the original order

On resume, `initial_dimension_order` comes from the checkpoint, **never** from a fresh read of the cube. A fresh read would take the crash-reordered order as the new "original", which loses the true original permanently and silently: the RAM baseline and the end-of-run restore would both target the wrong order, and it would be visible only in the final figures.

Best-effort restoration of the original order also runs on the crash and cancel paths, suppressed on failure (a dead connection makes it a no-op), so a run that is *not* resumed does not leave the cube reordered either.

## The RAM anchor

RAM stays on the percentage chain, which exists to avoid an expensive absolute read on every iteration. Resume performs exactly **one** absolute read to re-anchor the chain to the cube's real physical state; every subsequent reorder derives its RAM from the percentage as usual.

One read, not none: the chain's anchor no longer matches the cube after an interruption, and re-measuring orders against a stale anchor would produce wrong RAM for every one of them.

## In-flight reorder recovery

The window that v3 exists to close is the one where a reorder was sent and the response was lost. The cube may be at the target order or still at the previous one, and nothing in the result set says which.

An order is marked `submitted` **before** the reorder is sent, and promoted to `received` (moved into the completed results) only after the *full* evaluation succeeds: RAM, views and processes. On resume, if an order is still pending:

- **The cube's current order matches it.** The reorder landed before the drop, which is the common case. Its RAM is captured with the one absolute read, the percentage is back-calculated from the previous completed order, and the outstanding views and processes are run. The order is then marked done.
- **The cube's current order differs.** The reorder never landed, so the order is re-evaluated through the normal path.

Either way exactly one reorder is recovered, rather than re-running the whole interrupted position or pass. On a large, wide cube a single reorder is expensive enough that this matters.

## Guarantees

- An interruption never discards completed measurements, in any iterating mode.
- The original order is recoverable after a crash, and the cube is returned to it.
- A resumed run never re-applies a reorder that already landed.
- A schema change invalidates the checkpoint; a physical reorder does not.
- Elapsed time accumulates across sessions.
- Cost of resume: one absolute RAM read, then full-speed percentage iterations. Cost of the guarantee: one extra checkpoint write per iteration (the pre-reorder `submitted` marker).
