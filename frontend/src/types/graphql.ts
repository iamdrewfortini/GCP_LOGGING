// Manually generated GraphQL types (consider adding codegen later)

export const Severity = {
  DEBUG: 'DEBUG',
  INFO: 'INFO',
  NOTICE: 'NOTICE',
  WARNING: 'WARNING',
  ERROR: 'ERROR',
  CRITICAL: 'CRITICAL',
  ALERT: 'ALERT',
  EMERGENCY: 'EMERGENCY',
} as const;

export type Severity = (typeof Severity)[keyof typeof Severity];

export interface LogEntry {
  id: string;
  eventTs: string; // DateTime as string
  ingestTs: string;
  projectId: string;
  env: string;
  region: string;
  serviceName: string;
  severity: Severity;
  eventType: string;
  correlationIds: string[];
  labels: Record<string, any>;
  message?: string;
  body?: string;
  httpMethod?: string;
  httpStatus?: number;
  traceId?: string;
  spanId?: string;
}

export interface LogQuery {
  logs: LogEntry[];
  totalCount: number;
  hasMore: boolean;
}

export interface LogFilter {
  hours?: number;
  limit?: number;
  severity?: Severity;
  serviceName?: string;
  region?: string;
  env?: string;
}

export interface Health {
  ok: boolean;
  version: string;
  services: Record<string, string>;
}

// Add more types as needed