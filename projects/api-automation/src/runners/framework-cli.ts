import fs from 'node:fs/promises';
import path from 'node:path';

import { buildRequestScripts } from '../generators/build-request-scripts';
import { loadApiSource } from '../importers/load-api-source';
import { loadApiSourceFromUrl } from '../importers/load-api-source-from-url';
import { executeScriptsDryRunFromFile, executeScriptsLiveFromFile } from './execute-scripts';
import { generateScriptsFromFile, generateScriptsFromUrl } from './generate-scripts';

interface RunnerResult {
  output: string;
}

interface FolderScope {
  brand: string;
  adapter: string;
  api: string;
  sourceRoot?: string;
}

const DEFAULT_BRAND = 'Brand Four';
const DEFAULT_ADAPTER = 'loyalty-adapter';

interface OperationCatalogEntry {
  index: number;
  alias: string;
  id: string;
  method: string;
  url: string;
}

type ReportFormat = 'md' | 'json' | 'html';
type StatusCheck = 'not-provided' | 'pending' | 'pass' | 'fail';
type BodyAssertionCheck = 'pending' | 'pass' | 'fail';
type Verdict = 'PASS' | 'FAIL' | 'NOT_EXECUTED';

interface BodyAssertionInput {
  path: string;
  expectedRaw: string;
  expectedValue: unknown;
}

interface BodyAssertionResult {
  path: string;
  expected: string;
  actual?: string;
  check: BodyAssertionCheck;
  message?: string;
}

export async function runFrameworkCli(args: string[]): Promise<RunnerResult> {
  const command = args[0];

  if (!command || command === 'help' || command === '--help' || command === '-h') {
    return { output: buildHelpText() };
  }

  switch (command) {
    case 'inspect':
      return inspectCommand(args.slice(1));
    case 'generate':
      return generateCommand(args.slice(1));
    case 'dry-run':
      return executeCommand('dry-run', args.slice(1));
    case 'run':
      return executeCommand('live', args.slice(1));
    default:
      throw new Error(`Unknown command: ${command}. Use "help" to see available commands.`);
  }
}

async function inspectCommand(args: string[]): Promise<RunnerResult> {
  const source = await loadSourceFromArgs(args);
  const scripts = buildRequestScripts(source.source);
  const operations = buildOperationCatalog(scripts);

  const lines = [
    'API Automation Framework Summary',
    `Source: ${source.source.name} (${source.source.kind})`,
    `Version: ${source.source.version || 'unknown'}`,
    `Operations: ${scripts.length}`,
    '',
    'Selection shortcuts:',
    '  Use --op <index>, --op <alias>, or --operation <exact-id>',
    '',
    'Available operations:',
    ...operations.map((entry) => `${String(entry.index).padStart(2, '0')}. ${entry.alias} | ${entry.method} ${entry.url}`),
  ];

  return { output: lines.join('\n') };
}

async function generateCommand(args: string[]): Promise<RunnerResult> {
  const sourceInput = readSourceInput(args);
  const outputPath = readArgument(args, '--out');
  const outputRoot = readArgument(args, '--output-root') || 'output';

  if (!sourceInput.filePath && !sourceInput.url && !sourceInput.scope) {
    throw new Error('Missing source. Use --url, --file, or --brand/--adapter/--api.');
  }

  const output = sourceInput.url
    ? await generateScriptsFromUrl(sourceInput.url)
    : await generateScriptsFromFile(await resolveFilePathFromSourceInput(sourceInput));

  const resolvedOutputPath = outputPath
    ? path.resolve(outputPath)
    : buildDefaultOutputPath(sourceInput.scope, outputRoot);

  if (!resolvedOutputPath) {
    return { output };
  }

  await fs.mkdir(path.dirname(resolvedOutputPath), { recursive: true });
  await fs.writeFile(resolvedOutputPath, output, 'utf8');

  return { output: `Generated scripts saved to ${resolvedOutputPath}` };
}

async function executeCommand(mode: 'dry-run' | 'live', args: string[]): Promise<RunnerResult> {
  const filePath = await resolveExecutionFilePath(args);
  const operationId = await resolveOperationId(filePath, args);
  const variables = parseVariables(args);
  const baseUrlOverride = readArgument(args, '--base-url');
  const reportPath = readArgument(args, '--report');
  const reportFormat = parseReportFormat(readArgument(args, '--report-format'));
  const expectedStatus = parseExpectedStatus(readArgument(args, '--expect-status'));
  const bodyAssertions = parseBodyAssertions(args);
  const suiteName = readArgument(args, '--suite') || 'API Automation';
  const caseId = readArgument(args, '--case-id') || operationId;
  const artifactName = readArgument(args, '--artifact-name') || `${mode.toUpperCase()}_${normalizeArtifactName(caseId)}`;

  const output = mode === 'live'
    ? await executeScriptsLiveFromFile({ filePath, operationId, variables, baseUrlOverride })
    : await executeScriptsDryRunFromFile({ filePath, operationId, variables });

  if (reportPath) {
    const report = buildExecutionReport({
      mode,
      filePath,
      operationId,
      variables,
      suiteName,
      caseId,
      artifactName,
      expectedStatus,
      bodyAssertions,
      result: output,
    });
    const resolvedReportPath = path.resolve(reportPath);
    await fs.mkdir(path.dirname(resolvedReportPath), { recursive: true });
    const reportContent = reportFormat === 'json'
      ? JSON.stringify(report, null, 2)
      : reportFormat === 'html'
        ? renderHtmlReport(report)
        : renderMarkdownReport(report);
    await fs.writeFile(resolvedReportPath, reportContent, 'utf8');
  }

  return { output: JSON.stringify(output, null, 2) };
}

interface ExecutionReport {
  artifact: {
    id: string;
    name: string;
    suite: string;
    caseId: string;
    generatedAt: string;
    mode: 'dry-run' | 'live';
  };
  verdict: Verdict;
  expectation: {
    expectedStatus?: number;
    actualStatus?: number;
    statusCheck: StatusCheck;
    bodyAssertions: BodyAssertionResult[];
  };
  generatedAt: string;
  mode: 'dry-run' | 'live';
  source: {
    filePath: string;
    operationId: string;
  };
  request: {
    method: string;
    url: string;
  };
  variables: Record<string, string>;
  response?: {
    status: number;
    contentType?: string;
  };
}

function buildExecutionReport(input: {
  mode: 'dry-run' | 'live';
  filePath: string;
  operationId: string;
  variables: Record<string, string>;
  suiteName: string;
  caseId: string;
  artifactName: string;
  expectedStatus?: number;
  bodyAssertions: BodyAssertionInput[];
  result: Awaited<ReturnType<typeof executeScriptsDryRunFromFile>> | Awaited<ReturnType<typeof executeScriptsLiveFromFile>>;
}): ExecutionReport {
  const actualStatus = input.mode === 'live' && 'response' in input.result
    ? input.result.response.status
    : undefined;
  const statusCheck = evaluateStatusCheck(input.expectedStatus, actualStatus, input.mode);
  const bodyAssertionResults = evaluateBodyAssertions(input.bodyAssertions, input.result, input.mode);
  const verdict = deriveVerdict(statusCheck, bodyAssertionResults, input.mode);
  const generatedAt = new Date().toISOString();

  return {
    artifact: {
      id: createArtifactId(),
      name: input.artifactName,
      suite: input.suiteName,
      caseId: input.caseId,
      generatedAt,
      mode: input.mode,
    },
    verdict,
    expectation: {
      ...(typeof input.expectedStatus === 'number' ? { expectedStatus: input.expectedStatus } : {}),
      ...(typeof actualStatus === 'number' ? { actualStatus } : {}),
      statusCheck,
      bodyAssertions: bodyAssertionResults,
    },
    generatedAt,
    mode: input.mode,
    source: {
      filePath: input.filePath,
      operationId: input.operationId,
    },
    request: {
      method: input.result.request.method,
      url: input.result.request.url,
    },
    variables: input.variables,
    ...(input.mode === 'live' && 'response' in input.result ? {
      response: {
        status: input.result.response.status,
        contentType: input.result.response.contentType,
      },
    } : {}),
  };
}

function renderMarkdownReport(report: ExecutionReport): string {
  const variableEntries = Object.entries(report.variables);
  const variableLines = variableEntries.length === 0
    ? ['- none']
    : variableEntries.map(([key, value]) => `- ${key}: ${value}`);

  const expectationLine = typeof report.expectation.expectedStatus === 'number'
    ? `- Status Assertion: expected ${report.expectation.expectedStatus}, actual ${report.expectation.actualStatus ?? 'n/a'} (${report.expectation.statusCheck})`
    : '- Status Assertion: not provided';
  const bodyAssertionLines = report.expectation.bodyAssertions.length === 0
    ? ['- Body Assertions: none']
    : report.expectation.bodyAssertions.map((assertion) => {
      const actual = assertion.actual ?? 'n/a';
      return `- Body Assertion (${assertion.path}): expected ${assertion.expected}, actual ${actual} (${assertion.check})${assertion.message ? ` — ${assertion.message}` : ''}`;
    });

  const lines = [
    '# API Test Execution Artifact',
    '',
    `- Artifact ID: ${report.artifact.id}`,
    `- Artifact Name: ${report.artifact.name}`,
    `- Suite: ${report.artifact.suite}`,
    `- Case ID: ${report.artifact.caseId}`,
    `- Generated At: ${report.artifact.generatedAt}`,
    `- Mode: ${report.artifact.mode}`,
    `- Verdict: ${report.verdict}`,
    expectationLine,
    ...bodyAssertionLines,
    '',
    '## Source',
    '',
    `- Source File: ${report.source.filePath}`,
    `- Operation: ${report.source.operationId}`,
    '',
    '## Request',
    '',
    `- Method: ${report.request.method}`,
    `- URL: ${report.request.url}`,
    '',
    '## Variables',
    '',
    ...variableLines,
  ];

  if (report.response) {
    lines.push(
      '',
      '## Response',
      '',
      `- Status: ${report.response.status}`,
      `- Content-Type: ${report.response.contentType || 'unknown'}`,
    );
  }

  return `${lines.join('\n')}\n`;
}

function parseReportFormat(value: string | undefined): ReportFormat {
  if (!value) {
    return 'md';
  }

  if (value === 'md' || value === 'json' || value === 'html') {
    return value;
  }

  throw new Error('Invalid --report-format value. Use md, json, or html.');
}

function renderHtmlReport(report: ExecutionReport): string {
  const expectedStatus = typeof report.expectation.expectedStatus === 'number'
    ? String(report.expectation.expectedStatus)
    : 'none';
  const actualStatus = typeof report.expectation.actualStatus === 'number'
    ? String(report.expectation.actualStatus)
    : 'n/a';
  const bodyAssertionRows = report.expectation.bodyAssertions.length === 0
    ? '<tr><td colspan="5">none</td></tr>'
    : report.expectation.bodyAssertions
      .map((assertion) => `<tr><td>${escapeHtml(assertion.path)}</td><td>${escapeHtml(assertion.expected)}</td><td>${escapeHtml(assertion.actual ?? 'n/a')}</td><td>${escapeHtml(assertion.check)}</td><td>${escapeHtml(assertion.message ?? '')}</td></tr>`)
      .join('');

  const variableRows = Object.entries(report.variables)
    .map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(value)}</td></tr>`)
    .join('');

  const variablesTableBody = variableRows || '<tr><td colspan="2">none</td></tr>';

  const responseBlock = report.response
    ? `
      <section>
        <h2>Response</h2>
        <table>
          <tbody>
            <tr><th>Status</th><td>${report.response.status}</td></tr>
            <tr><th>Content-Type</th><td>${escapeHtml(report.response.contentType || 'unknown')}</td></tr>
          </tbody>
        </table>
      </section>
    `
    : '';

  const verdictClass = report.verdict === 'PASS'
    ? 'chip-pass'
    : report.verdict === 'FAIL'
      ? 'chip-fail'
      : 'chip-pending';

  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>API Test Execution Artifact</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f7f9fc;
        --surface: #ffffff;
        --text: #1e293b;
        --muted: #64748b;
        --line: #dbe3ef;
        --accent: #0f766e;
      }

      * { box-sizing: border-box; }

      body {
        margin: 0;
        background: radial-gradient(circle at top right, #e2f8f5 0%, var(--bg) 45%);
        color: var(--text);
        font-family: "Segoe UI", "Aptos", "Calibri", sans-serif;
        line-height: 1.45;
      }

      .wrap {
        max-width: 920px;
        margin: 32px auto;
        padding: 0 16px;
      }

      .card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 14px;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
        padding: 20px;
        margin-bottom: 14px;
      }

      h1 {
        margin: 0 0 8px;
        font-size: 28px;
      }

      h2 {
        margin: 0 0 10px;
        font-size: 18px;
      }

      .meta {
        color: var(--muted);
        font-size: 14px;
      }

      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
      }

      th, td {
        border-bottom: 1px solid var(--line);
        padding: 9px 8px;
        text-align: left;
        vertical-align: top;
      }

      th {
        width: 170px;
        color: var(--muted);
        font-weight: 600;
      }

      .chip {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
      }

      .chip-pass {
        border: 1px solid #86efac;
        color: #166534;
        background: #dcfce7;
      }

      .chip-fail {
        border: 1px solid #fecaca;
        color: #991b1b;
        background: #fee2e2;
      }

      .chip-pending {
        border: 1px solid #fde68a;
        color: #92400e;
        background: #fef3c7;
      }

      .url {
        word-break: break-all;
      }
    </style>
  </head>
  <body>
    <main class="wrap">
      <section class="card">
        <h1>API Test Execution Artifact</h1>
        <div class="meta">Generated at ${escapeHtml(report.artifact.generatedAt)}</div>
      </section>

      <section class="card">
        <h2>Execution Summary</h2>
        <table>
          <tbody>
            <tr><th>Artifact ID</th><td>${escapeHtml(report.artifact.id)}</td></tr>
            <tr><th>Artifact Name</th><td>${escapeHtml(report.artifact.name)}</td></tr>
            <tr><th>Suite</th><td>${escapeHtml(report.artifact.suite)}</td></tr>
            <tr><th>Case ID</th><td>${escapeHtml(report.artifact.caseId)}</td></tr>
            <tr><th>Mode</th><td><span class="chip chip-pending">${escapeHtml(report.mode)}</span></td></tr>
            <tr><th>Verdict</th><td><span class="chip ${verdictClass}">${escapeHtml(report.verdict)}</span></td></tr>
            <tr><th>Status Check</th><td>${escapeHtml(report.expectation.statusCheck)}</td></tr>
            <tr><th>Expected Status</th><td>${escapeHtml(expectedStatus)}</td></tr>
            <tr><th>Actual Status</th><td>${escapeHtml(actualStatus)}</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>Assertions</h2>
        <table>
          <thead>
            <tr><th>Path</th><th>Expected</th><th>Actual</th><th>Check</th><th>Message</th></tr>
          </thead>
          <tbody>
            ${bodyAssertionRows}
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>Source</h2>
        <table>
          <tbody>
            <tr><th>Source file</th><td>${escapeHtml(report.source.filePath)}</td></tr>
            <tr><th>Operation</th><td>${escapeHtml(report.source.operationId)}</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>Request</h2>
        <table>
          <tbody>
            <tr><th>Method</th><td>${escapeHtml(report.request.method)}</td></tr>
            <tr><th>URL</th><td class="url">${escapeHtml(report.request.url)}</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>Variables</h2>
        <table>
          <thead>
            <tr><th>Key</th><th>Value</th></tr>
          </thead>
          <tbody>
            ${variablesTableBody}
          </tbody>
        </table>
      </section>

      ${responseBlock}
    </main>
  </body>
</html>
`;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function parseExpectedStatus(value: string | undefined): number | undefined {
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 100 || parsed > 599) {
    throw new Error('Invalid --expect-status value. Use an HTTP status code between 100 and 599.');
  }

  return parsed;
}

function evaluateStatusCheck(
  expectedStatus: number | undefined,
  actualStatus: number | undefined,
  mode: 'dry-run' | 'live',
): StatusCheck {
  if (typeof expectedStatus !== 'number') {
    return 'not-provided';
  }

  if (mode === 'dry-run' || typeof actualStatus !== 'number') {
    return 'pending';
  }

  return expectedStatus === actualStatus ? 'pass' : 'fail';
}

function deriveVerdict(
  statusCheck: StatusCheck,
  bodyAssertions: BodyAssertionResult[],
  mode: 'dry-run' | 'live',
): Verdict {
  const hasBodyFailure = bodyAssertions.some((assertion) => assertion.check === 'fail');
  if (statusCheck === 'fail' || hasBodyFailure) {
    return 'FAIL';
  }

  const hasPendingBodyAssertion = bodyAssertions.some((assertion) => assertion.check === 'pending');
  if (mode === 'dry-run' || statusCheck === 'pending' || hasPendingBodyAssertion) {
    return 'NOT_EXECUTED';
  }

  return 'PASS';
}

function createArtifactId(): string {
  const timestamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
  const random = Math.random().toString(36).slice(2, 8).toUpperCase();
  return `ART-${timestamp}-${random}`;
}

function normalizeArtifactName(input: string): string {
  return input
    .trim()
    .replace(/\s+/g, '_')
    .replace(/[^a-zA-Z0-9_-]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
    .slice(0, 80) || 'operation';
}

async function resolveOperationId(filePath: string, args: string[]): Promise<string> {
  const exactOperationId = readArgument(args, '--operation');
  if (exactOperationId) {
    return exactOperationId;
  }

  const opSelector = readArgument(args, '--op');
  if (!opSelector) {
    throw new Error('Missing operation selector. Use --operation <exact-id> or --op <index|alias|text>.');
  }

  const content = await fs.readFile(filePath, 'utf8');
  const source = await loadApiSource({ filePath, content });
  const scripts = buildRequestScripts(source);
  const operations = buildOperationCatalog(scripts);

  const byAlias = operations.find((entry) => entry.alias.toLowerCase() === opSelector.toLowerCase());
  if (byAlias) {
    return byAlias.id;
  }

  if (/^\d+$/.test(opSelector)) {
    const index = Number(opSelector);
    const byIndex = operations.find((entry) => entry.index === index);
    if (byIndex) {
      return byIndex.id;
    }
  }

  const normalizedSelector = opSelector.toLowerCase();
  const matches = operations.filter((entry) => entry.id.toLowerCase().includes(normalizedSelector));
  if (matches.length === 1) {
    return matches[0].id;
  }

  if (matches.length > 1) {
    const preview = matches.slice(0, 5).map((entry) => `${entry.alias} -> ${entry.id}`).join(', ');
    throw new Error(`Selector '${opSelector}' matched multiple operations. Try --op <index|alias> instead. Matches: ${preview}`);
  }

  throw new Error(`Operation not found for selector '${opSelector}'. Run inspect to list available operations.`);
}

function buildOperationCatalog(
  scripts: Array<{ id: string; request: { method: string; url: string } }>,
): OperationCatalogEntry[] {
  return scripts.map((script, index) => ({
    index: index + 1,
    alias: `op-${String(index + 1).padStart(3, '0')}`,
    id: script.id,
    method: script.request.method,
    url: script.request.url,
  }));
}

interface LoadedSource {
  source: Awaited<ReturnType<typeof loadApiSource>>;
}

async function loadSourceFromArgs(args: string[]): Promise<LoadedSource> {
  const sourceInput = readSourceInput(args);

  if (!sourceInput.filePath && !sourceInput.url && !sourceInput.scope) {
    throw new Error('Missing source. Use --url, --file, or --brand/--adapter/--api.');
  }

  if (sourceInput.url) {
    const loaded = await loadApiSourceFromUrl(sourceInput.url);
    return { source: loaded.source };
  }

  const resolvedPath = await resolveFilePathFromSourceInput(sourceInput);
  const content = await fs.readFile(resolvedPath, 'utf8');
  const source = await loadApiSource({ filePath: resolvedPath, content });
  return { source };
}

interface SourceInput {
  filePath?: string;
  url?: string;
  scope?: FolderScope;
}

function readSourceInput(args: string[]): SourceInput {
  return {
    filePath: readArgument(args, '--file'),
    url: readArgument(args, '--url'),
    scope: readFolderScope(args),
  };
}

function readFolderScope(args: string[]): FolderScope | undefined {
  const brand = readArgument(args, '--brand');
  const adapter = readArgument(args, '--adapter');
  const api = readArgument(args, '--api');
  const sourceRoot = readArgument(args, '--source-root');

  if (!brand && !adapter && !api) {
    return undefined;
  }

  if (!api) {
    throw new Error('When using folder mode, provide --api. Optional: --brand, --adapter.');
  }

  return {
    brand: brand || DEFAULT_BRAND,
    adapter: adapter || DEFAULT_ADAPTER,
    api,
    sourceRoot,
  };
}

async function resolveExecutionFilePath(args: string[]): Promise<string> {
  const filePath = readArgument(args, '--file');
  if (filePath) {
    return path.resolve(filePath);
  }

  const scope = readFolderScope(args);
  if (!scope) {
    throw new Error('Missing source. Use --file <path> or --brand/--adapter/--api.');
  }

  return resolveFilePathFromScope(scope);
}

async function resolveFilePathFromSourceInput(input: SourceInput): Promise<string> {
  if (input.filePath) {
    return path.resolve(input.filePath);
  }

  if (!input.scope) {
    throw new Error('Expected source file or folder scope.');
  }

  return resolveFilePathFromScope(input.scope);
}

async function resolveFilePathFromScope(scope: FolderScope): Promise<string> {
  const sourceRoot = path.resolve(scope.sourceRoot || 'fixtures');
  const apiFolder = path.join(sourceRoot, scope.brand, scope.adapter, 'apis');
  const extension = path.extname(scope.api);

  const candidates = extension
    ? [path.join(apiFolder, scope.api)]
    : [
      path.join(apiFolder, `${scope.api}.yaml`),
      path.join(apiFolder, `${scope.api}.yml`),
      path.join(apiFolder, `${scope.api}.json`),
    ];

  for (const candidate of candidates) {
    if (await fileExists(candidate)) {
      return candidate;
    }
  }

  throw new Error(`API source not found for ${scope.brand}/${scope.adapter}/${scope.api}. Checked: ${candidates.join(', ')}`);
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function buildDefaultOutputPath(scope: FolderScope | undefined, outputRoot: string): string | undefined {
  if (!scope) {
    return undefined;
  }

  const baseName = path.basename(scope.api, path.extname(scope.api));
  return path.resolve(outputRoot, scope.brand, scope.adapter, 'apis', `${baseName}.scripts.json`);
}

function readRequiredArgument(args: string[], flag: string): string {
  const value = readArgument(args, flag);
  if (!value) {
    throw new Error(`Missing required ${flag} argument`);
  }

  return value;
}

function readArgument(args: string[], flag: string): string | undefined {
  const index = args.findIndex((entry) => entry === flag);
  if (index === -1 || !args[index + 1]) {
    return undefined;
  }

  return args[index + 1];
}

function parseVariables(args: string[]): Record<string, string> {
  const variables: Record<string, string> = {};

  for (let index = 0; index < args.length; index += 1) {
    if (args[index] !== '--var' || !args[index + 1]) {
      continue;
    }

    const [key, ...valueParts] = args[index + 1].split('=');
    if (!key || valueParts.length === 0) {
      throw new Error(`Invalid --var value: ${args[index + 1]}`);
    }

    variables[key] = valueParts.join('=');
  }

  return variables;
}

function parseBodyAssertions(args: string[]): BodyAssertionInput[] {
  const values = readArguments(args, '--assert-body');
  return values.map((value) => {
    const equalsIndex = value.indexOf('=');
    if (equalsIndex <= 0 || equalsIndex === value.length - 1) {
      throw new Error(`Invalid --assert-body value: ${value}. Use <json.path>=<expected>.`);
    }

    const pathValue = value.slice(0, equalsIndex).trim();
    const expectedRaw = value.slice(equalsIndex + 1).trim();
    if (!pathValue || !expectedRaw) {
      throw new Error(`Invalid --assert-body value: ${value}. Use <json.path>=<expected>.`);
    }

    return {
      path: pathValue,
      expectedRaw,
      expectedValue: parseExpectedBodyValue(expectedRaw),
    };
  });
}

function parseExpectedBodyValue(value: string): unknown {
  if (value === 'true') return true;
  if (value === 'false') return false;
  if (value === 'null') return null;

  if (/^-?\d+(\.\d+)?$/.test(value)) {
    return Number(value);
  }

  if (
    (value.startsWith('{') && value.endsWith('}'))
    || (value.startsWith('[') && value.endsWith(']'))
    || (value.startsWith('"') && value.endsWith('"'))
  ) {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  return value;
}

function evaluateBodyAssertions(
  assertions: BodyAssertionInput[],
  result: Awaited<ReturnType<typeof executeScriptsDryRunFromFile>> | Awaited<ReturnType<typeof executeScriptsLiveFromFile>>,
  mode: 'dry-run' | 'live',
): BodyAssertionResult[] {
  if (assertions.length === 0) {
    return [];
  }

  if (mode === 'dry-run' || !(mode === 'live' && 'response' in result)) {
    return assertions.map((assertion) => ({
      path: assertion.path,
      expected: stringifyForReport(assertion.expectedValue),
      check: 'pending',
      message: 'Body is only available in live mode.',
    }));
  }

  return assertions.map((assertion) => {
    const resolved = getValueByPath(result.response.body, assertion.path);
    if (!resolved.found) {
      return {
        path: assertion.path,
        expected: stringifyForReport(assertion.expectedValue),
        check: 'fail',
        message: `Path '${assertion.path}' not found in response body.`,
      };
    }

    const expected = assertion.expectedValue;
    const actual = resolved.value;
    const matches = deepEqual(expected, actual);
    return {
      path: assertion.path,
      expected: stringifyForReport(expected),
      actual: stringifyForReport(actual),
      check: matches ? 'pass' : 'fail',
      ...(matches ? {} : { message: 'Actual value does not match expected value.' }),
    };
  });
}

function getValueByPath(source: unknown, pathValue: string): { found: boolean; value?: unknown } {
  const segments = tokenizePath(pathValue);
  let current: unknown = source;

  for (const segment of segments) {
    if (typeof segment === 'number') {
      if (!Array.isArray(current) || segment < 0 || segment >= current.length) {
        return { found: false };
      }
      current = current[segment];
      continue;
    }

    if (current === null || typeof current !== 'object' || !(segment in current)) {
      return { found: false };
    }

    current = (current as Record<string, unknown>)[segment];
  }

  return { found: true, value: current };
}

function tokenizePath(pathValue: string): Array<string | number> {
  const normalized = pathValue.replace(/\[(\d+)\]/g, '.$1');
  return normalized
    .split('.')
    .filter((segment) => segment.length > 0)
    .map((segment) => (/^\d+$/.test(segment) ? Number(segment) : segment));
}

function deepEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function stringifyForReport(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }

  return JSON.stringify(value);
}

function readArguments(args: string[], flag: string): string[] {
  const values: string[] = [];
  for (let index = 0; index < args.length; index += 1) {
    if (args[index] === flag && args[index + 1]) {
      values.push(args[index + 1]);
      index += 1;
    }
  }

  return values;
}

function buildHelpText(): string {
  return [
    'API Automation Framework',
    `Default scope: ${DEFAULT_BRAND}/${DEFAULT_ADAPTER}/apis`,
    '',
    'Commands:',
    '  help',
    '  inspect --url <value> | --file <path> | --api <name> [--brand <brand>] [--adapter <adapter>]',
    '  generate --url <value> | --file <path> | --api <name> [--brand <brand>] [--adapter <adapter>] [--out <path>] [--output-root <path>]',
    '  dry-run (--file <path> | --api <name> [--brand <brand>] [--adapter <adapter>]) (--operation <id> | --op <index|alias|text>) [--var key=value]... [--expect-status <code>] [--assert-body <json.path>=<expected>]... [--suite <name>] [--case-id <id>] [--artifact-name <name>] [--report <path>] [--report-format md|json|html]',
    '  run (--file <path> | --api <name> [--brand <brand>] [--adapter <adapter>]) (--operation <id> | --op <index|alias|text>) [--var key=value]... [--base-url <value>] [--expect-status <code>] [--assert-body <json.path>=<expected>]... [--suite <name>] [--case-id <id>] [--artifact-name <name>] [--report <path>] [--report-format md|json|html]',
    '',
    'Examples:',
    '  npm run framework -- inspect --api orders-detailed',
    '  npm run framework -- generate --api orders-detailed',
    '  npm run framework -- dry-run --api orders-detailed --op 1 --var brandId=Brand Four --var orderId=ORDER-123',
    '  npm run framework -- run --file C:/path/to/collection.json --op op-002 --var brand=Brand Four --var lmsProfileId=123456',
    '  npm run framework -- run --file C:/path/to/collection.json --op op-002 --var brand=Brand Four --var lmsProfileId=123456 --expect-status 503 --assert-body errors.0.code=L08521 --assert-body errors.0.reasonCode=LA_EPSILON_CIRCUIT_OPEN --suite Loyalty-Adapter --case-id PROJ2-14359-2 --artifact-name epsilon-open-getProfile --report reports/op-002.html --report-format html',
    '  npm run framework -- generate --file C:/path/to/postman-collection.json --out output/brand4/loyalty-adapter/apis/collection.scripts.json',
  ].join('\n');
}

async function main(): Promise<void> {
  const { output } = await runFrameworkCli(process.argv.slice(2));
  process.stdout.write(`${output}\n`);
}

if (require.main === module) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}
