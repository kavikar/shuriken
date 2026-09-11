"""
scope_fetcher.py — Fetch release scope items from Jira.
"""

from __future__ import annotations

from typing import Any

import structlog

from models.scope import ScopeItem

logger = structlog.get_logger(__name__)


def _parse_scope_item(issue: dict[str, Any]) -> ScopeItem:
    """Parse a raw Jira issue into a ScopeItem."""
    fields = issue.get("fields", {})
    components = [c.get("name", "") for c in (fields.get("components") or [])]
    labels = fields.get("labels") or []
    fix_versions = [v.get("name", "") for v in (fields.get("fixVersions") or [])]
    priority = ""
    if fields.get("priority"):
        priority = fields["priority"].get("name", "")
    status = ""
    if fields.get("status"):
        status = fields["status"].get("name", "")
    issue_type = ""
    if fields.get("issuetype"):
        issue_type = fields["issuetype"].get("name", "")

    warnings: list[str] = []
    if not components:
        warnings.append(f"{issue.get('key', '?')} has no components — risk scoring will be degraded.")

    return ScopeItem(
        key=issue.get("key", ""),
        summary=fields.get("summary", ""),
        issue_type=issue_type,
        status=status,
        priority=priority,
        components=components,
        labels=labels,
        fix_versions=fix_versions,
        warnings=warnings,
    )


async def fetch_scope(
    jira_client: Any,
    *,
    filter_id: int | None = None,
    jql: str | None = None,
) -> list[ScopeItem]:
    """
    Fetch all scope items (stories, bugs, tasks) in the release.

    Pass either filter_id or jql directly.
    """
    if jql:
        raw_issues = await jira_client.search_issues(jql)
    elif filter_id:
        raw_issues = await jira_client.search_by_filter(filter_id)
    else:
        logger.warning("scope_fetcher.no_source", hint="Provide filter_id or jql")
        return []

    items = [_parse_scope_item(issue) for issue in raw_issues]
    logger.info("scope.fetched", count=len(items))
    return items
