# Runbook

## 1. Install dependencies

npm install

## 2. Verify local prerequisites

npm run doctor

## 3. Generate runtime artifacts from existing brand config

Update internal profile values first (placeholders):
- profiles/brand3/maestro.uat.json

npm run smoke:agentic -- -Brand brand3 -Env uat -Platform android

This creates:
- artifacts/runtime/brand3.uat.profile.json
- artifacts/runtime/brand3.uat.android.capabilities.json
- artifacts/runtime/brand3.uat.android.smoke.prompt.txt

## 4. Start Appium server

npm run appium:server

## 5. Start Appium MCP server (new terminal)

npm run appium:mcp:no-ui -- -CapabilitiesConfig artifacts/runtime/brand3.uat.android.capabilities.json

## 6. Execute prompt in MCP client

Use mcp.config.json in your MCP client and run the generated prompt from artifacts/runtime.
