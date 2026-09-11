# Maestro E2E Testing

BrowserStack Maestro-based mobile E2E testing for all Example Corp apps.

- **Flows**: `flows/` (brand-specific test flows)
- **Shared**: `shared/` (reusable sub-flows)
- **Config**: `config/projects.yaml` (brands, devices, custom IDs)

## Brands

| Brand | Code | BrowserStack Custom ID |
|-------|------|----------------------|
| Brand Three | b3 | `b3-staging` / `b3-staging-ios` |
| Brand One | b1 | `b1-staging` / `b1-staging-ios` |
| B2 | b2 | `b2-staging` / `b2-staging-ios` |
| Brand Four | b4 | `b4-staging` / `b4-staging-ios` |

## Test Suites

- **smoke** — Quick sanity (sign-in, sign-out)
- **order** — Full order flows (guest + authenticated)
- **auth** — Authentication flows
- **regression** — Full regression
