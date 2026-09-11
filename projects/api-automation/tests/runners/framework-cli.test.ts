import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { runFrameworkCli } from '../../src/runners/framework-cli';

const projectRoot = path.resolve(__dirname, '..', '..');

test('prints user-friendly help when no command is provided', async () => {
  const result = await runFrameworkCli([]);

  assert.match(result.output, /API Automation Framework/);
  assert.match(result.output, /Commands:/);
  assert.match(result.output, /inspect/);
  assert.match(result.output, /dry-run/);
  assert.match(result.output, /Default scope: Brand Four\/loyalty-adapter\/apis/);
});

test('inspects operations from an OpenAPI file', async () => {
  const result = await runFrameworkCli([
    'inspect',
    '--api',
    'orders-detailed',
  ]);

  assert.match(result.output, /Source: Orders API \(openapi\)/);
  assert.match(result.output, /Operations: 2/);
  assert.match(result.output, /01\. op-001 \| GET https:\/\/orders.example.com\/api\/brands\/{brandId}\/orders\/{orderId}/);
});

test('generates scripts in folder mode and writes to the default output structure', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-'));
  const outputFile = path.join(tempDir, 'brand4', 'loyalty-adapter', 'apis', 'ping-collection.scripts.json');

  const result = await runFrameworkCli([
    'generate',
    '--api',
    'ping-collection',
    '--output-root',
    tempDir,
  ]);

  const saved = await fs.readFile(outputFile, 'utf8');
  const parsed = JSON.parse(saved) as {
    source: { kind: string; name: string };
    scripts: Array<{ id: string }>;
  };

  assert.match(result.output, /Generated scripts saved to/);
  assert.equal(parsed.source.kind, 'postman');
  assert.equal(parsed.source.name, 'Ping API Collection');
  assert.equal(parsed.scripts[0]?.id, 'Health.Get Health');
});

test('runs dry-run execution through the friendly command surface', async () => {
  const result = await runFrameworkCli([
    'dry-run',
    '--api',
    'orders-detailed',
    '--op',
    '1',
    '--var',
    'brandId=Brand Four',
    '--var',
    'orderId=ORDER-123',
  ]);

  const parsed = JSON.parse(result.output) as {
    mode: string;
    request: { method: string; url: string };
  };

  assert.equal(parsed.mode, 'dry-run');
  assert.equal(parsed.request.method, 'GET');
  assert.equal(parsed.request.url, 'https://orders.example.com/api/brands/brand4/orders/ORDER-123');
});

test('supports dry-run operation selection by alias', async () => {
  const result = await runFrameworkCli([
    'dry-run',
    '--api',
    'orders-detailed',
    '--op',
    'op-002',
    '--var',
    'brandId=Brand Four',
  ]);

  const parsed = JSON.parse(result.output) as {
    mode: string;
    request: { method: string; url: string };
  };

  assert.equal(parsed.mode, 'dry-run');
  assert.equal(parsed.request.method, 'POST');
  assert.equal(parsed.request.url, 'https://orders.example.com/api/brands/brand4/orders');
});

test('writes a markdown report for dry-run execution', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-report-md-'));
  const reportPath = path.join(tempDir, 'report.md');

  await runFrameworkCli([
    'dry-run',
    '--api',
    'orders-detailed',
    '--op',
    '1',
    '--var',
    'brandId=Brand Four',
    '--var',
    'orderId=ORDER-123',
    '--expect-status',
    '200',
    '--suite',
    'Orders Regression',
    '--case-id',
    'ORD-GET-001',
    '--artifact-name',
    'orders_get_order_dry_run',
    '--report',
    reportPath,
  ]);

  const report = await fs.readFile(reportPath, 'utf8');
  assert.match(report, /# API Test Execution Artifact/);
  assert.match(report, /Mode: dry-run/);
  assert.match(report, /Suite: Orders Regression/);
  assert.match(report, /Case ID: ORD-GET-001/);
  assert.match(report, /Verdict: NOT_EXECUTED/);
  assert.match(report, /Status Assertion: expected 200, actual n\/a \(pending\)/);
  assert.match(report, /Operation: getOrder/);
  assert.match(report, /Method: GET/);
});

test('writes a json report when report format is json', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-report-json-'));
  const reportPath = path.join(tempDir, 'report.json');

  await runFrameworkCli([
    'dry-run',
    '--api',
    'orders-detailed',
    '--op',
    '1',
    '--var',
    'brandId=Brand Four',
    '--var',
    'orderId=ORDER-123',
    '--report',
    reportPath,
    '--report-format',
    'json',
  ]);

  const report = JSON.parse(await fs.readFile(reportPath, 'utf8')) as {
    mode: string;
    verdict: string;
    artifact: { suite: string; caseId: string; name: string; id: string };
    expectation: { statusCheck: string; expectedStatus?: number; actualStatus?: number };
    request: { method: string; url: string };
    source: { operationId: string };
  };

  assert.equal(report.mode, 'dry-run');
  assert.equal(report.verdict, 'NOT_EXECUTED');
  assert.equal(report.artifact.suite, 'API Automation');
  assert.equal(report.artifact.caseId, 'getOrder');
  assert.match(report.artifact.id, /^ART-/);
  assert.equal(report.expectation.statusCheck, 'not-provided');
  assert.equal(report.expectation.expectedStatus, undefined);
  assert.equal(report.expectation.actualStatus, undefined);
  assert.equal(report.source.operationId, 'getOrder');
  assert.equal(report.request.method, 'GET');
  assert.equal(report.request.url, 'https://orders.example.com/api/brands/brand4/orders/ORDER-123');
});

test('writes an html report when report format is html', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-report-html-'));
  const reportPath = path.join(tempDir, 'report.html');

  await runFrameworkCli([
    'dry-run',
    '--api',
    'orders-detailed',
    '--op',
    '1',
    '--var',
    'brandId=Brand Four',
    '--var',
    'orderId=ORDER-123',
    '--report',
    reportPath,
    '--report-format',
    'html',
  ]);

  const report = await fs.readFile(reportPath, 'utf8');
  assert.match(report, /<!doctype html>/i);
  assert.match(report, /<h1>API Test Execution Artifact<\/h1>/);
  assert.match(report, /Execution Summary<\/h2>/);
  assert.match(report, /Verdict<\/th><td><span class="chip chip-pending">NOT_EXECUTED<\/span><\/td>/);
  assert.match(report, /Operation<\/th><td>getOrder<\/td>/);
  assert.match(report, /https:\/\/orders.example.com\/api\/brands\/Brand Four\/orders\/ORDER-123/);
});

test('passes response body assertions for live run and reports PASS verdict', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-body-assert-pass-'));
  const reportPath = path.join(tempDir, 'report.json');

  const server = http.createServer((_request, response) => {
    response.writeHead(503, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({
      errors: [
        {
          code: 'L08521',
          reasonCode: 'LA_EPSILON_CIRCUIT_OPEN',
        },
      ],
    }));
  });

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const address = server.address();
  if (!address || typeof address === 'string') {
    server.close();
    throw new Error('Expected server to be available on dynamic port');
  }

  try {
    await runFrameworkCli([
      'run',
      '--api',
      'orders-detailed',
      '--op',
      '1',
      '--var',
      'brandId=Brand Four',
      '--var',
      'orderId=ORDER-123',
      '--base-url',
      `http://127.0.0.1:${address.port}`,
      '--expect-status',
      '503',
      '--assert-body',
      'errors.0.code=L08521',
      '--assert-body',
      'errors.0.reasonCode=LA_EPSILON_CIRCUIT_OPEN',
      '--report',
      reportPath,
      '--report-format',
      'json',
    ]);
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  const report = JSON.parse(await fs.readFile(reportPath, 'utf8')) as {
    verdict: string;
    expectation: {
      statusCheck: string;
      bodyAssertions: Array<{ path: string; check: string; expected: string; actual?: string }>;
    };
  };

  assert.equal(report.verdict, 'PASS');
  assert.equal(report.expectation.statusCheck, 'pass');
  assert.deepEqual(report.expectation.bodyAssertions, [
    {
      path: 'errors.0.code',
      expected: 'L08521',
      actual: 'L08521',
      check: 'pass',
    },
    {
      path: 'errors.0.reasonCode',
      expected: 'LA_EPSILON_CIRCUIT_OPEN',
      actual: 'LA_EPSILON_CIRCUIT_OPEN',
      check: 'pass',
    },
  ]);
});

test('fails response body assertions when actual response does not match expected', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-body-assert-fail-'));
  const reportPath = path.join(tempDir, 'report.md');

  const server = http.createServer((_request, response) => {
    response.writeHead(503, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({
      errors: [
        {
          code: 'L08524',
        },
      ],
    }));
  });

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const address = server.address();
  if (!address || typeof address === 'string') {
    server.close();
    throw new Error('Expected server to be available on dynamic port');
  }

  try {
    await runFrameworkCli([
      'run',
      '--api',
      'orders-detailed',
      '--op',
      '1',
      '--var',
      'brandId=Brand Four',
      '--var',
      'orderId=ORDER-123',
      '--base-url',
      `http://127.0.0.1:${address.port}`,
      '--expect-status',
      '503',
      '--assert-body',
      'errors.0.code=L08521',
      '--report',
      reportPath,
    ]);
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }

  const report = await fs.readFile(reportPath, 'utf8');
  assert.match(report, /Verdict: FAIL/);
  assert.match(report, /Body Assertion \(errors.0.code\): expected L08521, actual L08524 \(fail\)/);
});

test('validates expect-status input with a clear error', async () => {
  await assert.rejects(
    runFrameworkCli([
      'dry-run',
      '--api',
      'orders-detailed',
      '--op',
      '1',
      '--expect-status',
      'abc',
    ]),
    /Invalid --expect-status value/,
  );
});

test('returns a clear error for unknown commands', async () => {
  await assert.rejects(
    runFrameworkCli(['unknown-command']),
    /Unknown command: unknown-command/,
  );
});
