# servicesHealthCheck

Confluence-first reusable service health engine used by Shuriken Quick Bites.

## What it does

- Discovers environment/service endpoints from Confluence child pages.
- Builds a dynamic catalog (`envKey -> endpoint list`).
- Runs concurrent readiness checks.
- Returns stable CSV output (`Service,Status,HTTP Status,URL`).
- Supports TTL cache and optional force refresh.

## Environment variables

- `CONFLUENCE_BASE_URL` (default: `https://your-tenant.atlassian.net/wiki`)
- `CONFLUENCE_EMAIL`
- `CONFLUENCE_API_TOKEN`
- `HEALTH_CONFLUENCE_PARENT_PAGE_ID` (fallback: `CONFLUENCE_PARENT_PAGE_ID`, then `000000000000`)
- `HEALTH_CHECK_CACHE_TTL_SEC` (default: `300`)
- `HEALTH_CHECK_STATIC_FALLBACK` (default: `1`)

If process env variables are not set, the module also reads values from `projects/jira/.env`.

## Public API

- `get_health_catalog(force_refresh: bool = False) -> dict`
- `run_health_check(brand: str, env: str, timeout_sec: float = 6.0, max_workers: int = 16, force_refresh: bool = False) -> dict`
