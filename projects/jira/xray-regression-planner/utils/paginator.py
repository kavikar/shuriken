"""
paginator.py — Generic async pagination helper.
"""

from __future__ import annotations

from typing import Any, Callable, Awaitable

import structlog

logger = structlog.get_logger(__name__)


async def paginate(
    fetch_page: Callable[[int], Awaitable[tuple[list[Any], int]]],
    page_size: int = 100,
    max_pages: int = 50,
) -> list[Any]:
    """
    Generic paginator.

    fetch_page(start_at) → (items, total)
    """
    all_items: list[Any] = []
    start_at = 0

    for page_num in range(1, max_pages + 1):
        items, total = await fetch_page(start_at)
        all_items.extend(items)

        logger.debug(
            "paginator.page",
            page=page_num,
            fetched=len(items),
            total_so_far=len(all_items),
            total=total,
        )

        start_at += len(items)
        if start_at >= total or not items:
            break

    return all_items
