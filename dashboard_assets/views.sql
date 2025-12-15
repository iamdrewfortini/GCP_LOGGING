-- Errors by endpoint view
CREATE OR REPLACE VIEW `central_logging_v1.errors_by_endpoint` AS
SELECT
  service,
  requestUrl,
  status,
  COUNT(*) AS error_count,
  MIN(event_ts) AS first_seen,
  MAX(event_ts) AS last_seen
FROM `central_logging_v1.view_canonical_logs`
WHERE severity = 'ERROR' AND status >= 400
GROUP BY service, requestUrl, status;

-- Latency p95 view
CREATE OR REPLACE VIEW `central_logging_v1.latency_p95` AS
SELECT
  service,
  requestUrl,
  TIMESTAMP_TRUNC(event_ts, HOUR) AS hour,
  APPROX_QUANTILES(latency_s, 100)[OFFSET(95)] AS p95_latency
FROM `central_logging_v1.view_canonical_logs`
WHERE latency_s IS NOT NULL
GROUP BY service, requestUrl, hour;

-- Sessions failures view
CREATE OR REPLACE VIEW `central_logging_v1.sessions_failures` AS
SELECT *
FROM `central_logging_v1.view_canonical_logs`
WHERE service = 'glass-pane' AND requestUrl LIKE '%/api/sessions%' AND status >= 500;