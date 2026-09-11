"""Coverage gap detection across components."""

from __future__ import annotations

from engine.coverage_analyzer import detect_coverage_gaps
from engine.risk_scorer import build_component_metrics, score_all_components

from tests.fixtures.sample_data import (
    OVERRIDE_RULES,
    RISK_WEIGHTS,
    make_defect,
    make_scope_item,
    make_test_case,
)


def _gaps(scope_items, defects, tests):
    metrics = build_component_metrics(scope_items, defects, tests, [])
    score_all_components(metrics, defects, RISK_WEIGHTS, OVERRIDE_RULES)
    return metrics, detect_coverage_gaps(metrics, scope_items, defects, tests)


def _types_for(gaps, component):
    return {g.gap_type for g in gaps if g.component == component}


def test_flags_a_high_risk_component_with_no_tests():
    _, gaps = _gaps([make_scope_item("SCOPE-1", ["Payments"])], [], [])
    assert "NO_TESTS" in _types_for(gaps, "Payments")


def test_does_not_flag_a_component_that_has_tests():
    _, gaps = _gaps(
        [make_scope_item("SCOPE-1", ["Checkout"])],
        [],
        [make_test_case("TE-10001", components=["Checkout"])],
    )
    assert _types_for(gaps, "Checkout") == set()


def test_flags_escaped_defects_with_thin_coverage():
    # Two tests is below the threshold of three: the component has already
    # leaked a defect to production and is still barely covered.
    defects = [make_defect("BUG-1", ["Payments"], is_escaped=True)]
    tests = [
        make_test_case("TE-10001", components=["Payments"]),
        make_test_case("TE-10002", components=["Payments"]),
    ]
    _, gaps = _gaps([], defects, tests)
    assert "ESCAPED_LOW_COVERAGE" in _types_for(gaps, "Payments")


def test_does_not_flag_escaped_defects_with_adequate_coverage():
    defects = [make_defect("BUG-1", ["Payments"], is_escaped=True)]
    tests = [make_test_case(f"TE-1000{i}", components=["Payments"]) for i in range(1, 5)]
    _, gaps = _gaps([], defects, tests)
    assert "ESCAPED_LOW_COVERAGE" not in _types_for(gaps, "Payments")


def test_does_not_report_no_tests_twice_for_one_component():
    # A component that is both high-risk and bug-ridden satisfies two rules;
    # reporting it twice would inflate the gap count a reviewer reads.
    defects = [make_defect("BUG-1", ["Payments"])]
    _, gaps = _gaps([make_scope_item("SCOPE-1", ["Payments"])], defects, [])
    no_tests = [g for g in gaps if g.component == "Payments" and g.gap_type == "NO_TESTS"]
    assert len(no_tests) == 1


def test_every_gap_carries_an_explanation():
    _, gaps = _gaps([make_scope_item("SCOPE-1", ["Payments"])], [], [])
    assert gaps
    assert all(g.details for g in gaps)


def test_no_components_means_no_gaps():
    _, gaps = _gaps([], [], [])
    assert gaps == []
