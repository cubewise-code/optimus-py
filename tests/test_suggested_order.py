"""The Suggested Order on the UI's Overview tab: a leaf-count guess, never measured.

It may only suggest an order TM1 would accept. A dimension with string elements
stays last when it is already the cube's last dimension, and otherwise can go
anywhere except last, because TM1 refuses to move one into the last slot (#141).
"""
from optimuspy.core import _compute_suggested_order


def meta(name, leaves, strings=False):
    return {"name": name, "leaf_elements": leaves, "has_strings": strings,
            "string_elements": 1 if strings else 0}


def test_a_string_dimension_already_last_stays_last():
    dims = [meta("Year", 5), meta("Product", 900), meta("Measure", 12, strings=True)]
    result = _compute_suggested_order(dims, storage_order=["Year", "Product", "Measure"])
    assert result["order"] == ["Year", "Product", "Measure"]
    assert any("Measure" in n and "stays last" in n for n in result["notes"])


def test_string_dimensions_that_are_not_last_never_go_last():
    # The Revenue cube from #141, whose Suggested Order put Version last.
    dims = [meta("organization", 10), meta("Channel", 3), meta("product", 21),
            meta("Month", 15, strings=True), meta("Year", 5),
            meta("Version", 20, strings=True), meta("Revenue", 6)]
    storage = ["organization", "Channel", "product", "Month", "Year", "Version", "Revenue"]
    result = _compute_suggested_order(dims, storage_order=storage)
    order = result["order"]
    assert order[-1] == "product"  # the largest dimension that may go last
    assert order[:-1] == ["Channel", "Year", "Revenue", "organization", "Month", "Version"]
    assert any("Month, Version" in n and "can't go last" in n for n in result["notes"])
