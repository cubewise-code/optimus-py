import base64
import io
import itertools
import json
import logging
import os
import statistics
import time
from pathlib import Path
from typing import List, Union
from optimuspy.execution_mode import ExecutionMode

import pandas as pd

SEPARATOR = ","
HEADER = ["ID", "Mode", "Is Best", "Composite Query Time", "Query Ratio",
          "Composite Process Time", "Process Ratio", "RAM", "RAM in GB", "% Reduction",
          "Reorder Duration"]


class ExecutionContext:
    """Tracks mutable state across permutation evaluations within a single optimization run."""

    def __init__(self):
        self.counter = 1
        self.current_ram = None
        self.original_ram = None
        self.start_time = time.time()

    def next_id(self) -> int:
        pid = self.counter
        self.counter += 1
        return pid

    def reset(self):
        self.counter = 1

    def set_initial_ram(self, ram: float):
        self.original_ram = ram
        self.current_ram = ram

    def update_ram(self, percentage_change: float) -> float:
        self.current_ram = self.current_ram + (self.current_ram * percentage_change / 100)
        return self.current_ram

    def reanchor_ram(self, ram: float) -> float:
        """Re-anchor the %-chain to a fresh absolute reading on resume.

        Moves only current_ram (the chain anchor); original_ram — the baseline
        for ram_reduction — is left untouched, unlike set_initial_ram.
        """
        self.current_ram = ram
        return ram

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time + getattr(self, '_elapsed_offset', 0.0)

    def to_checkpoint_dict(self) -> dict:
        return {
            "counter": self.counter,
            "current_ram": self.current_ram,
            "original_ram": self.original_ram,
            "elapsed_offset": self.elapsed,
        }

    def restore_from_checkpoint(self, data: dict):
        self.counter = data['counter']
        self.current_ram = data['current_ram']
        self.original_ram = data['original_ram']
        self._elapsed_offset = data.get('elapsed_offset', 0.0)
        self.start_time = time.time()


class PermutationResult:

    def __init__(self, context: ExecutionContext, mode: str, cube_name: str, view_names: list,
                 process_names: list, dimension_order: list,
                 query_times_by_view: dict, process_times_by_process: dict, ram_usage: float = None,
                 ram_percentage_change: float = None, reorder_duration: float = 0.0,
                 reanchor: bool = False):

        self.mode = ExecutionMode(mode)
        self.cube_name = cube_name
        self.view_names = view_names
        self.process_names = process_names
        self.dimension_order = dimension_order
        self.query_times_by_view = query_times_by_view
        self.process_times_by_process = process_times_by_process
        self.is_best = False
        self.include_views = bool(view_names)
        self.include_process = bool(process_names)

        # from original dimension order (baseline) or a resume re-anchor
        if ram_usage is not None:
            self.ram_usage = ram_usage
            if reanchor:
                context.reanchor_ram(ram_usage)
            else:
                context.set_initial_ram(ram_usage)
        # from all other dimension orders
        elif ram_percentage_change is not None:
            self.ram_usage = context.update_ram(ram_percentage_change)
        else:
            raise RuntimeError("Either 'ram_usage' or 'ram_percentage_change' must be provided")

        self.ram_percentage_change = ram_percentage_change or 0
        self.ram_reduction = 1 - context.current_ram / context.original_ram
        self.reorder_duration = reorder_duration
        self.permutation_id = context.next_id()

    def median_query_time(self, view_name: str = None) -> float:
        if not self.query_times_by_view:
            return 0.0
        view_name = view_name or self.view_names[0]
        median = statistics.median(self.query_times_by_view[view_name])
        if not median:
            raise RuntimeError(f"view '{view_name}' in cube '{self.cube_name}' is too small")
        return median

    def median_process_time(self, process_name: str = None) -> float:
        process_name = process_name or self.process_names[0]
        return statistics.median(self.process_times_by_process[process_name])

    def composite_query_time(self) -> float:
        """Median of median query times across all views."""
        if not self.query_times_by_view:
            return 0.0
        medians = [statistics.median(times) for times in self.query_times_by_view.values()]
        return statistics.median(medians) if len(medians) > 1 else medians[0]

    def composite_process_time(self) -> float:
        """Median of median process times across all processes."""
        if not self.process_times_by_process:
            return 0.0
        medians = [statistics.median(times) for times in self.process_times_by_process.values()]
        return statistics.median(medians) if len(medians) > 1 else medians[0]

    def build_header(self) -> list:
        dimensions = ["Dimension" + str(d) for d in range(1, len(self.dimension_order) + 1)]
        return HEADER + dimensions

    def build_csv_header(self) -> str:
        return SEPARATOR.join(self.build_header()) + "\n"

    def to_row(self, original_order_result: 'PermutationResult') -> List[str]:
        row = [
            str(self.permutation_id),
            self.mode.label,
            str(self.is_best)]

        if self.include_views:
            composite_qt = self.composite_query_time()
            original_composite_qt = original_order_result.composite_query_time()
            query_time_ratio = composite_qt / original_composite_qt - 1
            row += [composite_qt, query_time_ratio]
        else:
            row += [0, 0]

        if self.include_process:
            composite_pt = self.composite_process_time()
            original_composite_pt = original_order_result.composite_process_time()
            process_time_ratio = composite_pt / original_composite_pt - 1
            row += [composite_pt, process_time_ratio]
        else:
            row += [0, 0]

        ram_in_gb = float(self.ram_usage) / (1024 ** 3)
        row += [self.ram_usage, ram_in_gb, f"{self.ram_reduction:.0%}",
                self.reorder_duration] + list(self.dimension_order)

        return row

    def to_csv_row(self, original_order_result: 'PermutationResult') -> str:
        row = [str(i) for i in self.to_row(original_order_result)]
        return SEPARATOR.join(row) + "\n"

    @classmethod
    def from_checkpoint(cls, data: dict) -> 'PermutationResult':
        """Reconstruct from checkpoint without triggering ExecutionContext side effects."""
        instance = object.__new__(cls)
        instance.mode = ExecutionMode(data['mode'])
        instance.cube_name = data['cube_name']
        instance.view_names = data['view_names']
        instance.process_names = data['process_names']
        instance.dimension_order = data['dimension_order']
        instance.query_times_by_view = {k: list(v) for k, v in data['query_times_by_view'].items()}
        instance.process_times_by_process = (
            {k: list(v) for k, v in data['process_times_by_process'].items()}
            if data.get('process_times_by_process') else {}
        )
        instance.is_best = False
        instance.include_views = bool(data['view_names'])
        instance.include_process = bool(data['process_names'])
        instance.ram_usage = data['ram_usage']
        instance.ram_percentage_change = data['ram_percentage_change']
        instance.ram_reduction = data['ram_reduction']
        instance.reorder_duration = data['reorder_duration']
        instance.permutation_id = data['permutation_id']
        return instance


class OptimusResult:
    TEXT_FONT_SIZE = 5

    def __init__(self, cube_name: str, permutation_results: List[PermutationResult],
                 instance_name: str = None):
        self.cube_name = cube_name
        self.instance_name = instance_name
        self.permutation_results = permutation_results
        if len(permutation_results) == 0:
            raise RuntimeError("Number of permutation results can not be 0")
        self.include_views = permutation_results[0].include_views
        self.include_process = permutation_results[0].include_process

        self.best_result = self.determine_best_result()
        if self.best_result:
            for permutation_result in permutation_results:
                if (permutation_result.permutation_id == self.best_result.permutation_id
                        and permutation_result.mode != ExecutionMode.ORIGINAL_ORDER):
                    permutation_result.is_best = True
                    permutation_result.mode = ExecutionMode.RESULT

    def to_dataframe(self) -> pd.DataFrame:
        header = self.permutation_results[0].build_header()
        rows = [r.to_row(self.original_order_result) for r in self.permutation_results]
        return pd.DataFrame(rows, columns=header)

    def to_lines(self) -> List[str]:
        lines = itertools.chain(
            [self.permutation_results[0].build_csv_header()],
            [r.to_csv_row(self.original_order_result) for r in self.permutation_results])
        return list(lines)

    def _metadata_lines(self) -> List[str]:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        return [
            "# OptimusPy Report\n",
            f"# Instance: {self.instance_name or 'N/A'}\n",
            f"# Cube: {self.cube_name}\n",
            f"# Generated: {timestamp}\n",
            "\n",
        ]

    def to_csv(self, file_name):
        lines = self._metadata_lines() + self.to_lines()
        os.makedirs(os.path.dirname(str(file_name)), exist_ok=True)
        with open(str(file_name), "w", encoding="utf-8") as file:
            file.writelines(lines)

    def to_xlsx(self, file_name):
        try:
            import xlsxwriter

            os.makedirs(os.path.dirname(str(file_name)), exist_ok=True)
            workbook = xlsxwriter.Workbook(str(file_name))
            worksheet = workbook.add_worksheet()

            line_data = []

            header_format = workbook.add_format({'bold': True})
            meta_format = workbook.add_format({'italic': True, 'font_color': '#475569'})
            original_format = workbook.add_format({'bg_color': '#DCE6F1'})
            result_format = workbook.add_format({'bg_color': '#B3FBC1'})
            iteration_format = workbook.add_format({'bg_color': '#FFFFFF'})

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            meta_rows = [
                ("OptimusPy Report", ""),
                ("Instance", self.instance_name or "N/A"),
                ("Cube", self.cube_name),
                ("Generated", timestamp),
            ]
            for r, (label, value) in enumerate(meta_rows):
                worksheet.write(r, 0, label, meta_format)
                worksheet.write(r, 1, value, meta_format)

            header_row = len(meta_rows) + 1  # blank row separator
            for offset, line in enumerate(self.to_lines()):
                row = header_row + offset
                line_data = line.split(SEPARATOR)
                if len(line_data) > 1 and "Original" in line_data[1]:
                    row_format = original_format
                elif len(line_data) > 1 and "Result" in line_data[1]:
                    row_format = result_format
                elif offset == 0:
                    row_format = header_format
                else:
                    row_format = iteration_format

                for col, item in enumerate(line_data):
                    worksheet.write(row, col, item, row_format)

            if line_data:
                worksheet.autofilter(header_row, 0, header_row, len(line_data) - 1)

            workbook.close()

        except ImportError:
            logging.warning("Failed to import xlsxwriter. Writing to csv instead")
            file_name = file_name.with_suffix(".csv")
            return self.to_csv(file_name)

    @staticmethod
    def _load_logo_base64() -> str:
        logo_path = Path(__file__).parent / "images" / "logo.png"
        if not logo_path.exists():
            return ""
        try:
            from PIL import Image
            img = Image.open(logo_path)
            ratio = 300 / img.width
            img = img.resize((300, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
        except ImportError:
            with open(logo_path, "rb") as f:
                return base64.b64encode(f.read()).decode()

    def to_html(self, file_name, total_duration: float = 0.0):
        original = self.original_order_result
        best = self.best_result
        logo_b64 = self._load_logo_base64()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        report_subject = f"{self.instance_name} / {self.cube_name}" if self.instance_name else self.cube_name

        # Summary metrics
        original_ram_gb = original.ram_usage / (1024 ** 3)
        best_ram_gb = best.ram_usage / (1024 ** 3) if best else original_ram_gb
        ram_reduction = best.ram_reduction if best else 0
        orders_tested = len(self.permutation_results)

        if self.include_views:
            original_qt = original.composite_query_time()
            best_qt = best.composite_query_time() if best else original_qt
            query_improvement = 1 - best_qt / original_qt if best and original_qt else 0
        else:
            original_qt = best_qt = query_improvement = 0

        def fmt_duration(seconds):
            if seconds < 60:
                return f"{seconds:.1f}s"
            m, s = divmod(seconds, 60)
            if m < 60:
                return f"{int(m)}m {int(s)}s"
            h, m = divmod(m, 60)
            return f"{int(h)}h {int(m)}m {int(s)}s"

        def fmt_pct(value):
            return f"{value:+.1%}" if value != 0 else "0.0%"

        # Build chart data
        chart_data = []
        original_pt = original.composite_process_time() if self.include_process else 0
        for r in self.permutation_results:
            ram_gb = float(r.ram_usage) / (1024 ** 3)
            if self.include_views:
                y_value = r.composite_query_time() / original_qt - 1 if original_qt else 0
            elif self.include_process:
                y_value = r.composite_process_time() / original_pt - 1 if original_pt else 0
            else:
                y_value = round(r.ram_reduction, 4)
            chart_data.append({
                "id": r.permutation_id,
                "x": round(ram_gb, 4),
                "y": round(y_value, 4),
                "mode": r.mode.label,
                "order": " > ".join(r.dimension_order),
                "processTime": round(r.composite_process_time(), 5) if self.include_process else None,
            })

        # Build permutation data for JavaScript table rendering
        perms_data = []
        for r in self.permutation_results:
            ram_gb = float(r.ram_usage) / (1024 ** 3)
            entry = {
                "id": r.permutation_id,
                "mode": r.mode.label,
                "isBest": r.is_best,
                "dims": list(r.dimension_order),
                "ramGB": round(ram_gb, 10),
                "ramReduction": round(r.ram_reduction, 4),
                "reorderDur": round(r.reorder_duration, 6),
            }
            if self.include_views:
                composite_qt = r.composite_query_time()
                qt_ratio = composite_qt / original_qt - 1 if original_qt else 0
                entry["qt"] = round(composite_qt, 10)
                entry["qtRatio"] = round(qt_ratio, 10)
            if self.include_process:
                composite_pt = r.composite_process_time()
                pt_ratio = composite_pt / original_pt - 1 if original_pt else 0
                entry["pt"] = round(composite_pt, 10)
                entry["ptRatio"] = round(pt_ratio, 10)
            perms_data.append(entry)

        # Query header columns for <thead>
        query_header = ""
        if self.include_views:
            query_header = """
                        <th class="sortable" data-sort="qt">Query Time <span class="sort-arrow"></span></th>
                        <th class="sortable" data-sort="qtRatio">Query Ratio <span class="sort-arrow"></span></th>"""

        # Process header columns for <thead>
        process_header = ""
        if self.include_process:
            process_header = """
                        <th class="sortable" data-sort="pt">Process Time <span class="sort-arrow"></span></th>
                        <th class="sortable" data-sort="ptRatio">Process Ratio <span class="sort-arrow"></span></th>"""

        total_cols = 7 + (2 if self.include_views else 0) + (2 if self.include_process else 0)
        include_views_js = "true" if self.include_views else "false"
        include_process_js = "true" if self.include_process else "false"

        # Query summary cards
        query_cards = ""
        if self.include_views:
            query_cards = f"""
                <div class="card">
                    <div class="card-label">Original Query Time</div>
                    <div class="card-value">{original_qt:.3f}s</div>
                </div>
                <div class="card">
                    <div class="card-label">Best Query Time</div>
                    <div class="card-value">{best_qt:.3f}s</div>
                    <div class="card-sub"><span class="{'negative' if query_improvement > 0 else ''}">{fmt_pct(-query_improvement)} vs original</span></div>
                </div>"""

        # Process summary cards
        process_cards = ""
        if self.include_process and best:
            original_pt = original.composite_process_time()
            best_pt = best.composite_process_time()
            proc_improvement = 1 - best_pt / original_pt if original_pt else 0
            process_cards = f"""
                <div class="card">
                    <div class="card-label">Best Process Time</div>
                    <div class="card-value">{best_pt:.3f}s</div>
                    <div class="card-sub">{fmt_pct(-proc_improvement)} vs original</div>
                </div>"""

        # Best order display
        best_order_html = ""
        if best:
            original_dims = original.dimension_order
            best_dims = best.dimension_order
            arrows = []
            for i, dim in enumerate(best_dims):
                orig_pos = list(original_dims).index(dim)
                if orig_pos < i:
                    cls = "dim-moved-down"
                elif orig_pos > i:
                    cls = "dim-moved-up"
                else:
                    cls = "dim-same"
                arrows.append(f'<span class="dim-tag {cls}">{dim}</span>')
            best_order_html = f"""
            <div class="panel">
                <h2>Recommended Dimension Order</h2>
                <div class="dim-order">
                    {"".join(arrows)}
                </div>
                <div class="dim-legend">
                    <span class="dim-tag dim-moved-up">Moved up</span>
                    <span class="dim-tag dim-moved-down">Moved down</span>
                    <span class="dim-tag dim-same">Unchanged</span>
                </div>
            </div>"""

        logo_html = ""
        if logo_b64:
            logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="OptimusPy" class="logo">'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OptimusPy Report — {report_subject}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: #F8FAFC;
        color: #1E293B;
        line-height: 1.5;
    }}
    .container {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    .header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid #E2E8F0;
    }}
    .header-left {{ display: flex; align-items: center; gap: 16px; }}
    .logo {{ height: 48px; width: auto; }}
    .header h1 {{ font-size: 20px; font-weight: 600; color: #0F172A; }}
    .header-meta {{ font-size: 13px; color: #64748B; text-align: right; }}
    .cards {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }}
    .card {{
        background: #fff;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .card-label {{ font-size: 12px; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 500; }}
    .card-value {{ font-size: 24px; font-weight: 700; color: #0F172A; font-family: 'SF Mono', 'Fira Code', monospace; margin: 4px 0; }}
    .card-sub {{ font-size: 12px; color: #64748B; }}
    .card-sub .positive {{ color: #DC2626; }}
    .card-sub .negative {{ color: #16A34A; }}
    .panel {{
        background: #fff;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .panel h2 {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #0F172A; }}
    .chart-container {{ position: relative; height: 400px; }}
    .dim-order {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }}
    .dim-tag {{
        display: inline-block;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
    }}
    .dim-moved-up {{ background: #DBEAFE; color: #1E40AF; }}
    .dim-moved-down {{ background: #FEF3C7; color: #92400E; }}
    .dim-same {{ background: #F1F5F9; color: #475569; }}
    .dim-legend {{ display: flex; gap: 12px; font-size: 12px; color: #64748B; }}
    .dim-legend .dim-tag {{ padding: 2px 8px; font-size: 11px; }}
    .positive {{ color: #DC2626; }}
    .negative {{ color: #16A34A; }}
    .footer {{ text-align: center; padding: 24px 0; font-size: 12px; color: #94A3B8; }}
    .podium {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
    .podium-card {{
        flex: 1; min-width: 200px; background: #F8FAFC; border: 1px solid #E2E8F0;
        border-radius: 10px; padding: 14px 16px; cursor: pointer; transition: all 0.15s ease;
    }}
    .podium-card:hover {{ border-color: #94A3B8; box-shadow: 0 2px 6px rgba(0,0,0,0.06); }}
    .podium-card.highlight {{ border-color: #2563EB; background: #EFF6FF; }}
    .podium-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }}
    .podium-query .podium-title {{ color: #1E40AF; }}
    .podium-process .podium-title {{ color: #92400E; }}
    .podium-ram .podium-title {{ color: #3730A3; }}
    .podium-best .podium-title {{ color: #166534; }}
    .podium-id {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 20px; font-weight: 700; color: #0F172A; }}
    .podium-detail {{ font-size: 12px; color: #64748B; margin-top: 2px; font-family: 'SF Mono', 'Fira Code', monospace; }}
    .podium-dims {{ display: flex; gap: 3px; flex-wrap: wrap; margin-top: 8px; }}
    .podium-dim {{ padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 500; background: #E2E8F0; color: #475569; }}
    .table-scroll {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{
        background: #F8FAFC; border-bottom: 2px solid #E2E8F0; padding: 10px 12px;
        text-align: left; font-weight: 600; color: #475569; font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.03em; position: sticky; top: 0; z-index: 2;
    }}
    th.sortable {{ cursor: pointer; user-select: none; }}
    th.sortable:hover {{ color: #0F172A; }}
    th.sorted {{ color: #0F172A; }}
    th .sort-arrow {{ font-size: 10px; margin-left: 3px; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #F1F5F9; }}
    .num {{ font-family: 'SF Mono', 'Fira Code', monospace; text-align: right; }}
    tr.data-row {{ cursor: pointer; transition: background 0.1s ease; }}
    tr.data-row:hover {{ background: #F8FAFC; }}
    tr.row-original {{ background: #EFF6FF; }}
    tr.row-original:hover {{ background: #DBEAFE; }}
    tr.row-best {{ background: #F0FDF4; }}
    tr.row-best:hover {{ background: #DCFCE7; }}
    tr.row-highlight {{ outline: 2px solid #2563EB; outline-offset: -2px; }}
    .expand-icon {{
        display: inline-block; width: 18px; height: 18px; line-height: 18px;
        text-align: center; border-radius: 4px; background: #F1F5F9;
        color: #64748B; font-size: 12px; font-weight: 700;
        transition: all 0.15s ease; flex-shrink: 0;
    }}
    tr.open .expand-icon {{ background: #0F172A; color: #fff; transform: rotate(90deg); }}
    .badge {{
        display: inline-block; padding: 2px 7px; border-radius: 5px;
        font-size: 10px; font-weight: 700; letter-spacing: 0.02em;
        white-space: nowrap; margin-right: 3px;
    }}
    .badge-original {{ background: #DBEAFE; color: #1E40AF; }}
    .badge-best {{ background: #DCFCE7; color: #166534; }}
    .badge-iteration {{ background: #F1F5F9; color: #475569; }}
    .badge-rank {{ background: #FEF3C7; color: #92400E; }}
    tr.detail-row {{ display: none; }}
    tr.detail-row.visible {{ display: table-row; }}
    tr.detail-row > td {{ padding: 0; border-bottom: 2px solid #E2E8F0; background: #FAFBFC; }}
    .detail-panel {{ padding: 16px 20px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}
    @media (max-width: 900px) {{ .detail-panel {{ grid-template-columns: 1fr; }} }}
    .detail-block h4 {{
        font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase;
        letter-spacing: 0.06em; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid #E2E8F0;
    }}
    .mini-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    .mini-table th {{ position: static; background: transparent; border-bottom: 1px solid #E2E8F0; padding: 4px 6px; font-size: 10px; color: #94A3B8; }}
    .mini-table td {{ padding: 4px 6px; border-bottom: 1px solid #F1F5F9; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; }}
    .mini-table td.label-cell {{ font-family: 'Inter', sans-serif; color: #475569; font-weight: 500; }}
    .dim-flow {{ display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }}
    .dim-flow .df-chip {{ padding: 3px 8px; border-radius: 5px; font-size: 11px; font-weight: 500; background: #F1F5F9; color: #475569; }}
    .dim-flow .df-chip.up {{ background: #DBEAFE; color: #1E40AF; }}
    .dim-flow .df-chip.down {{ background: #FEF3C7; color: #92400E; }}
    .dim-flow .df-arrow {{ color: #CBD5E1; font-size: 10px; }}
    .stat-row {{ display: flex; justify-content: space-between; padding: 3px 0; font-size: 12px; }}
    .stat-row .stat-label {{ color: #64748B; }}
    .stat-row .stat-val {{ font-family: 'SF Mono', 'Fira Code', monospace; font-weight: 600; }}
    .dim-up-text {{ color: #1E40AF; }}
    .dim-down-text {{ color: #92400E; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div class="header-left">
            {logo_html}
            <h1>Optimization Report — {report_subject}</h1>
        </div>
        <div class="header-meta">
            Generated {timestamp}
        </div>
    </div>

    <div class="cards">
        <div class="card">
            <div class="card-label">Orders Tested</div>
            <div class="card-value">{orders_tested}</div>
        </div>
        <div class="card">
            <div class="card-label">Original RAM</div>
            <div class="card-value">{original_ram_gb:.2f} GB</div>
        </div>
        <div class="card">
            <div class="card-label">Best RAM</div>
            <div class="card-value">{best_ram_gb:.2f} GB</div>
            <div class="card-sub"><span class="{'negative' if ram_reduction > 0 else ''}">{f'{ram_reduction:.0%}'} reduction</span></div>
        </div>
        {query_cards}
        {process_cards}
        <div class="card">
            <div class="card-label">Total Duration</div>
            <div class="card-value" style="font-size:18px">{fmt_duration(total_duration)}</div>
        </div>
    </div>

    {best_order_html}

    <div class="panel">
        <h2>{"RAM vs Query Performance" if self.include_views else "RAM vs Process Performance" if self.include_process else "RAM Usage Comparison"}</h2>
        <div class="chart-container">
            <canvas id="scatterChart"></canvas>
        </div>
    </div>

    <div class="panel">
        <h2>All Permutation Results</h2>
        <div class="podium" id="podium"></div>
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th style="width:30px"></th>
                        <th class="sortable" data-sort="id" style="width:40px">ID <span class="sort-arrow">&#9650;</span></th>
                        <th style="width:100px">Mode</th>
                        {query_header}
                        {process_header}
                        <th class="sortable" data-sort="ramGB">RAM <span class="sort-arrow"></span></th>
                        <th class="sortable" data-sort="ramReduction">Reduction <span class="sort-arrow"></span></th>
                        <th>Reorder</th>
                        <th>Dimensions</th>
                    </tr>
                </thead>
                <tbody id="tbody"></tbody>
            </table>
        </div>
    </div>

    <div class="footer">
        OptimusPy v2.0 — TM1 Cube Dimension Order Optimizer
    </div>
</div>

<script>
const data = {json.dumps(chart_data)};

const colorMap = {{
    'Original Order': {{ bg: 'rgba(59,130,246,0.7)', border: '#2563EB' }},
    'Result':         {{ bg: 'rgba(34,197,94,0.7)',  border: '#16A34A' }},
    'Iterations':     {{ bg: 'rgba(148,163,184,0.5)', border: '#64748B' }},
}};

const datasets = {{}};
data.forEach(d => {{
    if (!datasets[d.mode]) {{
        const c = colorMap[d.mode] || {{ bg: 'rgba(148,163,184,0.5)', border: '#64748B' }};
        datasets[d.mode] = {{
            label: d.mode,
            data: [],
            backgroundColor: c.bg,
            borderColor: c.border,
            borderWidth: 1.5,
            pointRadius: d.mode === 'Iterations' ? 5 : 8,
            pointHoverRadius: 10,
        }};
    }}
    datasets[d.mode].data.push({{ x: d.x, y: d.y, id: d.id, order: d.order }});
}});

new Chart(document.getElementById('scatterChart'), {{
    type: 'scatter',
    data: {{ datasets: Object.values(datasets) }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            tooltip: {{
                callbacks: {{
                    label: ctx => {{
                        const pt = ctx.raw;
                        return [
                            `#${{pt.id}} — ${{ctx.dataset.label}}`,
                            `RAM: ${{pt.x.toFixed(2)}} GB`,
                            `Query Ratio: ${{(pt.y * 100).toFixed(1)}}%`,
                            pt.order
                        ];
                    }}
                }}
            }},
            legend: {{ position: 'top' }}
        }},
        scales: {{
            x: {{ title: {{ display: true, text: 'RAM (GB)' }} }},
            y: {{
                title: {{ display: true, text: '{"Query Time vs Original" if self.include_views else "Process Time vs Original" if self.include_process else "RAM Reduction"}' }},
                ticks: {{ callback: v => (v * 100).toFixed(0) + '%' }}
            }}
        }}
    }}
}});
</script>

<script>
const includeViews = {include_views_js};
const includeProcess = {include_process_js};
const totalCols = {total_cols};
const originalOrder = {json.dumps(list(original.dimension_order))};
const perms = {json.dumps(perms_data)};

const iterations = perms.filter(p => p.mode !== 'Original Order');
const bestQuery = includeViews && iterations.length ? [...iterations].sort((a,b) => a.qt - b.qt)[0] : null;
const bestProcess = includeProcess && iterations.length ? [...iterations].sort((a,b) => a.pt - b.pt)[0] : null;
const bestRam = iterations.length ? [...iterations].sort((a,b) => a.ramGB - b.ramGB)[0] : null;
const bestOverall = perms.find(p => p.isBest);

iterations.forEach(p => {{
    if (includeViews) p.queryRank = [...iterations].sort((a,b) => a.qt - b.qt).findIndex(x => x.id === p.id) + 1;
    if (includeProcess) p.processRank = [...iterations].sort((a,b) => a.pt - b.pt).findIndex(x => x.id === p.id) + 1;
}});

function shortDims(dims) {{ return dims.map(d => `<span class="podium-dim">${{d}}</span>`).join(''); }}
function formatPct(v) {{ return (v > 0 ? '+' : '') + (v * 100).toFixed(1) + '%'; }}
function pctClass(v) {{ return v > 0 ? 'positive' : v < 0 ? 'negative' : ''; }}

if (bestOverall) {{
    let bestDetail = [];
    if (includeViews) bestDetail.push(bestOverall.qt.toFixed(4) + 's');
    if (includeProcess) bestDetail.push(bestOverall.pt.toFixed(2) + 's');
    bestDetail.push((bestOverall.ramGB * 1024).toFixed(1) + 'MB');
    let podiumHtml = `
        <div class="podium-card podium-best" data-highlight="${{bestOverall.id}}">
            <div class="podium-title">Best Overall</div>
            <div class="podium-id">#${{bestOverall.id}}</div>
            <div class="podium-detail">${{bestDetail.join(' &middot; ')}}</div>
            <div class="podium-dims">${{shortDims(bestOverall.dims)}}</div>
        </div>`;
    if (includeViews && bestQuery) {{
        podiumHtml += `
        <div class="podium-card podium-query" data-highlight="${{bestQuery.id}}">
            <div class="podium-title">#1 Fastest Query</div>
            <div class="podium-id">#${{bestQuery.id}}</div>
            <div class="podium-detail">${{bestQuery.qt.toFixed(5)}}s (${{formatPct(bestQuery.qtRatio)}})</div>
            <div class="podium-dims">${{shortDims(bestQuery.dims)}}</div>
        </div>`;
    }}
    if (includeProcess && bestProcess) {{
        podiumHtml += `
        <div class="podium-card podium-process" data-highlight="${{bestProcess.id}}">
            <div class="podium-title">#1 Fastest Process</div>
            <div class="podium-id">#${{bestProcess.id}}</div>
            <div class="podium-detail">${{bestProcess.pt.toFixed(3)}}s (${{formatPct(bestProcess.ptRatio)}})</div>
            <div class="podium-dims">${{shortDims(bestProcess.dims)}}</div>
        </div>`;
    }}
    podiumHtml += `
        <div class="podium-card podium-ram" data-highlight="${{bestRam.id}}">
            <div class="podium-title">#1 Lowest RAM</div>
            <div class="podium-id">#${{bestRam.id}}</div>
            <div class="podium-detail">${{(bestRam.ramGB * 1024).toFixed(2)}}MB (${{(bestRam.ramReduction * 100).toFixed(0)}}% reduction)</div>
            <div class="podium-dims">${{shortDims(bestRam.dims)}}</div>
        </div>`;
    document.getElementById('podium').innerHTML = podiumHtml;
}}

document.querySelectorAll('.podium-card').forEach(card => {{
    card.addEventListener('click', () => {{
        document.querySelectorAll('.podium-card').forEach(c => c.classList.remove('highlight'));
        card.classList.add('highlight');
        document.querySelectorAll('tr.row-highlight').forEach(r => r.classList.remove('row-highlight'));
        const row = document.querySelector(`tr[data-id="${{card.dataset.highlight}}"]`);
        if (row) {{ row.classList.add('row-highlight'); row.scrollIntoView({{ behavior: 'smooth', block: 'center' }}); }}
    }});
}});

const tbody = document.getElementById('tbody');
let sortCol = 'id', sortAsc = true;

function renderTable() {{
    const sorted = [...perms].sort((a, b) => {{
        let va = a[sortCol], vb = b[sortCol];
        if (sortCol === 'ramReduction') {{ va = -a.ramReduction; vb = -b.ramReduction; }}
        return sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    }});

    tbody.innerHTML = sorted.map(p => {{
        const isOriginal = p.mode === 'Original Order';
        const isBest = p.isBest;
        const rowClass = isBest ? 'row-best' : isOriginal ? 'row-original' : '';
        const modeBadge = isBest ? '<span class="badge badge-best">Best</span>'
            : isOriginal ? '<span class="badge badge-original">Original</span>'
            : '<span class="badge badge-iteration">Iteration</span>';
        let rankBadges = '';
        if (!isOriginal) {{
            if (bestQuery && p.id === bestQuery.id) rankBadges += '<span class="badge badge-rank">#1Q</span>';
            if (includeProcess && bestProcess && p.id === bestProcess.id) rankBadges += '<span class="badge badge-rank">#1P</span>';
        }}
        const dimCompact = p.dims.join(' > ');

        const dimFlow = p.dims.map((d, i) => {{
            const origIdx = originalOrder.indexOf(d);
            const cls = i < origIdx ? 'up' : i > origIdx ? 'down' : '';
            return `<span class="df-chip ${{cls}}">${{d}}</span>`;
        }}).join('<span class="df-arrow">&#9654;</span>');

        const dimTable = p.dims.map((d, i) => {{
            const oi = originalOrder.indexOf(d);
            const diff = oi - i;
            const mv = diff > 0 ? `<span class="dim-up-text">&uarr;${{diff}}</span>` : diff < 0 ? `<span class="dim-down-text">&darr;${{Math.abs(diff)}}</span>` : '&mdash;';
            return `<tr><td>${{i + 1}}</td><td class="label-cell">${{d}}</td><td>${{oi + 1}}</td><td>${{mv}}</td></tr>`;
        }}).join('');

        let queryCells = '';
        let queryStats = '';
        if (includeViews) {{
            queryCells = `
                <td class="num">${{p.qt.toFixed(5)}}</td>
                <td class="num ${{pctClass(p.qtRatio)}}">${{formatPct(p.qtRatio)}}</td>`;
            queryStats = `
                <div class="stat-row"><span class="stat-label">Query Time</span><span class="stat-val">${{p.qt.toFixed(5)}}s</span></div>
                <div class="stat-row"><span class="stat-label">vs Original</span><span class="stat-val ${{pctClass(p.qtRatio)}}">${{formatPct(p.qtRatio)}}</span></div>`;
        }}

        let processCells = '';
        let processStats = '';
        if (includeProcess) {{
            processCells = `
                <td class="num">${{p.pt.toFixed(3)}}</td>
                <td class="num ${{pctClass(p.ptRatio)}}">${{formatPct(p.ptRatio)}}</td>`;
            processStats = `
                <div class="stat-row"><span class="stat-label">Process Time</span><span class="stat-val">${{p.pt.toFixed(3)}}s</span></div>
                <div class="stat-row"><span class="stat-label">vs Original</span><span class="stat-val ${{pctClass(p.ptRatio)}}">${{formatPct(p.ptRatio)}}</span></div>`;
        }}

        let rankStats = '';
        if (!isOriginal) {{
            if (includeViews && p.queryRank) {{
                rankStats += `<div class="stat-row" style="margin-top:8px;padding-top:8px;border-top:1px solid #E2E8F0"><span class="stat-label">Query Rank</span><span class="stat-val">#${{p.queryRank}} of ${{iterations.length}}</span></div>`;
            }}
            if (includeProcess && p.processRank) {{
                rankStats += `<div class="stat-row" style="${{!includeViews ? 'margin-top:8px;padding-top:8px;border-top:1px solid #E2E8F0' : ''}}"><span class="stat-label">Process Rank</span><span class="stat-val">#${{p.processRank}} of ${{iterations.length}}</span></div>`;
            }}
        }}

        return `
        <tr class="data-row ${{rowClass}}" data-id="${{p.id}}" onclick="toggleDetail(this)">
            <td><span class="expand-icon">&#9654;</span></td>
            <td class="num">${{p.id}}</td>
            <td>${{modeBadge}} ${{rankBadges}}</td>
            ${{queryCells}}
            ${{processCells}}
            <td class="num">${{(p.ramGB * 1024).toFixed(2)}} MB</td>
            <td class="num ${{p.ramReduction > 0 ? 'negative' : ''}}">${{(p.ramReduction * 100).toFixed(0)}}%</td>
            <td class="num">${{p.reorderDur.toFixed(3)}}s</td>
            <td style="font-size:11px;color:#64748B;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${{dimCompact}}">${{dimCompact}}</td>
        </tr>
        <tr class="detail-row">
            <td colspan="${{totalCols}}">
                <div class="detail-panel">
                    <div class="detail-block">
                        <h4>Dimension Order</h4>
                        <div class="dim-flow">${{dimFlow}}</div>
                        <table class="mini-table" style="margin-top:10px">
                            <thead><tr><th>Pos</th><th>Dimension</th><th>Orig</th><th>Moved</th></tr></thead>
                            <tbody>${{dimTable}}</tbody>
                        </table>
                    </div>
                    <div class="detail-block">
                        <h4>Performance Summary</h4>
                        ${{queryStats}}
                        ${{processStats}}
                        <div class="stat-row" style="margin-top:8px;padding-top:8px;border-top:1px solid #E2E8F0"><span class="stat-label">RAM Usage</span><span class="stat-val">${{(p.ramGB * 1024).toFixed(2)}} MB</span></div>
                        <div class="stat-row"><span class="stat-label">RAM Reduction</span><span class="stat-val ${{p.ramReduction > 0 ? 'negative' : ''}}">${{(p.ramReduction * 100).toFixed(0)}}%</span></div>
                        ${{rankStats}}
                    </div>
                    <div class="detail-block">
                        <h4>Reorder Info</h4>
                        <div class="stat-row"><span class="stat-label">Reorder Duration</span><span class="stat-val">${{p.reorderDur.toFixed(3)}}s</span></div>
                        <div class="stat-row"><span class="stat-label">RAM % Change</span><span class="stat-val">${{(p.ramReduction * 100).toFixed(0)}}%</span></div>
                    </div>
                </div>
            </td>
        </tr>`;
    }}).join('');
}}

function toggleDetail(row) {{
    row.classList.toggle('open');
    const detail = row.nextElementSibling;
    if (detail && detail.classList.contains('detail-row')) detail.classList.toggle('visible');
}}

document.querySelectorAll('th.sortable').forEach(th => {{
    th.addEventListener('click', () => {{
        const col = th.dataset.sort;
        if (sortCol === col) sortAsc = !sortAsc;
        else {{ sortCol = col; sortAsc = true; }}
        document.querySelectorAll('th.sortable').forEach(t => {{
            t.classList.remove('sorted');
            t.querySelector('.sort-arrow').textContent = '';
        }});
        th.classList.add('sorted');
        th.querySelector('.sort-arrow').textContent = sortAsc ? '\u25B2' : '\u25BC';
        renderTable();
    }});
}});

renderTable();
</script>
</body>
</html>"""

        os.makedirs(os.path.dirname(str(file_name)), exist_ok=True)
        with open(str(file_name), "w", encoding="utf-8") as f:
            f.write(html)

    @property
    def original_order_result(self) -> PermutationResult:
        for result in self.permutation_results:
            if result.mode == ExecutionMode.ORIGINAL_ORDER:
                return result

    def determine_best_result(self) -> Union[PermutationResult, None]:
        ram_range = [r.ram_usage for r in self.permutation_results]
        min_ram, max_ram = min(ram_range), max(ram_range)

        if self.include_views:
            query_range = [r.composite_query_time() for r in self.permutation_results]
            min_query, max_query = min(query_range), max(query_range)

        if self.include_process:
            process_range = [r.composite_process_time() for r in self.permutation_results]
            min_process, max_process = min(process_range), max(process_range)

        # find a good balance between speed and ram and process speed
        for value in (0.01, 0.025, 0.05):
            ram_threshold = min_ram + value * (max_ram - min_ram)

            for r in self.permutation_results:
                if r.ram_usage > ram_threshold:
                    continue
                if self.include_views:
                    query_threshold = min_query + value * (max_query - min_query)
                    if r.composite_query_time() > query_threshold:
                        continue
                if self.include_process:
                    process_threshold = min_process + value * (max_process - min_process)
                    if r.composite_process_time() > process_threshold:
                        continue
                return r

        # no dimension order falls in sweet spot
        return None
