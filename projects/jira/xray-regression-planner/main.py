"""
main.py — CLI entry point for xray-regression-planner.

Usage:
  python main.py plan --release "Digital 26.8"
  python main.py plan --release "Digital 26.8" --publish
  python main.py plan --help
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import httpx
from rich.console import Console

from utils.logger import setup_logging
from utils.file_utils import load_yaml_config, resolve_output_dir
from client.auth import load_credentials
from client.jira_client import JiraClient
from client.xray_client import XrayClient
from ingestion.scope_fetcher import fetch_scope
from ingestion.bug_fetcher import fetch_all_bugs
from ingestion.testset_fetcher import fetch_test_cases, fetch_test_cases_from_filters, merge_test_inventories
from ingestion.execution_fetcher import fetch_execution_history, enrich_tests_with_history
from utils.copilot_request_parser import parse_execution_request
from engine.risk_scorer import build_component_metrics, score_all_components
from engine.platform_classifier import classify_platforms
from engine.test_selector import assign_tiers, apply_anti_bias_guard, build_platform_executions
from engine.coverage_analyzer import detect_coverage_gaps
from output.confidence_calculator import compute_confidence
from output.report_builder import build_html_report
from output.json_exporter import export_json
from output.csv_exporter import export_csv
from output.Planner_report_builder import write_Planner_markdown_report
from models.plan import RegressionPlan

console = Console()


@click.group()
def cli():
    """XRay Regression Planner — Risk-based test selection CLI."""
    pass


@cli.command()
@click.option("--release", required=True, help="Release version (e.g. 'Digital 26.8')")
@click.option("--config", default=None, help="Path to config.yaml")
@click.option("--env-file", default=None, help="Path to .env credentials file")
@click.option("--scope-filter", default=None, type=int, help="Jira filter ID for scope")
@click.option("--prod-bug-filter", default=None, type=int, help="Jira filter ID for prod bugs")
@click.option("--nonprod-bug-filter", default=None, type=int, help="Jira filter ID for non-prod bugs")
@click.option("--test-sets", default="", help="Comma-separated XRay test set keys")
@click.option("--test-filters", default="", help="Comma-separated Jira filter IDs that return Xray Test issues")
@click.option("--prev-executions", default="", help="Comma-separated previous execution keys")
@click.option("--publish", is_flag=True, default=False, help="Create XRay executions after planning")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging")
def plan(release, config, env_file, scope_filter, prod_bug_filter, nonprod_bug_filter,
         test_sets, test_filters, prev_executions, publish, verbose):
    """Run the risk-based regression planning pipeline."""
    setup_logging(verbose=verbose)
    asyncio.run(_run_pipeline(
        release=release,
        config_path=config,
        env_file=env_file,
        scope_filter_id=scope_filter,
        prod_bug_filter_id=prod_bug_filter,
        nonprod_bug_filter_id=nonprod_bug_filter,
        test_set_keys=[k.strip() for k in test_sets.split(",") if k.strip()],
        test_filter_ids=[int(k.strip()) for k in test_filters.split(",") if k.strip()],
        prev_execution_keys=[k.strip() for k in prev_executions.split(",") if k.strip()],
        do_publish=publish,
    ))


@cli.command(name="Planner-report")
@click.option("--release", required=True, help="Release version (e.g. 'Digital 26.12')")
@click.option("--config", default=None, help="Path to config.yaml")
@click.option("--env-file", default=None, help="Path to .env credentials file")
@click.option("--scope-filter", default=None, type=int, help="Jira filter ID for scope")
@click.option("--jql", default=None, help="Optional JQL override for scope fetch")
@click.option("--issue-types", default="Story", help="Comma-separated Jira issue types for default JQL")
@click.option("--out-dir", default=None, help="Output directory override")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging")
def Planner_report(release, config, env_file, scope_filter, jql, issue_types, out_dir, verbose):
    """Generate an Planner-style markdown analysis report from Jira scope."""
    setup_logging(verbose=verbose)
    asyncio.run(_run_Planner_report(
        release=release,
        config_path=config,
        env_file=env_file,
        scope_filter_id=scope_filter,
        jql=jql,
        issue_types=[t.strip() for t in issue_types.split(",") if t.strip()],
        out_dir_override=out_dir,
    ))


@cli.command(name="copilot-executions")
@click.option("--prompt", required=True, help="Natural-language Copilot request text")
@click.option("--config", default=None, help="Path to config.yaml")
@click.option("--env-file", default=None, help="Path to .env credentials file")
@click.option("--dry-run", is_flag=True, default=False, help="Only parse and preflight, do not publish")
@click.option("--verbose", is_flag=True, default=False, help="Enable debug logging")
def copilot_executions(prompt, config, env_file, dry_run, verbose):
    """Parse a Copilot chat request and execute regression planning/publish flow."""
    setup_logging(verbose=verbose)
    asyncio.run(_run_copilot_executions(
        prompt=prompt,
        config_path=config,
        env_file=env_file,
        dry_run=dry_run,
    ))


async def _run_pipeline(
    release: str,
    config_path: str | None,
    env_file: str | None,
    scope_filter_id: int | None,
    prod_bug_filter_id: int | None,
    nonprod_bug_filter_id: int | None,
    test_set_keys: list[str],
    test_filter_ids: list[int],
    prev_execution_keys: list[str],
    do_publish: bool,
) -> None:
    """Async pipeline execution."""
    config = load_yaml_config(config_path)
    risk_weights = config.get("risk_weights", {})
    tier_thresholds = config.get("tier_thresholds", {"tier1_min": 70, "tier2_min": 40})
    override_rules = config.get("override_rules", {})
    platform_labels = config.get("platform_labels", {})
    exec_config = config.get("execution", {})
    confidence_config = config.get("confidence", {})

    env_path = Path(env_file) if env_file else None
    jira_creds, xray_creds = load_credentials(env_path)

    async with httpx.AsyncClient(verify=False) as http_client:
        jira = JiraClient(jira_creds, http_client)
        xray = XrayClient(xray_creds, http_client)

        console.print("[bold blue]Step 1:[/bold blue] Fetching scope, bugs, tests…")
        scope_items = await fetch_scope(jira, filter_id=scope_filter_id)
        defects = await fetch_all_bugs(jira, prod_filter_id=prod_bug_filter_id,
                                        nonprod_filter_id=nonprod_bug_filter_id)
        tests_from_sets = await fetch_test_cases(xray, test_set_keys) if test_set_keys else []
        tests_from_filters = await fetch_test_cases_from_filters(xray, test_filter_ids) if test_filter_ids else []
        tests = merge_test_inventories(tests_from_sets, tests_from_filters)
        executions = await fetch_execution_history(xray, prev_execution_keys)
        enrich_tests_with_history(tests, executions)

        console.print("[bold blue]Step 2:[/bold blue] Scoring components…")
        components = build_component_metrics(scope_items, defects, tests, executions)
        score_all_components(components, defects, risk_weights, override_rules)

        console.print("[bold blue]Step 3:[/bold blue] Selecting tests…")
        classify_platforms(tests, platform_labels)
        assign_tiers(tests, components,
                     tier1_min=tier_thresholds.get("tier1_min", 70),
                     tier2_min=tier_thresholds.get("tier2_min", 40))
        anti_bias = apply_anti_bias_guard(tests,
                                          max_tier1_pct_per_component=exec_config.get("max_tier1_pct_per_component", 0.40))
        platform_executions, excluded = build_platform_executions(tests, release,
                                                                   avg_mins_per_test=exec_config.get("avg_mins_per_test", 3))
        coverage_gaps = detect_coverage_gaps(components, scope_items, defects, tests)

        console.print("[bold blue]Step 4:[/bold blue] Computing confidence…")
        confidence_level, confidence_details = compute_confidence(
            components, scope_items, defects, executions,
            high_threshold=confidence_config.get("high_threshold", 0.85),
            medium_threshold=confidence_config.get("medium_threshold", 0.60))

        warnings = [w for item in scope_items for w in item.warnings]
        total_selected = sum(len(e.tests) for e in platform_executions)

        plan = RegressionPlan(
            release_name=release, analyst="CLI User", tool_version="1.0.0",
            test_set_keys=test_set_keys + [f"FILTER:{fid}" for fid in test_filter_ids], prev_execution_keys=prev_execution_keys,
            total_scope_items=len(scope_items), total_bugs=len(defects),
            total_test_cases=len(tests), total_selected=total_selected,
            component_metrics=list(components.values()), executions=platform_executions,
            excluded_tests=excluded + anti_bias, coverage_gaps=coverage_gaps,
            confidence_level=confidence_level, confidence_details=confidence_details,
            warnings=warnings,
        )

        out_dir = resolve_output_dir(config.get("output", {}).get("dir"))
        console.print("[bold blue]Step 5:[/bold blue] Generating reports…")
        build_html_report(plan, out_dir)
        export_json(plan, out_dir)
        export_csv(plan, out_dir)

        console.print(f"\n[bold green]✅ Plan complete![/bold green] {total_selected} tests selected across {len(platform_executions)} platforms")
        console.print(f"   Confidence: {confidence_level.value}")
        console.print(f"   Reports saved to: {out_dir}\n")

        if do_publish:
            from publisher.confirmation_prompt import confirm_publish
            from publisher.xray_publisher import publish_plan

            if confirm_publish(plan):
                results = await publish_plan(plan, xray, jira, jira_creds.project_key)
                for r in results:
                    if "error" in r:
                        console.print(f"   ❌ {r['platform']}: {r['error']}", style="red")
                    else:
                        console.print(f"   ✅ {r['platform']}: {r['key']} ({r['tests']} tests)", style="green")


async def _run_Planner_report(
    release: str,
    config_path: str | None,
    env_file: str | None,
    scope_filter_id: int | None,
    jql: str | None,
    issue_types: list[str],
    out_dir_override: str | None,
) -> None:
    """Build Planner-style markdown report from Jira scope items."""
    config = load_yaml_config(config_path)
    env_path = Path(env_file) if env_file else None
    jira_creds, _xray_creds = load_credentials(env_path)

    effective_jql = jql
    if not effective_jql and not scope_filter_id:
        issue_type_clause = ", ".join([f'"{t}"' for t in issue_types])
        effective_jql = (
            f'fixVersion in ("{release}")\n'
            f'and issuetype IN ({issue_type_clause})\n'
            'and status NOT IN ("Rejected", "CANCELLED", "Ready for Prod", "Released")\n'
            'ORDER BY status ASC, created DESC'
        )

    async with httpx.AsyncClient(verify=False) as http_client:
        jira = JiraClient(jira_creds, http_client)
        console.print("[bold blue]Step 1:[/bold blue] Fetching scope for Planner-style report…")
        scope_items = await fetch_scope(jira, filter_id=scope_filter_id, jql=effective_jql)

    if not scope_items:
        console.print("[bold red]No scope items found.[/bold red] Check release/filter/JQL input.")
        return

    output_cfg = config.get("output", {}).get("dir")
    out_dir = Path(out_dir_override) if out_dir_override else resolve_output_dir(output_cfg)
    Planner_cfg = config.get("Planner_report", {})

    console.print("[bold blue]Step 2:[/bold blue] Rendering Planner-style markdown report…")
    report_path = write_Planner_markdown_report(
        release=release,
        scope_items=scope_items,
        out_dir=out_dir,
        issue_types=tuple(issue_types),
        taxonomy_overrides=Planner_cfg,
    )

    console.print(f"\n[bold green]✅ Report generated:[/bold green] {report_path}")
    console.print(f"   Tickets analyzed: {len(scope_items)}")


async def _run_copilot_executions(
    prompt: str,
    config_path: str | None,
    env_file: str | None,
    dry_run: bool,
) -> None:
    """Execute a Copilot-requested release TE flow with preflight checks."""
    config = load_yaml_config(config_path)
    copilot_cfg = config.get("copilot_chat", {})

    parsed = parse_execution_request(prompt, copilot_cfg)
    issue_types = copilot_cfg.get("default_issue_types", ["Story"])
    issue_type_clause = ", ".join([f'"{str(t).strip()}"' for t in issue_types if str(t).strip()])
    scope_jql = (
        f'fixVersion in ("{parsed.release}")\n'
        f'and issuetype IN ({issue_type_clause})\n'
        'and status NOT IN ("Rejected", "CANCELLED", "Ready for Prod", "Released")\n'
        'ORDER BY status ASC, created DESC'
    )

    brand_test_sets_cfg = copilot_cfg.get("brand_test_sets", {})
    brand_test_filters_cfg = copilot_cfg.get("brand_test_filters", {})
    brand_to_sets: dict[str, list[str]] = {}
    brand_to_filters: dict[str, list[int]] = {}
    missing_brands: list[str] = []
    all_test_sets: list[str] = []
    all_filter_ids: list[int] = []

    def _platform_keys(platforms: tuple[str, ...]) -> list[str]:
        keys: list[str] = []
        for p in platforms:
            up = p.upper()
            keys.append(up)
            if up == "IOS_APP":
                keys.append("IOS")
            if up == "AOS_APP":
                keys.append("ANDROID")
        return list(dict.fromkeys(keys))

    def _extract_filter_ids(values: list[object]) -> list[int]:
        ids: list[int] = []
        for value in values:
            raw = str(value).strip()
            if not raw:
                continue
            if raw.isdigit():
                ids.append(int(raw))
                continue
            if "filter=" in raw.lower():
                tail = raw.lower().split("filter=")[-1]
                digits = "".join(ch for ch in tail if ch.isdigit())
                if digits:
                    ids.append(int(digits))
        return ids

    def _resolve_sources(mapping: object, selected_platforms: tuple[str, ...]) -> tuple[list[str], list[int]]:
        if not mapping:
            return [], []
        selected_keys = set(_platform_keys(selected_platforms))
        if isinstance(mapping, dict):
            merged: list[object] = []
            for k, vals in mapping.items():
                if str(k).upper() in selected_keys and isinstance(vals, (list, tuple)):
                    merged.extend(list(vals))
            raw_strings = [str(v).strip() for v in merged if str(v).strip()]
        else:
            raw_strings = [str(v).strip() for v in (mapping or []) if str(v).strip()]

        sets = [v for v in raw_strings if v.upper().startswith("TE-")]
        filters = _extract_filter_ids(raw_strings)
        return sets, filters

    for brand in parsed.brands:
        sets, filter_ids = _resolve_sources(brand_test_sets_cfg.get(brand), parsed.platforms)
        _, extra_filter_ids = _resolve_sources(brand_test_filters_cfg.get(brand), parsed.platforms)
        filter_ids = list(dict.fromkeys(filter_ids + extra_filter_ids))

        if not sets and not filter_ids:
            missing_brands.append(brand)
            continue
        if sets:
            brand_to_sets[brand] = sets
        if filter_ids:
            brand_to_filters[brand] = filter_ids
        all_test_sets.extend(sets)
        all_filter_ids.extend(filter_ids)

    if missing_brands:
        console.print("[bold red]Missing brand test source mapping in config:[/bold red] " + ", ".join(missing_brands))
        console.print("Add mappings under [copilot_chat.brand_test_sets] and/or [copilot_chat.brand_test_filters] in config.yaml before publish.")
        return

    env_path = Path(env_file) if env_file else None
    jira_creds, xray_creds = load_credentials(env_path)

    console.print("[bold blue]Preflight:[/bold blue] validating Jira/Xray access and release scope…")
    async with httpx.AsyncClient(verify=False) as http_client:
        jira = JiraClient(jira_creds, http_client)
        xray = XrayClient(xray_creds, http_client)
        scope_items = await fetch_scope(jira, jql=scope_jql)
        tests_from_sets = await fetch_test_cases(xray, sorted(set(all_test_sets))) if all_test_sets else []
        tests_from_filters = await fetch_test_cases_from_filters(xray, sorted(set(all_filter_ids))) if all_filter_ids else []
        test_inventory = merge_test_inventories(tests_from_sets, tests_from_filters)

    if not scope_items:
        console.print("[bold red]Preflight failed:[/bold red] Release scope returned 0 items.")
        console.print("Check release version, issue type profile, or Jira visibility.")
        return

    if not test_inventory:
        console.print("[bold red]Preflight failed:[/bold red] Xray test inventory returned 0 tests.")
        console.print("Check test set keys, Xray permissions, or brand mappings.")
        return

    console.print("[bold green]Preflight passed.[/bold green]")
    console.print(f"  release={parsed.release}")
    console.print(f"  brands={', '.join(parsed.brands)}")
    console.print(f"  platforms={', '.join(parsed.platforms)}")
    console.print(f"  publish={parsed.publish and (not dry_run)}")
    console.print(f"  scope_items={len(scope_items)}")
    console.print(f"  test_inventory={len(test_inventory)}")

    if dry_run or not parsed.publish:
        console.print("[bold yellow]Dry-run complete.[/bold yellow] No TE creation executed.")
        return

    await _run_pipeline(
        release=parsed.release,
        config_path=config_path,
        env_file=env_file,
        scope_filter_id=None,
        prod_bug_filter_id=None,
        nonprod_bug_filter_id=None,
        test_set_keys=sorted(set(all_test_sets)),
        test_filter_ids=sorted(set(all_filter_ids)),
        prev_execution_keys=[],
        do_publish=True,
    )


if __name__ == "__main__":
    cli()
