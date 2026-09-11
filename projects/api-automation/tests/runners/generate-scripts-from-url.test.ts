import assert from 'node:assert/strict';
import http from 'node:http';
import test, { after } from 'node:test';

import { generateScriptsFromUrl } from '../../src/runners/generate-scripts';

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

test('generates request scripts from a Swagger UI URL', async () => {
  const server = http.createServer((request, response) => {
    if (request.url === '/swagger-ui/index.html') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(`
        <html>
          <body>
            <a href="/v3/api-docs">/v3/api-docs</a>
          </body>
        </html>
      `);
      return;
    }

    if (request.url === '/v3/api-docs') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({
        openapi: '3.1.0',
        info: {
          title: 'Swagger Sample',
          version: 'v0',
        },
        servers: [
          { url: 'https://example.test' },
        ],
        paths: {
          '/customers': {
            get: {
              operationId: 'listCustomers',
              summary: 'List customers',
            },
          },
        },
      }));
      return;
    }

    response.writeHead(404);
    response.end();
  });

  servers.push(server);

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Expected server to listen on a dynamic port');
  }

  const output = await generateScriptsFromUrl(`http://127.0.0.1:${address.port}/swagger-ui/index.html#/`);
  const document = JSON.parse(output) as {
    source: { kind: string; name: string; resolvedFrom?: string };
    scripts: Array<{ id: string; request: { method: string; url: string } }>;
  };

  assert.equal(document.source.kind, 'openapi');
  assert.equal(document.source.name, 'Swagger Sample');
  assert.equal(document.source.resolvedFrom, '/v3/api-docs');
  assert.deepEqual(document.scripts, [
    {
      id: 'listCustomers',
      name: 'List customers',
      request: {
        method: 'GET',
        url: 'https://example.test/customers',
      },
    },
  ]);
});

test('falls back to standard OpenAPI endpoints when Swagger UI does not expose a direct link', async () => {
  const server = http.createServer((request, response) => {
    if (request.url === '/swagger-ui/index.html') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(`
        <html>
          <body>
            <div id="swagger-ui"></div>
            <script src="./swagger-ui-bundle.js"></script>
          </body>
        </html>
      `);
      return;
    }

    if (request.url === '/v3/api-docs') {
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({
        openapi: '3.1.0',
        info: {
          title: 'Fallback Swagger Sample',
          version: 'v1',
        },
        servers: [
          { url: 'https://fallback.example.test' },
        ],
        paths: {
          '/status': {
            get: {
              operationId: 'getStatus',
              summary: 'Get status',
            },
          },
        },
      }));
      return;
    }

    response.writeHead(404);
    response.end();
  });

  servers.push(server);

  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve());
  });

  const address = server.address();
  if (!address || typeof address === 'string') {
    throw new Error('Expected server to listen on a dynamic port');
  }

  const output = await generateScriptsFromUrl(`http://127.0.0.1:${address.port}/swagger-ui/index.html#/`);
  const document = JSON.parse(output) as {
    source: { kind: string; name: string; resolvedFrom?: string };
    scripts: Array<{ id: string; request: { method: string; url: string } }>;
  };

  assert.equal(document.source.kind, 'openapi');
  assert.equal(document.source.name, 'Fallback Swagger Sample');
  assert.equal(document.source.resolvedFrom, '/v3/api-docs');
  assert.deepEqual(document.scripts, [
    {
      id: 'getStatus',
      name: 'Get status',
      request: {
        method: 'GET',
        url: 'https://fallback.example.test/status',
      },
    },
  ]);
});