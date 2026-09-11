/**
 * Test Executioner — TE Status List
 *
 * Fetch the full test case list from a Test Execution with current statuses.
 * Supports optional status filtering and CSV/JSON export for downstream parsing.
 *
 * Usage:
 *   npm run status-list -- --te TE-10082
 *   npm run status-list -- --te TE-10082 --status PASSED,FAILED
 *   npm run status-list -- --te TE-10082 --non-passed --export csv
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

interface CliArgs {
  te: string;
  statusFilter: Set<string>;
  nonPassedOnly: boolean;
  exportFormat: '' | 'csv' | 'json';
  outFile?: string;
}

function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  const result: CliArgs = {
    te: '',
    statusFilter: new Set<string>(),
    nonPassedOnly: false,
    exportFormat: '',
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--te':
        result.te = args[++i] || '';
        break;
      case '--status': {
        const raw = args[++i] || '';
        raw.split(',').map(v => v.trim().toUpperCase()).filter(Boolean).forEach(v => result.statusFilter.add(v));
        break;
      }
      case '--non-passed':
        result.nonPassedOnly = true;
        break;
      case '--export': {
        const format = (args[++i] || '').toLowerCase();
        if (format === 'csv' || format === 'json') result.exportFormat = format;
        break;
      }
      case '--out':
        result.outFile = args[++i] || '';
        break;
    }
  }

  if (!result.te) throw new Error('Missing --te <key>');
  return result;
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

function filterRuns(runs: RunInfo[], cli: CliArgs): RunInfo[] {
  return runs.filter((run) => {
    if (cli.nonPassedOnly && run.status === 'PASSED') return false;
    if (cli.statusFilter.size > 0 && !cli.statusFilter.has(run.status.toUpperCase())) return false;
    return true;
  });
}

function exportRuns(teKey: string, format: 'csv' | 'json', runs: RunInfo[], outFile?: string): string {
  let filePath = outFile || '';
  if (!filePath) {
    const reportsDir = path.resolve(__dirname, '..', '..', 'reports');
    if (!fs.existsSync(reportsDir)) fs.mkdirSync(reportsDir, { recursive: true });

    const stamp = new Date().toISOString().split('T')[0];
    filePath = path.join(reportsDir, `${teKey}-status-list-${stamp}.${format}`);
  }

  if (format === 'csv') {
    const rows = ['test_id,status,summary'];
    for (const run of runs) {
      rows.push(`${run.testKey},${run.status},"${run.summary.replace(/"/g, '""')}"`);
    }
    fs.writeFileSync(filePath, rows.join('\n'));
  } else {
    fs.writeFileSync(filePath, JSON.stringify({ te: teKey, total: runs.length, runs }, null, 2));
  }

  return filePath;
}

async function main() {
  const cli = parseArgs();
  const xrayConfig = getXrayConfig();
  if (!xrayConfig) throw new Error('Missing Xray credentials');

  console.log(`\n  📋 TEST EXECUTIONER — TE Status List`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  TE: ${cli.te}`);
  if (cli.nonPassedOnly) console.log(`  Filter: non-passed only`);
  if (cli.statusFilter.size > 0) console.log(`  Statuses: ${Array.from(cli.statusFilter).join(', ')}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  const allRuns = await getAllTestRuns(xrayConfig, cli.te);
  const filteredRuns = filterRuns(allRuns, cli);

  const counts: Record<string, number> = {};
  for (const run of allRuns) counts[run.status] = (counts[run.status] || 0) + 1;

  console.log(`  Total runs in TE: ${allRuns.length}`);
  console.log(`  Matching rows:    ${filteredRuns.length}\n`);
  for (const [status, count] of Object.entries(counts).sort()) {
    console.log(`  ${status.padEnd(10)} ${String(count).padStart(3)}`);
  }

  console.log('');
  for (const run of filteredRuns) {
    console.log(`  ${run.testKey.padEnd(14)} ${run.status.padEnd(10)} ${run.summary}`);
  }

  if (cli.exportFormat) {
    const exported = exportRuns(cli.te, cli.exportFormat, filteredRuns, cli.outFile);
    console.log(`\n  📁 Exported: ${exported}`);
  }

  console.log('');
}

main().catch((err) => {
  console.error(`\n💥 ${err.message}`);
  process.exit(1);
});