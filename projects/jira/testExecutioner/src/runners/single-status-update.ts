/**
 * Test Executioner — Single Status Update
 *
 * Update one test run inside a Test Execution with a target status and optional comment.
 * Bulk updates should continue to use results-uploader.ts.
 *
 * Usage:
 *   npm run single-update -- --te TE-10082 --test TE-10083 --status PASS --comment "Validated on build 42" --apply
 */

import {
  getXrayConfig,
  xrayGraphQL,
  type XrayConfig,
} from '../../../shared/xray-client';

const STATUS_MAP: Record<string, string> = {
  PASS: 'PASSED',
  PASSED: 'PASSED',
  FAIL: 'FAILED',
  FAILED: 'FAILED',
  BLOCKED: 'BLOCKED',
  TODO: 'TODO',
  EXECUTING: 'EXECUTING',
};

interface CliArgs {
  te: string;
  testKey: string;
  status: string;
  comment?: string;
  apply: boolean;
}

function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  const result: CliArgs = { te: '', testKey: '', status: '', apply: false };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--te':
        result.te = args[++i] || '';
        break;
      case '--test':
        result.testKey = (args[++i] || '').toUpperCase();
        break;
      case '--status':
        result.status = (args[++i] || '').toUpperCase();
        break;
      case '--comment':
        result.comment = args[++i] || '';
        break;
      case '--apply':
        result.apply = true;
        break;
      case '--dry-run':
        result.apply = false;
        break;
    }
  }

  if (!result.te) throw new Error('Missing --te <key>');
  if (!result.testKey) throw new Error('Missing --test <TE-...>');
  if (!STATUS_MAP[result.status]) throw new Error('Invalid --status. Use PASS, FAIL, BLOCKED, TODO, or EXECUTING.');
  return result;
}

async function findTestRun(
  xrayConfig: XrayConfig,
  teKey: string,
  testKey: string,
): Promise<{ runId: string; currentStatus: string } | null> {
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
              test { jira(fields: ["key"]) }
            }
          }
        }
      }
    }`);

    const te = result.data?.getTestExecutions?.results?.[0];
    if (!te) throw new Error(`TE ${teKey} not found`);

    const page = te.testRuns?.results || [];
    for (const run of page) {
      if (run.test?.jira?.key === testKey) {
        return { runId: run.id, currentStatus: run.status?.name || 'TODO' };
      }
    }

    const total = te.testRuns?.total || 0;
    start += page.length;
    if (start >= total || page.length === 0) break;
  }

  return null;
}

async function updateTestRunStatus(xrayConfig: XrayConfig, runId: string, status: string): Promise<void> {
  await xrayGraphQL(xrayConfig, `mutation UpdateStatus($id: String!, $status: String!) {
    updateTestRunStatus(id: $id, status: $status)
  }`, { id: runId, status: STATUS_MAP[status] });
}

async function updateTestRunComment(xrayConfig: XrayConfig, runId: string, comment: string): Promise<void> {
  await xrayGraphQL(xrayConfig, `mutation UpdateComment($id: String!, $comment: String!) {
    updateTestRunComment(id: $id, comment: $comment)
  }`, { id: runId, comment });
}

async function main() {
  const cli = parseArgs();
  const xrayConfig = getXrayConfig();
  if (!xrayConfig) throw new Error('Missing Xray credentials');

  console.log(`\n  ⚔️  TEST EXECUTIONER — Single Status Update`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  TE:      ${cli.te}`);
  console.log(`  Test:    ${cli.testKey}`);
  console.log(`  Status:  ${cli.status}`);
  if (cli.comment) console.log(`  Comment: ${cli.comment}`);
  console.log(`  Mode:    ${cli.apply ? 'APPLY' : 'DRY RUN'}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  const run = await findTestRun(xrayConfig, cli.te, cli.testKey);
  if (!run) throw new Error(`${cli.testKey} is not present in ${cli.te}`);

  console.log(`  Current status: ${run.currentStatus}`);
  console.log(`  Target status:  ${STATUS_MAP[cli.status]}`);

  if (!cli.apply) {
    console.log(`\n  🔍 DRY RUN COMPLETE — add --apply to update the run.\n`);
    return;
  }

  await updateTestRunStatus(xrayConfig, run.runId, cli.status);
  if (cli.comment) {
    await updateTestRunComment(xrayConfig, run.runId, cli.comment);
  }

  console.log(`\n  ✅ Updated ${cli.testKey} in ${cli.te}.\n`);
}

main().catch((err) => {
  console.error(`\n💥 ${err.message}`);
  process.exit(1);
});