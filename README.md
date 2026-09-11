# shuriken

[![CI](https://github.com/kavikar/shuriken/actions/workflows/ci.yml/badge.svg)](https://github.com/kavikar/shuriken/actions/workflows/ci.yml)

**A unified QA platform for a four-brand e-commerce estate** — mobile and API automation, test-management automation, menu-data validation, and the CI/CD orchestration that ties them together.

> Generic by construction. Four fictional brands ("Brand One".."Brand Four"), placeholder hosts, no real credentials, store data, or issue keys anywhere in the repository.

---

## What this is

Four consumer brands, each with its own mobile app and web storefront, sharing most of a commerce backend. QA for that estate was a collection of disconnected efforts: mobile flows in one place, API collections in another, test cases maintained by hand in Jira, menu-data problems found in production.

This is the platform built to connect them. The interesting part is not any single tool — it is that they share one configuration model, one test-management client, and one pipeline.

```
      config/  ──────────────────────────────┐
   brands · environments · projects          │  one registry, every consumer
                                             │
   ┌────────────┬────────────┬───────────────┴──┬──────────────┐
   ▼            ▼            ▼                  ▼              ▼
 Maestro     Appium       API/Newman      Jira + Xray       Menu tools
 (mobile)  (agentic)      (contract)      automation        (data quality)
   │            │            │                  │              │
   └────────────┴────────────┴──────────────────┘              │
                        │                                      │
                        ▼                                      ▼
              CI/CD orchestration                      Browser-based
       build → devices → report → notify                  portal
```

## Design decisions worth a look

| Decision | Rationale |
|---|---|
| One shared Jira/Xray client, not one per tool | Three tools each growing their own auth and token-refresh logic is three places for a 401 to hide |
| Everything writable has a `--dry-run` | The tools mutate a live test-management system. A preview that shows exactly what would change is the difference between a usable tool and a scary one |
| Central config loader for every CI script | Store IDs, bundle IDs and device pools drift the moment two scripts each keep their own copy |
| Missing store / OTP failure / infra failure → **blocked**, not failed | A pass/fail number that quietly folds in environment problems stops being worth reading |
| Archive, never delete, in report folders | Execution evidence is the one artifact you cannot regenerate after the fact |
| Test-case generation produces *prompts and Gherkin*, not brittle recorded scripts | Recorded scripts break on the next redesign; a well-specified intent survives it |
| A CI job greps for real brands, hosts and issue keys | This repository is generic by construction. Enforcing that in CI beats depending on anyone remembering — it caught two leaks the day it was added |

## Repository map

| Path | What's in it |
|---|---|
| `config/` | Brand, environment, project and test-data registries — the source of truth every tool reads |
| `projects/automation/maestro/` | Mobile E2E flows, YAML, organized per brand with shared sub-flows |
| `projects/automation/super-appium/` | Agentic Appium suite — natural-language prompts driving device automation |
| `projects/automation/playwright-web/` | Pointer to [`play-left`](https://github.com/kavikar/play-left), where web E2E lives |
| `projects/api-automation/` | OpenAPI/Swagger → request scripts → Newman runs with HTML reporting |
| `projects/jira/shared/` | The single Jira REST + Xray GraphQL client |
| `projects/jira/testCaseFullMeal/` | Epic → test cases → Gherkin / browser prompts → Xray |
| `projects/jira/testExecutioner/` | CSV/JSON/Markdown results → Xray test-run statuses |
| `projects/jira/xray-regression-planner/` | Risk-based regression scope selection, with unit tests |
| `projects/menu/` | Menu delta analyzer, mapping validator, unmapped-product checker |
| `projects/quickBites/` | Service health checks, OTP retrieval |
| `scripts/ci/` | Build → device cloud → wiki report → notification pipeline helpers |
| `scripts/regression/` | Historical leakage analysis, tier pools, zero-leak gating |
| `site/` | Static portal and browser-based tools |
| `desktop/`, `tools/otp-app/` | Paused desktop apps, superseded by the `serve.py` API |

## Companion repository

Web end-to-end automation is **not** in this repo — it is [**play-left**](https://github.com/kavikar/play-left), a standalone multi-brand Playwright framework. A thin Playwright project used to live here and overlapped it almost entirely; keeping two frameworks for one job is how selectors drift and coverage claims stop meaning anything. See `projects/automation/playwright-web/README.md` for the interface between the two.

---

## End-to-End Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Shuriken — CI/CD Pipeline                            │
│                                                                              │
│  ① BUILD PUBLISHED    ② SMOKE TESTS         ③ CONFLUENCE       ④ NOTIFY     │
│  ─────────────────    ────────────          ────────────       ────────      │
│                                                                              │
│  Developer merges     Bitrise webhook       Python script      Teams card    │
│  to release branch    triggers GitLab CI    parses JUnit XML   with pass/    │
│                       ─────────────────     + screenshots →    fail matrix   │
│  Bitrise builds       GitLab Runner         auto-publishes     + Confluence  │
│  new APK/IPA          uploads APK to        branded report     link          │
│                       BrowserStack →        page per run       ─────────     │
│  Build artifact       Maestro Cloud                            Outlook       │
│  ready                runs smoke suite      Version-tagged     email with    │
│                       on real devices       report with        summary to    │
│                                             brand matrix       stakeholders  │
│                       JUnit XML +                                            │
│                       screenshots                                            │
│                       captured                                               │
│                                                                              │
│  Bitrise ──► GitLab CI ──► BrowserStack ──► Confluence ──► Teams + Outlook   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Execution Infrastructure

| Component | Service | Purpose |
|-----------|---------|---------|
| **Build** | Bitrise | Builds APK/IPA, triggers Shuriken via webhook |
| **CI Orchestration** | GitLab CI/CD | Pipeline stages, runners, artifact management |
| **Test Execution** | BrowserStack + Maestro Cloud | Real Android/iOS devices in the cloud |
| **Reporting** | Confluence API | Auto-published test report per run |
| **Notification** | Teams Webhook + Outlook | Adaptive card + email with results & link |

### Pipeline Steps

| Step | Trigger | Action | Output |
|------|---------|--------|--------|
| **① Build Published** | Developer merges → Bitrise builds APK/IPA | Bitrise webhook triggers GitLab CI pipeline | Build artifact (APK/IPA) available |
| **② Upload to BrowserStack** | GitLab Runner picks up job | APK uploaded to BrowserStack App Automate via API | `bs://app_url` for device testing |
| **③ Smoke Tests on BrowserStack** | Maestro Cloud + BrowserStack | Runs brand-specific smoke suite on real Android devices | JUnit XML + screenshots |
| **④ Confluence Report** | Smoke suite completes | `publish-confluence-report.py` auto-creates branded report page | Confluence page URL |
| **⑤ Team Notification** | Report published | `notify.py` posts Adaptive Card to Teams + sends Outlook email | QA team informed with link |

---

## Why Maestro?

| Feature | Maestro | Appium/WDIO |
|---------|---------|-------------|
| Setup time | **0 min** (single CLI) | 30–60 min (Java, Node, drivers) |
| Test authoring | **YAML** — readable by QA & PMs | TypeScript + Page Objects |
| Execution speed | **~5s per flow step** | ~15–30s per step (JSON Wire) |
| Flakiness | Built-in retry & wait | Manual waits, brittle selectors |
| CI/CD | Single binary, no server | Appium server + driver install |

---

## Quick Start

### 1. Start Local Shuriken Web Server

```bash
python serve.py
# http://localhost:8888
```

### 2. Install Maestro

```bash
# Windows — see the installation guide below
# https://maestro.mobile.dev/getting-started/installing-maestro

# macOS / Linux
curl -Ls "https://get.maestro.mobile.dev" | bash
```

### 3. Verify

```bash
maestro -v
# Expected: 2.3.0
```

### 4. Run Your First Test

```bash
# Ensure an Android emulator is running
maestro test projects/automation/maestro/flows/brand3/smoke/app-launch.yaml
```

### 5. Run Full Smoke Suite

```powershell
.\scripts\run-smoke-suite.ps1
```

---

## Project Structure

```
shuriken/
├── .gitlab-ci.yml               # GitLab CI/CD pipeline definition
├── README.md
├── config/
│   ├── brands.yaml              # App bundle IDs per brand
│   ├── projects.yaml            # Multi-domain project registry
│   └── test_data.yaml           # Users, locations, cards, timeouts (per brand)
├── projects/
│   ├── automation/              # E2E test automation domain
│   │   └── maestro/             # Maestro mobile test project
│   │       ├── .maestro/        # Maestro global config
│   │       ├── flows/           # Test flows organized by brand
│   │       │   ├── brand3/
│   │       │   │   ├── smoke/   # Smoke suite (~30s each)
│   │       │   │   ├── auth/    # Authenticated flows
│   │       │   │   ├── guest/   # Guest E2E
│   │       │   │   ├── order/   # Order flows
│   │       │   │   ├── menu/    # Menu browsing
│   │       │   │   └── account/ # Account flows
│   │       │   ├── brand1/
│   │       │   │   └── smoke/
│   │       │   └── b2/
│   │       │       └── smoke/
│   │       └── shared/          # Reusable sub-flows (DRY)
│   │           ├── launch-and-dismiss.yaml
│   │           ├── sign-in.yaml
│   │           ├── sign-out.yaml
│   │           ├── select-location.yaml
│   │           ├── menu-add-item.yaml
│   │           └── guest-checkout.yaml
│   ├── jira/                    # Jira/Xray automation domain
│   │   └── testCaseFullMeal/    # Gherkin + Comet test case automation (TypeScript)
│   │       ├── src/
│   │       │   ├── generators/  # Comet batch prompt generators
│   │       │   ├── runners/     # Xray updater + LWL creator
│   │       │   └── client/      # Jira/Xray REST & GraphQL client
│   │       └── .env             # API tokens (git-ignored)
│   └── menu/                    # Menu engineering domain
│       ├── findUnmapped/        # MenuApi unmapped product validator
│       │   ├── find_unmapped.py       # Core CLI tool
│       │   ├── interactive.py         # Interactive CLI (manual/CSV/quick)
│       │   ├── web_server.py          # Flask web UI server (port 5050)
│       │   ├── web/index.html         # Flask-served SPA
│       │   └── public/index.html      # Standalone static version
│       └── pages/               # GitLab Pages static site
│           └── site/
│               ├── index.html   # Card-based landing page
│               └── tools.html   # Unified 3-tool dashboard
├── scripts/
│   ├── ci/                      # CI/CD pipeline scripts
│   │   ├── browserstack-maestro.py      # BrowserStack Maestro runner
│   │   ├── bitrise-to-browserstack.py   # Bitrise → BrowserStack uploader
│   │   ├── shuriken_config.py            # Multi-project config loader
│   │   ├── publish-confluence-report.py # JSON → Confluence page
│   │   └── notify.py                    # Teams + Outlook notifications
│   ├── run-smoke-suite.ps1      # Local multi-brand smoke runner
│   ├── run-maestro.ps1          # Smart runner (parses test_data.yaml → env vars)
│   └── record-test.ps1          # Screen recording during test execution
├── screenshots/                 # Auto-captured (git-ignored)
└── test-results/                # JUnit XML output (git-ignored)
```

---

## Running Tests

### Direct Maestro CLI

```bash
# Single flow
maestro test projects/automation/maestro/flows/brand3/smoke/app-launch.yaml

# All smoke tests for a brand
maestro test projects/automation/maestro/flows/brand3/smoke/

# Full brand suite
maestro test projects/automation/maestro/flows/brand3/

# All brands
maestro test projects/automation/maestro/flows/
```

### Smoke Suite Runner

```powershell
# Run all 12 smoke tests across 3 brands with results table
.\scripts\run-smoke-suite.ps1
```

### Smart Runner (auto-injects test data)

```powershell
# Reads test_data.yaml → injects BUNDLE_ID, credentials, store, card as --env
.\scripts\run-maestro.ps1 -Flow projects/automation/maestro/flows/brand3/smoke/app-launch.yaml -Brand brand3
.\scripts\run-maestro.ps1 -Flow projects/automation/maestro/flows/brand3/guest/pickup-order.yaml -Brand brand3
```

### Interactive Debugging

```bash
maestro studio
```

---

## Brands & Coverage

| Brand | Bundle ID (UAT) | Smoke Tests | Critical Path |
|-------|-----------------|-------------|---------------|
| **Brand Three** | `com.example.brand3.uat` | ✅ 4 tests | Sign-in, Guest Pickup, Auth Delivery |
| **Brand One** | `com.example.brand1.uat` | ✅ 4 tests | Planned |
| **B2** | `com.example.brand2.uat` | ✅ 4 tests | Planned |
| **Brand Four'** | `com.example.brand4.uat` | Planned | Planned |

### Smoke Tests (per brand)

| Test | What it validates |
|------|-------------------|
| `app-launch.yaml` | Cold start → home screen visible |
| `store-search.yaml` | Zip code search → store found |
| `tab-navigation.yaml` | Home, Menu, Orders, Rewards, Bag tabs |
| `browse-menu.yaml` | Menu tab → categories load |

### Critical Path Flows (Brand Three)

| Flow | Description |
|------|-------------|
| `sign-in-out.yaml` | Sign in → verify → sign out → verify |
| `pickup-order.yaml` | Guest ASAP pickup → MasterCard → place order |
| `signin-order.yaml` | Auth user delivery → Visa 4111 → place order |

---

## Architecture Patterns

> Adapted from a battle-tested production-sanity suite: the selectors and wait
> strategies below were proven against real devices before being generalized here.

| Pattern | Description |
|---------|-------------|
| **`${BUNDLE_ID}` env var** | All flows use env var, not hardcoded app IDs |
| **testID selectors** | `id: "TabBar.Menu.label"` preferred over `text: "Menu"` |
| **`extendedWaitUntil`** | Reliable waits with explicit timeouts |
| **`hideKeyboard`** | After every `inputText` to prevent overlap |
| **`evalScript` RUN_ID** | Unique timestamp in screenshot filenames |
| **`runFlow` + `when`** | Conditional steps that don't fail if element missing |
| **Brand-specific test data** | `test_data.yaml` sections per brand, injected as env vars |

---

## Menu Tools Suite

> **Live at: [https://your-pages.example.io](https://your-pages.example.io)**

A browser-based validation toolkit for Example Corp menu engineering — no backend required.

### Tools

| Tool | Brands | Description |
|------|--------|-------------|
| **🔍 Unmapped Product Checker** | B1, B2, B3 | Validates product IDs against MenuApi `unmapped_items` API. Manual entry or CSV upload. |
| **📊 Menu Delta Analyzer** | B1, B2, B3 | Compares PROD vs UAT IDP menus — detects new products, missing items, display name mismatches. |
| **🗺️ Mapping Validator** | B1, B2 | Validates Location Menu vs Master Menu POS-ID mappings via MenuApi API. |

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  GitLab Pages (static site, no server)              │
│                                                     │
│  index.html    ─── Card-based landing page          │
│       │                                             │
│       ├──→  tools.html?tool=unmapped  ── Checker    │
│       ├──→  tools.html?tool=analyzer  ── Analyzer   │
│       └──→  tools.html?tool=mapper    ── Validator  │
│                                                     │
│  Browser calls APIs directly:                       │
│  • MenuApi: menu-api.example/api/v1  │
│  • IDP PROD:  api.brand2.example/menu/    │
│  • IDP UAT:   menu2-b2.staging.staging.example/          │
└─────────────────────────────────────────────────────┘
```

### findUnmapped CLI

Also available as a local CLI tool:

```bash
# Core CLI — check specific products
cd projects/menu/findUnmapped
python find_unmapped.py --brand B1 --locations 10092,10093 --products shamrock-farms-lowfat-chocolate-milk

# Interactive CLI — guided mode
python interactive.py

# Web UI (Flask on localhost:5050)
python web_server.py
```

---

## Jira/Xray Test Automation

> **Project: `projects/jira/testCaseFullMeal/`** (TypeScript)

Automated bulk operations against Jira REST API v3 and Xray Cloud GraphQL API.

### Capabilities

| Feature | Description |
|---------|-------------|
| **Gherkin Updater** | Bulk-updated 109 APP test cases with BDD Given/When/Then steps via Xray GraphQL |
| **Comet Batch Generator** | Generated 45 imperative Comet prompts for WEB test cases across 11 scenarios |
| **LWL Loyalty Creator** | Auto-created 25 LWL Loyalty test cases (7 WEB + 9 iOS + 9 AOS) in Jira + Xray |
| **Description Pusher** | Per-test Jira description updater for Comet-generated content |

### New Jira/Scope Utilities

| Utility | Purpose |
|---------|---------|
| `te-status-list` | Fetches all tests (or non-passed only) for a Test Execution with status and summary export |
| `single-status-update` | Updates one test run status/comment in a specific Test Execution |
| `fetch_release_scope.py` | Fetches Jira release scope by fixVersion and exports JSON/CSV |
| `scope_coverage_matrix.py` | Builds component-level coverage matrix across multiple Test Executions vs release scope |

---

## Web Assistant and API Endpoints

The local Shuriken server (`serve.py`) now provides same-origin APIs used by the web UI.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Local server health |
| `/api/chat` | POST | Skill-routed assistant endpoint (OTP, TE status, release scope, coverage matrix) |
| `/api/otp` | POST | OTP retrieval proxy for browser clients |
| `/api/version-compare/tree` | GET | Version compare file discovery |
| `/api/version-compare/file` | GET | Version compare file fetch |

### OTP Note for GitLab Pages

GitLab Pages is static hosting. OTP retrieval requires a backend API endpoint (`/api/otp`) to proxy notifications-service calls. Without a deployed backend, OTP will not work from static-only hosting.

### Usage

```bash
cd projects/jira/testCaseFullMeal
npx ts-node src/runners/lwl-loyalty-creator.ts        # Create LWL test cases
npx ts-node src/runners/comet-description-updater.ts  # Push Comet descriptions
```

---

## CI/CD Integration

All test execution runs on **GitLab CI/CD Runners** with tests executing on **BrowserStack real devices**.

### Pipeline Stages (`.gitlab-ci.yml`)

```
upload → test → report → notify
```

| Stage | Job | What it does |
|-------|-----|-------------|
| **upload** | `upload-app-to-browserstack` | Uploads APK from Bitrise to BrowserStack App Automate |
| **test** | `smoke-test` | Runs brand smoke suite via Maestro Cloud on BrowserStack devices |
| **test** | `smoke-test-matrix` | Parallel smoke run across all 3 brands (scheduled/on-demand) |
| **report** | `publish-confluence-report` | Parses JUnit XML → generates Confluence page with brand matrix |
| **notify** | `notify-teams-outlook` | Posts Adaptive Card to Teams + sends Outlook email with link |

### GitLab CI/CD Variables Required

Set these in **GitLab → Settings → CI/CD → Variables**:

| Variable | Description |
|----------|-------------|
| `BROWSERSTACK_USERNAME` | BrowserStack username |
| `BROWSERSTACK_ACCESS_KEY` | BrowserStack access key |
| `MAESTRO_CLOUD_API_KEY` | Maestro Cloud API key |
| `CONFLUENCE_EMAIL` | Confluence service account email |
| `CONFLUENCE_API_TOKEN` | Confluence API token |
| `CONFLUENCE_PARENT_PAGE_ID` | Parent page ID for reports |
| `TEAMS_WEBHOOK_URL` | Teams incoming webhook URL |
| `OUTLOOK_WEBHOOK_URL` | (Optional) Power Automate webhook for email |

### Trigger from Bitrise

```yaml
# Bitrise step: triggers Shuriken pipeline after successful build
- trigger-pipeline@0:
    inputs:
    - pipeline_id: shuriken-smoke
    - variables: |
        BRAND=brand3
        BUILD_VERSION=$BITRISE_BUILD_NUMBER
        APP_URL=$BITRISE_PUBLIC_INSTALL_PAGE_URL
```

### Manual Trigger

```bash
# Trigger via GitLab API
curl -X POST \
  -F "ref=main" \
  -F "variables[BRAND]=brand3" \
  -F "variables[BUILD_VERSION]=manual" \
  "https://gitlab.com/api/v4/projects/<PROJECT_ID>/trigger/pipeline?token=<TRIGGER_TOKEN>"
```

### CI Helper Scripts (`scripts/ci/`)

| Script | Purpose |
|--------|---------|
| `parse-junit-results.py` | JUnit XML → structured JSON summary per brand |
| `publish-confluence-report.py` | JSON summaries → Confluence page with brand matrix |
| `notify.py` | JSON summaries → Teams Adaptive Card + Outlook email |

---

## MCP Integrations

| Server | Purpose |
|--------|---------|
| **example-mcp** | Jira, GitLab, Confluence, Bitrise, Figma |
| **browserstack** | Real device cloud testing |
| **maestro** | Maestro Cloud execution |
| **postman-api-mcp** | API testing |

---

## Status

Stated plainly, because a platform README that hides its gaps is worth less than one that doesn't.

**Verified on every push** — `30 planner unit tests`, three TypeScript projects typechecked, all config YAML parsed, and a sanitization scan

**Built and running**
- Mobile smoke suites across brands, with shared sub-flows and a data-injecting runner
- Shared Jira REST + Xray GraphQL client with token refresh, used by every test-management tool
- Test-case generation (Gherkin, browser-automation prompts) and result upload, both with dry-run
- Risk-based regression planner with unit tests
- Menu delta analyzer, mapping validator, unmapped-product checker
- API automation from OpenAPI specs and Postman collections via Newman
- Build → device cloud → wiki report → notification pipeline
- Static portal with browser-based tools and a local API server

**In progress**
- Critical-path E2E beyond smoke on every brand
- iOS coverage alongside Android
- Fourth-brand onboarding

**Known limitations**
- The CI pipeline is written for a GitLab-CI-style runner; porting it to another CI means rewriting `.gitlab-ci.yml`, not just the helper scripts
- Several PowerShell runners assume Windows; the Python and TypeScript tools are cross-platform
- `desktop/` and `tools/otp-app/` are paused, superseded by the `serve.py` API
- The `super-appium` agentic suite is exploratory — capable but less predictable than the Maestro flows
- Every external endpoint in this repository is a placeholder; the tools need real configuration to do anything

## Related

[**play-left**](https://github.com/kavikar/play-left) — the multi-brand Playwright web E2E framework this platform's web coverage lives in.

## License

MIT
