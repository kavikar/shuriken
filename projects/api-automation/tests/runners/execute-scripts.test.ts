import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test, { after } from 'node:test';

import { executeScriptsDryRunFromFile, executeScriptsLiveFromFile } from '../../src/runners/execute-scripts';

const projectRoot = path.resolve(__dirname, '..', '..');
const servers: http.Server[] = [];

after(async () => {
  await Promise.all(servers.map((server) => new Promise<void>((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }

      resolve();
    });
  })));
});

test('prepares a dry-run execution request for a selected OpenAPI operation', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'orders-detailed.yaml');

  const output = await executeScriptsDryRunFromFile({
    filePath,
    operationId: 'getOrder',
    variables: {
      brandId: 'Brand Four',
      orderId: 'ORDER-123',
      includeDetails: 'true',
    },
  });

  assert.deepEqual(output, {
    mode: 'dry-run',
    source: {
      filePath,
      operationId: 'getOrder',
    },
    request: {
      method: 'GET',
      url: 'https://orders.example.com/api/brands/brand4/orders/ORDER-123?includeDetails=true',
      security: [
        { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
      ],
    },
  });
});

test('prepares a dry-run execution request body from an OpenAPI example', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'orders-detailed.yaml');

  const output = await executeScriptsDryRunFromFile({
    filePath,
    operationId: 'createOrder',
    variables: {
      brandId: 'Brand Four',
    },
  });

  assert.deepEqual(output, {
    mode: 'dry-run',
    source: {
      filePath,
      operationId: 'createOrder',
    },
    request: {
      method: 'POST',
      url: 'https://orders.example.com/api/brands/brand4/orders',
      body: {
        contentType: 'application/json',
        value: {
          itemId: 'ITEM-100',
          quantity: 2,
        },
      },
      security: [
        { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
      ],
    },
  });
});

test('rejects a dry-run request when a required path variable is missing', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'orders-detailed.yaml');

  await assert.rejects(
    executeScriptsDryRunFromFile({
      filePath,
      operationId: 'getOrder',
      variables: {
        brandId: 'Brand Four',
      },
    }),
    /Missing required variable: orderId/,
  );
});

test('executes a prepared OpenAPI request against a live endpoint', async () => {
  const requests: Array<{ method?: string; url?: string; body: string }> = [];
  const server = http.createServer((request, response) => {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => {
      body += chunk;
    });
    request.on('end', () => {
      requests.push({
        method: request.method,
        url: request.url,
        body,
      });

      response.writeHead(201, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ ok: true, received: true }));
    });
  });

  servers.push(server);

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Expected server to listen on a dynamic port');
  }

  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'orders-detailed.yaml');
  const output = await executeScriptsLiveFromFile({
    filePath,
    operationId: 'createOrder',
    variables: {
      brandId: 'Brand Four',
    },
    baseUrlOverride: `http://127.0.0.1:${address.port}`,
  });

  assert.deepEqual(requests, [
    {
      method: 'POST',
      url: '/brands/brand4/orders',
      body: '{"itemId":"ITEM-100","quantity":2}',
    },
  ]);

  assert.deepEqual(output, {
    mode: 'live',
    source: {
      filePath,
      operationId: 'createOrder',
    },
    request: {
      method: 'POST',
      url: `http://127.0.0.1:${address.port}/brands/brand4/orders`,
      body: {
        contentType: 'application/json',
        value: {
          itemId: 'ITEM-100',
          quantity: 2,
        },
      },
      security: [
        { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
      ],
    },
    response: {
      status: 201,
      contentType: 'application/json',
      body: {
        ok: true,
        received: true,
      },
    },
  });
});

test('substitutes Postman-style URL variables in dry-run execution', async () => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'api-automation-postman-vars-'));
  const filePath = path.join(tempDir, 'postman-vars-collection.json');

  await fs.writeFile(filePath, JSON.stringify({
    info: {
      name: 'Postman Vars Collection',
      schema: 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
    },
    variable: [
      {
        key: 'baseUrl',
        value: 'https://example.test',
      },
    ],
    item: [
      {
        name: 'Profile',
        request: {
          method: 'GET',
          url: {
            path: ['loyalty', 'v4', 'brand', '{{brand}}', 'profiles', '{{lmsProfileId}}'],
          },
        },
      },
    ],
  }, null, 2), 'utf8');

  const output = await executeScriptsDryRunFromFile({
    filePath,
    operationId: 'Profile',
    variables: {
      brand: 'Brand Four',
      lmsProfileId: '12345',
    },
  });

  assert.deepEqual(output, {
    mode: 'dry-run',
    source: {
      filePath,
      operationId: 'Profile',
    },
    request: {
      method: 'GET',
      url: 'https://example.test/loyalty/v4/brand/brand4/profiles/12345',
    },
  });
});