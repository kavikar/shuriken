"""
testset_fetcher.py — Fetch test cases from XRay test sets.
"""

from __future__ import annotations

from typing import Any

import structlog

from models.test_case import TestCase

logger = structlog.get_logger(__name__)


def _parse_test(raw: dict[str, Any]) -> TestCase:
    """Parse XRay GraphQL test result into a TestCase."""
    jira_data = raw.get("jira", {}) or {}

    key = ""
    summary = ""
    labels: list[str] = []
    components: list[str] = []

    if isinstance(jira_data, dict):
        key = jira_data.get("key", "")
        summary = jira_data.get("summary", "")
        labels = jira_data.get("labels", []) or []
        raw_components = jira_data.get("components", []) or []
        if raw_components and isinstance(raw_components[0], dict):
            components = [c.get("name", "") for c in raw_components]
        else:
            components = [str(c) for c in raw_components]

    return TestCase(
        key=key,
        summary=summary,
        labels=labels,
        components=components,
    )


async def fetch_test_cases(
    xray_client: Any,
    test_set_keys: list[str],
) -> list[TestCase]:
    """Fetch all test cases from the given test sets."""
    all_tests: list[TestCase] = []
    seen_keys: set[str] = set()

    for ts_key in test_set_keys:
        try:
            raw_tests = await xray_client.get_tests_in_test_set(ts_key)
            for raw in raw_tests:
                test = _parse_test(raw)
                if test.key and test.key not in seen_keys:
                    seen_keys.add(test.key)
                    all_tests.append(test)
        except Exception as e:
            logger.error("testset.fetch_error", test_set=ts_key, error=str(e))

    logger.info("testset.all_fetched", total=len(all_tests), sets=len(test_set_keys))
    return all_tests


async def fetch_test_cases_from_filters(
    xray_client: Any,
    filter_ids: list[int],
) -> list[TestCase]:
    """Fetch all test cases from Jira filter IDs via Xray getTests(jql=...)."""
    all_tests: list[TestCase] = []
    seen_keys: set[str] = set()

    for fid in filter_ids:
        try:
            raw_tests = await xray_client.get_tests_by_jql(f"filter = {fid}")
            for raw in raw_tests:
                test = _parse_test(raw)
                if test.key and test.key not in seen_keys:
                    seen_keys.add(test.key)
                    all_tests.append(test)
        except Exception as e:
            logger.error("testset.filter_fetch_error", filter_id=fid, error=str(e))

    logger.info("testset.filters_fetched", total=len(all_tests), filters=len(filter_ids))
    return all_tests


def merge_test_inventories(*inventories: list[TestCase]) -> list[TestCase]:
    """Merge test inventories while preserving first-seen order and deduplicating by key."""
    merged: list[TestCase] = []
    seen_keys: set[str] = set()

    for tests in inventories:
        for test in tests:
            if test.key and test.key not in seen_keys:
                seen_keys.add(test.key)
                merged.append(test)

    return merged
