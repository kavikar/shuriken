# CLAUDE.md — AI Context & Rules for testCaseFullMeal

> This file provides context and rules for AI assistants working on this project.
> Read this FIRST before making any changes.

---

## 🎯 Project Purpose

**Test case generation and creation** for Example Corp' QA automation.
Takes a Jira EPIC link + date range → generates optimized test cases → creates in Jira + creates Test Execution.

Two primary platforms:
- **APP** — Mobile (Brand Three iOS/Android) — 109 test cases
- **WEB** — Desktop Web (Brand Three via Comet/Playwright) — 45 test cases

**⚠️ This project does NOT handle test execution results.**
Pass/fail status updates live in `testExecutioner` (sibling project).
The shared Xray/Jira client lives in `../shared/xray-client.ts`.

---

## 🔒 Absolute Rules (Never Violate)

### 1. Store Format
- **ALWAYS** use `"1000 1 Example St"` for Micros store (ZIP `00000`)
- **ALWAYS** use `"1001 3805 Example Ave"` for Infor store (ZIP `00000`)
- **NEVER** use old format `"00000 1000 Lab Micros Store"` or `"00000 1001 Lab Infor Store"`
- **NEVER** write just a ZIP code for store selection — use full store string

### 2. Test Credentials
- Email: `user@example.com` (NOT `user@example.com`)
- Password: `replace_me`
- Credit Card: `5555555555554444`
- CC Expiry: `12/33`
- CC CVV: `444`

### 3. Comet Prompts (WEB)
- Comet prompts are **natural language test descriptions**, NOT Playwright code
- Format: plain English steps describing what a human tester would do
- Include store name, URL, exact UI actions
- Do NOT include code syntax, selectors, or assertions
- Comet generates its own Playwright code from the prompt
- **Batch size**: 3–7 tests per Comet session (Comet's recommended limit)
- **Batch grouping rules**:
  - Group tests by similar flow (same auth mode, same store, same feature area)
  - Non-order tests (browse, profile, favorites) go together
  - Order-placement tests go together (same store)
  - Guest flows separate from signed-in flows
  - Infor store tests separate from Micros store tests
- **UAT URL**: `https://ignite-brand3.uat.staging.example/`
- **Comet template sections** (in order):
  1. `Role:` — QA Expert Tester
  2. `ENVIRONMENT:` — UAT URL
  3. `ACCOUNT:` — email/password or Guest
  4. `STORE:` — store name + ZIP
  5. `TEST CARDS:` — both test cards with ZIP
  6. `EXECUTION RULES:` — batch-specific instructions
  7. `SCREENSHOT MOMENTS:` — evidence capture points
  8. `MINI SUMMARY FORMAT:` — per-test result template
  9. `FINAL CONSOLIDATED REPORT FORMAT:` — batch summary table
  10. `TEST CASES TO EXECUTE:` — numbered test blocks

### 4. Gherkin BDD Steps
- Must be **specific** to each test — no vague/generic steps
- Include exact store names, exact product actions, exact UI flows
- Use `Given/When/Then/And` syntax
- Category detection must handle edge cases:
  - "credit" contains "edit" — check `credit-card` BEFORE `edit`
  - "auto-discount" is invalid — use `offers-deals`
  - Check order-related keywords BEFORE generic keywords

### 5. API Patterns
- **Jira REST**: `https://your-tenant.atlassian.net/rest/api/3/`
  - Auth: Basic (email + API token)
  - Search: POST `/search/jql` with `nextPageToken` pagination
  - Description: PUT `/issue/{key}` with ADF body
- **Xray Cloud GraphQL**: `https://xray.cloud.getxray.app/api/v2/graphql`
  - Auth: JWT Bearer (client_id + client_secret → POST `/authenticate`)
  - Token cached for 10 minutes
  - Gherkin: `updateGherkinTestDefinition(issueId: "<NUMERIC_ID>", gherkin: "<text>")`
  - Test type: `updateTestType(issueId: "<NUMERIC_ID>", testType: {name: "Cucumber"})`
  - **issueId** = Jira's numeric `id` field (e.g., `"3884290"`), NOT the issue key
- Always set `NODE_TLS_REJECT_UNAUTHORIZED=0` for corporate proxy/SSL

### 6. ADF (Atlassian Document Format)
- Description field uses ADF JSON, not plain text
- Use `promptToADF()` helper to convert text to ADF
- Structure: `{ type: "doc", version: 1, content: [{ type: "paragraph", content: [...] }] }`

### 7. GENERIC Component Categories (Official)
When classifying or labeling tests, use these official GENERIC components:
- `GENERIC_Reg_Wallet`, `GENERIC_Reg_Payments`, `GENERIC_Reg_Loyalty`
- `GENERIC_Reg_Location`, `GENERIC_Reg_Menu`, `GENERIC_Reg_OfferConstruct`
- `GENERIC_Reg_DeliveryOrder`, `GENERIC_Reg_GiftCards`
- `GENERIC_Reg_ProfileSettings`, `GENERIC_Reg_Auth`
- `GENERIC_Reg_GuestOrder`, `GENERIC_Reg_Cart`
- `GENERIC_Reg_FavoriteItems`, `GENERIC_Reg_FavoriteLocations`
- `GENERIC_Reg_OrderHistory`, `GENERIC_Reg_Nutrition`

### 8. Category Detection Priority (WEB)
When detecting test category from summary, check in this order:
1. `max-quantity` (quantity, max)
2. `temp-unavail-location` (temporarily unavailable + location)
3. `temp-unavail-menu` (temporarily unavailable + menu)
4. `modifier-bag` / `modifier-intensity-bag` / `modifier-intensity-full` (modifiers)
5. `nutrition` (nutrition, calorie)
6. `rewards-price` / `reward-no-qualifying` / `reward-applied` (rewards)
7. `payment-tender-logo` (tender, payment logo)
8. `phone-otp` (phone, OTP)
9. `complex-discount` (discount, promo code)
10. `mfa-profile-deletion` (MFA, profile deletion)
11. `offers-deals` / `offers-deals-promo-verified` (offers, deals)
12. `order-history-reorder` (order history, reorder)
13. `favorite-items` / `favorite-location` / `guest-no-favorites` (favorite)
14. `facebook-login` / `signup` / `change-password` / `login-logout` (auth)
15. `credit-card-edit` / `new-credit-card` (credit card) ← BEFORE generic "edit"
16. `confirmation-email` (confirmation)
17. `profile-update` (profile, editing) ← word-boundary regex `\bediting\b`
18. `guest-order` / `auth-order` (order placement) ← check AFTER credit-card
19. `map-pin` (map, pin)
20. `menu-browse` (menu, browse) ← fallback

---

## 📁 File Organization

```
projects/jira/
├── shared/              # 🔗 Shared Jira REST + Xray GraphQL client
│   └── xray-client.ts   # Single source of truth for API calls
├── testCaseFullMeal/    # 🍔 THIS PROJECT — test case generation
│   └── src/
│       ├── client/      # Re-exports from ../shared/ (backward compat)
│       ├── generators/  # Gherkin + prompt generators
│       ├── registry/    # Static test case key registries
│       ├── extractors/  # Dynamic test case extraction from Xray
│       ├── runners/     # Bulk operation scripts (create, update, verify)
│       ├── reports/     # Report generation
│       └── archive/     # Retired one-off scripts
├── testExecutioner/     # ⚔️ Test execution results (CSV → pass/fail → Xray)
└── dontBugMe/           # 🐛 Future: bug tracking & analysis tool
```

---

## 🔄 Workflow

```
User provides scope
       │
       ▼
┌─────────────────┐
│ Test Case        │  ← Extract from Test Set / Execution / Plan / JQL
│ Extractor        │
└────────┬────────┘
         │ test cases with full metadata
         ▼
┌─────────────────┐
│ Gherkin          │  ← Generate platform-specific BDD steps
│ Generator        │     (app-gherkin or web-gherkin)
└────────┬────────┘
         │ gherkin text
         ▼
┌─────────────────┐
│ Prompt           │  ← Generate executor-specific prompts
│ Generator        │     (Comet for web, Maestro for app)
└────────┬────────┘
         │ prompts
         ▼
┌─────────────────┐
│ Bulk Runner      │  ← Push to Xray / Jira
│ + Verifier       │  ← Verify correctness
└────────┬────────┘
         │ results
         ▼
┌─────────────────┐
│ Report           │  ← Generate HTML/JSON reports
│ Generator        │
└─────────────────┘
```

---

## 🧪 Test Data Quick Reference

| Constant | Value | Usage |
|----------|-------|-------|
| `STORE_1` | `1000 1 Example St` | Micros POS store |
| `STORE_ZIP_1` | `00000` | ZIP for Micros store |
| `STORE_2` | `1001 3805 Example Ave` | Infor POS store |
| `STORE_ZIP_2` | `00000` | ZIP for Infor store |
| `TEST_EMAIL` | `user@example.com` | Default test email |
| `TEST_PASSWORD` | `replace_me` | Default test password |
| `TEST_CC` | `5555555555554444` | Test credit card number |
| `TEST_CC_EXP` | `12/33` | Test CC expiry |
| `TEST_CC_CVV` | `444` | Test CC CVV |
| `BRAND3_WEB_URL` | `https://www.brand3.example` | Web test base URL |

---

## ⚠️ Common Pitfalls

1. **Don't use `String.matchAll()`** — TypeScript ES2020 target causes issues. Use `RegExp.exec()` loop instead.
2. **Xray needs numeric ID** — When calling Xray mutations, pass `issue.id` (e.g., `"3884290"`), not `issue.key` (e.g., `"TE-10045"`).
3. **Rate limiting** — Use batch processing with delays (10 per batch, 1.5s between batches).
4. **JWT token expiry** — Xray tokens expire in ~10 minutes. Client auto-refreshes.
5. **Description field is ADF** — Never push plain text to Jira description. Always use ADF format.
6. **"auto-discount" is not valid** — The correct GENERIC category is `offers-deals`.
7. **Corporate SSL** — Always set `NODE_TLS_REJECT_UNAUTHORIZED=0`.
