"""M2 — ResumeRecovery: land-check + back-calc, with injected I/O effects.

recover() is pure decision logic:
- LANDED (cube's current order == the pending order): the reorder reached TM1
  before the drop. Take ONE absolute RAM read, back-calculate the % relative to
  the last completed order's absolute RAM, then run only the outstanding
  views/processes.
- NOT LANDED (current != pending): the reorder never applied. Re-evaluate the
  pending order through the normal path (reorder + measure).

All TM1 I/O is injected via `effects`, so both branches are testable offline.
"""
from optimuspy.resume import recover, RecoveryEffects


class _RecordingEffects:
    def __init__(self, abs_ram=None, landed_result="LANDED", applied_result="APPLIED"):
        self._abs_ram = abs_ram
        self._landed_result = landed_result
        self._applied_result = applied_result
        self.calls = []

    def read_absolute_ram(self):
        self.calls.append(("read_absolute_ram",))
        return self._abs_ram

    def apply_and_measure(self, order):
        self.calls.append(("apply_and_measure", list(order)))
        return self._applied_result

    def measure_views_processes(self, order, abs_ram, pct):
        self.calls.append(("measure_views_processes", list(order), abs_ram, pct))
        return self._landed_result


def test_landed_branch_reads_absolute_backcalcs_pct_and_measures():
    eff = _RecordingEffects(abs_ram=900.0)
    result = recover(
        pending_order=["B", "A"], current_order=["B", "A"],
        prev_abs_ram=1000.0, effects=eff)

    assert result == "LANDED"
    kinds = [c[0] for c in eff.calls]
    assert kinds == ["read_absolute_ram", "measure_views_processes"]
    # never re-applies the reorder on the landed path
    assert "apply_and_measure" not in kinds
    # back-calc: (900/1000 - 1) * 100 == -10.0
    _, order, abs_ram, pct = eff.calls[-1]
    assert order == ["B", "A"]
    assert abs_ram == 900.0
    assert abs(pct - (-10.0)) < 1e-9


def test_not_landed_branch_reevaluates_via_normal_path():
    eff = _RecordingEffects(abs_ram=900.0)
    result = recover(
        pending_order=["B", "A"], current_order=["A", "B"],
        prev_abs_ram=1000.0, effects=eff)

    assert result == "APPLIED"
    kinds = [c[0] for c in eff.calls]
    assert kinds == ["apply_and_measure"]
    # no absolute read / back-calc when it never landed — the normal path re-anchors
    assert "read_absolute_ram" not in kinds


def test_recovery_effects_holds_injected_callables():
    eff = RecoveryEffects(
        read_absolute_ram=lambda: 42.0,
        apply_and_measure=lambda o: ("applied", o),
        measure_views_processes=lambda o, a, p: ("measured", o, a, p))
    assert eff.read_absolute_ram() == 42.0
    assert eff.apply_and_measure(["X"]) == ("applied", ["X"])
    assert eff.measure_views_processes(["X"], 1.0, 2.0) == ("measured", ["X"], 1.0, 2.0)
