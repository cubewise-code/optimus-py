"""Regression: the Fold B seed must not force a *numeric* measure into the last slot.

Reproduces the field report on cube 1185.PLAN_TL_Reporting_Weekly (see the
TM1 Internal Dimension Order guide, docs/): the value/measure dimension
`VAR_RPT_Value` has a single leaf element, so for RAM it belongs at the FRONT
(small-sparse first). The user's applied storage order (VAR_RPT_Value first,
PDT_MosaicSKU last) measured 69 GB. Fast mode's seed pinned VAR_RPT_Value last
purely because it is dims[-1] in the *presentation* order (the "Measures last"
build convention, which the guide says is for usability only). That evicted the
true last-dimension winner PDT_MosaicSKU (6,228 leaves) from the last slot — a
direct 90/10-rule violation — and the cube ballooned to 135 GB.

Only the STRING constraint (guide §7) may force a last position. A numeric
measure must be free to sit wherever cardinality wants it. This mirrors what
_compute_suggested_order already does (only string dims are locked last).

Asserts on the produced ORDER, not RAM — no live cube required. The 90/10 rule
is the deterministic bridge from "PDT off the last slot" to "~2x memory".
"""
from tests.test_fold_a import make_main_executor


# Leaf counts as shown on the cube's Overview tab. VAR_RPT_Value is the measure
# and is last in PRESENTATION order (the immutable build order); the middle order
# is irrelevant since the seed re-sorts by cardinality.
CARD = {
    "VAR_RPT_Value": 1,
    "MU_Country": 2,
    "VAR_RPT_Layers_Weekly": 6,
    "HFM_ParentEntity": 9,
    "CURR_TopLines": 9,
    "EntityType": 11,
    "TIME_Months": 12,
    "GTM_Plan_Full": 29,
    "SCENARIO_All": 81,
    "VAR_LocalTopLines": 191,
    "TIME_Weeks_Continuous": 213,
    "CUST_Plan_Full": 313,
    "LO_Plan_Full": 313,
    "PDT_MosaicSKU_DoubleView_Component": 6228,
}
# Presentation order: measure (VAR_RPT_Value) last, per the TM1 build convention.
PRESENTATION_ORDER = [
    "MU_Country", "VAR_RPT_Layers_Weekly", "HFM_ParentEntity", "CURR_TopLines",
    "EntityType", "TIME_Months", "GTM_Plan_Full", "SCENARIO_All",
    "VAR_LocalTopLines", "TIME_Weeks_Continuous", "CUST_Plan_Full", "LO_Plan_Full",
    "PDT_MosaicSKU_DoubleView_Component", "VAR_RPT_Value",
]


def test_seed_does_not_force_numeric_measure_last():
    # All dimensions are numeric-only, so measure_only_numeric=True (the flag is
    # derived from the storage-order last dim, PDT, which is numeric).
    ex = make_main_executor(PRESENTATION_ORDER, CARD, fast=True, measure_only_numeric=True)

    seed = ex._seed_order()

    # 90/10 rule: the largest-dense dim must take the last slot, not the 1-leaf measure.
    assert seed[-1] == "PDT_MosaicSKU_DoubleView_Component", (
        f"largest dim must be last; got {seed[-1]!r}. Full seed: {seed}")
    # A 1-leaf numeric measure belongs at the front for RAM (small-sparse first),
    # never pinned to the highest-impact last slot.
    assert seed[0] == "VAR_RPT_Value", (
        f"1-leaf measure must lead; got {seed[0]!r}. Full seed: {seed}")
    # The corrected seed is exactly pure cardinality-ascending (no string dims here).
    assert seed == sorted(PRESENTATION_ORDER, key=CARD.get), f"seed not cardinality-ascending: {seed}"
