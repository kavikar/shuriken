import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import { loadApiSource } from '../../src/importers/load-api-source';

const projectRoot = path.resolve(__dirname, '..', '..');

test('loads an OpenAPI document into the canonical source model', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'petstore-minimal.yaml');
  const content = fs.readFileSync(filePath, 'utf8');

  const source = await loadApiSource({ filePath, content });

  assert.equal(source.kind, 'openapi');
  assert.equal(source.name, 'Petstore API');
  assert.equal(source.version, '1.0.0');
  assert.equal(source.baseUrl, 'https://api.example.com/v1');
  assert.equal(source.operations.length, 2);
  assert.deepEqual(source.operations.map((operation) => ({
    id: operation.id,
    method: operation.method,
    path: operation.path,
    name: operation.name,
  })), [
    {
      id: 'listPets',
      method: 'GET',
      path: '/pets',
      name: 'List pets',
    },
    {
      id: 'createPet',
      method: 'POST',
      path: '/pets',
      name: 'Create pet',
    },
  ]);
});

test('loads a Postman collection into the canonical source model', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'postman', 'ping-collection.json');
  const content = fs.readFileSync(filePath, 'utf8');

  const source = await loadApiSource({ filePath, content });

  assert.equal(source.kind, 'postman');
  assert.equal(source.name, 'Ping API Collection');
  assert.equal(source.baseUrl, 'https://postman.example.com');
  assert.equal(source.operations.length, 1);
  assert.deepEqual(source.operations[0], {
    id: 'Health.Get Health',
    method: 'GET',
    path: '/health',
    name: 'Get Health',
    group: 'Health',
  });
});

test('loads execution metadata from an OpenAPI document into the canonical source model', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'orders-detailed.yaml');
  const content = fs.readFileSync(filePath, 'utf8');

  const source = await loadApiSource({ filePath, content });

  assert.equal(source.kind, 'openapi');
  assert.equal(source.name, 'Orders API');
  assert.equal(source.operations.length, 2);
  assert.deepEqual(source.operations, [
    {
      id: 'getOrder',
      method: 'GET',
      path: '/brands/{brandId}/orders/{orderId}',
      name: 'Get order',
      group: 'orders',
      parameters: [
        { name: 'brandId', in: 'path', required: true, type: 'string' },
        { name: 'orderId', in: 'path', required: true, type: 'string' },
        { name: 'includeDetails', in: 'query', required: false, type: 'boolean' },
      ],
      security: [
        { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
      ],
    },
    {
      id: 'createOrder',
      method: 'POST',
      path: '/brands/{brandId}/orders',
      name: 'Create order',
      group: 'orders',
      parameters: [
        { name: 'brandId', in: 'path', required: true, type: 'string' },
      ],
      requestBody: {
        required: true,
        contentType: 'application/json',
        example: {
          itemId: 'ITEM-100',
          quantity: 2,
        },
      },
      security: [
        { type: 'http', scheme: 'bearer', name: 'bearerAuth' },
      ],
    },
  ]);
});