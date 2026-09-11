import fs from 'node:fs/promises';
import path from 'node:path';

type NewmanFailure = {
  source?: { name?: string };
};

type NewmanExecution = {
  item?: { name?: string };
  response?: {
    code?: number;
    stream?: { data?: number[] };
  };
};

type NewmanReport = {
  run?: {
    stats?: {
      assertions?: {
        total?: number;
        failed?: number;
      };
    };
    failures?: NewmanFailure[];
    executions?: NewmanExecution[];
  };
};

type StatusCategory = 'DEFECT' | 'DATA_ISSUE' | 'ROUTE_ISSUE' | 'OTHER';

type FailureRow = {
  request: string;
  status: number | null;
  category: StatusCategory;
  reason: string;
  bodySnippet: string;
};

function readArg(argv: string[], flag: string): string | undefined {
  const idx = argv.indexOf(flag);
  if (idx === -1) return undefined;
  return argv[idx + 1];
}

function getLatestReportDir(baseDir: string): Promise<string> {
  return fs.readdir(baseDir, { withFileTypes: true }).then((entries) => {
    const dirs = entries
      .filter((e) => e.isDirectory() && e.name.startsWith('newman-epsilon-open-'))
      .map((e) => e.name)
      .sort((a, b) => b.localeCompare(a));

    if (dirs.length === 0) {
      throw new Error(`No newman epsilon report directories found in: ${baseDir}`);
    }

    return path.join(baseDir, dirs[0]);
  });
}

function decodeResponseBody(execution: NewmanExecution | undefined): string {
  const data = execution?.response?.stream?.data;
  if (!data || data.length === 0) return '';

  try {
    return Buffer.from(data).toString('utf8');
  } catch {
    return '';
  }
}

function parseReason(body: string): string {
  if (!body.trim()) return 'Empty response body';

  try {
    const parsed = JSON.parse(body) as {
      errorMessage?: string;
      errors?: Array<{ message?: string }>;
    };

    if (parsed.errors?.[0]?.message) return sanitizeReason(parsed.errors[0].message);
    if (parsed.errorMessage) return sanitizeReason(parsed.errorMessage);
  } catch {
    return 'Non-JSON response body';
  }

  return 'No explicit error message in body';
}

function sanitizeReason(reason: string): string {
  const firstLine = reason.split('\n')[0] || reason;
  const beforeStack = firstLine.split(': org.springframework')[0] || firstLine;
  return beforeStack.replace(/\s+/g, ' ').trim();
}

function classify(status: number | null, reason: string): StatusCategory {
  if (status === 200) return 'DEFECT';
  if (status === 404) return 'ROUTE_ISSUE';
  if (status === 400) return 'DATA_ISSUE';

  if (/validation|required|must not be null|field error/i.test(reason)) {
    return 'DATA_ISSUE';
  }

  return 'OTHER';
}

function renderMarkdownSummary(input: {
  reportPath: string;
  totalExecutions: number;
  totalAssertions: number;
  failedAssertions: number;
  rows: FailureRow[];
}): string {
  const byStatus = new Map<string, number>();
  const byCategory = new Map<string, number>();

  for (const row of input.rows) {
    const statusKey = String(row.status ?? 'null');
    byStatus.set(statusKey, (byStatus.get(statusKey) || 0) + 1);
    byCategory.set(row.category, (byCategory.get(row.category) || 0) + 1);
  }

  const lines: string[] = [];
  lines.push('# Epsilon Open Newman Summary');
  lines.push('');
  lines.push('## Totals');
  lines.push(`- Report: ${input.reportPath}`);
  lines.push(`- Executions: ${input.totalExecutions}`);
  lines.push(`- Assertions: ${input.totalAssertions}`);
  lines.push(`- Failed assertions: ${input.failedAssertions}`);
  lines.push(`- Failed requests: ${input.rows.length}`);
  lines.push('');

  lines.push('## Failed by Status');
  const sortedStatus = [...byStatus.entries()].sort((a, b) => Number(a[0]) - Number(b[0]));
  for (const [status, count] of sortedStatus) {
    lines.push(`- ${status}: ${count}`);
  }
  lines.push('');

  lines.push('## Failed by Category');
  for (const [category, count] of byCategory.entries()) {
    lines.push(`- ${category}: ${count}`);
  }
  lines.push('');

  lines.push('## Failure Details');
  lines.push('| Request | Status | Category | Reason |');
  lines.push('|---|---:|---|---|');
  for (const row of input.rows) {
    const safeReason = row.reason.replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim().slice(0, 180);
    lines.push(`| ${row.request} | ${row.status ?? 'n/a'} | ${row.category} | ${safeReason} |`);
  }
  lines.push('');

  lines.push('## Suggested Next Actions');
  lines.push('- DEFECT: circuit-open assertion expected 503 but endpoint returned 200.');
  lines.push('- ROUTE_ISSUE: endpoint path does not exist in current environment (404).');
  lines.push('- DATA_ISSUE: payload/query contract mismatch; validate required fields and enums.');

  return lines.join('\n');
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const explicitReportPath = readArg(args, '--report');
  const outputPath = readArg(args, '--output');
  const baseDir = path.resolve(
    readArg(args, '--base-dir') || './reports/brand4/loyalty-adapter',
  );

  const reportDir = explicitReportPath
    ? path.dirname(path.resolve(explicitReportPath))
    : await getLatestReportDir(baseDir);

  const reportPath = explicitReportPath
    ? path.resolve(explicitReportPath)
    : path.join(reportDir, 'newman-report.json');

  const raw = await fs.readFile(reportPath, 'utf8');
  const report = JSON.parse(raw) as NewmanReport;

  const executions = report.run?.executions || [];
  const failureNames = [
    ...new Set((report.run?.failures || []).map((f) => f.source?.name).filter(Boolean) as string[]),
  ];

  const rows: FailureRow[] = failureNames
    .map((name) => {
      const execution = executions.find((e) => e.item?.name === name);
      const body = decodeResponseBody(execution);
      const reason = parseReason(body);
      const status = execution?.response?.code ?? null;

      return {
        request: name,
        status,
        category: classify(status, reason),
        reason,
        bodySnippet: body.replace(/\s+/g, ' ').trim().slice(0, 180),
      };
    })
    .sort((a, b) => a.request.localeCompare(b.request, undefined, { numeric: true }));

  const summary = renderMarkdownSummary({
    reportPath,
    totalExecutions: executions.length,
    totalAssertions: report.run?.stats?.assertions?.total || 0,
    failedAssertions: report.run?.stats?.assertions?.failed || 0,
    rows,
  });

  const resolvedOutput = outputPath
    ? path.resolve(outputPath)
    : path.join(reportDir, 'epsilon-open-summary.md');
  const jsonOutputPath = resolvedOutput.replace(/\.md$/i, '.json');

  await fs.writeFile(resolvedOutput, summary, 'utf8');
  await fs.writeFile(
    jsonOutputPath,
    JSON.stringify(
      {
        reportPath,
        totalExecutions: executions.length,
        totalAssertions: report.run?.stats?.assertions?.total || 0,
        failedAssertions: report.run?.stats?.assertions?.failed || 0,
        failedRequests: rows.length,
        rows,
      },
      null,
      2,
    ),
    'utf8',
  );

  process.stdout.write(`Summary generated: ${resolvedOutput}\n`);
  process.stdout.write(`JSON generated: ${jsonOutputPath}\n`);
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
