"""M1 — CheckpointManager v3: validate-by-set and the `pending` field.

Behavioural tests (offline, local-file checkpoints under tmp_path):
- the schema version is 3;
- validate() accepts a cube whose live storage order was permuted (same dim
  SET) but rejects a genuine schema change (dimension added / removed / renamed)
  and a stale v2 checkpoint;
- a v3 checkpoint round-trips the top-level `pending` order, and a later save
  with pending=None clears it (submitted -> received).
"""
from optimuspy.checkpoint import CheckpointManager, CHECKPOINT_VERSION
from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext, PermutationResult


DIMS = ["A", "B", "C", "M"]


def _result(dims, ram=100.0):
    return PermutationResult(
        ExecutionContext(), ExecutionMode.ORIGINAL_ORDER, "C", [], [],
        list(dims), {}, None, ram_usage=ram, ram_percentage_change=None,
        reorder_duration=0.0)


def _manager(tmp_path):
    return CheckpointManager("C", "inst", "fp-123", result_path=tmp_path)


def _save(mgr, initial_dims, *, pending=None, completed=None):
    mgr.save(
        executor_type="MainExecutor",
        execution_context=ExecutionContext(),
        initial_dimension_order=list(initial_dims),
        last_applied_order=list(initial_dims),
        original_order_result=_result(initial_dims),
        completed_results=completed or [],
        executor_state={"fold_a_state": {}},
        pending=pending)


def test_checkpoint_version_is_three():
    assert CHECKPOINT_VERSION == 3


def test_validate_accepts_reordered_cube_same_set(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS)
    # Cube left physically reordered by a crash — same dims, different order.
    assert mgr.validate(["M", "C", "B", "A"]) is True


def test_validate_rejects_added_dimension(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS)
    assert mgr.validate(DIMS + ["X"]) is False


def test_validate_rejects_removed_dimension(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS)
    assert mgr.validate(["A", "B", "C"]) is False


def test_validate_rejects_renamed_dimension(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS)
    assert mgr.validate(["A", "B", "C", "Measure"]) is False


def test_validate_rejects_v2_checkpoint(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS)
    # Downgrade the stored version on disk to simulate a v2 checkpoint.
    import json
    path = mgr.checkpoint_path
    data = json.loads(path.read_text())
    data["version"] = 2
    path.write_text(json.dumps(data))
    assert mgr.validate(DIMS) is False


def test_pending_round_trips(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS, pending={"dimension_order": ["M", "A", "B", "C"]})
    loaded = mgr.load()
    assert loaded["pending"] == {"dimension_order": ["M", "A", "B", "C"]}


def test_received_save_clears_pending(tmp_path):
    mgr = _manager(tmp_path)
    _save(mgr, DIMS, pending={"dimension_order": ["M", "A", "B", "C"]})
    # promote to received: a subsequent save with no pending must null it out.
    _save(mgr, DIMS, pending=None, completed=[_result(["M", "A", "B", "C"], ram=90.0)])
    loaded = mgr.load()
    assert loaded["pending"] is None
    assert len(loaded["completed_results"]) == 1
