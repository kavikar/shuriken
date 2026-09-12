from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
from pathlib import Path

# Corporate-proxy escape hatch: TLS verification is on by default and only
# disabled when explicitly opted into, rather than always skipped.
_INSECURE_TLS = os.environ.get("ALLOW_INSECURE_TLS") == "1"

PROJECT_SCOPE_CLAUSE = (
    'project in ("IDP Blue Green and DR", "Digital Blueprint - Build Phase",'
    '"Customer Growth Value Stream", "example - IT CRM Email Campaigns",'
    '"Customer Data + Marketing Activation", "Post Order Value Stream",'
    '"IDP Order Ahead Value Stream", "Loyalty Value Stream",'
    '"Digital Operations Support", "On-Prem Digital Sales Value Stream",'
    '"Digital Ordering Value Stream", E2E, "Payment Solutions Value Stream",'
    ' "Non-Trad Value Stream")'
)

SCOPE_JQL_TEMPLATE = (
    PROJECT_SCOPE_CLAUSE +
    ' AND fixVersion in ("{release_version}")'
    ' AND issuetype NOT IN (Test, "Test Execution", "Testing Sub Task",'
    ' "Test Plan", Epic, "Sub Test Execution", Task)'
    ' AND status NOT IN (Rejected, CANCELLED)'
    ' ORDER BY created DESC'
)

EPIC_JQL_TEMPLATE = (
    PROJECT_SCOPE_CLAUSE +
    ' AND fixVersion in ("{release_version}")'
    ' AND issuetype IN (Epic)'
    ' AND status NOT IN (Rejected, CANCELLED)'
    ' ORDER BY created DESC'
)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _default_reports_dir() -> Path:
    reports = Path(__file__).parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports


async def _run(release: str, env_file: str | None, json_out: str | None, csv_out: str | None) -> None:
    import httpx

    from client.auth import load_credentials
    from client.jira_client import JiraClient
    from ingestion.scope_fetcher import fetch_scope

    env_path = Path(env_file) if env_file else None
    jira_creds, _ = load_credentials(env_path)
    if not jira_creds.email or not jira_creds.api_token:
      raise RuntimeError("Missing Jira credentials. Populate .env or pass --env-file.")

    jql = SCOPE_JQL_TEMPLATE.format(release_version=release)
    epic_jql = EPIC_JQL_TEMPLATE.format(release_version=release)

    async with httpx.AsyncClient(verify=not _INSECURE_TLS) as client:
        jira = JiraClient(jira_creds, client)
        scope_items = await fetch_scope(jira, jql=jql)
        release_epics = await fetch_scope(jira, jql=epic_jql)

    print(f"\nRelease scope for {release}")
    print(f"JQL: {jql}\n")
    print(f"Total scope items: {len(scope_items)}\n")
    print(f"Release EPIC filter JQL: {epic_jql}\n")
    print(f"Total release EPICs: {len(release_epics)}\n")

    component_counts: dict[str, int] = {}
    for item in scope_items:
        components = item.components or ["Uncategorized"]
        for component in components:
            component_counts[component] = component_counts.get(component, 0) + 1

    for item in scope_items:
        components = ", ".join(item.components or ["Uncategorized"])
        print(f"{item.key:<12} {item.status:<14} {item.issue_type:<16} {components:<28} {item.summary}")

    print("\nComponent counts:")
    for component, count in sorted(component_counts.items(), key=lambda pair: (-pair[1], pair[0])):
        print(f"  {component}: {count}")

    if release_epics:
        print("\nRelease EPICs:")
        for epic in release_epics:
            print(f"{epic.key:<12} {epic.status:<14} {epic.summary}")

    safe_release = _slugify(release)
    reports_dir = _default_reports_dir()
    json_path = Path(json_out) if json_out else reports_dir / f"{safe_release}-scope.json"
    csv_path = Path(csv_out) if csv_out else reports_dir / f"{safe_release}-scope.csv"
    epic_csv_path = reports_dir / f"{safe_release}-epics.csv"

    json_path.write_text(json.dumps({
        "release": release,
        "jql": jql,
        "epic_jql": epic_jql,
        "total": len(scope_items),
        "items": [item.model_dump() for item in scope_items],
        "epic_total": len(release_epics),
        "epics": [item.model_dump() for item in release_epics],
    }, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "summary", "status", "issue_type", "priority", "components", "fix_versions"])
        for item in scope_items:
            writer.writerow([
                item.key,
                item.summary,
                item.status,
                item.issue_type,
                item.priority,
                "|".join(item.components),
                "|".join(item.fix_versions),
            ])

    with epic_csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key", "summary", "status", "issue_type", "priority", "components", "fix_versions"])
        for item in release_epics:
            writer.writerow([
                item.key,
                item.summary,
                item.status,
                item.issue_type,
                item.priority,
                "|".join(item.components),
                "|".join(item.fix_versions),
            ])

    print(f"\nSaved JSON: {json_path}")
    print(f"Saved CSV:  {csv_path}\n")
    print(f"Saved EPIC CSV: {epic_csv_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Jira release scope by fixVersion")
    parser.add_argument("--release", required=True, help='Release version, for example "Digital 26.8"')
    parser.add_argument("--env-file", default=None, help="Optional path to .env credentials file")
    parser.add_argument("--json-out", default=None, help="Optional JSON output path")
    parser.add_argument("--csv-out", default=None, help="Optional CSV output path")
    args = parser.parse_args()
    asyncio.run(_run(args.release, args.env_file, args.json_out, args.csv_out))


if __name__ == "__main__":
    main()