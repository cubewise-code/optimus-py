import itertools
import os
import statistics
from typing import List

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

    def mean_query_time(self, view_name: str) -> float:
        return statistics.mean(self.query_times_by_view[view_name])

    def build_csv_header(self) -> str:
        return ",".join(
            ["ID", "Mode", "Mean Query Time", "RAM", "RAM Change in %"] +
            ["Dimension" + str(d) for d in range(1, len(self.dimension_order) + 1)]) + "\n"

    def to_csv_row(self, view_name: str) -> str:
        from optimuspy import LABEL_MAP

        return ",".join(
            [str(self.permutation_id)] +
            [LABEL_MAP[self.mode]] +
            ["{0:.8f}".format(self.mean_query_time(view_name))] +
            ["{0:.0f}".format(self.ram_usage)] +
            ["{0:.2f} %".format(self.ram_percentage_change)] +
            list(self.dimension_order)) + "\n"


class OptimusResult:
    def __init__(self, cube_name: str, permutation_results: List[PermutationResult]):
        self.cube_name = cube_name
        self.permutation_results = permutation_results

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
            query_time_ratio = float(result.mean_query_time(view_name)) / float(
                self.original_order_result.mean_query_time(view_name))
            ram_in_gb = float(result.ram_usage) / (1024 ** 3)
            plt.scatter(query_time_ratio, ram_in_gb, color=COLOR_MAP.get(result.mode),
                        label=LABEL_MAP.get(result.mode))
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
        plt.savefig(file_name)
        plt.clf()

    def sorted_by_query_time(self, view_name: str) -> List[PermutationResult]:
        return sorted(
            self.permutation_results,
            key=lambda r: r.mean_query_time(view_name))

    @property
    def original_order_result(self) -> PermutationResult:
        from optimuspy import ExecutionMode

        for result in self.permutation_results:
            if result.mode == ExecutionMode.ORIGINAL_ORDER:
                return result
