import pytest

from optimuspy import tau
from optimuspy.checkpoint import CheckpointManager, CHECKPOINT_VERSION
from optimuspy.execution_mode import ExecutionMode
from optimuspy.executors import OptimizationCancelled
from optimuspy.results import ExecutionContext, PermutationResult, OptimusResult
from tests.test_fold_a import make_main_executor


def test_checkpoint_version_is_three():
    assert CHECKPOINT_VERSION == 3


def test_fingerprint_changes_with_tau():
    cfg = {"cube": "C", "fast": False}
    a = CheckpointManager.compute_config_fingerprint(cfg, extra={"tau_ram": 4.0})
    b = CheckpointManager.compute_config_fingerprint(cfg, extra={"tau_ram": 5.0})
    assert a != b


def test_fingerprint_changes_with_fold():
    thorough = CheckpointManager.compute_config_fingerprint({"cube": "C", "fast": False})
    fast = CheckpointManager.compute_config_fingerprint({"cube": "C", "fast": True})
    assert thorough != fast


def test_fingerprint_stable_for_same_inputs():
    cfg = {"cube": "C", "fast": False}
    extra = {"tau_ram": tau.TAU_RAM, "tau_query": tau.TAU_QUERY}
    assert (CheckpointManager.compute_config_fingerprint(cfg, extra)
            == CheckpointManager.compute_config_fingerprint(cfg, extra))


# ---------------------------------------------------------------------------
# Task 12 — checkpoint resume round-trips for Fold A and Fold B
#
# A genuine round-trip: run a fold to completion (reference), then run it again
# but crash mid-fold via OptimizationCancelled, capture the checkpointed
# executor_state + pre-crash results, and resume a FRESH executor from that
# state exactly as core does (set_resume_context feeds _resumed_results, and the
# merged report is OptimusResult over [original] + resumed + new).
#
# Accepted resume-granularity characteristic (documented, out of scope to fix):
# Fold A resumes position-granular, Fold B per-pass granular. A crash mid
# position / mid pass re-evaluates that whole position / pass on resume; those
# re-measured orders get fresh permutation_ids that _deduplicate_results (keyed
# on id) will not collapse, so the merged report can carry duplicate rows. This
# is OUTPUT-SAFE (the recommended best is unchanged). Assertions below therefore
# check the recommended BEST outcome and that COMPLETED work is not re-run — not
# exact evaluated-set equality.
# ---------------------------------------------------------------------------


class RecordingCheckpointManager:
    """Fake checkpoint_manager that records the most recent save() kwargs."""

    def __init__(self):
        self.last = None

    def save(self, **kwargs):
        self.last = kwargs


def _original_result(dims, ram_of):
    """Build an ORIGINAL_ORDER result the way core's OriginalOrderExecutor does.

    Uses a throwaway ExecutionContext so constructing it never perturbs the
    executor under test; only ram_usage / mode matter for the merged report.
    """
    return PermutationResult(
        ExecutionContext(), ExecutionMode.ORIGINAL_ORDER, "C", [], [],
        list(dims), {}, None, ram_usage=ram_of(tuple(dims)),
        ram_percentage_change=None, reorder_duration=0.0)


def _recommended_order(original, *result_lists):
    """Mirror core: OptimusResult over [original] + merged results -> best order."""
    merged = [original]
    for rl in result_lists:
        merged.extend(rl)
    return list(OptimusResult("C", merged).best_result.dimension_order)


def _run_until_crash(ex, ram_of, cutoff, install, log):
    """Drive ex until the (cutoff+1)-th evaluation raises; return its recording cm.

    _save_checkpoint is bypassed so mid-run executor_state is captured without
    the production resume-context guard (core sets that context; here we assert
    on the raw checkpoint payload instead).
    """
    cm = RecordingCheckpointManager()
    ex.checkpoint_manager = cm
    ex._save_checkpoint = lambda **kw: setattr(cm, "last", kw)

    def ram_cut(o):
        if len(log) >= cutoff:
            raise OptimizationCancelled("stop")
        return ram_of(o)

    install(ex, ram_cut, log)
    ex.context.set_initial_ram(ram_of(tuple(ex.dimensions)))
    return cm


def test_fold_a_resume_skips_locked_positions_and_matches_best(scripted):
    # 6 sparse dims + numeric measure. mid = 3, so Fold A visits back-to-front
    # positions 5, 0, 4, 1 (then breaks at mid). RAM strongly rewards E in the
    # back-most slot and M at the front, tie-broken by A early -> the greedy has
    # one unambiguous global-min order, [M, A, C, D, B, E] @ 50.5.
    dims = ["A", "B", "C", "D", "E", "M"]
    card = {"A": 100, "B": 105, "C": 110, "D": 115, "E": 120, "M": 3}
    ram_of = (lambda o: 100.0 - 10 * list(o).index("E")
              + list(o).index("M") + 0.5 * list(o).index("A"))

    # 1) uninterrupted reference
    ref = make_main_executor(dims, card)
    ref_log = []
    scripted(ref, ram_of, ref_log)
    ref.context.set_initial_ram(ram_of(tuple(dims)))
    ref_results = ref._run_fold_a()
    original = _original_result(dims, ram_of)
    ref_best = _recommended_order(original, ref_results)
    assert ref_best == ["M", "A", "C", "D", "B", "E"]  # unambiguous global min

    # 2) crash mid-fold: positions 5 and 0 locked, crash during position-4 sweep
    ex = make_main_executor(dims, card)
    crash_log = []
    cm = _run_until_crash(ex, ram_of, 8, scripted, crash_log)
    with pytest.raises(OptimizationCancelled):
        ex._run_fold_a()
    executor_state = cm.last["executor_state"]
    precrash = cm.last["new_results"]
    locked = list(executor_state["fold_a_state"]["placed_positions"])
    assert locked == [5, 0]  # documents the resume point: two positions locked

    # 3) resume a fresh executor from the captured state, mirroring core
    ex2 = make_main_executor(dims, card)
    resume_log = []
    scripted(ex2, ram_of, resume_log)
    ex2.context.set_initial_ram(ram_of(tuple(dims)))
    ex2.set_resume_context(list(dims), original, list(precrash))

    swept_positions = []
    real_sweep = ex2._sweep_into_position

    def spy_sweep(current_order, target_position, *args, **kwargs):
        swept_positions.append(target_position)
        return real_sweep(current_order, target_position, *args, **kwargs)

    ex2._sweep_into_position = spy_sweep
    resumed_results = ex2._run_fold_a({"executor_state": executor_state})

    # (a) completed work not re-run: no locked position is swept again on resume;
    #     only the still-open positions (4, then 1) are.
    assert all(p not in locked for p in swept_positions)
    assert swept_positions == [4, 1]
    assert len(resume_log) < len(ref_log)  # strictly less work than a full run
    # (b) recommended best order is identical to the uninterrupted run
    resumed_best = _recommended_order(original, precrash, resumed_results)
    assert resumed_best == ref_best


def test_fold_b_resume_is_faithful_and_does_not_regress(scripted):
    # Fold B coordinate descent. RAM is order-dependent and uniquely minimised by
    # [C, A, B, M] (every other order matches fewer target positions -> higher
    # RAM), so the descent converges there and it is the unambiguous best.
    # "M" is a STRING dim, the sole reason a dim is locked last (CellPutS targets
    # the last dimension); that keeps the seed [A, B, C, M] and holds M last
    # throughout, without relying on the removed numeric-measure-last rule.
    dims = ["A", "B", "C", "M"]
    card = {"A": 100, "B": 110, "C": 120, "M": 3}
    strings = ["M"]
    seed = ["A", "B", "C", "M"]
    target = ["C", "A", "B", "M"]
    ram_of = lambda o: 100.0 - sum(1 for i, d in enumerate(target) if list(o)[i] == d)

    # 1) uninterrupted reference
    ref = make_main_executor(dims, card, fast=True, string_dims=strings)
    ref_log = []
    scripted(ref, ram_of, ref_log)
    ref.context.set_initial_ram(ram_of(tuple(dims)))
    ref_results = ref._run_fold_b()
    original = _original_result(dims, ram_of)
    ref_best = _recommended_order(original, ref_results)
    assert ref_best == target        # descent reached the unique optimum
    assert ref_log[0] == seed        # reference DID apply the seed first

    # 2) crash during the FINAL pass (pass 0 fully completed). The checkpointed
    #    current_order is the optimum itself -> a faithful resume must accept no
    #    move from it.
    ex = make_main_executor(dims, card, fast=True, string_dims=strings)
    crash_log = []
    # Crash on the 7th eval: the checkpoint captured (from eval 6) is the first
    # pass-1 sweep, whose anchor is already the optimum -> pass_index==1, anchor==
    # target. (Reserving the string dim's last slot narrows each numeric dim's
    # candidate positions, so the whole descent is 9 evals; 7 lands in pass 1.)
    cm = _run_until_crash(ex, ram_of, 7, scripted, crash_log)
    with pytest.raises(OptimizationCancelled):
        ex._run_fold_b()
    executor_state = cm.last["executor_state"]
    precrash = cm.last["new_results"]
    fold_b_state = executor_state["fold_b_state"]
    anchor = list(fold_b_state["current_order"])
    assert fold_b_state["pass_index"] == 1  # pass 0 already done
    assert anchor == target                 # resuming at the optimum

    # 3) resume a fresh executor mirroring core. set_resume_context feeds
    #    _resumed_results, which _current_metric must consult so the restored
    #    current_order's metric is found (not float('inf')).
    ex2 = make_main_executor(dims, card, fast=True, string_dims=strings)
    resume_log = []
    scripted(ex2, ram_of, resume_log)
    ex2.context.set_initial_ram(ram_of(tuple(dims)))
    ex2.set_resume_context(list(dims), original, list(precrash))
    resumed_results = ex2._run_fold_b({"executor_state": executor_state})

    # (a) seed NOT re-applied: the first resumed evaluation is a pass-sweep
    #     candidate, never the freshly-computed seed.
    assert resume_log[0] != seed
    # (a) completed passes NOT re-run and NO regression accepted (issue #1): with
    #     the anchor at the optimum, a faithful resume never moves resulting_order,
    #     so every resumed evaluation is a single transposition of the anchor
    #     (differs in <= 2 positions). Without _current_metric consulting
    #     _resumed_results, the first refine sweep sees inf and accepts a
    #     regression, after which later sweeps evaluate orders > 2 positions from
    #     the anchor -> this assertion fails (RED under mutation).
    def positions_differing(o):
        return sum(1 for i in range(len(anchor)) if o[i] != anchor[i])

    assert all(positions_differing(o) <= 2 for o in resume_log)
    assert len(resume_log) < len(ref_log)  # last pass only, not the whole descent
    # (b) recommended best order identical to the uninterrupted run
    resumed_best = _recommended_order(original, precrash, resumed_results)
    assert resumed_best == ref_best
