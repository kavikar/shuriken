# Test Case Full Meal 🍽️

> **One-stop toolkit for Xray test case management, BDD Gherkin generation, and AI-ready prompt creation for Comet (Web) and Maestro (App) test executors.**

## What This Does

Given a scope of test cases (Test Set, Test Execution, Test Plan, or ad-hoc list), this toolkit:

1. **Extracts** all test case details from Jira/Xray (summary, labels, components, steps)
2. **Generates** Gherkin BDD steps tailored to each test's functional area
3. **Pushes** Gherkin to Xray Cloud via GraphQL API
4. **Creates** AI-ready prompts for:
   - **Comet** (Brand Three Desktop Web E2E via Playwright)
   - **Maestro** (Mobile App E2E — iOS/Android)
5. **Reports** results with pass/fail status

## Project Structure

```
testCaseFullMeal/
├── .env.example          # Template for API credentials
├── package.json          # Dependencies & npm scripts
├── tsconfig.json         # TypeScript config
├── CLAUDE.md             # AI context & rules for future sessions
│
├── src/
│   ├── client/
│   │   └── xray-client.ts          # Core API client (Jira REST + Xray GraphQL)
│   │
│   ├── generators/
│   │   ├── app-gherkin-generator.ts # APP (mobile) Gherkin BDD generator
│   │   ├── web-gherkin-generator.ts # WEB (desktop) Gherkin BDD generator
│   │   ├── comet-prompt-generator.ts# Comet-ready AI prompt generator (Web)
│   │   └── maestro-prompt-generator.ts # Maestro-ready prompt generator (App) [FUTURE]
│   │
│   ├── registry/
│   │   ├── app-test-cases.ts        # APP test case keys (109 tests)
│   │   └── web-test-cases.ts        # WEB test case keys (45 tests)
│   │
│   ├── extractors/
│   │   └── test-case-extractor.ts   # Extract test cases from Test Set/Execution/Plan
│   │
│   ├── runners/
│   │   ├── app-bulk-update.ts       # Bulk push Gherkin for APP tests
│   │   ├── bulk-set-jira-fields.cjs # Generic Jira field bulk updater
│   │   ├── split-web-offer-batches.cjs # Split WEB offer prompt files into execution batches
│   │   ├── te-offer-prompt-push.cjs # Push WEB/APP offer prompts from TE scope to Jira descriptions
│   │   ├── web-bulk-update.ts       # Bulk push Gherkin + Comet for WEB tests
│   │   └── verify-all.ts            # Verification: check all tests are correct
│   │
│   └── reports/
│       └── report-generator.ts      # Generate HTML/JSON test result reports
│
└── reports/                          # Output folder for generated reports
```

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Copy and fill in credentials
cp .env.example .env
# Edit .env with your Jira + Xray credentials

# 3. Extract test cases from a Test Set
npx ts-node src/extractors/test-case-extractor.ts --test-set TE-10048

# 4. Dry-run WEB Gherkin generation
npx ts-node src/runners/web-bulk-update.ts --dry-run

# 5. Live push
npx ts-node src/runners/web-bulk-update.ts
```

## NPM Scripts

| Script | Description |
|--------|-------------|
| `npm run extract -- --test-set TE-10048` | Extract all test cases from a Test Set |
| `npm run extract -- --test-plan TE-XXXXX` | Extract from a Test Plan |
| `npm run extract -- --jql "project = IQE AND ..."` | Extract via JQL |
| `npm run app:dry-run` | Preview APP Gherkin changes |
| `npm run app:update` | Push APP Gherkin to Xray |
| `npm run web:dry-run` | Preview WEB Gherkin + Comet changes |
| `npm run web:update` | Push WEB Gherkin + Comet to Xray |
| `npm run verify` | Verify all tests in Xray are correct |

## Test Data

| Field | Value |
|-------|-------|
| Email | `user@example.com` |
| Password | `replace_me` |
| Store (Micros) | `1000 1 Example St` (ZIP `00000`) |
| Store (Infor) | `1001 3805 Example Ave` (ZIP `00000`) |
| Credit Card | `5555555555554444` / `12/33` / `444` |

## APIs Used

- **Jira REST API v3** — Issue metadata, search, description updates
- **Xray Cloud GraphQL v2** — Gherkin definitions, test types, test sets

## Reusable Bulk Field Updates

Use the generic Jira field updater when you need to set one or more fields across a TE, key list, JQL scope, or CSV file.

Runner:
- [src/runners/bulk-set-jira-fields.cjs](src/runners/bulk-set-jira-fields.cjs)

Supported scope inputs:
- `--test-execution TE-10095`
- `--keys TE-10083,TE-10085`
- `--jql "project = IQE AND labels = Offers"`
- `--csv reports/field-updates.csv`

Supported assignment patterns:
- One field, one value:
   `node src/runners/bulk-set-jira-fields.cjs --test-execution TE-10095 --field "Automation Status=Automated via Prompt"`
- One field, multiple values:
   `node src/runners/bulk-set-jira-fields.cjs --keys TE-10083 --field "Labels=Offers|UAT|Prompted"`
- Multiple fields, one command:
   `node src/runners/bulk-set-jira-fields.cjs --keys TE-10083,TE-10085 --fields "Automation Status=Automated via Prompt;Labels=Offers|UAT|Prompted;Priority=High"`

CSV format:

```csv
issueKey,Automation Status,Labels,Priority
TE-10083,Automated via Prompt,"Offers|UAT|Prompted",High
TE-10085,Automated via Prompt,"Offers|UAT|Prompted",High
```

Notes:
- Multiselect values use `|` as the separator.
- Use `--dry-run` first when validating field names or allowed values.
- Select-list values must match Jira option values exactly.

## Offer Prompt Runners

Use the TE-scoped offer prompt runner when the user wants Jira descriptions updated from a WEB or APP offers execution.

Runner:
- [src/runners/te-offer-prompt-push.cjs](src/runners/te-offer-prompt-push.cjs)

Examples:
- Dry run: `node src/runners/te-offer-prompt-push.cjs TE-10095 TE-10096`
- Apply updates: `node src/runners/te-offer-prompt-push.cjs TE-10095 TE-10096 --apply`

Generated prompt outputs:
- WEB: `reports/comet-offers/comet/`
- APP: `reports/maestro-prompts/`

## WEB Offer Batch Splitting

Use the WEB batch splitter to break a combined TE prompt file into smaller execution chunks.

Runner:
- [src/runners/split-web-offer-batches.cjs](src/runners/split-web-offer-batches.cjs)

Current usage:
- `node src/runners/split-web-offer-batches.cjs`

Output location:
- `reports/comet-offers/comet/te-10117-web-<date>-batch-*.txt`
