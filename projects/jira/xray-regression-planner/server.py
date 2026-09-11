"""
server.py — FastAPI web server for xray-regression-planner.

Provides:
  - GET  /              → Single-page UI dashboard
  - POST /api/run       → Execute the full pipeline (returns JSON plan)
  - POST /api/publish   → Create XRay executions from a plan
  - POST /api/create-test → Create suggested test cases
  - GET  /api/health    → Health check
  - GET  /api/config    → Current config.yaml values
  - GET  /api/brands    → Available brand configurations

Usage:
  python server.py                   # http://localhost:8050
  python server.py --port 9000       # custom port
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime

import httpx
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from utils.logger import setup_logging
from utils.file_utils import load_yaml_config, resolve_output_dir
from client.auth import load_credentials
from client.jira_client import JiraClient
from client.xray_client import XrayClient
from ingestion.scope_fetcher import fetch_scope
from ingestion.bug_fetcher import fetch_all_bugs
from ingestion.testset_fetcher import fetch_test_cases
from ingestion.execution_fetcher import fetch_execution_history, enrich_tests_with_history
from engine.risk_scorer import build_component_metrics, score_all_components
from engine.platform_classifier import classify_platforms
from engine.test_selector import assign_tiers, apply_anti_bias_guard, build_platform_executions
from engine.coverage_analyzer import detect_coverage_gaps
from output.confidence_calculator import compute_confidence
from output.report_builder import build_html_report
from output.json_exporter import export_json
from output.csv_exporter import export_csv
from models.plan import RegressionPlan

setup_logging(verbose=True)
logger = structlog.get_logger(__name__)

app = FastAPI(title="XRay Regression Planner", version="1.0.0")


# ── Brand Configuration ─────────────────────────────────────────────

BRAND_CONFIG = {
    "brand3": {
        "label": "Brand Three",
        "test_set_keys": {
            "ios": "TE-10046",
            "android": "TE-10047",
            "web": "TE-10048",
            "mweb": "TE-10049",
            "thirdparty": "TE-10080",
        },
        "prod_bug_jql": "project = DOPS AND created >= -{days}d order by created DESC",
        "nonprod_bug_jql": "(project = DOVS OR PROJECT=E2E) AND created >= -{days}d order by created DESC",
    },
    "b2": {
        "label": "Brand Two",
        "test_set_keys": {},
        "prod_bug_jql": "project = DOPS AND component = B2 AND created >= -{days}d order by created DESC",
        "nonprod_bug_jql": "(project = DOVS OR PROJECT=E2E) AND component = B2 AND created >= -{days}d order by created DESC",
    },
    "brand1": {
        "label": "Brand One",
        "test_set_keys": {},
        "prod_bug_jql": "project = DOPS AND component = Brand One AND created >= -{days}d order by created DESC",
        "nonprod_bug_jql": "(project = DOVS OR PROJECT=E2E) AND component = Brand One AND created >= -{days}d order by created DESC",
    },
    "brand4": {
        "label": "Brand Four'",
        "test_set_keys": {},
        "prod_bug_jql": "project = DOPS AND component = Brand Four AND created >= -{days}d order by created DESC",
        "nonprod_bug_jql": "(project = DOVS OR PROJECT=E2E) AND component = Brand Four AND created >= -{days}d order by created DESC",
    },
}

BRAND_IDP_VALUES = {
    "brand3": "Brand Three",
    "b2": "Brand Two",
    "brand1": "Brand One",
    "brand4": "Brand Four'",
}

CORE_FUNCTIONAL_AREAS = [
    {"id": "signin_signup", "name": "Sign In / Sign Up", "keywords": ["sign in", "signin", "sign up", "signup", "login", "register", "registration", "authentication", "create account"]},
    {"id": "pickup_order", "name": "Pickup Order", "keywords": ["pickup", "pick up", "pick-up", "order ahead", "curbside", "drive-thru", "drive thru"]},
    {"id": "delivery_order", "name": "Delivery Order", "keywords": ["delivery", "deliver", "dispatch", "doordash", "uber eats"]},
    {"id": "credit_card", "name": "Credit Card Payment", "keywords": ["credit card", "creditcard", "cc payment", "visa", "mastercard", "card payment", "debit card"]},
    {"id": "gift_card", "name": "Gift Card", "keywords": ["gift card", "giftcard", "gift balance", "egift", "e-gift"]},
    {"id": "apple_google_pay", "name": "Apple Pay / Google Pay", "keywords": ["apple pay", "applepay", "google pay", "googlepay", "gpay", "digital wallet"]},
    {"id": "wallet_manage", "name": "Wallet Add/Remove Cards", "keywords": ["wallet", "add card", "remove card", "delete card", "saved card", "payment method", "manage card"]},
    {"id": "profile_modify", "name": "Profile Modifications", "keywords": ["profile", "edit profile", "update profile", "account settings", "personal info", "name change", "email change", "phone change"]},
    {"id": "password_reset", "name": "Change/Forgot Password", "keywords": ["password", "forgot password", "reset password", "change password", "password reset"]},
    {"id": "loyalty_rewards", "name": "Loyalty & Rewards", "keywords": ["loyalty", "rewards", "points", "earn", "redeem", "offers", "coupon"]},
    {"id": "menu_browse", "name": "Menu Browse & Customize", "keywords": ["menu", "browse", "customize", "modifier", "add to cart", "cart", "item detail"]},
    {"id": "location_search", "name": "Location Search & Selection", "keywords": ["location", "store", "restaurant", "find store", "near me", "search location", "set location"]},
]

DEFAULT_PLATFORM_WEIGHTS = {"ios": 30, "android": 10, "web": 35, "mweb": 15, "thirdparty": 10}
ALL_PLATFORMS = ["ios", "android", "web", "mweb", "thirdparty"]

SCOPE_JQL_TEMPLATE = (
    'project in ("IDP Blue Green and DR", "Digital Blueprint - Build Phase",'
    '"Customer Growth Value Stream", "example - IT CRM Email Campaigns",'
    '"Customer Data + Marketing Activation","Post Order Value Stream",'
    '"IDP Order Ahead Value Stream", "Loyalty Value Stream",'
    '"Digital Operations Support", "On-Prem Digital Sales Value Stream",'
    '"Digital Ordering Value Stream", E2E)'
    ' AND fixVersion in ("{release_version}")'
    ' AND issuetype NOT IN (Test, "Test Execution", "Testing Sub Task",'
    ' "Test Plan", Epic, "Sub Test Execution", Task)'
    ' AND status NOT IN (Rejected, CANCELLED)'
    ' ORDER BY created DESC'
)

# ── Guardrails ──────────────────────────────────────────────────────
MAX_BUG_LOOKBACK_DAYS = 365
MIN_BUG_LOOKBACK_DAYS = 7
MAX_TARGET_TEST_COUNT = 2000
MIN_TARGET_TEST_COUNT = 10
MAX_RELEASE_VERSION_LEN = 50


# ── Request / Response Models ───────────────────────────────────────

class PipelineRequest(BaseModel):
    brand: str = "brand3"
    release_version: str = "Digital 26.8"
    prod_bug_days: int = Field(default=60, ge=MIN_BUG_LOOKBACK_DAYS, le=MAX_BUG_LOOKBACK_DAYS)
    nonprod_bug_days: int = Field(default=60, ge=MIN_BUG_LOOKBACK_DAYS, le=MAX_BUG_LOOKBACK_DAYS)
    target_test_count: int = Field(default=0, ge=0, le=MAX_TARGET_TEST_COUNT)
    selected_platforms: list[str] = Field(default_factory=lambda: ALL_PLATFORMS.copy())
    platform_weights: dict[str, int] = Field(default_factory=lambda: DEFAULT_PLATFORM_WEIGHTS.copy())
    prev_execution_keys: str = ""
    release_name: str = ""
    analyst: str = "QA Team"
    env_file: str | None = None


class PublishRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ALL_PLATFORMS.copy())
    tier1_only: bool = False


class CreateTestRequest(BaseModel):
    summary: str
    platform: str
    area_id: str
    priority: str = "Medium"
    labels: list[str] = Field(default_factory=list)


# ── State ───────────────────────────────────────────────────────────
_last_plan: RegressionPlan | None = None


# ── API Routes ──────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "tool": "xray-regression-planner", "version": "1.0.0"}


@app.get("/api/config")
async def get_config():
    return load_yaml_config(None)


@app.get("/api/brands")
async def get_brands():
    brands = []
    for key, cfg in BRAND_CONFIG.items():
        brands.append({
            "id": key,
            "label": cfg["label"],
            "configured": bool(cfg["test_set_keys"]),
            "test_set_count": len(cfg["test_set_keys"]),
        })
    return {
        "brands": brands,
        "platforms": ALL_PLATFORMS,
        "default_weights": DEFAULT_PLATFORM_WEIGHTS,
        "core_areas": [{"id": a["id"], "name": a["name"]} for a in CORE_FUNCTIONAL_AREAS],
    }


@app.post("/api/run")
async def run_pipeline(req: PipelineRequest):
    """Run the full risk-analysis pipeline."""
    global _last_plan

    # ── Guardrails ──────────────────────────────────────────────────
    release_version = req.release_version.strip()
    if not release_version:
        raise HTTPException(422, "Release version is required")
    if len(release_version) > MAX_RELEASE_VERSION_LEN:
        raise HTTPException(422, f"Release version too long (max {MAX_RELEASE_VERSION_LEN})")
    if any(c in release_version for c in ['"', "'", ";", "--", "/*"]):
        raise HTTPException(422, "Release version contains invalid characters")
    if req.target_test_count != 0 and req.target_test_count < MIN_TARGET_TEST_COUNT:
        raise HTTPException(422, f"Target test count must be >= {MIN_TARGET_TEST_COUNT} (or 0)")

    # ── Brand ───────────────────────────────────────────────────────
    brand = req.brand.lower()
    if brand not in BRAND_CONFIG:
        raise HTTPException(422, f"Unknown brand: {brand}")
    brand_cfg = BRAND_CONFIG[brand]
    if not brand_cfg["test_set_keys"]:
        raise HTTPException(422, f"Brand '{brand_cfg['label']}' test sets not yet configured.")

    # ── Platforms ───────────────────────────────────────────────────
    selected_platforms = [p.lower() for p in req.selected_platforms]
    invalid_plats = [p for p in selected_platforms if p not in ALL_PLATFORMS]
    if invalid_plats:
        raise HTTPException(422, f"Invalid platforms: {invalid_plats}")
    if not selected_platforms:
        selected_platforms = ALL_PLATFORMS.copy()

    # ── Weights ─────────────────────────────────────────────────────
    weights = req.platform_weights
    active_weights = {p: weights.get(p, 0) for p in selected_platforms}
    weight_sum = sum(active_weights.values())
    if weight_sum > 0 and abs(weight_sum - 100) > 20:
        raise HTTPException(422, f"Platform weights must sum to ~100. Current: {weight_sum}")
    if weight_sum > 0 and abs(weight_sum - 100) > 1:
        factor = 100.0 / weight_sum
        active_weights = {p: round(v * factor) for p, v in active_weights.items()}

    # ── Build JQL ───────────────────────────────────────────────────
    scope_jql = SCOPE_JQL_TEMPLATE.format(release_version=release_version)
    prod_bug_jql = brand_cfg["prod_bug_jql"].format(days=req.prod_bug_days)
    nonprod_bug_jql = brand_cfg["nonprod_bug_jql"].format(days=req.nonprod_bug_days)

    ts_keys = [v for k, v in brand_cfg["test_set_keys"].items() if k in selected_platforms]
    exec_keys = [k.strip() for k in req.prev_execution_keys.split(",") if k.strip()]
    release_name = req.release_name.strip() or release_version
    analyst = req.analyst.strip() or "QA Team"

    config = load_yaml_config(None)
    risk_weights = config.get("risk_weights", {
        "defect_density": 0.35, "escaped_defect": 0.25,
        "churn_frequency": 0.20, "change_type": 0.10, "severity_weight": 0.10,
    })
    tier_thresholds = config.get("tier_thresholds", {"tier1_min": 70, "tier2_min": 40})
    override_rules = config.get("override_rules", {
        "escaped_p1p2_floor": 85, "new_component_floor": 75, "stable_component_cap": 30,
    })
    platform_labels = config.get("platform_labels", {
        "web": ["web", "webapp", "desktop"], "mweb": ["mweb", "mobile-web", "mobileweb"],
        "ios": ["ios", "iphone", "ipad", "apple"], "android": ["android", "gms"],
        "thirdparty": ["thirdparty", "third-party", "3p", "integration"],
    })
    exec_config = config.get("execution", {"avg_mins_per_test": 3, "max_tier1_pct_per_component": 0.40})
    confidence_config = config.get("confidence", {"high_threshold": 0.85, "medium_threshold": 0.60})

    try:
        env_path = Path(req.env_file) if req.env_file else None
        jira_creds, xray_creds = load_credentials(env_path)
    except Exception as e:
        raise HTTPException(500, f"Credential error: {e}")

    try:
        async with httpx.AsyncClient(verify=False) as http_client:
            jira = JiraClient(jira_creds, http_client)
            xray = XrayClient(xray_creds, http_client)

            # Step 1: Ingest
            scope_items = await fetch_scope(jira, jql=scope_jql)
            defects = await fetch_all_bugs(jira, prod_jql=prod_bug_jql, nonprod_jql=nonprod_bug_jql)
            tests = await fetch_test_cases(xray, ts_keys)
            executions = await fetch_execution_history(xray, exec_keys)
            enrich_tests_with_history(tests, executions)

            # Step 2: Score
            components = build_component_metrics(scope_items, defects, tests, executions)
            score_all_components(components, defects, risk_weights, override_rules)

            # Step 3: Select
            classify_platforms(tests, platform_labels)
            assign_tiers(tests, components,
                         tier1_min=tier_thresholds.get("tier1_min", 70),
                         tier2_min=tier_thresholds.get("tier2_min", 40))
            anti_bias = apply_anti_bias_guard(tests,
                                              max_tier1_pct_per_component=exec_config.get("max_tier1_pct_per_component", 0.40))
            platform_executions, excluded = build_platform_executions(tests, release_name,
                                                                      avg_mins_per_test=exec_config.get("avg_mins_per_test", 3))

            # Filter to selected platforms
            from models.test_case import Platform as PlatformEnum
            plat_name_to_enum = {p.value.lower(): p for p in PlatformEnum}
            selected_enums = {plat_name_to_enum[sp] for sp in selected_platforms if sp in plat_name_to_enum}
            platform_executions = [e for e in platform_executions if e.platform in selected_enums]

            coverage_gaps = detect_coverage_gaps(components, scope_items, defects, tests)

            # Step 4: Confidence
            confidence_level, confidence_details = compute_confidence(
                components, scope_items, defects, executions,
                high_threshold=confidence_config.get("high_threshold", 0.85),
                medium_threshold=confidence_config.get("medium_threshold", 0.60))

            all_warnings = [w for item in scope_items for w in item.warnings]
            total_selected = sum(len(e.tests) for e in platform_executions)

            # Step 5: Budget analysis
            from models.plan import BudgetAnalysis
            budget = None
            if req.target_test_count > 0:
                target = req.target_test_count
                delta = total_selected - target
                utilization = (total_selected / target * 100) if target else 0.0
                tier1_total = sum(e.tier1_count for e in platform_executions)
                tier2_total = sum(e.tier2_count for e in platform_executions)
                tier3_total = sum(e.tier3_count for e in platform_executions)

                plat_breakdown = []
                for e in platform_executions:
                    plat_key = e.platform.value.lower()
                    allocated = round(target * active_weights.get(plat_key, 0) / 100)
                    plat_breakdown.append({
                        "platform": e.platform.value, "count": len(e.tests),
                        "allocated": allocated, "weight_pct": active_weights.get(plat_key, 0),
                        "tier1": e.tier1_count, "tier2": e.tier2_count, "tier3": e.tier3_count,
                        "delta": len(e.tests) - allocated,
                    })

                if delta > 0:
                    over_pct = delta / target * 100
                    rec = (f"⚠️ OVER BUDGET by {delta} tests ({over_pct:.0f}%). "
                           f"Tier 3 has {tier3_total} tests that could be deferred.") if over_pct <= 30 else (
                        f"⚠️ OVER BUDGET by {delta} ({over_pct:.0f}%). Drop Tier 3 ({tier3_total}) → {total_selected - tier3_total}.")
                elif delta < 0:
                    under_pct = abs(delta) / target * 100
                    rec = (f"✅ Under budget by {abs(delta)} ({under_pct:.0f}%). "
                           f"Consider adding Tier 2/3 tests.") if under_pct > 20 else (
                        f"✅ Within budget — {abs(delta)} under ({under_pct:.0f}% room).")
                else:
                    rec = "✅ Exactly on target."

                if tier1_total > target * 0.8:
                    all_warnings.append(f"🛡️ GUARDRAIL: Tier 1 ({tier1_total}) > 80% of target ({target}).")
                if total_selected > target * 2:
                    all_warnings.append(f"🛡️ GUARDRAIL: Selected ({total_selected}) > 2x target ({target}).")

                budget = BudgetAnalysis(
                    target_count=target, actual_count=total_selected, delta=delta,
                    utilization_pct=utilization, tier1_count=tier1_total,
                    tier2_count=tier2_total, tier3_count=tier3_total,
                    recommendation=rec, platform_breakdown=plat_breakdown,
                )

            # Step 6: Core coverage
            core_coverage = _analyze_core_coverage(tests, platform_executions, selected_platforms)
            suggestions = _generate_test_suggestions(core_coverage, brand, selected_platforms)

            # Guardrails
            if not scope_items:
                all_warnings.append(f'🛡️ Zero scope items for fixVersion "{release_version}".')
            if not defects:
                all_warnings.append("🛡️ Zero bugs found — risk scoring degraded.")
            if not tests:
                all_warnings.append("🛡️ Zero test cases — check XRay connectivity.")

            uncovered = sum(1 for a in core_coverage if not all(a["platforms"].get(p, False) for p in selected_platforms))
            if uncovered:
                all_warnings.append(f"🛡️ CORE COVERAGE: {uncovered}/{len(core_coverage)} areas have gaps.")

            plan = RegressionPlan(
                release_name=release_name, analyst=analyst, tool_version="1.0.0", brand=brand,
                scope_jql=scope_jql, prod_bug_jql=prod_bug_jql, nonprod_bug_jql=nonprod_bug_jql,
                test_set_keys=ts_keys, prev_execution_keys=exec_keys,
                selected_platforms=selected_platforms, platform_weights=active_weights,
                total_scope_items=len(scope_items), total_bugs=len(defects),
                total_test_cases=len(tests), total_selected=total_selected,
                component_metrics=list(components.values()), executions=platform_executions,
                excluded_tests=excluded + anti_bias, coverage_gaps=coverage_gaps,
                confidence_level=confidence_level, confidence_details=confidence_details,
                warnings=all_warnings, target_test_count=req.target_test_count,
                budget_analysis=budget, core_coverage=core_coverage, suggested_tests=suggestions,
            )

            out_dir = resolve_output_dir(None)
            build_html_report(plan, out_dir)
            export_json(plan, out_dir)
            _last_plan = plan
            return plan.model_dump(mode="json")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("pipeline.failed", error=str(e))
        raise HTTPException(500, str(e))


# ── Core Coverage Helpers ───────────────────────────────────────────

def _analyze_core_coverage(tests, platform_executions, selected_platforms):
    exec_test_keys = {}
    for e in platform_executions:
        exec_test_keys[e.platform.value.lower()] = {t.key for t in e.tests}

    results = []
    for area in CORE_FUNCTIONAL_AREAS:
        area_result = {"id": area["id"], "name": area["name"], "platforms": {}, "matching_tests": {}, "total_matches": 0}
        for plat in selected_platforms:
            plat_tests = exec_test_keys.get(plat, set())
            matches = []
            for t in tests:
                if t.key not in plat_tests:
                    continue
                combined = f"{(t.summary or '').lower()} {' '.join(l.lower() for l in (t.labels or []))}"
                if any(kw in combined for kw in area["keywords"]):
                    matches.append({"key": t.key, "summary": t.summary, "tier": t.tier})
            area_result["platforms"][plat] = len(matches) > 0
            area_result["matching_tests"][plat] = matches
            area_result["total_matches"] += len(matches)
        results.append(area_result)
    return results


def _generate_test_suggestions(core_coverage, brand, selected_platforms):
    suggestions = []
    brand_label = BRAND_CONFIG.get(brand, {}).get("label", brand.title())
    plat_labels = {"ios": "iOS", "android": "Android", "web": "Web", "mweb": "Mobile Web", "thirdparty": "Third Party"}
    critical_areas = {"signin_signup", "pickup_order", "delivery_order", "credit_card"}

    for area in core_coverage:
        for plat in selected_platforms:
            if not area["platforms"].get(plat, False):
                pl = plat_labels.get(plat, plat.upper())
                suggestions.append({
                    "area_id": area["id"], "area_name": area["name"],
                    "platform": plat, "platform_label": pl, "brand": brand,
                    "suggested_summary": f"[{brand_label}][{pl}] Verify {area['name']} functionality",
                    "priority": "High" if area["id"] in critical_areas else "Medium",
                    "reason": f"No test covers '{area['name']}' on {pl}.",
                })
    return suggestions


# ── Create Test ─────────────────────────────────────────────────────

@app.post("/api/create-test")
async def create_test_case(req: CreateTestRequest):
    try:
        jira_creds, xray_creds = load_credentials(None)
    except Exception as e:
        raise HTTPException(500, f"Credential error: {e}")

    plat_map = {"ios": "iOS", "android": "Android", "web": "Web", "mweb": "mWeb", "thirdparty": "3P"}
    labels = list(set(req.labels + [req.platform, plat_map.get(req.platform, req.platform),
                                     "auto-suggested", "core-coverage", req.area_id]))
    try:
        async with httpx.AsyncClient(verify=False) as http_client:
            jira = JiraClient(jira_creds, http_client)
            result = await jira.create_issue(
                project_key="IQE", issue_type="Test",
                summary=req.summary, labels=labels, priority=req.priority,
            )
            return {"success": True, "key": result.get("key", ""),
                    "url": f"{jira_creds.base_url}/browse/{result.get('key', '')}", "summary": req.summary}
    except Exception as e:
        logger.error("create_test.failed", error=str(e))
        raise HTTPException(500, str(e))


# ── Publish ─────────────────────────────────────────────────────────

@app.post("/api/publish")
async def publish_executions_api(req: PublishRequest):
    global _last_plan
    if not _last_plan:
        raise HTTPException(400, "No plan available. Run the pipeline first.")

    from models.test_case import Platform
    from models.plan import Tier

    try:
        jira_creds, xray_creds = load_credentials(None)
    except Exception as e:
        raise HTTPException(500, f"Credential error: {e}")

    platform_map = {p.value: p for p in Platform}
    selected = [platform_map[p] for p in req.platforms if p in platform_map]
    release_label = _last_plan.release_name.replace("Digital ", "").strip()
    brand_key = _last_plan.brand or "brand3"
    brand_idp = BRAND_IDP_VALUES.get(brand_key, "Brand Three")

    created = []
    async with httpx.AsyncClient(verify=False) as http_client:
        jira = JiraClient(jira_creds, http_client)
        xray = XrayClient(xray_creds, http_client)

        for execution in _last_plan.executions:
            if execution.platform not in selected:
                continue
            tests_to_add = execution.tests
            if req.tier1_only:
                tests_to_add = [t for t in execution.tests if t.tier == Tier.TIER1.value]
            if not tests_to_add:
                continue

            test_keys = [t.key for t in tests_to_add]
            try:
                result = await xray.create_execution(
                    test_issue_ids=test_keys, summary=execution.summary,
                    project_key=jira_creds.project_key,
                    labels=[release_label, "Regression", execution.platform.value],
                )
                exec_key = result.get("key", "UNKNOWN")
                exec_url = f"{jira_creds.base_url}/browse/{exec_key}"

                # Set IDP Brands custom field
                try:
                    await jira.update_issue(exec_key, {"customfield_10844": [{"value": brand_idp}]})
                except Exception as brand_err:
                    logger.warning("publish.brand_field_failed", key=exec_key, error=str(brand_err))

                execution.created_key = exec_key
                execution.jira_url = exec_url
                created.append({"platform": execution.platform.value, "key": exec_key, "url": exec_url, "tests": len(test_keys)})
            except Exception as e:
                created.append({"platform": execution.platform.value, "error": str(e)[:200]})

    _last_plan.created_execution_keys = created
    return {"created": created}


# ── Serve UI ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    ui_path = Path(__file__).parent / "ui" / "index.html"
    if not ui_path.exists():
        return HTMLResponse("<h1>UI not found</h1>", status_code=404)
    return HTMLResponse(ui_path.read_text(encoding="utf-8"))


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 8050
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])
    print(f"\n  🎯 XRay Regression Planner UI → http://localhost:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
