"""The results table and the podium cards present numbers consistently (#129).

A numeric column's header sits over its right-aligned numbers, and the cards
print each figure the way the table does, so "Best Overall" and "#1 Lowest RAM"
can be compared at a glance.
"""
import re

from optimuspy.execution_mode import ExecutionMode
from optimuspy.results import ExecutionContext, OptimusResult, PermutationResult


def _html(tmp_path, with_views):
    context = ExecutionContext()
    context.set_initial_ram(100.0)
    views = ["V"] if with_views else []
    results = [PermutationResult(
        context, ExecutionMode.ORIGINAL_ORDER, "C", views, [], ["A", "B"],
        {"V": [1.0]} if with_views else {}, None,
        ram_usage=100.0, ram_percentage_change=None, reorder_duration=0.0)]
    for pct in (-10.0, -5.0):
        results.append(PermutationResult(
            context, ExecutionMode.ITERATIONS, "C", views, [], ["B", "A"],
            {"V": [0.5]} if with_views else {}, None,
            ram_usage=None, ram_percentage_change=pct, reorder_duration=1.0))
    path = tmp_path / "report.html"
    OptimusResult("C", results).to_html(path)
    return path.read_text(encoding="utf-8")


def _headers(html):
    thead = re.search(r'<table class="results">\s*<thead>(.*?)</thead>', html, re.S).group(1)
    return [(re.sub(r"<.*?>|&#\d+;", "", inner).strip(), attrs)
            for attrs, inner in re.findall(r"<th([^>]*)>(.*?)</th>", thead, re.S)]


def test_numeric_headers_are_aligned_with_their_numbers(tmp_path):
    numeric = {"ID", "Query Time", "Query Ratio", "RAM", "Reduction", "Reorder"}
    headers = _headers(_html(tmp_path, with_views=True))
    assert numeric <= {name for name, _ in headers}
    for name, attrs in headers:
        is_num = re.search(r'class="[^"]*\bnum\b', attrs) is not None
        assert is_num == (name in numeric), name


def test_the_cards_print_ram_with_one_format(tmp_path):
    html = _html(tmp_path, with_views=False)
    assert "bestDetail.push(formatRam(bestOverall))" in html
    assert "${formatRam(bestRam)}" in html
    # no card builds its own RAM string any more
    assert not re.search(r"podium-detail[^\n]*ramGB", html)
