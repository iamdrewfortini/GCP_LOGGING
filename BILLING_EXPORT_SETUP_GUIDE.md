# Billing Export Setup Guide

## 🎯 OBJECTIVE
Enable BigQuery export for billing account 018EE0-B71384-D44551 to capture ALL GCP service costs ($135/month).

## 📋 STEP-BY-STEP PROCESS

### Step 1: Access Billing Console
1. Open: https://console.cloud.google.com/billing/018EE0B71384D44551
2. Ensure you're logged in with billing administrator permissions
3. Verify you see "DiatonicVisuals-projects" billing account

### Step 2: Navigate to Billing Export
1. In the left sidebar, click "Billing export"
2. You should see options for "BigQuery export" and "File export"
3. Click on "BigQuery export" tab

### Step 3: Configure BigQuery Export
1. Click "EDIT SETTINGS" or "CREATE EXPORT"
2. **Project**: Select "diatonic-ai-gcp"
3. **Dataset**: Enter "billing_export"
4. **Table prefix**: Enter "gcp_billing_export_018EE0_B71384_D44551"
5. **Enable detailed usage cost data**: ✅ CHECKED
6. **Enable pricing data**: ✅ CHECKED (if available)
7. **Partition settings**: Daily (recommended)

### Step 4: Enable Export
1. Click "SAVE" or "CREATE EXPORT"
2. Wait for confirmation message
3. Note: First data will appear within 24 hours

### Step 5: Verify Setup
Run this command to check if the dataset was created:
```bash
bq ls -d diatonic-ai-gcp:billing_export
```

Expected: Dataset should exist (may be empty initially)

## 🔍 VERIFICATION COMMANDS

After 24-48 hours, verify data is flowing:
```bash
# Check if export table exists and has data
bq query --use_legacy_sql=false "
SELECT 
  COUNT(*) as record_count,
  MIN(export_time) as earliest_export,
  MAX(export_time) as latest_export,
  COUNT(DISTINCT service.description) as service_count,
  SUM(cost) as total_cost_captured
FROM \`diatonic-ai-gcp.billing_export.gcp_billing_export_018EE0_B71384_D44551\`"

# Expected: record_count > 0, service_count > 5, total_cost > $3-5/day
```

## ⚠️ TROUBLESHOOTING

### Issue: "Access Denied"
- Ensure you have billing administrator role
- Check you're in the correct organization/project

### Issue: "Dataset creation failed" 
- Verify BigQuery API is enabled in diatonic-ai-gcp
- Ensure billing account has permissions to write to the project

### Issue: "No data after 48 hours"
- Check billing export is enabled and running
- Verify there are actual costs being generated
- Check export settings are correct

## ✅ COMPLETION CRITERIA
- [ ] Billing export enabled in Console
- [ ] Dataset `diatonic-ai-gcp.billing_export` exists
- [ ] First data appears within 24-48 hours
- [ ] Multiple services (5+) showing costs
- [ ] Daily cost totals match expected $4-5/day ($135/month)