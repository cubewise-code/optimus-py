"""Planner and budget rules for Optimize DB — the decisions made without TM1."""
import pytest

from optimuspy.optimize_db import (
    DEFAULT_OPTIONS,
    build_plan,
    collect_cube_records,
    estimate_seconds,
    fits_in_budget,
    resolve_options,
    resolve_target_order,
    validate_db_config,
)

MB = 1024 ** 2
GB = 1024 ** 3


def options(**overrides):
    return resolve_options({"instance": "srv", **overrides})


def cube(name, ram_gb, dims, strings=(), leaves=None, visible=None):
    """A collected cube record: storage order plus per-dimension shape."""
    leaves = leaves or {}
    return {
        "cube": name,
        "ram_bytes": ram_gb * GB,
        "storage_order": list(dims),
        "visible_order": list(visible) if visible is not None else list(dims),
        "dimensions": {d: {"name": d,
                           "leaf_elements": leaves.get(d, 100),
                           "has_strings": d in strings}
                       for d in dims},
    }


# --- target order ----------------------------------------------------------

def test_target_order_is_leaf_count_ascending():
    record = cube("Sales", 5, ["Time", "Product", "Measure"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12})
    target, reason = resolve_target_order(record, options())
    assert reason is None
    assert target == ["Measure", "Product", "Time"]


def test_cube_order_option_does_not_change_dimension_order():
    """`order` sequences cubes, never dimensions — the heuristic is always ascending."""
    record = cube("Sales", 5, ["Time", "Product", "Measure"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12})
    asc, _ = resolve_target_order(record, options(order="asc"))
    desc, _ = resolve_target_order(record, options(order="desc"))
    assert asc == desc == ["Measure", "Product", "Time"]


def test_cube_already_in_target_order_is_skipped():
    record = cube("Sales", 5, ["Measure", "Product", "Time"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12})
    target, reason = resolve_target_order(record, options())
    assert target is None
    assert reason == "already_in_target_order"


def test_equal_cardinality_breaks_ties_by_name_for_determinism():
    record = cube("Sales", 5, ["Zulu", "Alpha", "Mike"],
                  leaves={"Zulu": 50, "Alpha": 50, "Mike": 50})
    target, _ = resolve_target_order(record, options())
    assert target == ["Alpha", "Mike", "Zulu"]


# --- string policy ---------------------------------------------------------

def test_skip_any_skips_a_cube_with_string_elements():
    record = cube("Comments", 5, ["Time", "Product", "Measure"], strings=["Measure"])
    target, reason = resolve_target_order(record, options(string_policy="skip_any"))
    assert target is None
    assert reason == "string_elements"


def test_pin_last_keeps_the_single_string_dimension_last():
    record = cube("Comments", 5, ["Measure", "Time", "Product"], strings=["Measure"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12})
    target, reason = resolve_target_order(record, options(string_policy="pin_last"))
    assert reason is None
    assert target == ["Product", "Time", "Measure"]


def test_two_string_dimensions_are_skipped_even_under_pin_last():
    record = cube("Comments", 5, ["Time", "Notes", "Measure"], strings=["Notes", "Measure"])
    target, reason = resolve_target_order(record, options(string_policy="pin_last"))
    assert target is None
    assert reason == "multiple_string_dims"


# --- cheap skips -----------------------------------------------------------

@pytest.mark.parametrize("record, expected", [
    (cube("Tiny", 0.001, ["A", "B", "C"]), "below_min_ram"),
    (cube("Hollow", 0, ["A", "B", "C"]), "empty"),
    (cube("Flat", 5, ["A", "B"]), "too_few_dimensions"),
])
def test_cubes_not_worth_a_rebuild_are_skipped(record, expected):
    assert resolve_target_order(record, options())[1] == expected


def test_already_optimized_cubes_are_skipped_by_default():
    """A storage order that differs from the presentation order was set on purpose."""
    record = cube("Sales", 5, ["Product", "Measure", "Time"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12},
                  visible=["Time", "Product", "Measure"])
    assert resolve_target_order(record, options()) == (None, "already_optimized")


def test_include_optimized_reorders_them_like_any_other_cube():
    record = cube("Sales", 5, ["Product", "Measure", "Time"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12},
                  visible=["Time", "Product", "Measure"])
    target, reason = resolve_target_order(record, options(include_optimized=True))
    assert reason is None
    assert target == ["Measure", "Product", "Time"]


class _Cubes:
    def __init__(self, storage, visible):
        self.storage, self.visible, self.name_reads = storage, visible, 0

    def get_storage_dimension_order(self, cube_name):
        return list(self.storage)

    def get_dimension_names(self, cube_name):
        self.name_reads += 1
        return list(self.visible)


class _TM1:
    def __init__(self, cubes):
        self.cubes = cubes


def test_collector_reads_the_presentation_order_only_when_it_decides_a_skip(monkeypatch):
    from optimuspy import optimize_db as odb
    monkeypatch.setattr(odb, "_dimension_metadata",
                        lambda tm1, d: {"name": d, "leaf_elements": 10, "has_strings": False})
    tm1 = _TM1(_Cubes(["B", "C", "A"], ["A", "B", "C"]))

    [record] = collect_cube_records(tm1, {"Sales": 50 * MB}, options())
    assert record["visible_order"] == ["A", "B", "C"]
    assert resolve_target_order(record, options())[1] == "already_optimized"

    [record] = collect_cube_records(tm1, {"Sales": 50 * MB}, options(include_optimized=True))
    assert record["visible_order"] is None
    assert tm1.cubes.name_reads == 1


def test_excluded_cubes_are_never_touched():
    record = cube("Land Milestone", 50, ["Time", "Product", "Measure"],
                  leaves={"Time": 900, "Product": 40, "Measure": 12})
    assert resolve_target_order(record, options(exclude_cubes=["land milestone"]))[1] == "excluded"
    assert resolve_target_order(record, options(exclude_cubes=["Land *"]))[1] == "excluded"
    assert resolve_target_order(record, options(exclude_cubes=["Other"]))[1] is None


# --- plan assembly ---------------------------------------------------------

def records():
    leaves = {"Time": 900, "Product": 40, "Measure": 12}
    return [
        cube("Big", 100, ["Time", "Product", "Measure"], leaves=leaves),
        cube("Small", 1, ["Time", "Product", "Measure"], leaves=leaves),
        cube("Medium", 10, ["Time", "Product", "Measure"], leaves=leaves),
        cube("Stringy", 20, ["Time", "Product", "Measure"], strings=["Measure"], leaves=leaves),
    ]


def test_plan_sequences_cubes_smallest_to_largest():
    plan = build_plan("srv", "p1", options(order="asc"), records(), 131 * GB, [])
    assert [c["cube"] for c in plan["cubes"]] == ["Small", "Medium", "Big"]


def test_plan_sequences_cubes_largest_to_smallest():
    plan = build_plan("srv", "p1", options(order="desc"), records(), 131 * GB, [])
    assert [c["cube"] for c in plan["cubes"]] == ["Big", "Medium", "Small"]


def test_plan_reports_coverage_and_skips_so_the_operator_can_judge_the_budget():
    plan = build_plan("srv", "p1", options(), records(), 131 * GB, ["Nightly Load"])
    assert plan["planned_ram_bytes"] == 111 * GB
    assert plan["coverage_pct"] == pytest.approx(111 / 131 * 100)
    assert [(s["cube"], s["reason"]) for s in plan["skipped"]] == [("Stringy", "string_elements")]
    assert plan["active_chores"] == ["Nightly Load"]


def test_plan_carries_the_current_order_needed_to_revert():
    plan = build_plan("srv", "p1", options(), records(), 131 * GB, [])
    assert plan["cubes"][0]["current_order"] == ["Time", "Product", "Measure"]


# --- budget ----------------------------------------------------------------

def test_first_cube_always_runs_because_there_is_nothing_to_extrapolate_from():
    fits, estimate = fits_in_budget(500 * GB, [], now=0, deadline=1)
    assert fits is True
    assert estimate is None


def test_estimate_scales_the_observed_throughput_to_the_next_cube():
    # 100 GB took 600s; 150 GB should be predicted at 900s.
    assert estimate_seconds(150 * GB, [[100 * GB, 600]]) == pytest.approx(900)


def test_one_slow_cube_does_not_decide_the_next_stop():
    """Median over the window absorbs a single contention spike."""
    samples = [[10 * GB, 60], [10 * GB, 600], [10 * GB, 60]]
    assert estimate_seconds(10 * GB, samples) == pytest.approx(60)


def test_cube_expected_to_overrun_the_deadline_is_not_started():
    samples = [[100 * GB, 3600]]
    fits, estimate = fits_in_budget(200 * GB, samples, now=1000, deadline=1000 + 3 * 3600)
    assert estimate == pytest.approx(7200)
    assert fits is True

    fits, _ = fits_in_budget(200 * GB, samples, now=1000, deadline=1000 + 1.5 * 3600)
    assert fits is False


def test_expired_deadline_stops_the_sweep():
    assert fits_in_budget(1 * GB, [[1 * GB, 1]], now=100, deadline=99)[0] is False


# --- instructions ----------------------------------------------------------

def test_defaults_are_the_conservative_ones():
    resolved = resolve_options({"instance": "srv"})
    assert resolved["string_policy"] == "skip_any"
    assert resolved["revert_on_regression"] is True
    assert resolved["disable_active_chores"] is False
    assert resolved["order"] == "asc"
    assert resolved == {**DEFAULT_OPTIONS, "exclude_cubes": [],
                        "time_limit_hours": float(DEFAULT_OPTIONS["time_limit_hours"]),
                        "min_cube_mb": float(DEFAULT_OPTIONS["min_cube_mb"])}


@pytest.mark.parametrize("config, message", [
    ({}, "instance"),
    ({"instance": "srv", "time_limit_hours": 0}, "time_limit_hours"),
    ({"instance": "srv", "time_limit_hours": True}, "time_limit_hours"),
    ({"instance": "srv", "order": "sideways"}, "order"),
    ({"instance": "srv", "string_policy": "ignore"}, "string_policy"),
    ({"instance": "srv", "exclude_cubes": "Cube A"}, "exclude_cubes"),
    ({"instance": "srv", "min_cube_mb": -1}, "min_cube_mb"),
    ({"instance": "srv", "max_consecutive_failures": 0}, "max_consecutive_failures"),
    ({"instance": "srv", "revert_on_regression": "yes"}, "revert_on_regression"),
    ({"instance": "srv", "include_optimized": 1}, "include_optimized"),
])
def test_bad_instructions_fail_before_anything_is_touched(config, message):
    with pytest.raises(ValueError, match=message):
        validate_db_config(config)


def test_minimal_instructions_are_valid():
    validate_db_config({"instance": "srv"})
