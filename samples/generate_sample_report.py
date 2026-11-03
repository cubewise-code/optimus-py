"""Generate a sample HTML report with mock data for previewing the report design."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from results import ExecutionContext, PermutationResult, OptimusResult

CUBE_NAME = "Sales"

# RAM percentage changes are applied cumulatively by ExecutionContext.
# Designed so entry 6 has both lowest RAM and lowest query time → clear winner.
MOCK_DATA = [
    # (mode, dimension_order, query_times_by_view, process_times_by_process,
    #  ram_usage, ram_pct_change, reorder_duration)
    ("original_order",
     ["Time", "Version", "Region", "Product", "Customer", "SalesMeasure"],
     {"Optimus_View1": [2.45, 2.51, 2.48], "Optimus_View2": [1.82, 1.79, 1.85]},
     {"UpdateSales": [3.12, 3.08, 3.15], "CalcMargins": [1.45, 1.42, 1.48]},
     5368709120, None, 0.0),  # 5.0 GB

    ("iterations",
     ["Region", "Time", "Version", "Product", "Customer", "SalesMeasure"],
     {"Optimus_View1": [2.12, 2.18, 2.15], "Optimus_View2": [1.65, 1.62, 1.68]},
     {"UpdateSales": [2.85, 2.82, 2.88], "CalcMargins": [1.35, 1.32, 1.38]},
     None, -4.2, 12.3),

    ("iterations",
     ["Product", "Time", "Version", "Region", "Customer", "SalesMeasure"],
     {"Optimus_View1": [2.31, 2.35, 2.28], "Optimus_View2": [1.75, 1.72, 1.78]},
     {"UpdateSales": [3.25, 3.22, 3.28], "CalcMargins": [1.52, 1.48, 1.55]},
     None, -2.0, 11.8),

    ("iterations",
     ["Customer", "Time", "Version", "Region", "Product", "SalesMeasure"],
     {"Optimus_View1": [2.65, 2.72, 2.68], "Optimus_View2": [1.95, 1.92, 1.98]},
     {"UpdateSales": [3.45, 3.42, 3.48], "CalcMargins": [1.62, 1.58, 1.65]},
     None, 3.0, 13.1),

    ("iterations",
     ["Region", "Product", "Time", "Version", "Customer", "SalesMeasure"],
     {"Optimus_View1": [1.95, 2.02, 1.98], "Optimus_View2": [1.52, 1.48, 1.55]},
     {"UpdateSales": [2.65, 2.62, 2.68], "CalcMargins": [1.22, 1.18, 1.25]},
     None, -8.0, 14.2),

    ("iterations",
     ["Region", "Product", "Customer", "Time", "Version", "SalesMeasure"],
     {"Optimus_View1": [1.88, 1.92, 1.85], "Optimus_View2": [1.42, 1.38, 1.45]},
     {"UpdateSales": [2.55, 2.52, 2.58], "CalcMargins": [1.15, 1.12, 1.18]},
     None, -12.0, 15.5),

    ("iterations",
     ["Region", "Product", "Customer", "Version", "Time", "SalesMeasure"],
     {"Optimus_View1": [2.08, 2.12, 2.05], "Optimus_View2": [1.58, 1.55, 1.62]},
     {"UpdateSales": [2.78, 2.75, 2.82], "CalcMargins": [1.28, 1.25, 1.32]},
     None, 1.0, 12.8),

    ("iterations",
     ["Version", "Region", "Product", "Customer", "Time", "SalesMeasure"],
     {"Optimus_View1": [2.42, 2.48, 2.45], "Optimus_View2": [1.82, 1.78, 1.85]},
     {"UpdateSales": [3.08, 3.05, 3.12], "CalcMargins": [1.42, 1.38, 1.45]},
     None, 5.0, 11.5),

    ("iterations",
     ["Region", "Customer", "Product", "Time", "Version", "SalesMeasure"],
     {"Optimus_View1": [1.92, 1.98, 1.95], "Optimus_View2": [1.48, 1.45, 1.52]},
     {"UpdateSales": [2.72, 2.68, 2.75], "CalcMargins": [1.25, 1.22, 1.28]},
     None, -3.0, 13.9),

    ("iterations",
     ["Time", "Region", "Product", "Customer", "Version", "SalesMeasure"],
     {"Optimus_View1": [2.22, 2.28, 2.25], "Optimus_View2": [1.72, 1.68, 1.75]},
     {"UpdateSales": [2.95, 2.92, 2.98], "CalcMargins": [1.38, 1.35, 1.42]},
     None, -1.5, 12.1),
]

context = ExecutionContext()
results = []

for mode, dim_order, qt_by_view, pt_by_proc, ram, ram_pct, reorder_dur in MOCK_DATA:
    r = PermutationResult(
        context=context,
        mode=mode,
        cube_name=CUBE_NAME,
        view_names=list(qt_by_view.keys()),
        process_names=list(pt_by_proc.keys()),
        dimension_order=dim_order,
        query_times_by_view=qt_by_view,
        process_times_by_process=pt_by_proc,
        ram_usage=ram,
        ram_percentage_change=ram_pct,
        reorder_duration=reorder_dur,
    )
    results.append(r)

optimus_result = OptimusResult(CUBE_NAME, results)

# Verify best result was found
if optimus_result.best_result:
    print(f"Best result: #{optimus_result.best_result.permutation_id} "
          f"- {' > '.join(optimus_result.best_result.dimension_order)}")
else:
    print("WARNING: No best result determined!")

output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "samples", "sample_report.html")
optimus_result.to_html(output_path, total_duration=847.3)

print(f"Sample report generated: {output_path}")
