import itertools
import os
import statistics
from typing import List, Union

import matplotlib.lines as mlines
from matplotlib import pyplot as plt


class PermutationResult:
    counter = 1
    current_ram = None

    def __init__(self, mode: str, cube_name: str, view_names: list, dimension_order: list,
                 query_times_by_view: dict, ram_usage: float = None, ram_percentage_change: float = None,
                 reset_counter: bool = False):
        from optimuspy import ExecutionMode

        self.mode = ExecutionMode(mode)
        self.cube_name = cube_name
        self.view_names = view_names
        self.dimension_order = dimension_order
        self.query_times_by_view = query_times_by_view
        self.is_best = False

        # from original dimension order
        if ram_usage:
            self.ram_usage = ram_usage

        # from all other dimension orders
        elif ram_percentage_change is not None:
            self.ram_usage = PermutationResult.current_ram + (
                    PermutationResult.current_ram * ram_percentage_change / 100)

        else:
            raise RuntimeError("Either 'ram_usage' or 'ram_percentage_change' must be provided")

        PermutationResult.current_ram = self.ram_usage
        self.ram_percentage_change = ram_percentage_change or 0

        if reset_counter:
            PermutationResult.counter = 1

        self.permutation_id = PermutationResult.counter
        PermutationResult.counter += 1

    def median_query_time(self, view_name: str = None) -> float:
        median = statistics.median(self.query_times_by_view[view_name or self.view_names[0]])
        if not median:
            raise RuntimeError(f"view '{view_name}' in cube '{self.cube_name}' is too small")

        return median

    def build_csv_header(self) -> str:
        return ",".join(
            ["ID", "Mode", "Is Best", "Mean Query Time", "RAM"] +
            ["Dimension" + str(d) for d in range(1, len(self.dimension_order) + 1)]) + "\n"

    def to_csv_row(self, view_name: str) -> str:
        from optimuspy import LABEL_MAP

        return ",".join(
            [str(self.permutation_id)] +
            [LABEL_MAP[self.mode]] +
            [str(self.is_best)] +
            ["{0:.8f}".format(self.median_query_time(view_name))] +
            ["{0:.0f}".format(self.ram_usage)] +
            list(self.dimension_order)) + "\n"


class OptimusResult:
    TEXT_FONT_SIZE = 5

    def __init__(self, cube_name: str, permutation_results: List[PermutationResult]):

        self.cube_name = cube_name
        self.permutation_results = permutation_results

        self.best_result = self.determine_best_result()
        if self.best_result:
            for permutation_result in permutation_results:
                if permutation_result.permutation_id == self.best_result.permutation_id:
                    permutation_result.is_best = True

    def to_csv(self, view_name: str, file_name: str):
        lines = itertools.chain(
            [self.permutation_results[0].build_csv_header()],
            [result.to_csv_row(view_name) for result in self.permutation_results])

        os.makedirs(os.path.dirname(file_name), exist_ok=True)
        with open(file_name, "w") as file:
            file.writelines(lines)

    # create scatter plot ram vs. performance
    def to_png(self, view_name: str, file_name: str):
        from optimuspy import LABEL_MAP, COLOR_MAP

        for result in self.permutation_results:
            query_time_ratio = float(result.median_query_time(view_name)) / float(
                self.original_order_result.median_query_time(view_name)) - 1
            ram_in_gb = float(result.ram_usage) / (1024 ** 3)
            plt.scatter(
                query_time_ratio,
                ram_in_gb,
                color=COLOR_MAP.get(result.mode),
                label=LABEL_MAP.get(result.mode),
                marker="x" if result.is_best else ".")
            plt.text(query_time_ratio, ram_in_gb, result.permutation_id, fontsize=self.TEXT_FONT_SIZE)

        mean_query_time = statistics.mean(
            [result.median_query_time(view_name)
             for result
             in self.permutation_results]) / float(self.original_order_result.median_query_time(view_name)) - 1
        mean_ram = statistics.mean(
            [result.ram_usage
             for result
             in self.permutation_results]) / (1024 ** 3)
        plt.scatter(mean_query_time, mean_ram, color=COLOR_MAP.get("Mean"), label=LABEL_MAP.get("Mean"), marker=".")
        plt.text(mean_query_time, mean_ram, "", fontsize=self.TEXT_FONT_SIZE)

        # prettify axes
        plt.xlabel('Query Time Compared to Original Order')
        plt.ylabel('RAM in GB')
        plt.gca().set_xticklabels(['{:.0f}%'.format(x * 100) for x in plt.gca().get_xticks()])

        # plot legend
        handles, labels = plt.gca().get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        # add custom best order marker: x
        by_label["Best"] = mlines.Line2D([], [], color=COLOR_MAP.get("Iterations"), marker='x', linestyle='None',
                                         label='Best Order')
        plt.legend(by_label.values(), by_label.keys())

        plt.grid(True)
        plt.savefig(file_name, dpi=400)
        plt.clf()

    @property
    def original_order_result(self) -> PermutationResult:
        from optimuspy import ExecutionMode

        for result in self.permutation_results:
            if result.mode == ExecutionMode.ORIGINAL_ORDER:
                return result

    def determine_best_result(self) -> Union[PermutationResult, None]:
        ram_range = [result.ram_usage for result in self.permutation_results]
        min_ram, max_ram = min(ram_range), max(ram_range)

        query_speed_range = [result.median_query_time() for result in self.permutation_results]
        min_query_speed, max_query_speed = min(query_speed_range), max(query_speed_range)

        # find a good balance between speed and ram
        for value in (0.01, 0.025, 0.05, 0.075, 0.1, 0.0125, 0.15, 0.2, 0.25):
            ram_threshold = min_ram + value * (max_ram - min_ram)
            query_speed_threshold = min_query_speed + value * (max_query_speed - min_query_speed)
            for permutation_result in self.permutation_results:
                if all([permutation_result.ram_usage <= ram_threshold,
                        permutation_result.median_query_time() <= query_speed_threshold]):
                    return permutation_result

        # no dimension order falls in sweet spot
        return None
