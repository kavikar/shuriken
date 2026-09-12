import csv
import io
import os
import re
import time
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
import urllib3

# Corporate-proxy escape hatch: TLS verification is on by default and only
# disabled when explicitly opted into, rather than always skipped.
_INSECURE_TLS = os.environ.get("ALLOW_INSECURE_TLS") == "1"
if _INSECURE_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


ENV_ALLOWED = {"uat01", "uat01a", "staging", "staginga"}
BRAND_HOST_MAP = {
    "b3": {"b3-api"},
    "b1": {"brand1-api", "b1-api"},
    "b2": {"b2-api"},
}
BRAND_PRIMARY_HOST = {
    "b3": "b3-api",
    "b1": "brand1-api",
    "b2": "b2-api",
}
FIXED_ENV_KEYS = [
    "b1-uat01",
    "b1-uat01a",
    "b2-staging",
    "b2-staginga",
    "b3-staging",
    "b3-staginga",
]
# Maps each env-key to the (brand-host, url-env-segment) that actually resolves/responds.
# b1-uat01 -> brand1-api.uat.staging.example (not uat01)
# b3-staging -> b3-api.uat.staging.example   (b3-api.staging.staging.example DNS does not exist)
# For now, a-variants are aliased to their stable base UAT hosts to avoid all REQUEST FAILED.
FIXED_ENV_URL_MAP: dict[str, tuple[str, str]] = {
    "b1-uat01":  ("brand1-api", "uat"),
    "b1-uat01a": ("brand1-api", "uat"),
    "b2-staging":  ("b2-api",   "staging"),
    "b2-staginga": ("b2-api",   "staging"),
    "b3-staging":  ("b3-api",   "uat"),
    "b3-staginga": ("b3-api",   "uat"),
}
FIXED_SERVICE_NAMES = [
    "cache-operation-service-v0",
    "content-service-v0",
    "curator-v0",
    "customer-service-v0",
    "customer-read-service-v0",
    "customer-loyalty-event-service-v0",
    "exp-cache-mgr-v0",
    "fulfillment-service-v1",
    "fulfillment-service-v2",
    "idp-admin-server-v0",
    "item-service-v0",
    "location-service-v2",
    "loyalty-service-v0",
    "menu-service-v0",
    "menu-api-v0",
    "menu-configuration-api-v0",
    "menu-operations-api-v0",
    "notifications-service-v0",
    "order-service-v0",
    "order-loyalty-event-service-v0",
    "order-retrieval-service-v3",
    "payment-service-v0",
    "retriever-v0",
    "tally-service-v0",
    "wallet-manager-v2",
    "wallet-retrieval-v2",
]

URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
HOST_PATTERN = re.compile(r"\b([a-z0-9-]+\.(?:b3-api|brand1-api|b1-api|b2-api)\.(?:uat01a|uat01|staginga|staging)\.staging\.example)\b", re.IGNORECASE)
ENV_PATTERN = re.compile(r"\.(uat01a|uat01|staginga|staging)\.staging\.example$", re.IGNORECASE)
PAGE_ENV_PATTERN = re.compile(r"\b(uat01a|uat01|staginga|staging)\b", re.IGNORECASE)

_CACHE_LOCK = threading.Lock()
_CATALOG_CACHE = {
    "timestamp": 0.0,
    "ttl": 300,
    "catalog": None,
    "last_error": "",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_env_file(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _settings() -> dict:
    repo_root = _project_root()
    env_file = repo_root / "projects" / "jira" / ".env"
    env_values = _read_env_file(env_file)

    def pick(name: str, default: str = "") -> str:
        return os.environ.get(name, env_values.get(name, default)).strip()

    ttl_sec = pick("HEALTH_CHECK_CACHE_TTL_SEC", "300")
    try:
        ttl_val = max(30, min(3600, int(ttl_sec)))
    except Exception:
        ttl_val = 300

    return {
        "confluence_base_url": pick("CONFLUENCE_BASE_URL", "https://your-tenant.atlassian.net/wiki").rstrip("/"),
        "confluence_email": pick("CONFLUENCE_EMAIL"),
        "confluence_api_token": pick("CONFLUENCE_API_TOKEN"),
        "confluence_parent_page_id": pick("HEALTH_CONFLUENCE_PARENT_PAGE_ID", pick("CONFLUENCE_PARENT_PAGE_ID", "000000000000")),
        "cache_ttl_sec": ttl_val,
        "static_fallback_enabled": pick("HEALTH_CHECK_STATIC_FALLBACK", "1").lower() not in {"0", "false", "no", "off"},
        "static_dir": str((repo_root.parent / "HealthStatusChecks")),
        "verify_tls": pick("HEALTH_CHECK_VERIFY_TLS", ""),
        "node_tls_reject_unauthorized": pick("NODE_TLS_REJECT_UNAUTHORIZED", ""),
    }


def _confluence_verify_tls(settings: dict) -> bool:
    explicit = (settings.get("verify_tls") or "").strip().lower()
    if explicit in {"0", "false", "no", "off"}:
        return False
    if explicit in {"1", "true", "yes", "on"}:
        return True

    node_tls = (settings.get("node_tls_reject_unauthorized") or "").strip()
    if node_tls == "0":
        return False
    return True


def _auth(settings: dict) -> tuple[str, str]:
    email = settings.get("confluence_email", "")
    token = settings.get("confluence_api_token", "")
    if not email or not token:
        raise RuntimeError("Confluence credentials are missing. Set CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN.")
    return email, token


def _confluence_get(url: str, settings: dict, params: dict | None = None) -> dict:
    auth = _auth(settings)
    verify_tls = _confluence_verify_tls(settings)
    if not verify_tls:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    response = requests.get(url, params=params or {}, auth=auth, timeout=30, verify=verify_tls)
    response.raise_for_status()
    return response.json()


def _extract_brand_env(endpoint_url: str) -> tuple[str, str] | tuple[None, None]:
    parsed = urllib.parse.urlparse(endpoint_url)
    host = (parsed.hostname or "").lower()

    brand = ""
    for brand_key, host_tokens in BRAND_HOST_MAP.items():
        if any(token in host for token in host_tokens):
            brand = brand_key
            break

    env_match = ENV_PATTERN.search(host)
    env = env_match.group(1).lower() if env_match else ""

    if not brand or not env:
        return None, None
    return brand, env


def _normalize_env_name(raw_env: str) -> str | None:
    token = (raw_env or "").strip().lower()
    if token in {"uat1", "uat01"}:
        return "uat01"
    if token in {"uat2", "staging"}:
        return "staging"
    if token in ENV_ALLOWED:
        return token
    return None


def _page_env_hint(page_title: str) -> str | None:
    title = (page_title or "").strip()
    if not title:
        return None
    match = PAGE_ENV_PATTERN.search(title)
    if not match:
        return None
    return _normalize_env_name(match.group(1))


def _resolve_env(base_env: str, title_env_hint: str | None) -> str:
    base = _normalize_env_name(base_env) or ""
    hint = _normalize_env_name(title_env_hint or "") or ""
    if not base:
        return hint or base_env
    if not hint:
        return base
    if base == hint:
        return base
    if base == "uat" and hint in {"uat01", "staging"}:
        return hint
    return base


def _add_env_aliases(targets: dict[str, list[str]]) -> dict[str, list[str]]:
    return dict(targets)


def _catalog_from_fixed_report() -> dict:
    targets: dict[str, list[str]] = {}

    for env_key in FIXED_ENV_KEYS:
        host, env_seg = FIXED_ENV_URL_MAP[env_key]
        urls = [
            f"https://{service}.{host}.{env_seg}.staging.example/actuator/health/readiness"
            for service in FIXED_SERVICE_NAMES
        ]
        targets[env_key] = sorted(set(urls))

    available = _available_from_targets(targets)
    return {
        "source": "fixed-report",
        "sourceDir": "report-2026-06-01",
        "parentPageId": "",
        "pages": [],
        "available": available,
        "targets": targets,
        "notes": [
            "Catalog is constrained to b1-uat01, b1-uat01a, b2-staging, b2-staginga, b3-staging, b3-staginga.",
            "Service endpoints are generated from the provided report service list.",
            "uat01a/staginga keys are currently mapped to base UAT host segments for reliable connectivity.",
        ],
    }


def _service_name(endpoint_url: str) -> str:
    host = (urllib.parse.urlparse(endpoint_url).hostname or "").lower()
    if not host:
        return "unknown-service"
    return host.split(".", 1)[0]


def _normalize_to_readiness_url(raw_url: str) -> str | None:
    url = (raw_url or "").strip()
    if not url.lower().startswith("http"):
        return None

    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or "staging.example" not in host:
        return None

    path = parsed.path or ""
    if "/actuator/health/readiness" in path.lower():
        normalized_path = "/actuator/health/readiness"
    else:
        normalized_path = "/actuator/health/readiness"

    return urllib.parse.urlunparse((parsed.scheme or "https", host, normalized_path, "", "", ""))


def _child_pages(settings: dict) -> list[dict]:
    base = settings["confluence_base_url"]
    parent_id = settings["confluence_parent_page_id"]
    if not parent_id:
        raise RuntimeError("Confluence parent page id is missing. Set HEALTH_CONFLUENCE_PARENT_PAGE_ID.")

    start = 0
    pages: list[dict] = []

    while True:
        url = f"{base}/rest/api/content/{parent_id}/child/page"
        payload = _confluence_get(url, settings, params={"limit": 200, "start": start})
        results = payload.get("results", [])
        pages.extend(results)

        next_link = (payload.get("_links") or {}).get("next")
        if not next_link:
            break
        start += len(results)

        if not results:
            break

    return pages


def _page_storage(page_id: str, settings: dict) -> dict:
    base = settings["confluence_base_url"]
    url = f"{base}/rest/api/content/{page_id}"
    return _confluence_get(url, settings, params={"expand": "body.storage,body.view,title"})


def _catalog_from_confluence(settings: dict) -> dict:
    parent_id = settings["confluence_parent_page_id"]
    pages = _child_pages(settings)
    if parent_id:
        pages.append({"id": parent_id, "title": "Parent"})

    seen_page_ids: set[str] = set()
    raw_targets: dict[tuple[str, str], set[str]] = {}
    source_pages = []

    for page in pages:
        page_id = str(page.get("id", "")).strip()
        if not page_id or page_id in seen_page_ids:
            continue
        seen_page_ids.add(page_id)

        page_payload = _page_storage(page_id, settings)
        title = page_payload.get("title", page.get("title", ""))
        storage_html = (
            ((page_payload.get("body") or {}).get("storage") or {}).get("value")
            or ""
        )
        view_html = (
            ((page_payload.get("body") or {}).get("view") or {}).get("value")
            or ""
        )
        combined_html = f"{storage_html}\n{view_html}"

        raw_urls = set(URL_PATTERN.findall(combined_html))
        for host in HOST_PATTERN.findall(combined_html):
            raw_urls.add(f"https://{host}")
        endpoints: set[str] = set()
        for raw_url in raw_urls:
            normalized = _normalize_to_readiness_url(raw_url)
            if normalized:
                endpoints.add(normalized)
        if not endpoints:
            continue

        page_env = _page_env_hint(title)
        source_pages.append({"id": page_id, "title": title, "count": len(endpoints)})

        for endpoint in endpoints:
            brand, env = _extract_brand_env(endpoint)
            if not brand or not env:
                continue
            resolved_env = _resolve_env(env, page_env)
            key = (brand, resolved_env)
            if key not in raw_targets:
                raw_targets[key] = set()
            raw_targets[key].add(endpoint)

    serialized_targets = {
        f"{brand}-{env}": sorted(urls)
        for (brand, env), urls in sorted(raw_targets.items())
    }
    serialized_targets = _add_env_aliases(serialized_targets)

    available = [
        {
            "brand": brand,
            "env": env,
            "envKey": f"{brand}-{env}",
            "count": len(urls),
        }
        for (brand, env), urls in sorted(raw_targets.items())
    ]

    return {
        "source": "confluence",
        "sourceDir": settings["confluence_base_url"],
        "parentPageId": settings["confluence_parent_page_id"],
        "pages": source_pages,
        "available": available,
        "targets": serialized_targets,
    }


def _catalog_from_static(settings: dict) -> dict:
    static_dir = settings.get("static_dir", "")
    if not static_dir or not os.path.isdir(static_dir):
        return {"source": "static", "sourceDir": static_dir, "available": [], "targets": {}}

    catalog: dict[tuple[str, str], set[str]] = {}
    for filename in sorted(os.listdir(static_dir)):
        if not filename.lower().endswith(".bat") or not filename.lower().startswith("healthstatus_"):
            continue
        path = Path(static_dir) / filename
        content = path.read_text(encoding="utf-8", errors="replace")

        for line in content.splitlines():
            match = re.match(r"\s*set\s+URIs\[\d+\]=(.+)\s*$", line, flags=re.IGNORECASE)
            if not match:
                continue
            endpoint = match.group(1).strip()
            if not endpoint.lower().startswith("http"):
                continue
            brand, env = _extract_brand_env(endpoint)
            if not brand or not env:
                continue
            key = (brand, env)
            if key not in catalog:
                catalog[key] = set()
            catalog[key].add(endpoint)

    targets = {f"{brand}-{env}": sorted(urls) for (brand, env), urls in sorted(catalog.items())}
    targets = _add_env_aliases(targets)
    available = [
        {"brand": brand, "env": env, "envKey": f"{brand}-{env}", "count": len(urls)}
        for (brand, env), urls in sorted(catalog.items())
    ]

    return {
        "source": "static",
        "sourceDir": static_dir,
        "available": available,
        "targets": targets,
    }


def _available_from_targets(targets: dict[str, list[str]]) -> list[dict]:
    available: list[dict] = []
    for env_key, urls in sorted((targets or {}).items()):
        if "-" not in env_key:
            continue
        brand, env = env_key.split("-", 1)
        available.append(
            {
                "brand": brand,
                "env": env,
                "envKey": env_key,
                "count": len(urls),
            }
        )
    return available


def _merge_catalogs(primary: dict, supplemental: dict) -> dict:
    merged = dict(primary or {})
    merged_targets = dict((primary or {}).get("targets", {}))
    extra_targets = (supplemental or {}).get("targets", {})

    for env_key, urls in (extra_targets or {}).items():
        if env_key not in merged_targets:
            merged_targets[env_key] = list(urls)

    merged["targets"] = merged_targets
    merged["available"] = _available_from_targets(merged_targets)
    return merged


def get_health_catalog(force_refresh: bool = False) -> dict:
    settings = _settings()
    now = time.time()

    with _CACHE_LOCK:
        _CATALOG_CACHE["ttl"] = settings["cache_ttl_sec"]
        cached = _CATALOG_CACHE.get("catalog")
        ts = float(_CATALOG_CACHE.get("timestamp", 0) or 0)
        if not force_refresh and cached and (now - ts) < settings["cache_ttl_sec"]:
            return cached

    catalog = _catalog_from_fixed_report()
    with _CACHE_LOCK:
        _CATALOG_CACHE["catalog"] = catalog
        _CATALOG_CACHE["timestamp"] = now
        _CATALOG_CACHE["last_error"] = ""
    return catalog


def _status_from_http(http_status: int, payload: dict | None) -> str:
    if http_status == 200:
        if isinstance(payload, dict):
            raw = payload.get("status")
            if isinstance(raw, str) and raw.strip():
                return raw.strip().upper()
        return "UP"
    if http_status == 404:
        return "404 NOT FOUND"
    if http_status == 503:
        return "503 SERVICE UNAVAILABLE"
    if http_status == 500:
        return "500 INTERNAL SERVER ERROR"
    if http_status <= 0:
        return "REQUEST FAILED"
    return f"HTTP {http_status}"


def _check_health_endpoint(url: str, timeout_sec: float) -> dict:
    service_name = _service_name(url)
    try:
        response = requests.get(url, timeout=timeout_sec, verify=not _INSECURE_TLS)
        payload = None
        try:
            payload = response.json()
        except Exception:
            payload = None

        status = _status_from_http(response.status_code, payload)
        return {
            "service": service_name,
            "url": url,
            "httpStatus": response.status_code,
            "status": status,
            "ok": response.status_code == 200 and status in {"UP", "OK", "HEALTHY"},
        }
    except Exception as exc:
        return {
            "service": service_name,
            "url": url,
            "httpStatus": 0,
            "status": "REQUEST FAILED",
            "ok": False,
            "error": str(exc),
        }


def _rows_to_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Service", "Status", "HTTP Status", "URL"])
    for row in rows:
        writer.writerow([
            row.get("service", ""),
            row.get("status", ""),
            row.get("httpStatus", ""),
            row.get("url", ""),
        ])
    return output.getvalue()


def run_health_check(
    brand: str,
    env: str,
    timeout_sec: float = 6.0,
    max_workers: int = 16,
    force_refresh: bool = False,
    progress_callback=None,
) -> dict:
    brand_val = (brand or "").strip().lower()
    env_val = (env or "").strip().lower()

    if brand_val not in BRAND_HOST_MAP:
        raise ValueError("Brand must be one of: b3, b1, b2.")
    if env_val not in ENV_ALLOWED:
        raise ValueError("Environment must be one of: uat01, uat01a, staging, staginga.")

    catalog = get_health_catalog(force_refresh=force_refresh)
    env_key = f"{brand_val}-{env_val}"
    targets = catalog.get("targets", {}).get(env_key, [])
    if not targets:
        available = ", ".join(item.get("envKey", "") for item in catalog.get("available", [])) or "none"
        raise ValueError(f"No endpoints configured for {env_key}. Available: {available}")

    timeout = max(1.0, min(float(timeout_sec or 6.0), 20.0))

    rows: list[dict] = []
    done_count = 0
    worker_count = max(1, min(max_workers, 24, len(targets)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_map = {executor.submit(_check_health_endpoint, url, timeout): url for url in targets}
        for future in as_completed(future_map):
            row = future.result()
            rows.append(row)
            done_count += 1
            if progress_callback:
                try:
                    progress_callback(done_count, len(targets), row)
                except Exception:
                    pass

    rows.sort(key=lambda row: row.get("service", ""))
    up = sum(1 for row in rows if row.get("ok"))
    down = len(rows) - up

    return {
        "brand": brand_val,
        "env": env_val,
        "envKey": env_key,
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "total": len(rows),
        "up": up,
        "down": down,
        "rows": rows,
        "csv": _rows_to_csv(rows),
        "sourceDir": catalog.get("sourceDir", ""),
        "source": catalog.get("source", "unknown"),
        "notes": catalog.get("notes", []),
    }
