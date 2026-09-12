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

SCOPE_JQL_TEMPLATE = (
    'project in ("Platform Infra and DR", "Digital Foundation Build",'
    '"Customer Growth Stream", "example - CRM Email Campaigns",'
    '"Customer Data and Marketing","Post-Order Stream",'
    '"Order Ahead Stream", "Loyalty Stream",'
    '"Digital Ops Support", "In-Store Digital Sales Stream",'
    '"Digital Ordering Stream", E2E)'
    ' AND fixVersion in ("{release_version}")'
    ' AND issuetype NOT IN (Test, "Test Execution", "Testing Sub Task",'
    ' "Test Plan", Epic, "Sub Test Execution", Task)'
    ' AND status NOT IN (Rejected, CANCELLED)'
    ' ORDER BY created DESC'
)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _chunk(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _default_reports_dir() -> Path:
    reports = Path(__file__).parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports


async def _fetch_test_details(jira, test_keys: list[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for batch in _chunk(sorted(set(test_keys)), 50):
        quoted = ", ".join(f'"{key}"' for key in batch)
        issues = await jira.search_issues(
            f"key in ({quoted})",
            fields=["summary", "components", "labels"],
            max_results_per_page=100,
        )
        for issue in issues:
            fields = issue.get("fields", {})
            components = [component.get("name", "") for component in (fields.get("components") or [])]
            results[issue.get("key", "")] = {
                "summary": fields.get("summary", ""),
                "components": components or ["Uncategorized"],
                "labels": fields.get("labels") or [],
            }
    return results


async def _run(release: str, executions: list[str], env_file: str | None, json_out: str | None, csv_out: str | None) -> None:
    import httpx

    from client.auth import load_credentials
    from client.jira_client import JiraClient
    from client.xray_client import XrayClient
    from ingestion.execution_fetcher import fetch_execution_history
    from ingestion.scope_fetcher import fetch_scope

    env_path = Path(env_file) if env_file else None
    jira_creds, xray_creds = load_credentials(env_path)
    if not jira_creds.email or not jira_creds.api_token:
        raise RuntimeError("Missing Jira credentials. Populate .env or pass --env-file.")
    if not xray_creds.client_id or not xray_creds.client_secret:
        raise RuntimeError("Missing Xray credentials. Populate .env or pass --env-file.")

    jql = SCOPE_JQL_TEMPLATE.format(release_version=release)

    async with httpx.AsyncClient(verify=not _INSECURE_TLS) as client:
        jira = JiraClient(jira_creds, client)
        xray = XrayClient(xray_creds, client)

        scope_items = await fetch_scope(jira, jql=jql)
        execution_runs = await fetch_execution_history(xray, executions)
        test_details = await _fetch_test_details(jira, [run.test_key for run in execution_runs])

    scope_components: dict[str, dict] = {}
    for item in scope_items:
        for component in (item.components or ["Uncategorized"]):
            row = scope_components.setdefault(component, {"scope_items": 0, "scope_keys": []})
            row["scope_items"] += 1
            row["scope_keys"].append(item.key)

    execution_component_stats: dict[str, dict[str, dict[str, int | list[str]]]] = {}
    for execution in executions:
        execution_component_stats[execution] = {}

    for run in execution_runs:
        details = test_details.get(run.test_key, {"components": ["Uncategorized"], "summary": ""})
        for component in details.get("components") or ["Uncategorized"]:
            row = execution_component_stats[run.execution_key].setdefault(component, {
                "tests": 0,
                "passed": 0,
                "failed": 0,
                "blocked": 0,
                "todo": 0,
                "test_keys": [],
            })
            row["tests"] += 1
            row["test_keys"].append(run.test_key)
            status = (run.status or "TODO").upper()
            if status == "PASSED":
                row["passed"] += 1
            elif status == "FAILED":
                row["failed"] += 1
            elif status == "BLOCKED":
                row["blocked"] += 1
            else:
                row["todo"] += 1

    all_components = sorted(
        set(scope_components.keys()) | {component for stats in execution_component_stats.values() for component in stats.keys()},
        key=lambda component: (-scope_components.get(component, {}).get("scope_items", 0), component),
    )

    rows: list[dict] = []
    for component in all_components:
        row = {
            "component": component,
            "scope_items": scope_components.get(component, {}).get("scope_items", 0),
            "scope_keys": sorted(set(scope_components.get(component, {}).get("scope_keys", []))),
        }
        for execution in executions:
            stats = execution_component_stats[execution].get(component, {
                "tests": 0,
                "passed": 0,
                "failed": 0,
                "blocked": 0,
                "todo": 0,
                "test_keys": [],
            })
            row[execution] = {
                "tests": stats["tests"],
                "passed": stats["passed"],
                "failed": stats["failed"],
                "blocked": stats["blocked"],
                "todo": stats["todo"],
                "test_keys": sorted(set(stats["test_keys"])),
            }
        rows.append(row)

    print(f"\nScope Coverage Matrix for {release}\n")
    print(f"Scope items: {len(scope_items)}")
    print(f"Executions:  {', '.join(executions)}\n")

    for row in rows:
        summary = [f"scope={row['scope_items']}"]
        for execution in executions:
            stats = row[execution]
            summary.append(
                f"{execution}: tests={stats['tests']} pass={stats['passed']} fail={stats['failed']} blocked={stats['blocked']} todo={stats['todo']}"
            )
        print(f"{row['component']}: {' | '.join(summary)}")

    safe_release = _slugify(release)
    safe_execs = "-vs-".join(_slugify(key) for key in executions)
    reports_dir = _default_reports_dir()
    json_path = Path(json_out) if json_out else reports_dir / f"{safe_release}-{safe_execs}-scope-matrix.json"
    csv_path = Path(csv_out) if csv_out else reports_dir / f"{safe_release}-{safe_execs}-scope-matrix.csv"

    json_path.write_text(json.dumps({
        "release": release,
        "executions": executions,
        "rows": rows,
    }, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["component", "scope_items", "scope_keys"]
        for execution in executions:
            header.extend([
                f"{execution}_tests",
                f"{execution}_passed",
                f"{execution}_failed",
                f"{execution}_blocked",
                f"{execution}_todo",
                f"{execution}_test_keys",
            ])
        writer.writerow(header)
        for row in rows:
            csv_row = [row["component"], row["scope_items"], "|".join(row["scope_keys"])]
            for execution in executions:
                stats = row[execution]
                csv_row.extend([
                    stats["tests"],
                    stats["passed"],
                    stats["failed"],
                    stats["blocked"],
                    stats["todo"],
                    "|".join(stats["test_keys"]),
                ])
            writer.writerow(csv_row)

    print(f"\nSaved JSON: {json_path}")
    print(f"Saved CSV:  {csv_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a component-level scope coverage matrix versus Test Executions")
    parser.add_argument("--release", required=True, help='Release version, for example "Digital 26.8"')
    parser.add_argument("--executions", required=True, help='Comma-separated TE keys, for example "TE-10081,TE-10082"')
    parser.add_argument("--env-file", default=None, help="Optional path to .env credentials file")
    parser.add_argument("--json-out", default=None, help="Optional JSON output path")
    parser.add_argument("--csv-out", default=None, help="Optional CSV output path")
    args = parser.parse_args()

    execution_keys = [key.strip() for key in args.executions.split(',') if key.strip()]
    if len(execution_keys) < 2:
        raise SystemExit("Pass at least two execution keys via --executions")

    asyncio.run(_run(args.release, execution_keys, args.env_file, args.json_out, args.csv_out))


if __name__ == "__main__":
    main()