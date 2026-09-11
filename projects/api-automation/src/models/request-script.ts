import type {
  ApiParameterSummary,
  ApiRequestBodySummary,
  ApiSecuritySummary,
} from './api-source';

export interface RequestScript {
  id: string;
  name: string;
  request: {
    method: string;
    url: string;
    parameters?: ApiParameterSummary[];
    body?: ApiRequestBodySummary;
    security?: ApiSecuritySummary[];
  };
}