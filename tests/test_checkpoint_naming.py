"""A checkpoint is named like its run's report: instance, cube and run stamp.

The instance keeps two servers that share a cube name apart. Before, both wrote
results/checkpoint_<cube>.json, and a run on one instance read the other's,
rejected it as belonging to another instance, and deleted it.
"""
import json

from optimuspy.checkpoint import CheckpointManager


def _manager(tmp_path, instance="inst", cube="C", stamp="2026-10-13_16-10-46"):
    return CheckpointManager(cube, instance, "fp", result_path=tmp_path, run_stamp=stamp)


def _write(mgr):
    mgr.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    mgr.checkpoint_path.write_text(json.dumps({"run_stamp": mgr.run_stamp}))


def test_the_checkpoint_sits_beside_the_report_and_is_named_like_it(tmp_path):
    mgr = _manager(tmp_path, instance="Benelux_Site", cube="SITE.2150.Total_SITE_COMM")
    assert mgr.checkpoint_path == (
        tmp_path / "Benelux_Site"
        / "checkpoint_Benelux_Site_SITE.2150.Total_SITE_COMM_2026-10-13_16-10-46.json")


def test_two_instances_with_the_same_cube_never_see_each_others_checkpoint(tmp_path):
    _write(_manager(tmp_path, instance="Benelux_Site", cube="SITE.2150"))
    assert not _manager(tmp_path, instance="WestBalkans_Site", cube="SITE.2150").exists()


def test_a_cube_does_not_claim_the_checkpoint_of_a_cube_whose_name_it_starts(tmp_path):
    _write(_manager(tmp_path, cube="Sales_Plan"))
    assert not _manager(tmp_path, cube="Sales").exists()


def test_a_later_run_finds_the_checkpoint_and_takes_its_stamp(tmp_path):
    first = _manager(tmp_path, stamp="2026-10-13_16-10-46")
    _write(first)

    resumed = _manager(tmp_path, stamp="2026-10-14_09-00-00")
    assert resumed.exists()
    assert resumed.run_stamp == "2026-10-13_16-10-46"
    assert resumed.checkpoint_path == first.checkpoint_path


def test_the_newest_of_several_checkpoints_is_the_one_found(tmp_path):
    for stamp in ("2026-10-12_08-00-00", "2026-10-13_16-10-46"):
        _write(_manager(tmp_path, stamp=stamp))
    mgr = _manager(tmp_path, stamp="2026-10-14_09-00-00")
    assert mgr.exists()
    assert mgr.run_stamp == "2026-10-13_16-10-46"


def test_discard_deletes_the_found_checkpoint_and_returns_to_this_runs_stamp(tmp_path):
    old = _manager(tmp_path, stamp="2026-10-13_16-10-46")
    _write(old)

    mgr = _manager(tmp_path, stamp="2026-10-14_09-00-00")
    assert mgr.exists()
    mgr.discard()

    assert not old.checkpoint_path.exists()
    assert mgr.run_stamp == "2026-10-14_09-00-00"
    assert not mgr.exists()


def test_save_writes_the_run_stamp_into_the_checkpoint(tmp_path):
    from tests.test_checkpoint_v3 import DIMS, _save
    mgr = _manager(tmp_path)
    _save(mgr, DIMS)
    data = json.loads(mgr.checkpoint_path.read_text())
    assert data["run_stamp"] == "2026-10-13_16-10-46"
    assert data["instance"] == "inst"
