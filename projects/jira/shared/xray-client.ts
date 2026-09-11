/**
 * Xray Cloud Client + Jira REST Helpers  (SHARED)
 *
 * Two APIs are used:
 *   1. Jira REST API v3 — for reading issue metadata (summary, labels, status)
 *   2. Xray Cloud GraphQL API v2 — for reading/writing test steps & Gherkin definitions
 *
 * The Xray Cloud API uses client_id/secret → JWT bearer token auth,
 * separate from Jira credentials.
 *
 * Requires env vars:
 *   JIRA_BASE_URL       — e.g. https://your-tenant.atlassian.net
 *   JIRA_EMAIL           — your Jira account email
 *   JIRA_API_TOKEN       — API token from id.atlassian.com
 *   XRAY_CLIENT_ID       — Xray Cloud API client ID
 *   XRAY_CLIENT_SECRET   — Xray Cloud API client secret
 *   XRAY_BASE_URL        — https://xray.cloud.getxray.app/api/v2
 */

import dotenv from 'dotenv';
import path from 'path';

// Load .env — tries caller's project dir first, then common locations
export function loadEnv(projectRoot?: string) {
  const envPaths = [
    projectRoot ? path.join(projectRoot, '.env') : '',
    path.resolve(__dirname, '..', '.env'),
    path.resolve(process.env.USERPROFILE || process.env.HOME || '', 'Documents', 'jira-automation', '.env'),
  ].filter(Boolean);

  for (const envPath of envPaths) {
    const result = dotenv.config({ path: envPath });
    if (!result.error) break;
  }

  // Corporate proxy SSL bypass — must be set before any fetch calls
  if (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0') {
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
  }
}

// Auto-load on import
loadEnv();

// ── Types ──────────────────────────────────────────────────────────

export interface JiraConfig {
  baseUrl: string;
  email: string;
  apiToken: string;
}

export interface XrayConfig {
  baseUrl: string;
  clientId: string;
  clientSecret: string;
}

export interface XrayTestIssue {
  key: string;
  summary: string;
  labels: string[];
  status: string;
  components: string[];
  /** Numeric Jira issue ID needed for Xray Cloud mutations */
  numericId?: string;
  /** Current Gherkin definition from Xray Cloud */
  gherkin?: string | null;
  /** Test type name from Xray Cloud (Manual / Cucumber / Generic) */
  testType?: string | null;
}

export interface BulkSearchResult {
  total: number;
  issues: XrayTestIssue[];
}

// ── Config ─────────────────────────────────────────────────────────

export function getConfig(): JiraConfig | null {
  const baseUrl = process.env.JIRA_BASE_URL?.replace(/\/+$/, '');
  const email = process.env.JIRA_EMAIL;
  const apiToken = process.env.JIRA_API_TOKEN;

  if (!baseUrl || !email || !apiToken) {
    return null;
  }
  return { baseUrl, email, apiToken };
}

export function getXrayConfig(): XrayConfig | null {
  const baseUrl = (process.env.XRAY_BASE_URL || 'https://xray.cloud.getxray.app/api/v2').replace(/\/+$/, '');
  const clientId = process.env.XRAY_CLIENT_ID;
  const clientSecret = process.env.XRAY_CLIENT_SECRET;

  if (!clientId || !clientSecret) {
    return null;
  }
  return { baseUrl, clientId, clientSecret };
}

function authHeader(config: JiraConfig): string {
  return `Basic ${Buffer.from(`${config.email}:${config.apiToken}`).toString('base64')}`;
}

// ── Jira REST Low-Level HTTP ───────────────────────────────────────

async function jiraGet<T>(config: JiraConfig, endpoint: string): Promise<T> {
  const url = `${config.baseUrl}${endpoint}`;
  const resp = await fetch(url, {
    headers: { Authorization: authHeader(config), Accept: 'application/json' },
  });
  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`GET ${endpoint} → ${resp.status} ${resp.statusText}\n${body}`);
  }
  return resp.json() as Promise<T>;
}

async function jiraPut(config: JiraConfig, endpoint: string, body: unknown): Promise<void> {
  const url = `${config.baseUrl}${endpoint}`;
  const resp = await fetch(url, {
    method: 'PUT',
    headers: { Authorization: authHeader(config), 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`PUT ${endpoint} → ${resp.status} ${resp.statusText}\n${text}`);
  }
}

async function jiraPost<T>(config: JiraConfig, endpoint: string, body: unknown): Promise<T> {
  const url = `${config.baseUrl}${endpoint}`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: { Authorization: authHeader(config), 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`POST ${endpoint} → ${resp.status} ${resp.statusText}\n${text}`);
  }
  return resp.json() as Promise<T>;
}

/**
 * Upload a file attachment to a Jira issue.
 * Uses multipart/form-data as required by the Jira REST API v3.
 */
export async function addAttachment(
  config: JiraConfig,
  issueKey: string,
  filePath: string,
  fileName?: string,
): Promise<void> {
  const fs = await import('fs');
  const pathModule = await import('path');

  const resolvedName = fileName || pathModule.basename(filePath);
  const fileData = fs.readFileSync(filePath);

  // Build multipart/form-data manually (Node 18+ compatible)
  const boundary = `----FormBoundary${Date.now().toString(36)}`;
  const CRLF = '\r\n';

  // Determine mime type
  const ext = pathModule.extname(filePath).toLowerCase();
  const mimeTypes: Record<string, string> = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.webp': 'image/webp', '.pdf': 'application/pdf',
    '.csv': 'text/csv', '.txt': 'text/plain', '.json': 'application/json',
  };
  const mimeType = mimeTypes[ext] || 'application/octet-stream';

  const header = Buffer.from(
    `--${boundary}${CRLF}` +
    `Content-Disposition: form-data; name="file"; filename="${resolvedName}"${CRLF}` +
    `Content-Type: ${mimeType}${CRLF}${CRLF}`
  );
  const footer = Buffer.from(`${CRLF}--${boundary}--${CRLF}`);
  const body = Buffer.concat([header, fileData, footer]);

  const url = `${config.baseUrl}/rest/api/3/issue/${issueKey}/attachments`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: authHeader(config),
      'X-Atlassian-Token': 'no-check',
      'Content-Type': `multipart/form-data; boundary=${boundary}`,
    },
    body,
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`POST attachments for ${issueKey} → ${resp.status} ${resp.statusText}\n${text}`);
  }
}

// ── Xray Cloud Auth & GraphQL ──────────────────────────────────────

let cachedXrayToken: string | null = null;
let tokenExpiry: number = 0;

/**
 * Get a JWT bearer token from Xray Cloud. Cached for ~10 minutes.
 */
export async function getXrayToken(xrayConfig: XrayConfig): Promise<string> {
  if (cachedXrayToken && Date.now() < tokenExpiry) {
    return cachedXrayToken;
  }

  const resp = await fetch(`${xrayConfig.baseUrl}/authenticate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: xrayConfig.clientId, client_secret: xrayConfig.clientSecret }),
  });
  if (!resp.ok) throw new Error(`Xray auth: ${resp.status} ${await resp.text()}`);

  const token = (await resp.text()).replace(/"/g, '');
  cachedXrayToken = token;
  tokenExpiry = Date.now() + 10 * 60 * 1000; // 10 min cache
  return token;
}

/**
 * Execute a GraphQL query/mutation against Xray Cloud.
 */
export async function xrayGraphQL(
  xrayConfig: XrayConfig,
  query: string,
  variables?: Record<string, unknown>,
): Promise<any> {
  const token = await getXrayToken(xrayConfig);
  const body: any = { query };
  if (variables) body.variables = variables;

  const resp = await fetch(`${xrayConfig.baseUrl}/graphql`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Xray GQL ${resp.status}: ${(await resp.text()).substring(0, 500)}`);

  const data = await resp.json() as any;
  if (data.errors?.length) {
    const msg = data.errors.map((e: any) => e.message).join('; ');
    throw new Error(`GraphQL error: ${msg}`);
  }
  return data;
}

// ── Parse Raw Jira Issue ───────────────────────────────────────────

interface RawIssue {
  id: string;
  key: string;
  fields: {
    summary: string;
    labels: string[];
    status: { name: string };
    components?: Array<{ name: string }>;
    [key: string]: unknown;
  };
}

function parseIssue(raw: RawIssue): XrayTestIssue {
  return {
    key: raw.key,
    summary: raw.fields.summary,
    labels: raw.fields.labels || [],
    status: raw.fields.status?.name || 'Unknown',
    components: (raw.fields.components || []).map((c) => c.name),
    numericId: raw.id,
  };
}

// ── Public: Jira REST API ──────────────────────────────────────────

export async function testConnection(config: JiraConfig): Promise<boolean> {
  try {
    await jiraGet(config, '/rest/api/3/myself');
    return true;
  } catch {
    return false;
  }
}

export async function getIssue(config: JiraConfig, issueKey: string): Promise<XrayTestIssue> {
  const raw = await jiraGet<RawIssue>(config, `/rest/api/3/issue/${issueKey}?fields=summary,labels,status,components`);
  return parseIssue(raw);
}

/**
 * Search issues by JQL with auto-pagination (uses enhanced search /search/jql).
 */
export async function searchIssues(
  config: JiraConfig,
  jql: string,
  maxResults = 200,
): Promise<BulkSearchResult> {
  const allIssues: XrayTestIssue[] = [];
  let nextPageToken: string | undefined = undefined;

  do {
    const body: any = {
      jql,
      fields: ['summary', 'labels', 'status', 'components'],
      maxResults: Math.min(50, maxResults - allIssues.length),
    };
    if (nextPageToken) body.nextPageToken = nextPageToken;

    const result = await jiraPost<{
      issues: RawIssue[];
      nextPageToken?: string;
      isLast?: boolean;
    }>(config, '/rest/api/3/search/jql', body);

    const parsed = result.issues.map(parseIssue);
    allIssues.push(...parsed);
    nextPageToken = result.nextPageToken;

    if (result.isLast || !nextPageToken || allIssues.length >= maxResults) break;
  } while (true);

  return { total: allIssues.length, issues: allIssues };
}

/**
 * Fetch multiple issues by their keys (batches JQL query).
 * Returns issues with their numeric Jira IDs (needed for Xray Cloud).
 */
export async function getIssuesByKeys(
  config: JiraConfig,
  keys: string[],
): Promise<XrayTestIssue[]> {
  if (keys.length === 0) return [];

  const batches: string[][] = [];
  for (let i = 0; i < keys.length; i += 50) {
    batches.push(keys.slice(i, i + 50));
  }

  const allIssues: XrayTestIssue[] = [];
  for (const batch of batches) {
    const jql = `key in (${batch.join(',')})`;
    const result = await searchIssues(config, jql, batch.length);
    allIssues.push(...result.issues);
  }

  return allIssues;
}

// ── Public: Xray Cloud GraphQL API ─────────────────────────────────

/**
 * Read the current Gherkin definition for a test.
 */
export async function readGherkinDefinition(
  xrayConfig: XrayConfig,
  issueKey: string,
): Promise<{ issueId: string; testType: string; gherkin: string | null } | null> {
  const result = await xrayGraphQL(xrayConfig, `{
    getTests(jql: "key = ${issueKey}", limit: 1) {
      results {
        issueId
        testType { name kind }
        gherkin
      }
    }
  }`);
  const test = result.data?.getTests?.results?.[0];
  if (!test) return null;
  return {
    issueId: test.issueId,
    testType: test.testType?.name || 'Unknown',
    gherkin: test.gherkin || null,
  };
}

/**
 * Update the Gherkin (Cucumber) definition for a test in Xray Cloud.
 *
 * IMPORTANT: Requires the numeric Jira issue ID, NOT the issue key.
 *            Use issue.numericId from getIssuesByKeys().
 */
export async function updateGherkinDefinition(
  xrayConfig: XrayConfig,
  numericIssueId: string,
  gherkin: string,
): Promise<void> {
  await xrayGraphQL(
    xrayConfig,
    `mutation UpdateGherkin($issueId: String!, $gherkin: String!) {
      updateGherkinTestDefinition(issueId: $issueId, gherkin: $gherkin) {
        issueId
        testType { name kind }
      }
    }`,
    { issueId: numericIssueId, gherkin },
  );
}

/**
 * Set the test type to Cucumber if it's not already.
 * Uses numeric issueId.
 */
export async function setTestTypeCucumber(
  xrayConfig: XrayConfig,
  numericIssueId: string,
): Promise<void> {
  await xrayGraphQL(
    xrayConfig,
    `mutation SetCucumber($issueId: String!) {
      updateTestType(issueId: $issueId, testType: { name: "Cucumber" }) {
        issueId
        testType { name kind }
      }
    }`,
    { issueId: numericIssueId },
  );
}

/**
 * Update the description field of a Jira issue.
 * Body must be in Atlassian Document Format (ADF).
 */
export async function updateDescription(
  config: JiraConfig,
  issueKey: string,
  adfDescription: object,
): Promise<void> {
  await jiraPut(config, `/rest/api/3/issue/${issueKey}`, {
    fields: { description: adfDescription },
  });
}

/**
 * Read the current description of a Jira issue (raw ADF).
 */
export async function getDescription(
  config: JiraConfig,
  issueKey: string,
): Promise<any> {
  const raw = await jiraGet<{ fields: { description: any } }>(
    config,
    `/rest/api/3/issue/${issueKey}?fields=description`,
  );
  return raw.fields.description;
}

/**
 * Discover Xray-related custom fields (for diagnostics).
 */
export async function discoverFields(
  config: JiraConfig,
): Promise<Array<{ id: string; name: string; type: string }>> {
  const allFields = await jiraGet<Array<{ id: string; name: string; schema?: { type: string } }>>(
    config,
    '/rest/api/3/field',
  );

  const xrayRelated = allFields.filter((f) => {
    const lower = (f.name || '').toLowerCase();
    return (
      lower.includes('cucumber') || lower.includes('xray') ||
      lower.includes('test') || lower.includes('gherkin') ||
      lower.includes('scenario') || lower.includes('bdd')
    );
  });

  return xrayRelated.map((f) => ({
    id: f.id,
    name: f.name,
    type: f.schema?.type || 'unknown',
  }));
}
