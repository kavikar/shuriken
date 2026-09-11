import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';

import { generateScriptsFromFile } from '../../src/runners/generate-scripts';

const projectRoot = path.resolve(__dirname, '..', '..');

test('generates request scripts from an OpenAPI file', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'openapi', 'petstore-minimal.yaml');

  const output = await generateScriptsFromFile(filePath);
  const document = JSON.parse(output) as {
    source: { kind: string; name: string };
    scripts: Array<{ id: string; request: { url: string } }>;
  };

  assert.equal(document.source.kind, 'openapi');
  assert.equal(document.source.name, 'Petstore API');
  assert.equal(document.scripts.length, 2);
  assert.equal(document.scripts[0].id, 'listPets');
  assert.equal(document.scripts[0].request.url, 'https://api.example.com/v1/pets');
});

test('generates request scripts from a Postman file', async () => {
  const filePath = path.join(projectRoot, 'fixtures', 'postman', 'ping-collection.json');

  const output = await generateScriptsFromFile(filePath);
  const document = JSON.parse(output) as {
    source: { kind: string; name: string };
    scripts: Array<{ id: string; request: { url: string } }>;
  };

  assert.equal(document.source.kind, 'postman');
  assert.equal(document.source.name, 'Ping API Collection');
  assert.equal(document.scripts.length, 1);
  assert.equal(document.scripts[0].id, 'Health.Get Health');
  assert.equal(document.scripts[0].request.url, 'https://postman.example.com/health');
});