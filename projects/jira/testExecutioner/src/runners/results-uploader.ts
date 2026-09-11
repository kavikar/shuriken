/**
 * Test Executioner — Results Uploader
 *
 * Generic tool-agnostic results uploader for Xray Cloud test executions.
 * Takes a CSV/JSON/Markdown file with test case IDs and pass/fail status,
 * and pushes the results to Xray Cloud via GraphQL API.
 *
 * Input sources: Comet, Maestro, manual spreadsheet, any CI/CD pipeline
 *
 * ═══════════════════════════════════════════════════════════════════
 *  CSV FORMAT (recommended — simplest for all tools):
 * ═══════════════════════════════════════════════════════════════════
 *  Required columns: test_id, status
 *  Optional columns: comment, evidence, order_id, defect, discount
 *
 *  Example:
 *    test_id,status,comment,order_id,evidence
 *    TE-10083,PASS,Order placed successfully,ORD-12345,screenshot.png
 *    TE-10084,FAIL,Discount not applied,,
 *    TE-10085,BLOCKED,Store closed for maintenance,,
 *
 * ═══════════════════════════════════════════════════════════════════
 *  JSON FORMAT (structured — for programmatic tools):
 * ═══════════════════════════════════════════════════════════════════
 *  {
 *    "source": "comet|maestro|manual",
 *    "executedAt": "2025-01-15T10:30:00Z",
 *    "results": [
 *      { "testKey": "TE-10083", "status": "PASS", "comment": "...", "orderId": "..." },
 *      ...
 *    ]
 *  }
 *
 * ═══════════════════════════════════════════════════════════════════
 *  MARKDOWN FORMAT (from Comet/AI tools — auto-parsed):
 * ═══════════════════════════════════════════════════════════════════
 *  Pipe-delimited table or mini-summary blocks (see parsers below).
 *
 * ═══════════════════════════════════════════════════════════════════
 *
 * Usage:
 *   npx ts-node src/runners/results-uploader.ts --file results.csv --te TE-10082 --dry-run
 *   npx ts-node src/runners/results-uploader.ts --file results.csv --te TE-10082 --upload
 *   npx ts-node src/runners/results-uploader.ts --file results.json --te TE-10082 --upload --comment "Sprint 42 regression"
 *
 * Flags:
 *   --file <path>       Path to results file (CSV, JSON, or Markdown)
 *   --te <key>          Test Execution key (e.g. TE-10082)
 *   --evidence <dir>    Directory containing screenshot PNGs (optional)
 *   --pdf <path>        Shared PDF evidence attached to ALL test runs
 *   --dry-run           Preview what would be uploaded (default)
 *   --upload            Actually push results + evidence to Xray
 *   --comment <text>    Global comment to attach to every test run
 *   --source <name>     Source tool name (comet, maestro, manual — for reporting)
 */

import * as fs from 'fs';
import * as path from 'path';
import {
  getConfig,
  getXrayConfig,
  xrayGraphQL,
  addAttachment,
  type JiraConfig,
  type XrayConfig,
} from '../../../shared/xray-client';

// ── Types ──────────────────────────────────────────────────────────

export interface TestResult {
  /** Jira test key, e.g. TE-10083 */
  testKey: string;
  /** PASS, FAIL, BLOCKED, TODO */
  status: 'PASS' | 'FAIL' | 'BLOCKED' | 'TODO';
  /** Free-form comment (order ID, defect, notes, etc.) */
  comment?: string;
  /** Order/confirmation ID */
  orderId?: string;
  /** Offer name or test description (for display) */
  description?: string;
  /** Discount amount observed */
  discount?: string;
  /** Defect description if FAIL */
  defect?: string;
  /** Paths to screenshot/evidence files */
  evidenceFiles?: string[];
}

export interface ResultsFile {
  /** Source tool (comet, maestro, manual, etc.) */
  source?: string;
  /** When the test was executed */
  executedAt?: string;
  /** Tester name or identifier */
  tester?: string;
  /** Environment (QA, UAT, STG, etc.) */
  environment?: string;
  /** The actual results */
  results: TestResult[];
}

// ── Xray Status Mapping ────────────────────────────────────────────
const STATUS_MAP: Record<string, string> = {
  'PASS': 'PASSED',
  'PASSED': 'PASSED',
  'FAIL': 'FAILED',
  'FAILED': 'FAILED',
  'BLOCKED': 'BLOCKED',
  'TODO': 'TODO',
  'EXECUTING': 'EXECUTING',
  'SKIP': 'TODO',
  'SKIPPED': 'TODO',
};

// ═══════════════════════════════════════════════════════════════════
//  PARSERS — Auto-detect format and parse input files
// ═══════════════════════════════════════════════════════════════════

/**
 * Parse a structured JSON results file.
 */
function parseJsonResults(filePath: string): ResultsFile {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const data = JSON.parse(raw);

  if (!data.results || !Array.isArray(data.results)) {
    throw new Error('JSON file must have a "results" array');
  }

  for (const r of data.results) {
    if (!r.testKey && !r.test_id) throw new Error(`Each result must have a "testKey" or "test_id" field`);
    if (!r.status) throw new Error(`Result for ${r.testKey || r.test_id} missing "status" field`);

    // Normalize field names
    if (r.test_id && !r.testKey) r.testKey = r.test_id;
    if (r.order_id && !r.orderId) r.orderId = r.order_id;

    r.status = r.status.toUpperCase();
    if (!['PASS', 'FAIL', 'BLOCKED', 'TODO', 'PASSED', 'FAILED', 'SKIP', 'SKIPPED'].includes(r.status)) {
      throw new Error(`Invalid status "${r.status}" for ${r.testKey}. Use PASS, FAIL, BLOCKED, or TODO`);
    }
    // Normalize to short form
    if (r.status === 'PASSED') r.status = 'PASS';
    if (r.status === 'FAILED') r.status = 'FAIL';
    if (r.status === 'SKIP' || r.status === 'SKIPPED') r.status = 'TODO';
  }

  return {
    source: data.source,
    executedAt: data.executedAt,
    tester: data.tester,
    environment: data.environment,
    results: data.results,
  };
}

/**
 * Parse a CSV file.
 *
 * Flexible column detection — supports these column name patterns:
 *   test_id / testKey / test_key / jira_id / key  →  testKey
 *   status / result                                →  status
 *   comment / notes / note                         →  comment
 *   order_id / orderId / confirmation              →  orderId
 *   description / offer / offer_name / name        →  description
 *   discount                                       →  discount
 *   defect / bug / issue                           →  defect
 *   evidence / screenshot / file                   →  evidenceFiles
 */
function parseCsvResults(filePath: string): ResultsFile {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const results: TestResult[] = [];

  // CSV parser handling quoted fields
  function parseCsvLine(line: string): string[] {
    const fields: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"') {
          if (i + 1 < line.length && line[i + 1] === '"') {
            current += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          current += ch;
        }
      } else {
        if (ch === '"') {
          inQuotes = true;
        } else if (ch === ',') {
          fields.push(current.trim());
          current = '';
        } else {
          current += ch;
        }
      }
    }
    fields.push(current.trim());
    return fields;
  }

  const lines = raw.split(/\r?\n/).filter(l => l.trim().length > 0);
  if (lines.length < 2) throw new Error('CSV file must have a header row and at least one data row');

  // ── Column mapping ──
  const headers = parseCsvLine(lines[0]).map(h => h.toLowerCase().replace(/[^a-z0-9_]/g, ''));
  const colMap: Record<string, number> = {};

  const fieldAliases: Record<string, string[]> = {
    testKey:     ['test_id', 'testkey', 'test_key', 'jira_id', 'jiraid', 'key', 'id', 'tc', 'testcase'],
    status:      ['status', 'result', 'pass_fail', 'passfail', 'outcome'],
    comment:     ['comment', 'comments', 'notes', 'note', 'remark', 'remarks'],
    orderId:     ['order_id', 'orderid', 'confirmation', 'confirmation_number', 'confirmationnumber', 'conf'],
    description: ['description', 'offer', 'offer_name', 'offername', 'name', 'test_name', 'testname', 'summary'],
    discount:    ['discount', 'discount_amount', 'discountamount', 'amount'],
    defect:      ['defect', 'bug', 'issue', 'defect_description', 'bugid', 'bug_id'],
    evidence:    ['evidence', 'screenshot', 'file', 'attachment', 'image'],
  };

  for (const [field, aliases] of Object.entries(fieldAliases)) {
    for (const alias of aliases) {
      const idx = headers.indexOf(alias);
      if (idx !== -1) {
        colMap[field] = idx;
        break;
      }
    }
  }

  if (colMap.testKey === undefined) {
    // Fallback: if no header match, assume old format: TC#, Jira ID, Offer, Result, ...
    if (headers.length >= 4) {
      colMap.testKey = 1;
      colMap.description = 2;
      colMap.status = 3;
      colMap.discount = 4;
      colMap.orderId = 5;
      colMap.comment = 6;
    } else {
      throw new Error('CSV must have headers including test_id and status columns');
    }
  }
  if (colMap.status === undefined) {
    throw new Error('CSV must have a "status" or "result" column');
  }

  // ── Parse rows ──
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);

    const testKey = cols[colMap.testKey] || '';
    const rawStatus = cols[colMap.status] || '';

    // Must have a valid Jira key
    if (!testKey.match(/^[A-Z]+-\d+$/)) continue;

    // Extract status — strip emoji and whitespace
    const statusMatch = rawStatus.replace(/[^\w\s]/g, '').trim().match(/\b(PASS|FAIL|BLOCKED|TODO|PASSED|FAILED|SKIP|SKIPPED)\b/i);
    let status: TestResult['status'] = 'TODO';
    if (statusMatch) {
      const s = statusMatch[1].toUpperCase();
      if (s === 'PASS' || s === 'PASSED') status = 'PASS';
      else if (s === 'FAIL' || s === 'FAILED') status = 'FAIL';
      else if (s === 'BLOCKED') status = 'BLOCKED';
      else status = 'TODO';
    }

    // Clean discount — strip Excel escaping
    let discount = colMap.discount !== undefined ? (cols[colMap.discount] || '').replace(/^['']/, '').trim() : undefined;
    const discountMatch = discount?.match(/(-?\$[\d.]+)/);
    if (discountMatch) discount = discountMatch[1];
    if (!discount || discount === 'N/A') discount = undefined;

    // Clean orderId
    const rawOrderId = colMap.orderId !== undefined ? (cols[colMap.orderId] || '').trim() : '';
    const orderId = (rawOrderId && rawOrderId !== 'N/A') ? rawOrderId : undefined;

    results.push({
      testKey,
      status,
      description: colMap.description !== undefined ? (cols[colMap.description] || '').trim() || undefined : undefined,
      discount,
      orderId,
      comment: colMap.comment !== undefined ? (cols[colMap.comment] || '').trim() || undefined : undefined,
      defect: colMap.defect !== undefined ? (cols[colMap.defect] || '').trim() || undefined : undefined,
    });
  }

  if (results.length === 0) {
    throw new Error('Could not parse any test results from CSV.');
  }

  return { results };
}

/**
 * Parse a Markdown/text summary table (from Comet, AI tools, etc.)
 * Supports pipe-delimited tables and mini-summary blocks.
 */
function parseMarkdownResults(filePath: string): ResultsFile {
  const raw = fs.readFileSync(filePath, 'utf-8');
  const lines = raw.split('\n');
  const results: TestResult[] = [];

  // Strategy 1: Pipe-delimited table rows with Jira keys
  const tableRowRegex = /\|\s*(\d+)\s*\|\s*([A-Z]+-\d+)\s*\|\s*([^|]+)\|\s*(PASS|FAIL|BLOCKED|TODO)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|/i;

  for (const line of lines) {
    const match = line.match(tableRowRegex);
    if (match) {
      results.push({
        testKey: match[2].trim(),
        description: match[3].trim(),
        status: match[4].trim().toUpperCase() as TestResult['status'],
        discount: match[5].trim() || undefined,
        orderId: match[6].trim() || undefined,
        comment: match[7].trim() || undefined,
      });
    }
  }

  // Strategy 2: Mini-summary blocks (TC1 | TE-10083 | offer name)
  if (results.length === 0) {
    const tcHeaderRegex = /TC(\d+)\s*\|\s*([A-Z]+-\d+)\s*\|\s*(.+)/i;
    const resultRegex = /Result:\s*(PASS|FAIL|BLOCKED|TODO)/i;
    const confirmRegex = /(?:Confirmation|Order)\s*#?:\s*(\S+)/i;
    const defectRegex = /Defect:\s*(.+)/i;
    const discountRegex = /Discount:\s*(\$[\d.]+)/i;

    let current: Partial<TestResult> | null = null;

    for (const line of lines) {
      const tcMatch = line.match(tcHeaderRegex);
      if (tcMatch) {
        if (current?.testKey) {
          results.push({
            testKey: current.testKey,
            status: current.status || 'TODO',
            description: current.description || '',
            discount: current.discount,
            orderId: current.orderId,
            defect: current.defect,
            comment: current.comment,
          } as TestResult);
        }
        current = {
          testKey: tcMatch[2].trim(),
          description: tcMatch[3].trim(),
        };
        continue;
      }

      if (current) {
        const resMatch = line.match(resultRegex);
        if (resMatch) current.status = resMatch[1].toUpperCase() as TestResult['status'];

        const confMatch = line.match(confirmRegex);
        if (confMatch && confMatch[1] !== 'N/A') current.orderId = confMatch[1];

        const defMatch = line.match(defectRegex);
        if (defMatch && defMatch[1].trim().toLowerCase() !== 'none') current.defect = defMatch[1].trim();

        const discMatch = line.match(discountRegex);
        if (discMatch) current.discount = discMatch[1];
      }
    }

    // Last block
    if (current?.testKey) {
      results.push({
        testKey: current.testKey,
        status: current.status || 'TODO',
        description: current.description || '',
        discount: current.discount,
        orderId: current.orderId,
        defect: current.defect,
        comment: current.comment,
      } as TestResult);
    }
  }

  if (results.length === 0) {
    throw new Error('Could not parse any test results. Expected pipe-delimited table or TC mini-summary blocks.');
  }

  return { results };
}

/**
 * Auto-detect file format and parse.
 */
function parseResultsFile(filePath: string): ResultsFile {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.json') return parseJsonResults(filePath);
  if (ext === '.csv')  return parseCsvResults(filePath);
  return parseMarkdownResults(filePath);
}

// ═══════════════════════════════════════════════════════════════════
//  EVIDENCE HELPERS
// ═══════════════════════════════════════════════════════════════════

/**
 * Find screenshot files for a test key in the evidence directory.
 * Convention: files named like TE-261953_*.png or TE-10083-signed-in.png
 */
function findEvidenceFiles(evidenceDir: string, testKey: string): string[] {
  if (!fs.existsSync(evidenceDir)) return [];

  const files = fs.readdirSync(evidenceDir);
  const keyNormalized = testKey.replace(/-/g, '[-_]');
  const pattern = new RegExp(`^${keyNormalized}`, 'i');

  return files
    .filter(f => pattern.test(f) && /\.(png|jpg|jpeg|gif|webp|pdf)$/i.test(f))
    .map(f => path.join(evidenceDir, f))
    .sort();
}

// ═══════════════════════════════════════════════════════════════════
//  XRAY CLOUD GRAPHQL OPERATIONS
// ═══════════════════════════════════════════════════════════════════

/**
 * Get all test runs in a TE at once.
 * Returns a map of testKey → { runId, currentStatus }
 */
async function getAllTestRuns(
  xrayConfig: XrayConfig,
  teKey: string,
): Promise<Map<string, { runId: string; status: string }>> {
  const runMap = new Map<string, { runId: string; status: string }>();
  let start = 0;
  const pageSize = 100;

  while (true) {
    const result = await xrayGraphQL(xrayConfig, `{
      getTestExecutions(jql: "key = ${teKey}", limit: 1) {
        results {
          issueId
          testRuns(limit: ${pageSize}, start: ${start}) {
            total
            results {
              id
              status { name }
              test {
                issueId
                jira(fields: ["key"])
              }
            }
          }
        }
      }
    }`);

    const te = result.data?.getTestExecutions?.results?.[0];
    if (!te) throw new Error(`Test Execution ${teKey} not found in Xray`);

    const page = te.testRuns?.results || [];
    for (const run of page) {
      const key = run.test?.jira?.key;
      if (key) {
        runMap.set(key, {
          runId: run.id,
          status: run.status?.name || 'TODO',
        });
      }
    }

    const total = te.testRuns?.total || 0;
    start += page.length;
    if (start >= total || page.length === 0) break;
  }

  return runMap;
}

/**
 * Update the status of a test run.
 */
async function updateTestRunStatus(
  xrayConfig: XrayConfig,
  testRunId: string,
  status: string,
): Promise<void> {
  const xrayStatus = STATUS_MAP[status] || status;

  await xrayGraphQL(xrayConfig, `mutation UpdateStatus($id: String!, $status: String!) {
    updateTestRunStatus(id: $id, status: $status)
  }`, { id: testRunId, status: xrayStatus });
}

/**
 * Add a comment to a test run.
 */
async function updateTestRunComment(
  xrayConfig: XrayConfig,
  testRunId: string,
  comment: string,
): Promise<void> {
  await xrayGraphQL(xrayConfig, `mutation UpdateComment($id: String!, $comment: String!) {
    updateTestRunComment(id: $id, comment: $comment)
  }`, { id: testRunId, comment });
}

/**
 * Upload a screenshot/file as evidence to a test run.
 */
async function addEvidenceToTestRun(
  xrayConfig: XrayConfig,
  testRunId: string,
  filePath: string,
): Promise<void> {
  const fileName = path.basename(filePath);
  const fileData = fs.readFileSync(filePath);
  const base64Data = fileData.toString('base64');

  const ext = path.extname(filePath).toLowerCase();
  const mimeTypes: Record<string, string> = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.webp': 'image/webp', '.pdf': 'application/pdf',
  };
  const mimeType = mimeTypes[ext] || 'application/octet-stream';

  await xrayGraphQL(xrayConfig, `mutation AddEvidence($id: String!, $evidence: [AttachmentInput!]!) {
    addEvidenceToTestRun(id: $id, evidence: $evidence)
  }`, {
    id: testRunId,
    evidence: [{ filename: fileName, mimeType, data: base64Data }],
  });
}

// ═══════════════════════════════════════════════════════════════════
//  CLI
// ═══════════════════════════════════════════════════════════════════

interface CliArgs {
  file: string;
  te: string;
  evidenceDir?: string;
  pdfFile?: string;
  dryRun: boolean;
  comment?: string;
  source?: string;
}

function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  const result: CliArgs = { file: '', te: '', dryRun: true };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--file':     result.file = args[++i]; break;
      case '--te':       result.te = args[++i]; break;
      case '--evidence': result.evidenceDir = args[++i]; break;
      case '--pdf':      result.pdfFile = args[++i]; break;
      case '--upload':   result.dryRun = false; break;
      case '--dry-run':  result.dryRun = true; break;
      case '--comment':  result.comment = args[++i]; break;
      case '--source':   result.source = args[++i]; break;
    }
  }

  if (!result.file) throw new Error('Missing --file <path>');
  if (!result.te) throw new Error('Missing --te <key> (e.g. TE-10082)');

  return result;
}

// ═══════════════════════════════════════════════════════════════════
//  MAIN
// ═══════════════════════════════════════════════════════════════════

async function main() {
  const cli = parseArgs();

  console.log('');
  console.log('  ⚔️  TEST EXECUTIONER — Results Uploader');
  console.log('═══════════════════════════════════════════════════════');
  console.log(`  Mode:       ${cli.dryRun ? '🔍 DRY RUN (preview only)' : '🚀 UPLOAD (pushing to Xray)'}`);
  console.log(`  Results:    ${cli.file}`);
  console.log(`  TE:         ${cli.te}`);
  if (cli.source)      console.log(`  Source:     ${cli.source}`);
  if (cli.evidenceDir) console.log(`  Evidence:   ${cli.evidenceDir}`);
  if (cli.pdfFile)     console.log(`  PDF:        ${cli.pdfFile}`);
  if (cli.comment)     console.log(`  Comment:    ${cli.comment}`);
  console.log('═══════════════════════════════════════════════════════\n');

  // ── Parse results file ──────────────────────────────────────────
  const absFile = path.isAbsolute(cli.file) ? cli.file : path.resolve(cli.file);
  if (!fs.existsSync(absFile)) {
    throw new Error(`Results file not found: ${absFile}`);
  }

  console.log('📄 Parsing results file...');
  const data = parseResultsFile(absFile);
  if (cli.source) data.source = cli.source;
  console.log(`   Found ${data.results.length} test results${data.source ? ` (source: ${data.source})` : ''}\n`);

  // Status summary
  const pass    = data.results.filter(r => r.status === 'PASS').length;
  const fail    = data.results.filter(r => r.status === 'FAIL').length;
  const blocked = data.results.filter(r => r.status === 'BLOCKED').length;
  const todo    = data.results.filter(r => r.status === 'TODO').length;
  console.log(`   ✅ PASS: ${pass}  ❌ FAIL: ${fail}  🚫 BLOCKED: ${blocked}  ⬜ TODO: ${todo}\n`);

  // Results table
  const hasDesc    = data.results.some(r => r.description);
  const hasOrderId = data.results.some(r => r.orderId);

  console.log('   ┌─────────────────┬──────────┬' + (hasOrderId ? '───────────────┬' : '') + (hasDesc ? '──────────────────────────────────────┐' : '──────────────────────────────────┐'));
  console.log('   │ Test Key        │ Status   │' + (hasOrderId ? ' Order ID      │' : '') + (hasDesc ? ' Description                          │' : ' Comment                          │'));
  console.log('   ├─────────────────┼──────────┼' + (hasOrderId ? '───────────────┼' : '') + (hasDesc ? '──────────────────────────────────────┤' : '──────────────────────────────────┤'));

  for (const r of data.results) {
    const icon = r.status === 'PASS' ? '✅' : r.status === 'FAIL' ? '❌' : r.status === 'BLOCKED' ? '🚫' : '⬜';
    const key = r.testKey.padEnd(15);
    const status = `${icon} ${r.status}`.padEnd(8);
    const orderId = hasOrderId ? (r.orderId || 'N/A').substring(0, 13).padEnd(13) + ' │' : '';
    const desc = hasDesc
      ? (r.description || '').substring(0, 36).padEnd(36)
      : (r.comment || '').substring(0, 32).padEnd(32);
    console.log(`   │ ${key} │ ${status} │${orderId ? ' ' + orderId : ''} ${desc} │`);
  }

  console.log('   └─────────────────┴──────────┴' + (hasOrderId ? '───────────────┴' : '') + (hasDesc ? '──────────────────────────────────────┘' : '──────────────────────────────────┘'));
  console.log('');

  // ── Find evidence files ─────────────────────────────────────────
  const evidenceDir = cli.evidenceDir
    ? (path.isAbsolute(cli.evidenceDir) ? cli.evidenceDir : path.resolve(cli.evidenceDir))
    : null;

  if (evidenceDir) {
    console.log('📸 Scanning for evidence screenshots...');
    let totalEvidence = 0;
    for (const r of data.results) {
      const files = findEvidenceFiles(evidenceDir, r.testKey);
      r.evidenceFiles = files;
      if (files.length > 0) {
        console.log(`   ${r.testKey}: ${files.length} file(s) — ${files.map(f => path.basename(f)).join(', ')}`);
        totalEvidence += files.length;
      }
    }
    console.log(`   Total evidence files: ${totalEvidence}\n`);
  }

  // ── DRY RUN: Stop here ──────────────────────────────────────────
  if (cli.dryRun) {
    console.log('════════════════════════════════════════════════════');
    console.log('  DRY RUN COMPLETE — No changes pushed to Xray');
    console.log('  Re-run with --upload to push results');
    console.log('════════════════════════════════════════════════════');
    return;
  }

  // ── Connect to Xray ─────────────────────────────────────────────
  const jiraConfig = getConfig();
  const xrayConfig = getXrayConfig();
  if (!jiraConfig || !xrayConfig) {
    throw new Error('Missing Jira/Xray credentials. Check .env file or ~/Documents/jira-automation/.env');
  }

  console.log('🔗 Connecting to Xray Cloud...');
  const runMap = await getAllTestRuns(xrayConfig, cli.te);
  console.log(`   Found ${runMap.size} test runs in ${cli.te}\n`);

  // ── Match results to test runs ──────────────────────────────────
  const matched: Array<{ result: TestResult; runId: string; currentStatus: string }> = [];
  const unmatched: TestResult[] = [];

  for (const r of data.results) {
    const run = runMap.get(r.testKey);
    if (run) {
      matched.push({ result: r, runId: run.runId, currentStatus: run.status });
    } else {
      unmatched.push(r);
    }
  }

  if (unmatched.length > 0) {
    console.log(`⚠️  ${unmatched.length} result(s) not found in ${cli.te}:`);
    for (const r of unmatched) {
      console.log(`   ❓ ${r.testKey} — ${r.description || r.comment || ''}`);
    }
    console.log('   These will be skipped.\n');
  }

  console.log(`🚀 Uploading ${matched.length} results to ${cli.te}...\n`);

  // ── Upload results ──────────────────────────────────────────────
  let successCount = 0;
  let errorCount = 0;

  for (const { result, runId } of matched) {
    const icon = result.status === 'PASS' ? '✅' : result.status === 'FAIL' ? '❌' : '🚫';
    process.stdout.write(`   ${icon} ${result.testKey} → ${result.status}`);

    try {
      // Build comment
      const commentParts: string[] = [];
      if (cli.comment) commentParts.push(cli.comment);
      if (result.orderId) commentParts.push(`Order/Confirmation: ${result.orderId}`);
      if (result.discount) commentParts.push(`Discount: ${result.discount}`);
      if (result.defect) commentParts.push(`Defect: ${result.defect}`);
      if (result.comment) commentParts.push(result.comment);
      if (data.source) commentParts.push(`Source: ${data.source}`);
      const fullComment = commentParts.length > 0 ? commentParts.join('\n') : undefined;

      // Update status
      await updateTestRunStatus(xrayConfig, runId, result.status);
      process.stdout.write(' [status ✓]');

      // Add comment
      if (fullComment) {
        try {
          await updateTestRunComment(xrayConfig, runId, fullComment);
          process.stdout.write(' [comment ✓]');
        } catch (e: any) {
          process.stdout.write(` [comment ⚠ ${e.message.substring(0, 40)}]`);
        }
      }

      // Upload evidence screenshots
      if (result.evidenceFiles && result.evidenceFiles.length > 0) {
        for (const evidenceFile of result.evidenceFiles) {
          try {
            await addEvidenceToTestRun(xrayConfig, runId, evidenceFile);
            process.stdout.write(` [📎 ${path.basename(evidenceFile)}]`);
          } catch (e: any) {
            process.stdout.write(` [📎 ❌ ${path.basename(evidenceFile)}: ${e.message.substring(0, 50)}]`);
          }
        }
      }

      console.log();
      successCount++;
    } catch (e: any) {
      console.log(` [❌ ERROR: ${e.message.substring(0, 80)}]`);
      errorCount++;
    }

    // Rate limit protection
    await new Promise(resolve => setTimeout(resolve, 300));
  }

  // ── Upload PDF as Jira attachment ────────────────────────────────
  if (cli.pdfFile) {
    const absPdf = path.isAbsolute(cli.pdfFile) ? cli.pdfFile : path.resolve(cli.pdfFile);
    if (fs.existsSync(absPdf)) {
      process.stdout.write(`\n📄 Attaching PDF to ${cli.te}...`);
      try {
        await addAttachment(jiraConfig!, cli.te, absPdf);
        console.log(` ✅ ${path.basename(absPdf)}`);
      } catch (e: any) {
        console.log(` ❌ ${e.message.substring(0, 100)}`);
      }
    } else {
      console.log(`\n⚠️  PDF not found: ${absPdf}`);
    }
  }

  // ── Attach results file to TE ────────────────────────────────────
  if (absFile) {
    process.stdout.write(`📎 Attaching results file to ${cli.te}...`);
    try {
      await addAttachment(jiraConfig!, cli.te, absFile);
      console.log(` ✅ ${path.basename(absFile)}`);
    } catch (e: any) {
      console.log(` ❌ ${e.message.substring(0, 100)}`);
    }
  }

  // ── Final Summary ───────────────────────────────────────────────
  console.log('');
  console.log('  ⚔️  UPLOAD COMPLETE');
  console.log('═══════════════════════════════════════════════════════');
  console.log(`  TE:          ${cli.te}`);
  console.log(`  Uploaded:    ${successCount} / ${matched.length}`);
  if (errorCount > 0) console.log(`  Errors:      ${errorCount}`);
  if (unmatched.length > 0) console.log(`  Unmatched:   ${unmatched.length}`);
  console.log(`  Results:     ✅ ${pass} PASS  ❌ ${fail} FAIL  🚫 ${blocked} BLOCKED  ⬜ ${todo} TODO`);
  if (data.source) console.log(`  Source:      ${data.source}`);
  console.log('═══════════════════════════════════════════════════════\n');
}

main().catch((err) => {
  console.error('\n💥 Fatal error:', err.message);
  process.exit(1);
});
