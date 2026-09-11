#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i];
    const next = argv[i + 1];
    if (key.startsWith("--")) {
      args[key.slice(2)] = next && !next.startsWith("--") ? next : "true";
      if (next && !next.startsWith("--")) i++;
    }
  }
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function writeText(filePath, text) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, text, "utf8");
}

function buildTestPrompt(test, context) {
  const checkpointLines = (test.checkpoints || [])
    .map((cp, idx) => `${idx + 1}. ${cp}`)
    .join("\n");

  return [
    `TEST KEY: ${test.key}`,
    `TITLE: ${test.title}`,
    `OBJECTIVE: ${test.objective}`,
    "",
    "Context:",
    `- Brand: ${context.brand}`,
    `- Environment: ${context.env}`,
    `- Platform: ${context.platform}`,
    `- Bundle ID: ${context.bundleId}`,
    `- API Endpoint: ${context.apiEndpoint || "n/a"}`,
    "",
    "Execution Policy:",
    "1. Create session using CAPABILITIES_CONFIG.",
    "2. Capture screenshot at launch checkpoint.",
    "3. Perform test objective actions.",
    "4. Capture screenshot at final checkpoint.",
    "5. If a blocker appears, capture evidence and continue to next test.",
    "",
    "Checkpoints:",
    checkpointLines || "1. No checkpoints defined",
    "",
    "Output format:",
    "SUMMARY: PASS | FAIL | BLOCKED",
    "EVIDENCE: screenshot file paths",
    "RESULT: what was validated",
    "ISSUE: blocker/failure details"
  ].join("\n");
}

function main() {
  const args = parseArgs(process.argv);
  const planPath = path.resolve(args.plan || "plans/brand3.smoke.json");
  const profilePath = path.resolve(args.profile || "artifacts/runtime/brand3.uat.profile.json");
  const outRoot = path.resolve(args.out || "artifacts/runtime/suites");

  if (!fs.existsSync(planPath)) {
    throw new Error(`Plan not found: ${planPath}`);
  }
  if (!fs.existsSync(profilePath)) {
    throw new Error(`Profile not found: ${profilePath}`);
  }

  const plan = readJson(planPath);
  const profile = readJson(profilePath);
  const tests = Array.isArray(plan.tests) ? plan.tests : [];

  const bundleId =
    plan.platform === "ios"
      ? profile.app.iosBundleId
      : profile.app.androidBundleId;

  const suiteDir = path.join(outRoot, `${plan.brand}.${plan.env}.${plan.platform}.${plan.suite}`);
  ensureDir(suiteDir);

  const context = {
    brand: plan.brand,
    env: plan.env,
    platform: plan.platform,
    bundleId,
    apiEndpoint: profile.endpoints && profile.endpoints.apiEndpoint
  };

  const perTestFiles = [];
  tests.forEach((test, index) => {
    const fileName = `${String(index + 1).padStart(2, "0")}-${test.key}.prompt.txt`;
    const filePath = path.join(suiteDir, fileName);
    writeText(filePath, buildTestPrompt(test, context));
    perTestFiles.push(filePath);
  });

  const consolidated = [
    `SUITE: ${plan.suite}`,
    `BRAND: ${plan.brand}`,
    `ENV: ${plan.env}`,
    `PLATFORM: ${plan.platform}`,
    `BUNDLE_ID: ${bundleId}`,
    "",
    "Execution order:",
    ...tests.map((t, i) => `${i + 1}. ${t.key} | ${t.title}`),
    "",
    "Per-test prompt files:",
    ...perTestFiles.map(p => `- ${p}`)
  ].join("\n");

  const consolidatedPath = path.join(suiteDir, "combined-suite-prompt.txt");
  writeText(consolidatedPath, consolidated);

  const summaryPath = path.join(suiteDir, "suite-manifest.json");
  const summary = {
    generatedAt: new Date().toISOString(),
    planPath,
    profilePath,
    suiteDir,
    consolidatedPath,
    tests: tests.map((t, i) => ({
      index: i + 1,
      key: t.key,
      title: t.title,
      promptFile: perTestFiles[i]
    }))
  };
  fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2), "utf8");

  process.stdout.write(`${summaryPath}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`generate-suite-artifacts failed: ${error.message}\n`);
  process.exit(1);
}
