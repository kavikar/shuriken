"""
bug_fetcher.py — Fetch production and non-production bugs from Jira.
"""

from __future__ import annotations

from typing import Any

import structlog

from models.defect import Defect

logger = structlog.get_logger(__name__)

SEVERITY_WEIGHTS = {
    "Highest": 1.0,
    "High": 0.8,
    "Medium": 0.5,
    "Low": 0.2,
    "Lowest": 0.1,
}


def _parse_defect(issue: dict[str, Any], source: str) -> Defect:
    """Parse a raw Jira issue into a Defect."""
    fields = issue.get("fields", {})
    components = [c.get("name", "") for c in (fields.get("components") or [])]
    labels = fields.get("labels") or []
    priority_name = ""
    if fields.get("priority"):
        priority_name = fields["priority"].get("name", "")
    status = ""
    if fields.get("status"):
        status = fields["status"].get("name", "")

    is_escaped = source == "prod" and priority_name in ("Highest", "High")

    return Defect(
        key=issue.get("key", ""),
        summary=fields.get("summary", ""),
        priority=priority_name,
        status=status,
        components=components,
        labels=labels,
        source=source,
        is_escaped=is_escaped,
        severity_weight=SEVERITY_WEIGHTS.get(priority_name, 0.3),
    )


async def fetch_bugs(
    jira_client: Any,
    *,
    filter_id: int | None = None,
    jql: str | None = None,
    source: str = "prod",
) -> list[Defect]:
    """Fetch bugs from Jira — either by filter ID or direct JQL."""
    if jql:
        raw_issues = await jira_client.search_issues(jql)
    elif filter_id:
        raw_issues = await jira_client.search_by_filter(filter_id)
    else:
        logger.warning("bug_fetcher.no_source", source=source)
        return []

    defects = [_parse_defect(issue, source) for issue in raw_issues]
    logger.info("bugs.fetched", source=source, count=len(defects))
    return defects


async def fetch_all_bugs(
    jira_client: Any,
    *,
    prod_filter_id: int | None = None,
    nonprod_filter_id: int | None = None,
    prod_jql: str | None = None,
    nonprod_jql: str | None = None,
) -> list[Defect]:
    """Fetch both prod and non-prod bugs."""
    prod = await fetch_bugs(jira_client, filter_id=prod_filter_id, jql=prod_jql, source="prod")
    nonprod = await fetch_bugs(jira_client, filter_id=nonprod_filter_id, jql=nonprod_jql, source="nonprod")

    all_bugs = prod + nonprod
    logger.info("bugs.all_fetched", prod=len(prod), nonprod=len(nonprod), total=len(all_bugs))
    return all_bugs
