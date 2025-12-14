CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.view_canonical_logs` AS

WITH unioned_logs AS (
    -- 1. Cloud Audit Logs (Activity)
    SELECT 
        timestamp as event_ts,
        receiveTimestamp as receive_ts,
        'cloudaudit_activity' as source_table,
        resource.type as resource_type,
        resource.labels.project_id as project_id,
        COALESCE(resource.labels.service_name, resource.labels.module_id, '') as service,
        severity,
        trace,
        spanId,
        protoPayload.methodName as operation,
        '' as message, -- Audit logs usually have details in protoPayload
        TO_JSON_STRING(protoPayload) as json_payload_str,
        TO_JSON_STRING(labels) as labels_json
    FROM `{project_id}.{dataset_id}.cloudaudit_googleapis_com_activity`
    
    UNION ALL

    -- 2. Cloud Run Stdout
    SELECT 
        timestamp as event_ts,
        receiveTimestamp as receive_ts,
        'run_stdout' as source_table,
        resource.type as resource_type,
        resource.labels.project_id as project_id,
        resource.labels.service_name as service,
        severity,
        trace,
        spanId,
        '' as operation,
        textPayload as message,
        TO_JSON_STRING(jsonPayload) as json_payload_str,
        TO_JSON_STRING(labels) as labels_json
    FROM `{project_id}.{dataset_id}.run_googleapis_com_stdout`

    UNION ALL

    -- 3. Cloud Run Stderr
    SELECT 
        timestamp as event_ts,
        receiveTimestamp as receive_ts,
        'run_stderr' as source_table,
        resource.type as resource_type,
        resource.labels.project_id as project_id,
        resource.labels.service_name as service,
        severity,
        trace,
        spanId,
        '' as operation,
        textPayload as message,
        TO_JSON_STRING(jsonPayload) as json_payload_str,
        TO_JSON_STRING(labels) as labels_json
    FROM `{project_id}.{dataset_id}.run_googleapis_com_stderr`

    UNION ALL

    -- 4. Syslog (VMs)
    SELECT 
        timestamp as event_ts,
        receiveTimestamp as receive_ts,
        'syslog' as source_table,
        resource.type as resource_type,
        resource.labels.project_id as project_id,
        '' as service,
        severity,
        trace,
        spanId,
        '' as operation,
        textPayload as message,
        TO_JSON_STRING(jsonPayload) as json_payload_str,
        TO_JSON_STRING(labels) as labels_json
    FROM `{project_id}.{dataset_id}.syslog`
)

SELECT 
    event_ts,
    receive_ts,
    source_table,
    resource_type,
    project_id,
    service,
    severity,
    trace,
    spanId,
    operation,
    -- Fallback strategy for the main "message" to display
    COALESCE(
        IF(message != '', message, NULL), 
        JSON_VALUE(json_payload_str, '$.message'), 
        JSON_VALUE(json_payload_str, '$.msg'),
        'No message content'
    ) as display_message,
    json_payload_str,
    labels_json
FROM unioned_logs
