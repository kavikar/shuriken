# CLAUDE.md — shuriken agent context

A unified QA platform for Example Corp (Brand One, Brand Two, Brand Three, Brand Four):
mobile and API automation, Jira/Xray test-management automation, menu-data validation,
and CI/CD orchestration.

Generic by construction — fictional brands, placeholder hosts, no real credentials,
store data, or issue keys. Keep it that way.

- Local dev: `python serve.py` (port 8888)
- CI: `.gitlab-ci.yml`, generated from `config/projects.example.yaml`
- Web E2E is NOT here: it lives in https://github.com/kavikar/play-left
  (see `projects/automation/playwright-web/README.md`)

## Project Structure
- site/: Static portal (index.html, menu tools, quick bites, Jira tools)
- projects/jira/: Jira/Xray automation (shared client, testCaseFullMeal, testExecutioner, xray-regression-planner)
- projects/automation/: maestro (mobile), super-appium (agentic), playwright-web (pointer to play-left)
- projects/api-automation/: OpenAPI/Postman → Newman
- projects/menu/: analyzer, mapper, findUnmapped — canonical home for the menu tools
- projects/quickBites/: service health checks, OTP
- scripts/: CI/CD, Maestro runners, regression analysis
- config/: Brand/env/project/test-data YAMLs — the registry every tool reads
- desktop/, tools/otp-app/: Paused desktop apps (bundled from projects/menu/, not vendored copies)

## Design System
- Brand colors: Brand One #d4242b, Brand Two #f4b223, Brand Three #0072ce, Brand Four #ff671f
- Theme: Dark, accent #6c63ff, concentric circles logo

## Key Tools
- offer-test-generator.ts: EPIC → test cases → Jira/Xray → auto-create Test Executions
- testExecutioner: CSV/JSON/MD → Xray test run status updates
- Menu Mapping Validator, Menu Delta Analyzer, Unmapped Product Checker
- OTP Retriever, Version Compare (Quick Bites)

## Must-Have Agent Skills (For Your Workflow)
- Context loading skill: quickly read TE scope, pending statuses, and prior batch history before taking action.
- Prompt adaptation skill: convert raw test definitions into Comet-ready prompts that execute reliably (no tool-mismatch framing).
- Execution triage skill: identify what is truly pending (EXECUTING/TODO/BLOCKED/Not-Applicable) and prioritize highest-impact reruns.
- Jira/Xray API skill: fetch live data, map test keys accurately, and avoid manual copy errors when building or updating runs.
- Status update skill: normalize mixed result formats into clean PASS/FAIL/BLOCKED/TODO payloads and upload safely.
- Evidence governance skill: enforce screenshot checkpoints, confirmation capture, and defect-ready notes for each failed/blocked case.
- Targeted-offer handling skill: account for eligibility gates, daypart/date constraints, and proper BLOCKED vs FAIL decisions.
- Report synthesis skill: produce mini summaries plus consolidated final tables with discount math and order-level traceability.
- Safe cleanup skill: archive generated artifacts by date, keep active files discoverable, and never destroy execution evidence.
- Recovery skill: when a run is interrupted, resume from latest TE/export state and regenerate only the missing pieces.

## Agent Do/Don't Rules

### Do
- Do read current TE status first and act only on pending/in-scope tests.
- Do prefer API-based data retrieval (Jira/Xray) over manual copy/paste.
- Do generate Comet prompts in executable natural-language format with clear evidence checkpoints.
- Do enforce one-offer-per-order and explicit PASS/FAIL/BLOCKED criteria.
- Do preserve confirmation numbers, discount amounts, and notes in every summary.
- Do use archive-first cleanup (move files, do not delete) with date-stamped folders.
- Do keep active prompt files in place and archive only historical/generated artifacts.
- Do provide deterministic output formats so uploads and reports are repeatable.

### Don't
- Don't use DevTools/MCP/tooling language in Comet prompts that causes execution refusal.
- Don't update Xray statuses without matching test keys in the active TE.
- Don't mark targeted offers as FAIL when the offer is not visible; use BLOCKED with evidence.
- Don't mix multiple offers in a single order unless a test explicitly requires it.
- Don't overwrite or remove prior evidence artifacts; archive them.
- Don't run destructive cleanup commands in reports folders.
- Don't change store/account constants casually; keep environment contracts stable.

## Jira/Xray Issue Type IDs
- 10314: Test
- 10315: Test Set
- 10316: Test Plan
- 10317: Test Execution (correct for TEs)

## Sanitization rules — this repo is public-facing

Never introduce, and remove on sight:
- Real company, brand, or legal-entity names
- Real hostnames, store IDs, addresses, or phone numbers
- Real Jira/Xray issue keys — the fictional range is TE-10001..TE-10118, EPIC-1001+
- Credentials of any kind (the published Visa/Mastercard *test* card numbers are fine)
- Hardcoded personal filesystem paths — use $PSScriptRoot or repo-relative paths

## Completed Work
- Offer test cases (APP+WEB), browser-automation batches, results uploader
- Project restructuring: shared client, testCaseFullMeal, testExecutioner
- Static portal: brand colors, logo, interactive cards
- Version Compare tool, OTP tool, menu tools
- Split web E2E out to play-left; removed the duplicated desktop/servers fork

## Usage Examples
- offer-test-generator: npx ts-node src/runners/offer-test-generator.ts --epics EPIC-1001 --from 2026-04-01 --to 2026-06-30 --platforms WEB,APP
- testExecutioner: npm run upload -- --file results.csv --te TE-10082

## Environment
- .env required for Jira/Xray credentials
- Test accounts: user@example.com / replace_me
- Store: 1000 Example Street, Example City, EX (ZIP: 00000), store 1000

## Future
- Interactive Jira landing page (tabs, expand/collapse, copy buttons)
- dontBugMe: bug analysis, Jira hygiene
- Natural language chatbot for test creation

---
This file is the single source of truth for shuriken project context. Update as the project evolves.
