import logging
import random
import time
from itertools import chain
from typing import List, Dict

from TM1py import TM1Service, Process

from optimuspy import tau
from optimuspy.execution_mode import ExecutionMode
from optimuspy.metrics import read_cube_memory_bytes
from optimuspy.results import ExecutionContext, PermutationResult


class OptimizationCancelled(Exception):
    pass


def swap(order: list, i1, i2) -> List[str]:
    seq = order[:]
    seq[i1], seq[i2] = seq[i2], seq[i1]
    return seq


def swap_random(order: list) -> List[str]:
    idx = range(len(order))
    i1, i2 = random.sample(idx, 2)
    return swap(order, i1, i2)


class OptipyzerExecutor:
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_names: List[str],
                 displayed_dimension_order: List[str],
                 executions: int, measure_dimension_only_numeric: bool, context: ExecutionContext,
                 checkpoint_manager=None, process_parameters: dict = None, cancel_event=None,
                 is_v12: bool = False):
        self.tm1 = tm1
        self.cube_name = cube_name
        self.view_names = view_names
        self.process_names = process_names
        self.dimensions = displayed_dimension_order
        self.executions = executions
        self.measure_dimension_only_numeric = measure_dimension_only_numeric
        self.is_v12 = is_v12
        self.mode = None
        self.include_process = bool(process_names)
        self.cube_dim_number = len(self.dimensions)
        self.context = context
        self.checkpoint_manager = checkpoint_manager
        self.process_parameters = process_parameters or {}
        self.cancel_event = cancel_event
        self._initial_dimension_order = None
        self._original_order_result = None
        self._resumed_results = []
        # One-shot: the first evaluation after a resume takes an absolute RAM read
        # to re-anchor the stale %-chain (set by set_resume_context).
        self._reanchor_needed = False
        # Snapshot of the last `received` checkpoint (completed results + executor
        # state), so a `submitted` write can preserve it while adding pending.
        self._last_checkpoint = None
        # Level-2 recovered in-flight orders keyed by tuple(order); the evaluation
        # paths inject these instead of re-applying the reorder.
        self._recovered_results = {}

    def _check_cancelled(self):
        if self.cancel_event and self.cancel_event.is_set():
            raise OptimizationCancelled("Optimization cancelled by user")

    def set_resume_context(self, initial_dimension_order, original_order_result, resumed_results,
                           resuming=True):
        """Set checkpoint resume context. Called before execute() on every run.

        `resuming` arms the one-shot RAM re-anchor: True only when actually
        resuming a checkpoint (the %-chain anchor is stale then). On a fresh run
        core passes resuming=False so the first iteration keeps the fast % method.
        """
        self._initial_dimension_order = initial_dimension_order
        self._original_order_result = original_order_result
        self._resumed_results = resumed_results
        self._reanchor_needed = resuming

    def register_recovered(self, result):
        """Record a Level-2 recovered in-flight order so it is never re-applied.

        The order joins _resumed_results (so it appears in the merged report and
        the checkpoint), and the evaluation paths inject its result instead of
        re-sending the reorder. Recovery already took the one absolute RAM read,
        so the first-eval re-anchor is disarmed here.
        """
        self._resumed_results.append(result)
        self._recovered_results[tuple(result.dimension_order)] = result
        self._reanchor_needed = False

    def measure_recovered_landed(self, order, abs_ram, pct):
        """Landed branch: run only the outstanding views/processes for `order`.

        The reorder already landed before the drop, so it is not repeated. The
        result carries the fresh absolute RAM (re-anchoring the %-chain) and the
        back-calculated % for display.
        """
        query_times_by_view = self._determine_query_permutation_result()
        process_times_by_process = None
        if self.include_process:
            process_times_by_process = self._determine_process_permutation_result()
        return PermutationResult(
            self.context, self.mode, self.cube_name, self.view_names, self.process_names,
            list(order), query_times_by_view, process_times_by_process,
            ram_usage=abs_ram, ram_percentage_change=pct, reorder_duration=0.0,
            reanchor=True)

    def _determine_query_permutation_result(self) -> Dict[str, List[float]]:
        query_times_by_view = {}
        for view_name in self.view_names:
            query_times = []
            for _ in range(self.executions):
                self.clear_cube_cache()

                before = time.time()
                self.tm1.cells.create_cellset_from_view(cube_name=self.cube_name, view_name=view_name, private=False)
                query_times.append(time.time() - before)
            query_times_by_view[view_name] = query_times
        return query_times_by_view

    def _determine_process_permutation_result(self) -> Dict[str, List[float]]:
        process_times_by_process = {}
        for process_name in self.process_names:
            execution_times = []
            for _ in range(self.executions):
                self.clear_cube_cache()
                before = time.time()
                params = self.process_parameters.get(process_name, {})
                success, status, _ = self.tm1.processes.execute_with_return(process_name=process_name, **params)
                if not success:
                    raise RuntimeError(f"Process: '{process_name}' not successful; Status: '{status}'")
                execution_times.append(time.time() - before)
            process_times_by_process[process_name] = execution_times
        return process_times_by_process

    def _progress_label(self, is_original_order: bool, total_permutations) -> str:
        # 1-indexed. Omit "of N" when the total is unknown (the folds prune the
        # candidate set as they go, so no honest upfront total exists).
        if is_original_order:
            return "Original Order"
        n = self.context.counter - 1
        return f"Iteration {n} of {total_permutations}" if total_permutations else f"Iteration {n}"

    def _evaluate_permutation(self, permutation: List[str], retrieve_ram: bool = False,
                              is_original_order: bool = False,
                              total_permutations=None) -> PermutationResult:
        progress_label = self._progress_label(is_original_order, total_permutations)

        logging.info(f"{progress_label} - Testing order: {permutation}")

        # Mark this order `submitted` (v3 pending) before the reorder is sent, so a
        # drop between the reorder and the received write leaves it recoverable.
        if not is_original_order:
            self._write_pending(permutation)

        # First measurement after a resume: take one absolute read to re-anchor the
        # stale %-chain, then fall back to the fast % method for every later order.
        reanchor = False
        if self._reanchor_needed and not is_original_order:
            retrieve_ram = True
            reanchor = True
            self._reanchor_needed = False

        reorder_start = time.time()
        ram_percentage_change = self.tm1.cubes.update_storage_dimension_order(self.cube_name, permutation)
        reorder_duration = time.time() - reorder_start
        query_times_by_view = self._determine_query_permutation_result()

        process_times_by_process = None
        if self.include_process:
            process_times_by_process = self._determine_process_permutation_result()

        ram_usage = None
        if retrieve_ram:
            ram_usage = self._retrieve_ram_usage()

        permutation_result = PermutationResult(
            self.context, self.mode, self.cube_name, self.view_names, self.process_names,
            permutation, query_times_by_view, process_times_by_process, ram_usage,
            ram_percentage_change, reorder_duration, reanchor=reanchor)

        query_log = ""
        if self.view_names:
            query_log = f" - Query [s]: {permutation_result.composite_query_time():.5f}"

        process_log = ""
        if self.include_process:
            process_log = f" - Process [s]: {permutation_result.composite_process_time():.5f}"

        logging.info(f"{progress_label} - Result: RAM [GB]: {permutation_result.ram_usage / 1024 ** 3:.2f}"
                     + query_log + process_log)

        return permutation_result

    def _retrieve_ram_usage(self):
        # RAM baseline in bytes via MetricService (cube_memory_used), version-agnostic.
        # v11 keeps the read-retry loop; v12 fails fast (see read_cube_memory_bytes).
        return read_cube_memory_bytes(self.tm1, self.cube_name, self.is_v12)

    def _has_string_elements(self, dimension_name: str) -> bool:
        hierarchy_name = "Leaves" if self.tm1.hierarchies.exists(
            dimension_name=dimension_name, hierarchy_name="Leaves") else dimension_name
        elements = self.tm1.elements.get_element_types(
            dimension_name=dimension_name, hierarchy_name=hierarchy_name, skip_consolidations=True)
        return any(etype != "Numeric" for etype in elements.values())

    def clear_cube_cache(self):
        process = Process(name="", prolog_procedure=f"DebugUtility(125 ,0 ,0 ,'{self.cube_name}' ,'' ,'');")
        success, status, error_log_file = self.tm1.processes.execute_process_with_return(process)

        if not success:
            raise RuntimeError(f"Failed to clear cache for cube '{self.cube_name}'. Status: '{status}'")

    @staticmethod
    def _dedup_results(results):
        """Drop duplicate PermutationResults by permutation_id, preserving order.

        A recovered in-flight order lives in both _resumed_results and a sweep's
        results; deduping here keeps completed_results a clean set.
        """
        seen, unique = set(), []
        for r in results:
            if r.permutation_id in seen:
                continue
            seen.add(r.permutation_id)
            unique.append(r)
        return unique

    def _save_checkpoint(self, new_results, last_applied_order, executor_state=None):
        if not self.checkpoint_manager:
            return
        if not self._original_order_result or not self._initial_dimension_order:
            logging.warning("Checkpoint skipped — resume context not set (call set_resume_context first)")
            return
        # Snapshot this `received` state so a later `submitted` write can preserve
        # it (same completed set + executor_state) while adding a pending order.
        self._last_checkpoint = {
            "new_results": list(new_results),
            "last_applied_order": list(last_applied_order),
            "executor_state": executor_state,
        }
        all_completed = self._dedup_results(self._resumed_results + new_results)
        self.checkpoint_manager.save(
            executor_type=self.__class__.__name__,
            execution_context=self.context,
            initial_dimension_order=self._initial_dimension_order,
            last_applied_order=last_applied_order,
            original_order_result=self._original_order_result,
            completed_results=all_completed,
            executor_state=executor_state,
            pending=None)

    def _write_pending(self, permutation):
        """Write a `submitted` checkpoint (pending set) before the reorder is sent.

        Preserves the last `received` snapshot's completed_results and
        executor_state so no progress is lost; only `pending` is added.
        """
        if not self.checkpoint_manager:
            return
        if not self._original_order_result or not self._initial_dimension_order:
            return
        snap = self._last_checkpoint
        new_results = snap["new_results"] if snap else []
        executor_state = snap["executor_state"] if snap else None
        last_applied = snap["last_applied_order"] if snap else self._initial_dimension_order
        all_completed = self._dedup_results(self._resumed_results + new_results)
        self.checkpoint_manager.save(
            executor_type=self.__class__.__name__,
            execution_context=self.context,
            initial_dimension_order=self._initial_dimension_order,
            last_applied_order=last_applied,
            original_order_result=self._original_order_result,
            completed_results=all_completed,
            executor_state=executor_state,
            pending={"dimension_order": list(permutation)})

    def _sweep_into_position(self, current_order, target_position, candidate_dims,
                             total_permutations, skip_candidate=None,
                             skip_permutation=None, checkpoint_cb=None):
        """P1 primitive: swap each candidate dim into target_position, evaluate.

        Returns the PermutationResult for each candidate that was actually tested.
        Shared by PositionOptimizerExecutor (all candidates) and Fold A (τ-frontier).
        """
        results = []
        for dim in candidate_dims:
            if skip_candidate and skip_candidate(dim, target_position):
                continue
            permutation = swap(current_order, target_position, current_order.index(dim))
            if skip_permutation and skip_permutation(permutation):
                continue
            recovered = self._recovered_results.get(tuple(permutation))
            if recovered is not None:
                # Injected, not re-applied — still competes in _pick_best.
                results.append(recovered)
                if checkpoint_cb:
                    checkpoint_cb(dim, results)
                continue
            self._check_cancelled()
            result = self._evaluate_permutation(permutation, total_permutations=total_permutations)
            results.append(result)
            if checkpoint_cb:
                checkpoint_cb(dim, results)
        return results

    def _sweep_across_positions(self, current_order, target_dim, candidate_positions,
                                total_permutations, skip_permutation=None,
                                checkpoint_cb=None):
        """P2 primitive: move target_dim into each candidate position, evaluate.

        Shared by DimensionOptimizerExecutor (all positions) and Fold B (τ span).
        """
        results = []
        for position in candidate_positions:
            permutation = swap(current_order, position, current_order.index(target_dim))
            if skip_permutation and skip_permutation(permutation):
                continue
            recovered = self._recovered_results.get(tuple(permutation))
            if recovered is not None:
                # Injected, not re-applied — still competes in _pick_best.
                results.append(recovered)
                if checkpoint_cb:
                    checkpoint_cb(position, results)
                continue
            self._check_cancelled()
            result = self._evaluate_permutation(permutation, total_permutations=total_permutations)
            results.append(result)
            if checkpoint_cb:
                checkpoint_cb(position, results)
        return results

    def _pick_best(self, results, ranking):
        """Return the best result by the ranking metric (ascending)."""
        if ranking == "query":
            key = lambda r: r.composite_query_time()
        elif ranking == "process":
            key = lambda r: r.composite_process_time()
        else:
            key = lambda r: r.ram_usage
        return sorted(results, key=key)[0]


class OriginalOrderExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_names: List[str],
                 dimensions: List[str], executions: int,
                 measure_dimension_only_numeric: bool, original_dimension_order: List[str],
                 context: ExecutionContext, checkpoint_manager=None, process_parameters: dict = None,
                 cancel_event=None, is_v12: bool = False):
        super().__init__(tm1, cube_name, view_names, process_names, dimensions, executions,
                         measure_dimension_only_numeric, context, checkpoint_manager, process_parameters,
                         cancel_event, is_v12=is_v12)
        self.mode = ExecutionMode.ORIGINAL_ORDER
        self.original_dimension_order = original_dimension_order

    def execute(self):
        self._check_cancelled()
        # at initial execution ram must be retrieved
        return [self._evaluate_permutation(
            self.original_dimension_order,
            retrieve_ram=True,
            is_original_order=True)]


class MainExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_names: List[str],
                 dimensions: List[str], executions: int, measure_dimension_only_numeric: bool,
                 context: ExecutionContext, fast: bool = False,
                 dimensions_to_exclude: List[str] = None,
                 orders_to_ignore: List[List[str]] = None,
                 checkpoint_manager=None, process_parameters: dict = None,
                 dimension_position_rules: list = None, cancel_event=None, is_v12: bool = False,
                 cardinality: Dict[str, int] = None, string_dims: List[str] = None):
        super().__init__(tm1, cube_name, view_names, process_names, dimensions, executions,
                         measure_dimension_only_numeric, context, checkpoint_manager, process_parameters,
                         cancel_event, is_v12=is_v12)
        self.mode = ExecutionMode.ITERATIONS
        self.fast = fast
        self.dimensions_to_exclude = dimensions_to_exclude or []
        self.orders_to_ignore = orders_to_ignore or []
        self.dimension_position_rules = dimension_position_rules or []
        self.cardinality = cardinality or {}
        self.string_dims = set(string_dims or [])

    def _violates_position_rules(self, permutation: List[str]) -> bool:
        for rule in self.dimension_position_rules:
            dim_name = rule['dimension']
            pos = rule['position']
            if dim_name not in permutation:
                continue
            actual_index = permutation.index(dim_name)
            if pos == 'first' and actual_index == 0:
                return True
            elif pos == 'last' and actual_index == len(permutation) - 1:
                return True
            else:
                try:
                    if actual_index == int(pos) - 1:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def _string_last_skip(self, dim, target_position):
        """Skip swapping a string-bearing dim into the last position (forced order)."""
        last = target_position + 1 == self.cube_dim_number
        return last and dim in self.string_dims

    def _greedy_skip_permutation(self, permutation):
        if permutation in self.orders_to_ignore:
            logging.debug(f"Skipping ignored order: {permutation}")
            return True
        if self._violates_position_rules(permutation):
            logging.debug(f"Skipping order due to position rule violation: {permutation}")
            return True
        return False

    def execute(self, resume_state: dict = None) -> List[PermutationResult]:
        if self.fast:
            return self._run_fold_b(resume_state)
        return self._run_fold_a(resume_state)

    def _run_fold_a(self, resume_state: dict = None) -> List[PermutationResult]:
        dimensions = self.dimensions[:]
        resulting_order = self.dimensions[:]
        permutation_results = []
        dimension_pool = [d for d in self.dimensions if d not in self.dimensions_to_exclude]
        mid = int(len(dimension_pool) / 2)
        if not self.measure_dimension_only_numeric:
            # Lock the string-bearing dim to the last slot using the authoritative
            # string_dims set — NOT presentation-order [-1], which need not be the
            # string dim on an already-optimized cube. Move it last if it isn't,
            # then freeze it: never a swap candidate (out of the pool) and its slot
            # is never a sweep target (out of the iterated range). Fall back to [-1]
            # only if metadata flags no string dim while the measure is non-numeric.
            # TM1 permits at most one such dim, but a list is handled defensively.
            string_last = [d for d in self.dimensions if d in self.string_dims] or [self.dimensions[-1]]
            for sd in string_last:
                if sd in dimension_pool:
                    dimension_pool.remove(sd)
                if sd in dimensions:
                    dimensions.remove(sd)
                if resulting_order[-1] != sd:
                    resulting_order.remove(sd)
                    resulting_order.append(sd)
        has_views, has_processes = bool(self.view_names), bool(self.process_names)

        # Result representing the current resulting_order. It carries the "keep the
        # dim already here" option into _pick_best, so the dim already sitting at a
        # target position is never re-swept into its own slot (a redundant no-op
        # reorder that would duplicate the current order in the report).
        current_result = self._original_order_result

        placed_positions = []
        executor_state = resume_state.get("executor_state", {}) if resume_state else {}
        if "fold_a_state" in executor_state:
            fs = executor_state["fold_a_state"]
            resulting_order = fs["resulting_order"]
            dimension_pool = fs["dimension_pool"]
            placed_positions = fs["placed_positions"]
            current_result = next(
                (r for r in reversed(self._resumed_results)
                 if list(r.dimension_order) == list(resulting_order)),
                self._original_order_result)
            logging.info(f"Resuming Fold A — {len(placed_positions)} positions already locked")

        for target_position in chain(*zip(reversed(range(len(dimensions))), range(len(dimensions)))):
            if target_position == mid:
                break
            if target_position in placed_positions:
                continue
            # Positions held by an excluded (non-pool) dim are frozen — never sweep into them.
            if resulting_order[target_position] not in dimension_pool:
                continue

            unplaced = [(d, self.cardinality.get(d, 0)) for d in dimension_pool]
            ranking = tau.ranking_for_position(target_position, mid, has_views, has_processes)
            tau_val = tau.tau_for_position(ranking)
            is_back = target_position > mid
            frontier = tau.fold_a_candidates(unplaced, is_back, tau_val)
            # Skip the dim already at this position; its "keep" value is current_result.
            occupant = resulting_order[target_position]
            candidates = [c for c in frontier if c != occupant]

            def checkpoint_cb(dim, results, _pp=list(placed_positions)):
                self._save_checkpoint(
                    new_results=permutation_results + results,
                    last_applied_order=list(results[-1].dimension_order),
                    executor_state={"fold_a_state": {
                        "resulting_order": list(resulting_order),
                        "dimension_pool": list(dimension_pool),
                        "placed_positions": _pp,
                    }})

            results = self._sweep_into_position(
                resulting_order, target_position, candidates, None,
                skip_candidate=self._string_last_skip,
                skip_permutation=self._greedy_skip_permutation,
                checkpoint_cb=checkpoint_cb)
            permutation_results.extend(results)

            # Compare the swept alternatives against keeping the current order.
            pool_for_best = results + ([current_result] if current_result is not None else [])
            if pool_for_best:
                best = self._pick_best(pool_for_best, ranking)
                resulting_order = list(best.dimension_order)
                current_result = best
                dimension_pool.remove(resulting_order[target_position])
                placed_positions.append(target_position)

        return permutation_results

    def _seed_order(self):
        """Cardinality-ascending seed with string dims last.

        Only a *string*-bearing dimension is forced to the last slot — that is
        TM1's sole storage-order constraint (CellPutS/string writes target the
        last dimension, so a string dim cannot leave it). A numeric measure has
        no such constraint and is placed purely by cardinality like any other
        dimension: a small/degenerate measure belongs at the FRONT for RAM
        (small-sparse first; the 90/10 rule reserves the last slot for the
        largest-dense dim). This mirrors _compute_suggested_order, which likewise
        locks only string dims last.

        Dimensions in dimensions_to_exclude are frozen at their original index;
        only the movable dims are re-ordered, into the movable positions.
        """
        excluded = set(self.dimensions_to_exclude)
        result = list(self.dimensions)
        movable_positions = [i for i, d in enumerate(self.dimensions) if d not in excluded]
        movable = [d for d in self.dimensions if d not in excluded]
        non_string = [d for d in movable if d not in self.string_dims]
        string_last = [d for d in movable if d in self.string_dims]
        non_string.sort(key=lambda d: self.cardinality.get(d, 0))
        ordered_movable = non_string + string_last
        for pos, dim in zip(movable_positions, ordered_movable):
            result[pos] = dim
        return result

    def _run_fold_b(self, resume_state: dict = None) -> List[PermutationResult]:
        has_views, has_processes = bool(self.view_names), bool(self.process_names)
        # The refine SET uses one tau_split (a dim is "undecided"/worth refining if
        # a neighbour is within it): looser on views cubes so query candidates
        # survive, else RAM strength. The ACCEPT metric and the position SPAN, by
        # contrast, are both chosen PER DIM by region below (ranking_for_position /
        # tau_for_position): RAM strength on the back/last half (the 90/10 rule),
        # looser query on the front (views), unpruned on process fronts. So a
        # query-improving move that regresses RAM at the back is rejected, and a
        # back dim's window is pruned tightly by RAM even when views are set.
        # Mirrors fold A and ADR-0002 ("the back half is always RAM-ranked").
        tau_split = tau.TAU_QUERY if has_views else tau.TAU_RAM

        resulting_order = self._seed_order()
        permutation_results = []
        mid = int(len(resulting_order) / 2)

        start_pass = 0
        executor_state = resume_state.get("executor_state", {}) if resume_state else {}
        if "fold_b_state" in executor_state:
            fs = executor_state["fold_b_state"]
            resulting_order = fs["current_order"]
            start_pass = fs["pass_index"]
            logging.info(f"Resuming Fold B from pass {start_pass}")
        else:
            # seed apply (one reorder) — the anchor of the % chain for this fold
            seed_result = self._evaluate_permutation(resulting_order, total_permutations=None)
            permutation_results.append(seed_result)

        for pass_index in range(start_pass, tau.FOLD_B_MAX_PASSES):
            improved = False
            ordered = [(d, self.cardinality.get(d, 0)) for d in resulting_order]
            # A string-bearing dim is locked to its (seeded-last) slot — moving it
            # off last breaks CellPutS — and an excluded dim is frozen. Neither is
            # ever a refine target, and no other dim may be swept INTO their slots.
            refine = [d for d in tau.fold_b_refine_order(ordered, tau_split)
                      if d not in self.string_dims
                      and d not in self.dimensions_to_exclude]
            reserved_positions = {i for i, d in enumerate(resulting_order)
                                  if d in self.dimensions_to_exclude
                                  or d in self.string_dims}
            for dim in refine:
                current_idx = resulting_order.index(dim)
                # Judge this dim's move — and prune its position window — by the
                # metric that owns its region: RAM for the back/last half, query
                # (views) or process for the front. tau_for_position returns None
                # for process fronts (cardinality can't predict process time), so
                # fold_b_allowed_span leaves those spans unpruned.
                ranking = tau.ranking_for_position(current_idx, mid, has_views, has_processes)
                span_tau = tau.tau_for_position(ranking)
                lo, hi = tau.fold_b_allowed_span(
                    dim, [(d, self.cardinality.get(d, 0)) for d in resulting_order], span_tau)
                positions = [p for p in range(lo, hi + 1)
                             if p != current_idx
                             and p not in reserved_positions]
                if not positions:
                    continue

                def checkpoint_cb(position, results, _p=pass_index):
                    self._save_checkpoint(
                        new_results=permutation_results + results,
                        last_applied_order=list(results[-1].dimension_order),
                        executor_state={"fold_b_state": {
                            "current_order": list(resulting_order),
                            "pass_index": _p,
                        }})

                results = self._sweep_across_positions(
                    resulting_order, dim, positions, total_permutations=None,
                    skip_permutation=self._greedy_skip_permutation,
                    checkpoint_cb=checkpoint_cb)
                permutation_results.extend(results)
                if results:
                    best = self._pick_best(results, ranking)
                    metric = {"query": best.composite_query_time,
                              "process": best.composite_process_time}.get(ranking)
                    best_val = metric() if metric else best.ram_usage
                    # accept only a strict improvement over the current placement
                    current_val = self._current_metric(resulting_order, ranking, permutation_results)
                    if best_val < current_val:
                        resulting_order = list(best.dimension_order)
                        improved = True
            if not improved:
                break

        return permutation_results

    def _current_metric(self, order, ranking, results):
        """Metric value of the most recent result whose order == order (fallback: worst).

        On resume the restored current_order was measured in the PRIOR run, so it
        lives in self._resumed_results, not in this run's `results`. Search both
        (resumed first as older, new results last) most-recent-first, so the
        anchor's real metric is found instead of float('inf') — which would let
        the first resumed sweep accept a regression. On a fresh run
        _resumed_results is empty, so behaviour is identical.
        """
        for r in reversed(self._resumed_results + results):
            if list(r.dimension_order) == list(order):
                if ranking == "query":
                    return r.composite_query_time()
                if ranking == "process":
                    return r.composite_process_time()
                return r.ram_usage
        return float("inf")


class PredefinedOrderExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_names: List[str],
                 dimensions: List[str], executions: int,
                 measure_dimension_only_numeric: bool, predefined_orders: List[List[str]],
                 context: ExecutionContext, checkpoint_manager=None, process_parameters: dict = None,
                 cancel_event=None, is_v12: bool = False):
        super().__init__(tm1, cube_name, view_names, process_names, dimensions, executions,
                         measure_dimension_only_numeric, context, checkpoint_manager, process_parameters,
                         cancel_event, is_v12=is_v12)
        self.mode = ExecutionMode.ITERATIONS
        self.predefined_orders = predefined_orders

    def execute(self, resume_state: dict = None) -> List[PermutationResult]:
        total = len(self.predefined_orders)
        results = []

        completed_indices = set()
        executor_state = resume_state.get("executor_state", {}) if resume_state else {}
        if "predefined_state" in executor_state:
            completed_indices = set(executor_state["predefined_state"]["completed_indices"])
            logging.info(f"Resuming predefined orders: {len(completed_indices)}/{total} already completed")

        for idx, order in enumerate(self.predefined_orders):
            if idx in completed_indices:
                continue

            recovered = self._recovered_results.get(tuple(order))
            if recovered is not None:
                # Injected, not re-applied.
                results.append(recovered)
                completed_indices.add(idx)
                self._save_checkpoint(
                    new_results=results,
                    last_applied_order=list(order),
                    executor_state={
                        "predefined_state": {"completed_indices": sorted(completed_indices)}
                    })
                continue

            self._check_cancelled()
            result = self._evaluate_permutation(order, total_permutations=total)
            results.append(result)

            # Save checkpoint after each permutation
            completed_indices.add(idx)
            self._save_checkpoint(
                new_results=results,
                last_applied_order=list(order),
                executor_state={
                    "predefined_state": {"completed_indices": sorted(completed_indices)}
                })

        return results


class PositionOptimizerExecutor(OptipyzerExecutor):
    """Find the best dimension for a given position."""

    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_names: List[str],
                 dimensions: List[str], executions: int, measure_dimension_only_numeric: bool,
                 target_position: int, context: ExecutionContext,
                 dimensions_to_exclude: List[str] = None, checkpoint_manager=None,
                 process_parameters: dict = None, cancel_event=None, is_v12: bool = False):
        super().__init__(tm1, cube_name, view_names, process_names, dimensions, executions,
                         measure_dimension_only_numeric, context, checkpoint_manager, process_parameters,
                         cancel_event, is_v12=is_v12)
        self.mode = ExecutionMode.ITERATIONS
        self.target_position = target_position
        self.dimensions_to_exclude = dimensions_to_exclude or []

    def execute(self, resume_state: dict = None) -> List[PermutationResult]:
        current_order = self.dimensions[:]
        is_last = (self.target_position == len(current_order) - 1)

        completed_dimensions = set()
        executor_state = resume_state.get("executor_state", {}) if resume_state else {}
        if "position_state" in executor_state:
            completed_dimensions = set(executor_state["position_state"]["completed_dimensions"])
            logging.info(f"Resuming position optimizer: {len(completed_dimensions)} dimensions already tested")

        candidates = [
            dim for dim in current_order
            if dim != current_order[self.target_position] and dim not in self.dimensions_to_exclude
        ]
        # cosmetic upper bound for progress labels only — no API calls here
        total = len([d for d in candidates if d not in completed_dimensions])

        def skip_candidate(dim, target_position):
            if dim in completed_dimensions:
                return True
            if is_last and self._has_string_elements(dim):
                logging.info(f"Skip '{dim}' — has string elements, can't be last")
                return True
            return False

        def checkpoint_cb(dim, results):
            completed_dimensions.add(dim)
            self._save_checkpoint(
                new_results=results,
                last_applied_order=list(results[-1].dimension_order),
                executor_state={"position_state": {"completed_dimensions": sorted(completed_dimensions)}})

        return self._sweep_into_position(
            current_order, self.target_position, candidates, total_permutations=total,
            skip_candidate=skip_candidate, checkpoint_cb=checkpoint_cb)


class DimensionOptimizerExecutor(OptipyzerExecutor):
    """Find the best position for a given dimension."""

    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_names: List[str],
                 dimensions: List[str], executions: int, measure_dimension_only_numeric: bool,
                 target_dimension: str, context: ExecutionContext, checkpoint_manager=None,
                 process_parameters: dict = None, cancel_event=None, is_v12: bool = False):
        super().__init__(tm1, cube_name, view_names, process_names, dimensions, executions,
                         measure_dimension_only_numeric, context, checkpoint_manager, process_parameters,
                         cancel_event, is_v12=is_v12)
        self.mode = ExecutionMode.ITERATIONS
        self.target_dimension = target_dimension

    def execute(self, resume_state: dict = None) -> List[PermutationResult]:
        current_order = self.dimensions[:]
        current_idx = current_order.index(self.target_dimension)
        has_strings = self._has_string_elements(self.target_dimension)
        last_pos = len(current_order) - 1

        completed_positions = set()
        executor_state = resume_state.get("executor_state", {}) if resume_state else {}
        if "dimension_state" in executor_state:
            completed_positions = set(executor_state["dimension_state"]["completed_positions"])
            logging.info(f"Resuming dimension optimizer: {len(completed_positions)} positions already tested")

        candidate_positions = [
            p for p in range(len(current_order))
            if p != current_idx
            and p not in completed_positions
            and not (p == last_pos and has_strings)
        ]
        total = last_pos if not has_strings else last_pos - 1

        def skip_permutation(_permutation):
            return False

        def checkpoint_cb(position, results):
            completed_positions.add(position)
            self._save_checkpoint(
                new_results=results,
                last_applied_order=list(results[-1].dimension_order),
                executor_state={"dimension_state": {"completed_positions": sorted(completed_positions)}})

        return self._sweep_across_positions(
            current_order, self.target_dimension, candidate_positions,
            total_permutations=total, skip_permutation=skip_permutation,
            checkpoint_cb=checkpoint_cb)
