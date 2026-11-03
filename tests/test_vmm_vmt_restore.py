"""On v11 an optimization raises the cube's VMM/VMT for the run and puts the
originals back at the end. A cube config rejected before the first reorder must
leave them as they were, not stranded at the raised value.

Offline: the VMM/VMT helpers are replaced by a dict that stands in for
}CubeProperties, and the rejections under test fire before any other TM1 call.
"""
import pytest

from optimuspy import core

STORAGE = ["Year", "Region", "Product", "Measure"]
ORIGINAL = ("500", "2000")


@pytest.fixture
def server(monkeypatch, tmp_path):
    """The cube's VMM/VMT as the server holds them."""
    state = {"vmm_vmt": ORIGINAL}

    def _retrieve(tm1, cube_name):
        return state["vmm_vmt"]

    def _write(tm1, cube_name, vmm, vmt):
        state["vmm_vmt"] = (vmm, vmt)

    monkeypatch.setattr(core, "retrieve_vmm_vmt", _retrieve)
    monkeypatch.setattr(core, "write_vmm_vmt", _write)
    monkeypatch.setattr(core, "is_dimension_only_numeric", lambda tm1, dimension_name: True)
    # The checkpoint lookup reads from RESULT_PATH; keep it out of the repo.
    monkeypatch.setattr(core, "RESULT_PATH", tmp_path / "results")
    return state


def _optimize(**kwargs):
    return core._execute_optimize_mode(
        object(), "Sales", "tm1dev", view_names=[], process_names=[], executions=1,
        output="csv", update=False, fast=False, dimensions_to_exclude=[],
        orders_to_ignore=[], initial_dimension_order=STORAGE, is_v12=False, **kwargs)


def test_rejected_position_rules_leave_vmm_vmt_as_they_were(server):
    with pytest.raises(ValueError, match="dimension_position_rules"):
        _optimize(predefined_orders=[],
                  dimension_position_rules=[{"dimension": "Yaer", "position": 0}])

    assert server["vmm_vmt"] == ORIGINAL


def test_rejected_predefined_orders_leave_vmm_vmt_as_they_were(server):
    with pytest.raises(ValueError, match="predefined_orders"):
        _optimize(predefined_orders=[["Year", "Region", "Prodcut", "Measure"]])

    assert server["vmm_vmt"] == ORIGINAL
