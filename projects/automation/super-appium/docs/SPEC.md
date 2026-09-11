# SPEC - Super Appium MCP

## Problem Statement

Mobile agentic testing needs a stable Appium MCP harness with brand-aware runtime profiles and repeatable smoke validation.

## Objective

Build a reusable Appium MCP project that can execute agent-guided mobile smoke runs across Brand Three, Brand One, B2, and Brand Four using only internal project assets.

## Phase 1 Scope

- Appium doctor script
- Appium server startup script
- Appium MCP startup script
- Brand profile sync from internal profiles/{brand}/maestro.{env}.json
- Runtime capabilities generation and smoke prompt artifact generation

## Non-Goals

- Full checkout completion in this phase
- Multi-device parallel orchestration
- Cloud execution orchestration in this phase

## Success Criteria

1. One command validates local prerequisites.
2. One command generates runtime profile, capabilities, and smoke prompt.
3. Appium MCP can be launched with generated capabilities config.
