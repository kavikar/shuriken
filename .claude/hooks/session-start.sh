#!/bin/bash
#
# SessionStart hook — prepare the platform so tests and typechecks run immediately.
#
# This repo has three independent npm projects plus a Python package, and one
# ordering trap: projects/jira/shared holds the client the Jira tools compile
# against, so its dependencies must exist before either of them typechecks.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

echo "[session-start] Python: planner dependencies"
pip install --quiet --disable-pip-version-check \
  pytest pydantic pyyaml python-dotenv structlog httpx click rich jinja2

# The planner's package directory is hyphenated, so it cannot be imported as a
# package. Its conftest.py handles pytest; this makes ad-hoc `python -c` work
# from the planner directory too.
echo 'export PYTHONPATH="${PYTHONPATH:-}:$CLAUDE_PROJECT_DIR/projects/jira/xray-regression-planner"' >> "$CLAUDE_ENV_FILE"

# Shared client first — the two Jira tools compile it from ../shared and will
# fail to resolve dotenv and @types/node without it.
echo "[session-start] Node: shared Jira/Xray client"
(cd projects/jira/shared && npm install --no-audit --no-fund --silent)

for project in projects/jira/testCaseFullMeal projects/jira/testExecutioner projects/api-automation; do
  echo "[session-start] Node: $project"
  (cd "$project" && npm install --no-audit --no-fund --silent)
done

echo "[session-start] Ready. Verify with:"
echo "  cd projects/jira/xray-regression-planner && python -m pytest tests/ -q   # 30 passing"
echo "  cd projects/api-automation && npx tsc --noEmit"
