import { parse as parseYaml } from 'yaml';

import type {
  ApiParameterSummary,
  ApiOperationSummary,
  ApiRequestBodySummary,
  ApiSecuritySummary,
  ApiSourceDocument,
  LoadApiSourceInput,
} from '../models/api-source';

interface OpenApiDocument {
  openapi?: string;
  swagger?: string;
  info?: {
    title?: string;
    version?: string;
  };
  servers?: Array<{
    url?: string;
  }>;
  components?: {
    securitySchemes?: Record<string, { type?: string; scheme?: string }>;
  };
  paths?: Record<string, Record<string, OpenApiOperation>>;
}

interface OpenApiOperation {
  operationId?: string;
  summary?: string;
  tags?: string[];
  parameters?: OpenApiParameter[];
  requestBody?: OpenApiRequestBody;
  security?: Array<Record<string, string[]>>;
}

interface OpenApiParameter {
  name?: string;
  in?: 'path' | 'query' | 'header' | 'cookie';
  required?: boolean;
  schema?: {
    type?: string;
  };
}

interface OpenApiRequestBody {
  required?: boolean;
  content?: Record<string, { example?: unknown }>;
}

interface PostmanCollection {
  info?: {
    name?: string;
  };
  variable?: Array<{
    key?: string;
    value?: string;
  }>;
  item?: PostmanItem[];
}

interface PostmanItem {
  name?: string;
  item?: PostmanItem[];
  request?: {
    method?: string;
    url?: {
      raw?: string;
      path?: string[];
    };
  };
}

export async function loadApiSource(input: LoadApiSourceInput): Promise<ApiSourceDocument> {
  const document = parseSourceDocument(input.content);

  if (isOpenApiDocument(document)) {
    return loadOpenApiSource(document);
  }

  if (isPostmanCollection(document)) {
    return loadPostmanSource(document);
  }

  throw new Error(`Unsupported API source format for ${input.filePath}`);
}

function parseSourceDocument(content: string): unknown {
  try {
    return JSON.parse(content);
  } catch {
    return parseYaml(content);
  }
}

function isOpenApiDocument(value: unknown): value is OpenApiDocument {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const candidate = value as OpenApiDocument;
  return Boolean(candidate.openapi || candidate.swagger);
}

function isPostmanCollection(value: unknown): value is PostmanCollection {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const candidate = value as PostmanCollection;
  return Array.isArray(candidate.item) && typeof candidate.info?.name === 'string';
}

function loadOpenApiSource(document: OpenApiDocument): ApiSourceDocument {
  const operations: ApiOperationSummary[] = [];
  const securitySchemes = document.components?.securitySchemes || {};

  for (const [routePath, methods] of Object.entries(document.paths || {})) {
    for (const [method, operation] of Object.entries(methods || {})) {
      const parameters = toApiParameters(operation.parameters);
      const requestBody = toApiRequestBody(operation.requestBody);
      const security = toApiSecurity(operation.security, securitySchemes);
      operations.push({
        id: operation.operationId || `${method.toUpperCase()} ${routePath}`,
        method: method.toUpperCase(),
        path: routePath,
        name: operation.summary || operation.operationId || `${method.toUpperCase()} ${routePath}`,
        group: operation.tags?.[0],
        ...(parameters.length > 0 ? { parameters } : {}),
        ...(requestBody ? { requestBody } : {}),
        ...(security.length > 0 ? { security } : {}),
      });
    }
  }

  return {
    kind: 'openapi',
    name: document.info?.title || 'OpenAPI Document',
    version: document.info?.version,
    baseUrl: document.servers?.[0]?.url,
    operations,
  };
}

function loadPostmanSource(collection: PostmanCollection): ApiSourceDocument {
  const operations: ApiOperationSummary[] = [];

  for (const item of collection.item || []) {
    visitPostmanItem(item, [], operations);
  }

  return {
    kind: 'postman',
    name: collection.info?.name || 'Postman Collection',
    baseUrl: collection.variable?.find((entry) => entry.key === 'baseUrl')?.value,
    operations,
  };
}

function visitPostmanItem(
  item: PostmanItem,
  groups: string[],
  operations: ApiOperationSummary[],
): void {
  if (Array.isArray(item.item) && item.item.length > 0) {
    const nextGroups = item.name ? [...groups, item.name] : groups;
    for (const child of item.item) {
      visitPostmanItem(child, nextGroups, operations);
    }
    return;
  }

  if (!item.request) {
    return;
  }

  const pathSegments = item.request.url?.path || [];
  const path = pathSegments.length > 0 ? `/${pathSegments.join('/')}` : '/';
  const group = groups[0];
  const name = item.name || `${item.request.method || 'GET'} ${path}`;

  operations.push({
    id: group ? `${group}.${name}` : name,
    method: (item.request.method || 'GET').toUpperCase(),
    path,
    name,
    group,
  });
}

function toApiParameters(parameters: OpenApiParameter[] | undefined): ApiParameterSummary[] {
  return (parameters || [])
    .filter((parameter): parameter is Required<Pick<OpenApiParameter, 'name' | 'in'>> & OpenApiParameter => Boolean(parameter.name && parameter.in))
    .map((parameter) => ({
      name: parameter.name,
      in: parameter.in,
      required: Boolean(parameter.required),
      type: parameter.schema?.type,
    }));
}

function toApiRequestBody(requestBody: OpenApiRequestBody | undefined): ApiRequestBodySummary | undefined {
  if (!requestBody?.content) {
    return undefined;
  }

  const [contentType, content] = Object.entries(requestBody.content)[0] || [];
  if (!contentType) {
    return undefined;
  }

  return {
    required: Boolean(requestBody.required),
    contentType,
    example: content?.example,
  };
}

function toApiSecurity(
  security: Array<Record<string, string[]>> | undefined,
  securitySchemes: Record<string, { type?: string; scheme?: string }>,
): ApiSecuritySummary[] {
  const result: ApiSecuritySummary[] = [];

  for (const requirement of security || []) {
    for (const name of Object.keys(requirement)) {
      result.push({
        name,
        type: securitySchemes[name]?.type,
        scheme: securitySchemes[name]?.scheme,
      });
    }
  }

  return result;
}