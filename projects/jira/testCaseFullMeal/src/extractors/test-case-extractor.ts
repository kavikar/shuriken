/**
 * Test Case Extractor
 *
 * Extracts test cases dynamically from Xray Cloud entities:
 *   - Test Set (e.g., TE-10048)
 *   - Test Execution (e.g., TE-XXXXX)
 *   - Test Plan (e.g., TE-XXXXX)
 *   - JQL query (any custom filter)
 *   - Comma-separated keys (ad-hoc list)
 *
 * For each test case, fetches:
 *   - Jira metadata (summary, labels, components, status)
 *   - Xray Cloud data (test type, Gherkin definition)
 *   - Numeric Jira ID (needed for mutations)
 *
 * Usage:
 *   npx ts-node src/extractors/test-case-extractor.ts --test-set TE-10048
 *   npx ts-node src/extractors/test-case-extractor.ts --test-execution TE-XXXXX
 *   npx ts-node src/extractors/test-case-extractor.ts --test-plan TE-XXXXX
 *   npx ts-node src/extractors/test-case-extractor.ts --jql "project = IQE AND labels = WEB"
 *   npx ts-node src/extractors/test-case-extractor.ts --keys TE-10075,TE-10054
 *   npx ts-node src/extractors/test-case-extractor.ts --test-set TE-10048 --output results.json
 */

import fs from 'fs';
import path from 'path';
import {
  getConfig,
  getXrayConfig,
  testConnection,
  getXrayToken,
  xrayGraphQL,
  getIssuesByKeys,
  searchIssues,
  readGherkinDefinition,
  XrayTestIssue,
  XrayConfig,
  JiraConfig,
} from '../client/xray-client';

// ── Types ──────────────────────────────────────────────────────────

export interface ExtractedTestCase {
  key: string;
  numericId: string;
  summary: string;
  labels: string[];
  components: string[];
  status: string;
  testType: string | null;
  hasGherkin: boolean;
  gherkinLineCount: number;
  gherkin: string | null;
}

export interface ExtractionResult {
  source: string;
  sourceKey: string;
  timestamp: string;
  totalExtracted: number;
  tests: ExtractedTestCase[];
}

// ── Xray GraphQL Queries ───────────────────────────────────────────

/**
 * Get all test issue keys from a Test Set via Xray Cloud GraphQL.
 */
async function getTestsFromTestSet(
  xrayConfig: XrayConfig,
  testSetKey: string,
): Promise<string[]> {
  const keys: string[] = [];
  let start = 0;
  const limit = 100;

  while (true) {
    const result = await xrayGraphQL(xrayConfig, `{
      getTestSets(jql: "key = ${testSetKey}", limit: 1) {
        results {
          issueId
          tests(limit: ${limit}, start: ${start}) {
            total
            results {
              issueId
              jira(fields: ["key"])
            }
            start
            limit
          }
        }
      }
    }`);

    const testSet = result.data?.getTestSets?.results?.[0];
    if (!testSet) {
      throw new Error(`Test Set "${testSetKey}" not found in Xray`);
    }

    const tests = testSet.tests;
    for (const t of tests.results || []) {
      const key = t.jira?.key;
      if (key) keys.push(key);
    }

    const fetched = tests.results?.length || 0;
    const total = tests.total || 0;
    start += fetched;
    if (fetched < limit || start >= total) break;
  }

  return keys;
}

/**
 * Get all test issue keys from a Test Execution via Xray Cloud GraphQL.
 */
async function getTestsFromTestExecution(
  xrayConfig: XrayConfig,
  testExecKey: string,
): Promise<string[]> {
  const keys: string[] = [];

  const result = await xrayGraphQL(xrayConfig, `{
    getTestExecutions(jql: "key = ${testExecKey}", limit: 1) {
      results {
        issueId
        testRuns(limit: 100) {
          total
          results {
            test {
              issueId
              jira(fields: ["key"])
            }
          }
        }
      }
    }
  }`);

  const testExec = result.data?.getTestExecutions?.results?.[0];
  if (!testExec) {
    throw new Error(`Test Execution "${testExecKey}" not found in Xray`);
  }

  for (const run of testExec.testRuns?.results || []) {
    const key = run.test?.jira?.key;
    if (key) keys.push(key);
  }

  return keys;
}

/**
 * Get all test issue keys from a Test Plan via Xray Cloud GraphQL.
 */
async function getTestsFromTestPlan(
  xrayConfig: XrayConfig,
  testPlanKey: string,
): Promise<string[]> {
  const keys: string[] = [];

  const result = await xrayGraphQL(xrayConfig, `{
    getTestPlans(jql: "key = ${testPlanKey}", limit: 1) {
      results {
        issueId
        tests(limit: 100) {
          total
          results {
            issueId
            jira(fields: ["key"])
          }
        }
      }
    }
  }`);

  const testPlan = result.data?.getTestPlans?.results?.[0];
  if (!testPlan) {
    throw new Error(`Test Plan "${testPlanKey}" not found in Xray`);
  }

  for (const t of testPlan.tests?.results || []) {
    const key = t.jira?.key;
    if (key) keys.push(key);
  }

  return keys;
}

// ── Enrichment ─────────────────────────────────────────────────────

/**
 * Enrich Jira issues with Xray Gherkin data.
 */
async function enrichWithXray(
  xrayConfig: XrayConfig,
  issues: XrayTestIssue[],
): Promise<ExtractedTestCase[]> {
  const results: ExtractedTestCase[] = [];
  const BATCH_SIZE = 5;

  for (let i = 0; i < issues.length; i += BATCH_SIZE) {
    const batch = issues.slice(i, i + BATCH_SIZE);
    const promises = batch.map(async (issue) => {
      try {
        const xrayData = await readGherkinDefinition(xrayConfig, issue.key);
        return {
          key: issue.key,
          numericId: issue.numericId || '',
          summary: issue.summary,
          labels: issue.labels,
          components: issue.components,
          status: issue.status,
          testType: xrayData?.testType || null,
          hasGherkin: !!xrayData?.gherkin,
          gherkinLineCount: xrayData?.gherkin?.split('\n').length || 0,
          gherkin: xrayData?.gherkin || null,
        } as ExtractedTestCase;
      } catch {
        return {
          key: issue.key,
          numericId: issue.numericId || '',
          summary: issue.summary,
          labels: issue.labels,
          components: issue.components,
          status: issue.status,
          testType: null,
          hasGherkin: false,
          gherkinLineCount: 0,
          gherkin: null,
        } as ExtractedTestCase;
      }
    });

    results.push(...await Promise.all(promises));
    const done = Math.min(i + BATCH_SIZE, issues.length);
    process.stdout.write(`\r  Enriching with Xray data... ${done}/${issues.length}`);

    // Rate limit
    if (i + BATCH_SIZE < issues.length) {
      await new Promise((r) => setTimeout(r, 800));
    }
  }
  console.log('');
  return results;
}

// ── CLI ────────────────────────────────────────────────────────────

interface CLIArgs {
  testSet?: string;
  testExecution?: string;
  testPlan?: string;
  jql?: string;
  keys?: string[];
  output?: string;
  noXray?: boolean;
}

function parseArgs(): CLIArgs {
  const args = process.argv.slice(2);
  const result: CLIArgs = {};

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--test-set':
        result.testSet = args[++i];
        break;
      case '--test-execution':
        result.testExecution = args[++i];
        break;
      case '--test-plan':
        result.testPlan = args[++i];
        break;
      case '--jql':
        result.jql = args[++i];
        break;
      case '--keys':
        result.keys = args[++i].split(',').map((k) => k.trim());
        break;
      case '--output':
        result.output = args[++i];
        break;
      case '--no-xray':
        result.noXray = true;
        break;
    }
  }

  return result;
}

// ── Main ───────────────────────────────────────────────────────────

async function main() {
  const cliArgs = parseArgs();

  console.log('╔══════════════════════════════════════════════════════╗');
  console.log('║  Test Case Extractor                                ║');
  console.log('╚══════════════════════════════════════════════════════╝\n');

  // Validate that at least one source is provided
  if (!cliArgs.testSet && !cliArgs.testExecution && !cliArgs.testPlan && !cliArgs.jql && !cliArgs.keys) {
    console.error('❌ Please provide one of:');
    console.error('   --test-set TE-10048');
    console.error('   --test-execution TE-XXXXX');
    console.error('   --test-plan TE-XXXXX');
    console.error('   --jql "project = IQE AND labels = WEB"');
    console.error('   --keys TE-10075,TE-10054');
    process.exit(1);
  }

  // Connect
  const jiraConfig = getConfig();
  const xrayConfig = getXrayConfig();
  if (!jiraConfig || !xrayConfig) {
    console.error('❌ Missing credentials. Either create a local .env or ensure ~/Documents/jira-automation/.env exists.');
    process.exit(1);
  }

  console.log('🔌 Connecting...');
  const ok = await testConnection(jiraConfig);
  if (!ok) {
    console.error('❌ Cannot connect to Jira.');
    process.exit(1);
  }
  await getXrayToken(xrayConfig);
  console.log('  ✅ Jira + Xray authenticated\n');

  // ── Step 1: Resolve test case keys ──
  let testKeys: string[] = [];
  let sourceName = '';
  let sourceKey = '';

  if (cliArgs.testSet) {
    sourceName = 'Test Set';
    sourceKey = cliArgs.testSet;
    console.log(`📦 Extracting from Test Set: ${sourceKey}`);
    testKeys = await getTestsFromTestSet(xrayConfig, sourceKey);
  } else if (cliArgs.testExecution) {
    sourceName = 'Test Execution';
    sourceKey = cliArgs.testExecution;
    console.log(`🏃 Extracting from Test Execution: ${sourceKey}`);
    testKeys = await getTestsFromTestExecution(xrayConfig, sourceKey);
  } else if (cliArgs.testPlan) {
    sourceName = 'Test Plan';
    sourceKey = cliArgs.testPlan;
    console.log(`📋 Extracting from Test Plan: ${sourceKey}`);
    testKeys = await getTestsFromTestPlan(xrayConfig, sourceKey);
  } else if (cliArgs.jql) {
    sourceName = 'JQL';
    sourceKey = cliArgs.jql;
    console.log(`🔍 Extracting via JQL: ${sourceKey}`);
    const result = await searchIssues(jiraConfig, cliArgs.jql, 500);
    testKeys = result.issues.map((i) => i.key);
  } else if (cliArgs.keys) {
    sourceName = 'Ad-hoc Keys';
    sourceKey = cliArgs.keys.join(',');
    testKeys = cliArgs.keys;
    console.log(`🎯 Extracting specific keys: ${testKeys.join(', ')}`);
  }

  // Deduplicate
  testKeys = [...new Set(testKeys)];
  console.log(`  Found ${testKeys.length} test case(s)\n`);

  if (testKeys.length === 0) {
    console.log('⚠️  No test cases found. Check your input.');
    process.exit(0);
  }

  // ── Step 2: Fetch Jira metadata ──
  console.log('📥 Fetching Jira metadata...');
  const issues = await getIssuesByKeys(jiraConfig, testKeys);
  console.log(`  Got ${issues.length} issues from Jira\n`);

  // ── Step 3: Enrich with Xray data (Gherkin, test type) ──
  let extracted: ExtractedTestCase[];
  if (cliArgs.noXray) {
    console.log('⏭️  Skipping Xray enrichment (--no-xray)\n');
    extracted = issues.map((i) => ({
      key: i.key,
      numericId: i.numericId || '',
      summary: i.summary,
      labels: i.labels,
      components: i.components,
      status: i.status,
      testType: null,
      hasGherkin: false,
      gherkinLineCount: 0,
      gherkin: null,
    }));
  } else {
    console.log('📡 Enriching with Xray Cloud data...');
    extracted = await enrichWithXray(xrayConfig, issues);
  }

  // ── Step 4: Build result ──
  const result: ExtractionResult = {
    source: sourceName,
    sourceKey,
    timestamp: new Date().toISOString(),
    totalExtracted: extracted.length,
    tests: extracted,
  };

  // ── Step 5: Output ──
  // Console summary
  console.log('\n' + '═'.repeat(70));
  console.log(`  Source:       ${sourceName} → ${sourceKey}`);
  console.log(`  Total Tests:  ${extracted.length}`);
  console.log(`  With Gherkin: ${extracted.filter((t) => t.hasGherkin).length}`);
  console.log(`  Cucumber:     ${extracted.filter((t) => t.testType === 'Cucumber').length}`);
  console.log('═'.repeat(70));

  // Print table
  console.log('\n  Key            | Type       | Gherkin | Summary');
  console.log('  ' + '─'.repeat(66));
  for (const t of extracted) {
    const type = (t.testType || 'N/A').padEnd(10);
    const gherkin = t.hasGherkin ? `✅ ${String(t.gherkinLineCount).padStart(3)} ln` : '❌  none';
    console.log(`  ${t.key.padEnd(15)}| ${type} | ${gherkin} | ${t.summary.substring(0, 40)}...`);
  }

  // Save to file
  const outputPath = cliArgs.output
    ? path.resolve(cliArgs.output)
    : path.resolve(__dirname, '..', '..', 'reports', `extraction-${sourceKey.replace(/[^a-zA-Z0-9-]/g, '_')}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`);

  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
  console.log(`\n📄 Full extraction saved: ${outputPath}`);

  // Output just the keys for piping
  console.log(`\n🔑 Keys (for piping to other scripts):`);
  console.log(`   ${extracted.map((t) => t.key).join(',')}`);
}

// ── Programmatic API (for use by other scripts) ────────────────────

export async function extractFromTestSet(testSetKey: string): Promise<ExtractionResult> {
  const jiraConfig = getConfig()!;
  const xrayConfig = getXrayConfig()!;
  await getXrayToken(xrayConfig);

  const testKeys = await getTestsFromTestSet(xrayConfig, testSetKey);
  const issues = await getIssuesByKeys(jiraConfig, testKeys);
  const extracted = await enrichWithXray(xrayConfig, issues);

  return {
    source: 'Test Set',
    sourceKey: testSetKey,
    timestamp: new Date().toISOString(),
    totalExtracted: extracted.length,
    tests: extracted,
  };
}

export async function extractFromTestExecution(testExecKey: string): Promise<ExtractionResult> {
  const jiraConfig = getConfig()!;
  const xrayConfig = getXrayConfig()!;
  await getXrayToken(xrayConfig);

  const testKeys = await getTestsFromTestExecution(xrayConfig, testExecKey);
  const issues = await getIssuesByKeys(jiraConfig, testKeys);
  const extracted = await enrichWithXray(xrayConfig, issues);

  return {
    source: 'Test Execution',
    sourceKey: testExecKey,
    timestamp: new Date().toISOString(),
    totalExtracted: extracted.length,
    tests: extracted,
  };
}

export async function extractFromTestPlan(testPlanKey: string): Promise<ExtractionResult> {
  const jiraConfig = getConfig()!;
  const xrayConfig = getXrayConfig()!;
  await getXrayToken(xrayConfig);

  const testKeys = await getTestsFromTestPlan(xrayConfig, testPlanKey);
  const issues = await getIssuesByKeys(jiraConfig, testKeys);
  const extracted = await enrichWithXray(xrayConfig, issues);

  return {
    source: 'Test Plan',
    sourceKey: testPlanKey,
    timestamp: new Date().toISOString(),
    totalExtracted: extracted.length,
    tests: extracted,
  };
}

export async function extractByJQL(jql: string): Promise<ExtractionResult> {
  const jiraConfig = getConfig()!;
  const xrayConfig = getXrayConfig()!;
  await getXrayToken(xrayConfig);

  const searchResult = await searchIssues(jiraConfig, jql, 500);
  const extracted = await enrichWithXray(xrayConfig, searchResult.issues);

  return {
    source: 'JQL',
    sourceKey: jql,
    timestamp: new Date().toISOString(),
    totalExtracted: extracted.length,
    tests: extracted,
  };
}

export async function extractByKeys(keys: string[]): Promise<ExtractionResult> {
  const jiraConfig = getConfig()!;
  const xrayConfig = getXrayConfig()!;
  await getXrayToken(xrayConfig);

  const issues = await getIssuesByKeys(jiraConfig, keys);
  const extracted = await enrichWithXray(xrayConfig, issues);

  return {
    source: 'Ad-hoc Keys',
    sourceKey: keys.join(','),
    timestamp: new Date().toISOString(),
    totalExtracted: extracted.length,
    tests: extracted,
  };
}

// Run if invoked directly
main().catch(console.error);
