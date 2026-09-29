# src/optimuspy/tau.py
"""Leaf-count tolerance (τ) — the cardinality-pruning core of the smart greedy.

Pure functions over dimension *cardinality* (leaf-element counts). No TM1, no
I/O. See docs/adr/0002-cardinality-pruning-keyed-to-optimization-metric.md and
CONTEXT.md (terms: cardinality, leaf-count tolerance (τ)).

The decided-after relation: X is *decided to sit after* Y (larger => sparser =>
later) iff cardinality(X) / cardinality(Y) >= τ. It is a strict partial order
(antisymmetric; transitive for τ > 1), so it can never produce a contradictory
cycle. Pinning and the confidence gate are emergent degenerate cases, not
special-cased here.
"""
from typing import List, Optional, Tuple

# Initial tunable ratios — validated against samples/, not user-exposed. None final.
TAU_RAM = 4.0     # decides an ordering at RAM-ranked positions (full strength)
TAU_QUERY = 10.0  # looser ratio at query-ranked front positions
FOLD_B_MAX_PASSES = 2  # K: Fold B coordinate-descent pass cap


def decides_after(card_larger: int, card_smaller: int, tau: float) -> bool:
    """True if card_larger is decided to sit AFTER card_smaller (>= τ ratio)."""
    if card_smaller <= 0:
        return card_larger > 0
    return card_larger / card_smaller >= tau


def back_frontier(unplaced: List[Tuple[str, int]], tau: float) -> List[str]:
    """Dims eligible for the current back-most open position.

    The maximal elements of the decided-after order: a dim survives unless some
    other unplaced dim is decided to sit after it. Equivalently, dims within τ of
    the current maximum cardinality. Preserves input order.
    """
    if not unplaced:
        return []
    maximum = max(card for _, card in unplaced)
    return [name for name, card in unplaced if not decides_after(maximum, card, tau)]


def front_frontier(unplaced: List[Tuple[str, int]], tau: float) -> List[str]:
    """Dims eligible for the current front-most open position.

    The minimal elements: a dim survives unless it is decided to sit after some
    other unplaced dim. Equivalently, dims within τ of the current minimum
    cardinality. Preserves input order.
    """
    if not unplaced:
        return []
    minimum = min(card for _, card in unplaced)
    return [name for name, card in unplaced if not decides_after(card, minimum, tau)]


def midpoint(dimension_count: int) -> int:
    """The front/back split of a cube's order, shared by both folds.

    Always derived from the FULL storage order, never from a subset such as the
    movable dimensions. The split is a property of the cube's shape, not of how
    much of that shape a given run happens to be searching — ADR-0002 keys
    pruning strength to the metric that owns a position, and a position's metric
    must not change because the user excluded a dimension somewhere else in the
    order, or because the last slot is locked.
    """
    return dimension_count // 2


def ranking_for_position(target_position: int, mid: int,
                         has_views: bool, has_processes: bool) -> str:
    """Which metric ranks a position: 'ram' | 'query' | 'process'.

    Mirrors MainExecutor's best-of selection (executors.py:350-365): the back
    half (target_position > mid) is always RAM-ranked; the front half is
    query-ranked when views are set, else process-ranked when processes are set,
    else RAM.
    """
    if target_position > mid:
        return "ram"
    if has_views:
        return "query"
    if has_processes:
        return "process"
    return "ram"


def tau_for_position(ranking: str, tau_ram: float = TAU_RAM,
                     tau_query: float = TAU_QUERY) -> Optional[float]:
    """The τ used to prune a position, or None when the position must not be pruned.

    RAM-ranked -> full strength; query-ranked -> looser; process-ranked -> None
    (cardinality cannot predict process time; search in full). See docs/adr/0002.
    """
    if ranking == "ram":
        return tau_ram
    if ranking == "query":
        return tau_query
    return None


def fold_a_candidates(unplaced: List[Tuple[str, int]], is_back: bool,
                      tau: Optional[float]) -> List[str]:
    """Candidate dims to test at the current open position.

    tau is None (process-ranked front) -> no pruning: every unplaced dim, in
    order. Otherwise the τ-frontier: back_frontier for a back position, else
    front_frontier.
    """
    if tau is None:
        return [name for name, _ in unplaced]
    return back_frontier(unplaced, tau) if is_back else front_frontier(unplaced, tau)


def _card_of(dim: str, ordered: List[Tuple[str, int]]) -> int:
    for name, card in ordered:
        if name == dim:
            return card
    raise KeyError(dim)


def fold_b_refine_order(ordered: List[Tuple[str, int]], tau: float) -> List[str]:
    """Undecided dims to refine in Fold B, in refinement order.

    A dim is undecided if at least one *other* dim is within τ of it (neither
    dominates nor is dominated). Decided/pinned dims (clearly separated from every
    neighbour) are excluded — the seed already places them correctly. Ordered by
    descending cardinality (a larger dim's placement moves RAM more), input order
    as the tiebreak.
    """
    undecided = []
    for i, (name, card) in enumerate(ordered):
        within_tau_neighbour = any(
            not decides_after(card, other, tau) and not decides_after(other, card, tau)
            for j, (other_name, other) in enumerate(ordered) if j != i
        )
        if within_tau_neighbour:
            undecided.append((i, name, card))
    undecided.sort(key=lambda t: (-t[2], t[0]))  # -cardinality, then seed index
    return [name for _, name, _ in undecided]


def fold_b_allowed_span(dim: str, ordered: List[Tuple[str, int]],
                        tau: Optional[float]) -> Tuple[int, int]:
    """Inclusive (lo, hi) position range dim may occupy under τ.

    tau is None -> every position. Otherwise lo = number of dims dim dominates
    (they must precede it), hi = last index minus the number of dims that dominate
    dim (they must follow it). The contiguous span between what it dominates and
    what dominates it.
    """
    n = len(ordered)
    if tau is None:
        return (0, n - 1)
    card = _card_of(dim, ordered)
    must_precede = sum(1 for name, other in ordered
                       if name != dim and decides_after(card, other, tau))
    must_follow = sum(1 for name, other in ordered
                      if name != dim and decides_after(other, card, tau))
    return (must_precede, (n - 1) - must_follow)
