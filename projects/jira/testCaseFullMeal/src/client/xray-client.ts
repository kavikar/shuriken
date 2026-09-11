/**
 * Xray Cloud Client + Jira REST Helpers
 *
 * ⚡ THIN WRAPPER — Re-exports everything from the shared client.
 * The actual implementation lives in: projects/jira/shared/xray-client.ts
 *
 * This file exists so that existing imports in testCaseFullMeal don't need
 * to change. All runners can keep using:
 *   import { ... } from '../client/xray-client';
 */

export {
  // Types
  type JiraConfig,
  type XrayConfig,
  type XrayTestIssue,
  type BulkSearchResult,

  // Config
  loadEnv,
  getConfig,
  getXrayConfig,

  // Jira REST
  testConnection,
  getIssue,
  searchIssues,
  getIssuesByKeys,
  addAttachment,
  updateDescription,
  getDescription,
  discoverFields,

  // Xray Cloud GraphQL
  getXrayToken,
  xrayGraphQL,
  readGherkinDefinition,
  updateGherkinDefinition,
  setTestTypeCucumber,
} from '../../../shared/xray-client';
