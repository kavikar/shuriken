"""
xray_client.py — XRay Cloud REST API wrapper.

Handles:
- Authentication (client credentials → bearer token)
- Test set → test case retrieval via GraphQL
- Execution history via GraphQL
- Execution creation via REST import
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from client.auth import XrayCredentials

logger = structlog.get_logger(__name__)

XRAY_AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
XRAY_GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
XRAY_IMPORT_EXECUTION_URL = "https://xray.cloud.getxray.app/api/v2/import/execution"

MAX_RETRIES = 3
RETRY_STATUS_CODES = {429, 502, 503}


class XrayClient:
    """XRay Cloud API client with GraphQL + REST support."""

    def __init__(self, credentials: XrayCredentials, client: httpx.AsyncClient) -> None:
        self._creds = credentials
        self._client = client
        self._token: str | None = None

    async def _ensure_token(self) -> str:
        """Authenticate and cache the bearer token."""
        if self._token:
            return self._token

        resp = await self._client.post(
            XRAY_AUTH_URL,
            json={
                "client_id": self._creds.client_id,
                "client_secret": self._creds.client_secret,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        self._token = resp.json()  # XRay returns the raw token string
        if isinstance(self._token, str):
            self._token = self._token.strip('"')
        logger.info("xray.auth.success")
        return self._token

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute HTTP request with bearer auth and retry logic."""
        token = await self._ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await self._client.request(
                    method, url, headers=headers, timeout=30.0, **kwargs
                )

                if resp.status_code in RETRY_STATUS_CODES:
                    wait = 2**attempt
                    logger.warning("xray.request.retrying", status=resp.status_code, attempt=attempt)
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
                logger.warning("xray.request.error_retry", error=str(exc), attempt=attempt)
                import asyncio
                await asyncio.sleep(wait)

        raise RuntimeError(f"XRay request failed after {MAX_RETRIES} retries: {last_exc}")

    async def graphql(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        """Execute a GraphQL query against XRay Cloud."""
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables

        resp = await self._request_with_retry("POST", XRAY_GRAPHQL_URL, json=body)
        data = resp.json()

        if "errors" in data:
            logger.error("xray.graphql.errors", errors=data["errors"])
            raise RuntimeError(f"XRay GraphQL errors: {data['errors']}")

        return data.get("data", {})

    async def get_tests_in_test_set(self, test_set_key: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch all tests in a test set via GraphQL with pagination."""
        all_tests: list[dict[str, Any]] = []
        start = 0
        has_more = True

        while has_more:
            query = """
            query($jql: String!, $limit: Int!, $start: Int!) {
                getTests(jql: $jql, limit: $limit, start: $start) {
                    total
                    results {
                        issueId
                        jira(fields: ["key", "summary", "labels", "components"])
                    }
                }
            }
            """
            variables = {
                "jql": f"issue in testSetTests('{test_set_key}')",
                "limit": limit,
                "start": start,
            }

            data = await self.graphql(query, variables)
            results_data = data.get("getTests", {})
            results = results_data.get("results", [])
            total = results_data.get("total", 0)

            all_tests.extend(results)
            start += len(results)
            has_more = start < total and len(results) > 0

            logger.debug(
                "xray.testset.page",
                test_set=test_set_key,
                fetched=len(results),
                total_so_far=len(all_tests),
                total=total,
            )

        logger.info(
            "xray.testset.fetched",
            test_set=test_set_key,
            test_count=len(all_tests),
        )
        return all_tests

    async def get_tests_by_jql(self, jql: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch tests using a JQL expression via GraphQL with pagination."""
        all_tests: list[dict[str, Any]] = []
        start = 0
        has_more = True

        while has_more:
            query = """
            query($jql: String!, $limit: Int!, $start: Int!) {
                getTests(jql: $jql, limit: $limit, start: $start) {
                    total
                    results {
                        issueId
                        jira(fields: ["key", "summary", "labels", "components"])
                    }
                }
            }
            """
            variables = {
                "jql": jql,
                "limit": limit,
                "start": start,
            }

            data = await self.graphql(query, variables)
            results_data = data.get("getTests", {})
            results = results_data.get("results", [])
            total = results_data.get("total", 0)

            all_tests.extend(results)
            start += len(results)
            has_more = start < total and len(results) > 0

            logger.debug(
                "xray.tests_by_jql.page",
                jql=jql,
                fetched=len(results),
                total_so_far=len(all_tests),
                total=total,
            )

        logger.info("xray.tests_by_jql.fetched", jql=jql, test_count=len(all_tests))
        return all_tests

    async def get_test_runs(self, execution_key: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch test runs from an execution via GraphQL with pagination."""
        all_runs: list[dict[str, Any]] = []
        start = 0
        has_more = True

        while has_more:
            query = """
            query($jql: String!, $limit: Int!, $start: Int!) {
                getTestExecutions(jql: $jql, limit: 1) {
                    results {
                        issueId
                        testRuns(limit: $limit, start: $start) {
                            total
                            results {
                                status { name }
                                test { issueId jira(fields: ["key"]) }
                                startedOn
                                finishedOn
                                comment
                            }
                        }
                    }
                }
            }
            """
            variables = {
                "jql": f"key = '{execution_key}'",
                "limit": limit,
                "start": start,
            }

            data = await self.graphql(query, variables)
            execs = data.get("getTestExecutions", {}).get("results", [])
            if not execs:
                break

            runs_data = execs[0].get("testRuns", {})
            runs = runs_data.get("results", [])
            total = runs_data.get("total", 0)

            all_runs.extend(runs)
            start += len(runs)
            has_more = start < total and len(runs) > 0

        logger.info(
            "xray.execution.fetched",
            key=execution_key,
            run_count=len(all_runs),
        )
        return all_runs

    async def create_execution(
        self,
        test_issue_ids: list[str],
        summary: str,
        project_key: str,
        labels: list[str] | None = None,
        test_plan_key: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Test Execution via XRay REST import."""
        info: dict[str, Any] = {
            "project": project_key,
            "summary": summary,
        }
        if labels:
            info["labels"] = labels

        body: dict[str, Any] = {
            "info": info,
            "tests": [{"testKey": tid} for tid in test_issue_ids],
        }

        if test_plan_key:
            body["testPlanKey"] = test_plan_key

        resp = await self._request_with_retry(
            "POST", XRAY_IMPORT_EXECUTION_URL, json=body
        )
        result = resp.json()
        logger.info(
            "xray.execution.created",
            key=result.get("key"),
            summary=summary,
            test_count=len(test_issue_ids),
        )
        return result
