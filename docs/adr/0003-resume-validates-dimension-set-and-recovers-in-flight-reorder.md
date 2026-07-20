# Checkpoint resume validates the dimension set and recovers the in-flight reorder

## Context

Checkpoints exist so an interrupted optimization — a crash, a dropped TM1 connection, or `Ctrl+C` — can continue without re-running hours of benchmarking. Resume validated a checkpoint by requiring the cube's **current** storage dimension order to *exactly equal* the `initial_dimension_order` captured when the run started.

That guard is incompatible with how OptimusPy runs. Every order-iterating mode physically reorders the cube on each evaluation (`update_storage_dimension_order` inside `_evaluate_permutation`), and the original order is restored **only on clean completion** — not on a crash or a UI cancel, which restore VMM/VMT but leave the dimension order at the last-applied permutation. So after any real interruption the cube sits reordered, the exact-order check fails, and the run logs *"Checkpoint invalid — starting fresh"* and deletes the checkpoint — the opposite of what resume is for. Two further defects compound it: on the fresh restart `initial_dimension_order` is re-read from the *reordered* cube, so the crashed order becomes the new "original" (the true original is lost); and the RAM `%`-chain anchor (`context.current_ram`, see [ADR-0001](0001-metricservice-replaces-statsbycube.md)) no longer matches the cube's physical state, so re-measured orders would derive wrong RAM.

This machinery is shared by **every** iterating mode — greedy Fold A/Fold B (`MainExecutor`), `PositionOptimizerExecutor`, `DimensionOptimizerExecutor`, `PredefinedOrderExecutor` — all of which go through the same `_evaluate_permutation` and `CheckpointManager`. Any fix must live in that shared layer.

## Decision

Validate a resumable checkpoint by the cube's **dimension set**, treat the checkpoint as the source of truth for the original order, keep the fast `%`-derived RAM model with a single re-anchor on resume, and recover the one in-flight reorder from a recorded `submitted`/`received` status. All in the shared layer, so every mode inherits it.

1. **Validate the dimension *set*, not the exact order.** Resume correctness does not depend on the cube's live order: reorders are absolute (`update_storage_dimension_order` sets a full order), and completed results are keyed by their own order. The only thing that makes a checkpoint's stored orders inapplicable is a **schema** change, so validation compares `set(checkpoint dims) == set(current dims)`; the version, config-fingerprint, cube, and instance checks are unchanged. A cube left reordered by OptimusPy — or reordered manually between runs — no longer discards valid work.

2. **The checkpoint is the source of truth for the original order.** On resume, `initial_dimension_order` comes from the checkpoint, never from a fresh read of the (reordered) cube, so the RAM baseline and the end-of-run restore both target the true original. Best-effort restoration of the original order is also added to the crash and cancel paths (suppressed on failure — a dead connection makes it a no-op) so a *non-resumed* cube is not left reordered.

3. **RAM stays on the `%` chain except for one re-anchor.** The `%`-derived model exists to avoid the ~60 s `}CubeProperties` settle on every iteration (see [ADR-0001](0001-metricservice-replaces-statsbycube.md)); it is preserved. Resume performs exactly **one** absolute read (`read_cube_memory_bytes`, reusing the v11 retry / v12 gauge-lag handling) to re-anchor the chain to the cube's real state; every subsequent reorder uses the fast `%` method.

4. **Recover the single in-flight order via a `submitted`/`received` status.** The checkpoint (schema v3) marks an order `submitted` *before* the reorder is sent and promotes it to `received` — into `completed_results` — only after the full evaluation (RAM, views, processes) succeeds. On resume, if an order is still `pending`, compare it to the cube's current order: if they match, the reorder landed before the drop (the common case) — capture its RAM with the one absolute read, back-calculate the `%` from the previous completed order, and run the outstanding views/processes; if they differ, it never landed, so re-evaluate it through the normal path. The recovered order is marked done so the executor does not repeat it — keeping recovery to a single reorder instead of re-running the whole interrupted position/pass.

## Considered alternatives

- **Keep exact-order validation.** Rejected: it fails after *any* real interruption, because the greedy always leaves the cube reordered — which is exactly the case resume exists to handle.
- **Accept current order == stored original OR last *received* order.** Rejected: it still misses the common "submitted but response lost" case and the mid-views/mid-processes windows, where the cube sits at an order that was never checkpointed.
- **Drop the dimension check entirely** (rely on fingerprint + cube + instance). Rejected: it loses detection of a genuine schema change (a dimension added, removed, or renamed), which would make the stored orders inapplicable.
- **Level 1 only** — set validation + re-anchor, then re-run the whole interrupted position/pass. Kept as the correctness floor, but the `submitted`/`received` status is added on top because a single reorder on a large, wide cube is expensive and re-running a position/pass repeats several of them.
- **Store absolute RAM per reorder** so each record is self-contained. Rejected: it reintroduces the ~60 s settle wait on every iteration — the precise cost the `%` chain exists to avoid.

## Consequences

- Resume becomes reliable after connection drops for every iterating mode: completed work is retained and the interrupted order is recovered, not discarded.
- Checkpoint schema advances to **v3**; existing v2 checkpoints fail the version check and start fresh (no in-place upgrade).
- One extra checkpoint write per iteration (the pre-reorder `submitted` marker) — negligible for local-file checkpoints, one extra REST call for TM1-blob checkpoints.
- A one-time absolute-read cost on resume (the same settle the original baseline pays), then full-speed `%` iterations.
- The full mechanism, schema delta, and test plan are specified in `docs/superpowers/specs/2026-07-20-checkpoint-resume-robustness-design.md`.
