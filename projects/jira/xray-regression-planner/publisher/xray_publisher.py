"""
xray_publisher.py — Publish regression plan to XRay as Test Executions.
"""

from __future__ import annotations

from typing import Any

import structlog

from client.xray_client import XrayClient
from client.jira_client import JiraClient
from models.plan import RegressionPlan, Tier
from models.test_case import Platform

logger = structlog.get_logger(__name__)


async def publish_plan(
    plan: RegressionPlan,
    xray: XrayClient,
    jira: JiraClient,
    project_key: str,
    platforms: list[Platform] | None = None,
    tier1_only: bool = False,
) -> list[dict[str, Any]]:
    """Create XRay Test Executions for each platform in the plan."""
    created: list[dict[str, Any]] = []

    for execution in plan.executions:
        if platforms and execution.platform not in platforms:
            continue

        tests = execution.tests
        if tier1_only:
            tests = [t for t in tests if t.tier == Tier.TIER1.value]

        if not tests:
            continue

        test_keys = [t.key for t in tests]

        try:
            result = await xray.create_execution(
                test_issue_ids=test_keys,
                summary=execution.summary,
                project_key=project_key,
                labels=[plan.release_name.replace(" ", "_"), "Regression", execution.platform.value],
            )
            created.append({
                "platform": execution.platform.value,
                "key": result.get("key", "UNKNOWN"),
                "tests": len(test_keys),
            })
            logger.info(
                "publisher.created",
                platform=execution.platform.value,
                key=result.get("key"),
                tests=len(test_keys),
            )
        except Exception as e:
            created.append({
                "platform": execution.platform.value,
                "error": str(e)[:200],
            })
            logger.error("publisher.failed", platform=execution.platform.value, error=str(e))

    return created
