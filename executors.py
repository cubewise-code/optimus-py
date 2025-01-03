import logging
import random
import time
from itertools import chain
from typing import List, Dict

from TM1py import TM1Service, Process

from execution_mode import ExecutionMode
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
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: list, process_name: str,
                 displayed_dimension_order: List[str],
                 executions: int, measure_dimension_only_numeric: bool):
        self.tm1 = tm1
        self.cube_name = cube_name
        self.view_names = view_names
        self.process_name = process_name
        self.dimensions = displayed_dimension_order
        self.executions = executions
        self.measure_dimension_only_numeric = measure_dimension_only_numeric
        self.mode = None
        self.include_process = bool(process_name)
        self.cube_dim_number = len(self.dimensions)

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
        execution_times = []
        for _ in range(self.executions):
            self.clear_cube_cache()
            before = time.time()
            try:
                success, status, _ = self.tm1.processes.execute_with_return(process_name=self.process_name)
            except Exception as e:
                raise e
            if not success:
                raise RuntimeError(f"Process: '{self.process_name}' not successful; Status: '{status}'")
            execution_times.append(time.time() - before)

        return {self.process_name: execution_times}

    def _evaluate_permutation(self, permutation: List[str], retrieve_ram: bool = False,
                              reset_counter: bool = False, is_original_order: bool = False,
                              total_permutations=None) -> PermutationResult:
        ram_percentage_change = self.tm1.cubes.update_storage_dimension_order(self.cube_name, permutation)
        query_times_by_view = self._determine_query_permutation_result()

        process_times_by_process = None
        if self.include_process:
            process_times_by_process = self._determine_process_permutation_result()

        ram_usage = None
        if retrieve_ram:
            ram_usage = self._retrieve_ram_usage()

        permutation_result = PermutationResult(self.mode, self.cube_name, self.view_names, self.process_name,
                                               permutation,
                                               query_times_by_view, process_times_by_process, ram_usage,
                                               ram_percentage_change, reset_counter)

        if is_original_order:
            progress_log = "Original Order"
        else:
            # decrease counter by 2 because log happens post increment and original order not considered as iteration
            progress_log = f"Iteration {PermutationResult.counter - 2} of {total_permutations}"

        process_log = " - No process included in test"
        if self.include_process:
            process_log = f" - Process time [s]: {permutation_result.median_process_time():.5f}"

        logging.info(f"{progress_log} - Evaluated order: {permutation} "
                     f"- RAM [GB]: {permutation_result.ram_usage / 1024 ** 3:.2f} "
                     f"- Query time [s]: {permutation_result.median_query_time():.5f}"
                     + process_log)

        return permutation_result

    def _retrieve_ram_usage(self):
        number_of_iterations = 4
        for i in range(number_of_iterations):
            mdx = """
            SELECT  
            {{ [}}PerfCubes].[{}] }} ON ROWS,
            {{ [}}StatsStatsByCube].[Total Memory Used] }} ON COLUMNS
            FROM [}}StatsByCube]
            WHERE ([}}TimeIntervals].[LATEST])
            """.format(self.cube_name)
            value = list(self.tm1.cells.execute_mdx_values(mdx=mdx))[0]
            if value:
                return value

            logging.info("Failed to retrieve RAM consumption. Waiting 15s before retry")
            if i < number_of_iterations - 1:
                time.sleep(15)

        raise RuntimeError("Performance Monitor must be activated")

    def clear_cube_cache(self):
        process = Process(name="", prolog_procedure=f"DebugUtility(125 ,0 ,0 ,'{self.cube_name}' ,'' ,'');")
        success, status, error_log_file = self.tm1.processes.execute_process_with_return(process)

        if not success:
            raise RuntimeError(f"Failed to clear cache for cube '{self.cube_name}'. Status: '{status}'")


class OriginalOrderExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_name: str, dimensions: List[str],
                 executions: int,
                 measure_dimension_only_numeric: bool, original_dimension_order: List[str]):
        super().__init__(tm1, cube_name, view_names, process_name, dimensions, executions,
                         measure_dimension_only_numeric)
        self.mode = ExecutionMode.ORIGINAL_ORDER
        self.original_dimension_order = original_dimension_order

    def execute(self, reset_counter=True):
        # at initial execution ram must be retrieved
        return [self._evaluate_permutation(
            self.original_dimension_order,
            retrieve_ram=True,
            reset_counter=reset_counter,
            is_original_order=True)]


class MainExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name: str, view_names: List[str], process_name: str, dimensions: List[str],
                 executions: int, measure_dimension_only_numeric: bool, fast: bool = False,
                 dimensions_to_exclude: List[str] = None):
        super().__init__(tm1, cube_name, view_names, process_name, dimensions, executions,
                         measure_dimension_only_numeric)
        self.mode = ExecutionMode.ITERATIONS
        self.fast = fast
        self.dimensions_to_exclude = (
            [] if dimensions_to_exclude is None else dimensions_to_exclude
        )

        if len(view_names) > 1:
            logging.warning("BestExecutor mode will use first view and ignore other views: " + str(view_names[1:]))

        self.view_name = view_names[0]

    def _check_swap_dim_with_str_to_last_position(
            self, dimension_name: str, target_position: int
    ) -> bool:
        # if a dimension has strings and target dimension is the last dimension in the cube - do not swap.
        # rest API allows to swap a dim with string to the last position, but not out of the last position
        if self.tm1.hierarchies.exists(
                dimension_name=dimension_name, hierarchy_name="Leaves"
        ):
            hierarchy_name = "Leaves"
        else:
            hierarchy_name = dimension_name

        elements = self.tm1.elements.get_element_types(
            dimension_name=dimension_name,
            hierarchy_name=hierarchy_name,
            skip_consolidations=True,
        )
        string_elements = [element for element, element_type in elements.items() if element_type != "Numeric"]
        if string_elements:
            logging.info(
                f"Skip swapping dimension '{dimension_name}' into last position because it has string elements: {string_elements}")
        last_target_position = target_position + 1 == self.cube_dim_number
        return string_elements and last_target_position

    def execute(self) -> List[PermutationResult]:
        dimensions = self.dimensions[:]
        resulting_order = self.dimensions[:]
        permutation_results = []
        # dimensions that we're allowed to swap
        dimension_pool = [
            dim for dim in self.dimensions[:] if dim not in self.dimensions_to_exclude
        ]

        mid = int(len(dimension_pool) / 2)

        if not self.measure_dimension_only_numeric:
            dimension_pool.remove(self.dimensions[-1])
            dimensions.remove(self.dimensions[-1])

        if self.fast:
            # for 5 dimensional cubes we evaluate 5 + 4 permutations
            total_permutations = len(dimension_pool) * 2 - 1
        else:
            # for 5 dimensional cubes we evaluate 5 + 4 + 3 + 2 permutations
            total_permutations = sum(range(2, len(dimension_pool) + 1))

        # iteration through positions like: n, 0, n-1, 1, n-2, 2, ...
        for iteration, target_position in enumerate(
                chain(*zip(reversed(range(len(dimensions))), range(len(dimensions))))):
            if self.fast and iteration == 2:
                break

            if target_position == mid:
                break

            results_per_dimension = list()

            # for the current position - swap all the allowed dimensions and append all possible orders to the result set
            for dimension in dimension_pool:
                original_position = resulting_order.index(dimension)
                dimension_target = resulting_order[target_position]

                if (not self._check_swap_dim_with_str_to_last_position(dimension, target_position)
                        and dimension_target in dimension_pool):
                    permutation = list(resulting_order)
                    permutation = swap(permutation, target_position, original_position)
                    permutation_result = self._evaluate_permutation(permutation, total_permutations=total_permutations)
                    permutation_results.append(permutation_result)
                    results_per_dimension.append(permutation_result)

            # only check for best results if any valid dim swaps are returned
            if len(results_per_dimension) > 0:
                # for the current position - if position is higher than the mid-point - sort by ram use
                if target_position > mid:
                    best_order = sorted(
                        results_per_dimension,
                        key=lambda r: r.ram_usage)[0]
                # for the current position - if position is lower than the mid-point - sort by view execution time
                else:
                    best_order = sorted(
                        results_per_dimension,
                        key=lambda r: r.median_query_time(self.view_name))[0]

                resulting_order = list(best_order.dimension_order)
                dimension_pool.remove(resulting_order[target_position])

        return permutation_results
