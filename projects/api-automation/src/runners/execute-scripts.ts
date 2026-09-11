import fs from 'node:fs/promises';
import path from 'node:path';

import { buildRequestScripts } from '../generators/build-request-scripts';
import { loadApiSource } from '../importers/load-api-source';
import type { RequestScript } from '../models/request-script';

export interface ExecuteScriptsDryRunOptions {
  filePath: string;
  operationId: string;
  variables: Record<string, string>;
}

export interface ExecuteScriptsLiveOptions extends ExecuteScriptsDryRunOptions {
  baseUrlOverride?: string;
}

export interface PreparedRequestResult {
  mode: 'dry-run';
  source: {
    filePath: string;
    operationId: string;
  };
  request: {
    method: string;
    url: string;
    body?: {
      contentType: string;
      value: unknown;
    };
    security?: Array<{
      name: string;
      type?: string;
      scheme?: string;
    }>;
  };
}

export interface LiveExecutionResult {
  mode: 'live';
  source: {
    filePath: string;
    operationId: string;
  };
  request: PreparedRequestResult['request'];
  response: {
    status: number;
    contentType?: string;
    body: unknown;
  };
}

export async function executeScriptsDryRunFromFile(options: ExecuteScriptsDryRunOptions): Promise<PreparedRequestResult> {
  const prepared = await prepareRequestFromFile(options);

  return {
    mode: 'dry-run',
    source: {
      filePath: prepared.filePath,
      operationId: options.operationId,
    },
    request: prepared.request,
  };
}

export async function executeScriptsLiveFromFile(options: ExecuteScriptsLiveOptions): Promise<LiveExecutionResult> {
  const prepared = await prepareRequestFromFile(options);
  const response = await fetch(prepared.request.url, {
    method: prepared.request.method,
    headers: prepared.request.body ? {
      'Content-Type': prepared.request.body.contentType,
    } : undefined,
    body: prepared.request.body ? JSON.stringify(prepared.request.body.value) : undefined,
  });

  const contentType = response.headers.get('content-type') || undefined;
  const responseBody = await readResponseBody(response, contentType);

  return {
    mode: 'live',
    source: {
      filePath: prepared.filePath,
      operationId: options.operationId,
    },
    request: prepared.request,
    response: {
      status: response.status,
      contentType,
      body: responseBody,
    },
  };
}

interface PreparedRequestInternal {
  filePath: string;
  request: PreparedRequestResult['request'];
}

async function prepareRequestFromFile(options: ExecuteScriptsLiveOptions): Promise<PreparedRequestInternal> {
  const resolvedPath = path.resolve(options.filePath);
  const content = await fs.readFile(resolvedPath, 'utf8');
  const source = await loadApiSource({ filePath: resolvedPath, content });
  const scripts = buildRequestScripts(source);
  const script = scripts.find((candidate) => candidate.id === options.operationId);

  if (!script) {
    throw new Error(`Operation not found: ${options.operationId}`);
  }

  const resolvedUrl = resolveUrl(
    overrideBaseUrl(script.request.url, source.baseUrl, options.baseUrlOverride),
    script,
    options.variables,
  );

  return {
    filePath: resolvedPath,
    request: {
      method: script.request.method,
      url: resolvedUrl,
      ...(script.request.body ? {
        body: {
          contentType: script.request.body.contentType,
          value: script.request.body.example,
        },
      } : {}),
      ...(script.request.security ? { security: script.request.security } : {}),
    },
  };
}

function resolveUrl(
  templateUrl: string,
  script: RequestScript,
  variables: Record<string, string>,
): string {
  const parameters = script.request.parameters || [];
  let resolvedUrl = templateUrl;

  for (const parameter of parameters.filter((entry) => entry.in === 'path')) {
    const value = variables[parameter.name];
    if (value === undefined) {
      if (parameter.required) {
        throw new Error(`Missing required variable: ${parameter.name}`);
      }
      continue;
    }

    resolvedUrl = resolvedUrl.replaceAll(`{${parameter.name}}`, encodeURIComponent(value));
  }

  const query = new URLSearchParams();
  for (const parameter of parameters.filter((entry) => entry.in === 'query')) {
    const value = variables[parameter.name];
    if (value === undefined && parameter.required) {
      throw new Error(`Missing required variable: ${parameter.name}`);
    }
    if (value !== undefined) {
      query.set(parameter.name, value);
    }
  }

  const queryString = query.toString();
  const withQuery = queryString ? `${resolvedUrl}?${queryString}` : resolvedUrl;
  const withPostmanVariables = replacePostmanVariables(withQuery, variables);
  const unresolvedPostmanVariables = collectPostmanVariables(withPostmanVariables);

  if (unresolvedPostmanVariables.length > 0) {
    throw new Error(`Missing required variable(s): ${unresolvedPostmanVariables.join(', ')}`);
  }

  return withPostmanVariables;
}

function replacePostmanVariables(url: string, variables: Record<string, string>): string {
  return url.replace(/\{\{\s*([^{}\s]+)\s*\}\}/g, (match, key: string) => {
    const value = variables[key];
    return value === undefined ? match : encodeURIComponent(value);
  });
}

function collectPostmanVariables(url: string): string[] {
  const matches = url.matchAll(/\{\{\s*([^{}\s]+)\s*\}\}/g);
  return [...new Set(Array.from(matches, (match) => match[1]))];
}

function overrideBaseUrl(url: string, sourceBaseUrl: string | undefined, baseUrlOverride: string | undefined): string {
  if (!baseUrlOverride || !sourceBaseUrl) {
    return url;
  }

  if (!url.startsWith(sourceBaseUrl)) {
    return url;
  }

  const suffix = url.slice(sourceBaseUrl.length);
  return `${baseUrlOverride.replace(/\/+$/, '')}${suffix.startsWith('/') ? suffix : `/${suffix}`}`;
}

async function readResponseBody(response: Response, contentType: string | undefined): Promise<unknown> {
  if (contentType?.includes('application/json')) {
    return response.json();
  }

  return response.text();
}

async function main(): Promise<void> {
  const { mode, options } = parseArgs(process.argv.slice(2));
  const output = mode === 'live'
    ? await executeScriptsLiveFromFile(options)
    : await executeScriptsDryRunFromFile(options);
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
}

function parseArgs(args: string[]): { mode: 'dry-run' | 'live'; options: ExecuteScriptsLiveOptions } {
  const filePath = readRequiredArgument(args, '--file');
  const operationId = readRequiredArgument(args, '--operation');
  const variables = parseVariables(args);
  const baseUrlOverride = readOptionalArgument(args, '--base-url');
  const mode = args.includes('--live') ? 'live' : 'dry-run';

  return {
    mode,
    options: { filePath, operationId, variables, baseUrlOverride },
  };
}

function readRequiredArgument(args: string[], flag: string): string {
  const index = args.findIndex((entry) => entry === flag);
  if (index === -1 || !args[index + 1]) {
    throw new Error(`Missing required ${flag} argument`);
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

function readOptionalArgument(args: string[], flag: string): string | undefined {
  const index = args.findIndex((entry) => entry === flag);
  if (index === -1 || !args[index + 1]) {
    return undefined;
  }

  return args[index + 1];
}

if (require.main === module) {
  main().catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}