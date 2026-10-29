"""The parity gate's verdict logic, offline.

compare() decides PASS / FAIL / ERROR for every mode, and both of the judgements
it makes were wrong in ways a live run exposed:

  - it demanded a total order where the measurements only supported an
    equivalence class, so two adjacent dimensions of similar cardinality that
    genuinely measure the same could flake the gate on a good run;
  - it reported a dropped connection with the same word as a real version
    disagreement, so a transport failure got diagnosed as a product bug.

These are pure functions over parsed CSV data — no server, no fixture, and the
gate itself stays behind @pytest.mark.live where it belongs.
"""
from tests.conftest import sample_module

parity = sample_module("validate_v11_v12_parity")

A = ["Measure", "Dim6", "Dim7", "Dim4"]
B = ["Measure", "Dim7", "Dim6", "Dim4"]


def _side(winner, ram_by_order):
    return ({"ram_by_order": {"|".join(o): v for o, v in ram_by_order}},
            {"order": winner, "ram_bytes": dict(
                ("|".join(o), v) for o, v in ram_by_order)["|".join(winner)]})


def test_two_orders_each_version_measures_identically_are_a_tie():
    # The live case: v11 picked A, v12 picked B, and a controlled settled probe
    # read the two orders byte-identically on both servers.
    r11, b11 = _side(A, [(A, 41_939_968.0), (B, 41_939_968.0)])
    r12, b12 = _side(B, [(A, 41_979_904.0), (B, 41_979_904.0)])

    tie, detail = parity._winners_tie(r11, b11, r12, b12)

    assert tie is True
    assert len(detail) == 2


def test_a_version_with_a_real_preference_is_not_a_tie():
    # v11 measured its own winner 14% smaller. That is a disagreement, and no
    # tolerance should absorb it.
    r11, b11 = _side(A, [(A, 35_948_481.0), (B, 41_939_968.0)])
    r12, b12 = _side(B, [(A, 41_979_904.0), (B, 41_979_904.0)])

    tie, _ = parity._winners_tie(r11, b11, r12, b12)

    assert tie is False


def test_both_versions_must_agree_it_is_a_tie():
    # v12 sees no difference but v11 does. One side having a reason to prefer its
    # own winner is enough to make this a real divergence.
    r11, b11 = _side(A, [(A, 40_000_000.0), (B, 44_000_000.0)])
    r12, b12 = _side(B, [(A, 41_979_904.0), (B, 41_979_904.0)])

    tie, _ = parity._winners_tie(r11, b11, r12, b12)

    assert tie is False


def test_an_order_the_other_version_never_evaluated_is_not_a_tie():
    # The modes prune candidates as they go. An unexplored order is an unknown,
    # and calling it equal would turn missing evidence into a pass.
    r11, b11 = _side(A, [(A, 41_939_968.0)])
    r12, b12 = _side(B, [(A, 41_979_904.0), (B, 41_979_904.0)])

    tie, detail = parity._winners_tie(r11, b11, r12, b12)

    assert tie is False
    assert any("never evaluated" in line for line in detail)


def test_a_difference_just_inside_the_tolerance_still_ties():
    within = 41_939_968.0 * (1 + parity._TIE_TOLERANCE / 2)
    r11, b11 = _side(A, [(A, 41_939_968.0), (B, within)])
    r12, b12 = _side(B, [(A, 41_979_904.0), (B, 41_979_904.0)])

    assert parity._winners_tie(r11, b11, r12, b12)[0] is True


def test_a_dropped_connection_is_classified_as_transport():
    assert parity.classify_failure(
        "Fatal error: ConnectionResetError(54, 'Connection reset by peer')") == "transport"
    assert parity.classify_failure(
        "HTTPSConnectionPool: Max retries exceeded with url: /api") == "transport"


def test_anything_else_is_classified_as_a_run_failure():
    assert parity.classify_failure(
        "Fatal error: view 'Default' in cube 'C' is too small") == "run"
    assert parity.classify_failure(None) == "run"


# --- the readiness probe's choice of rearrangement --------------------------
#
# Which rearrangement the probe applies is the whole of its value, so it is
# pinned here. Most rearrangements of this fixture are free on BOTH engines —
# measured 22 Sep on 11.8.02200.2 and 12.6.4, an identity, an adjacent swap of
# the two smallest dimensions and a swap of the two largest all returned 0% on
# each. A probe built on any of those would pass against a cube that is not
# resident. Moving the largest dimension to position 6 returned about -12.5% on
# both, which is why it is the one that gets asked.

def test_the_probe_moves_the_largest_dimension_to_position_six():
    d = [f"D{i}" for i in range(1, 8)] + ["Measure"]
    assert parity._probe_order(d) == ["D2", "D3", "D4", "D5", "D6", "D7", "D1", "Measure"]


def test_the_probe_is_not_one_of_the_free_rearrangements():
    d = [f"D{i}" for i in range(1, 8)] + ["Measure"]
    probe = parity._probe_order(d)
    assert probe != d                                        # not the identity
    assert probe != [*d[:5], d[6], d[5], d[7]]               # not the D6<->D7 swap
    assert probe != [d[1], d[0], *d[2:]]                     # not the D1<->D2 swap


def test_the_probe_leaves_the_measure_dimension_last():
    # The fixture's measure dimension is last-position legal and must stay put;
    # a probe that moved it would be testing a different cube.
    d = [f"D{i}" for i in range(1, 8)] + ["Measure"]
    assert parity._probe_order(d)[-1] == "Measure"


# --- the directly measured tie-break ----------------------------------------
#
# When neither version's search evaluated the other's winner, _winners_tie has
# nothing to compare and must refuse to claim a tie. The gap is then measured on
# both servers instead (resolve_disputed_winners), and that measurement decides.

def test_a_measured_zero_gap_on_both_servers_is_a_tie():
    tie, detail = parity._measured_gap_tie({"cross_gap_pct": 0}, {"cross_gap_pct": 0})
    assert tie is True
    assert all("tied" in line for line in detail)


def test_a_real_measured_cost_on_either_server_is_not_a_tie():
    assert parity._measured_gap_tie(
        {"cross_gap_pct": 0}, {"cross_gap_pct": -12.4931})[0] is False
    assert parity._measured_gap_tie(
        {"cross_gap_pct": -12.5004}, {"cross_gap_pct": 0})[0] is False


def test_a_gap_just_inside_tolerance_is_a_tie():
    inside = parity._TIE_TOLERANCE_PCT * 0.9
    assert parity._measured_gap_tie(
        {"cross_gap_pct": inside}, {"cross_gap_pct": -inside})[0] is True


def test_no_measurement_means_no_verdict_from_this_route():
    # Absent on either side hands the decision back to _winners_tie.
    assert parity._measured_gap_tie({}, {"cross_gap_pct": 0}) is None
    assert parity._measured_gap_tie({"cross_gap_pct": 0}, {}) is None
