import pytest

from optimuspy import search


def test_ranking_back_half_is_always_ram():
    assert search.ranking_for_position(4, 3, has_views=False, has_processes=False) == "ram"
    assert search.ranking_for_position(4, 3, has_views=True, has_processes=True) == "ram"


def test_ranking_front_half_prefers_query_then_process_then_ram():
    assert search.ranking_for_position(1, 3, has_views=True, has_processes=True) == "query"
    assert search.ranking_for_position(1, 3, has_views=False, has_processes=True) == "process"
    assert search.ranking_for_position(1, 3, has_views=False, has_processes=False) == "ram"


@pytest.mark.parametrize("count, expected", [(0, 0), (1, 0), (2, 1), (5, 2),
                                             (6, 3), (7, 3), (8, 4)])
def test_midpoint_halves_the_dimension_count(count, expected):
    assert search.midpoint(count) == expected


def test_the_walk_goes_outside_in_and_stops_at_the_midpoint():
    # 12 dims, midpoint 6: last, first, then inward, never reaching slot 6 or 5.
    assert search.outside_in_slots(12, reserved=()) == [11, 0, 10, 1, 9, 2, 8, 3, 7, 4]


def test_the_walk_passes_over_reserved_slots():
    assert search.outside_in_slots(6, reserved={5}) == [0, 4, 1]
    assert search.outside_in_slots(6, reserved={0, 4}) == [5, 1]


def test_fast_keeps_the_first_two_slots_of_the_walk():
    assert search.outside_in_slots(12, reserved=(), fast=True) == [11, 0]
    # A locked last slot: the last free slot and the first.
    assert search.outside_in_slots(12, reserved={11}, fast=True) == [0, 10]


def test_planned_evaluations_counts_every_unplaced_dimension_at_every_slot():
    # 12 movable dims: fast measures 11 + 10, thorough 11 + 10 + ... + 2.
    assert search.planned_evaluations(12, 2) == 21
    assert search.planned_evaluations(12, 10) == 65
    assert search.planned_evaluations(2, 5) == 1
