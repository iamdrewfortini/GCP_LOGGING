-- Org Enterprise SCD2 merge operations
-- Run after staging tables are populated
-- Project: diatonic-ai-gcp

-- Dim Org (from Asset Inventory)
MERGE `diatonic-ai-gcp.org_enterprise.dim_org` T
USING (
  SELECT DISTINCT
    JSON_VALUE(payload, '$.organization') AS org_id,
    JSON_VALUE(payload, '$.displayName') AS org_name,
    JSON_VALUE(payload, '$.parent') AS parent_org_id,
    'asset_inventory' AS source_system,
    SAFE_CAST(fetched_at AS DATE) AS active_from,
    payload
  FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
  WHERE JSON_VALUE(payload, '$.organization') IS NOT NULL
) S
ON T.org_id = S.org_id AND T.is_current = TRUE
WHEN MATCHED AND (T.org_name IS DISTINCT FROM S.org_name OR T.parent_org_id IS DISTINCT FROM S.parent_org_id) THEN
  UPDATE SET is_current = FALSE, active_to = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY), updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (org_id, org_name, parent_org_id, region, active_from, active_to, is_current, source_system, trace_id, span_id, created_at, labels)
  VALUES (S.org_id, S.org_name, S.parent_org_id, NULL, COALESCE(S.active_from, CURRENT_DATE()), NULL, TRUE, S.source_system, NULL, NULL, CURRENT_TIMESTAMP(), NULL);

-- Dim Project
MERGE `diatonic-ai-gcp.org_enterprise.dim_project` T
USING (
  SELECT DISTINCT
    JSON_VALUE(payload, '$.project') AS project_id,
    JSON_VALUE(payload, '$.projectNumber') AS project_number,
    JSON_VALUE(payload, '$.organization') AS org_id,
    JSON_VALUE(payload, '$.displayName') AS project_name,
    JSON_VALUE(payload, '$.parent') AS folder_id,
    JSON_VALUE(payload, '$.state') AS lifecycle_state,
    NULL AS billing_account,
    SAFE_CAST(fetched_at AS DATE) AS active_from
  FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`
  WHERE JSON_VALUE(payload, '$.project') IS NOT NULL
) S
ON T.project_id = S.project_id AND T.is_current = TRUE
WHEN MATCHED AND (T.project_name IS DISTINCT FROM S.project_name OR T.lifecycle_state IS DISTINCT FROM S.lifecycle_state) THEN
  UPDATE SET is_current = FALSE, active_to = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY), updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (project_id, project_number, org_id, project_name, folder_id, lifecycle_state, billing_account, active_from, active_to, is_current, source_system, trace_id, span_id, created_at, labels)
  VALUES (S.project_id, S.project_number, S.org_id, S.project_name, S.folder_id, S.lifecycle_state, S.billing_account, COALESCE(S.active_from, CURRENT_DATE()), NULL, TRUE, 'asset_inventory', NULL, NULL, CURRENT_TIMESTAMP(), NULL);

-- Dim Service (from Service Usage)
MERGE `diatonic-ai-gcp.org_enterprise.dim_service` T
USING (
  SELECT DISTINCT
    service_name AS service_id,
    service_name AS service_name,
    NULL AS application_id,
    NULL AS project_id,
    NULL AS runtime,
    NULL AS owner_team,
    SAFE_CAST(fetched_at AS DATE) AS active_from
  FROM `diatonic-ai-gcp.org_enterprise.stg_service_usage`
  WHERE service_name IS NOT NULL
) S
ON T.service_id = S.service_id AND T.is_current = TRUE
WHEN MATCHED AND (T.service_name IS DISTINCT FROM S.service_name) THEN
  UPDATE SET is_current = FALSE, active_to = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY), updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (service_id, service_name, application_id, project_id, runtime, owner_team, active_from, active_to, is_current, source_system, trace_id, span_id, created_at, labels)
  VALUES (S.service_id, S.service_name, S.application_id, S.project_id, S.runtime, S.owner_team, COALESCE(S.active_from, CURRENT_DATE()), NULL, TRUE, 'service_usage', NULL, NULL, CURRENT_TIMESTAMP(), NULL);

-- Dim Workforce Member (from Admin SDK users)
MERGE `diatonic-ai-gcp.org_enterprise.dim_workforce_member` T
USING (
  SELECT
    JSON_VALUE(payload, '$.primaryEmail') AS member_id,
    JSON_VALUE(payload, '$.primaryEmail') AS email,
    JSON_VALUE(payload, '$.name.fullName') AS display_name,
    NULL AS org_id,
    JSON_VALUE(payload, '$.relations[0].value') AS manager_id,
    JSON_VALUE(payload, '$.orgUnitPath') AS employment_type,
    SAFE_CAST(fetched_at AS DATE) AS active_from
  FROM `diatonic-ai-gcp.org_enterprise.stg_admin_users`
  WHERE JSON_VALUE(payload, '$.primaryEmail') IS NOT NULL
) S
ON T.member_id = S.member_id AND T.is_current = TRUE
WHEN MATCHED AND (T.display_name IS DISTINCT FROM S.display_name OR T.manager_id IS DISTINCT FROM S.manager_id) THEN
  UPDATE SET is_current = FALSE, active_to = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY), updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (member_id, email, display_name, org_id, manager_id, employment_type, active_from, active_to, is_current, source_system, trace_id, span_id, created_at, labels)
  VALUES (S.member_id, S.email, S.display_name, S.org_id, S.manager_id, S.employment_type, COALESCE(S.active_from, CURRENT_DATE()), NULL, TRUE, 'admin_sdk', NULL, NULL, CURRENT_TIMESTAMP(), NULL);

-- Fact Policy (from Asset Inventory IAM policies if present)
INSERT INTO `diatonic-ai-gcp.org_enterprise.fact_policy` (
  policy_snapshot_date, project_id, resource, member, role, condition, origin, trace_id, span_id, source_system, ingestion_method, created_at
)
SELECT
  SAFE_CAST(fetched_at AS DATE) AS policy_snapshot_date,
  JSON_VALUE(payload, '$.project') AS project_id,
  JSON_VALUE(payload, '$.name') AS resource,
  member,
  role,
  condition,
  'asset_inventory' AS origin,
  NULL AS trace_id,
  NULL AS span_id,
  'org_model' AS source_system,
  'asset_export' AS ingestion_method,
  CURRENT_TIMESTAMP()
FROM (
  SELECT fetched_at, payload, iam_member AS member, iam_role AS role, iam_condition AS condition
  FROM (
    SELECT fetched_at, payload,
           JSON_EXTRACT_SCALAR(binding, '$.members[0]') AS iam_member,
           JSON_EXTRACT_SCALAR(binding, '$.role') AS iam_role,
           JSON_EXTRACT_SCALAR(binding, '$.condition') AS iam_condition,
           binding
    FROM `diatonic-ai-gcp.org_enterprise.stg_asset_inventory`,
    UNNEST(JSON_QUERY_ARRAY(payload, '$.iamPolicy.bindings')) AS binding
  )
) WHERE member IS NOT NULL AND project_id IS NOT NULL;

-- Fact Usage (daily agg from logs_canon)
INSERT INTO `diatonic-ai-gcp.org_enterprise.fact_usage` (
  usage_date, project_id, service_id, application_id, environment_id,
  request_count, error_count, success_count, latency_p50_ms, latency_p95_ms, cost_usd,
  trace_id, span_id, source_system, ingestion_method, created_at, updated_at
)
SELECT
  log_date AS usage_date,
  NULL AS project_id,
  service_name AS service_id,
  NULL AS application_id,
  NULL AS environment_id,
  COUNTIF(is_request) AS request_count,
  COUNTIF(is_error) AS error_count,
  COUNTIF(is_request AND NOT is_error) AS success_count,
  APPROX_QUANTILES(http_latency_ms, 100)[OFFSET(50)] AS latency_p50_ms,
  APPROX_QUANTILES(http_latency_ms, 100)[OFFSET(95)] AS latency_p95_ms,
  NULL AS cost_usd,
  NULL AS trace_id,
  NULL AS span_id,
  'logs' AS source_system,
  'bq_insert_select' AS ingestion_method,
  CURRENT_TIMESTAMP() AS created_at,
  CURRENT_TIMESTAMP() AS updated_at
FROM `diatonic-ai-gcp.org_logs_canon.fact_logs`
WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY usage_date, service_id;
