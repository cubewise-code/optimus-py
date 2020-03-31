import argparse
import configparser
import itertools
import logging
import os
import random
import statistics
import time
from enum import Enum

from TM1py import TM1Service
from matplotlib import pyplot as plt

APP_NAME = "optipyzer"
TIME_STAMP = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
LOGFILE = APP_NAME + ".log"
RESULT_CSV = "results\\{}_{}_{}.csv"
RESULT_PNG = "results\\{}_{}_{}.png"

logging.basicConfig(
    filename=LOGFILE,
    format="%(asctime)s - " + APP_NAME + " - %(levelname)s - %(message)s",
    level=logging.INFO,
)

config = configparser.ConfigParser()
config.read(r'config.ini')


class ExecutionMode(Enum):
    ALL = 0
    BRUTE_FORCE = 1
    ONE_SHOT = 2
    GREEDY = 3
    SMART = 4
    ORIGINAL_ORDER = 5

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        # default
        return cls.ALL


COLOR_MAP = {
    ExecutionMode.BRUTE_FORCE: "#1f77b4",
    ExecutionMode.ORIGINAL_ORDER: "silver",
    ExecutionMode.ONE_SHOT: "darkred",
    ExecutionMode.GREEDY: "#7000a0",
    "Mean": "orange"}

LABEL_MAP = {
    ExecutionMode.BRUTE_FORCE: "Brute Force",
    ExecutionMode.ORIGINAL_ORDER: "Original Order",
    ExecutionMode.ONE_SHOT: "One Shot",
    ExecutionMode.GREEDY: "Greedy",
    "Mean": "Mean"}


class PermutationResult:
    counter = 1

    def __init__(self, mode: str, cube_name: str, view_names: list, dimension_order: list,
                 query_times_by_view: dict, ram_usage):
        self.mode = mode
        self.cube_name = cube_name
        self.view_names = view_names
        self.dimension_order = dimension_order
        self.query_times_by_view = query_times_by_view
        self.ram_usage = ram_usage
        self.permutation_id = PermutationResult.counter
        PermutationResult.counter += 1

    def mean_query_time(self, view_name: str):
        return statistics.mean(self.query_times_by_view[view_name])

    def build_csv_header(self):
        return ",".join(
            ["ID", "Mode", "Mean Query Time", "RAM"] +
            ["Dimension" + str(d) for d in range(1, len(self.dimension_order) + 1)]) + "\n"

    def to_csv_row(self, view_name: str):
        return ",".join(
            [str(self.permutation_id)] +
            [LABEL_MAP.get(self.mode)] +
            ["{0:.8f}".format(self.mean_query_time(view_name))] +
            ["{0:.0f}".format(self.ram_usage)] +
            list(self.dimension_order)) + "\n"


class OptipyzerResult:
    def __init__(self, cube_name: str, permutation_results: list):
        self.cube_name = cube_name
        self.permutation_results = permutation_results

    def to_csv(self, view_name):
        lines = itertools.chain(
            [self.permutation_results[0].build_csv_header()],
            [result.to_csv_row(view_name) for result in self.sorted_by_query_time(view_name)])

        os.makedirs(os.path.dirname(RESULT_CSV), exist_ok=True)
        with open(RESULT_CSV.format(self.cube_name, view_name, TIME_STAMP), "w") as file:
            file.writelines(lines)

    # create scatter plot ram vs. performance
    def to_png(self, view_name: str):
        for result in self.permutation_results:
            query_time_ratio = float(result.mean_query_time(view_name)) / float(
                self.original_order_result.mean_query_time(view_name))
            ram_in_gb = float(result.ram_usage) / (1024 ** 3)
            plt.scatter(query_time_ratio, ram_in_gb, color=COLOR_MAP.get(result.mode), label=LABEL_MAP.get(result.mode))
            plt.text(query_time_ratio, ram_in_gb, result.permutation_id, fontsize=7)

        mean_query_time = statistics.mean(
            [result.mean_query_time(view_name)
             for result
             in self.permutation_results]) / float(self.original_order_result.mean_query_time(view_name))
        mean_ram = statistics.mean(
            [result.ram_usage
             for result
             in self.permutation_results]) / (1024 ** 3)
        plt.scatter(mean_query_time, mean_ram, color=COLOR_MAP.get("Mean"), label=LABEL_MAP.get("Mean"))
        plt.text(mean_query_time, mean_ram, "", fontsize=7)

        # prettify axes
        plt.xlabel('Query Time Compared to Original Order')
        plt.ylabel('RAM in GB')
        plt.gca().set_xticklabels(['{:.0f}%'.format(x * 100) for x in plt.gca().get_xticks()])

        # plot legend
        handles, labels = plt.gca().get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        plt.legend(by_label.values(), by_label.keys())

        plt.grid(True)
        plt.savefig(RESULT_PNG.format(self.cube_name, view_name, TIME_STAMP))
        plt.clf()

    def sorted_by_query_time(self, view_name: str):
        return sorted(self.permutation_results, key=lambda r: r.mean_query_time(view_name))

    @property
    def original_order_result(self):
        for result in self.permutation_results:
            if result.mode == ExecutionMode.ORIGINAL_ORDER:
                return result

    def best_query_result(self, view_name: str):
        return self.sorted_by_query_time(view_name)[0]


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

    def _determine_query_permutation_result(self):
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

    def _evaluate_permutation(self, permutation: list) -> PermutationResult:
        self.tm1.cubes.update_storage_dimension_order(self.cube_name, permutation)

        query_times_by_view = self._determine_query_permutation_result()
        ram_usage = self._retrieve_ram_usage()

        return PermutationResult(self.mode, self.cube_name, self.view_names, permutation, query_times_by_view,
                                 ram_usage)

    def _retrieve_ram_usage(self):
        mdx = """
        SELECT  
        {{ [}}PerfCubes].[{}] }} ON ROWS,
        {{ [}}StatsStatsByCube].[Total Memory Used] }} ON COLUMNS
        FROM [}}StatsByCube]
        WHERE ([}}TimeIntervals].[LATEST])
        """.format(self.cube_name)
        value = next(self.tm1.cubes.cells.execute_mdx_values(mdx=mdx))
        if not value:
            raise RuntimeError("Aborting " + APP_NAME + " - Performance Monitor must be activated")
        return value

    @staticmethod
    def swap(order: list, i1, i2) -> list:
        seq = order[:]
        seq[i1], seq[i2] = seq[i2], seq[i1]
        return seq

    @staticmethod
    def swap_random(order: list) -> list:
        idx = range(len(order))
        i1, i2 = random.sample(idx, 2)
        return OptipyzerExecutor.swap(order, i1, i2)


class OriginalOrderExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric, original_dimension_order):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)
        self.mode = ExecutionMode.ORIGINAL_ORDER
        self.original_dimension_order = original_dimension_order

    def execute(self):
        return [self._evaluate_permutation(self.original_dimension_order)]


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

    def execute(self):
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

    def _determine_one_shot_order(self):
        sparsity_ratios = []

        for dimension in self.dimensions:
            ratio = self._calculate_sparsity_ratio(
                dimension=dimension,
                other_dimensions=[d for d in self.dimensions if d != dimension],
                cube_name=self.cube_name)

            logging.info("Sparsity ratio for dimension '{dimension}': {0:.2f}".format(ratio, dimension=dimension))
            sparsity_ratios.append((ratio, dimension))

        one_shot_order = [tupl[1] for tupl in reversed(sorted(sparsity_ratios))]
        logging.info("Determined {} order: {}".format(LABEL_MAP.get(self.mode), one_shot_order))

        return one_shot_order

    def _calculate_sparsity_ratio(self, dimension, other_dimensions, cube_name):
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

    def execute(self):
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

    def _determine_start_order(self) -> list:
        return sorted(
            self.dimensions,
            key=lambda dim: self.tm1.dimensions.hierarchies.elements.get_number_of_leaf_elements(dim, dim))

    def _determine_next_order(self, order) -> list:
        return self.swap_random(order)

    def execute(self) -> list:
        best_order = self._determine_start_order()
        best_result = self._evaluate_permutation(best_order)
        results = [best_result]
        discarded_orders = set()

        for _ in range(self.max_permutations):
            current_order = self._determine_next_order(best_order)
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


class SmartExecutor(OptipyzerExecutor):
    def __init__(self, tm1: TM1Service, cube_name, view_names, dimensions, executions,
                 measure_dimension_only_numeric):
        super().__init__(tm1, cube_name, view_names, dimensions, executions,
                         measure_dimension_only_numeric)

        if len(view_names) > 1:
            logging.warning("Smart mode will use first view and ignore other views: " + str(view_names[1:]))

        self.view_name = view_names[0]
        self.mode = ExecutionMode.SMART

    def execute(self):
        current_order = []
        dimensions_left = self.dimensions[:]

        for position in range(len(self.dimensions)):
            results_per_dimension = list()

            for original_position, dimension in enumerate(self.dimensions):
                if dimension in current_order:
                    continue

                permutation = current_order + OptipyzerExecutor.swap(dimensions_left, position, original_position)[
                                              position:]
                results_per_dimension.append(self._evaluate_permutation(permutation))

            best_dimension_for_position = sorted(
                results_per_dimension,
                key=lambda r: r.mean_query_time(self.view_name))[0].dimension_order[position]

            current_order.append(best_dimension_for_position)
            dimensions_left.remove(best_dimension_for_position)

        return current_order


def main(cube_name, view_names, measure_dimension_only_numeric, max_permutations, executions, mode):
    with TM1Service(**config["tm1srv01"], session_context=APP_NAME) as tm1:
        original_dimension_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)
        displayed_dimension_order = tm1.cubes.get_dimension_names(cube_name=cube_name)

        try:
            permutation_results = list()
            # One Shot goes first, as it may blow up the overall RAM for the cube
            if mode == ExecutionMode.ALL or mode == ExecutionMode.ONE_SHOT:
                one_shot = OneShotExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric)
                permutation_results += one_shot.execute()

            if mode == ExecutionMode.ALL or mode == ExecutionMode.BRUTE_FORCE:
                brute_force = BruteForceExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, max_permutations)
                permutation_results += brute_force.execute()

            if mode == ExecutionMode.ALL or mode == ExecutionMode.GREEDY:
                greedy = GreedyExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, max_permutations)
                permutation_results += greedy.execute()

            if mode == ExecutionMode.ALL or mode == ExecutionMode.SMART:
                smart = SmartExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric)
                permutation_results += smart.execute()

            original_order = OriginalOrderExecutor(
                tm1, cube_name, view_names, displayed_dimension_order, executions,
                measure_dimension_only_numeric, original_dimension_order)
            permutation_results += original_order.execute()

            optipyzer_result = OptipyzerResult(cube_name, permutation_results)

            logging.info("Analysis Completed")
            logging.info("More details in csv and png files in results folder")
            for view_name in view_names:
                optipyzer_result.to_csv(view_name)
                optipyzer_result.to_png(view_name)

        except Exception:
            logging.error("Fatal error", exc_info=True)

        finally:
            logging.info("Reestablishing original dimension order")
            tm1.cubes.update_storage_dimension_order(cube_name, original_dimension_order)


if __name__ == "__main__":
    # take arguments from cmd
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--cube',
                        action="store",
                        dest="cube_name",
                        help="name of the cube",
                        default=None)
    parser.add_argument('-v', '--views',
                        action="store",
                        dest="view_names",
                        help="comma separated list cube views",
                        default=None)
    parser.add_argument('-n', '--numeric',
                        action="store",
                        dest="measure_dimension_only_numeric",
                        help="all measures are numeric elements (True=1, False=0)",
                        default=1)
    parser.add_argument('-p', '--permutations',
                        action="store",
                        dest="max_permutations",
                        help="maximum number of permutations to evaluate (required for BRUTE_FORCE or GREEDY mode)",
                        default=100)
    parser.add_argument('-e', '--executions',
                        action="store",
                        dest="executions",
                        help="number of executions per view",
                        default=15)
    parser.add_argument('-m', '--mode',
                        action="store",
                        dest="mode",
                        help="All, Brute_Force or One_Shot",
                        default="All")

    cmd_args = parser.parse_args()
    logging.info("Starting. Arguments retrieved from cmd: " + str(cmd_args))
    main(
        cube_name=cmd_args.cube_name,
        view_names=cmd_args.view_names.split(","),
        measure_dimension_only_numeric=int(cmd_args.measure_dimension_only_numeric),
        max_permutations=int(cmd_args.max_permutations),
        executions=int(cmd_args.executions),
        mode=ExecutionMode(cmd_args.mode))
    logging.info("Done")
