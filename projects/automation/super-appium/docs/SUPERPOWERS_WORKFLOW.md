# Superpowers Workflow - Super Appium MCP

## Lifecycle

1. Refine scope in spec.
2. Confirm phased implementation plan.
3. Implement in small verified batches.
4. Produce deterministic runbook and verification commands.

## Working Agreement

- Use only internal project contracts under this folder.
- Keep scripts deterministic and platform-explicit.
- Do not commit credentials or copied secret values.
- Prefer runtime-generated artifacts in artifacts/runtime.

## Quality Gates

1. doctor script passes.
2. smoke:agentic generates profile, capabilities, and prompt artifacts.
3. appium:mcp can start with generated capabilities config.
