/**
 * Bulk Update — Push Gherkin BDD steps to all IQE Xray Test cases
 *
 * Uses the Xray Cloud GraphQL API (updateGherkinTestDefinition mutation)
 * to push generated Gherkin scenarios to each test's Cucumber definition.
 *
 * Features:
 *   - Batch processing with rate limiting (10 per batch, 1s delay)
 *   - Dry-run mode (--dry-run) to preview without making changes
 *   - Area-specific filter (--area "Combo Builder")
 *   - Progress reporting with success/fail counts
 *   - JSON report saved to reports/
 *
 * Usage:
 *   npm run dry-run                         # Preview all changes
 *   npm run bulk-update                     # Execute all updates
 *   npm run bulk-update -- --area "Combo Builder"  # Only one area
 *   npm run bulk-update -- --keys TE-10006,TE-10005  # Specific keys
 */

import * as fs from 'fs';
import * as path from 'path';
import {
  getConfig,
  getXrayConfig,
  testConnection,
  getIssuesByKeys,
  getXrayToken,
  updateGherkinDefinition,
  setTestTypeCucumber,
  XrayTestIssue,
  XrayConfig,
} from '../client/xray-client';
import { generateGherkin, getCategory } from '../generators/app-gherkin-generator';
import { FUNCTIONAL_AREAS, getAllKeys, getAreaForKey } from '../registry/app-test-cases';

// ── Types ──────────────────────────────────────────────────────────

interface UpdateResult {
  key: string;
  summary: string;
  category: string;
  area: string;
  numericId?: string;
  status: 'success' | 'failed' | 'skipped';
  error?: string;
  gherkinPreview?: string;
}

interface BulkReport {
  timestamp: string;
  mode: 'dry-run' | 'live';
  total: number;
  success: number;
  failed: number;
  skipped: number;
  results: UpdateResult[];
}

// ── CLI Args ───────────────────────────────────────────────────────

function parseArgs(): { dryRun: boolean; area: string | null; keys: string[] | null } {
  const args = process.argv.slice(2);
  const dryRun = args.includes('--dry-run');
  let area: string | null = null;
  let keys: string[] | null = null;

  const areaIdx = args.indexOf('--area');
  if (areaIdx !== -1 && args[areaIdx + 1]) {
    area = args[areaIdx + 1];
  }

  const keysIdx = args.indexOf('--keys');
  if (keysIdx !== -1 && args[keysIdx + 1]) {
    keys = args[keysIdx + 1].split(',').map((k) => k.trim());
  }

  return { dryRun, area, keys };
}

// ── Helpers ────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function saveReport(report: BulkReport): string {
  const dir = path.resolve(__dirname, '..', 'reports');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const filename = `bulk-update-${report.mode}-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  const filePath = path.join(dir, filename);
  fs.writeFileSync(filePath, JSON.stringify(report, null, 2));
  return filePath;
}

// ── Main ───────────────────────────────────────────────────────────

async function main() {
  const { dryRun, area, keys } = parseArgs();
  const mode = dryRun ? 'dry-run' : 'live';

  console.log('╔══════════════════════════════════════════════════════╗');
  console.log(`║  Bulk Xray Gherkin Update — ${mode.toUpperCase().padEnd(22)}║`);
  console.log('╚══════════════════════════════════════════════════════╝\n');

  if (dryRun) {
    console.log('🔍 DRY RUN MODE — No changes will be made.\n');
  }

  // 1. Validate configs
  const config = getConfig();
  if (!config) {
    console.error('❌ Missing Jira env vars (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN).');
    process.exit(1);
  }

  const xrayConfig = getXrayConfig();
  if (!xrayConfig) {
    console.error('❌ Missing Xray env vars (XRAY_CLIENT_ID, XRAY_CLIENT_SECRET).');
    process.exit(1);
  }

  // 2. Test connections
  console.log('🔌 Testing Jira connection...');
  const ok = await testConnection(config);
  if (!ok) {
    console.error('❌ Cannot connect to Jira.');
    process.exit(1);
  }
  console.log('  ✅ Jira connected');

  console.log('🔑 Testing Xray Cloud auth...');
  await getXrayToken(xrayConfig);
  console.log('  ✅ Xray Cloud authenticated\n');

  // 3. Determine which keys to process
  let targetKeys: string[];
  if (keys) {
    targetKeys = keys;
    console.log(`🎯 Processing specific keys: ${keys.join(', ')}\n`);
  } else if (area) {
    const matchedArea = FUNCTIONAL_AREAS.find((a) =>
      a.name.toLowerCase() === area.toLowerCase());
    if (!matchedArea) {
      console.error(`❌ Unknown area: "${area}". Available areas:`);
      FUNCTIONAL_AREAS.forEach((a) => console.log(`  - ${a.name} (${a.keys.length} tests)`));
      process.exit(1);
    }
    targetKeys = matchedArea.keys;
    console.log(`🎯 Processing area: ${matchedArea.name} (${targetKeys.length} tests)\n`);
  } else {
    targetKeys = getAllKeys();
    console.log(`📋 Processing ALL ${targetKeys.length} test cases across ${FUNCTIONAL_AREAS.length} areas\n`);
  }

  // 4. Fetch all issues from Jira (to get summaries + numeric IDs)
  console.log('📥 Fetching issues from Jira...');
  const issues = await getIssuesByKeys(config, targetKeys);
  console.log(`   Fetched ${issues.length} / ${targetKeys.length} issues`);

  // Map by key for lookup
  const issueMap = new Map<string, XrayTestIssue>();
  for (const issue of issues) {
    issueMap.set(issue.key, issue);
  }

  // Verify we have numeric IDs
  const withIds = issues.filter((i) => i.numericId);
  console.log(`   ${withIds.length} issues have numeric IDs for Xray\n`);

  // 5. Process in batches
  const BATCH_SIZE = 10;
  const BATCH_DELAY = 1500; // 1.5s between batches (Xray rate limits)
  const results: UpdateResult[] = [];
  let successCount = 0;
  let failCount = 0;
  let skipCount = 0;

  for (let i = 0; i < targetKeys.length; i += BATCH_SIZE) {
    const batch = targetKeys.slice(i, i + BATCH_SIZE);
    const batchNum = Math.floor(i / BATCH_SIZE) + 1;
    const totalBatches = Math.ceil(targetKeys.length / BATCH_SIZE);
    console.log(`\n── Batch ${batchNum}/${totalBatches} ──`);

    for (const key of batch) {
      const issue = issueMap.get(key);

      if (!issue) {
        console.log(`  ⚠️  ${key} — Not found in Jira (skipped)`);
        results.push({ key, summary: '(not found)', category: 'unknown', area: getAreaForKey(key) || 'Unknown', status: 'skipped' });
        skipCount++;
        continue;
      }

      if (!issue.numericId) {
        console.log(`  ⚠️  ${key} — No numeric ID (skipped)`);
        results.push({ key, summary: issue.summary, category: 'unknown', area: getAreaForKey(key) || 'Unknown', status: 'skipped', error: 'No numeric Jira ID' });
        skipCount++;
        continue;
      }

      const category = getCategory(issue.summary);
      const areaName = getAreaForKey(key) || 'Unknown';
      const gherkin = generateGherkin(issue);

      if (dryRun) {
        console.log(`  📝 ${key} (id: ${issue.numericId}) — ${issue.summary.substring(0, 50)}...`);
        console.log(`     Category: ${category} | Area: ${areaName}`);
        console.log(`     Gherkin (${gherkin.split('\n').length} lines):`);
        gherkin.split('\n').forEach((l) => console.log(`       ${l}`));
        results.push({
          key, summary: issue.summary, category, area: areaName,
          numericId: issue.numericId, status: 'success',
          gherkinPreview: gherkin.split('\n')[0],
        });
        successCount++;
      } else {
        try {
          await updateGherkinDefinition(xrayConfig, issue.numericId, gherkin);
          console.log(`  ✅ ${key} — ${category} — updated`);
          results.push({
            key, summary: issue.summary, category, area: areaName,
            numericId: issue.numericId, status: 'success',
            gherkinPreview: gherkin.split('\n')[0],
          });
          successCount++;
        } catch (err: any) {
          console.log(`  ❌ ${key} — FAILED: ${err.message.substring(0, 80)}`);
          results.push({
            key, summary: issue.summary, category, area: areaName,
            numericId: issue.numericId, status: 'failed', error: err.message,
          });
          failCount++;
        }
      }
    }

    // Rate limit between batches
    if (i + BATCH_SIZE < targetKeys.length) {
      await sleep(BATCH_DELAY);
    }
  }

  // 6. Summary
  const report: BulkReport = {
    timestamp: new Date().toISOString(),
    mode,
    total: targetKeys.length,
    success: successCount,
    failed: failCount,
    skipped: skipCount,
    results,
  };

  console.log('\n══════════════════════════════════════════════════════');
  console.log(`  Mode:     ${mode.toUpperCase()}`);
  console.log(`  Total:    ${targetKeys.length}`);
  console.log(`  Success:  ${successCount}`);
  console.log(`  Failed:   ${failCount}`);
  console.log(`  Skipped:  ${skipCount}`);
  console.log('══════════════════════════════════════════════════════');

  // Save report
  const reportPath = saveReport(report);
  console.log(`\n📄 Report saved: ${reportPath}`);

  if (failCount > 0) {
    console.log('\n⚠️  Some updates failed. Check the report for details.');
    console.log('   Failed keys:');
    results.filter((r) => r.status === 'failed').forEach((r) => {
      console.log(`     ${r.key}: ${r.error?.substring(0, 60)}`);
    });
  }

  if (dryRun) {
    console.log('\n💡 This was a dry run. To execute for real, run: npm run bulk-update');
  } else {
    console.log('\n✅ Bulk update complete!');
  }
}

main().catch(console.error);
