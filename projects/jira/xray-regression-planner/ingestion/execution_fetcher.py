"""
execution_fetcher.py — Fetch past execution history from XRay.
"""

from __future__ import annotations

from typing import Any

import structlog

from models.execution import ExecutionRun
from models.test_case import TestCase

logger = structlog.get_logger(__name__)


def _parse_run(raw: dict[str, Any], execution_key: str) -> ExecutionRun:
    """Parse a raw XRay test run into an ExecutionRun."""
    status = ""
    status_data = raw.get("status", {})
    if isinstance(status_data, dict):
        status = status_data.get("name", "")

    test_key = ""
    test_data = raw.get("test", {})
    if isinstance(test_data, dict):
        jira = test_data.get("jira", {}) or {}
        if isinstance(jira, dict):
            test_key = jira.get("key", "")

    return ExecutionRun(
        test_key=test_key,
        status=status,
        execution_key=execution_key,
        started_on=raw.get("startedOn") or "",
        finished_on=raw.get("finishedOn") or "",
        comment=raw.get("comment", "") or "",
    )


async def fetch_execution_history(
    xray_client: Any,
    execution_keys: list[str],
) -> list[ExecutionRun]:
    """Fetch all test runs from the given execution keys."""
    all_runs: list[ExecutionRun] = []

    for exec_key in execution_keys:
        if not exec_key:
            continue
        try:
            raw_runs = await xray_client.get_test_runs(exec_key)
            for raw in raw_runs:
                run = _parse_run(raw, exec_key)
                if run.test_key:
                    all_runs.append(run)
        except Exception as e:
            logger.error("execution.fetch_error", key=exec_key, error=str(e))

    logger.info("execution.all_fetched", total=len(all_runs), keys=len(execution_keys))
    return all_runs


def enrich_tests_with_history(tests: list[TestCase], runs: list[ExecutionRun]) -> None:
    """Attach execution history to test cases."""
    # Build lookup: test_key → list of runs
    run_map: dict[str, list[ExecutionRun]] = {}
    for run in runs:
        run_map.setdefault(run.test_key, []).append(run)

    for test in tests:
        test_runs = run_map.get(test.key, [])
        if not test_runs:
            continue

        test.total_runs = len(test_runs)
        test.fail_count = sum(1 for r in test_runs if r.status.upper() in ("FAIL", "FAILED"))
        test.pass_count = sum(1 for r in test_runs if r.status.upper() in ("PASS", "PASSED"))

        # Sort by date descending to get latest
        sorted_runs = sorted(test_runs, key=lambda r: r.finished_on or r.started_on, reverse=True)
        if sorted_runs:
            test.last_status = sorted_runs[0].status
            test.last_execution_date = sorted_runs[0].finished_on or sorted_runs[0].started_on

        # Flaky detection: alternating pass/fail
        if test.total_runs >= 3 and test.fail_count >= 1 and test.pass_count >= 1:
            flaky_ratio = min(test.fail_count, test.pass_count) / test.total_runs
            test.flaky = flaky_ratio >= 0.25

    enriched = sum(1 for t in tests if t.total_runs > 0)
    logger.info("execution.enriched", enriched=enriched, total=len(tests))
