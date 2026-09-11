"""
risk_scorer.py — Build component metrics and compute risk scores.
"""

from __future__ import annotations

from typing import Any

import structlog

from models.scope import ScopeItem, ComponentMetrics
from models.defect import Defect
from models.test_case import TestCase
from models.execution import ExecutionRun

logger = structlog.get_logger(__name__)


def build_component_metrics(
    scope_items: list[ScopeItem],
    defects: list[Defect],
    tests: list[TestCase],
    executions: list[ExecutionRun],
) -> dict[str, ComponentMetrics]:
    """Aggregate scope, bugs, tests into per-component metrics."""
    metrics: dict[str, ComponentMetrics] = {}

    def _ensure(name: str) -> ComponentMetrics:
        if name not in metrics:
            metrics[name] = ComponentMetrics(name=name)
        return metrics[name]

    # Scope items → scope_item_count, churn
    for item in scope_items:
        comps = item.components or ["Uncategorized"]
        for c in comps:
            m = _ensure(c)
            m.scope_item_count += 1
            m.churn_frequency += 1

    # Defects → bug counts
    for defect in defects:
        comps = defect.components or ["Uncategorized"]
        for c in comps:
            m = _ensure(c)
            m.total_bugs += 1
            if defect.source == "prod":
                m.prod_bugs += 1
            else:
                m.nonprod_bugs += 1
            if defect.is_escaped:
                m.escaped_p1p2_count += 1

    # Tests → test count per component
    for test in tests:
        comps = test.components or ["Uncategorized"]
        for c in comps:
            m = _ensure(c)
            m.test_count += 1

    logger.info("risk_scorer.metrics_built", component_count=len(metrics))
    return metrics


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def score_all_components(
    metrics: dict[str, ComponentMetrics],
    defects: list[Defect],
    risk_weights: dict[str, float],
    override_rules: dict[str, Any],
) -> None:
    """Compute risk scores for all components using weighted formula + overrides."""
    max_scope = max((m.scope_item_count for m in metrics.values()), default=1) or 1
    max_bugs = max((m.total_bugs for m in metrics.values()), default=1) or 1
    max_churn = max((m.churn_frequency for m in metrics.values()), default=1) or 1
    max_tests = max((m.test_count for m in metrics.values()), default=1) or 1

    w_dd = risk_weights.get("defect_density", 0.35)
    w_ed = risk_weights.get("escaped_defect", 0.25)
    w_cf = risk_weights.get("churn_frequency", 0.20)
    w_ct = risk_weights.get("change_type", 0.10)
    w_sv = risk_weights.get("severity_weight", 0.10)

    escaped_floor = override_rules.get("escaped_p1p2_floor", 85)
    new_comp_floor = override_rules.get("new_component_floor", 75)
    stable_cap = override_rules.get("stable_component_cap", 30)

    # Compute avg severity per component
    comp_severity: dict[str, float] = {}
    for defect in defects:
        for c in (defect.components or ["Uncategorized"]):
            comp_severity.setdefault(c, []).append(defect.severity_weight)

    for name, m in metrics.items():
        # Normalized sub-scores (0–100 scale)
        m.defect_density_score = _clamp(m.total_bugs / max_bugs * 100)
        m.escaped_defect_score = _clamp(m.escaped_p1p2_count * 25)  # 4+ escaped = 100
        m.churn_score = _clamp(m.churn_frequency / max_churn * 100)
        m.change_type_score = _clamp(m.scope_item_count / max_scope * 100)

        sev_list = comp_severity.get(name, [])
        m.severity_score = _clamp((sum(sev_list) / len(sev_list) * 100) if sev_list else 30)

        # Weighted risk score
        raw_score = (
            w_dd * m.defect_density_score
            + w_ed * m.escaped_defect_score
            + w_cf * m.churn_score
            + w_ct * m.change_type_score
            + w_sv * m.severity_score
        )
        m.risk_score = _clamp(raw_score)

        # Override rules
        if m.escaped_p1p2_count > 0 and m.risk_score < escaped_floor:
            m.risk_score = escaped_floor
            m.overrides_applied.append(f"escaped_p1p2_floor→{escaped_floor}")

        if m.scope_item_count > 0 and m.total_bugs == 0 and m.test_count == 0:
            if m.risk_score < new_comp_floor:
                m.risk_score = new_comp_floor
                m.overrides_applied.append(f"new_component_floor→{new_comp_floor}")

        if m.scope_item_count == 0 and m.total_bugs == 0 and m.risk_score > stable_cap:
            m.risk_score = stable_cap
            m.overrides_applied.append(f"stable_component_cap→{stable_cap}")

    logger.info("risk_scorer.scored", component_count=len(metrics))
