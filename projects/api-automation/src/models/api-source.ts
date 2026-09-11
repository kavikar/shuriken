export type ApiSourceKind = 'openapi' | 'postman';

export interface ApiParameterSummary {
  name: string;
  in: 'path' | 'query' | 'header' | 'cookie';
  required: boolean;
  type?: string;
}

export interface ApiSecuritySummary {
  name: string;
  type?: string;
  scheme?: string;
}

export interface ApiRequestBodySummary {
  required: boolean;
  contentType: string;
  example?: unknown;
}

export interface ApiOperationSummary {
  id: string;
  method: string;
  path: string;
  name: string;
  group?: string;
  parameters?: ApiParameterSummary[];
  requestBody?: ApiRequestBodySummary;
  security?: ApiSecuritySummary[];
}

export interface ApiSourceDocument {
  kind: ApiSourceKind;
  name: string;
  version?: string;
  baseUrl?: string;
  operations: ApiOperationSummary[];
}

export interface LoadApiSourceInput {
  filePath: string;
  content: string;
}