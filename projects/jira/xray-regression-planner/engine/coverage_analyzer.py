"""
coverage_analyzer.py — Detect coverage gaps in the regression plan.
"""

from __future__ import annotations

import structlog

from models.scope import ScopeItem, ComponentMetrics
from models.defect import Defect
from models.test_case import TestCase
from models.plan import CoverageGap

logger = structlog.get_logger(__name__)


def detect_coverage_gaps(
    components: dict[str, ComponentMetrics],
    scope_items: list[ScopeItem],
    defects: list[Defect],
    tests: list[TestCase],
) -> list[CoverageGap]:
    """Identify components with missing test coverage."""
    gaps: list[CoverageGap] = []

    # Build sets for quick lookup
    tested_components: set[str] = set()
    for test in tests:
        for comp in (test.components or []):
            tested_components.add(comp)

    bugged_components: set[str] = set()
    for defect in defects:
        for comp in (defect.components or []):
            bugged_components.add(comp)

    for name, cm in components.items():
        # High-risk component with no tests
        if cm.risk_score >= 40 and name not in tested_components:
            gaps.append(CoverageGap(
                component=name,
                gap_type="NO_TESTS",
                details=f"Component '{name}' has risk score {cm.risk_score:.0f} but no test cases cover it.",
            ))

        # Component has bugs but no tests
        if cm.total_bugs > 0 and name not in tested_components:
            if not any(g.component == name and g.gap_type == "NO_TESTS" for g in gaps):
                gaps.append(CoverageGap(
                    component=name,
                    gap_type="NO_BUG_COVERAGE",
                    details=f"Component '{name}' has {cm.total_bugs} bugs but no tests.",
                ))

        # Component in scope with escaped defects but low test coverage
        if cm.escaped_p1p2_count > 0 and cm.test_count < 3:
            gaps.append(CoverageGap(
                component=name,
                gap_type="ESCAPED_LOW_COVERAGE",
                details=f"Component '{name}' has {cm.escaped_p1p2_count} escaped P1/P2 bugs but only {cm.test_count} tests.",
            ))

    logger.info("coverage_analyzer.gaps", count=len(gaps))
    return gaps
