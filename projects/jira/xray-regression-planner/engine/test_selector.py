"""
test_selector.py — Tier assignment, anti-bias guard, and platform execution building.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

from models.test_case import TestCase, Platform
from models.scope import ComponentMetrics
from models.plan import Tier, PlatformExecution, ExcludedTest

logger = structlog.get_logger(__name__)


def assign_tiers(
    tests: list[TestCase],
    components: dict[str, ComponentMetrics],
    tier1_min: int = 70,
    tier2_min: int = 40,
) -> None:
    """Assign risk tier to each test based on its components' max risk score."""
    for test in tests:
        # Compute max risk score across all components
        max_risk = 0.0
        for comp_name in (test.components or ["Uncategorized"]):
            cm = components.get(comp_name)
            if cm:
                max_risk = max(max_risk, cm.risk_score)

        # Boost for flaky or recently-failed tests
        if test.flaky:
            max_risk = min(100.0, max_risk + 15)
        if test.last_status and test.last_status.upper() in ("FAIL", "FAILED"):
            max_risk = min(100.0, max_risk + 10)

        test.risk_score = max_risk
        test.component_risk_max = max_risk

        if max_risk >= tier1_min:
            test.tier = Tier.TIER1.value
        elif max_risk >= tier2_min:
            test.tier = Tier.TIER2.value
        else:
            test.tier = Tier.TIER3.value

    tier_counts = defaultdict(int)
    for t in tests:
        tier_counts[t.tier] += 1
    logger.info("test_selector.tiers_assigned", **dict(tier_counts))


def apply_anti_bias_guard(
    tests: list[TestCase],
    max_tier1_pct_per_component: float = 0.40,
) -> list[ExcludedTest]:
    """
    Prevent a single component from dominating Tier 1.
    Demotes excess tests to Tier 2 unless risk ≥ 90.
    """
    # Group Tier 1 tests by component
    comp_tier1: dict[str, list[TestCase]] = defaultdict(list)
    total_tier1 = sum(1 for t in tests if t.tier == Tier.TIER1.value)

    for test in tests:
        if test.tier != Tier.TIER1.value:
            continue
        for comp in (test.components or ["Uncategorized"]):
            comp_tier1[comp].append(test)

    max_allowed = max(1, int(total_tier1 * max_tier1_pct_per_component))
    demoted: list[ExcludedTest] = []

    for comp, comp_tests in comp_tier1.items():
        if len(comp_tests) <= max_allowed:
            continue

        # Sort by risk ascending — demote the lowest-risk ones
        sorted_tests = sorted(comp_tests, key=lambda t: t.risk_score)
        excess = len(comp_tests) - max_allowed

        for t in sorted_tests[:excess]:
            if t.risk_score >= 90:
                continue  # Never demote very high risk
            t.tier = Tier.TIER2.value
            demoted.append(ExcludedTest(
                key=t.key,
                summary=t.summary,
                reason=f"ANTI_BIAS: {comp} exceeded {max_tier1_pct_per_component*100:.0f}% of Tier 1",
            ))

    if demoted:
        logger.info("anti_bias.demoted", count=len(demoted))
    return demoted


def build_platform_executions(
    tests: list[TestCase],
    release_name: str,
    avg_mins_per_test: int = 3,
) -> tuple[list[PlatformExecution], list[ExcludedTest]]:
    """
    Group selected tests into per-platform execution plans.
    Returns (executions, excluded_tests).
    """
    platform_tests: dict[Platform, list[TestCase]] = defaultdict(list)
    excluded: list[ExcludedTest] = []

    for test in tests:
        assigned = False
        for plat in test.platforms:
            if plat != Platform.UNKNOWN:
                platform_tests[plat].append(test)
                assigned = True

        if not assigned:
            excluded.append(ExcludedTest(
                key=test.key,
                summary=test.summary,
                reason="NO_PLATFORM: Could not classify to any platform",
            ))

    executions: list[PlatformExecution] = []

    for plat in Platform:
        if plat == Platform.UNKNOWN:
            continue
        plat_tests_list = platform_tests.get(plat, [])
        if not plat_tests_list:
            continue

        # Sort by risk descending
        plat_tests_list.sort(key=lambda t: t.risk_score, reverse=True)

        tier1_count = sum(1 for t in plat_tests_list if t.tier == Tier.TIER1.value)
        tier2_count = sum(1 for t in plat_tests_list if t.tier == Tier.TIER2.value)
        tier3_count = sum(1 for t in plat_tests_list if t.tier == Tier.TIER3.value)
        est_mins = len(plat_tests_list) * avg_mins_per_test

        executions.append(PlatformExecution(
            platform=plat,
            summary=f"{release_name} — {plat.value.upper()} Regression ({len(plat_tests_list)} tests)",
            tests=plat_tests_list,
            tier1_count=tier1_count,
            tier2_count=tier2_count,
            tier3_count=tier3_count,
            estimated_minutes=est_mins,
        ))

    logger.info(
        "test_selector.executions_built",
        platforms=len(executions),
        excluded=len(excluded),
    )
    return executions, excluded
