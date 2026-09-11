"""
copilot_request_parser.py

Parse natural-language Copilot requests into normalized execution intent.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ParsedExecutionRequest:
    raw_prompt: str
    release: str
    brands: tuple[str, ...]
    platforms: tuple[str, ...]
    publish: bool


DEFAULT_BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "Brand One": ("b1", "brand1", "brand1", "Brand One"),
    "B2": ("b2", "Brand Two"),
    "Brand Three": ("b3", "brand3"),
    "Brand Four": ("dnk", "dd", "brand4"),
    "Ignite": ("ignite",),
}

DEFAULT_PLATFORMS: tuple[str, ...] = ("WEB", "MWEB", "IOS_APP", "AOS_APP")


def _normalize_release(prompt: str) -> str | None:
    # Supports: 26.12, Digital 26.12, release 26.12
    m = re.search(r"(?i)(?:digital\s*)?(\d{2}\.\d{1,2})", prompt)
    if not m:
        return None
    return f"Digital {m.group(1)}"


def _extract_brands(prompt: str, aliases: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    text = prompt.lower()
    matched: list[str] = []

    for brand, keys in aliases.items():
        if any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in keys):
            matched.append(brand)

    if "all brands" in text and not matched:
        return tuple(sorted(aliases.keys()))

    return tuple(sorted(set(matched)))


def _extract_platforms(prompt: str) -> tuple[str, ...]:
    text = prompt.lower()
    selected: list[str] = []

    if any(k in text for k in ["web", "desktop"]):
        selected.append("WEB")
    if any(k in text for k in ["mweb", "mobile web", "mobile-web"]):
        selected.append("MWEB")
    if any(k in text for k in ["ios", "iphone"]):
        selected.append("IOS_APP")
    if any(k in text for k in ["android", "aos"]):
        selected.append("AOS_APP")

    return tuple(sorted(set(selected))) if selected else DEFAULT_PLATFORMS


def _extract_publish_mode(prompt: str) -> bool:
    text = prompt.lower()
    # Anything explicitly saying dry-run/no publish disables publish.
    if any(k in text for k in ["dry run", "dry-run", "analyze only", "plan only", "do not publish", "no publish"]):
        return False
    return any(k in text for k in ["create test execution", "create test executions", "publish", "push to xray", "run publish"]) or True


def parse_execution_request(prompt: str, copilot_cfg: dict[str, Any] | None = None) -> ParsedExecutionRequest:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    cfg = copilot_cfg or {}
    alias_cfg = cfg.get("brand_aliases", {})

    aliases: dict[str, tuple[str, ...]] = {}
    if isinstance(alias_cfg, dict) and alias_cfg:
        for brand, vals in alias_cfg.items():
            if isinstance(vals, (list, tuple)):
                aliases[str(brand)] = tuple(str(v).lower() for v in vals if str(v).strip())
    if not aliases:
        aliases = DEFAULT_BRAND_ALIASES

    release = _normalize_release(prompt)
    if not release:
        raise ValueError("Could not parse release from prompt. Example: 'Digital 26.12'.")

    brands = _extract_brands(prompt, aliases)
    if not brands:
        raise ValueError("Could not parse brands from prompt. Example: 'b1,b2,b3' or 'all brands'.")

    platforms = _extract_platforms(prompt)
    publish = _extract_publish_mode(prompt)

    return ParsedExecutionRequest(
        raw_prompt=prompt.strip(),
        release=release,
        brands=brands,
        platforms=platforms,
        publish=publish,
    )
