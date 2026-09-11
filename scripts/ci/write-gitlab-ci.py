#!/usr/bin/env python3
"""Generate .gitlab-ci.yml for Shuriken project."""
import sys

content = r'''# ════════════════════════════════════════════════════════════════════
#  Shuriken — Predictive Lifecycle Assurance & Testing Engine
#  GitLab CI/CD Pipeline (Example Corp Convention)
#
#  Brands:  b3 (Brand Three) | b1 (Brand One) | b2 (B2) | b4 (Brand Four)
#
#  App Resolution: Uses --skip-upload-app with BrowserStack custom_id.
#    Upload apps once with custom_id (e.g. b3-staging), then pipeline
#    reuses the last uploaded version automatically.
# ════════════════════════════════════════════════════════════════════

# -- Global defaults --
default:
  image: python:3.11-slim
  tags:
    - ci02-perf

# -- Variables (shown in GitLab Run Pipeline UI) --
variables:
  BRAND:
    value: "b3"
    description: "Brand to test (3-letter code)"
    options:
      - "b3"
      - "b1"
      - "b2"
      - "b4"
      - "all"

  TEST_SUITE:
    value: "auth"
    description: "Test suite to run"
    options:
      - "smoke"
      - "auth"
      - "order"
      - "all"

  TEST_ENV:
    value: "UAT"
    description: "Target environment"
    options:
      - "QA"
      - "UAT"

  BS_DEVICE:
    value: "Samsung Galaxy S25 Ultra-15.0,Google Pixel 10 Pro XL-16.0"
    description: "BrowserStack device(s) — comma-separated for multi-device"
    options:
      - "Samsung Galaxy S25 Ultra-15.0,Google Pixel 10 Pro XL-16.0"
      - "Samsung Galaxy S25 Ultra-15.0"
      - "Google Pixel 10 Pro XL-16.0"
      - "Samsung Galaxy S25-15.0"
      - "Google Pixel 10-16.0"
      - "Google Pixel 9-16.0"
      - "Google Pixel 8-14.0"
      - "Samsung Galaxy S24-14.0"
      - "iPhone 16 Pro Max-18"
      - "iPhone 17-19"
      - "iPhone 15 Pro-17"

  BS_PLATFORM:
    value: "android"
    description: "Target platform"
    options:
      - "android"
      - "ios"
      - "all"

  # BrowserStack credentials (set in GitLab CI/CD Variables → Settings → CI/CD)
  BROWSERSTACK_USERNAME: ""
  BROWSERSTACK_ACCESS_KEY: ""

  # Confluence (Report Publishing)
  CONFLUENCE_EMAIL: ""
  CONFLUENCE_API_TOKEN: ""
  CONFLUENCE_BASE_URL: "https://your-tenant.atlassian.net/wiki"
  CONFLUENCE_SPACE_KEY: "~000000000000"
  CONFLUENCE_PARENT_PAGE_ID: "000000000000"

  # Teams Webhook (Power Automate)
  TEAMS_WEBHOOK_URL: ""

  # Outlook Email Webhook (Power Automate — "Send an email" flow)
  OUTLOOK_WEBHOOK_URL: ""

  # Bitrise Auth Token (for fetching latest app builds)
  BITRISE_AUTH_TOKEN: ""

  # Auto-fetch from Bitrise before running tests (true/false)
  FETCH_FROM_BITRISE:
    value: "false"
    description: "Auto-fetch latest app from Bitrise before testing"
    options:
      - "false"
      - "true"

# -- Workflow rules --
workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'
      when: always
    - if: '$CI_PIPELINE_SOURCE == "trigger"'
      when: always
    - if: '$CI_PIPELINE_SOURCE == "pipeline"'
      when: always
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
      when: always
    - when: never

# -- Stages --
stages:
  - test
  - report
  - notify

# ════════════════════════════════════════════════════════════════════
#  STAGE 1: Run Maestro Tests on BrowserStack
# ════════════════════════════════════════════════════════════════════

.browserstack_base:
  image: python:3.11-slim
  tags:
    - ci02-perf
  before_script:
    - pip install requests pyyaml --quiet
    # ── Optional: Fetch latest app from Bitrise ──
    - |
      if [ "${FETCH_FROM_BITRISE}" = "true" ] && [ -n "${BITRISE_AUTH_TOKEN}" ]; then
        echo "🚀 Fetching latest app from Bitrise for ${BRAND} (${BS_PLATFORM})..."
        python3 scripts/ci/bitrise-to-browserstack.py \
          --brand "${BRAND}" \
          --platform "${BS_PLATFORM}" \
          --env "${TEST_ENV:-uat}" \
          --token "${BITRISE_AUTH_TOKEN}"
        echo "✅ App fetched from Bitrise and uploaded to BrowserStack"
      else
        echo "⏭️  Skipping Bitrise fetch (FETCH_FROM_BITRISE=${FETCH_FROM_BITRISE:-false})"
      fi
    # ── Start BrowserStack Local tunnel so devices can reach UAT APIs ──
    # --force-local ensures ALL device traffic routes through the tunnel
    # (same pattern as automation-ui-api-master and idp-domain-services)
    - apt-get update -qq && apt-get install -y -qq wget unzip > /dev/null 2>&1
    - wget -q "https://www.browserstack.com/browserstack-local/BrowserStackLocal-linux-x64.zip" -O /tmp/bslocal.zip
    - unzip -q /tmp/bslocal.zip -d /usr/local/bin/ && chmod +x /usr/local/bin/BrowserStackLocal
    - /usr/local/bin/BrowserStackLocal --key "${BROWSERSTACK_ACCESS_KEY}" --daemon start --force-local --verbose 1
    - sleep 10
    - echo "Verifying BrowserStack Local tunnel..."
    - /usr/local/bin/BrowserStackLocal --daemon status || echo "Status check not supported in daemon mode"
    - echo "BrowserStack Local tunnel started ✅"
  after_script:
    - /usr/local/bin/BrowserStackLocal --daemon stop 2>/dev/null || true
    - echo "BrowserStack Local tunnel stopped"
  artifacts:
    paths:
      - test-results/
      - screenshots/
    when: always
    expire_in: 30 days

# ════════════════════════════════════════════════════════════════════
#  JOB A: Single-flow suites (auth, smoke)
#         Runs when BRAND != "all" AND TEST_SUITE != "order"
#         Uses --skip-upload-app so BrowserStack resolves app by custom_id
# ════════════════════════════════════════════════════════════════════
browserstack-test:
  extends: .browserstack_base
  stage: test
  rules:
    - if: '$BRAND != "all" && $TEST_SUITE != "order"'
  script:
    - echo "Running Shuriken ${TEST_SUITE} suite for ${BRAND} on ${BS_PLATFORM} — BrowserStack"
    - mkdir -p test-results screenshots
    - |
      case "${TEST_SUITE}" in
        auth)  SUITE_OR_FLOW="--suite auth" ;;
        smoke) SUITE_OR_FLOW="--suite smoke" ;;
        *)     SUITE_OR_FLOW="--suite ${TEST_SUITE}" ;;
      esac
    - echo "Brand     -- ${BRAND}"
    - echo "Suite     -- ${TEST_SUITE}"
    - echo "Device(s) -- ${BS_DEVICE}"
    - echo "Platform  -- ${BS_PLATFORM}"
    - |
      # Split comma-separated devices into --devices arg list
      IFS=',' read -ra DEVICE_LIST <<< "${BS_DEVICE}"
      python3 scripts/ci/browserstack-maestro.py \
        --brand "${BRAND}" \
        --platform "${BS_PLATFORM}" \
        ${SUITE_OR_FLOW} \
        --skip-upload-app \
        --local \
        --devices "${DEVICE_LIST[@]}" \
        --output test-results/${BRAND}-result.json
    - echo "BrowserStack test completed for ${BRAND} (${BS_PLATFORM})"
  timeout: 30m
  allow_failure: true

# ════════════════════════════════════════════════════════════════════
#  JOB B: Order suite — runs ALL order flows in one build
#         Uses --suite order + --skip-upload-app (custom_id)
# ════════════════════════════════════════════════════════════════════
browserstack-order:
  extends: .browserstack_base
  stage: test
  rules:
    - if: '$BRAND != "all" && $TEST_SUITE == "order"'
  script:
    - echo "Running Shuriken ORDER suite for ${BRAND} on ${BS_PLATFORM} — ${BS_DEVICE}"
    - mkdir -p test-results screenshots
    - echo "Brand     -- ${BRAND}"
    - echo "Suite     -- order"
    - echo "Device(s) -- ${BS_DEVICE}"
    - echo "Platform  -- ${BS_PLATFORM}"
    - |
      # Split comma-separated devices into --devices arg list
      IFS=',' read -ra DEVICE_LIST <<< "${BS_DEVICE}"
      python3 scripts/ci/browserstack-maestro.py \
        --brand "${BRAND}" \
        --platform "${BS_PLATFORM}" \
        --suite order \
        --skip-upload-app \
        --local \
        --devices "${DEVICE_LIST[@]}" \
        --output "test-results/${BRAND}-${BS_PLATFORM}-order-result.json"
    - echo "BrowserStack order suite completed for ${BRAND} (${BS_PLATFORM})"
    - ls -la test-results/ 2>/dev/null || echo "No test-results/"
  timeout: 45m
  allow_failure: true

# ════════════════════════════════════════════════════════════════════
#  JOB C: Multi-brand matrix (when BRAND=all)
# ════════════════════════════════════════════════════════════════════
browserstack-test-matrix:
  extends: .browserstack_base
  stage: test
  rules:
    - if: '$BRAND == "all"'
  parallel:
    matrix:
      - MATRIX_BRAND: [b3, b1, b2, b4]
  script:
    - echo "Running Shuriken ${TEST_SUITE} for ${MATRIX_BRAND} on ${BS_PLATFORM} — BrowserStack"
    - mkdir -p test-results screenshots
    - |
      case "${TEST_SUITE}" in
        auth)  SUITE_OR_FLOW="--suite auth" ;;
        smoke) SUITE_OR_FLOW="--suite smoke" ;;
        order) SUITE_OR_FLOW="--suite order" ;;
        *)     SUITE_OR_FLOW="--suite ${TEST_SUITE}" ;;
      esac
    - echo "Flow/Suite -- ${SUITE_OR_FLOW}"
    - |
      # Split comma-separated devices into --devices arg list
      IFS=',' read -ra DEVICE_LIST <<< "${BS_DEVICE}"
      python3 scripts/ci/browserstack-maestro.py \
        --brand "${MATRIX_BRAND}" \
        --platform "${BS_PLATFORM}" \
        ${SUITE_OR_FLOW} \
        --skip-upload-app \
        --local \
        --devices "${DEVICE_LIST[@]}" \
        --output test-results/${MATRIX_BRAND}-result.json
    - echo "BrowserStack test completed for ${MATRIX_BRAND} (${BS_PLATFORM})"
  timeout: 30m
  allow_failure: true

# ════════════════════════════════════════════════════════════════════
#  STAGE 2: Publish Report to Confluence
# ════════════════════════════════════════════════════════════════════
publish-confluence-report:
  stage: report
  extends: .browserstack_base
  needs:
    - job: browserstack-test
      optional: true
      artifacts: true
    - job: browserstack-order
      optional: true
      artifacts: true
    - job: browserstack-test-matrix
      optional: true
      artifacts: true
  script:
    - pip install jinja2 --quiet
    - echo "Publishing test report to Confluence..."
    - ls -la test-results/ 2>/dev/null || echo "No test-results/ directory found"
    - |
      python3 scripts/ci/publish-confluence-report.py \
        --results-dir test-results/ \
        --screenshots-dir screenshots/ \
        --space-key "${CONFLUENCE_SPACE_KEY}" \
        --parent-page-id "${CONFLUENCE_PARENT_PAGE_ID}" \
        --base-url "${CONFLUENCE_BASE_URL:-https://your-tenant.atlassian.net/wiki}" \
        --email "${CONFLUENCE_EMAIL}" \
        --api-token "${CONFLUENCE_API_TOKEN}" \
        --build-version "${BUILD_VERSION:-manual}" \
        --pipeline-url "${CI_PIPELINE_URL}" \
        --output test-results/confluence-result.json \
      || echo "Confluence publish failed (non-blocking)"
    - echo "Report published"
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'
      when: on_success
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
      when: on_success
    - if: '$CI_PIPELINE_SOURCE == "trigger"'
      when: on_success
  allow_failure: true

# ════════════════════════════════════════════════════════════════════
#  STAGE 3: Send Notifications (Teams)
# ════════════════════════════════════════════════════════════════════
notify-teams:
  stage: notify
  image: python:3.11-slim
  tags:
    - ci02-perf
  needs:
    - job: publish-confluence-report
      optional: true
      artifacts: true
    - job: browserstack-test
      optional: true
      artifacts: true
    - job: browserstack-order
      optional: true
      artifacts: true
    - job: browserstack-test-matrix
      optional: true
      artifacts: true
  before_script:
    - pip install requests --quiet
  script:
    - echo "Sending Teams notification..."
    - ls -la test-results/ 2>/dev/null || echo "No test-results/ directory found"
    - |
      CONFLUENCE_URL=""
      if [ -f test-results/confluence-result.json ]; then
        echo "Found confluence-result.json:"
        cat test-results/confluence-result.json
        CONFLUENCE_URL=$(python3 -c "import json; print(json.load(open('test-results/confluence-result.json')).get('url',''))" 2>/dev/null || echo "")
      fi
      if [ -z "$CONFLUENCE_URL" ]; then
        CONFLUENCE_URL="N/A"
        echo "No Confluence URL found — using fallback"
      fi
      echo "CONFLUENCE_URL=${CONFLUENCE_URL}"
    - |
      python3 scripts/ci/notify.py \
        --confluence-url "${CONFLUENCE_URL}" \
        --teams-webhook "${TEAMS_WEBHOOK_URL}" \
        --outlook-webhook "${OUTLOOK_WEBHOOK_URL}" \
        --brand "${BRAND:-all}" \
        --build-version "${BUILD_VERSION:-manual}" \
        --pipeline-url "${CI_PIPELINE_URL}" \
        --results-dir test-results/ \
      || echo "Teams notification failed (non-blocking)"
    - echo "Notifications sent"
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'
      when: always
    - if: '$CI_PIPELINE_SOURCE == "schedule"'
      when: always
    - if: '$CI_PIPELINE_SOURCE == "trigger"'
      when: always
  allow_failure: true
'''

output_path = sys.argv[1] if len(sys.argv) > 1 else '.gitlab-ci.yml'
with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
print(f'Written {output_path} ({len(content)} bytes)')
