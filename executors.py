import logging
import random
import time
from typing import List, Dict

from TM1py import TM1Service

from optimuspy import ExecutionMode
from results import PermutationResult


def swap(order: list, i1, i2) -> List[str]:
    seq = order[:]
    seq[i1], seq[i2] = seq[i2], seq[i1]
    return seq


def swap_random(order: list) -> List[str]:
    idx = range(len(order))
    i1, i2 = random.sample(idx, 2)
    return swap(order, i1, i2)


class OptipyzerExecutor:
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: list, displayed_dimension_order, executions,
                 measure_dimension_only_numeric):
        self.tm1 = tm1
        self.cube_name = cube_name
        self.view_names = view_names
        self.dimensions = displayed_dimension_order
        self.executions = executions
        self.measure_dimension_only_numeric = measure_dimension_only_numeric
        self.mode = None

    def _determine_query_permutation_result(self) -> Dict[str, List[float]]:
        query_times_by_view = {}
        for view_name in self.view_names:
            query_times = []
            for _ in range(self.executions):
                before = time.time()
                self.tm1.cubes.cells.create_cellset_from_view(
                    cube_name=self.cube_name, view_name=view_name, private=False)
                query_times.append(time.time() - before)
            query_times_by_view[view_name] = query_times
        return query_times_by_view

    def _evaluate_permutation(self, permutation: List[str], retrieve_ram: bool = False) -> PermutationResult:
        ram_percentage_change = self.tm1.cubes.update_storage_dimension_order(self.cube_name, permutation)
        query_times_by_view = self._determine_query_permutation_result()

        ram_usage = None
        if retrieve_ram:
            ram_usage = self._retrieve_ram_usage()

        return PermutationResult(self.mode, self.cube_name, self.view_names, permutation, query_times_by_view,
                                 ram_usage, ram_percentage_change)

    def _retrieve_ram_usage(self):
        value = None
        for _ in range(10):
            mdx = """
            SELECT  
            {{ [}}PerfCubes].[{}] }} ON ROWS,
            {{ [}}StatsStatsByCube].[Total Memory Used] }} ON COLUMNS
            FROM [}}StatsByCube]
            WHERE ([}}TimeIntervals].[LATEST)
            """.format(self.cube_name)
            value = next(self.tm1.cubes.cells.execute_mdx_values(mdx=mdx))
            if value:
                break

            logging.info("Failed to retrieve RAM consumption. Waiting 15s before retry")
            time.sleep(15)

        if not value:
            raise RuntimeError("Performance Monitor must be activated")

        return value


class OriginalOrderExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric, original_dimension_order):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)
        self.mode = ExecutionMode.ORIGINAL_ORDER
        self.original_dimension_order = original_dimension_order

    def execute(self):
        # at initial execution ram must be retrieved
        return [self._evaluate_permutation(self.original_dimension_order, retrieve_ram=True)]


class BruteForceExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric, max_permutations):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)
        self.mode = ExecutionMode.BRUTE_FORCE
        self.max_permutations = max_permutations

    def _generate_permutation(self):
        for _ in range(self.max_permutations):
            permutation = self.dimensions[:]
            if self.measure_dimension_only_numeric:
                random.shuffle(permutation)

            else:
                non_measure_dimensions = permutation[0:-1]
                random.shuffle(non_measure_dimensions)
                permutation = non_measure_dimensions + permutation[-1:]

            yield permutation

    def execute(self) -> List[PermutationResult]:
        results = list()

        for it, permutation in enumerate(self._generate_permutation()):
            results.append(self._evaluate_permutation(permutation))

            if it > 0 and it % 10 == 0:
                logging.info("{} {}% done. {} iterations completed".format(
                    self.mode,
                    int((it / self.max_permutations) * 100),
                    it))

        logging.info("{} 100 % done. {} iterations completed".format(self.mode, self.max_permutations))
        return results


class OneShotExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)
        self.mode = ExecutionMode.ONE_SHOT

    def _determine_one_shot_order(self) -> List[str]:
        sparsity_ratios = []

        for dimension in self.dimensions:
            ratio = self._calculate_sparsity_ratio(
                dimension=dimension,
                other_dimensions=[d for d in self.dimensions if d != dimension],
                cube_name=self.cube_name)

            logging.info("Sparsity ratio for dimension '{dimension}': {0:.2f}".format(ratio, dimension=dimension))
            sparsity_ratios.append((ratio, dimension))

        one_shot_order = [tupl[1] for tupl in reversed(sorted(sparsity_ratios))]
        logging.info("Determined One Shot order: '{}'".format(one_shot_order))

        return one_shot_order

    def _calculate_sparsity_ratio(self, dimension, other_dimensions, cube_name) -> float:
        number_of_leaves = self.tm1.dimensions.hierarchies.elements.get_number_of_leaf_elements(
            dimension_name=dimension,
            hierarchy_name=dimension)
        mdx = """
    SELECT 
    NON EMPTY {} ON ROWS,
    NON EMPTY {} ON COLUMNS
    FROM [{}]
    """.format(
            "{Tm1FilterByLevel({Tm1SubsetAll([" + dimension + "])}, 0)}",
            "*".join("{[" + dimension_name + "].DefaultMember}" for dimension_name in other_dimensions),
            cube_name)
        populated_rows = self.tm1.cubes.cells.execute_mdx_cellcount(mdx)
        return populated_rows / number_of_leaves

    def execute(self) -> List[PermutationResult]:
        order = self._determine_one_shot_order()
        return [self._evaluate_permutation(order)]


class GreedyExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric, max_permutations):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)

        if len(view_names) > 1:
            logging.warning("Greedy mode will use first view and ignore other views: " + str(view_names[1:]))

        self.view_name = view_names[0]
        self.mode = ExecutionMode.GREEDY
        self.max_permutations = max_permutations

    def _determine_start_order(self) -> List[str]:
        return sorted(
            self.dimensions,
            key=lambda dim: self.tm1.dimensions.hierarchies.elements.get_number_of_leaf_elements(dim, dim))

    def execute(self) -> List[PermutationResult]:
        best_order = self._determine_start_order()
        best_result = self._evaluate_permutation(best_order)
        results = [best_result]
        discarded_orders = set()

        for _ in range(self.max_permutations):
            current_order = swap_random(best_order)
            if tuple(current_order) in discarded_orders:
                continue
            current_permutation_result = self._evaluate_permutation(current_order)

            if current_permutation_result.mean_query_time(self.view_name) < best_result.mean_query_time(self.view_name):
                results.append(current_permutation_result)
                best_order = current_order
                best_result = current_permutation_result
            else:
                discarded_orders.add(tuple(current_order))

        return results


class BestExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)

        if len(view_names) > 1:
            logging.warning("BestExecutor mode will use first view and ignore other views: " + str(view_names[1:]))

        self.view_name = view_names[0]

    def execute(self) -> List[PermutationResult]:
        resulting_order = self.dimensions[:]
        permutation_results = []
        dimension_pool = self.dimensions[:]

        # position at which to switch from looking at memory change to looking at performance
        switch = int(len(dimension_pool) / 2)

        for position in reversed(range(len(self.dimensions))):
            results_per_dimension = list()

            for original_position, dimension in enumerate(dimension_pool):
                permutation = list(resulting_order)
                permutation = swap(permutation, position, original_position)
                permutation_result = self._evaluate_permutation(permutation)
                permutation_results.append(permutation_result)
                results_per_dimension.append(permutation_result)

            if position > switch:
                best_order = sorted(
                    results_per_dimension,
                    key=lambda r: r.mean_query_time(self.view_name))[0]

            else:
                best_order = sorted(
                    results_per_dimension,
                    key=lambda r: r.ram_usage)[0]

            resulting_order = list(best_order.dimension_order)

            dimension_pool = list(resulting_order)
            del dimension_pool[position]

        return permutation_results
