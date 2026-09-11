"""
scope.py — Pydantic models for Jira scope items and component metrics.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScopeItem(BaseModel):
    """A Jira issue in the release scope."""

    key: str = ""
    summary: str = ""
    issue_type: str = ""
    status: str = ""
    priority: str = ""
    components: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    fix_versions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ComponentMetrics(BaseModel):
    """Aggregated risk metrics for a single component."""

    name: str = ""
    scope_item_count: int = 0
    total_bugs: int = 0
    prod_bugs: int = 0
    nonprod_bugs: int = 0
    escaped_p1p2_count: int = 0
    churn_frequency: int = 0
    test_count: int = 0
    risk_score: float = 0.0
    overrides_applied: list[str] = Field(default_factory=list)

    # Sub-scores
    defect_density_score: float = 0.0
    escaped_defect_score: float = 0.0
    churn_score: float = 0.0
    change_type_score: float = 0.0
    severity_score: float = 0.0
