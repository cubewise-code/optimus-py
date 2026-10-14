# src/optimuspy/search.py
"""The shape of the greedy search: which slots it visits, and what ranks each one.

Pure functions over positions. No TM1, no I/O. See
docs/adr/0005-greedy-measures-every-candidate.md.

The greedy places one storage slot at a time, from the outside in: the last
slot, then the first, then the second-to-last, then the second, and so on until
the midpoint. The two ends are where the large savings are; the slots in between
refine. At every slot it visits, every dimension not yet placed is measured.
Nothing is ruled out on leaf count: the dimension that belongs last is the
densest one, and leaf count measures size, not density.
"""
from itertools import chain
from typing import Iterable, List

# Fast mode visits only this many slots of the walk: the last free slot and the
# first free slot.
FAST_SLOTS = 2


def midpoint(dimension_count: int) -> int:
    """The front/back split of a cube's order.

    Always derived from the FULL storage order, never from a subset such as the
    movable dimensions. The split is a property of the cube's shape, not of how
    much of that shape a given run happens to be searching: a position's metric
    must not change because the user excluded a dimension somewhere else in the
    order, or because the last slot is locked.
    """
    return dimension_count // 2


def ranking_for_position(target_position: int, mid: int,
                         has_views: bool, has_processes: bool) -> str:
    """Which metric ranks a position: 'ram' | 'query' | 'process'.

    The back half (target_position > mid) is always RAM-ranked; the front half
    is query-ranked when views are set, else process-ranked when processes are
    set, else RAM.
    """
    if target_position > mid:
        return "ram"
    if has_views:
        return "query"
    if has_processes:
        return "process"
    return "ram"


def outside_in_slots(dimension_count: int, reserved: Iterable[int],
                     fast: bool = False) -> List[int]:
    """The slots the greedy sweeps, in the order it sweeps them.

    The walk is last, first, second-to-last, second, ... and stops at the
    midpoint. Reserved slots — held by a locked, excluded or pinned dimension —
    are passed over, so with a locked last slot the walk starts at the
    second-to-last. Fast mode keeps the first FAST_SLOTS slots of the walk.
    """
    reserved = set(reserved)
    mid = midpoint(dimension_count)
    slots = []
    walk = chain(*zip(reversed(range(dimension_count)), range(dimension_count)))
    for position in walk:
        if position == mid:
            break
        if position not in reserved:
            slots.append(position)
    return slots[:FAST_SLOTS] if fast else slots


def planned_evaluations(movable_count: int, slot_count: int) -> int:
    """How many orders a full sweep measures: at the k-th slot, every dimension
    still unplaced except the one already sitting there.

    An upper bound: an order listed in orders_to_ignore is skipped, not measured.
    """
    return sum(max(movable_count - k - 1, 0) for k in range(slot_count))
