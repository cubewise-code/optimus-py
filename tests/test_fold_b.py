from optimuspy.executors import MainExecutor
from tests.test_fold_a import make_main_executor


def test_fold_b_seeds_pure_cardinality_ascending_for_numeric_only(scripted):
    # Numeric-only cube: NOTHING is forced last. A numeric measure has no TM1
    # constraint, so the seed is pure cardinality ascending -- the smallest dim
    # ("M", 3) leads and the largest ("Big", 50000) takes the last slot (90/10).
    # (The old behaviour force-pinned dims[-1]="M" last; that rule is gone.)
    dims = ["Big", "Sm", "Md", "M"]
    card = {"Big": 50000, "Sm": 50, "Md": 300, "M": 3}
    ex = make_main_executor(dims, card, fast=True)
    log = []
    scripted(ex, lambda o: 100.0, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_b()
    # first evaluated order is the seed: strictly ascending cardinality
    assert log[0] == ["M", "Sm", "Md", "Big"]
    # every pairwise cardinality gap here is >= tau_ram (4x), so fold_b_refine_order
    # decides every dim (nothing undecided) -> the seed apply is the ONLY reorder.
    assert len(log) == 1


def test_fold_b_skips_pinned_dims_and_refines_only_undecided(scripted):
    # NOTE: the brief's original assertion here — `all(o.index("Big") == 2 for o
    # in log)` — is not reachable: Big is pinned/decided (excluded from *refine*,
    # i.e. never chosen as the dim a sweep repositions), but _sweep_across_positions
    # moves dims via raw index swaps, so a genuinely undecided dim (A or B) being
    # swept INTO Big's seeded slot (position 2) necessarily displaces Big out of
    # it as a side effect of that swap. Hand-trace confirms this actually happens
    # here (dim B's tau-allowed span is exactly (1, 2), and 2 is Big's seeded
    # slot), so the literal brief assertion fails on a correct implementation.
    # The real, reachable invariant is: Big is never the *target_dim* of a sweep
    # (fold_b_refine_order excludes it) — we verify that directly by spying on
    # _sweep_across_positions instead of inferring it from collateral positions.
    #
    # With the numeric-measure-last rule removed, the seed is pure cardinality
    # ascending: [M, A, B, Big], so Big (largest) seeds into the LAST slot (3).
    # Big dominates every other dim by >> tau, so its own allowed span is locked
    # to that slot and no other dim's sweep (A/B spans are (1,2)) can reach it —
    # Big stays last throughout.
    dims = ["A", "B", "Big", "M"]
    card = {"A": 180, "B": 205, "Big": 50000, "M": 3}  # A,B undecided; Big pinned
    ex = make_main_executor(dims, card, fast=True)
    log = []
    scripted(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)

    swept_dims = []
    original_sweep = ex._sweep_across_positions

    def spy_sweep(current_order, target_dim, candidate_positions, *args, **kwargs):
        swept_dims.append(target_dim)
        return original_sweep(current_order, target_dim, candidate_positions, *args, **kwargs)

    ex._sweep_across_positions = spy_sweep

    ex._run_fold_b()

    # Big is never the dimension a sweep repositions — it is excluded from
    # refine entirely because it is decided (pinned) relative to every neighbour.
    assert "Big" not in swept_dims
    # Only the genuinely undecided dims (A, B) were ever swept.
    assert set(swept_dims) == {"A", "B"}
    # seed is pure cardinality ascending -> Big (largest) seeds last, and stays
    # last in every evaluated order (no sweep can reach its dominance-locked slot).
    assert all(o.index("Big") == 3 for o in log)


def test_fold_b_caps_at_k_passes(scripted, monkeypatch):
    import optimuspy.tau as tau_mod
    monkeypatch.setattr(tau_mod, "FOLD_B_MAX_PASSES", 2)
    dims = ["A", "B", "C", "M"]
    card = {"A": 100, "B": 110, "C": 120, "M": 3}  # all undecided -> always "improvable"
    ex = make_main_executor(dims, card, fast=True)
    log = []
    # strictly decreasing RAM so every pass finds an improvement -> would loop forever if uncapped
    scripted(ex, lambda o: 100.0 - len(log) * 0.01, log)
    ex.context.set_initial_ram(100.0)
    ex._run_fold_b()
    # bounded: seed(1) + at most K passes * (dims * positions) reorders
    assert len(log) <= 1 + 2 * 3 * 3


def test_fold_b_rejects_ties_and_stops_early_when_a_pass_improves_nothing(scripted):
    # Ties (best_val == the current placement's metric) must NOT be accepted —
    # only a STRICT improvement may move resulting_order. With every candidate
    # tied at the same RAM, the very first pass finds nothing better, so the
    # K-pass loop must stop after pass 0 instead of burning all FOLD_B_MAX_PASSES.
    dims = ["A", "B", "M"]
    card = {"A": 100, "B": 110, "M": 3}  # A,B undecided; M pinned
    ex = make_main_executor(dims, card, fast=True)
    log = []
    scripted(ex, lambda o: 100.0, log)  # every permutation ties at the same RAM
    ex.context.set_initial_ram(100.0)
    ex._run_fold_b()
    # seed [M, A, B] (pure ascending) + one full pass over refine=[B,A]: from that
    # seed B (idx 2) has 1 allowed position and A (idx 1) has 1 -> 2 sweeps.
    # If ties were wrongly accepted (`<=` instead of `<`), resulting_order would
    # keep "changing" and the loop would run the full 2 passes instead of 1.
    assert len(log) == 3


def test_fold_b_process_only_leaves_position_span_unpruned(scripted):
    # ADR-0002: process-only cubes must NOT tau-prune the position SPAN
    # (tau_span=None), even though the refine SET is still pinned via TAU_RAM.
    dims = ["A", "B", "Big", "M"]
    card = {"A": 180, "B": 205, "Big": 50000, "M": 3}
    ex = make_main_executor(dims, card, fast=True, process_names=["P"])
    log = []
    scripted(ex, lambda o: 100.0, log)  # ties everywhere -> no improvement ever accepted
    ex.context.set_initial_ram(100.0)

    swept_dims = []
    original_sweep = ex._sweep_across_positions

    def spy_sweep(current_order, target_dim, candidate_positions, *args, **kwargs):
        swept_dims.append(target_dim)
        return original_sweep(current_order, target_dim, candidate_positions, *args, **kwargs)

    ex._sweep_across_positions = spy_sweep

    ex._run_fold_b()

    # Big/M are still decided (pinned) under TAU_RAM -> excluded from refine.
    assert set(swept_dims) == {"A", "B"}
    # Seed places B at index 1; under a tau_ram-PRUNED span, B could never reach
    # index 0 (M must precede it there, so lo=1). Reaching index 0 proves the
    # SPAN itself was left unpruned for this process-only cube.
    assert any(o.index("B") == 0 for o in log)


def test_fold_b_uses_looser_query_tau_when_views_present(scripted):
    # With views set, the refine SET uses TAU_QUERY (10x), not TAU_RAM (4x).
    # B/A = 500/100 = 5x: decided (excluded from refine) under TAU_RAM, but
    # undecided (included) under TAU_QUERY. If Fold B mistakenly used TAU_RAM for
    # the refine set, refine would be empty and nothing beyond the seed would be
    # evaluated. seed=[M, A, B], mid=1: A (idx 1) is a front/query dim and is swept
    # under its looser TAU_QUERY span; B (idx 2) is a back/RAM dim, now span-locked
    # by TAU_RAM, so it is not swept. A being swept still requires the TAU_QUERY
    # refine set (under TAU_RAM, A is decided -> nothing swept -> len==1).
    dims = ["A", "B", "M"]
    card = {"A": 100, "B": 500, "M": 3}
    ex = make_main_executor(dims, card, fast=True, view_names=["V"])
    log = []
    scripted(ex, lambda o: 100.0, log, query_of=lambda o: 1.0)  # ties -> no acceptance needed
    ex.context.set_initial_ram(100.0)
    ex._run_fold_b()
    # The front/query dim A was swept beyond the seed -> only possible under the
    # looser TAU_QUERY refine set.
    assert len(log) > 1


def test_fold_b_back_span_pruned_by_ram_tau_even_with_views(scripted):
    # Companion to the ranking fix: on a VIEWS cube the back/last position SPAN is
    # pruned by TAU_RAM (4x), not the looser TAU_QUERY (10x). B (4000) and C
    # (25000) are 6.25x apart: undecided under TAU_QUERY (so both enter the refine
    # SET) but decided under TAU_RAM. Both sit in the back half (5 dims, mid=2 ->
    # positions 3,4). Under the OLD global TAU_QUERY span each could move (B<->C
    # swap), so both were swept. With the SPAN pruned per region by TAU_RAM, each
    # dominates/defers the other -> their windows collapse to their own slot and
    # neither is swept. The three front dims are cardinality-separated (decided).
    dims = ["f0", "f1", "f2", "B", "C"]
    card = {"f0": 1, "f1": 15, "f2": 300, "B": 4000, "C": 25000}
    ex = make_main_executor(dims, card, fast=True, view_names=["V"])
    log = []
    scripted(ex, lambda o: 100.0, log, query_of=lambda o: 1.0)
    ex.context.set_initial_ram(100.0)

    swept_dims = []
    original_sweep = ex._sweep_across_positions

    def spy_sweep(current_order, target_dim, candidate_positions, *args, **kwargs):
        swept_dims.append(target_dim)
        return original_sweep(current_order, target_dim, candidate_positions, *args, **kwargs)

    ex._sweep_across_positions = spy_sweep
    ex._run_fold_b()

    # Both back dims are span-locked by TAU_RAM -> neither is ever swept. (Under
    # the old TAU_QUERY span both B and C would have been swept.)
    assert swept_dims == []
    # Only the seed was evaluated; no refine move had any allowed position.
    assert len(log) == 1


def test_fold_b_never_refines_string_dim_off_last(scripted):
    # Review fix: refine must exclude ALL string-bearing dims (decided-by-rule,
    # seeded last), not just the pinned measure. Before the fix, a non-measure
    # string dim that happens to be "undecided" by cardinality (within tau of
    # some other dim) stayed in refine. Since the seed always places string dims
    # last, and the span->positions filter forbids a string dim's OWN sweep from
    # landing back on the last index, refining it necessarily moves it off the
    # last slot with no way back -- violating the hard string-last TM1 rule.
    #
    # "S" (card 120) is deliberately within tau of "D1" (card 100, 1.2x) so it is
    # genuinely undecided -> a real trigger for the bug, not a decided/pinned dim
    # that would be excluded anyway. "D2" (card 50000) dominates D1 by >>4x, which
    # caps D1's own allowed span below the last index (index 3) -- so D1's sweep
    # can never collaterally bump S off its seeded slot either, keeping the
    # assertion clean.
    dims = ["D1", "D2", "S", "M"]
    card = {"D1": 100, "D2": 50000, "S": 120, "M": 3}
    ex = make_main_executor(dims, card, fast=True, string_dims=["S"])
    log = []
    scripted(ex, lambda o: 100.0, log)  # ties everywhere -> nothing ever accepted
    ex.context.set_initial_ram(100.0)

    swept_dims = []
    original_sweep = ex._sweep_across_positions

    def spy_sweep(current_order, target_dim, candidate_positions, *args, **kwargs):
        swept_dims.append(target_dim)
        return original_sweep(current_order, target_dim, candidate_positions, *args, **kwargs)

    ex._sweep_across_positions = spy_sweep

    ex._run_fold_b()

    # S is undecided (within tau of D1) yet must NEVER be the target dim a sweep
    # repositions -- it is excluded from refine unconditionally as a string dim.
    assert "S" not in swept_dims
    # The genuinely undecided non-string dim (D1) was still refined normally.
    assert "D1" in swept_dims
    # S never leaves its seeded last slot in any evaluated order.
    assert all(o[-1] == "S" for o in log)


def test_fold_b_back_positions_are_ram_ranked_even_with_views(scripted):
    # ADR-0002 / 90/10 rule: the back/last positions are RAM-driven regardless of
    # config. Even on a VIEWS cube (front = query-ranked), a move that improves
    # query but REGRESSES RAM at a back position must be REJECTED.
    #
    # 5 dims, mid=2 -> positions 3,4 are the back half. d3 (8000) and d4 (9000) are
    # within tau (undecided) so both are refined and can swap between slots 3 and 4;
    # the three front dims are cardinality-separated (decided) and never refined.
    # RAM rewards the largest dim (d4) in the last slot (seed); query rewards d4 one
    # slot forward (index 3). Under the OLD global query-ranking, fold B accepted the
    # query gain, regressed RAM, and ran a second pass (len(log)==5). Ranking the
    # back half by RAM rejects the swap in pass 0 -> the descent stops (len(log)==3).
    dims = ["d0", "d1", "d2", "d3", "d4"]
    card = {"d0": 1, "d1": 15, "d2": 300, "d3": 8000, "d4": 9000}
    ex = make_main_executor(dims, card, fast=True, view_names=["V"])
    log = []
    # RAM: better (lower) when the largest dim d4 holds the last slot.
    ram_of = lambda o: 100.0 - (5.0 if list(o)[-1] == "d4" else 0.0)
    # Query: better (lower) when d4 sits one slot forward (index 3).
    query_of = lambda o: 1.0 - (0.5 if list(o)[3] == "d4" else 0.0)
    scripted(ex, ram_of, log, query_of=query_of)
    ex.context.set_initial_ram(ram_of(tuple(dims)))
    ex._run_fold_b()

    # seed has d4 last (RAM-optimal); it is never displaced for the query gain.
    assert log[0] == ["d0", "d1", "d2", "d3", "d4"]
    # The RAM-regressing swap is rejected in pass 0, so no second pass runs:
    # seed(1) + one pass over refine=[d4, d3] (1 candidate position each) = 3.
    # (Under the buggy query-ranking this would be 5: the swap is accepted and a
    # second pass runs.)
    assert len(log) == 3


def test_fold_b_never_evicts_string_measure_from_last_slot(scripted):
    # The hard TM1 rule: a string-bearing dim must stay last (CellPutS targets the
    # last dimension). A small string measure S plus two large, similar numeric
    # dims (X=8000, Y=9000, undecided so both are refined) is the trigger: each
    # large dim's RAM-span reaches the last slot (S is too small to defer them),
    # and RAM ranking rewards a large dim last (90/10) -> a sweep would move X/Y
    # into the last slot, evicting S. Reserving string-held positions forbids it.
    dims = ["A", "B", "X", "Y", "S"]
    card = {"A": 1, "B": 15, "X": 8000, "Y": 9000, "S": 50}
    ex = make_main_executor(dims, card, fast=True, string_dims=["S"],
                            measure_only_numeric=False)
    log = []
    # RAM rewards the largest dim last -> maximal pressure to evict the small S.
    ram_of = lambda o: 100.0 - {"Y": 10.0, "X": 9.0}.get(list(o)[-1], 0.0)
    scripted(ex, ram_of, log)
    ex.context.set_initial_ram(ram_of(tuple(dims)))
    ex._run_fold_b()

    # S is seeded last and never leaves it in ANY evaluated order.
    assert log[0][-1] == "S"
    assert all(o[-1] == "S" for o in log), \
        f"string measure evicted from last: {[o for o in log if o[-1] != 'S']}"
    # The large numeric dims are still refined (they just cannot land on S's slot).
    # X and Y remain movable among the non-reserved positions.


def test_fold_b_resume_skips_seed_and_completed_passes(scripted):
    # On resume, _run_fold_b must NOT re-apply the seed (that % was already
    # anchored before checkpointing) and must resume from the checkpointed
    # current_order / pass_index rather than restarting the coordinate descent.
    dims = ["A", "B", "C", "M"]
    card = {"A": 100, "B": 110, "C": 120, "M": 3}  # all undecided -> always "improvable"
    ex = make_main_executor(dims, card, fast=True)
    log = []
    scripted(ex, lambda o: 100.0 - len(log) * 0.1, log)
    ex.context.set_initial_ram(100.0)

    resumed_order = ["C", "B", "M", "A"]
    resume_state = {"executor_state": {"fold_b_state": {
        "seed_order": ["A", "B", "C", "M"],
        "current_order": list(resumed_order),
        "pass_index": 1,  # only the last of FOLD_B_MAX_PASSES=2 remains
    }}}
    ex._run_fold_b(resume_state)

    # No seed re-apply: the first evaluation must be a sweep candidate derived
    # from the resumed current_order, not the freshly-computed seed.
    assert log[0] != ["A", "B", "C", "M"]
    assert log[0] == ["B", "C", "M", "A"]
    # Only ONE remaining pass ran (pass_index resumed at 1, cap is 2): refine=[C,B,A].
    # dim C sweeps 3 positions (current_idx=0 -> [1,2,3]), then dim B sweeps 2
    # positions (current_idx=1 -> [2,3]), then dim A sweeps 3 positions (its
    # current_idx has shifted to 0 by then, since resulting_order was updated by
    # the C- and B-sweeps within this same pass -> [1,2,3] again). 3+2+3=8, with
    # no seed-apply reorder.
    assert len(log) == 8


def test_fold_b_freezes_excluded_dim(scripted):
    # "Excl" is pinned via dimensions_to_exclude at its original index (1).
    # card values are chosen so that:
    #  - the OLD (unfixed) cardinality-only seed sort would relocate Excl (its
    #    absolute rank among all four dims differs from its original slot);
    #  - Excl is genuinely within tau of a neighbour (M, ratio ~1.67 < TAU_RAM)
    #    is avoided (Excl/M = 30, clearly decided) so entanglement with the
    #    pinned measure doesn't confuse the scenario; instead Excl sits close
    #    to A (100/90 ~= 1.11 < TAU_RAM) so it would be marked "undecided" by
    #    tau.fold_b_refine_order and swept if not explicitly excluded;
    #  - A/B (100/110, ratio 1.1) are genuinely undecided, so refinement
    #    actually runs on non-excluded dims;
    #  - both A's and B's allowed spans legitimately include position 1
    #    (Excl's slot), so without the positions exclusion a sweep of A or B
    #    would collaterally displace Excl even though Excl itself is never
    #    the swept target_dim.
    dims = ["A", "Excl", "B", "M"]
    card = {"A": 100, "Excl": 90, "B": 110, "M": 3}
    ex = make_main_executor(dims, card, fast=True)
    ex.dimensions_to_exclude = ["Excl"]
    log = []
    scripted(ex, lambda o: 100.0, log)  # ties everywhere -> nothing ever accepted
    ex.context.set_initial_ram(100.0)

    swept_dims = []
    original_sweep = ex._sweep_across_positions

    def spy_sweep(current_order, target_dim, candidate_positions, *args, **kwargs):
        swept_dims.append(target_dim)
        return original_sweep(current_order, target_dim, candidate_positions, *args, **kwargs)

    ex._sweep_across_positions = spy_sweep

    ex._run_fold_b()

    # (a) the seed keeps Excl frozen at its ORIGINAL index (1), not resorted
    # in among the movable dims by cardinality.
    assert log[0].index("Excl") == 1
    # (b) Excl is never the dimension a sweep repositions.
    assert "Excl" not in swept_dims
    # Refinement genuinely ran on the undecided movable dims (A, B).
    assert set(swept_dims) == {"A", "B"}
    # (c) Excl never leaves its seeded slot in ANY evaluated order -- proving
    # A's/B's sweeps never collaterally swap into Excl's frozen position.
    assert all(o.index("Excl") == 1 for o in log)
