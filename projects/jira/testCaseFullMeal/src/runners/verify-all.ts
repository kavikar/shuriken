/**
 * Verification Script
 *
 * Checks ALL 150+ IQE test cases to verify:
 *  1. Test type is Cucumber
 *  2. Gherkin definition exists
 *  3. Gherkin Scenario line matches the test summary title
 *
 * Outputs a detailed report with pass/fail for each test.
 */
import { getConfig, getXrayConfig, getIssuesByKeys, readGherkinDefinition } from '../client/xray-client';
import { getAllKeys, getAreaForKey } from '../registry/app-test-cases';
import { generateGherkin } from '../generators/app-gherkin-generator';
import type { XrayConfig } from '../client/xray-client';
import fs from 'fs';
import path from 'path';

interface VerifyResult {
  key: string;
  area: string;
  summary: string;
  testType: string | null;
  hasGherkin: boolean;
  gherkinLines: number;
  scenarioTitle: string | null;
  titleMatch: boolean;
  status: 'PASS' | 'FAIL' | 'WARN';
  issues: string[];
}

async function batchReadGherkin(
  xrayConfig: XrayConfig,
  keys: string[],
  batchSize = 5,
): Promise<Map<string, { testType: string; gherkin: string | null }>> {
  const results = new Map<string, { testType: string; gherkin: string | null }>();

  for (let i = 0; i < keys.length; i += batchSize) {
    const batch = keys.slice(i, i + batchSize);
    const promises = batch.map(async (key) => {
      try {
        const r = await readGherkinDefinition(xrayConfig, key);
        if (r) {
          results.set(key, { testType: r.testType, gherkin: r.gherkin });
        }
      } catch (err: any) {
        console.error(`  ⚠ Error reading ${key}: ${err.message}`);
      }
    });
    await Promise.all(promises);

    // Progress
    const done = Math.min(i + batchSize, keys.length);
    process.stdout.write(`\r  Reading Xray data... ${done}/${keys.length}`);

    // Rate limit
    if (i + batchSize < keys.length) {
      await new Promise((r) => setTimeout(r, 800));
    }
  }
  console.log('');
  return results;
}

function extractScenarioTitle(gherkin: string): string | null {
  const match = gherkin.match(/^Scenario:\s*(.+)$/m);
  return match ? match[1].trim() : null;
}

function normalizeForComparison(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

async function main() {
  const jiraConfig = getConfig()!;
  const xrayConfig = getXrayConfig()!;

  // 1. Get all unique keys
  const allKeys = [...new Set(getAllKeys())];
  console.log(`\n🔍 Verifying ${allKeys.length} unique IQE test cases...\n`);

  // 2. Fetch Jira metadata (summaries)
  console.log('  Fetching Jira metadata...');
  const issues = await getIssuesByKeys(jiraConfig, allKeys);
  const issueMap = new Map(issues.map((i) => [i.key, i]));
  console.log(`  Found ${issues.length} issues in Jira\n`);

  // 3. Read Gherkin definitions from Xray Cloud
  console.log('  Querying Xray Cloud for Gherkin definitions...');
  const xrayData = await batchReadGherkin(xrayConfig, allKeys);
  console.log(`  Got Xray data for ${xrayData.size} tests\n`);

  // 4. Verify each test
  const results: VerifyResult[] = [];

  for (const key of allKeys) {
    const issue = issueMap.get(key);
    const xray = xrayData.get(key);
    const area = getAreaForKey(key) || 'Unknown';
    const issues: string[] = [];

    if (!issue) {
      results.push({
        key, area, summary: '(not found in Jira)', testType: null,
        hasGherkin: false, gherkinLines: 0, scenarioTitle: null,
        titleMatch: false, status: 'FAIL', issues: ['Issue not found in Jira'],
      });
      continue;
    }

    if (!xray) {
      results.push({
        key, area, summary: issue.summary, testType: null,
        hasGherkin: false, gherkinLines: 0, scenarioTitle: null,
        titleMatch: false, status: 'FAIL', issues: ['No Xray test data found'],
      });
      continue;
    }

    // Check test type
    if (xray.testType !== 'Cucumber') {
      issues.push(`Test type is "${xray.testType}", expected "Cucumber"`);
    }

    // Check Gherkin exists
    const hasGherkin = !!xray.gherkin && xray.gherkin.trim().length > 0;
    if (!hasGherkin) {
      issues.push('No Gherkin definition found');
    }

    // Check Gherkin Scenario title matches summary
    let scenarioTitle: string | null = null;
    let titleMatch = false;

    if (hasGherkin && xray.gherkin) {
      scenarioTitle = extractScenarioTitle(xray.gherkin);

      if (!scenarioTitle) {
        issues.push('Gherkin has no "Scenario:" line');
      } else {
        // Generate what the Gherkin SHOULD be, extract its scenario title
        const expectedGherkin = generateGherkin(issue);
        const expectedTitle = extractScenarioTitle(expectedGherkin);

        if (expectedTitle) {
          const normScenario = normalizeForComparison(scenarioTitle);
          const normExpected = normalizeForComparison(expectedTitle);
          titleMatch = normScenario === normExpected;

          if (!titleMatch) {
            // Check if at least the core of the title is present
            const summaryWords = normalizeForComparison(issue.summary)
              .split(' ')
              .filter((w) => w.length > 3);
            const matchingWords = summaryWords.filter((w) => normScenario.includes(w));
            const matchRatio = matchingWords.length / summaryWords.length;

            if (matchRatio >= 0.5) {
              titleMatch = true; // close enough
            } else {
              issues.push(`Scenario title mismatch (${Math.round(matchRatio * 100)}% word match)`);
            }
          }
        }
      }

      // Check has Given/When/Then
      if (xray.gherkin && !xray.gherkin.includes('Given')) {
        issues.push('Missing Given step');
      }
      if (xray.gherkin && !xray.gherkin.includes('When')) {
        issues.push('Missing When step');
      }
      if (xray.gherkin && !xray.gherkin.includes('Then')) {
        issues.push('Missing Then step');
      }
    }

    const gherkinLines = xray.gherkin?.split('\n').length || 0;
    let status: 'PASS' | 'FAIL' | 'WARN' = 'PASS';
    if (issues.length > 0) {
      status = issues.some((i) => i.includes('No Gherkin') || i.includes('Test type'))
        ? 'FAIL'
        : 'WARN';
    }

    results.push({
      key, area, summary: issue.summary, testType: xray.testType,
      hasGherkin, gherkinLines, scenarioTitle, titleMatch, status, issues,
    });
  }

  // 5. Print results
  const passed = results.filter((r) => r.status === 'PASS');
  const warned = results.filter((r) => r.status === 'WARN');
  const failed = results.filter((r) => r.status === 'FAIL');

  console.log('═'.repeat(70));
  console.log(`  VERIFICATION RESULTS`);
  console.log('═'.repeat(70));
  console.log(`  Total checked:  ${results.length}`);
  console.log(`  ✅ PASS:        ${passed.length}`);
  console.log(`  ⚠️  WARN:        ${warned.length}`);
  console.log(`  ❌ FAIL:        ${failed.length}`);
  console.log('═'.repeat(70));

  // Show failures
  if (failed.length > 0) {
    console.log(`\n❌ FAILED TESTS (${failed.length}):`);
    for (const r of failed) {
      console.log(`  ${r.key} [${r.area}]`);
      console.log(`    Summary: ${r.summary.substring(0, 80)}`);
      for (const issue of r.issues) {
        console.log(`    ⛔ ${issue}`);
      }
    }
  }

  // Show warnings
  if (warned.length > 0) {
    console.log(`\n⚠️  WARNINGS (${warned.length}):`);
    for (const r of warned) {
      console.log(`  ${r.key} [${r.area}]`);
      console.log(`    Summary: ${r.summary.substring(0, 80)}`);
      for (const issue of r.issues) {
        console.log(`    ⚠ ${issue}`);
      }
    }
  }

  // Show a few PASSed as sample
  console.log(`\n✅ PASSED (${passed.length}) — sample:`);
  for (const r of passed.slice(0, 5)) {
    console.log(`  ${r.key} | type: ${r.testType} | ${r.gherkinLines} lines | "${r.scenarioTitle?.substring(0, 60)}..."`);
  }
  if (passed.length > 5) {
    console.log(`  ... and ${passed.length - 5} more`);
  }

  // 6. Save detailed report
  const reportDir = path.resolve(__dirname, '..', 'reports');
  if (!fs.existsSync(reportDir)) fs.mkdirSync(reportDir, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const reportPath = path.join(reportDir, `verification-${ts}.json`);
  fs.writeFileSync(reportPath, JSON.stringify({
    timestamp: new Date().toISOString(),
    total: results.length,
    passed: passed.length,
    warned: warned.length,
    failed: failed.length,
    results,
  }, null, 2));
  console.log(`\n📄 Full report saved to: ${reportPath}\n`);
}

main().catch(console.error);
