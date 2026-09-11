"""
jira_client.py — Jira Cloud REST API wrapper.

Handles:
- Paginated search via JQL / filter ID
- Retry with exponential backoff on 429/502/503
- Fail-fast on 401/403/404
- Issue creation and update
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx
import structlog

from client.auth import JiraCredentials

logger = structlog.get_logger(__name__)

# Retry config
MAX_RETRIES = 3
RETRY_STATUS_CODES = {429, 502, 503}
FAIL_FAST_CODES = {401, 403, 404}


@runtime_checkable
class JiraConnector(Protocol):
    """Swap CSV loader here for offline/dev mode."""

    async def search_issues(
        self,
        jql: str,
        fields: list[str],
        max_results_per_page: int,
    ) -> list[dict[str, Any]]:
        ...


class JiraClient:
    """Live Jira Cloud REST API client."""

    def __init__(self, credentials: JiraCredentials, client: httpx.AsyncClient) -> None:
        self._creds = credentials
        self._client = client

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._creds.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request with retry logic."""
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await self._client.request(
                    method, url, headers=self._headers, timeout=30.0, **kwargs
                )

                if resp.status_code in FAIL_FAST_CODES:
                    logger.error(
                        "jira.request.fail_fast",
                        status=resp.status_code,
                        url=url,
                        body=resp.text[:300],
                    )
                    raise httpx.HTTPStatusError(
                        f"Jira {resp.status_code}: {resp.text[:200]}",
                        request=resp.request,
                        response=resp,
                    )

                if resp.status_code in RETRY_STATUS_CODES:
                    wait = 2**attempt
                    logger.warning(
                        "jira.request.retrying",
                        status=resp.status_code,
                        attempt=attempt,
                        wait_seconds=wait,
                    )
                    import asyncio
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError:
                raise
            except Exception as exc:
                last_exc = exc
                wait = 2**attempt
                logger.warning(
                    "jira.request.error_retry",
                    error=str(exc),
                    attempt=attempt,
                    wait_seconds=wait,
                )
                import asyncio
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"Jira request failed after {MAX_RETRIES} retries: {last_exc}"
        )

    async def get_filter_jql(self, filter_id: int) -> str:
        """Fetch the JQL string from a Jira saved filter."""
        url = f"{self._creds.base_url}/rest/api/3/filter/{filter_id}"
        resp = await self._request_with_retry("GET", url)
        data = resp.json()
        jql = data.get("jql", "")
        logger.info("jira.filter.fetched", filter_id=filter_id, jql=jql[:120])
        return jql

    async def search_issues(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results_per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """Paginated Jira search using the enhanced JQL search endpoint."""
        if fields is None:
            fields = [
                "summary", "components", "labels", "issuetype",
                "status", "priority", "fixVersions", "subtasks", "parent",
            ]

        all_issues: list[dict[str, Any]] = []
        next_page_token: str | None = None

        while True:
            url = f"{self._creds.base_url}/rest/api/3/search/jql"
            payload: dict[str, Any] = {
                "jql": jql,
                "fields": fields,
                "maxResults": max_results_per_page,
                "fieldsByKeys": False,
            }
            if next_page_token:
                payload["nextPageToken"] = next_page_token

            resp = await self._request_with_retry("POST", url, json=payload)
            data = resp.json()

            issues = data.get("issues", [])
            all_issues.extend(issues)
            next_page_token = data.get("nextPageToken")
            is_last = bool(data.get("isLast", False))

            logger.debug(
                "jira.search.page",
                fetched=len(issues),
                total_so_far=len(all_issues),
                is_last=is_last,
                next_page_token=bool(next_page_token),
            )

            if is_last or not issues or not next_page_token:
                break

        logger.info(
            "jira.search.complete",
            jql=jql[:100],
            total_issues=len(all_issues),
        )
        return all_issues

    async def search_by_filter(
        self,
        filter_id: int,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all issues from a Jira saved filter."""
        jql = await self.get_filter_jql(filter_id)
        return await self.search_issues(jql, fields=fields)

    async def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        labels: list[str] | None = None,
        priority: str = "Medium",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new Jira issue (e.g. Test, Story, Bug)."""
        url = f"{self._creds.base_url}/rest/api/3/issue"
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "priority": {"name": priority},
            }
        }
        if labels:
            payload["fields"]["labels"] = labels
        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }

        resp = await self._request_with_retry("POST", url, json=payload)
        data = resp.json()
        logger.info(
            "jira.issue.created",
            key=data.get("key"),
            summary=summary[:80],
        )
        return data

    async def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any],
    ) -> None:
        """Update fields on an existing Jira issue."""
        url = f"{self._creds.base_url}/rest/api/3/issue/{issue_key}"
        payload = {"fields": fields}
        await self._request_with_retry("PUT", url, json=payload)
        logger.info("jira.issue.updated", key=issue_key, fields=list(fields.keys()))
