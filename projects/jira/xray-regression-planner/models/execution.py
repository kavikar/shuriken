"""
execution.py — Pydantic model for XRay test execution runs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionRun(BaseModel):
    """A single test run from a past execution."""

    test_key: str = ""
    status: str = ""  # PASS, FAIL, TODO, EXECUTING
    execution_key: str = ""
    started_on: str = ""
    finished_on: str = ""
    comment: str = ""
