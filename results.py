import itertools
import logging
import os
import statistics
from pathlib import WindowsPath
from typing import List, Union

import seaborn as sns;

sns.set_theme()
import matplotlib.pyplot as plt
import pandas as pd

SEPARATOR = ","
HEADER = ["ID", "Mode", "Is Best", "Mean Query Time", "Query Ratio", "Mean Process Time", "Process Ratio", "RAM",
          "RAM in GB"]


class PermutationResult:
    counter = 1
    current_ram = None

    def __init__(self, mode: str, cube_name: str, view_names: list, process_name: str, dimension_order: list,
                 query_times_by_view: dict, process_times_by_process: dict, ram_usage: float = None,
                 ram_percentage_change: float = None,
                 reset_counter: bool = False):
        from optimuspy import ExecutionMode

        self.mode = ExecutionMode(mode)
        self.cube_name = cube_name
        self.view_names = view_names
        self.process_name = process_name
        self.dimension_order = dimension_order
        self.query_times_by_view = query_times_by_view
        self.process_times_by_process = process_times_by_process
        self.is_best = False
        if process_name is None:
            self.include_process = False
        else:
            self.include_process = True

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
        view_name = view_name or self.view_names[0]
        median = statistics.median(self.query_times_by_view[view_name])
        if not median:
            raise RuntimeError(f"view '{view_name}' in cube '{self.cube_name}' is too small")

        return median

    def median_process_time(self, process_name: str = None) -> float:
        process_name = process_name or self.process_name
        median = statistics.median(self.process_times_by_process[process_name])
        return median

    def build_header(self) -> list:
        dimensions = []
        for d in range(1, len(self.dimension_order) + 1):
            dimensions.append("Dimension" + str(d))
        header = HEADER + dimensions
        return header

    def build_csv_header(self) -> str:
        return SEPARATOR.join(self.build_header()) + "\n"

    def to_row(self, view_name: str, process_name: str, original_order_result: 'PermutationResult') -> List[str]:
        from optimuspy import LABEL_MAP

        median_query_time = float(self.median_query_time(view_name))
        original_median_query_time = float(original_order_result.median_query_time(view_name))
        query_time_ratio = median_query_time / original_median_query_time - 1
        row = [
            str(self.permutation_id),
            LABEL_MAP[self.mode],
            str(self.is_best),
            median_query_time,
            query_time_ratio]

        if process_name is not None:
            median_process_time = float(self.median_process_time(process_name))
            original_median_process_time = float(original_order_result.median_process_time(process_name))
            process_time_ratio = median_process_time / original_median_process_time - 1
            row += [median_process_time, process_time_ratio]

        else:
            row += [0, 0]

        ram_in_gb = float(self.ram_usage) / (1024 ** 3)
        row += [self.ram_usage, ram_in_gb] + list(self.dimension_order)

        return row

    def to_csv_row(self, view_name: str, process_name: str, original_order_result: 'PermutationResult') -> str:
        row = [str(i) for i in self.to_row(view_name, process_name, original_order_result)]
        return SEPARATOR.join(row) + "\n"


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

    def to_dataframe(self, view_name: str, process_name: str) -> pd.DataFrame:
        header = self.permutation_results[0].build_header()
        rows = []
        for result in self.permutation_results:
            rows.append(result.to_row(view_name, process_name, self.original_order_result))

        return pd.DataFrame(rows, columns=header)

    def to_lines(self, view_name: str, process_name: str) -> List[str]:
        lines = itertools.chain(
            [self.permutation_results[0].build_csv_header()],
            [result.to_csv_row(view_name, process_name, self.original_order_result) for result in
             self.permutation_results])

        return list(lines)

    def to_csv(self, view_name: str, process_name: str, file_name: 'WindowsPath'):
        lines = self.to_lines(view_name, process_name)

        os.makedirs(os.path.dirname(str(file_name)), exist_ok=True)
        with open(str(file_name), "w") as file:
            file.writelines(lines)

    def to_xlsx(self, view_name: str, process_name: str, file_name: 'WindowsPath'):
        try:
            import xlsxwriter

            # Create a workbook and add a worksheet.
            workbook = xlsxwriter.Workbook(file_name)
            worksheet = workbook.add_worksheet()

            # Iterate over the data and write it out row by row.
            for row, line in enumerate(self.to_lines(view_name, process_name)):
                for col, item in enumerate(line.split(SEPARATOR)):
                    worksheet.write(row, col, item)

            workbook.close()

        except ImportError:
            logging.warning("Failed to import xlsxwriter. Writing to csv instead")
            file_name = file_name.with_suffix(".csv")
            return self.to_csv(view_name, process_name, file_name)

    # create scatter plot ram vs. performance
    def to_png(self, view_name: str, process_name: str, file_name: str):
        df = self.to_dataframe(view_name, process_name)

        plt.figure(figsize=(8, 8))
        sns.set_style("ticks")

        p = sns.scatterplot(
            data=df,
            x="RAM in GB",
            y="Query Ratio",
            size="Mean Process Time" if process_name is not None else None,
            hue="Mode",
            palette="viridis",
            edgecolors="black",
            legend=True,
            alpha=0.4,
            sizes=(20, 500) if process_name is not None else None)

        for index, row in df.iterrows():
            p.text(row["RAM in GB"],
                   row["Query Ratio"],
                   row["ID"],
                   color='black')

        sns.despine(trim=True, offset=2)
        p.set_xlabel("RAM (GB)")
        p.set_ylabel("Query Time Compared to Original Order")
        p.legend(title='Legend', loc='best')

        plt.grid()
        plt.tight_layout()

        os.makedirs(os.path.dirname(str(file_name)), exist_ok=True)

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
        for value in (0.01, 0.025, 0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.25):
            ram_threshold = min_ram + value * (max_ram - min_ram)
            query_speed_threshold = min_query_speed + value * (max_query_speed - min_query_speed)
            for permutation_result in self.permutation_results:
                if all([permutation_result.ram_usage <= ram_threshold,
                        permutation_result.median_query_time() <= query_speed_threshold]):
                    return permutation_result

        # no dimension order falls in sweet spot
        return None
