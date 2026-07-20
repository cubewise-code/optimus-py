"""M3 — one absolute RAM re-anchor on the first resumed measurement.

The %-chain anchor (context.current_ram) goes stale across a resume because the
cube's physical state no longer matches it. The first evaluation after
set_resume_context must take ONE absolute read to re-anchor current_ram (without
disturbing original_ram, the baseline for ram_reduction); every later evaluation
uses the fast % method.
"""
import types

from optimuspy.execution_mode import ExecutionMode
from optimuspy.executors import OptipyzerExecutor
from optimuspy.results import ExecutionContext, PermutationResult


class _FakeCubes:
    def __init__(self, pct):
        self._pct = pct
        self.applied = []

    def update_storage_dimension_order(self, cube_name, order):
        self.applied.append(list(order))
        return self._pct


class _FakeTM1:
    def __init__(self, pct=0.0):
        self.cubes = _FakeCubes(pct)


def _make_executor(pct=0.0):
    ex = object.__new__(OptipyzerExecutor)
    ex.tm1 = _FakeTM1(pct)
    ex.cube_name = "C"
    ex.view_names = []
    ex.process_names = []
    ex.include_process = False
    ex.executions = 1
    ex.is_v12 = False
    ex.mode = ExecutionMode.ITERATIONS
    ex.context = ExecutionContext()
    ex.checkpoint_manager = None
    ex.cancel_event = None
    ex._initial_dimension_order = None
    ex._original_order_result = None
    ex._resumed_results = []
    ex._reanchor_needed = False
    return ex


def _install_ram_spy(ex, abs_value):
    calls = {"n": 0}

    def _spy(self):
        calls["n"] += 1
        return abs_value

    ex._retrieve_ram_usage = types.MethodType(_spy, ex)
    return calls


def test_first_resumed_measurement_is_absolute_rest_are_percent():
    ex = _make_executor(pct=0.0)
    # baseline established in the prior run: original 1000, but current_ram is now
    # STALE (800) relative to the cube's real state.
    ex.context.set_initial_ram(1000.0)
    ex.context.current_ram = 800.0

    calls = _install_ram_spy(ex, abs_value=900.0)
    ex.set_resume_context(["A", "B"], None, [])

    first = ex._evaluate_permutation(["B", "A"])
    second = ex._evaluate_permutation(["A", "B"])

    # exactly one absolute read — the re-anchor — across both evaluations
    assert calls["n"] == 1
    # re-anchored to the fresh absolute value, not the stale 800
    assert first.ram_usage == 900.0
    # second is derived by the % chain from the re-anchored current_ram
    assert second.ram_usage == 900.0  # pct == 0
    # the baseline (original_ram) is preserved, so ram_reduction stays honest
    assert ex.context.original_ram == 1000.0
    assert abs(first.ram_reduction - 0.1) < 1e-9


def test_no_reanchor_without_resume_context():
    ex = _make_executor(pct=0.0)
    ex.context.set_initial_ram(1000.0)
    calls = _install_ram_spy(ex, abs_value=900.0)
    # no set_resume_context — a fresh run must never take an absolute read here
    ex._evaluate_permutation(["B", "A"])
    assert calls["n"] == 0


def test_fresh_run_does_not_reanchor():
    # core calls set_resume_context on every run; a fresh run (resuming=False)
    # must NOT arm the absolute read — the % chain would otherwise pay a settle
    # on the first iteration of every fresh run.
    ex = _make_executor(pct=0.0)
    ex.context.set_initial_ram(1000.0)
    calls = _install_ram_spy(ex, abs_value=900.0)
    ex.set_resume_context(["A", "B"], None, [], resuming=False)
    ex._evaluate_permutation(["B", "A"])
    assert calls["n"] == 0


def test_reanchor_ram_only_moves_current():
    ctx = ExecutionContext()
    ctx.set_initial_ram(1000.0)
    ctx.reanchor_ram(500.0)
    assert ctx.current_ram == 500.0
    assert ctx.original_ram == 1000.0
