"""
file_utils.py — YAML config loader + output directory helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_yaml_config(config_path: Path | str | None) -> dict[str, Any]:
    """Load config.yaml; fall back to defaults if missing."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.info("config.loaded", path=str(path))
        return data
    logger.warning("config.not_found", path=str(path))
    return {}


def resolve_output_dir(config_dir: str | None) -> Path:
    """Resolve and create the output directory."""
    base = Path(config_dir) if config_dir else Path(__file__).parent.parent / "output"
    base.mkdir(parents=True, exist_ok=True)
    return base
