"""The report numbers each order the way the progress log does.

The log says "Iteration 80 was the best one"; the report used to show that order
as #81, because it printed the internal permutation_id, which the original order
takes first. One number per order, everywhere: the original is 0 and the
iterations count from 1.
"""
import json
import re

from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext, OptimusResult, PermutationResult


def _run(rams):
    context = ExecutionContext()
    context.set_initial_ram(rams[0])
    results = [PermutationResult(
        context, ExecutionMode.ORIGINAL_ORDER, "C", [], [], ["A", "B", "C"], {}, None,
        ram_usage=rams[0], ram_percentage_change=None, reorder_duration=0.0)]
    for ram in rams[1:]:
        results.append(PermutationResult(
            context, ExecutionMode.ITERATIONS, "C", [], [], ["B", "A", "C"], {}, None,
            ram_usage=ram, ram_percentage_change=None, reorder_duration=0.0))
    return OptimusResult("C", results)


def test_iteration_number_matches_the_label():
    report = _run([100.0, 90.0, 80.0])
    original, first, second = report.permutation_results
    assert (original.iteration_number, original.label) == (0, "Original Order")
    assert (first.iteration_number, first.label) == (1, "Iteration 1")
    assert (second.iteration_number, second.label) == (2, "Iteration 2")


def test_csv_ids_are_iteration_numbers():
    report = _run([100.0, 90.0, 80.0])
    rows = report.to_lines()[1:]
    assert [row.split(",")[0] for row in rows] == ["0", "1", "2"]


def test_html_ids_are_iteration_numbers(tmp_path):
    report = _run([100.0, 90.0, 80.0])
    path = tmp_path / "report.html"
    report.to_html(path)
    html = path.read_text(encoding="utf-8")

    perms = json.loads(re.search(r"const perms = (\[.*?\]);\n", html).group(1))
    points = json.loads(re.search(r"const data = (\[.*?\]);\n", html).group(1))
    assert [p["id"] for p in perms] == [0, 1, 2]
    assert [p["id"] for p in points] == [0, 1, 2]
    # the best order (Iteration 2) is the one marked best, under the same number
    assert [p["id"] for p in perms if p["isBest"]] == [2]
