import { loadApiSource } from './load-api-source';

import type { ApiSourceDocument } from '../models/api-source';

export interface LoadedApiSourceFromUrl {
  source: ApiSourceDocument;
  resolvedFrom?: string;
}

export async function loadApiSourceFromUrl(url: string): Promise<LoadedApiSourceFromUrl> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }

  const contentType = response.headers.get('content-type') || '';
  const content = await response.text();

  if (looksLikeHtml(contentType, content)) {
    const resolvedDocUrl = await resolveSwaggerDocumentUrl(url, content);
    if (!resolvedDocUrl) {
      throw new Error(`Could not find an OpenAPI document link in Swagger UI URL: ${url}`);
    }

    const docResponse = await fetch(resolvedDocUrl.absoluteUrl);
    if (!docResponse.ok) {
      throw new Error(`Failed to fetch ${resolvedDocUrl.absoluteUrl}: ${docResponse.status} ${docResponse.statusText}`);
    }

    const docContent = await docResponse.text();
    return {
      source: await loadApiSource({ filePath: resolvedDocUrl.absoluteUrl, content: docContent }),
      resolvedFrom: resolvedDocUrl.relativePath,
    };
  }

  return {
    source: await loadApiSource({ filePath: url, content }),
  };
}

function looksLikeHtml(contentType: string, content: string): boolean {
  return contentType.includes('text/html') || /<html[\s>]/i.test(content);
}

async function resolveSwaggerDocumentUrl(pageUrl: string, content: string): Promise<{ absoluteUrl: string; relativePath: string } | null> {
  const directDocMatch = content.match(/href=["']([^"']*\/v3\/api-docs[^"']*)["']/i)
    || content.match(/url:\s*["']([^"']+)["']/i)
    || content.match(/urls:\s*\[\s*\{\s*url:\s*["']([^"']+)["']/i)
    || content.match(/["'](\/v3\/api-docs[^"']*)["']/i);

  if (directDocMatch && directDocMatch[1]) {
    const relativePath = stripFragment(directDocMatch[1]);
    const absoluteUrl = new URL(relativePath, pageUrl).toString();
    return { absoluteUrl, relativePath };
  }

  return tryFallbackDocumentUrls(pageUrl);
}

function stripFragment(value: string): string {
  const hashIndex = value.indexOf('#');
  return hashIndex === -1 ? value : value.slice(0, hashIndex);
}

async function tryFallbackDocumentUrls(pageUrl: string): Promise<{ absoluteUrl: string; relativePath: string } | null> {
  const page = new URL(pageUrl);
  const candidates = buildFallbackCandidates(page);

  for (const candidate of candidates) {
    try {
      const response = await fetch(candidate.absoluteUrl);
      if (!response.ok) {
        continue;
      }

      const body = await response.text();
      if (looksLikeApiDocument(body)) {
        return candidate;
      }
    } catch {
      continue;
    }
  }

  return null;
}

function buildFallbackCandidates(page: URL): Array<{ absoluteUrl: string; relativePath: string }> {
  const pathname = page.pathname || '/';
  const pageDirectory = pathname.endsWith('/') ? pathname : pathname.slice(0, pathname.lastIndexOf('/') + 1);
  const rootRelativeCandidates = [
    '/v3/api-docs',
    '/v3/api-docs.yaml',
    '/swagger-config',
    '/v2/api-docs',
  ];
  const pageRelativeCandidates = [
    `${pageDirectory}../v3/api-docs`,
    `${pageDirectory}swagger-config`,
    `${pageDirectory}../swagger-config`,
  ];

  const uniquePaths = Array.from(new Set([...rootRelativeCandidates, ...pageRelativeCandidates]));
  return uniquePaths.map((relativePath) => ({
    absoluteUrl: new URL(relativePath, page).toString(),
    relativePath,
  }));
}

function looksLikeApiDocument(content: string): boolean {
  return /"openapi"\s*:\s*"|"swagger"\s*:\s*"|^openapi\s*:/m.test(content);
}