#!/bin/bash
# setup_master.sh
# Master script to orchestrate complete data ingestion setup

set -e

echo "🎯 GCP Logging Master Setup"
echo "=========================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}!${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_section() { echo -e "${BLUE}📋${NC} $1"; }

# Configuration
PROJECT_ID="${PROJECT_ID:-diatonic-ai-gcp}"
SETUP_MODE="${SETUP_MODE:-all}" # all|billing|assets|admin|validate

# Make all scripts executable
chmod +x scripts/*.sh scripts/*.py

echo "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Setup Mode: $SETUP_MODE"
echo ""

# Function to check prerequisites
check_prerequisites() {
    log_section "Checking Prerequisites"
    
    local errors=0
    
    # Check gcloud
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not installed"
        ((errors++))
    else
        log_info "gcloud CLI installed"
    fi
    
    # Check bq
    if ! command -v bq &> /dev/null; then
        log_error "BigQuery CLI not installed"
        ((errors++))
    else
        log_info "BigQuery CLI installed"
    fi
    
    # Check python3
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 not installed"
        ((errors++))
    else
        log_info "Python 3 installed"
    fi
    
    # Check authentication
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        log_error "Not authenticated with gcloud. Run: gcloud auth login"
        ((errors++))
    else
        log_info "gcloud authenticated"
    fi
    
    # Set project
    gcloud config set project $PROJECT_ID --quiet
    log_info "Project set: $PROJECT_ID"
    
    if [ $errors -gt 0 ]; then
        log_error "Prerequisites check failed. Fix errors above and retry."
        exit 1
    fi
    
    echo ""
}

# Function to apply base schema
apply_base_schema() {
    log_section "Applying Base Schema"
    
    if [ -f "infra/bigquery/03_standardization.sql" ]; then
        log_info "Applying standardization schema..."
        bq query --use_legacy_sql=false < infra/bigquery/03_standardization.sql
        log_info "Schema applied successfully"
    else
        log_warn "Base schema file not found, skipping..."
    fi
    
    echo ""
}

# Function to run setup scripts
run_setup_script() {
    local script=$1
    local name=$2
    
    log_section "Setting up $name"
    
    if [ -f "$script" ]; then
        chmod +x "$script"
        if ./"$script"; then
            log_info "$name setup completed"
        else
            log_error "$name setup failed"
            return 1
        fi
    else
        log_error "Setup script not found: $script"
        return 1
    fi
    
    echo ""
}

# Function to run validation
run_validation() {
    log_section "Running End-to-End Validation"
    
    if [ -f "scripts/validate_end_to_end.sql" ]; then
        log_info "Running validation queries..."
        
        # Save results to file
        VALIDATION_FILE="validation_results_$(date +%Y%m%d_%H%M%S).txt"
        
        {
            echo "=== GCP Logging Validation Results ==="
            echo "Date: $(date)"
            echo "Project: $PROJECT_ID"
            echo ""
            
            bq query --use_legacy_sql=false --max_rows=1000 < scripts/validate_end_to_end.sql
        } | tee "$VALIDATION_FILE"
        
        log_info "Validation results saved to: $VALIDATION_FILE"
        
        # Quick health check
        echo ""
        log_info "Quick Health Summary:"
        bq query --use_legacy_sql=false --format=table \
            "SELECT data_domain, health_status, total_rows 
             FROM (
               WITH summary_stats AS (
                 SELECT 'Logs' as data_domain, COUNT(*) as total_rows, MAX(log_date) as latest_data
                 FROM \`$PROJECT_ID.org_logs_canon.fact_logs\`
                 WHERE log_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                 UNION ALL
                 SELECT 'FinOps' as data_domain, COUNT(*) as total_rows, MAX(dt) as latest_data
                 FROM \`$PROJECT_ID.org_finops.bq_jobs_daily_v2\`
                 WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                 UNION ALL
                 SELECT 'Agent' as data_domain, COUNT(*) as total_rows, MAX(invocation_date) as latest_data
                 FROM \`$PROJECT_ID.org_agent.tool_invocations\`
                 WHERE invocation_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
               )
               SELECT data_domain, total_rows,
                 CASE WHEN total_rows > 0 THEN '✅ Has Data' ELSE '❌ No Data' END as health_status
               FROM summary_stats
             )" 2>/dev/null || log_warn "Health check query failed (expected if tables don't exist yet)"
        
    else
        log_error "Validation script not found"
        return 1
    fi
    
    echo ""
}

# Function to display next steps
show_next_steps() {
    log_section "Next Steps"
    
    cat << 'EOF'
🎯 IMMEDIATE ACTIONS REQUIRED:

1. 💰 Complete Billing Export Setup:
   - Go to: https://console.cloud.google.com/billing
   - Set up BigQuery export to org_finops dataset
   - Wait 24-48 hours for data to populate
   - Monitor: ./scripts/monitor_billing_export.sh

2. 🏗️ Set up Asset Inventory:
   - Run: ./scripts/create_scheduler_job.sh
   - Test: python3 scripts/load_asset_inventory.py
   - Verify: gsutil ls gs://diatonic-ai-gcp-asset-inventory/

3. 👥 Configure Admin SDK (if using Google Workspace):
   - Set environment: export DOMAIN="your-domain.com"
   - Complete domain-wide delegation setup
   - Test: python3 scripts/test_admin_sdk.py
   - Run: python3 scripts/fetch_admin_data.py

4. 🔄 Automation Setup:
   - Create daily Cloud Scheduler jobs
   - Set up monitoring/alerting
   - Configure backup retention

5. 📊 Monitoring:
   - Run validation weekly: bq query < scripts/validate_end_to_end.sql
   - Monitor costs and performance
   - Update schemas as needed

EOF

    echo ""
    log_info "Setup documentation: https://cloud.google.com/bigquery/docs"
    log_info "For support, check: docs/ directory and error logs"
    echo ""
}

# Main execution
main() {
    echo "Starting GCP Logging setup..."
    echo ""
    
    # Always check prerequisites
    check_prerequisites
    
    # Apply base schema
    apply_base_schema
    
    case $SETUP_MODE in
        "all")
            log_info "Running complete setup..."
            
            # Run all setup scripts
            if ! run_setup_script "scripts/setup_billing_export.sh" "Billing Export"; then
                log_warn "Billing export setup failed, continuing..."
            fi
            
            if ! run_setup_script "scripts/setup_asset_inventory.sh" "Asset Inventory"; then
                log_warn "Asset inventory setup failed, continuing..."
            fi
            
            if ! run_setup_script "scripts/setup_admin_sdk.sh" "Admin SDK"; then
                log_warn "Admin SDK setup failed, continuing..."
            fi
            
            # Run validation
            run_validation
            ;;
            
        "billing")
            run_setup_script "scripts/setup_billing_export.sh" "Billing Export"
            ;;
            
        "assets") 
            run_setup_script "scripts/setup_asset_inventory.sh" "Asset Inventory"
            ;;
            
        "admin")
            run_setup_script "scripts/setup_admin_sdk.sh" "Admin SDK"
            ;;
            
        "validate")
            run_validation
            ;;
            
        *)
            log_error "Invalid setup mode: $SETUP_MODE"
            log_info "Valid modes: all, billing, assets, admin, validate"
            exit 1
            ;;
    esac
    
    show_next_steps
    
    log_info "🎉 Master setup completed!"
    echo ""
    echo "📁 Generated files:"
    find scripts/ -name "*.sh" -o -name "*.py" -o -name "*.sql" | grep -E "(monitor|load|fetch|merge|transform)" | sort
    echo ""
    echo "📋 To run individual components:"
    echo "  ./scripts/setup_master.sh billing   # Billing export only"
    echo "  ./scripts/setup_master.sh assets    # Asset inventory only" 
    echo "  ./scripts/setup_master.sh admin     # Admin SDK only"
    echo "  ./scripts/setup_master.sh validate  # Validation only"
}

# Handle script arguments
case "${1:-}" in
    "billing"|"assets"|"admin"|"validate")
        SETUP_MODE=$1
        ;;
    "--help"|"-h")
        echo "Usage: $0 [billing|assets|admin|validate|all]"
        echo ""
        echo "Modes:"
        echo "  all (default) - Run complete setup"
        echo "  billing       - Set up billing export only"
        echo "  assets        - Set up asset inventory only"  
        echo "  admin         - Set up Admin SDK only"
        echo "  validate      - Run validation queries only"
        exit 0
        ;;
    "")
        SETUP_MODE="all"
        ;;
    *)
        log_error "Unknown argument: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac

# Run main function
main