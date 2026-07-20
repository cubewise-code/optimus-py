#!/usr/bin/env python3
"""Live smoke test: resume survives a mid-run connection drop (v11 + v12).

Builds the parity fixture cube on one instance, then drives the real
``core.main`` optimize flow while deterministically faulting
``update_storage_dimension_order`` to simulate a dropped connection at a precise
point — exercising BOTH Level-2 recovery branches against a live server:

  * NOT-LANDED: the reorder raises *before* it applies, so the cube stays at the
    previous order; on resume the pending order is re-evaluated normally.
  * LANDED: the reorder applies, then the call raises; the cube sits at the
    pending order, so on resume it is recovered without re-applying (one absolute
    RAM read + back-calc).

For each branch it asserts the crash left a valid checkpoint (with pending), then
runs ``core.main`` again (no fault) and asserts resume: validated (not "starting
fresh"), recovered the in-flight order, completed, removed the checkpoint, and
restored the ORIGINAL storage order.

Run with the sandbox disabled (Tailscale IPs) and the pyenv ``python``:

    python samples/smoke_resume_drop.py --config config/config.ini --instance tm1srv01
    python samples/smoke_resume_drop.py --config config/config.ini --instance tm1srv02
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from TM1py import TM1Service  # noqa: E402
from TM1py.Services.CubeService import CubeService  # noqa: E402

from optimuspy import core  # noqa: E402
from optimuspy.core import get_tm1_config, RESULT_PATH  # noqa: E402
from optimuspy.checkpoint import CheckpointManager  # noqa: E402
from optimuspy.metrics import detect_is_v12  # noqa: E402

from validate_v11_v12_parity import (  # noqa: E402
    CUBE, setup_instance, teardown_instance,
)


class _DropSignal(RuntimeError):
    """Stand-in for a dropped TM1 connection."""


class _Fault:
    """Simulate a dropped connection on the trip_on-th reorder, then STAY down.

    Once tripped, every later update_storage_dimension_order also raises — so the
    crash-path best-effort restore is a genuine no-op (as with a real drop), and
    the cube is left at the last order it managed to apply. For the landed case
    the trip_on reorder is applied first (it reached TM1) and then raises.
    """

    def __init__(self, trip_on: int, landed: bool):
        self.trip_on = trip_on
        self.landed = landed
        self.calls = 0
        self._orig = CubeService.update_storage_dimension_order

    @property
    def tripped(self):
        return self.calls >= self.trip_on

    def __enter__(self):
        orig = self._orig
        fault = self

        def patched(cube_self, cube_name, dimension_names, *a, **kw):
            fault.calls += 1
            if fault.calls < fault.trip_on:
                return orig(cube_self, cube_name, dimension_names, *a, **kw)
            if fault.landed and fault.calls == fault.trip_on:
                orig(cube_self, cube_name, dimension_names, *a, **kw)  # this one lands
            raise _DropSignal(f"connection dropped at reorder #{fault.calls}")

        CubeService.update_storage_dimension_order = patched
        return self

    def __exit__(self, *exc):
        CubeService.update_storage_dimension_order = self._orig


class _LogCapture:
    def __init__(self):
        self.messages = []

    def __enter__(self):
        self._handler = logging.Handler()
        self._handler.emit = lambda record: self.messages.append(record.getMessage())
        logging.getLogger().addHandler(self._handler)
        logging.getLogger().setLevel(logging.INFO)
        return self

    def __exit__(self, *exc):
        logging.getLogger().removeHandler(self._handler)

    def has(self, needle):
        return any(needle in m for m in self.messages)


def _cube_config(instance):
    return {
        "instance": instance,
        "cube": CUBE,
        "views": [],
        "executions": 1,
        "output": "csv",
    }


def _storage_order(tm1):
    return list(tm1.cubes.get_storage_dimension_order(cube_name=CUBE))


def _checkpoint_mgr(instance, cube_config):
    fp = CheckpointManager.compute_config_fingerprint(
        cube_config,
        extra={"tau_ram": core.tau.TAU_RAM, "tau_query": core.tau.TAU_QUERY,
               "fold_b_max_passes": core.tau.FOLD_B_MAX_PASSES})
    return CheckpointManager(CUBE, instance, fp, RESULT_PATH)


PASS, FAIL = "✓", "✗"


def _run_scenario(name, instance, config_ini, original_order, landed, trip_on):
    print(f"\n=== {name} (trip on reorder #{trip_on}, "
          f"{'landed' if landed else 'not landed'}) ===")
    cfg = _cube_config(instance)
    mgr = _checkpoint_mgr(instance, cfg)
    mgr.remove()  # clean slate

    # 1) fresh run that drops mid-fold. core catches the drop internally (real
    #    crash behaviour: log + return False), leaving the checkpoint in place.
    with _Fault(trip_on, landed) as fault:
        crashed = core.main("optimize", cfg, config_ini, no_resume=True)
    assert fault.tripped, "fault did not trip — increase the cube size / lower trip_on"
    assert crashed is False, "crash run should have returned False"
    print(f"  {PASS} simulated drop at reorder #{fault.calls}; core returned False")

    assert mgr.exists(), "no checkpoint left after the drop"
    data = mgr.load()
    pending = data.get("pending")
    print(f"  {'✓' if pending else 'i'} checkpoint pending = "
          f"{pending['dimension_order'] if pending else None}")
    print(f"  completed_results so far: {len(data['completed_results'])}")
    with TM1Service(**_tm1_args(config_ini, instance)) as tm1:
        live = _storage_order(tm1)
    print(f"  cube left at: {live}")

    # 2) resume (no fault) to completion
    with _LogCapture() as log:
        ok = core.main("optimize", cfg, config_ini, no_resume=False)
    assert ok, "resume run returned False"
    assert log.has("Resuming from checkpoint"), "did NOT resume — started fresh!"
    print(f"  {PASS} resumed from checkpoint (not fresh)")
    if pending:
        assert log.has("Recovered in-flight order"), "pending order not recovered"
        print(f"  {PASS} recovered the in-flight order")
    assert not mgr.exists(), "checkpoint not removed after successful completion"
    print(f"  {PASS} checkpoint removed on completion")

    with TM1Service(**_tm1_args(config_ini, instance)) as tm1:
        restored = _storage_order(tm1)
    assert restored == original_order, (
        f"original order NOT restored\n   want {original_order}\n   got  {restored}")
    print(f"  {PASS} original storage order restored")
    return True


def _tm1_args(config_ini, instance):
    cfg = get_tm1_config(config_ini)
    args = dict(cfg[instance])
    args["session_context"] = "optimuspy-smoke"
    return args


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--keep", action="store_true", help="do not delete the fixture cube")
    args = ap.parse_args()

    logging.getLogger().setLevel(logging.INFO)
    tm1_args = _tm1_args(args.config, args.instance)

    with TM1Service(**tm1_args) as tm1:
        is_v12 = detect_is_v12(tm1)
        print(f"Connected to {args.instance} — TM1 {'v12' if is_v12 else 'v11'}")
        if not tm1.cubes.exists(CUBE):
            print("Building fixture cube (300k-cell skewed fill)…")
            setup_instance(tm1)
        original_order = _storage_order(tm1)
        print(f"Original storage order: {original_order}")

    try:
        _run_scenario("NOT-LANDED drop", args.instance, args.config,
                      original_order, landed=False, trip_on=4)
        _run_scenario("LANDED drop", args.instance, args.config,
                      original_order, landed=True, trip_on=4)
        print(f"\n{PASS} ALL RESUME SMOKE CHECKS PASSED on {args.instance}")
    finally:
        if not args.keep:
            with TM1Service(**tm1_args) as tm1:
                teardown_instance(tm1)
                print("Fixture cube removed.")


if __name__ == "__main__":
    main()
