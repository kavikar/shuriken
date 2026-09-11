# Copilot Tool Steps (Minimal)

## 1. One-time setup

1. Open shuriken/.vscode/mcp.json.
2. Start the example-mcp server in VS Code.
3. When prompted, enter your own credentials:
   - GitLab token
   - Jira email or username
   - Jira API token
   - Planner token
4. Ensure planner credentials are available in projects/jira/.env.

## 2. Confirm configuration

1. Open projects/jira/xray-regression-planner/config.yaml.
2. Verify copilot_chat mappings are filled for your brand codes and platform filters or test sets.

## 3. Run dry-run first

From projects/jira/xray-regression-planner, run:

python main.py copilot-executions --prompt "create test executions for release 26.12 for all brands brand1,brand2,brand3" --config config.yaml --env-file ../.env --dry-run

Expected outcome:
- Preflight passed
- Non-zero scope_items
- Non-zero test_inventory

## 4. Publish test executions

Run the same command without --dry-run:

python main.py copilot-executions --prompt "create test executions for release 26.12 for all brands brand1,brand2,brand3" --config config.yaml --env-file ../.env

## 5. If preflight fails

1. Fix missing brand mappings in config.yaml.
2. Confirm release value and Jira visibility.
3. Confirm Xray permissions and test source filters or test sets.
4. Re-run dry-run.
