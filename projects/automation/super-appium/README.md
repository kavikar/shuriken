# Super Appium MCP

Super Appium MCP is a brand-aware mobile automation harness under Shuriken automation projects.
It is fully self-contained and does not depend on external workspace repos.

## Internal Project Contracts

- Brand runtime profiles: profiles/{brand}/maestro.{env}.json
- Generated runtime artifacts: artifacts/runtime/
- Appium MCP client config: mcp.config.json

## Quick Start

1. npm install
2. npm run doctor
3. npm run smoke:brand3:android
4. npm run appium:server
5. npm run appium:mcp:no-ui -- -CapabilitiesConfig artifacts/runtime/brand3.uat.android.capabilities.json

Brand shortcuts:
- npm run smoke:Brand One:android
- npm run smoke:b2:android
- npm run smoke:Brand Four:android

Suite shortcuts:
- npm run suite:brand3:smoke
- npm run suite:Brand One:smoke
- npm run suite:b2:smoke
- npm run suite:Brand Four:smoke

## Primary Scripts

- doctor: validates local prerequisites
- appium:server: starts Appium server with local Android SDK inference
- appium:mcp / appium:mcp:no-ui: starts appium-mcp
- profile:sync: reads internal brand profile into runtime profile artifact
- smoke:agentic: generates runtime profile, capabilities, and prompt artifact
- suite:agentic: generates smoke artifact + per-test prompt pack + combined suite prompt

## Security Model

- Credentials are never copied into committed files.
- Runtime outputs are written to artifacts/runtime.
- Only key presence flags are preserved in profile metadata.

## Brand Profile Setup

Each brand has a starter profile:
- profiles/brand3/maestro.uat.json
- profiles/brand1/maestro.uat.json
- profiles/b2/maestro.uat.json
- profiles/brand4/maestro.uat.json

Replace placeholder values (auth, payment, notification URL) with safe test data before execution.

## Suite Plans

Internal smoke suite plans:
- plans/brand3.smoke.json
- plans/Brand One.smoke.json
- plans/b2.smoke.json
- plans/Brand Four.smoke.json

Plan schema details:
- docs/SUITE_PLAN_FORMAT.md
