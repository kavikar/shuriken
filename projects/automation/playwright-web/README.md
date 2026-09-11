# Web E2E — lives in `play-left`

Web end-to-end automation for this platform is **not** in this repository. It is
a standalone framework:

### → [github.com/kavikar/play-left](https://github.com/kavikar/play-left)

## Why it was split out

This directory previously held a thin Playwright project (a handful of page
objects and specs) that overlapped almost entirely with `play-left`. Two
frameworks solving the same problem is how selectors drift apart and coverage
claims stop meaning anything, so the thin copy was removed and `play-left`
became the single implementation.

The split follows the seam already in the platform:

| Repository | Scope |
|---|---|
| **shuriken** (this repo) | Mobile (Maestro, Appium), API automation, Jira/Xray test-management automation, menu validation, CI/CD orchestration, the portal |
| **play-left** | Web E2E: brand registry, typed fixtures, page objects, selector tooling, coverage classification, regression manifest |

## The interface between them

`play-left` is a consumer of this platform's contracts, not a subordinate of it:

- **Brands** — `play-left` keeps its own `knowledge/registry/brand-config.json`
  because a web framework needs hosts, store contexts and feature flags that
  `config/brands.yaml` here does not carry. The brand *ids* match
  (`brand-one`…`brand-four`) so results correlate across both repos.
- **Test management** — both write to the same Xray test-run model.
  `play-left` classifies which cases are web-automatable; `testExecutioner`
  here uploads results. Neither reimplements the other's half.
- **Regression scope** — `xray-regression-planner` here decides *what to test*
  (risk scoring, release scope, Xray publishing). `play-left`'s regression
  manifest decides *what is executable on web* (Gherkin → page-object method
  matching). Related question, different answers; keep them separate.

## Using it alongside this repo

```bash
git clone https://github.com/kavikar/play-left
cd play-left && npm install && npx playwright install chromium
npm run typecheck && npx playwright test --project=config
```
