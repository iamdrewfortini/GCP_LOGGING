#!/usr/bin/env python3
"""
Missing Cost Identification Script
Purpose: Identify where the $134/month (~99.2% of total billing) is coming from
Current: BigQuery only shows $0.035/day, but actual monthly is $135
Gap: Need to find Compute Engine, Storage, Functions, etc. costs
"""

import subprocess
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MissingCostAnalyzer:
    """Analyze where the missing $134/month is coming from"""
    
    def __init__(self):
        self.project_id = 'diatonic-ai-gcp'
        self.billing_account = '018EE0-B71384-D44551'  # Active account
        self.known_daily_bq_cost = 0.035  # From current BigQuery analysis
        self.target_monthly_cost = 135.0
        self.estimated_daily_gap = (self.target_monthly_cost / 30) - self.known_daily_bq_cost
        
    def check_current_billing_via_console(self):
        """Check what's visible in billing console"""
        logger.info("🔍 Checking current billing visibility...")
        
        # This would require manual verification, but let's structure the analysis
        analysis = {
            'known_costs': {
                'bigquery': {
                    'daily': self.known_daily_bq_cost,
                    'monthly_projected': self.known_daily_bq_cost * 30,
                    'source': 'INFORMATION_SCHEMA.JOBS_BY_PROJECT'
                }
            },
            'cost_gap': {
                'daily_gap': self.estimated_daily_gap,
                'monthly_gap': self.target_monthly_cost - (self.known_daily_bq_cost * 30),
                'percentage_missing': ((self.target_monthly_cost - (self.known_daily_bq_cost * 30)) / self.target_monthly_cost) * 100
            },
            'potential_sources': self._get_potential_cost_sources(),
            'investigation_plan': self._create_investigation_plan()
        }
        
        return analysis
    
    def _get_potential_cost_sources(self) -> List[Dict[str, Any]]:
        """Identify potential sources of the missing costs"""
        return [
            {
                'service': 'Compute Engine', 
                'service_id': '6F81-5844-456A',
                'likely_cost_drivers': ['VM instances', 'Persistent disks', 'Network egress'],
                'cost_estimate_range': '$50-100/month',
                'investigation_method': 'Check VM instances, disk usage, network transfer'
            },
            {
                'service': 'Cloud Storage',
                'service_id': '95FF-2EF5-5EA1', 
                'likely_cost_drivers': ['Storage buckets', 'Data transfer', 'Operations'],
                'cost_estimate_range': '$20-50/month',
                'investigation_method': 'Check bucket sizes, storage classes, transfer logs'
            },
            {
                'service': 'Cloud Run',
                'service_id': '152E-C115-5142',
                'likely_cost_drivers': ['CPU time', 'Memory usage', 'Request count'],
                'cost_estimate_range': '$10-30/month',
                'investigation_method': 'Check Cloud Run services, execution metrics'
            },
            {
                'service': 'Cloud Functions',
                'service_id': 'CF07-9B5E-8035',
                'likely_cost_drivers': ['Invocations', 'Compute time', 'Memory allocation'],
                'cost_estimate_range': '$5-20/month',
                'investigation_method': 'Check function execution logs, memory/cpu usage'
            },
            {
                'service': 'Networking',
                'service_ids': ['D5D1-5F71-F8A9', 'F25E-5C5C-EDA1'],
                'likely_cost_drivers': ['Load balancing', 'CDN usage', 'VPN', 'NAT gateway'],
                'cost_estimate_range': '$10-40/month',
                'investigation_method': 'Check networking components, data transfer'
            },
            {
                'service': 'Security/IAM',
                'service_ids': ['various'],
                'likely_cost_drivers': ['Secret Manager', 'KMS', 'Security Command Center'],
                'cost_estimate_range': '$5-15/month',
                'investigation_method': 'Check security services usage'
            },
            {
                'service': 'Monitoring/Logging',
                'service_ids': ['various'],
                'likely_cost_drivers': ['Cloud Logging ingestion', 'Cloud Monitoring metrics', 'Error Reporting'],
                'cost_estimate_range': '$10-25/month',
                'investigation_method': 'Check logging volume, monitoring usage'
            }
        ]
    
    def _create_investigation_plan(self) -> Dict[str, Any]:
        """Create systematic investigation plan"""
        return {
            'immediate_actions': [
                {
                    'action': 'Setup billing export',
                    'description': 'Enable BigQuery billing export in Cloud Console',
                    'priority': 'HIGH',
                    'estimated_time': '15 minutes',
                    'steps': [
                        'Go to https://console.cloud.google.com/billing',
                        f'Select billing account {self.billing_account}',
                        'Navigate to Billing Export',
                        'Enable BigQuery export',
                        f'Set dataset: {self.project_id}.billing_export',
                        'Wait 24 hours for data'
                    ]
                },
                {
                    'action': 'Check Compute Engine costs',
                    'description': 'Identify running VMs and their costs',
                    'priority': 'HIGH',
                    'estimated_time': '30 minutes',
                    'commands': [
                        'gcloud compute instances list --format="table(name,zone,status,machineType,creationTimestamp)"',
                        'gcloud compute disks list --format="table(name,zone,sizeGb,type,status)"',
                        'gcloud compute addresses list --global --format="table(name,address,status)"'
                    ]
                },
                {
                    'action': 'Check Cloud Storage costs',
                    'description': 'Analyze storage usage and transfer costs',
                    'priority': 'HIGH',
                    'estimated_time': '20 minutes',
                    'commands': [
                        'gsutil ls -L -b gs://*',
                        'gsutil du -s gs://*',
                        'gcloud logging read "resource.type=gcs_bucket" --limit=100 --format=json'
                    ]
                }
            ],
            'automated_discovery': [
                {
                    'method': 'Resource inventory',
                    'description': 'Scan all GCP resources across services',
                    'command': 'gcloud asset search-all-resources --format=json',
                    'analysis': 'Correlate resources with potential costs'
                },
                {
                    'method': 'Service usage analysis',
                    'description': 'Check which services are actively being used',
                    'command': 'gcloud services list --enabled --format="table(name,title)"',
                    'analysis': 'Map enabled services to cost potential'
                }
            ],
            'manual_verification': [
                {
                    'location': 'Cloud Console > Billing > Cost breakdown',
                    'description': 'Visual breakdown of costs by service',
                    'url': f'https://console.cloud.google.com/billing/{self.billing_account.replace("-", "")}/reports'
                },
                {
                    'location': 'Cloud Console > Billing > Cost table', 
                    'description': 'Detailed cost table with SKU breakdown',
                    'url': f'https://console.cloud.google.com/billing/{self.billing_account.replace("-", "")}/costbreakdown'
                }
            ]
        }
    
    def run_immediate_discovery(self) -> Dict[str, Any]:
        """Run immediate resource discovery to identify cost sources"""
        logger.info("🔎 Running immediate resource discovery...")
        
        discovery_results = {
            'compute_instances': self._check_compute_instances(),
            'storage_buckets': self._check_storage_buckets(),
            'cloud_run_services': self._check_cloud_run_services(),
            'enabled_services': self._check_enabled_services(),
            'resource_inventory': self._check_resource_inventory()
        }
        
        return discovery_results
    
    def _run_gcloud_command(self, command: str) -> Dict[str, Any]:
        """Run gcloud command and return parsed results"""
        try:
            logger.info(f"Running: {command}")
            result = subprocess.run(
                command.split(), 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            if result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {'raw_output': result.stdout.strip()}
            else:
                return {'status': 'no_output'}
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"Command failed: {command}")
            logger.warning(f"Error: {e.stderr}")
            return {'error': str(e), 'stderr': e.stderr}
        except Exception as e:
            logger.error(f"Unexpected error running command: {e}")
            return {'error': str(e)}
    
    def _check_compute_instances(self) -> Dict[str, Any]:
        """Check for Compute Engine instances"""
        instances = self._run_gcloud_command('gcloud compute instances list --format=json')
        disks = self._run_gcloud_command('gcloud compute disks list --format=json')
        
        analysis = {
            'instances': instances,
            'disks': disks,
            'cost_potential': 'unknown'
        }
        
        # Analyze potential costs
        if isinstance(instances, list) and len(instances) > 0:
            running_instances = [i for i in instances if i.get('status') == 'RUNNING']
            analysis['cost_potential'] = f'HIGH - {len(running_instances)} running instances'
            analysis['running_count'] = len(running_instances)
            
        return analysis
    
    def _check_storage_buckets(self) -> Dict[str, Any]:
        """Check Cloud Storage usage"""
        try:
            # List buckets
            buckets = self._run_gcloud_command('gsutil ls -L -b')
            
            # Get storage usage (this might require different approach)
            analysis = {
                'buckets': buckets,
                'cost_potential': 'unknown'
            }
            
            return analysis
            
        except Exception as e:
            return {'error': str(e), 'cost_potential': 'unknown'}
    
    def _check_cloud_run_services(self) -> Dict[str, Any]:
        """Check Cloud Run services"""
        services = self._run_gcloud_command('gcloud run services list --format=json')
        
        analysis = {
            'services': services,
            'cost_potential': 'unknown'
        }
        
        if isinstance(services, list) and len(services) > 0:
            analysis['cost_potential'] = f'MEDIUM - {len(services)} services'
            analysis['service_count'] = len(services)
            
        return analysis
    
    def _check_enabled_services(self) -> Dict[str, Any]:
        """Check enabled GCP services"""
        services = self._run_gcloud_command('gcloud services list --enabled --format=json')
        
        analysis = {
            'enabled_services': services,
            'cost_potential_services': []
        }
        
        # High-cost potential services
        high_cost_services = [
            'compute.googleapis.com',
            'storage.googleapis.com', 
            'run.googleapis.com',
            'cloudsql.googleapis.com',
            'container.googleapis.com',
            'cloudfunctions.googleapis.com'
        ]
        
        if isinstance(services, list):
            enabled_names = [s.get('name', '') for s in services]
            cost_services = [s for s in enabled_names if any(h in s for h in high_cost_services)]
            analysis['cost_potential_services'] = cost_services
            analysis['high_cost_service_count'] = len(cost_services)
            
        return analysis
    
    def _check_resource_inventory(self) -> Dict[str, Any]:
        """Get comprehensive resource inventory"""
        resources = self._run_gcloud_command('gcloud asset search-all-resources --format=json --limit=500')
        
        analysis = {
            'all_resources': resources,
            'resource_summary': {}
        }
        
        if isinstance(resources, list):
            # Group by asset type
            resource_types = {}
            for resource in resources:
                asset_type = resource.get('assetType', 'unknown')
                if asset_type not in resource_types:
                    resource_types[asset_type] = 0
                resource_types[asset_type] += 1
                
            analysis['resource_summary'] = resource_types
            analysis['total_resources'] = len(resources)
            
        return analysis
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive missing cost analysis report"""
        logger.info("📊 Generating comprehensive missing cost analysis...")
        
        # Run all analyses
        console_analysis = self.check_current_billing_via_console()
        discovery_results = self.run_immediate_discovery()
        
        report = {
            'summary': {
                'target_monthly_cost': self.target_monthly_cost,
                'known_bigquery_monthly': self.known_daily_bq_cost * 30,
                'missing_monthly': self.target_monthly_cost - (self.known_daily_bq_cost * 30),
                'missing_percentage': ((self.target_monthly_cost - (self.known_daily_bq_cost * 30)) / self.target_monthly_cost) * 100,
                'daily_gap': self.estimated_daily_gap
            },
            'console_analysis': console_analysis,
            'discovery_results': discovery_results,
            'recommendations': self._generate_recommendations(discovery_results),
            'next_steps': self._generate_next_steps()
        }
        
        return report
    
    def _generate_recommendations(self, discovery_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate recommendations based on discovery results"""
        recommendations = []
        
        # Check compute instances
        compute_analysis = discovery_results.get('compute_instances', {})
        if compute_analysis.get('running_count', 0) > 0:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'compute',
                'finding': f"{compute_analysis['running_count']} running compute instances detected",
                'action': 'Immediately set up Compute Engine billing monitoring',
                'potential_cost': 'HIGH - VMs can cost $50-200/month depending on type and usage'
            })
        
        # Check enabled services
        services_analysis = discovery_results.get('enabled_services', {})
        if services_analysis.get('high_cost_service_count', 0) > 0:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'services',
                'finding': f"{services_analysis['high_cost_service_count']} high-cost services enabled",
                'action': 'Set up billing export to capture all service costs',
                'potential_cost': 'VARIES - Each service can contribute $10-100/month'
            })
        
        # Resource inventory
        inventory_analysis = discovery_results.get('resource_inventory', {})
        if inventory_analysis.get('total_resources', 0) > 50:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'resources',
                'finding': f"{inventory_analysis['total_resources']} total resources detected",
                'action': 'Implement comprehensive resource cost tracking',
                'potential_cost': 'CUMULATIVE - Many small costs can add up to $100+/month'
            })
            
        return recommendations
    
    def _generate_next_steps(self) -> List[Dict[str, Any]]:
        """Generate concrete next steps"""
        return [
            {
                'step': 1,
                'action': 'Enable billing export',
                'description': 'Set up BigQuery billing export in Cloud Console',
                'urgency': 'IMMEDIATE',
                'time_estimate': '15 minutes',
                'blocking': True,
                'url': 'https://console.cloud.google.com/billing'
            },
            {
                'step': 2,
                'action': 'Deploy comprehensive billing function',
                'description': 'Run the deployment script we created',
                'urgency': 'HIGH',
                'time_estimate': '30 minutes',
                'blocking': False,
                'command': 'bash /home/daclab-ai/GCP_LOGGING/scripts/deploy_comprehensive_billing.sh'
            },
            {
                'step': 3,
                'action': 'Manual cost verification',
                'description': 'Check Cloud Console billing breakdown',
                'urgency': 'HIGH',
                'time_estimate': '20 minutes',
                'blocking': False,
                'url': f'https://console.cloud.google.com/billing/{self.billing_account.replace("-", "")}/reports'
            },
            {
                'step': 4,
                'action': 'Wait for billing data',
                'description': 'Wait 24 hours for billing export data to populate',
                'urgency': 'SCHEDULED',
                'time_estimate': '24 hours',
                'blocking': True
            },
            {
                'step': 5,
                'action': 'Run historical import',
                'description': 'Import 1+ year of historical billing data',
                'urgency': 'MEDIUM',
                'time_estimate': '2 hours',
                'blocking': False
            }
        ]

def main():
    """Main execution"""
    print("🔍 Missing Cost Analysis for GCP Billing")
    print("="*50)
    
    analyzer = MissingCostAnalyzer()
    report = analyzer.generate_report()
    
    # Print summary
    summary = report['summary']
    print(f"\n📊 COST GAP ANALYSIS:")
    print(f"   Target Monthly Cost: ${summary['target_monthly_cost']}")
    print(f"   Known BigQuery Cost: ${summary['known_bigquery_monthly']:.2f}/month")
    print(f"   Missing Cost: ${summary['missing_monthly']:.2f}/month ({summary['missing_percentage']:.1f}%)")
    print(f"   Daily Gap: ${summary['daily_gap']:.2f}/day")
    
    # Print key findings
    print(f"\n🔎 KEY FINDINGS:")
    discovery = report['discovery_results']
    
    # Compute instances
    compute = discovery.get('compute_instances', {})
    if compute.get('running_count', 0) > 0:
        print(f"   ⚠️  {compute['running_count']} RUNNING COMPUTE INSTANCES")
    
    # Enabled services
    services = discovery.get('enabled_services', {})
    if services.get('high_cost_service_count', 0) > 0:
        print(f"   ⚠️  {services['high_cost_service_count']} HIGH-COST SERVICES ENABLED")
    
    # Resources
    inventory = discovery.get('resource_inventory', {})
    if inventory.get('total_resources', 0) > 0:
        print(f"   ℹ️  {inventory['total_resources']} TOTAL GCP RESOURCES")
        
    # Print recommendations
    print(f"\n🚨 PRIORITY RECOMMENDATIONS:")
    for rec in report['recommendations']:
        print(f"   {rec['priority']}: {rec['finding']}")
        print(f"      → {rec['action']}")
        print(f"      → {rec['potential_cost']}")
        print()
    
    # Print next steps
    print(f"📋 IMMEDIATE NEXT STEPS:")
    for step in report['next_steps'][:3]:  # First 3 steps
        print(f"   {step['step']}. {step['action']} ({step['urgency']})")
        print(f"      {step['description']}")
        if 'command' in step:
            print(f"      Command: {step['command']}")
        if 'url' in step:
            print(f"      URL: {step['url']}")
        print()
    
    print("💡 The $134/month gap is likely from Compute Engine VMs, Storage, and other services")
    print("   not captured in BigQuery job billing. Enable billing export to get full visibility!")
    
    # Save detailed report
    report_file = '/home/daclab-ai/GCP_LOGGING/analysis/missing_cost_analysis.json'
    try:
        import os
        os.makedirs(os.path.dirname(report_file), exist_ok=True)
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n📄 Detailed report saved to: {report_file}")
    except Exception as e:
        logger.warning(f"Could not save report: {e}")

if __name__ == "__main__":
    main()