import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import { buildRequestScripts } from '../../src/generators/build-request-scripts';
import { loadApiSource } from '../../src/importers/load-api-source';

const projectRoot = path.resolve(__dirname, '..', '..');

test('builds runnable request scripts from an OpenAPI source', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'petstore-minimal.yaml');
  const source = await loadApiSource({ filePath, content: fs.readFileSync(filePath, 'utf8') });

  const scripts = buildRequestScripts(source);

  assert.deepEqual(scripts, [
    {
      id: 'listPets',
      name: 'List pets',
      request: {
        method: 'GET',
        url: 'https://api.example.com/v1/pets',
      },
    },
    {
      id: 'createPet',
      name: 'Create pet',
      request: {
        method: 'POST',
        url: 'https://api.example.com/v1/pets',
      },
    },
  ]);
});

test('builds runnable request scripts from a Postman source', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'postman', 'ping-collection.json');
  const source = await loadApiSource({ filePath, content: fs.readFileSync(filePath, 'utf8') });

  const scripts = buildRequestScripts(source);

  assert.deepEqual(scripts, [
    {
      id: 'Health.Get Health',
      name: 'Get Health',
      request: {
        method: 'GET',
        url: 'https://postman.example.com/health',
      },
    },
  ]);
});

test('builds execution-ready request scripts from detailed OpenAPI metadata', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'orders-detailed.yaml');
  const source = await loadApiSource({ filePath, content: fs.readFileSync(filePath, 'utf8') });

  const scripts = buildRequestScripts(source);

  assert.deepEqual(scripts, [
    {
      id: 'getOrder',
      name: 'Get order',
      request: {
        method: 'GET',
        url: 'https://orders.example.com/api/brands/{brandId}/orders/{orderId}',
        parameters: [
          { name: 'brandId', in: 'path', required: true, type: 'string' },
          { name: 'orderId', in: 'path', required: true, type: 'string' },
          { name: 'includeDetails', in: 'query', required: false, type: 'boolean' },
        ],
        security: [
          { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
        ],
      },
    },
    {
      id: 'createOrder',
      name: 'Create order',
      request: {
        method: 'POST',
        url: 'https://orders.example.com/api/brands/{brandId}/orders',
        parameters: [
          { name: 'brandId', in: 'path', required: true, type: 'string' },
        ],
        body: {
          contentType: 'application/json',
          required: true,
          example: {
            itemId: 'ITEM-100',
            quantity: 2,
          },
        },
        security: [
          { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
        ],
      },
    },
  ]);
});