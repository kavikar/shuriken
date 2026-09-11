"""Component metric aggregation and weighted risk scoring."""

from __future__ import annotations

from engine.risk_scorer import build_component_metrics, score_all_components

from tests.fixtures.sample_data import (
    OVERRIDE_RULES,
    RISK_WEIGHTS,
    SAMPLE_DEFECTS,
    SAMPLE_SCOPE_ITEMS,
    SAMPLE_TEST_CASES,
    make_defect,
    make_scope_item,
    make_test_case,
)


def _metrics():
    return build_component_metrics(
        SAMPLE_SCOPE_ITEMS, SAMPLE_DEFECTS, SAMPLE_TEST_CASES, []
    )


def test_aggregates_every_component_that_appears_anywhere():
    metrics = _metrics()
    # Components arrive from three independent sources; a component named only
    # by a defect still has to exist, or its risk never gets scored.
    assert {"Checkout", "Payments", "Auth", "Menu"} <= set(metrics)


def test_counts_scope_items_and_churn_per_component():
    metrics = _metrics()
    assert metrics["Checkout"].scope_item_count == 1
    assert metrics["Checkout"].churn_frequency == 1


def test_splits_prod_and_nonprod_defects():
    metrics = _metrics()
    payments = metrics["Payments"]
    assert payments.total_bugs == 2
    assert payments.prod_bugs == 1
    assert payments.nonprod_bugs == 1


def test_counts_escaped_defects_separately():
    metrics = _metrics()
    assert metrics["Payments"].escaped_p1p2_count == 1
    assert metrics["Checkout"].escaped_p1p2_count == 0


def test_uncategorized_absorbs_items_with_no_component():
    metrics = build_component_metrics(
        [make_scope_item("SCOPE-9", components=[])], [], [], []
    )
    assert "Uncategorized" in metrics


def test_scores_stay_within_bounds():
    metrics = _metrics()
    score_all_components(metrics, SAMPLE_DEFECTS, RISK_WEIGHTS, OVERRIDE_RULES)
    assert all(0.0 <= m.risk_score <= 100.0 for m in metrics.values())


def test_escaped_defect_raises_the_score_to_the_floor():
    # One escaped production defect is the signal that matters most; the floor
    # exists so a component cannot be scored low just because it is quiet.
    metrics = build_component_metrics(
        [], [make_defect("BUG-9", ["Payments"], is_escaped=True, severity_weight=0.1)], [], []
    )
    score_all_components(metrics, [], RISK_WEIGHTS, OVERRIDE_RULES)

    payments = metrics["Payments"]
    assert payments.risk_score >= OVERRIDE_RULES["escaped_p1p2_floor"]
    assert any("escaped_p1p2_floor" in o for o in payments.overrides_applied)


def test_new_untested_component_gets_the_new_component_floor():
    # Changed, no bugs yet, no tests at all — the riskiest shape there is,
    # and the one a purely defect-driven score would rank lowest.
    metrics = build_component_metrics([make_scope_item("SCOPE-9", ["Brand New"])], [], [], [])
    score_all_components(metrics, [], RISK_WEIGHTS, OVERRIDE_RULES)

    component = metrics["Brand New"]
    assert component.risk_score >= OVERRIDE_RULES["new_component_floor"]
    assert any("new_component_floor" in o for o in component.overrides_applied)


def test_a_component_with_tests_does_not_get_the_new_component_floor():
    metrics = build_component_metrics(
        [make_scope_item("SCOPE-9", ["Settled"])],
        [],
        [make_test_case("TE-10009", components=["Settled"])],
        [],
    )
    score_all_components(metrics, [], RISK_WEIGHTS, OVERRIDE_RULES)

    assert not any("new_component_floor" in o for o in metrics["Settled"].overrides_applied)


def test_records_which_overrides_fired():
    metrics = _metrics()
    score_all_components(metrics, SAMPLE_DEFECTS, RISK_WEIGHTS, OVERRIDE_RULES)
    # Traceability: a reviewer has to be able to see why a score is what it is.
    assert all(isinstance(m.overrides_applied, list) for m in metrics.values())


def test_handles_no_components_without_dividing_by_zero():
    metrics = build_component_metrics([], [], [], [])
    score_all_components(metrics, [], RISK_WEIGHTS, OVERRIDE_RULES)
    assert metrics == {}
