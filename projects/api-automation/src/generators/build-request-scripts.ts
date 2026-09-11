import type { ApiSourceDocument } from '../models/api-source';
import type { RequestScript } from '../models/request-script';

export function buildRequestScripts(source: ApiSourceDocument): RequestScript[] {
  return source.operations.map((operation) => ({
    id: operation.id,
    name: operation.name,
    request: {
      method: operation.method,
      url: buildRequestUrl(source.baseUrl, operation.path),
      ...(operation.parameters ? { parameters: operation.parameters } : {}),
      ...(operation.requestBody ? { body: operation.requestBody } : {}),
      ...(operation.security ? { security: operation.security } : {}),
    },
  }));
}

function buildRequestUrl(baseUrl: string | undefined, path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;

  if (!baseUrl) {
    return normalizedPath;
  }

  return `${baseUrl.replace(/\/+$/, '')}${normalizedPath}`;
}