/**
 * Test Executioner — Reset TE
 *
 * Reset all test runs in a Test Execution back to TODO status.
 * Useful for re-running tests from scratch.
 *
 * Usage:
 *   npx ts-node src/runners/reset-te.ts --te TE-10082 --dry-run
 *   npx ts-node src/runners/reset-te.ts --te TE-10082 --reset
 */

import {
  getXrayConfig,
  xrayGraphQL,
  type XrayConfig,
} from '../../../shared/xray-client';

async function getAllTestRuns(
  xrayConfig: XrayConfig,
  teKey: string,
): Promise<Array<{ runId: string; testKey: string; status: string }>> {
  const runs: Array<{ runId: string; testKey: string; status: string }> = [];
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
      runs.push({
        runId: run.id,
        testKey: run.test?.jira?.key || '???',
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
  let dryRun = true;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--te') teKey = args[++i];
    if (args[i] === '--reset') dryRun = false;
    if (args[i] === '--dry-run') dryRun = true;
  }

  if (!teKey) throw new Error('Missing --te <key>');

  console.log(`\n  ⚔️  TEST EXECUTIONER — Reset TE`);
  console.log(`═══════════════════════════════════════════════════════`);
  console.log(`  TE:    ${teKey}`);
  console.log(`  Mode:  ${dryRun ? '🔍 DRY RUN' : '🔄 RESET ALL TO TODO'}`);
  console.log(`═══════════════════════════════════════════════════════\n`);

  const xrayConfig = getXrayConfig();
  if (!xrayConfig) throw new Error('Missing Xray credentials');

  const runs = await getAllTestRuns(xrayConfig, teKey);
  const nonTodo = runs.filter(r => r.status !== 'TODO');

  console.log(`   Total runs: ${runs.length}`);
  console.log(`   Already TODO: ${runs.length - nonTodo.length}`);
  console.log(`   To reset: ${nonTodo.length}\n`);

  if (nonTodo.length === 0) {
    console.log('   ✅ All runs are already TODO. Nothing to do.');
    return;
  }

  for (const run of nonTodo) {
    const icon = run.status === 'PASSED' ? '✅' : run.status === 'FAILED' ? '❌' : '🚫';
    if (dryRun) {
      console.log(`   ${icon} ${run.testKey} (${run.status}) → would reset to TODO`);
    } else {
      process.stdout.write(`   ${icon} ${run.testKey} (${run.status}) → TODO`);
      await xrayGraphQL(xrayConfig, `mutation { updateTestRunStatus(id: "${run.runId}", status: "TODO") }`);
      console.log(' ✓');
      await new Promise(r => setTimeout(r, 300));
    }
  }

  console.log(`\n  ${dryRun ? '🔍 DRY RUN COMPLETE — run with --reset to apply' : '✅ RESET COMPLETE'}\n`);
}

main().catch(err => { console.error('\n💥', err.message); process.exit(1); });
