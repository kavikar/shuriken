# XRay Regression Planner

**Risk-based test selection engine** for XRay Cloud regression cycles. Analyzes Jira scope, bug history, and test execution data to produce an optimized regression plan with tiered test assignments.

## Features

- **JQL-driven scope ingestion** — Pulls stories/bugs from release fixVersion
- **Multi-source bug analysis** — DOPS (prod) + DOVS/E2E (non-prod) with configurable lookback
- **Risk scoring engine** — Component-level risk heatmap based on scope churn, bugs, fail rates, escaped defects
- **Tier assignment** — TIER 1 (Critical) / TIER 2 (Important) / TIER 3 (Best Effort)
- **Platform-aware selection** — iOS, Android, Web, mWeb, 3P with weight-based allocation
- **Budget analysis** — Target test count with platform-level utilization tracking
- **Core coverage analysis** — Ensures 12 critical functional areas covered per platform
- **Test suggestions** — AI-generated suggestions for missing core coverage gaps
- **Publish to XRay** — Create test executions with IDP Brands field + release labels
- **Web UI** — Beautiful dark-theme dashboard with 8 result tabs

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your Jira + XRay credentials

# 3. Run Web UI
python server.py
# Open http://localhost:8050

# 4. Or run CLI
python -m xray_regression_planner --release-version "Digital 26.8" --prod-bug-days 60 --nonprod-bug-days 60

# 5. Copilot-chat style release execution request
python main.py copilot-executions --prompt "create test executions for release 26.12 for all brands b1,b2,b3" --config config.yaml --env-file ../.env
# Add --dry-run to validate preflight without publishing
```

## Architecture

```
xray_regression_planner/
├── models/          # Pydantic data models
├── client/          # Jira + XRay API clients
├── ingestion/       # Data fetching & normalization
├── engine/          # Risk scoring, platform classifier, test selector
├── output/          # Reports, JSON/CSV export, confidence
├── publisher/       # XRay execution creator
├── utils/           # Logger, pagination, file utils
server.py            # FastAPI web server
main.py              # CLI entry point
ui/index.html        # Web dashboard
```

## Brand Support

| Brand | Status | Test Sets |
|-------|--------|-----------|
| Brand Three | ✅ Active | TE-10046 (iOS), TE-10047 (AOS), TE-10048 (Web), TE-10049 (mWeb), TE-10080 (3P) |
| B2 | 🔜 Coming | — |
| Brand One | 🔜 Coming | — |
| Brand Four' | 🔜 Coming | — |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/run` | Run full analysis pipeline |
| POST | `/api/publish` | Create XRay executions |
| POST | `/api/create-test` | Create individual test issue |
| GET | `/api/brands` | Get brand metadata |
| GET | `/api/health` | Health check |

## Tests

```bash
pytest tests/ -v
```

## License

Internal — Example Corp QA Engineering
