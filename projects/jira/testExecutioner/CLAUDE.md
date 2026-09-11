# CLAUDE.md — AI Context & Rules for testExecutioner

> This file provides context and rules for AI assistants working on this project.
> Read this FIRST before making any changes.

---

## 🎯 Project Purpose

**testExecutioner** handles the **execution results** side of the test lifecycle.
It takes pass/fail results from any test execution tool (Comet, Maestro, manual spreadsheets, CI/CD)
and pushes them to Xray Cloud as test run status updates with optional evidence attachments.

**This is NOT the test creation tool.** Test cases are created by `testCaseFullMeal`.
testExecutioner only updates the *status* of existing test runs inside a Test Execution (TE).

---

## 🔄 Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  Test Execution Happens                                       │
│  (Comet, Maestro, manual testing, CI/CD pipeline)             │
│                                                               │
│  Output: CSV / JSON / Markdown with test IDs + pass/fail      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  testExecutioner — Results Uploader                           │
│                                                               │
│  1. Parse input file (auto-detects CSV/JSON/MD)               │
│  2. Match test IDs to test runs in the TE                     │
│  3. Update PASS/FAIL/BLOCKED/TODO status via Xray GraphQL     │
│  4. Add comments (order ID, defect, notes)                    │
│  5. Upload evidence screenshots (optional)                    │
│  6. Attach results file + PDF to the TE Jira issue            │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 File Organization

```
testExecutioner/
├── package.json           # npm scripts for common operations
├── tsconfig.json          # TypeScript config
├── .env.example           # Credential template
├── CLAUDE.md              # This file
├── src/
│   └── runners/
│       ├── results-uploader.ts    # 🔑 Main tool — CSV/JSON/MD → Xray
│       ├── reset-te.ts            # Reset all test runs in a TE to TODO
│       └── execution-report.ts    # Generate TE status report
└── reports/                # Generated reports (CSV/JSON exports)
```

### Shared Client (../shared/)
Both testExecutioner and testCaseFullMeal share the same Xray/Jira client at
`projects/jira/shared/xray-client.ts`. Import like:
```typescript
import { getConfig, getXrayConfig, xrayGraphQL } from '../../../shared/xray-client';
```

---

## 📋 CSV Format (Recommended Input)

The simplest and most flexible format. Column detection is automatic — use any of these headers:

| Your Column | Maps To | Required |
|---|---|---|
| `test_id`, `testKey`, `key`, `jira_id` | Test case key | ✅ Yes |
| `status`, `result`, `outcome` | PASS/FAIL/BLOCKED/TODO | ✅ Yes |
| `comment`, `notes`, `remark` | Free-form text | Optional |
| `order_id`, `confirmation` | Order/confirmation number | Optional |
| `description`, `offer`, `name` | Test name (for display) | Optional |
| `discount` | Discount amount | Optional |
| `defect`, `bug` | Defect description | Optional |
| `evidence`, `screenshot` | Evidence file path | Optional |

**Example CSV:**
```csv
test_id,status,comment,order_id
TE-10083,PASS,Order placed successfully,ORD-12345
TE-10084,FAIL,Discount not applied,
TE-10085,BLOCKED,Store closed for maintenance,
```

---

## 🔒 Rules

### 1. API Patterns
- **Xray Cloud GraphQL**: `https://xray.cloud.getxray.app/api/v2/graphql`
- Auth: JWT Bearer (client_id + client_secret → `/authenticate`)
- Token cached 10 minutes (auto-refresh in shared client)
- **Jira REST v3**: `https://your-tenant.atlassian.net/rest/api/3/`
- Auth: Basic (email + API token)
- Always set `NODE_TLS_REJECT_UNAUTHORIZED=0` for corporate proxy

### 2. Status Values
- Input accepts: PASS, FAIL, BLOCKED, TODO, PASSED, FAILED, SKIP, SKIPPED
- All normalized before sending to Xray (PASS→PASSED, FAIL→FAILED, etc.)
- Emoji in CSV status field are auto-stripped (✅ PASS → PASS)

### 3. Rate Limiting
- 300ms delay between Xray API calls
- Batch evidence uploads sequentially per test run

### 4. Evidence Files
- Naming convention: `TE-261953_*.png` or `TE-10083-signed-in.png`
- Supported: PNG, JPG, JPEG, GIF, WEBP, PDF
- Pass `--evidence <dir>` to auto-discover files by test key

---

## 🧪 Quick Reference

| Command | Description |
|---|---|
| `npm run dry-run -- --file results.csv --te TE-10082` | Preview upload |
| `npm run upload -- --file results.csv --te TE-10082` | Push to Xray |
| `npm run upload:web -- --file results.csv` | Upload to WEB TE |
| `npm run upload:app -- --file results.csv` | Upload to APP TE |
| `npm run reset -- --te TE-10082 --dry-run` | Preview TE reset |
| `npm run reset -- --te TE-10082 --reset` | Reset all to TODO |
| `npm run report -- --te TE-10082` | Status report |
| `npm run report -- --te TE-10082 --export csv` | Export CSV report |

---

## ⚠️ Common Pitfalls

1. **Column headers are case-insensitive** — `Test_ID`, `TEST_ID`, `test_id` all work
2. **Jira key pattern** — Must match `^[A-Z]+-\d+$` (e.g., TE-10083)
3. **Unmatched keys** — Tests not found in the TE are skipped with a warning
4. **Excel CSV exports** — May prefix discount with `'` (text escape) — auto-stripped
5. **Don't confuse TE with Test Set** — `--te` expects a Test Execution key, not a Test Set
