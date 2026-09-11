/**
 * Test Executioner — Execution Report
 *
 * Generate a summary report of a Test Execution's current status.
 * Shows pass/fail breakdown, identifies TODO tests, and optionally
 * exports as CSV or JSON.
 *
 * Usage:
 *   npx ts-node src/runners/execution-report.ts --te TE-10082
 *   npx ts-node src/runners/execution-report.ts --te TE-10082 --export csv
 *   npx ts-node src/runners/execution-report.ts --te TE-10082 --export json
 */

import * as fs from 'fs';
import * as path from 'path';
import {
  getXrayConfig,
  xrayGraphQL,
  type XrayConfig,
} from '../../../shared/xray-client';

interface RunInfo {
  runId: string;
  testKey: string;
  summary: string;
  status: string;
}

async function getAllTestRuns(
  xrayConfig: XrayConfig,
  teKey: string,
): Promise<RunInfo[]> {
  const runs: RunInfo[] = [];
  let start = 0;

  while (true) {
    const result = await xrayGraphQL(xrayConfig, `{
      getTestExecutions(jql: "key = ${teKey}", limit: 1) {
        results {
          testRuns(limit: 100, start: ${start}) {
            total
            results {
              id
              status { name }
              test {
                jira(fields: ["key", "summary"])
              }
            }
          }
        }
      }
    }`);

    const te = result.data?.getTestExecutions?.results?.[0];
    if (!te) throw new Error(`TE ${teKey} not found`);

    const page = te.testRuns?.results || [];
    for (const run of page) {
      runs.push({
        runId: run.id,
        testKey: run.test?.jira?.key || '???',
        summary: run.test?.jira?.summary || '',
        status: run.status?.name || 'TODO',
      });
    }

    const total = te.testRuns?.total || 0;
    start += page.length;
    if (start >= total || page.length === 0) break;
  }

  return runs;
}

async function main() {
  const args = process.argv.slice(2);
  let teKey = '';
  let exportFormat = '';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--te') teKey = args[++i];
    if (args[i] === '--export') exportFormat = args[++i];
  }

  if (!teKey) throw new Error('Missing --te <key>');

  const xrayConfig = getXrayConfig();
  if (!xrayConfig) throw new Error('Missing Xray credentials');

  console.log(`\n  📊 TEST EXECUTIONER — Execution Report`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  TE: ${teKey}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  const runs = await getAllTestRuns(xrayConfig, teKey);

  // Status breakdown
  const statusCounts: Record<string, number> = {};
  for (const r of runs) {
    statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
  }

  console.log(`  Total Test Runs: ${runs.length}\n`);
  for (const [status, count] of Object.entries(statusCounts).sort()) {
    const pct = ((count / runs.length) * 100).toFixed(1);
    const icon = status === 'PASSED' ? '✅' : status === 'FAILED' ? '❌' : status === 'BLOCKED' ? '🚫' : '⬜';
    const bar = '█'.repeat(Math.round((count / runs.length) * 30));
    console.log(`  ${icon} ${status.padEnd(10)} ${String(count).padStart(3)} (${pct.padStart(5)}%)  ${bar}`);
  }

  // Completion rate
  const completed = runs.filter(r => r.status === 'PASSED' || r.status === 'FAILED').length;
  const completionPct = ((completed / runs.length) * 100).toFixed(1);
  console.log(`\n  📈 Completion: ${completed}/${runs.length} (${completionPct}%)`);

  // Pass rate (of completed)
  const passed = runs.filter(r => r.status === 'PASSED').length;
  if (completed > 0) {
    const passRate = ((passed / completed) * 100).toFixed(1);
    console.log(`  🎯 Pass Rate:  ${passed}/${completed} (${passRate}%)`);
  }

  // TODO / remaining
  const todoRuns = runs.filter(r => r.status === 'TODO');
  if (todoRuns.length > 0) {
    console.log(`\n  ⬜ Remaining TODO (${todoRuns.length}):`);
    for (const r of todoRuns) {
      console.log(`     ${r.testKey} — ${r.summary.substring(0, 60)}`);
    }
  }

  // Failed tests
  const failedRuns = runs.filter(r => r.status === 'FAILED');
  if (failedRuns.length > 0) {
    console.log(`\n  ❌ Failed (${failedRuns.length}):`);
    for (const r of failedRuns) {
      console.log(`     ${r.testKey} — ${r.summary.substring(0, 60)}`);
    }
  }

  // Export
  if (exportFormat === 'csv') {
    const reportsDir = path.resolve(__dirname, '..', '..', 'reports');
    if (!fs.existsSync(reportsDir)) fs.mkdirSync(reportsDir, { recursive: true });

    const csvPath = path.join(reportsDir, `${teKey}-report-${new Date().toISOString().split('T')[0]}.csv`);
    const csvLines = ['test_id,status,summary'];
    for (const r of runs) {
      csvLines.push(`${r.testKey},${r.status},"${r.summary.replace(/"/g, '""')}"`);
    }
    fs.writeFileSync(csvPath, csvLines.join('\n'));
    console.log(`\n  📁 Exported: ${csvPath}`);
  }

  if (exportFormat === 'json') {
    const reportsDir = path.resolve(__dirname, '..', '..', 'reports');
    if (!fs.existsSync(reportsDir)) fs.mkdirSync(reportsDir, { recursive: true });

    const jsonPath = path.join(reportsDir, `${teKey}-report-${new Date().toISOString().split('T')[0]}.json`);
    fs.writeFileSync(jsonPath, JSON.stringify({
      te: teKey,
      generatedAt: new Date().toISOString(),
      totalRuns: runs.length,
      statusCounts,
      completionPct: parseFloat(completionPct),
      passRate: completed > 0 ? parseFloat(((passed / completed) * 100).toFixed(1)) : 0,
      runs,
    }, null, 2));
    console.log(`\n  📁 Exported: ${jsonPath}`);
  }

  console.log('');
}

main().catch(err => { console.error('\n💥', err.message); process.exit(1); });
