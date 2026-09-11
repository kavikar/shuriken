"""
defect.py — Pydantic model for a Jira defect/bug.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Defect(BaseModel):
    """A Jira bug/defect for risk scoring."""

    key: str = ""
    summary: str = ""
    priority: str = ""
    status: str = ""
    components: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    source: str = ""  # "prod" or "nonprod"
    is_escaped: bool = False
    severity_weight: float = 0.0
