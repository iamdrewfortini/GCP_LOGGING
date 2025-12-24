-- Merge Admin SDK data into workforce dimensional tables
-- Run this after loading staging data

-- Merge users into dim_workforce_member
MERGE `diatonic-ai-gcp.org_enterprise.dim_workforce_member` AS target
USING (
  SELECT DISTINCT
    JSON_EXTRACT_SCALAR(payload, '$.id') as member_id,
    JSON_EXTRACT_SCALAR(payload, '$.primaryEmail') as email,
    JSON_EXTRACT_SCALAR(payload, '$.name.fullName') as display_name,
    JSON_EXTRACT_SCALAR(payload, '$.orgUnitPath') as org_id,
    JSON_EXTRACT_SCALAR(payload, '$.relations[0].value') as manager_id,
    JSON_EXTRACT_SCALAR(payload, '$.employeeType') as employment_type,
    CURRENT_DATE() as active_from,
    CAST(NULL AS DATE) as active_to,
    NOT JSON_EXTRACT_SCALAR(payload, '$.suspended') = 'true' as is_current,
    'google_admin_sdk' as source_system,
    GENERATE_UUID() as trace_id,
    GENERATE_UUID() as span_id,
    CURRENT_TIMESTAMP() as created_at,
    CURRENT_TIMESTAMP() as updated_at,
    payload as labels
  FROM `diatonic-ai-gcp.org_enterprise.stg_admin_users`
  WHERE data_type = 'users'
    AND DATE(fetched_at) = CURRENT_DATE()
) AS source
ON target.member_id = source.member_id AND target.is_current = TRUE

WHEN NOT MATCHED THEN
  INSERT (member_id, email, display_name, org_id, manager_id, employment_type,
          active_from, active_to, is_current, source_system, trace_id, span_id,
          created_at, updated_at, labels)
  VALUES (source.member_id, source.email, source.display_name, source.org_id,
          source.manager_id, source.employment_type, source.active_from,
          source.active_to, source.is_current, source.source_system,
          source.trace_id, source.span_id, source.created_at, source.updated_at,
          source.labels)

WHEN MATCHED AND (
  target.email != source.email OR
  target.display_name != source.display_name OR
  target.org_id != source.org_id OR
  target.employment_type != source.employment_type OR
  target.is_current != source.is_current
) THEN UPDATE SET
  active_to = CURRENT_DATE(),
  is_current = FALSE,
  updated_at = CURRENT_TIMESTAMP();
