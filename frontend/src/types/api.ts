import { z } from "zod"

// ============================================
// LOG TYPES
// ============================================

export const LogSeveritySchema = z.enum([
  "DEFAULT",
  "DEBUG",
  "INFO",
  "NOTICE",
  "WARNING",
  "ERROR",
  "CRITICAL",
  "ALERT",
  "EMERGENCY",
])

export type LogSeverity = z.infer<typeof LogSeveritySchema>

export const LogEntrySchema = z.object({
  insert_id: z.string(),
  event_timestamp: z.string(),
  severity: LogSeveritySchema,
  service_name: z.string().nullable(),
  log_name: z.string().nullable(),
  display_message: z.string().nullable(),
  source_table: z.string(),
  trace_id: z.string().nullable(),
  span_id: z.string().nullable(),
})

export type LogEntry = z.infer<typeof LogEntrySchema>

export const LogQueryParamsSchema = z.object({
  hours: z.number().min(1).max(168).default(24),
  limit: z.number().min(1).max(1000).default(100),
  severity: LogSeveritySchema.optional(),
  service: z.string().optional(),
  search: z.string().optional(),
  source_table: z.string().optional(),
})

export type LogQueryParams = z.infer<typeof LogQueryParamsSchema>

export const LogsResponseSchema = z.object({
  status: z.literal("success"),
  count: z.number(),
  data: z.array(LogEntrySchema),
})

export type LogsResponse = z.infer<typeof LogsResponseSchema>

// ============================================
// STATS TYPES
// ============================================

export const SeverityStatsSchema = z.object({
  status: z.literal("success"),
  hours: z.number(),
  data: z.record(z.string(), z.number()),
})

export type SeverityStats = z.infer<typeof SeverityStatsSchema>

export const ServiceStatsItemSchema = z.object({
  service: z.string(),
  count: z.number(),
  error_count: z.number(),
})

export type ServiceStatsItem = z.infer<typeof ServiceStatsItemSchema>

export const ServiceStatsSchema = z.object({
  status: z.literal("success"),
  hours: z.number(),
  data: z.array(ServiceStatsItemSchema),
})

export type ServiceStats = z.infer<typeof ServiceStatsSchema>

// ============================================
// SESSION TYPES
// ============================================

export const SessionStatusSchema = z.enum(["active", "archived", "deleted"])

export type SessionStatus = z.infer<typeof SessionStatusSchema>

export const SessionMetadataSchema = z.object({
  totalMessages: z.number(),
  totalCost: z.number(),
  tags: z.array(z.string()),
})

export type SessionMetadata = z.infer<typeof SessionMetadataSchema>

export const SessionSchema = z.object({
  id: z.string(),
  userId: z.string(),
  title: z.string(),
  status: SessionStatusSchema,
  createdAt: z.string(),
  updatedAt: z.string(),
  metadata: SessionMetadataSchema,
})

export type Session = z.infer<typeof SessionSchema>

export const MessageRoleSchema = z.enum(["user", "assistant", "system", "tool"])

export type MessageRole = z.infer<typeof MessageRoleSchema>

export const MessageSchema = z.object({
  id: z.string(),
  role: MessageRoleSchema,
  content: z.string(),
  timestamp: z.string(),
  metadata: z.record(z.string(), z.unknown()).optional(),
})

export type Message = z.infer<typeof MessageSchema>

export const CreateSessionRequestSchema = z.object({
  title: z.string(),
})

export type CreateSessionRequest = z.infer<typeof CreateSessionRequestSchema>

export const SessionsListResponseSchema = z.object({
  status: z.literal("success"),
  sessions: z.array(SessionSchema),
})

export type SessionsListResponse = z.infer<typeof SessionsListResponseSchema>

export const SessionDetailResponseSchema = z.object({
  status: z.literal("success"),
  session: SessionSchema,
  messages: z.array(MessageSchema),
})

export type SessionDetailResponse = z.infer<typeof SessionDetailResponseSchema>

// ============================================
// SAVED QUERIES TYPES
// ============================================

export const SavedQuerySchema = z.object({
  id: z.string(),
  userId: z.string(),
  name: z.string(),
  queryParams: z.record(z.string(), z.unknown()),
  createdAt: z.string(),
  lastRunAt: z.string(),
  runCount: z.number(),
})

export type SavedQuery = z.infer<typeof SavedQuerySchema>

export const SaveQueryRequestSchema = z.object({
  name: z.string(),
  query_params: z.record(z.string(), z.unknown()),
})

export type SaveQueryRequest = z.infer<typeof SaveQueryRequestSchema>

export const SavedQueriesResponseSchema = z.object({
  status: z.literal("success"),
  queries: z.array(SavedQuerySchema),
})

export type SavedQueriesResponse = z.infer<typeof SavedQueriesResponseSchema>

// ============================================
// CHAT TYPES
// ============================================

export const ChatRequestSchema = z.object({
  message: z.string(),
  session_id: z.string().optional(),
  context: z.record(z.string(), z.unknown()).optional(),
})

export type ChatRequest = z.infer<typeof ChatRequestSchema>

export const ChatEventTypeSchema = z.enum([
  "session",
  "on_chat_model_stream",
  "on_tool_start",
  "on_tool_end",
  "error",
])

export type ChatEventType = z.infer<typeof ChatEventTypeSchema>

export const ChatStreamEventSchema = z.object({
  type: z.string(),
  data: z.record(z.string(), z.unknown()),
})

export type ChatStreamEvent = z.infer<typeof ChatStreamEventSchema>

// ============================================
// ERROR TYPES
// ============================================

export const ApiErrorSchema = z.object({
  status: z.literal("error"),
  message: z.string().optional(),
  error_type: z.string().optional(),
  errors: z.array(z.string()).optional(),
})

export type ApiError = z.infer<typeof ApiErrorSchema>

// ============================================
// HEALTH TYPES
// ============================================

export const HealthResponseSchema = z.object({
  status: z.literal("ok"),
})

export type HealthResponse = z.infer<typeof HealthResponseSchema>

// ============================================
// GCP SERVICE TYPES (for dashboards)
// ============================================

export const CloudRunServiceSchema = z.object({
  name: z.string(),
  region: z.string(),
  url: z.string().optional(),
  latestRevision: z.string().optional(),
  status: z.enum(["READY", "DEPLOYING", "ERROR"]),
  lastDeployed: z.string().optional(),
})

export type CloudRunService = z.infer<typeof CloudRunServiceSchema>

export const CloudFunctionSchema = z.object({
  name: z.string(),
  runtime: z.string(),
  region: z.string(),
  trigger: z.string(),
  status: z.enum(["ACTIVE", "DEPLOYING", "OFFLINE"]),
  lastDeployed: z.string().optional(),
})

export type CloudFunction = z.infer<typeof CloudFunctionSchema>

export const GKEClusterSchema = z.object({
  name: z.string(),
  zone: z.string(),
  nodeCount: z.number(),
  status: z.enum(["RUNNING", "PROVISIONING", "STOPPED", "ERROR"]),
  k8sVersion: z.string().optional(),
})

export type GKECluster = z.infer<typeof GKEClusterSchema>

export const StorageBucketSchema = z.object({
  name: z.string(),
  location: z.string(),
  storageClass: z.string(),
  sizeBytes: z.number().optional(),
  objectCount: z.number().optional(),
})

export type StorageBucket = z.infer<typeof StorageBucketSchema>

export const BigQueryDatasetSchema = z.object({
  datasetId: z.string(),
  projectId: z.string(),
  location: z.string(),
  tableCount: z.number().optional(),
  sizeBytes: z.number().optional(),
})

export type BigQueryDataset = z.infer<typeof BigQueryDatasetSchema>

export const PubSubTopicSchema = z.object({
  name: z.string(),
  subscriptionCount: z.number(),
  messageRetentionDays: z.number().optional(),
})

export type PubSubTopic = z.infer<typeof PubSubTopicSchema>

// ============================================
// COST TYPES
// ============================================

export const CostByServiceSchema = z.object({
  service: z.string(),
  cost: z.number(),
  change: z.number(),
  budget: z.number().optional(),
})

export type CostByService = z.infer<typeof CostByServiceSchema>

export const CostSummarySchema = z.object({
  totalSpend: z.number(),
  budgetUsedPercent: z.number(),
  forecast: z.number(),
  vsLastMonth: z.number(),
  byService: z.array(CostByServiceSchema),
})

export type CostSummary = z.infer<typeof CostSummarySchema>
