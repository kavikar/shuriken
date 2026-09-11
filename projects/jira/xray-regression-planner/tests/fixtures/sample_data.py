"""Sample data for planner unit tests. All values are fictional."""

from __future__ import annotations

from models.defect import Defect
from models.execution import ExecutionRun
from models.scope import ScopeItem
from models.test_case import Platform, TestCase


# `None` means "use the default"; an explicit [] means "genuinely no
# components", which is a case the aggregation has to handle. Collapsing the
# two with `components or [...]` would make that case untestable.
_DEFAULT_COMPONENTS = ["Checkout"]


def _components(value: list[str] | None) -> list[str]:
    return list(_DEFAULT_COMPONENTS) if value is None else value


def make_test_case(
    key: str = "TE-10001",
    summary: str = "Sample test",
    labels: list[str] | None = None,
    components: list[str] | None = None,
) -> TestCase:
    return TestCase(
        key=key,
        summary=summary,
        labels=labels if labels is not None else [],
        components=_components(components),
    )


def make_scope_item(key: str = "SCOPE-1", components: list[str] | None = None) -> ScopeItem:
    return ScopeItem(
        key=key,
        summary="Sample scope item",
        issue_type="Story",
        components=_components(components),
    )


def make_defect(
    key: str = "BUG-1",
    components: list[str] | None = None,
    source: str = "prod",
    is_escaped: bool = False,
    severity_weight: float = 0.5,
) -> Defect:
    return Defect(
        key=key,
        components=_components(components),
        source=source,
        is_escaped=is_escaped,
        severity_weight=severity_weight,
    )


PLATFORM_LABELS: dict[str, list[str]] = {
    Platform.WEB.value: ["web", "desktop"],
    Platform.MWEB.value: ["mweb", "mobile web"],
    Platform.IOS.value: ["ios", "iphone"],
    Platform.ANDROID.value: ["android", "aos"],
    Platform.THIRDPARTY.value: ["3p", "aggregator"],
}

RISK_WEIGHTS: dict[str, float] = {
    "defect_density": 0.35,
    "escaped_defect": 0.25,
    "churn_frequency": 0.20,
    "change_type": 0.10,
    "severity_weight": 0.10,
}

OVERRIDE_RULES: dict[str, float] = {
    "escaped_p1p2_floor": 85,
    "new_component_floor": 75,
    "stable_component_cap": 30,
}

SAMPLE_TEST_CASES: list[TestCase] = [
    make_test_case("TE-10001", "Guest checkout on web", ["web"], ["Checkout"]),
    make_test_case("TE-10002", "Sign in on android", ["android"], ["Auth"]),
    make_test_case("TE-10003", "Browse menu", [], ["Menu"]),
]

SAMPLE_SCOPE_ITEMS: list[ScopeItem] = [
    make_scope_item("SCOPE-1", ["Checkout"]),
    make_scope_item("SCOPE-2", ["Payments"]),
]

SAMPLE_DEFECTS: list[Defect] = [
    make_defect("BUG-1", ["Checkout"], source="prod", severity_weight=0.8),
    make_defect("BUG-2", ["Payments"], source="prod", is_escaped=True, severity_weight=1.0),
    make_defect("BUG-3", ["Payments"], source="nonprod", severity_weight=0.3),
]

SAMPLE_EXECUTIONS: list[ExecutionRun] = []
