# XRay Regression Planner — Full Project Context
> Last updated: April 16, 2026 | Author: Test | Chat: Copilot Session

---

## 1. What This Tool Is

A **risk-based regression test planner** that:
- Reads release scope from Jira Cloud (live JQL)
- Reads defect history from prod + non-prod bug filters (adjustable timeline)
- Reads existing test cases from XRay Cloud Test Sets (GraphQL)
- Reads previous test execution results from XRay
- Computes a **weighted risk score** per component (0–100)
- Selects tests into **Tier 1 / Tier 2 / Tier 3** buckets
- Generates **5 platform-specific Test Executions** (iOS, Android, Web, mWeb, 3P)
- Provides **HTML dashboard UI** at `http://localhost:8050`
- Supports **budget targeting** (e.g., "I want 200 tests total")
- Shows **core functional coverage matrix** per platform
- **Suggests missing test cases** and can auto-create them in Jira

---

## 2. Project Location

```
shuriken/projects/jira/xray-regression-planner/
```

Part of the **shuriken** monorepo: `gitlab.com:your-org/quality-engineering/automation/shuriken.git`
Branch: `test-branch`

---

## 3. Architecture

```
/xray-regression-planner
  main.py                     # Click CLI entrypoint
  server.py                   # FastAPI web UI backend (port 8050)
  config.yaml                 # Tunable risk weights, thresholds, platform labels
  .env                        # Credentials (gitignored)
  .env.example                # Template
  requirements.txt            # httpx, pydantic, structlog, fastapi, click, etc.

  /client
    auth.py                   # .env loading, XRay OAuth2 token fetch + auto-refresh
    jira_client.py            # Jira Cloud REST wrapper (search, create, update)
    xray_client.py            # XRay Cloud REST + GraphQL wrapper

  /ingestion
    scope_fetcher.py          # Fetch release scope via JQL (paginated)
    bug_fetcher.py            # Fetch prod + nonprod bugs via JQL (adjustable days)
    testset_fetcher.py        # Fetch tests from XRay Test Sets (GraphQL, paginated)
    execution_fetcher.py      # Fetch previous execution results
    normalizer.py             # Severity normalization, component inheritance

  /models
    scope.py                  # ScopeItem, ComponentMetrics (Pydantic v2)
    defect.py                 # Defect model
    test_case.py              # TestCase, Platform enum
    execution.py              # ExecutionResult
    plan.py                   # RegressionPlan, BudgetAnalysis, CoreCoverageArea,
                              #   SuggestedTest, Tier enum

  /engine
    risk_scorer.py            # Weighted risk scoring (pure functions)
    test_selector.py          # Tier assignment, dedup, anti-bias guard
    coverage_analyzer.py      # Gap detection (components with bugs but no tests)
    platform_classifier.py    # Label/component → platform mapping

  /output
    report_builder.py         # Self-contained HTML report generation
    json_exporter.py          # JSON export
    csv_exporter.py           # CSV export (TestRail/Zephyr format)
    confidence_calculator.py  # HIGH/MEDIUM/LOW confidence scoring

  /publisher
    xray_publisher.py         # Create XRay Test Executions via REST import
    confirmation_prompt.py    # Interactive CLI confirmation flow

  /utils
    logger.py                 # structlog setup
    file_utils.py             # Safe pathlib file handling
    paginator.py              # Jira API pagination helper

  /ui
    index.html                # Single-page dark-themed dashboard (zero deps)

  /tests
    test_risk_scorer.py       # 20 tests
    test_platform_classifier.py # 12 tests
    test_normalizer.py        # 12 tests
    test_coverage_analyzer.py # 10 tests
    fixtures/sample_data.py   # Realistic test data
```

---

## 4. How to Run

### Web UI (primary)
```bash
cd shuriken/projects/jira/xray-regression-planner
pip install -r requirements.txt
python server.py              # → http://localhost:8050
```

### CLI
```bash
python main.py \
  --scope-filter-id 42000 \
  --prod-bug-filter-id 42001 \
  --nonprod-bug-filter-id 42002 \
  --test-set-keys TE-10046,TE-10047,TE-10048,TE-10049,TE-10080 \
  --release-name "Digital 26.8" \
  --analyst "Test" \
  --dry-run
```

### Tests
```bash
cd shuriken/projects/jira/xray-regression-planner
python -m pytest tests/ -v    # 54 tests, all passing
```

---

## 5. Credentials (.env)

```env
JIRA_BASE_URL=https://your-tenant.atlassian.net
JIRA_EMAIL=<your-email>
JIRA_API_TOKEN=<your-jira-api-token>
XRAY_CLIENT_ID=<your-xray-client-id>
XRAY_CLIENT_SECRET=<your-xray-client-secret>
JIRA_PROJECT_KEY=IQE
```

**Never committed.** `.gitignore` excludes `.env`. Only `.env.example` is in repo.

---

## 6. Brand Configuration (in server.py)

### Brand Three (fully configured)
| Platform | Test Set Key | Pool Size |
|----------|-------------|-----------|
| iOS      | TE-10046  | 106       |
| Android  | TE-10047  | 92        |
| Web      | TE-10048  | 144       |
| mWeb     | TE-10049  | 34        |
| 3P       | TE-10080  | 16        |

### B2, Brand One, Brand Four' — Stub configs exist, no test set keys yet

### JQL Templates
- **Scope**: `project in ("IDP Blue Green and DR", "Digital Blueprint - Build Phase", ...) AND fixVersion in ("{release_version}") AND issuetype NOT IN (Test, "Test Execution", ...) AND status NOT IN (Rejected, CANCELLED)`
- **Prod bugs**: `project = DOPS AND created >= -{days}d`
- **Non-prod bugs**: `(project = DOVS OR PROJECT=E2E) AND created >= -{days}d`

---

## 7. Risk Scoring Engine

### Weights (configurable in config.yaml)
| Signal | Weight | Description |
|--------|--------|-------------|
| defect_density | 35% | Bugs per scope item in component |
| escaped_defect | 25% | Prod bugs / total bugs |
| churn_frequency | 20% | How often component appeared in past executions |
| change_type | 10% | New > Modified > Config change |
| severity_weight | 10% | P1×4 + P2×3 + P3×2 + P4×1 normalized |

### Override Rules
| Rule | Action |
|------|--------|
| Escaped P1/P2 in last 2 cycles | Floor score = 85 |
| First-time component | Floor score = 75 |
| Pass rate ≥ 95%, zero prod bugs | Cap score at 30 |
| Never executed before | Promote to Tier 2 minimum |
| Failed in most recent execution | Promote to Tier 1 |

### Tier Thresholds
- **Tier 1 (MUST RUN)**: risk_score ≥ 70
- **Tier 2 (SHOULD RUN)**: risk_score 40–69
- **Tier 3 (NICE TO HAVE)**: risk_score < 40

### Anti-bias Guard
Max 40% of Tier 1 from single component (unless risk_score ≥ 90)

---

## 8. Core Functional Areas (coverage matrix)

These 12 areas must have at least 1 test per platform:
1. Sign In / Sign Up
2. Pickup Order
3. Delivery Order
4. Credit Card Payment
5. Gift Card Payment
6. Apple Pay / Google Pay
7. Wallet - Add/Remove Cards
8. Profile Modifications
9. Change/Forgot Password
10. Menu Browsing & PDP
11. Bag & Checkout
12. Order History & Reorder

---

## 9. UI Features

### Form Inputs
- **Brand tabs**: Brand Three (active), B2/Brand One/Brand Four' (coming soon)
- **Release Version**: e.g. "Digital 26.8" → auto-builds JQL
- **Platform chips**: Toggle iOS/Android/Web/mWeb/3P on/off
- **Bug lookback days**: Adjustable 7–365 (default 60)
- **Target test count**: Budget cap with per-platform allocation
- **Platform weight allocation**:
  - Visual progress bars per platform
  - Editable weight % AND test count (bidirectional sync)
  - Smart Balance: prioritizes iOS & Web, caps at pool limits
  - Even Split: equal distribution
  - Live pool warnings when est. tests > available
  - Auto-rebalance when changing any count or weight

### Result Tabs
1. **Risk Heatmap** — sortable component risk table
2. **Execution Plans** — per-platform test listings with tier badges
3. **Budget Analysis** — target vs actual, per-platform breakdown with shortfall warnings
4. **Core Coverage** — functional area × platform matrix (✓/✗)
5. **Suggestions** — missing test cases with "Create Test" button
6. **Excluded Tests** — with reason codes
7. **Coverage Gaps** — components with bugs but no tests
8. **Audit Trail** — full provenance (JQL, weights, config, timestamp)

### Publish Section
- Checkbox per platform
- "Tier 1 Only" filter option
- Creates XRay Test Executions with:
  - Label = release number (e.g. "26.8")
  - IDP Brands custom field = brand name
  - Naming: `{release} — Regression — {Platform} — {date}`

---

## 10. Jira Custom Field IDs (Brand Three)

| Field | Value ID |
|-------|----------|
| OS - iOS | 11713 |
| OS - Android | 11712 |
| OS - Web | 19947 |
| Channel - App | 11976 |
| Channel - Web | 11977 |
| Brand - Brand Three | 11975 |
| Test Execution issue type | 10317 |

---

## 11. Known Issues & Technical Debt

### P0 — Must Fix
1. **`_last_plan` global state** — race condition if multiple users hit `/api/run` concurrently. Fix: use UUID-keyed dictionary or return plan in publish payload.
2. **`verify=False`** on all httpx calls — disables SSL verification. Should be configurable via `.env`.

### P1 — Should Fix
3. **Budget `available` vs `pool_sizes` mismatch** — server budget uses `len(e.tests)` but UI uses `pool_sizes` from config. Can disagree.
4. **Weight rounding error** — `round()` on normalized weights can sum to 99 or 101. Use remainder-distribution algorithm.

### P2 — Nice to Fix
5. **No API caching** — every Run fetches fresh from Jira/XRay (15-30s). Cache by release version.
6. **Relative normalization** — risk scores shift between runs as dataset changes. Consider absolute thresholds.
7. **Keyword-only platform classification** — misses tests with XRay custom field-based platform tagging.

### P3 — Future
8. **Core coverage keyword matching is brittle** — "SSO authentication" won't match "sign in" keywords.
9. **Scope JQL hardcoded project names** — if Jira projects rename, silently returns 0 scope items.
10. **No MCP integration** — could use example MCP for better context (mentioned in spec, not implemented).

---

## 12. Shuriken Site Integration

The Regression Planner is listed on the Shuriken portal:
- **Main page**: `shuriken/site/index.html` → Jira section card (4th tool)
- **Detail page**: `shuriken/site/jira/index.html` → full description with workflow diagram, 6 features, command table

### Shuriken Site Flaws (from review)
- All CSS inline (~150 lines) — should extract to `styles.css`
- No shared layout/template — each sub-page duplicates nav/footer/styles
- Hardcoded tool counts in category badges — manual sync needed when adding tools
- No 404 fallback page
- Asset paths are relative — can break under subdirectory deployment

---

## 13. Git History

| Commit | Message |
|--------|---------|
| `88cc28e` | feat(regression-planner): pool warnings |
| `77247c7` | feat(regression-planner): editable test counts |
| `72bcfd5` | feat(regression-planner): auto-rebalance weights when editing test counts |

Branch: `test-branch` on `gitlab.com:your-org/quality-engineering/automation/shuriken.git`

---

## 14. Future Enhancements (from original spec)

- [ ] MCP integration for better context awareness
- [ ] ML-based scoring model (swap via `ScoringModel` Protocol)
- [ ] Slack/Teams notifications on execution creation (`NotificationHook` Protocol)
- [ ] CSV import mode for offline/dev usage (`JiraConnector` Protocol)
- [ ] Multi-brand support (B2, Brand One, Brand Four' configs)
- [ ] Historical trend tracking across releases
- [ ] API result caching with TTL
- [ ] Absolute risk thresholds instead of relative normalization

---

## 15. Build Sequence (for new chat sessions)

If you need to modify or extend this tool in a new Copilot session, provide this file as context and say:

> "Read CONTEXT.md in `shuriken/projects/jira/xray-regression-planner/`. I want to [describe change]."

### Key files to reference for common tasks:
- **Add a new brand**: Edit `BRAND_CONFIG` in `server.py` + add brand tab in `ui/index.html`
- **Change risk weights**: Edit `config.yaml`
- **Add core functional area**: Edit `CORE_FUNCTIONAL_AREAS` in `server.py`
- **Add platform**: Edit `Platform` enum in `models/test_case.py`, `BRAND_CONFIG`, and UI chips
- **Fix scoring logic**: Edit `engine/risk_scorer.py` (pure functions, unit-testable)
- **Change JQL**: Edit `SCOPE_JQL_TEMPLATE` or `BRAND_CONFIG` JQL templates in `server.py`

---

*Generated from Copilot session — April 16, 2026*
