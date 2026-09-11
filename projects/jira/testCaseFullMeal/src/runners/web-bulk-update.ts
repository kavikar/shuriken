/**
 * WEB Bulk Update — Push corrected Gherkin + Comet Prompts for all 45 WEB tests
 *
 * Two-phase update:
 *   Phase 1: Push new WEB-specific Gherkin to Xray Cloud (updateGherkinTestDefinition)
 *   Phase 2: Generate Comet prompts from the new Gherkin and push to Jira description
 *
 * Usage:
 *   npx ts-node src/web-bulk-update.ts --dry-run     # Preview only
 *   npx ts-node src/web-bulk-update.ts               # Live push
 *   npx ts-node src/web-bulk-update.ts --phase 1     # Gherkin only
 *   npx ts-node src/web-bulk-update.ts --phase 2     # Comet only
 *   npx ts-node src/web-bulk-update.ts --keys TE-10075,TE-10054  # Specific keys
 */

import {
  getConfig, getXrayConfig, testConnection,
  getIssuesByKeys, getXrayToken,
  updateGherkinDefinition, setTestTypeCucumber,
  updateDescription, readGherkinDefinition,
  XrayTestIssue, XrayConfig,
} from '../client/xray-client';
import { generateWebGherkin, getWebCategory } from '../generators/web-gherkin-generator';
import { generateCometPrompt, promptToADF } from '../generators/comet-prompt-generator';
import { WEB_TEST_KEYS } from '../registry/web-test-cases';

// ── CLI Parsing ────────────────────────────────────────────────────

const args = process.argv.slice(2);
const DRY_RUN = args.includes('--dry-run');
const phaseArg = args.find((_, i, a) => a[i - 1] === '--phase');
const PHASE = phaseArg ? parseInt(phaseArg) : 0; // 0 = both
const keysArg = args.find((_, i, a) => a[i - 1] === '--keys');
const FILTER_KEYS = keysArg ? keysArg.split(',').map(k => k.trim()) : null;

interface Result {
  key: string;
  summary: string;
  category: string;
  phase1: 'success' | 'failed' | 'skipped';
  phase2: 'success' | 'failed' | 'skipped';
  error?: string;
}

// ── Main ───────────────────────────────────────────────────────────

async function main() {
  const jiraConfig = getConfig();
  const xrayConfig = getXrayConfig();
  if (!jiraConfig || !xrayConfig) {
    console.error('❌ Missing JIRA or XRAY config in .env');
    process.exit(1);
  }

  console.log(`\n${'═'.repeat(70)}`);
  console.log(`WEB Bulk Update — ${DRY_RUN ? '🔍 DRY RUN' : '🚀 LIVE'}`);
  console.log(`Phase: ${PHASE === 0 ? 'Both (Gherkin + Comet)' : PHASE === 1 ? 'Gherkin only' : 'Comet only'}`);
  console.log('═'.repeat(70));

  // Verify connection
  if (!DRY_RUN) {
    const ok = await testConnection(jiraConfig);
    if (!ok) { console.error('❌ Jira connection failed'); process.exit(1); }
    await getXrayToken(xrayConfig);
    console.log('✅ Jira + Xray authenticated\n');
  }

  // Get target keys
  const keys = FILTER_KEYS || WEB_TEST_KEYS;
  console.log(`Target: ${keys.length} WEB test cases\n`);

  // Fetch issue metadata
  console.log('Fetching issue metadata from Jira...');
  const issues = await getIssuesByKeys(jiraConfig, keys);
  const issueMap = new Map(issues.map(i => [i.key, i]));
  console.log(`  Got ${issues.length} issues\n`);

  const results: Result[] = [];
  let p1Success = 0, p1Fail = 0, p2Success = 0, p2Fail = 0;

  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const issue = issueMap.get(key);
    if (!issue) {
      console.log(`  ⚠ ${key} — not found in Jira`);
      results.push({ key, summary: 'NOT FOUND', category: '', phase1: 'skipped', phase2: 'skipped' });
      continue;
    }

    const cat = getWebCategory(issue.summary);
    const result: Result = { key, summary: issue.summary, category: cat, phase1: 'skipped', phase2: 'skipped' };

    // ── Phase 1: Push Gherkin to Xray ──
    if (PHASE === 0 || PHASE === 1) {
      const gherkin = generateWebGherkin(issue);

      if (DRY_RUN) {
        console.log(`\n[${i + 1}/${keys.length}] ${key} [${cat}]`);
        console.log(`  ${issue.summary}`);
        console.log(`  Gherkin preview (${gherkin.split('\n').length} lines):`);
        const preview = gherkin.split('\n').slice(0, 6).map(l => `    ${l}`).join('\n');
        console.log(preview);
        if (gherkin.split('\n').length > 6) console.log('    ...');
        result.phase1 = 'skipped';
      } else {
        try {
          if (!issue.numericId) throw new Error('No numeric ID');
          await updateGherkinDefinition(xrayConfig, issue.numericId, gherkin);
          result.phase1 = 'success';
          p1Success++;
          process.stdout.write(`  ✅ ${key} Gherkin pushed [${i + 1}/${keys.length}]\n`);
        } catch (err: any) {
          result.phase1 = 'failed';
          result.error = err.message?.substring(0, 100);
          p1Fail++;
          console.error(`  ❌ ${key} Gherkin FAILED: ${result.error}`);
        }
        // Rate limit
        await new Promise(r => setTimeout(r, 500));
      }
    }

    // ── Phase 2: Generate Comet prompt and push to Jira description ──
    if (PHASE === 0 || PHASE === 2) {
      if (DRY_RUN) {
        result.phase2 = 'skipped';
      } else {
        try {
          // Read the (now updated) Gherkin from Xray
          const xrayData = await readGherkinDefinition(xrayConfig, key);
          const gherkin = xrayData?.gherkin;
          if (!gherkin) throw new Error('No Gherkin in Xray after push');

          const cometPrompt = generateCometPrompt(issue, gherkin);
          const adf = promptToADF(cometPrompt.prompt);
          await updateDescription(jiraConfig, key, adf);

          result.phase2 = 'success';
          p2Success++;
          process.stdout.write(`  ✅ ${key} Comet prompt pushed [${i + 1}/${keys.length}]\n`);
        } catch (err: any) {
          result.phase2 = 'failed';
          result.error = (result.error || '') + ' | Comet: ' + err.message?.substring(0, 100);
          p2Fail++;
          console.error(`  ❌ ${key} Comet FAILED: ${err.message?.substring(0, 100)}`);
        }
        await new Promise(r => setTimeout(r, 500));
      }
    }

    results.push(result);
  }

  // ── Summary ──
  console.log(`\n${'═'.repeat(70)}`);
  if (DRY_RUN) {
    console.log(`DRY RUN complete — ${keys.length} tests previewed. No changes made.`);
  } else {
    console.log('RESULTS:');
    if (PHASE === 0 || PHASE === 1) {
      console.log(`  Phase 1 (Gherkin): ${p1Success} success, ${p1Fail} failed`);
    }
    if (PHASE === 0 || PHASE === 2) {
      console.log(`  Phase 2 (Comet):   ${p2Success} success, ${p2Fail} failed`);
    }

    if (p1Fail > 0 || p2Fail > 0) {
      console.log('\nFailed tests:');
      for (const r of results) {
        if (r.phase1 === 'failed' || r.phase2 === 'failed') {
          console.log(`  ${r.key}: ${r.error}`);
        }
      }
    }
  }
  console.log('═'.repeat(70));
}

main().catch(console.error);
