"""Crash-and-resume against a real server, both recovery branches.

This is the live counterpart to the offline resume tests. Those prove the
arithmetic — which positions a resumed fold skips, that the recommended order is
unchanged — with no server involved. What they cannot prove is the part that
only a server has: where the cube is actually left when a connection dies
mid-reorder, and whether reading it back tells us the truth.

Two branches, both driven by faulting ``update_storage_dimension_order``:

  NOT LANDED  the reorder raises before it applies, so the cube is still at the
              previous order and the pending order is re-evaluated on resume.
  LANDED      the reorder applies and then the call raises, so the cube sits at
              the pending order and is recovered without re-applying it.

    pytest -m live --instance tm1srv01     # v11
    pytest -m live --instance tm1srv02     # v12

The scenario itself stays in samples/smoke_resume_drop.py, where it can also be
run by hand against an instance that is misbehaving. This module supplies the
fixture cube and lets pytest report the result.
"""
import pytest

from tests.conftest import sample_module

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def smoke():
    return sample_module("smoke_resume_drop")


@pytest.fixture(scope="module")
def parity_fixture(tm1):
    """The 300k-cell skewed cube the scenario runs against.

    Left in place if it was already there — building it takes minutes, and an
    instance kept warm between runs should stay that way. But an existing cube is
    only reused once it has been checked: a run that died partway leaves a cube
    that carries the right name and nothing else guaranteed, and adopting one
    silently is how a broken fixture survives across runs looking healthy. If it
    is not the fixture this module expects, say so rather than testing against it.
    """
    parity = sample_module("validate_v11_v12_parity")
    built_here = not tm1.cubes.exists(parity.CUBE)
    if not built_here:
        found = set(tm1.cubes.get_dimension_names(parity.CUBE))
        expected = set(parity._dimension_names())
        if found != expected:
            pytest.fail(
                f"cube '{parity.CUBE}' already exists on this instance but is not "
                f"the parity fixture: missing {sorted(expected - found)}, extra "
                f"{sorted(found - expected)}. Drop it and re-run; this test will "
                f"not adopt a cube it cannot recognise.",
                pytrace=False)
    try:
        # setup_instance creates the cube, then eight dimensions, then loads
        # 300k cells. A failure anywhere in there must still be torn down —
        # without the try, a half-built fixture never reaches the yield and is
        # left on a shared instance. teardown_instance guards every delete with
        # exists(), so it is safe on a partial build.
        if built_here:
            parity.setup_instance(tm1)
        yield list(tm1.cubes.get_storage_dimension_order(cube_name=parity.CUBE))
    finally:
        if built_here:
            parity.teardown_instance(tm1)


@pytest.mark.parametrize("landed", [False, True], ids=["not_landed", "landed"])
def test_a_dropped_reorder_resumes_and_restores_the_original_order(
        smoke, parity_fixture, live_instance, tm1_config_path, landed):
    # _run_scenario asserts each step: the crash left a checkpoint with pending,
    # the second run resumed rather than starting fresh, the in-flight order was
    # recovered, the checkpoint was removed on completion, and the cube was put
    # back to the order it started in.
    assert smoke._run_scenario(
        f"{'LANDED' if landed else 'NOT-LANDED'} drop",
        live_instance, tm1_config_path, parity_fixture,
        landed=landed, trip_on=4)
