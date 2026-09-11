"""
plan.py — Pydantic models for the regression plan output.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from models.test_case import Platform, TestCase
from models.scope import ComponentMetrics


class Tier(str, Enum):
    TIER1 = "TIER 1 — MUST RUN"
    TIER2 = "TIER 2 — SHOULD RUN"
    TIER3 = "TIER 3 — NICE TO HAVE"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PlatformExecution(BaseModel):
    """Planned execution for a single platform."""

    platform: Platform
    summary: str = ""
    tests: list[TestCase] = Field(default_factory=list)
    tier1_count: int = 0
    tier2_count: int = 0
    tier3_count: int = 0
    estimated_minutes: int = 0

    # Populated after XRay creation
    created_key: str | None = None
    jira_url: str | None = None


class ExcludedTest(BaseModel):
    """A test that was excluded from all executions."""

    key: str
    summary: str = ""
    reason: str = ""  # LOW_RISK, STABLE_COMPONENT, DUPLICATE_IN_EXECUTION


class CoverageGap(BaseModel):
    """A component with missing coverage."""

    component: str
    gap_type: str = ""  # NO_TESTS, NO_BUG_LINKS, NO_COMPONENT_TESTS
    details: str = ""


class BudgetAnalysis(BaseModel):
    """Analysis of selected tests vs target budget."""

    target_count: int = 0
    actual_count: int = 0
    delta: int = 0  # positive = over budget, negative = under
    utilization_pct: float = 0.0  # actual / target * 100
    tier1_count: int = 0
    tier2_count: int = 0
    tier3_count: int = 0
    recommendation: str = ""
    platform_breakdown: list[dict] = Field(default_factory=list)


class RegressionPlan(BaseModel):
    """The complete regression plan — all platforms, all tiers."""

    release_name: str = ""
    analyst: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)
    tool_version: str = "1.0.0"
    brand: str = "brand3"

    # Input references
    scope_filter_id: int = 0
    prod_bug_filter_id: int = 0
    nonprod_bug_filter_id: int = 0
    scope_jql: str = ""
    prod_bug_jql: str = ""
    nonprod_bug_jql: str = ""
    test_set_keys: list[str] = Field(default_factory=list)
    prev_execution_keys: list[str] = Field(default_factory=list)
    selected_platforms: list[str] = Field(default_factory=list)
    platform_weights: dict[str, int] = Field(default_factory=dict)

    # Metrics
    total_scope_items: int = 0
    total_bugs: int = 0
    total_test_cases: int = 0
    total_selected: int = 0

    # Component risk heatmap
    component_metrics: list[ComponentMetrics] = Field(default_factory=list)

    # Platform execution plans
    executions: list[PlatformExecution] = Field(default_factory=list)

    # Gaps and exclusions
    excluded_tests: list[ExcludedTest] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)

    # Confidence
    confidence_level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    confidence_details: str | dict = ""

    # Warnings
    warnings: list[str] = Field(default_factory=list)

    # Budget / target analysis
    target_test_count: int = 0
    budget_analysis: BudgetAnalysis | None = None

    # Core functional coverage
    core_coverage: list[dict] = Field(default_factory=list)

    # Suggested test cases (gaps in core coverage)
    suggested_tests: list[dict] = Field(default_factory=list)

    # Audit trail — created execution keys
    created_execution_keys: list[dict[str, str]] = Field(default_factory=list)
