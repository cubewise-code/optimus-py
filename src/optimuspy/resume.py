"""Recover the single in-flight (pending) order on resume — Level 2.

When a run is interrupted, checkpoint v3 records one order as `pending` (written
`submitted` before the reorder). On resume, `recover` decides how to finish it:

- **Landed** (the cube's current storage order already equals the pending order):
  the reorder reached TM1 before the drop. Take one absolute RAM read, back-
  calculate the % relative to the last completed order's absolute RAM, and run
  only the outstanding views/processes (the reorder is not repeated).
- **Not landed** (current != pending): the reorder never applied, so re-evaluate
  the pending order through the normal path (reorder + absolute re-anchor +
  measure).

The decision is pure; every TM1 side effect is injected via `effects`, which
makes both branches unit-testable without a live server.
"""


class RecoveryEffects:
    """Injected I/O for :func:`recover` — one callable per side effect.

    read_absolute_ram() -> float
        One absolute RAM read (re-anchors the %-chain).
    apply_and_measure(order) -> PermutationResult
        Normal-path evaluation of `order` (reorder + absolute re-anchor + measure).
    measure_views_processes(order, abs_ram, pct) -> PermutationResult
        Run only the outstanding views/processes for an already-applied order,
        recording it with the given absolute RAM and back-calculated %.
    """

    def __init__(self, read_absolute_ram, apply_and_measure, measure_views_processes):
        self.read_absolute_ram = read_absolute_ram
        self.apply_and_measure = apply_and_measure
        self.measure_views_processes = measure_views_processes


def recover(pending_order, current_order, prev_abs_ram, effects):
    """Finish the in-flight `pending_order`; return its PermutationResult.

    See the module docstring for the land-check semantics.
    """
    if list(current_order) == list(pending_order):
        abs_ram = effects.read_absolute_ram()
        pct = (abs_ram / prev_abs_ram - 1.0) * 100.0 if prev_abs_ram else 0.0
        return effects.measure_views_processes(pending_order, abs_ram, pct)
    return effects.apply_and_measure(pending_order)
