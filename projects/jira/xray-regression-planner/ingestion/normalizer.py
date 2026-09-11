"""
normalizer.py — Normalize raw Jira/XRay data into internal models.

This module provides helper functions for edge-case normalization
(empty components, label deduplication, etc.).
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

UNCATEGORIZED = "Uncategorized"


def normalize_component_name(name: str) -> str:
    """Strip whitespace, lowercase, dedup."""
    return name.strip() or UNCATEGORIZED


def normalize_labels(labels: list[str]) -> list[str]:
    """Deduplicate and lowercase labels."""
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        lower = label.strip().lower()
        if lower and lower not in seen:
            seen.add(lower)
            result.append(label.strip())
    return result
