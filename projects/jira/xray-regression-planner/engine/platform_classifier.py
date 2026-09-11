"""
platform_classifier.py — Assign platforms to test cases based on labels/summary.
"""

from __future__ import annotations

import structlog

from models.test_case import TestCase, Platform

logger = structlog.get_logger(__name__)


def classify_platforms(
    tests: list[TestCase],
    platform_labels: dict[str, list[str]],
) -> None:
    """Assign platform(s) to each test based on labels and summary keywords."""
    classified = 0
    for test in tests:
        combined = " ".join(test.labels).lower() + " " + (test.summary or "").lower()
        platforms: list[Platform] = []

        for plat_name, keywords in platform_labels.items():
            if any(kw in combined for kw in keywords):
                try:
                    platforms.append(Platform(plat_name))
                except ValueError:
                    pass

        if platforms:
            test.platforms = platforms
            classified += 1
        else:
            test.platforms = [Platform.UNKNOWN]

    logger.info(
        "platform_classifier.done",
        classified=classified,
        unknown=len(tests) - classified,
        total=len(tests),
    )
