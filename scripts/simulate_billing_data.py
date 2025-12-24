#!/usr/bin/env python3
"""
Create simulated billing data for testing the FinOps pipeline
Since billing export setup requires Console access, this creates test data
"""

import json
from datetime import datetime, timedelta
import random

# Configuration
PROJECT_ID = "diatonic-ai-gcp"
DATASET_ID = "org_finops"
TABLE_ID = "bq_billing_export"

def generate_sample_billing_data(days=7):
    """Generate sample billing data for the last N days"""
    
    services = [
        "BigQuery", "Cloud Storage", "Compute Engine", 
        "Cloud Functions", "Cloud Run", "Firebase"
    ]
    
    skus = [
        "BigQuery Analysis", "BigQuery Storage", "Standard Storage",
        "N1 Predefined Instance Core running", "Cloud Function Invocations",
        "Cloud Run CPU Allocation", "Firebase Hosting"
    ]
    
    projects = [PROJECT_ID]
    
    records = []
    
    for day_offset in range(days):
        date = datetime.utcnow() - timedelta(days=day_offset)
        
        # Generate 10-50 records per day
        daily_records = random.randint(10, 50)
        
        for _ in range(daily_records):
            service = random.choice(services)
            sku = random.choice(skus)
            project_id = random.choice(projects)
            
            # Generate realistic costs (mostly small, some larger)
            if random.random() < 0.8:
                cost = round(random.uniform(0.01, 5.0), 4)
            else:
                cost = round(random.uniform(5.0, 100.0), 2)
            
            record = {
                "billing_account_id": "018EE0-B71384-D44551",
                "service": {"id": service.lower().replace(" ", "_"), "description": service},
                "sku": {"id": sku.lower().replace(" ", "_"), "description": sku},
                "usage_start_time": date.isoformat() + "Z",
                "usage_end_time": (date + timedelta(hours=1)).isoformat() + "Z",
                "project": {"id": project_id, "number": "845772051724", "name": project_id},
                "cost": cost,
                "currency": "USD",
                "usage": {"amount": random.uniform(1, 1000), "unit": "byte-seconds" if "Storage" in sku else "requests"},
                "credits": [],
                "invoice": {"month": date.strftime("%Y%m")},
                "cost_type": "regular",
                "location": {"location": "us", "country": "US", "region": "us-central1"}
            }
            
            records.append(record)
    
    return records

def main():
    """Generate and save sample billing data"""
    print("🧪 Generating sample billing data for testing...")
    
    # Generate sample data
    billing_records = generate_sample_billing_data(30)  # 30 days of data
    
    # Save to JSON file for loading
    output_file = "/tmp/sample_billing_data.json"
    with open(output_file, 'w') as f:
        for record in billing_records:
            f.write(json.dumps(record) + '\n')
    
    print(f"✅ Generated {len(billing_records)} sample billing records")
    print(f"📁 Saved to: {output_file}")
    print(f"💡 Load with: bq load --source_format=NEWLINE_DELIMITED_JSON {PROJECT_ID}:{DATASET_ID}.{TABLE_ID} {output_file}")
    
    return output_file

if __name__ == "__main__":
    main()