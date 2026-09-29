"""The front/back split is a property of the cube, not of the search.

ADR-0002 keys pruning strength to the metric that owns a position: the back half
is RAM-ranked and pruned at full τ, the front half is query-ranked (views) or
left unpruned (processes). `mid` is what decides which half a position is in, so
deriving it from anything narrower than the full storage order makes a
position's *metric* depend on how much of the cube a given run happens to be
searching.

These tests assert on the ranking of **every** position, not only the ones a run
sweeps. Fold A skips a position whose occupant has drifted out of the movable
pool, and that skipping can mask a moved split — a position silently not
searched looks the same as one correctly ranked. The full vector cannot be
masked that way.

Offline, no fake: the measure_orders evaluator stands in for the server, and what is
under test is arithmetic over positions.
"""
import pytest

from optimuspy import tau
from tests.conftest import install_offline_measurements
from tests.test_fold_a import make_main_executor

DIMS = ["D0", "D1", "D2", "D3", "D4", "M"]
CARD = {"D0": 100, "D1": 400, "D2": 2000, "D3": 9000, "D4": 40000, "M": 3}

# Captured before any monkeypatching, so a helper called twice in one test does
# not end up delegating to the previous test double.
_RANKING = tau.ranking_for_position


def _run(monkeypatch, *, fast=False, **frame_kwargs):
    """Run a fold and return the set of `mid` values it ranked positions against."""
    mids = set()

    def recording(target_position, mid, has_views, has_processes):
        mids.add(mid)
        return _RANKING(target_position, mid, has_views, has_processes)

    monkeypatch.setattr(tau, "ranking_for_position", recording)

    ex = make_main_executor(DIMS, CARD, fast=fast, view_names=["V"], **frame_kwargs)
    log = []
    install_offline_measurements(
        ex, lambda o: 100.0 - len(log) * 0.1, log,
        query_of=lambda o: 1.0 + len(log) * 0.01)
    ex.context.set_initial_ram(100.0)
    ex.execute()
    assert mids, "the fold ranked no position — the test would prove nothing"
    return mids


def _split(monkeypatch, **kwargs):
    mids = _run(monkeypatch, **kwargs)
    assert len(mids) == 1, f"one run ranked against more than one split: {mids}"
    return mids.pop()


def _ranking_vector(mid):
    """The metric that owns each position of the cube, under this split."""
    return [_RANKING(p, mid, True, False) for p in range(len(DIMS))]


def test_excluding_a_dimension_does_not_move_the_front_back_split(monkeypatch):
    # The defect this test exists for: `mid` was derived from the movable
    # dimensions, so excluding one shrank it and pushed the boundary forward.
    # Positions the unexcluded cube treats as front — query-ranked, pruned at the
    # wider TAU_QUERY — became back positions pruned at TAU_RAM, the outcome
    # ADR-0002 explicitly rejects.
    baseline = _ranking_vector(_split(monkeypatch))
    excluded = _ranking_vector(_split(monkeypatch, exclude=["D2"]))
    assert excluded == baseline


def test_excluding_more_dimensions_does_not_move_it_further(monkeypatch):
    # Two exclusions shrank the old pool by two, so this is where the old
    # derivation drifted furthest from the cube's real shape.
    baseline = _ranking_vector(_split(monkeypatch))
    excluded = _ranking_vector(_split(monkeypatch, exclude=["D1", "D2"]))
    assert excluded == baseline


def test_locking_the_last_slot_does_not_move_the_front_back_split(monkeypatch):
    # Same defect, reached by the other route that shortens the movable list.
    baseline = _ranking_vector(_split(monkeypatch))
    locked = _ranking_vector(_split(monkeypatch, last_slot_locked=True))
    assert locked == baseline


def test_both_folds_read_the_same_split(monkeypatch):
    # One derivation, two callers. Fold A and Fold B must agree on where the
    # cube's back half starts, or a dim refined by B is judged by a different
    # metric than the one that governed the position A placed it in.
    fold_a = _run(monkeypatch, fast=False, last_slot_locked=True, exclude=["D2"])
    fold_b = _run(monkeypatch, fast=True, last_slot_locked=True, exclude=["D2"])
    assert fold_a == fold_b == {tau.midpoint(len(DIMS))}


# --- the derivation itself -------------------------------------------------

@pytest.mark.parametrize("count, expected", [(0, 0), (1, 0), (2, 1), (5, 2),
                                             (6, 3), (7, 3), (8, 4)])
def test_midpoint_halves_the_dimension_count(count, expected):
    assert tau.midpoint(count) == expected
