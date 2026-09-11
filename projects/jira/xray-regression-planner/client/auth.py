"""
auth.py — Credential loading from .env files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from base64 import b64encode

from dotenv import load_dotenv
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class JiraCredentials:
    base_url: str = ""
    email: str = ""
    api_token: str = ""
    project_key: str = "IQE"

    @property
    def auth_header(self) -> str:
        token = b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return f"Basic {token}"


@dataclass
class XrayCredentials:
    client_id: str = ""
    client_secret: str = ""


def load_credentials(env_path: Path | None = None) -> tuple[JiraCredentials, XrayCredentials]:
    """Load Jira + XRay credentials from .env file or environment."""
    if env_path and env_path.exists():
        load_dotenv(env_path, override=True)
        logger.info("auth.env_loaded", path=str(env_path))
    else:
        # Try default .env in project root
        default_env = Path(__file__).parent.parent / ".env"
        if default_env.exists():
            load_dotenv(default_env, override=True)
            logger.info("auth.env_loaded", path=str(default_env))

    jira = JiraCredentials(
        base_url=os.getenv("JIRA_BASE_URL", "https://your-tenant.atlassian.net"),
        email=os.getenv("JIRA_EMAIL", ""),
        api_token=os.getenv("JIRA_API_TOKEN", ""),
        project_key=os.getenv("JIRA_PROJECT_KEY", "IQE"),
    )
    xray = XrayCredentials(
        client_id=os.getenv("XRAY_CLIENT_ID", ""),
        client_secret=os.getenv("XRAY_CLIENT_SECRET", ""),
    )

    if not jira.email or not jira.api_token:
        logger.warning("auth.jira_missing", hint="Set JIRA_EMAIL and JIRA_API_TOKEN")
    if not xray.client_id or not xray.client_secret:
        logger.warning("auth.xray_missing", hint="Set XRAY_CLIENT_ID and XRAY_CLIENT_SECRET")

    return jira, xray
