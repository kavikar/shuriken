import fs from 'node:fs/promises';
import path from 'node:path';

import { buildRequestScripts } from '../generators/build-request-scripts';
import { loadApiSource } from '../importers/load-api-source';
import { loadApiSourceFromUrl } from '../importers/load-api-source-from-url';

export async function generateScriptsFromFile(filePath: string): Promise<string> {
  const resolvedPath = path.resolve(filePath);
  const content = await fs.readFile(resolvedPath, 'utf8');
  const source = await loadApiSource({ filePath: resolvedPath, content });
  return serializeGeneratedScripts({ source });
}

export async function generateScriptsFromUrl(url: string): Promise<string> {
  const loaded = await loadApiSourceFromUrl(url);
  return serializeGeneratedScripts(loaded);
}

function serializeGeneratedScripts(input: { source: Awaited<ReturnType<typeof loadApiSource>>; resolvedFrom?: string }): string {
  const scripts = buildRequestScripts(input.source);

  return JSON.stringify({
    source: {
      kind: input.source.kind,
      name: input.source.name,
      version: input.source.version,
      baseUrl: input.source.baseUrl,
      resolvedFrom: input.resolvedFrom,
    },
    scripts,
  }, null, 2);
}

async function main(): Promise<void> {
  const output = await generateScriptsFromArgs(process.argv.slice(2));
  process.stdout.write(`${output}\n`);
}

async function generateScriptsFromArgs(args: string[]): Promise<string> {
  const url = readArgument(args, '--url');
  if (url) {
    return generateScriptsFromUrl(url);
  }

  const filePath = readRequiredArgument(args, '--file');
  return generateScriptsFromFile(filePath);
}

function readRequiredArgument(args: string[], flag: string): string {
  const value = readArgument(args, flag);
  if (!value) {
    throw new Error('Missing required --file <path> or --url <value> argument');
  }

  return value;
}

function readArgument(args: string[], flag: string): string | undefined {
  const fileIndex = args.findIndex((arg) => arg === flag);

  if (fileIndex === -1 || !args[fileIndex + 1]) {
    return undefined;
  }

  return args[fileIndex + 1];
}

function readFileArgument(args: string[]): string {
  const fileIndex = args.findIndex((arg) => arg === '--file');

  if (fileIndex === -1 || !args[fileIndex + 1]) {
    throw new Error('Missing required --file <path> argument');
  }

  return args[fileIndex + 1];
}

if (require.main === module) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}