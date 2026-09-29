"""The cross-version gate: v11 and v12 must agree, mode for mode.

Builds a byte-identical 8-dimension cube with the same seeded data on both
instances, runs every OptimusPy mode against each, and compares the winning
storage order each mode picked. Identical data on identical dimensions must
produce an identical winner; a divergence means a version difference has reached
the search, not the server.

It also proves the Unit->bytes conversion end to end: the original-order RAM
both runs measured must agree within tolerance. v11 reports B and v12 reports
KB, so a conversion error shows up as a factor of about 1024 rather than as
anything subtle.

Needs BOTH instances, and takes minutes:

    pytest -m live --v11 tm1srv01 --v12 tm1srv02

Run it before a merge that touches the search, the metrics read or the executors.
"""
import pytest

from tests.conftest import sample_module

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def instances(request):
    v11 = request.config.getoption("--v11")
    v12 = request.config.getoption("--v12")
    if not (v11 and v12):
        pytest.skip("the parity gate needs both --v11 and --v12")
    return v11, v12


@pytest.fixture(scope="module")
def snapshots(instances, tm1_config_path):
    """Build and run both instances, and tear both down whatever happens.

    The setup calls belong INSIDE the try. A v12 setup that fails after v11 has
    already built its cube would otherwise leave that cube on a shared instance —
    the failure mode that actually costs someone something here. teardown_instance
    guards every delete with exists(), so it is safe on an instance that was never
    built.
    """
    parity = sample_module("validate_v11_v12_parity")
    v11_name, v12_name = instances
    try:
        snapshot = {
            "v11": parity.process_instance(v11_name, tm1_config_path, None, do_setup=True),
            "v12": parity.process_instance(v12_name, tm1_config_path, None, do_setup=True),
        }
        # Any mode whose two winners differ gets the missing measurement taken
        # now, while both fixtures are still up. A search only evaluates orders
        # on its own path, so without this a disagreement cannot be told apart
        # from two orders that cost the same — and the gate fails on the latter.
        parity.resolve_disputed_winners(snapshot, tm1_config_path, v11_name, v12_name)
        yield parity, snapshot
    finally:
        # One instance failing to clean up must not skip the other, and a
        # leftover fixture cube is itself a reportable failure — not a warning
        # swallowed by a passing test.
        left_behind = []
        for name in (v11_name, v12_name):
            try:
                _teardown(parity, tm1_config_path, name)
            except Exception as exc:                      # noqa: BLE001
                left_behind.append(f"{name}: {exc}")
        if left_behind:
            pytest.fail("parity fixture cube may be left behind on "
                        + "; ".join(left_behind))


def test_both_versions_pick_the_same_winner_in_every_mode(snapshots):
    parity, snapshot = snapshots
    # compare() prints a per-mode table and returns the verdict; the printed
    # detail is what makes a failure actionable, so it is not re-derived here.
    assert parity.compare(snapshot["v11"], snapshot["v12"])


def _teardown(parity, config_ini, instance):
    from TM1py import TM1Service

    args = dict(parity.get_tm1_config(config_ini)[instance])
    args["session_context"] = "optimuspy-parity"
    with TM1Service(**args) as tm1:
        parity.teardown_instance(tm1)
