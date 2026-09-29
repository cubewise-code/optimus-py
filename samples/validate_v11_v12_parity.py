#!/usr/bin/env python3
"""Manual pre-merge gate: prove OptimusPy behaves identically on TM1 v11 and v12.

This is NOT a unit test and is NOT run in CI — it needs two live TM1 instances
(one v11, one v12) reachable from the same ``config.ini``. It builds a *byte-for
byte identical* 8-dimension cube, loaded with the *same* seeded random data, on
both servers, then:

  1. Runs every OptimusPy mode (greedy, fast greedy, predefined, position,
     dimension, set) against both servers and compares the winning storage order
     each mode picks. Identical data must yield the same winner on both versions.
  2. Proves the ``cube_memory_used`` Unit->bytes conversion is correct (v11 reports
     ``B``, v12 reports ``KB``) by checking that the *original-order* RAM OptimusPy
     measured during those runs converts to near-equal bytes across versions — a
     wrong conversion would differ by ~1024x. It uses the run-time reading (taken
     on a cube the readiness probe has shown to be measurable), not the pre-run
     baseline sample, which reads a skeleton figure on a cube nothing has touched
     since its load. The pre-run baseline is still captured for information only.
  3. Writes a JSON snapshot (``--snapshot``). Run this script on the *pre-change*
     commit against the v11 instance, keep the snapshot, then run it again on the
     post-change commit and diff the two snapshots to confirm v11 behaviour is
     frozen byte-for-byte.

Usage
-----
    # config.ini must contain a [v11srv] and a [v12srv] section (any names).
    python samples/validate_v11_v12_parity.py \
        --config config/config.ini \
        --v11 v11srv --v12 v12srv \
        --snapshot v11_after.json

    # frozen-behaviour check (run on each commit, then diff the snapshots):
    git stash && python samples/validate_v11_v12_parity.py --config ... \
        --v11 v11srv --only v11 --snapshot v11_before.json && git stash pop
    python samples/validate_v11_v12_parity.py --config ... \
        --v11 v11srv --only v11 --snapshot v11_after.json
    diff <(jq -S . v11_before.json) <(jq -S . v11_after.json)

Pass ``--cleanup`` to delete the generated cube + dimensions afterwards.
"""
import argparse
import csv
import glob
import json
import logging
import os
import sys
import time
from pathlib import Path

# Make the in-tree package importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from TM1py import TM1Service, Dimension, Hierarchy, Element, Cube  # noqa: E402

from optimuspy import core  # noqa: E402
from optimuspy.core import get_tm1_config  # noqa: E402
from optimuspy.metrics import (  # noqa: E402
    detect_is_v12, ram_source_ready, unit_to_bytes, CUBE_MEMORY_METRIC,
)

# Pre-run baseline sampling (informational only — the conversion proof uses the
# settled original-order RAM from the mode runs; see _settled_original_ram). A
# cold cube reports a small skeleton figure here, which is normal and harmless:
# the readiness probe below, not this sample, is what decides whether the run may
# proceed.
_SETTLE_ATTEMPTS = 24
_SETTLE_WAIT_SECONDS = 10
_SETTLE_TOLERANCE = 0.01

# Readiness probe (see _probe_until_the_ram_channel_answers). One rearrangement
# known to cost memory on both engines, measured side by side on 11.8.02200.2 and
# 12.5.9/12.6.4: moving the largest dimension to position 6 returns about -12.5%
# on each. Requiring a non-zero answer to exactly that change tests the channel
# the gate depends on, rather than a proxy for it.
_PROBE_ATTEMPTS = 8
_PROBE_WAIT_SECONDS = 15

# Two orders count as tied when their measured RAM differs by less than this
# fraction. The gate compares each version's winner against the OTHER version's
# winner using that version's own numbers, so this is a within-run tolerance on a
# single %-chain, not a cross-server one. It is tighter than the product's own
# best-result banding (1%/2.5%/5% of the measured range in determine_best_result).
_TIE_TOLERANCE = 0.005

# The same tolerance expressed for the percentage channel, which is what a
# disputed pair is settled with when neither mode's search happened to evaluate
# the other's winner. Percentages come back as e.g. -12.4931 for -12.4931%.
_TIE_TOLERANCE_PCT = _TIE_TOLERANCE * 100

# --- Fixture definition -----------------------------------------------------

CUBE = "OptimusPy_Parity_Test"
SEED = 20260605  # LCG seed — fixed so v11 and v12 receive byte-identical data
# 7 sparse dimensions of widely-varying size + 1 numeric measure dimension (last).
# Varied cardinality + the skewed fill below make storage dimension order actually
# affect RAM, so a genuine winner emerges (a uniform fill ties on every order).
DIM_SIZES = {
    f"{CUBE}_Dim1": 200,
    f"{CUBE}_Dim2": 160,
    f"{CUBE}_Dim3": 120,
    f"{CUBE}_Dim4": 80,
    f"{CUBE}_Dim5": 50,
    f"{CUBE}_Dim6": 25,
    f"{CUBE}_Dim7": 12,
}
MEASURE_DIM = f"{CUBE}_Measure"
MEASURES = ["Value", "Count", "Amount"]
FILL_CELLS = 300_000  # number of deterministic LCG-driven cell writes (server-side)


def _dimension_names():
    return list(DIM_SIZES.keys()) + [MEASURE_DIM]


def _build_dimensions(tm1: TM1Service):
    # Non-padded element names ('E0', 'E1', ...) so the server-side TI can rebuild
    # each name with a plain TRIM(STR(idx, 12, 0)) — no zero-pad logic needed.
    for dim_name, size in DIM_SIZES.items():
        elements = [Element(f"E{i}", "Numeric") for i in range(size)]
        hier = Hierarchy(dim_name, dim_name, elements=elements)
        tm1.dimensions.update_or_create(Dimension(dim_name, [hier]))
    # measure dimension: numeric measures only (keeps it last-position legal)
    elements = [Element(m, "Numeric") for m in MEASURES]
    hier = Hierarchy(MEASURE_DIM, MEASURE_DIM, elements=elements)
    tm1.dimensions.update_or_create(Dimension(MEASURE_DIM, [hier]))


def _build_cube(tm1: TM1Service):
    tm1.cubes.update_or_create(Cube(CUBE, _dimension_names()))


def _ti_fill_prolog():
    """Generate TI prolog that fills the cube with deterministic, skewed sparse data.

    Pushing 300k cells from the client tripped a v12 request-memory cap, so the fill
    runs server-side instead. A MINSTD LCG (integer math, identical on every IEEE
    double engine) makes v11 and v12 produce byte-identical data without RAND().
    A square-skew on each index concentrates density toward low elements so RAM
    genuinely depends on dimension order.
    """
    lines = [
        f"sCube = '{CUBE}';",
        f"nState = {SEED};",
        f"nCells = {FILL_CELLS};",
        "nM = 2147483647;",
        "nA = 48271;",
        "i = 1;",
        "WHILE( i <= nCells );",
    ]
    coords = []
    for k, size in enumerate(DIM_SIZES.values(), start=1):
        lines += [
            "  nState = MOD( nA * nState, nM );",
            f"  nR = MOD( nState, {size} );",
            f"  nIdx{k} = INT( nR * nR / {size} );",  # square-skew toward low indices
        ]
        coords.append(f"'E' | TRIM(STR(nIdx{k}, 12, 0))")
    lines += [
        "  nState = MOD( nA * nState, nM );",
        f"  nMeas = MOD( nState, {len(MEASURES)} );",
        "  IF( nMeas = 0 ); sMeas = 'Value'; ELSEIF( nMeas = 1 ); sMeas = 'Count'; ELSE; sMeas = 'Amount'; ENDIF;",
        "  nState = MOD( nA * nState, nM );",
        "  nVal = MOD( nState, 1000000 ) + 1;",
        f"  CellPutN( nVal, sCube, {', '.join(coords)}, sMeas );",
        "  i = i + 1;",
        "END;",
    ]
    return lines


def read_gauge_bytes(tm1: TM1Service):
    """One raw cube_memory_used sample in bytes, or None if the metric is absent.

    No settling, no retry — the callers here want the instantaneous reading so
    they can watch it move.
    """
    rows = tm1.metrics.by_cube(cube=CUBE)
    row = next((r for r in rows
                if r.get("Metric") == CUBE_MEMORY_METRIC and r.get("Value") is not None), None)
    return None if row is None else unit_to_bytes(row.get("Value"), row.get("Unit"))


def _probe_order(canonical):
    """The rearrangement the readiness probe applies: largest dimension to position 6.

    Chosen because it is *known* to cost memory on both engines rather than
    assumed to. Most rearrangements of this cube are free on v11 and v12 alike —
    an identity, an adjacent swap of the two smallest dimensions, even a swap of
    the two largest all return 0% on both — and a 0 from one of those is the
    truth, not a missing answer. A probe built on one of them would pass on a
    dead channel and fail on a live one.
    """
    return [*canonical[1:7], canonical[0], canonical[7]]


def _probe_until_the_ram_channel_answers(tm1: TM1Service):
    """Block until a reorder returns a non-zero percentage, or fail the setup.

    This is the gate that stops the whole comparison running before the fixture
    is measurable. It does not watch the gauge and does not wait a fixed time:
    it exercises the exact channel every mode run depends on — the percentage
    ``update_storage_dimension_order`` returns — and demands a real answer from
    it.

    Why that is the right test. A cube whose data is not yet resident costs the
    same in every order, so it truthfully returns 0% for every rearrangement and
    a truthfully tiny figure from the memory gauge. Both readings are honest;
    the run built on them is not. A gate that waited for the gauge to grow would
    be testing a symptom, and a gate that waited a fixed number of seconds would
    be testing nothing at all.

    Raising is deliberate. A gate that cannot get an answer out of its own
    fixture has nothing to say about parity, and saying nothing loudly beats
    reporting a comparison between two numbers that were never measurements.

    The cube is returned to the order it came in on, whatever the outcome.
    """
    is_v12 = detect_is_v12(tm1)
    canonical = list(tm1.cubes.get_storage_dimension_order(cube_name=CUBE))
    probe = _probe_order(canonical)
    last = None

    with ram_source_ready(tm1, is_v12):
        for attempt in range(_PROBE_ATTEMPTS):
            try:
                last = tm1.cubes.update_storage_dimension_order(CUBE, probe)
            finally:
                # Restore on every path: a probe that leaves the fixture
                # rearranged has corrupted the very "original order" the gate
                # compares across versions.
                tm1.cubes.update_storage_dimension_order(CUBE, canonical)
            if last:
                print(f"    RAM channel answering: probe reorder returned {last:.4f}% "
                      f"(gauge {read_gauge_bytes(tm1)})")
                return last
            if attempt < _PROBE_ATTEMPTS - 1:
                print(f"    probe returned 0% — cube not measurable yet, retrying in "
                      f"{_PROBE_WAIT_SECONDS}s")
                time.sleep(_PROBE_WAIT_SECONDS)

    raise RuntimeError(
        f"the RAM channel for '{CUBE}' never answered: moving the largest "
        f"dimension to position 6 returned {last} on every one of "
        f"{_PROBE_ATTEMPTS} attempts over "
        f"{_PROBE_ATTEMPTS * _PROBE_WAIT_SECONDS}s. That rearrangement costs "
        f"about 12.5% on both v11 and v12 when the cube is measurable, so a zero "
        f"means the fill has not become resident. Every mode would measure the "
        f"same value and every winner would be a tie-break. Refusing to run the "
        f"gate on numbers that are not measurements.")


def setup_instance(tm1: TM1Service):
    """Build the fixture from scratch and do not return until it is measurable.

    A fixture this run did not build is never adopted. `update_or_create` would
    happily reuse one left behind by a crashed run, and that is worse than it
    sounds: a crash *after* a mode run leaves the cube in a REORDERED storage
    order, and the next run reads that back as its "original order" — the exact
    value the gate compares across versions. Dropping first costs one delete and
    removes the whole class of problem. The cube name is owned by this script.
    """
    if tm1.cubes.exists(CUBE):
        print(f"    found a leftover '{CUBE}' — dropping it rather than adopting it")
        teardown_instance(tm1)
    _build_dimensions(tm1)
    _build_cube(tm1)
    # Server-side fill (avoids the client->server request-memory cap on v12).
    tm1.processes.execute_ti_code(_ti_fill_prolog())
    _probe_until_the_ram_channel_answers(tm1)


def teardown_instance(tm1: TM1Service):
    if tm1.cubes.exists(CUBE):
        tm1.cubes.delete(CUBE)
    for dim in _dimension_names():
        if tm1.dimensions.exists(dim):
            tm1.dimensions.delete(dim)


# --- Reads ------------------------------------------------------------------

def read_baseline(tm1: TM1Service, is_v12: bool) -> dict:
    """Read cube_memory_used once it plateaus; report raw value + Unit + bytes.

    This is a best-effort *pre-run informational* sample only, and a small value
    here is not a defect: a cube that has not yet been touched since its load
    reports a skeleton figure, and a passing six-mode parity run has been
    recorded with a 40,960 B sample sitting beside a correct 67,145,728 B
    run-time measurement. The conversion proof uses the latter — the
    original-order RAM OptimusPy measures *during* the mode runs, on a cube the
    readiness probe has already shown to be measurable (see
    _settled_original_ram / compare).
    """
    best = None
    raw = None
    for attempt in range(_SETTLE_ATTEMPTS):
        rows = tm1.metrics.by_cube(cube=CUBE)
        row = next((r for r in rows
                    if r.get("Metric") == CUBE_MEMORY_METRIC and r.get("Value") is not None), None)
        if row is not None:
            b = unit_to_bytes(row.get("Value"), row.get("Unit"))
            raw = row
            if best is not None and b <= best * (1 + _SETTLE_TOLERANCE):
                best = max(best, b)
                break
            best = b if best is None else max(best, b)
        if attempt < _SETTLE_ATTEMPTS - 1:
            time.sleep(_SETTLE_WAIT_SECONDS)
    return {
        "raw_value": None if raw is None else raw.get("Value"),
        "raw_unit": None if raw is None else raw.get("Unit"),
        "bytes": best,
    }


# --- Mode runs --------------------------------------------------------------

MODE_CONFIGS = {
    "greedy": {"executions": 1, "output": "csv"},
    "greedy_fast": {"executions": 1, "output": "csv", "fast": True},
    "predefined": {"executions": 1, "output": "csv", "predefined_orders": "PREDEFINED"},
    "position_last": {"executions": 1, "output": "csv", "optimize_position": "last"},
    "dimension": {"executions": 1, "output": "csv", "optimize_dimension": f"{CUBE}_Dim3"},
    "set": {"executions": 1, "output": "csv", "predefined_orders": "PREDEFINED"},
}


def _cube_config(instance: str, overrides: dict) -> dict:
    base = {"instance": instance, "cube": CUBE, "views": [], "processes": []}
    cfg = {**base, **overrides}
    if cfg.get("predefined_orders") == "PREDEFINED":
        # one swapped order; reversing the sparse dims is a legal, distinct order
        sparse = list(DIM_SIZES.keys())
        cfg["predefined_orders"] = [list(reversed(sparse)) + [MEASURE_DIM]]
    return cfg


def _latest_csv(instance: str) -> str:
    pattern = str(core.RESULT_PATH / instance / f"{instance}_{CUBE}_*.csv")
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def _parse_result_csv(path: str) -> dict:
    """Extract the winner, the original-order baseline, and every order's RAM.

    ``ram_by_order`` is what lets the comparison tell a disagreement from a tie:
    given v12's winning order, it answers what v11 measured for that same order.
    Keys are the order joined by ``|`` so the snapshot stays JSON-serialisable.
    """
    n_dims = len(_dimension_names())
    best = None
    original_ram = None
    ram_by_order = {}
    with open(path, newline="") as f:
        # Result CSVs begin with '# ...' comment lines and a blank line before
        # the real 'ID,Mode,...' header; drop those so DictReader sees the header.
        data_lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    for row in csv.DictReader(data_lines):
        order = [row[f"Dimension{i}"] for i in range(1, n_dims + 1)]
        ram = float(row["RAM"])
        ram_by_order["|".join(order)] = ram
        if (row.get("Mode") or "").upper().startswith("ORIGINAL"):
            original_ram = ram
        if (row.get("Is Best") or "").strip().lower() == "true":
            best = {"order": order, "ram_bytes": ram}
    return {"best": best, "original_ram_bytes": original_ram,
            "ram_by_order": ram_by_order}


class _FatalCatcher(logging.Handler):
    """Keep the ERROR records a mode run logged, so the report can quote them.

    core.main catches its own fatal exceptions, logs them and returns False, so
    the reason a mode failed is otherwise only in the log file. Without it the
    report cannot tell the reader whether a mode failed because the two versions
    disagree or because the socket died, and someone re-diagnoses it from scratch.
    """

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


# Substrings that mark a failure as transport rather than anything OptimusPy
# decided. A hint for the label only — the captured text is printed either way
# and is what should be believed.
_TRANSPORT_MARKERS = (
    "ConnectionReset", "Connection reset", "ConnectionError", "Connection aborted",
    "RemoteDisconnected", "Max retries exceeded", "Timeout", "timed out",
    "BrokenPipe", "SSLError",
)


def classify_failure(error_text):
    """'transport' for a dead connection, 'run' for anything else."""
    if not error_text:
        return "run"
    return "transport" if any(m in error_text for m in _TRANSPORT_MARKERS) else "run"


def run_modes(instance: str, config_ini: str, password: str) -> dict:
    results = {}
    for mode_label, overrides in MODE_CONFIGS.items():
        tm1_mode = "set" if mode_label == "set" else "optimize"
        cube_config = _cube_config(instance, overrides)
        catcher = _FatalCatcher()
        logging.getLogger().addHandler(catcher)
        error = None
        try:
            ok = core.main(tm1_mode, cube_config, config_ini, password=password,
                           no_resume=True)
        except Exception as exc:                            # noqa: BLE001
            ok, error = False, f"{type(exc).__name__}: {exc}"
        finally:
            logging.getLogger().removeHandler(catcher)
        if not ok and error is None and catcher.messages:
            error = catcher.messages[-1]
        csv_path = _latest_csv(instance)
        parsed = _parse_result_csv(csv_path) if (ok and csv_path) else None
        results[mode_label] = {"ok": bool(ok), "result": parsed, "error": error}
        suffix = "" if ok else f" [{classify_failure(error)}] {error or 'no error captured'}"
        print(f"    [{instance}] {mode_label}: ok={bool(ok)}{suffix}")
    return results


# --- Orchestration ----------------------------------------------------------

def process_instance(name: str, config_ini: str, password: str, do_setup: bool) -> dict:
    cfg = get_tm1_config(config_ini)
    tm1_args = dict(cfg[name])
    tm1_args["session_context"] = "optimuspy-parity"
    if password:
        tm1_args["password"] = password
        tm1_args["decode_b64"] = False

    with TM1Service(**tm1_args) as tm1:
        is_v12 = detect_is_v12(tm1)
        version = tm1.server.get_product_version()
        print(f"  {name}: TM1 {version} ({'v12' if is_v12 else 'v11'})")
        if do_setup:
            print(f"  {name}: building fixture cube '{CUBE}'...")
            setup_instance(tm1)
        baseline = read_baseline(tm1, is_v12)
        print(f"  {name}: cube_memory_used raw={baseline['raw_value']} "
              f"{baseline['raw_unit']} -> {baseline['bytes']:.0f} bytes")
    # mode runs open their own connections via core.main
    modes = run_modes(name, config_ini, password)
    return {"version": str(version), "is_v12": is_v12,
            "baseline": baseline, "modes": modes}


def _settled_original_ram(snapshot: dict):
    """The original-order RAM OptimusPy measured during the mode runs, in bytes.

    Every optimize mode reads the same original order first (OriginalOrderExecutor),
    parsed back as ``original_ram_bytes``. That read happens well after the load, on
    a settled cube, via the product's own version-aware read path — so it is the
    reliable cross-version conversion-proof value, unlike the pre-run read_baseline
    whose sample is taken on a cube nothing has touched since its load. Returns
    the first available mode's value (they all read the identical original order).
    """
    for mode in MODE_CONFIGS:
        res = (snapshot.get("modes", {}).get(mode) or {}).get("result") or {}
        val = res.get("original_ram_bytes")
        if val:
            return val
    return None


def measure_order_gap(tm1: TM1Service, order_a, order_b):
    """Percentage change this server reports for going from order_a to order_b.

    Deliberately the percentage channel and not the memory gauge. On v11 the
    gauge is sampled and sits one step behind its own reported percentages, so
    reading it immediately after a reorder returns the PREVIOUS order's figure —
    which on a two-order comparison is exactly the wrong number. Both versions
    report the percentage correctly and immediately.

    A near-zero answer means the two orders cost the same on this server. The
    cube is left on order_b; callers restore.
    """
    tm1.cubes.update_storage_dimension_order(CUBE, list(order_a))
    return tm1.cubes.update_storage_dimension_order(CUBE, list(order_b))


def resolve_disputed_winners(snapshot: dict, config_ini: str, v11_name: str, v12_name: str):
    """Measure, on both servers, every pair of winners the runs left unresolved.

    A greedy search is a hill-climb: it only ever evaluates orders on its own
    path. When the two versions finish on different orders, neither one has
    usually measured the other's, so ``ram_by_order`` cannot say whether the
    disagreement is a real preference or two orders that cost the same. Without
    this the gate has to call every such pair a failure, which is how it flakes
    on a good run — v11 and v12 finishing on Dim6/Dim7 swapped is the live case,
    and that swap measures 0% on both engines.

    So the missing measurement is taken rather than assumed, while the fixture is
    still up: apply one winner, then the other, and record what the server says
    the change cost. This asserts the thing that is actually true instead of
    relaxing the thing that was asserted.

    Each cube is put back to the order it was found in.
    """
    disputed = []
    for mode in MODE_CONFIGS:
        r11 = (snapshot["v11"]["modes"].get(mode) or {}).get("result") or {}
        r12 = (snapshot["v12"]["modes"].get(mode) or {}).get("result") or {}
        b11, b12 = r11.get("best"), r12.get("best")
        if not b11 or not b12 or b11["order"] == b12["order"]:
            continue
        disputed.append((mode, b11["order"], b12["order"]))
    if not disputed:
        return

    print(f"\n  resolving {len(disputed)} disputed winner(s) by measurement:")
    for label, instance in (("v11", v11_name), ("v12", v12_name)):
        args = dict(get_tm1_config(config_ini)[instance])
        args["session_context"] = "optimuspy-parity-tie"
        with TM1Service(**args) as tm1:
            is_v12 = detect_is_v12(tm1)
            original = list(tm1.cubes.get_storage_dimension_order(cube_name=CUBE))
            try:
                with ram_source_ready(tm1, is_v12):
                    for mode, o11, o12 in disputed:
                        pct = measure_order_gap(tm1, o11, o12)
                        snapshot[label]["modes"][mode]["cross_gap_pct"] = pct
                        print(f"    [{instance}] {mode}: v11's winner -> v12's "
                              f"winner costs {pct}%")
            finally:
                tm1.cubes.update_storage_dimension_order(CUBE, original)


def _measured_gap_tie(m11, m12):
    """(tie, detail) from the directly measured gaps, or None when they are absent."""
    g11, g12 = m11.get("cross_gap_pct"), m12.get("cross_gap_pct")
    if g11 is None or g12 is None:
        return None
    detail, tie = [], True
    for label, gap in (("v11", g11), ("v12", g12)):
        within = abs(gap) <= _TIE_TOLERANCE_PCT
        tie &= within
        detail.append(
            f"{label} measured the step from one winner to the other at {gap}% "
            f"({'no cost — tied' if within else 'a real preference'})")
    return tie, detail


def _winners_tie(r11, b11, r12, b12):
    """True when each version measures the other version's winner as equivalent.

    Cross-server byte comparison would be the wrong test — the two servers report
    slightly different absolute sizes for identical data, and the %-chains are
    independent. What actually matters is whether either version had a reason to
    prefer its own winner. So v11's numbers are asked about v12's order and vice
    versa, and only if BOTH say "no measurable difference" is this a tie.

    An order the other version never evaluated is not a tie: the modes prune
    candidates as they go, and an unexplored order is an unknown, not an equal.
    Returns (tie, detail_lines) — the lines are printed either way, because the
    numbers are what make a FAIL actionable.
    """
    detail = []
    tie = True
    for label, own, own_best, other_best in (
            ("v11", r11, b11, b12), ("v12", r12, b12, b11)):
        by_order = own.get("ram_by_order") or {}
        other_ram = by_order.get("|".join(other_best["order"]))
        if other_ram is None:
            detail.append(f"{label} never evaluated the other version's winner "
                          f"— no tie can be claimed")
            tie = False
            continue
        mine = own_best["ram_bytes"]
        delta = abs(mine - other_ram)
        within = delta <= max(mine, other_ram) * _TIE_TOLERANCE
        tie &= within
        detail.append(
            f"{label} measured its own winner at {mine:.0f} B and the other's at "
            f"{other_ram:.0f} B (delta {delta:.0f}, "
            f"{'tied' if within else 'a real preference'})")
    return tie, detail


def compare(v11: dict, v12: dict) -> bool:
    print("\n=== PARITY REPORT ===")
    ok = True

    # Conversion proof uses the settled original-order RAM the product measured
    # during the runs (both versions), NOT the pre-run baseline sample, which is a
    # cold read. If the Unit->bytes conversion were wrong, v11 (B) and v12 (KB)
    # would differ by ~1024x rather than by identical-data noise.
    o11, o12 = _settled_original_ram(v11), _settled_original_ram(v12)
    print(f"\nRAM (Unit->bytes conversion proof — original-order RAM as measured during the runs):")
    if o11 and o12:
        delta = abs(o11 - o12)
        tol = max(o11, o12) * 0.001  # 0.1% — identical data should be near-identical
        conv_ok = delta <= tol
        ok &= conv_ok
        print(f"  v11 -> {o11:.0f} bytes")
        print(f"  v12 -> {o12:.0f} bytes")
        print(f"  delta {delta:.0f} bytes ({'PASS' if conv_ok else 'FAIL'}; tol {tol:.0f})")
    else:
        ok = False
        print("  FAIL (no original-order RAM captured on one version)")
    print(f"  [pre-run cold sample, informational — a small figure here is normal] "
          f"v11: {v11['baseline']['raw_value']} {v11['baseline']['raw_unit']}; "
          f"v12: {v12['baseline']['raw_value']} {v12['baseline']['raw_unit']}")

    print(f"\nMode winner parity:")
    print("  (PASS = same winner or a measured tie; FAIL = the versions disagree; "
          "ERROR = a run did not complete, so nothing was compared)")
    for mode in MODE_CONFIGS:
        m11 = v11["modes"].get(mode) or {}
        m12 = v12["modes"].get(mode) or {}
        r11, r12 = m11.get("result"), m12.get("result")
        if not m11.get("ok") or not m12.get("ok") or not r11 or not r12:
            # Not a disagreement: no comparison happened at all. Say which side
            # died and quote the reason, so a dropped socket is not re-diagnosed
            # as a version difference by the next person to read this.
            ok = False
            print(f"  {mode}: ERROR (the run did not complete — nothing was compared)")
            for label, m in (("v11", m11), ("v12", m12)):
                if m.get("ok") and m.get("result"):
                    continue
                err = m.get("error")
                kind = classify_failure(err)
                print(f"    {label}: [{kind}] {err or 'failed with no error captured'}")
                if kind == "transport":
                    print(f"    {label}: a dropped connection is a harness/network "
                          f"failure, not a parity result — re-run this mode.")
            continue
        b11, b12 = r11.get("best"), r12.get("best")
        if b11 is None and b12 is None:
            # Neither version found an order that beats the original. For an
            # identical cube that is itself parity — both agree there is no
            # RAM-improving order — not a failure.
            print(f"  {mode}: PASS (no improving order on either version)")
            continue
        if not b11 or not b12:
            print(f"  {mode}: FAIL (a winner emerged on one version only)")
            ok = False
            continue
        if b11["order"] == b12["order"]:
            print(f"  {mode}: PASS")
            continue

        # Different winners. Before calling that a disagreement, ask whether the
        # data even supports a preference: adjacent dimensions of similar
        # cardinality can measure identically, and demanding a total order where
        # the measurements only support an equivalence class makes this gate flake
        # on a perfectly good run. Each version is asked about the other's winner
        # using its OWN numbers.
        # A gap measured directly on both servers beats inference from orders
        # the searches happened to visit, so it is used when it is available.
        measured = _measured_gap_tie(m11, m12)
        tie, detail = measured if measured else _winners_tie(r11, b11, r12, b12)
        if tie:
            print(f"  {mode}: PASS (tie — the two winners measure the same on both "
                  f"versions, within {_TIE_TOLERANCE:.1%})")
            for line in detail:
                print(f"    {line}")
            continue
        ok = False
        print(f"  {mode}: FAIL")
        print(f"    v11 -> {b11['order']}")
        print(f"    v12 -> {b12['order']}")
        for line in detail:
            print(f"    {line}")

    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/config.ini",
                    help="path to config.ini (default: config/config.ini)")
    ap.add_argument("--v11", help="config.ini section name for the v11 instance")
    ap.add_argument("--v12", help="config.ini section name for the v12 instance")
    ap.add_argument("--password", default=None, help="password override for both")
    ap.add_argument("--only", choices=["v11", "v12"], default=None,
                    help="run against a single instance (for the before/after-change diff)")
    ap.add_argument("--no-setup", action="store_true",
                    help="skip cube/data creation (reuse an existing fixture)")
    ap.add_argument("--cleanup", action="store_true",
                    help="delete the fixture cube + dimensions when done")
    ap.add_argument("--snapshot", default=None, help="write results JSON to this path")
    args = ap.parse_args()

    snapshot = {}
    do_setup = not args.no_setup

    if args.only != "v12" and args.v11:
        print("v11 instance:")
        snapshot["v11"] = process_instance(args.v11, args.config, args.password, do_setup)
    if args.only != "v11" and args.v12:
        print("v12 instance:")
        snapshot["v12"] = process_instance(args.v12, args.config, args.password, do_setup)

    passed = True
    if "v11" in snapshot and "v12" in snapshot:
        passed = compare(snapshot["v11"], snapshot["v12"])

    if args.snapshot:
        Path(args.snapshot).write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        print(f"\nSnapshot written to {args.snapshot}")

    if args.cleanup:
        for key, name in (("v11", args.v11), ("v12", args.v12)):
            if key in snapshot and name:
                cfg = get_tm1_config(args.config)
                tm1_args = dict(cfg[name])
                tm1_args["session_context"] = "optimuspy-parity"
                if args.password:
                    tm1_args["password"] = args.password
                    tm1_args["decode_b64"] = False
                with TM1Service(**tm1_args) as tm1:
                    teardown_instance(tm1)
                    print(f"Cleaned up fixture on {name}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
