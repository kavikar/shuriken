"""
test_case.py — Pydantic model for a single test case.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Platform(str, Enum):
    WEB = "web"
    MWEB = "mweb"
    IOS = "ios"
    ANDROID = "android"
    THIRDPARTY = "thirdparty"
    UNKNOWN = "unknown"


class TestCase(BaseModel):
    """A single XRay test case with risk metadata."""

    key: str = ""
    summary: str = ""
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    platforms: list[Platform] = Field(default_factory=list)
    risk_score: float = 0.0
    tier: str = ""
    tags: list[str] = Field(default_factory=list)

    # Execution history (enriched later)
    last_status: str | None = None
    last_execution_date: str | None = None
    total_runs: int = 0
    fail_count: int = 0
    pass_count: int = 0
    flaky: bool = False

    # Internal
    component_risk_max: float = 0.0
