# Design Document: Multi-Cloud Foundation

## Overview

The Multi-Cloud Foundation extends Glass Pane's existing AI intelligence stack to support unified management of cloud infrastructure across AWS, GCP, Azure, and DigitalOcean. This design builds on the established LangGraph agent, Firebase/BigQuery dual-write storage, and MCP tool system to provide:

- **Secure cloud account connection** with encrypted credential storage
- **Automated resource discovery** across multiple cloud providers
- **Real-time metrics collection** with time-series storage
- **Unified dashboard** for cross-cloud visibility
- **Integration with existing AI agent** for intelligent infrastructure management

This foundation enables future phases including cost optimization, project management, and advanced AI-powered automation.

### Design Principles

1. **Build on existing foundation** - Leverage current LangGraph, Firebase, BigQuery, and MCP systems
2. **Security first** - Encrypt credentials, use least-privilege access, audit all actions
3. **Provider abstraction** - Unified resource model across clouds for consistent UX
4. **Incremental adoption** - Start with read-only operations, expand to management
5. **Cost conscious** - Respect API rate limits, cache aggressively, partition data
6. **Observable** - Log all cloud API calls, track costs, monitor health

## Architecture

### High-Level Component Diagram

```mermaid
graph TB
    subgraph "Frontend (React)"
        UI[Multi-Cloud Dashboard]
        CloudUI[Cloud Account Manager]
        ResourceUI[Resource Browser]
    end
    
    subgraph "Backend (FastAPI)"
        API[/api/cloud/*]
        CloudSvc[Cloud Service]
        DiscoverySvc[Discovery Service]
        MetricsSvc[Metrics Service]
    end
    
    subgraph "Cloud Connectors"
        AWS[AWS Connector]
        GCP[GCP Connector]
        Azure[Azure Connector]
        DO[DigitalOcean Connector]
    end
    
    subgraph "Storage Layer"
        FS[(Firestore<br/>Hot Path)]
        BQ[(BigQuery<br/>Cold Path)]
        TS[(TimescaleDB<br/>Metrics)]
        Vault[Credential Vault<br/>Secret Manager]
    end
    
    subgraph "Workers (Cloud Functions)"
        DiscoveryWorker[Discovery Worker]
        MetricsWorker[Metrics Collector]
        HealthWorker[Health Checker]
    end
    
    subgraph "Existing AI Stack"
        Agent[LangGraph Agent]
        MCPTools[MCP Tool Registry]
    end
    
    UI --> API
    CloudUI --> API
    ResourceUI --> API
    
    API --> CloudSvc
    API --> DiscoverySvc
    API --> MetricsSvc
    
    CloudSvc --> Vault
    CloudSvc --> AWS
    CloudSvc --> GCP
    CloudSvc --> Azure
    CloudSvc --> DO
    
    DiscoverySvc --> DiscoveryWorker
    MetricsSvc --> MetricsWorker
    
    DiscoveryWorker --> AWS
    DiscoveryWorker --> GCP
    DiscoveryWorker --> Azure
    DiscoveryWorker --> DO
    
    MetricsWorker --> AWS
    MetricsWorker --> GCP
    MetricsWorker --> Azure
    MetricsWorker --> DO
    
    CloudSvc --> FS
    DiscoveryWorker --> FS
    DiscoveryWorker --> BQ
    MetricsWorker --> TS
    
    HealthWorker --> FS
    
    Agent --> MCPTools
    MCPTools --> CloudSvc
    MCPTools --> DiscoverySvc
```

### Integration with Existing Stack

The multi-cloud foundation integrates seamlessly with Glass Pane's existing architecture:

**Firestore (Hot Path)**
- Cloud accounts and credentials metadata
- Resource inventory (last 30 days)
- Real-time health status
- User preferences for cloud views

**BigQuery (Cold Path)**
- Cloud API call audit logs
- Resource change history
- Long-term cost data
- Analytics and reporting

**TimescaleDB (New)**
- Time-series metrics (CPU, memory, network)
- High-frequency data (1-minute granularity)
- Automatic downsampling and retention

**MCP Tool System**
- New cloud management tools (list_resources, get_metrics, etc.)
- Follows existing YAML spec format
- Integrates with LangGraph agent for AI-powered queries

## Components and Interfaces

### 1. Cloud Connector Interface

All cloud providers implement a common interface for consistency:

```python
# src/cloud/base_connector.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

class CloudCredentials(BaseModel):
    """Base credentials model"""
    provider: str
    account_id: str
    
class AWSCredentials(CloudCredentials):
    provider: str = "aws"
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"
    
class GCPCredentials(CloudCredentials):
    provider: str = "gcp"
    project_id: str
    service_account_json: str
    
class AzureCredentials(CloudCredentials):
    provider: str = "azure"
    subscription_id: str
    tenant_id: str
    client_id: str
    client_secret: str
    
class DOCredentials(CloudCredentials):
    provider: str = "digitalocean"
    api_token: str

class Resource(BaseModel):
    """Unified resource model"""
    id: str
    name: str
    type: str  # compute, database, storage, network
    provider: str
    region: str
    status: str
    tags: Dict[str, str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

class Metric(BaseModel):
    """Time-series metric"""
    resource_id: str
    metric_name: str
    value: float
    unit: str
    timestamp: datetime
    labels: Dict[str, str]

class BaseCloudConnector(ABC):
    """Abstract base class for cloud provider connectors"""
    
    def __init__(self, credentials: CloudCredentials):
        self.credentials = credentials
        self.provider = credentials.provider
    
    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Verify credentials are valid and have required permissions"""
        pass
    
    @abstractmethod
    async def discover_resources(self) -> List[Resource]:
        """Discover all resources in the account"""
        pass
    
    @abstractmethod
    async def get_resource(self, resource_id: str) -> Optional[Resource]:
        """Get details for a specific resource"""
        pass
    
    @abstractmethod
    async def get_metrics(
        self,
        resource_id: str,
        metric_names: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Metric]:
        """Fetch metrics for a resource"""
        pass
    
    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """Check account health and API connectivity"""
        pass
```

### 2. AWS Connector Implementation

```python
# src/cloud/aws_connector.py
import boto3
from botocore.exceptions import ClientError
from typing import List, Optional
from datetime import datetime, timedelta

class AWSConnector(BaseCloudConnector):
    """AWS cloud provider connector"""
    
    def __init__(self, credentials: AWSCredentials):
        super().__init__(credentials)
        self.session = boto3.Session(
            aws_access_key_id=credentials.access_key_id,
            aws_secret_access_key=credentials.secret_access_key,
            region_name=credentials.region
        )
    
    async def validate_credentials(self) -> bool:
        """Verify AWS credentials using STS GetCallerIdentity"""
        try:
            sts = self.session.client('sts')
            response = sts.get_caller_identity()
            return response['ResponseMetadata']['HTTPStatusCode'] == 200
        except ClientError:
            return False
    
    async def discover_resources(self) -> List[Resource]:
        """Discover EC2, RDS, S3, Lambda resources"""
        resources = []
        
        # EC2 Instances
        ec2 = self.session.client('ec2')
        instances = ec2.describe_instances()
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                resources.append(Resource(
                    id=instance['InstanceId'],
                    name=self._get_tag_value(instance.get('Tags', []), 'Name') or instance['InstanceId'],
                    type='compute',
                    provider='aws',
                    region=self.credentials.region,
                    status=instance['State']['Name'],
                    tags=self._parse_tags(instance.get('Tags', [])),
                    metadata={
                        'instance_type': instance['InstanceType'],
                        'vpc_id': instance.get('VpcId'),
                        'subnet_id': instance.get('SubnetId'),
                        'public_ip': instance.get('PublicIpAddress'),
                        'private_ip': instance.get('PrivateIpAddress')
                    },
                    created_at=instance['LaunchTime'],
                    updated_at=datetime.utcnow()
                ))
        
        # RDS Instances
        rds = self.session.client('rds')
        db_instances = rds.describe_db_instances()
        for db in db_instances['DBInstances']:
            resources.append(Resource(
                id=db['DBInstanceIdentifier'],
                name=db['DBInstanceIdentifier'],
                type='database',
                provider='aws',
                region=self.credentials.region,
                status=db['DBInstanceStatus'],
                tags=self._parse_tags(db.get('TagList', [])),
                metadata={
                    'engine': db['Engine'],
                    'engine_version': db['EngineVersion'],
                    'instance_class': db['DBInstanceClass'],
                    'storage_gb': db['AllocatedStorage'],
                    'endpoint': db.get('Endpoint', {}).get('Address')
                },
                created_at=db['InstanceCreateTime'],
                updated_at=datetime.utcnow()
            ))
        
        # S3 Buckets
        s3 = self.session.client('s3')
        buckets = s3.list_buckets()
        for bucket in buckets['Buckets']:
            resources.append(Resource(
                id=bucket['Name'],
                name=bucket['Name'],
                type='storage',
                provider='aws',
                region=self._get_bucket_region(s3, bucket['Name']),
                status='active',
                tags={},
                metadata={'bucket_name': bucket['Name']},
                created_at=bucket['CreationDate'],
                updated_at=datetime.utcnow()
            ))
        
        return resources
    
    async def get_metrics(
        self,
        resource_id: str,
        metric_names: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Metric]:
        """Fetch CloudWatch metrics"""
        cloudwatch = self.session.client('cloudwatch')
        metrics = []
        
        for metric_name in metric_names:
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName=metric_name,
                Dimensions=[{'Name': 'InstanceId', 'Value': resource_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=60,  # 1 minute
                Statistics=['Average']
            )
            
            for datapoint in response['Datapoints']:
                metrics.append(Metric(
                    resource_id=resource_id,
                    metric_name=metric_name,
                    value=datapoint['Average'],
                    unit=datapoint['Unit'],
                    timestamp=datapoint['Timestamp'],
                    labels={'provider': 'aws', 'region': self.credentials.region}
                ))
        
        return metrics
    
    async def check_health(self) -> Dict[str, Any]:
        """Check AWS account health"""
        try:
            sts = self.session.client('sts')
            identity = sts.get_caller_identity()
            return {
                'healthy': True,
                'account_id': identity['Account'],
                'user_id': identity['UserId'],
                'arn': identity['Arn']
            }
        except ClientError as e:
            return {
                'healthy': False,
                'error': str(e)
            }
    
    def _parse_tags(self, tags: List[Dict]) -> Dict[str, str]:
        """Convert AWS tag format to dict"""
        return {tag['Key']: tag['Value'] for tag in tags}
    
    def _get_tag_value(self, tags: List[Dict], key: str) -> Optional[str]:
        """Get value for a specific tag key"""
        for tag in tags:
            if tag['Key'] == key:
                return tag['Value']
        return None
    
    def _get_bucket_region(self, s3_client, bucket_name: str) -> str:
        """Get S3 bucket region"""
        try:
            response = s3_client.get_bucket_location(Bucket=bucket_name)
            return response['LocationConstraint'] or 'us-east-1'
        except:
            return 'unknown'
```

### 3. GCP Connector Implementation

```python
# src/cloud/gcp_connector.py
from google.cloud import compute_v1, sql_v1, storage
from google.oauth2 import service_account
import json
from typing import List, Optional
from datetime import datetime

class GCPConnector(BaseCloudConnector):
    """Google Cloud Platform connector"""
    
    def __init__(self, credentials: GCPCredentials):
        super().__init__(credentials)
        self.project_id = credentials.project_id
        
        # Parse service account JSON
        sa_info = json.loads(credentials.service_account_json)
        self.credentials_obj = service_account.Credentials.from_service_account_info(sa_info)
    
    async def validate_credentials(self) -> bool:
        """Verify GCP credentials"""
        try:
            client = compute_v1.InstancesClient(credentials=self.credentials_obj)
            # Try to list instances (will fail if no permission)
            request = compute_v1.AggregatedListInstancesRequest(project=self.project_id)
            client.aggregated_list(request=request, max_results=1)
            return True
        except Exception:
            return False
    
    async def discover_resources(self) -> List[Resource]:
        """Discover Compute Engine, Cloud SQL, GCS resources"""
        resources = []
        
        # Compute Engine Instances
        compute_client = compute_v1.InstancesClient(credentials=self.credentials_obj)
        request = compute_v1.AggregatedListInstancesRequest(project=self.project_id)
        
        for zone, response in compute_client.aggregated_list(request=request):
            if response.instances:
                for instance in response.instances:
                    resources.append(Resource(
                        id=instance.name,
                        name=instance.name,
                        type='compute',
                        provider='gcp',
                        region=self._extract_region(zone),
                        status=instance.status,
                        tags=dict(instance.labels) if instance.labels else {},
                        metadata={
                            'machine_type': instance.machine_type.split('/')[-1],
                            'zone': zone.split('/')[-1],
                            'internal_ip': instance.network_interfaces[0].network_i_p if instance.network_interfaces else None,
                            'external_ip': instance.network_interfaces[0].access_configs[0].nat_i_p if instance.network_interfaces and instance.network_interfaces[0].access_configs else None
                        },
                        created_at=datetime.fromisoformat(instance.creation_timestamp.replace('Z', '+00:00')),
                        updated_at=datetime.utcnow()
                    ))
        
        # Cloud SQL Instances
        sql_client = sql_v1.SqlInstancesServiceClient(credentials=self.credentials_obj)
        sql_request = sql_v1.SqlInstancesListRequest(project=self.project_id)
        
        for instance in sql_client.list(request=sql_request):
            resources.append(Resource(
                id=instance.name,
                name=instance.name,
                type='database',
                provider='gcp',
                region=instance.region,
                status=instance.state.name,
                tags={},
                metadata={
                    'database_version': instance.database_version.name,
                    'tier': instance.settings.tier,
                    'ip_address': instance.ip_addresses[0].ip_address if instance.ip_addresses else None
                },
                created_at=datetime.fromisoformat(instance.create_time.replace('Z', '+00:00')),
                updated_at=datetime.utcnow()
            ))
        
        # Cloud Storage Buckets
        storage_client = storage.Client(credentials=self.credentials_obj, project=self.project_id)
        for bucket in storage_client.list_buckets():
            resources.append(Resource(
                id=bucket.name,
                name=bucket.name,
                type='storage',
                provider='gcp',
                region=bucket.location,
                status='active',
                tags=dict(bucket.labels) if bucket.labels else {},
                metadata={
                    'storage_class': bucket.storage_class,
                    'location_type': bucket.location_type
                },
                created_at=bucket.time_created,
                updated_at=datetime.utcnow()
            ))
        
        return resources
    
    async def get_metrics(
        self,
        resource_id: str,
        metric_names: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> List[Metric]:
        """Fetch Cloud Monitoring metrics"""
        from google.cloud import monitoring_v3
        
        client = monitoring_v3.MetricServiceClient(credentials=self.credentials_obj)
        project_name = f"projects/{self.project_id}"
        
        metrics = []
        for metric_name in metric_names:
            interval = monitoring_v3.TimeInterval({
                "start_time": start_time,
                "end_time": end_time
            })
            
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": f'metric.type="compute.googleapis.com/instance/{metric_name}" AND resource.labels.instance_id="{resource_id}"',
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL
                }
            )
            
            for result in results:
                for point in result.points:
                    metrics.append(Metric(
                        resource_id=resource_id,
                        metric_name=metric_name,
                        value=point.value.double_value or point.value.int64_value,
                        unit='',
                        timestamp=point.interval.end_time,
                        labels={'provider': 'gcp', 'project': self.project_id}
                    ))
        
        return metrics
    
    async def check_health(self) -> Dict[str, Any]:
        """Check GCP project health"""
        try:
            client = compute_v1.InstancesClient(credentials=self.credentials_obj)
            request = compute_v1.AggregatedListInstancesRequest(project=self.project_id)
            client.aggregated_list(request=request, max_results=1)
            return {
                'healthy': True,
                'project_id': self.project_id
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e)
            }
    
    def _extract_region(self, zone: str) -> str:
        """Extract region from zone (e.g., us-central1-a -> us-central1)"""
        parts = zone.split('/')[-1].rsplit('-', 1)
        return parts[0] if len(parts) > 1 else zone
```



### 4. Credential Vault Service

```python
# src/cloud/credential_vault.py
from google.cloud import secretmanager
from cryptography.fernet import Fernet
import json
import base64
from typing import Optional

class CredentialVault:
    """Secure credential storage using Google Secret Manager"""
    
    def __init__(self, project_id: str):
        self.client = secretmanager.SecretManagerServiceClient()
        self.project_id = project_id
        self.project_path = f"projects/{project_id}"
    
    def store_credentials(
        self,
        account_id: str,
        provider: str,
        credentials: dict
    ) -> str:
        """Store encrypted credentials in Secret Manager"""
        secret_id = f"cloud-{provider}-{account_id}"
        secret_path = f"{self.project_path}/secrets/{secret_id}"
        
        # Serialize credentials
        credentials_json = json.dumps(credentials)
        
        # Create or update secret
        try:
            # Try to create new secret
            parent = self.project_path
            secret = self.client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {
                        "replication": {"automatic": {}},
                        "labels": {
                            "provider": provider,
                            "account_id": account_id
                        }
                    }
                }
            )
        except Exception:
            # Secret already exists, that's fine
            pass
        
        # Add secret version
        parent = f"{self.project_path}/secrets/{secret_id}"
        payload = credentials_json.encode("UTF-8")
        
        response = self.client.add_secret_version(
            request={
                "parent": parent,
                "payload": {"data": payload}
            }
        )
        
        return response.name
    
    def get_credentials(
        self,
        account_id: str,
        provider: str
    ) -> Optional[dict]:
        """Retrieve and decrypt credentials"""
        secret_id = f"cloud-{provider}-{account_id}"
        name = f"{self.project_path}/secrets/{secret_id}/versions/latest"
        
        try:
            response = self.client.access_secret_version(request={"name": name})
            payload = response.payload.data.decode("UTF-8")
            return json.loads(payload)
        except Exception:
            return None
    
    def delete_credentials(
        self,
        account_id: str,
        provider: str
    ) -> bool:
        """Delete credentials from vault"""
        secret_id = f"cloud-{provider}-{account_id}"
        name = f"{self.project_path}/secrets/{secret_id}"
        
        try:
            self.client.delete_secret(request={"name": name})
            return True
        except Exception:
            return False
    
    def rotate_credentials(
        self,
        account_id: str,
        provider: str,
        new_credentials: dict
    ) -> str:
        """Rotate credentials (add new version)"""
        return self.store_credentials(account_id, provider, new_credentials)
```

### 5. Cloud Service (API Layer)

```python
# src/services/cloud_service.py
from typing import List, Optional, Dict, Any
from google.cloud import firestore
from datetime import datetime
from ..cloud.base_connector import BaseCloudConnector, Resource
from ..cloud.aws_connector import AWSConnector, AWSCredentials
from ..cloud.gcp_connector import GCPConnector, GCPCredentials
from ..cloud.credential_vault import CredentialVault

class CloudService:
    """Main service for cloud account management"""
    
    def __init__(self, project_id: str):
        self.db = firestore.Client()
        self.vault = CredentialVault(project_id)
        self.connectors: Dict[str, BaseCloudConnector] = {}
    
    async def connect_account(
        self,
        user_id: str,
        provider: str,
        credentials: dict
    ) -> Dict[str, Any]:
        """Connect a new cloud account"""
        
        # Create connector
        connector = self._create_connector(provider, credentials)
        
        # Validate credentials
        is_valid = await connector.validate_credentials()
        if not is_valid:
            raise ValueError(f"Invalid {provider} credentials")
        
        # Check health
        health = await connector.check_health()
        if not health['healthy']:
            raise ValueError(f"Account health check failed: {health.get('error')}")
        
        # Generate account ID
        account_id = self._generate_account_id(provider, credentials)
        
        # Store credentials in vault
        self.vault.store_credentials(account_id, provider, credentials)
        
        # Store metadata in Firestore
        account_ref = self.db.collection('cloud_accounts').document(account_id)
        account_ref.set({
            'user_id': user_id,
            'provider': provider,
            'account_id': account_id,
            'status': 'active',
            'health': health,
            'connected_at': firestore.SERVER_TIMESTAMP,
            'last_health_check': firestore.SERVER_TIMESTAMP,
            'metadata': {
                'region': credentials.get('region'),
                'project_id': credentials.get('project_id')
            }
        })
        
        # Trigger initial discovery
        await self._trigger_discovery(account_id)
        
        return {
            'account_id': account_id,
            'provider': provider,
            'status': 'active',
            'health': health
        }
    
    async def disconnect_account(
        self,
        account_id: str
    ) -> bool:
        """Disconnect a cloud account"""
        
        # Get account info
        account_ref = self.db.collection('cloud_accounts').document(account_id)
        account = account_ref.get()
        
        if not account.exists:
            return False
        
        account_data = account.to_dict()
        provider = account_data['provider']
        
        # Delete credentials from vault
        self.vault.delete_credentials(account_id, provider)
        
        # Mark account as disconnected
        account_ref.update({
            'status': 'disconnected',
            'disconnected_at': firestore.SERVER_TIMESTAMP
        })
        
        # Mark resources as disconnected
        resources = self.db.collection('resources').where('cloud_account_id', '==', account_id).stream()
        for resource in resources:
            resource.reference.update({
                'status': 'disconnected',
                'updated_at': firestore.SERVER_TIMESTAMP
            })
        
        return True
    
    async def get_connector(
        self,
        account_id: str
    ) -> Optional[BaseCloudConnector]:
        """Get connector for an account"""
        
        # Check cache
        if account_id in self.connectors:
            return self.connectors[account_id]
        
        # Get account info
        account_ref = self.db.collection('cloud_accounts').document(account_id)
        account = account_ref.get()
        
        if not account.exists:
            return None
        
        account_data = account.to_dict()
        provider = account_data['provider']
        
        # Get credentials from vault
        credentials = self.vault.get_credentials(account_id, provider)
        if not credentials:
            return None
        
        # Create connector
        connector = self._create_connector(provider, credentials)
        
        # Cache connector
        self.connectors[account_id] = connector
        
        return connector
    
    def _create_connector(
        self,
        provider: str,
        credentials: dict
    ) -> BaseCloudConnector:
        """Factory method to create provider-specific connector"""
        
        if provider == 'aws':
            return AWSConnector(AWSCredentials(**credentials))
        elif provider == 'gcp':
            return GCPConnector(GCPCredentials(**credentials))
        elif provider == 'azure':
            # TODO: Implement Azure connector
            raise NotImplementedError("Azure connector not yet implemented")
        elif provider == 'digitalocean':
            # TODO: Implement DigitalOcean connector
            raise NotImplementedError("DigitalOcean connector not yet implemented")
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _generate_account_id(
        self,
        provider: str,
        credentials: dict
    ) -> str:
        """Generate unique account ID"""
        import hashlib
        
        if provider == 'aws':
            base = f"{provider}-{credentials['access_key_id']}"
        elif provider == 'gcp':
            base = f"{provider}-{credentials['project_id']}"
        else:
            base = f"{provider}-{credentials.get('account_id', 'unknown')}"
        
        return hashlib.sha256(base.encode()).hexdigest()[:16]
    
    async def _trigger_discovery(self, account_id: str):
        """Trigger resource discovery for an account"""
        from google.cloud import pubsub_v1
        import json
        
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path("diatonic-ai-gcp", "cloud-discovery")
        
        message = json.dumps({
            'account_id': account_id,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        publisher.publish(topic_path, message.encode('utf-8'))
```

## Data Models

### Firestore Collections

#### `cloud_accounts/{accountId}`
```typescript
interface CloudAccount {
  user_id: string;
  provider: 'aws' | 'gcp' | 'azure' | 'digitalocean';
  account_id: string;
  status: 'active' | 'disconnected' | 'unhealthy';
  health: {
    healthy: boolean;
    last_check: Timestamp;
    error?: string;
  };
  connected_at: Timestamp;
  last_health_check: Timestamp;
  metadata: {
    region?: string;
    project_id?: string;
    account_name?: string;
  };
}
```

#### `resources/{resourceId}`
```typescript
interface Resource {
  id: string;
  cloud_account_id: string;
  user_id: string;
  name: string;
  type: 'compute' | 'database' | 'storage' | 'network';
  provider: 'aws' | 'gcp' | 'azure' | 'digitalocean';
  region: string;
  status: string;
  tags: Record<string, string>;
  metadata: Record<string, any>;
  created_at: Timestamp;
  updated_at: Timestamp;
  discovered_at: Timestamp;
}
```

#### `resource_changes/{changeId}`
```typescript
interface ResourceChange {
  resource_id: string;
  cloud_account_id: string;
  change_type: 'created' | 'modified' | 'deleted';
  timestamp: Timestamp;
  old_state?: Record<string, any>;
  new_state?: Record<string, any>;
  detected_at: Timestamp;
}
```

### BigQuery Tables

#### `cloud_api_calls`
```sql
CREATE TABLE cloud_api_calls (
  call_id STRING NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  account_id STRING NOT NULL,
  provider STRING NOT NULL,
  api_method STRING NOT NULL,
  
  -- Request details
  request_params JSON,
  
  -- Response details
  status_code INT64,
  duration_ms INT64,
  success BOOLEAN,
  error_message STRING,
  
  -- Cost tracking
  bytes_processed INT64,
  estimated_cost_usd NUMERIC(10, 6),
  
  -- Metadata
  user_id STRING,
  session_id STRING
)
PARTITION BY DATE(timestamp)
CLUSTER BY account_id, provider, api_method
OPTIONS(
  partition_expiration_days=90,
  require_partition_filter=true
);
```

#### `resource_inventory_history`
```sql
CREATE TABLE resource_inventory_history (
  snapshot_id STRING NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  account_id STRING NOT NULL,
  provider STRING NOT NULL,
  
  -- Resource details
  resource_id STRING NOT NULL,
  resource_type STRING NOT NULL,
  resource_name STRING,
  region STRING,
  status STRING,
  tags JSON,
  metadata JSON,
  
  -- Change tracking
  change_type STRING,  -- discovered, modified, deleted
  previous_snapshot_id STRING
)
PARTITION BY DATE(timestamp)
CLUSTER BY account_id, resource_type, provider
OPTIONS(
  partition_expiration_days=365,
  require_partition_filter=true
);
```

### TimescaleDB Tables

#### `metrics`
```sql
CREATE TABLE metrics (
  time TIMESTAMPTZ NOT NULL,
  resource_id TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  value DOUBLE PRECISION NOT NULL,
  unit TEXT,
  labels JSONB,
  PRIMARY KEY (time, resource_id, metric_name)
);

-- Create hypertable for time-series optimization
SELECT create_hypertable('metrics', 'time');

-- Create indexes
CREATE INDEX idx_metrics_resource ON metrics (resource_id, time DESC);
CREATE INDEX idx_metrics_name ON metrics (metric_name, time DESC);

-- Set up retention policy (90 days at 1-minute granularity)
SELECT add_retention_policy('metrics', INTERVAL '90 days');

-- Set up continuous aggregates for downsampling
CREATE MATERIALIZED VIEW metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 hour', time) AS bucket,
  resource_id,
  metric_name,
  AVG(value) as avg_value,
  MAX(value) as max_value,
  MIN(value) as min_value,
  COUNT(*) as sample_count
FROM metrics
GROUP BY bucket, resource_id, metric_name;

-- Refresh policy for continuous aggregate
SELECT add_continuous_aggregate_policy('metrics_hourly',
  start_offset => INTERVAL '3 hours',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour');
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Credential Validation Consistency
*For any* valid cloud provider credentials (AWS, GCP, Azure, DigitalOcean), the validation process should successfully verify the credentials and create an active cloud account connection.
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: Invalid Credential Rejection
*For any* invalid or malformed credentials, the system should reject the connection attempt and return a descriptive error message without creating an account.
**Validates: Requirements 1.5**

### Property 3: Credential Encryption at Rest
*For any* stored credentials, retrieving them from the Credential Vault and checking the storage format should confirm they are encrypted using AES-256 encryption.
**Validates: Requirements 1.6, 2.2**

### Property 4: Permission Verification
*For any* cloud account connection, the system should verify that the provided credentials have at least the minimum required permissions before marking the account as active.
**Validates: Requirements 1.7**

### Property 5: Account Disconnection Cleanup
*For any* cloud account, disconnecting it should result in all credentials being removed from the Credential Vault and all associated resources being marked as disconnected.
**Validates: Requirements 1.8**

### Property 6: Credential Rotation Continuity
*For any* cloud account with active credentials, rotating to new credentials should maintain service continuity without marking the account as unhealthy or disconnected.
**Validates: Requirements 2.4**

### Property 7: Failed Validation Health Update
*For any* cloud account where credential validation fails, the system should mark the account as unhealthy and generate a notification event.
**Validates: Requirements 2.5**

### Property 8: Complete Resource Discovery
*For any* connected cloud account, running resource discovery should identify and store all compute, database, storage, and network resources with complete metadata (name, type, region, tags).
**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6**

### Property 9: Discovery Timestamp Update
*For any* completed resource discovery run, the system should update the resource inventory timestamp to reflect the completion time.
**Validates: Requirements 3.7**

### Property 10: Change Detection Recording
*For any* detected resource change (create, modify, delete), the system should record the change type, timestamp, and affected resource in the change history.
**Validates: Requirements 4.4**

### Property 11: Inventory State Consistency
*For any* detected resource change, the resource inventory should be updated to reflect the current state of the resource.
**Validates: Requirements 4.5**

### Property 12: Concurrent Change Processing
*For any* set of simultaneous resource changes, the system should process all changes without data loss or corruption.
**Validates: Requirements 4.6**

### Property 13: Metrics Collection Initiation
*For any* newly discovered compute resource, the system should initiate collection of CPU, memory, disk I/O, and network I/O metrics.
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 14: Metrics Storage Format
*For any* collected metrics, they should be stored in the time-series database with 1-minute granularity and include resource_id, metric_name, value, unit, and timestamp.
**Validates: Requirements 5.5**

### Property 15: Metrics Collection Retry
*For any* failed metrics collection attempt, the system should retry up to 3 times with exponential backoff before marking the collection as failed.
**Validates: Requirements 5.8**

### Property 16: Health Check State Updates
*For any* health check result, the system should update the cloud account status to "healthy" if the check succeeds or "unhealthy" if it fails.
**Validates: Requirements 6.2, 6.3**

### Property 17: Dashboard Resource Aggregation
*For any* set of resources across multiple cloud providers, the dashboard should display the correct total count and group resources by both provider and type.
**Validates: Requirements 7.1, 7.2, 7.3**

### Property 18: Dashboard Health Display
*For any* set of connected cloud accounts, the dashboard should display the current health status of each account.
**Validates: Requirements 7.4**

### Property 19: Activity Feed Display
*For any* set of recent resource changes, the dashboard should display them in chronological order in the activity feed.
**Validates: Requirements 7.5**

### Property 20: Resource Search Filtering
*For any* search query with filters (name, type, region, tags), the system should return only resources that match all specified criteria.
**Validates: Requirements 7.6**

### Property 21: Resource Detail Display
*For any* resource, clicking on it should display complete resource information including metadata and current metrics.
**Validates: Requirements 7.7**

### Property 22: Tag Association
*For any* resource and tag, adding the tag should create an association that persists in storage and is retrievable.
**Validates: Requirements 8.1**

### Property 23: Tag Removal
*For any* resource with an associated tag, removing the tag should delete the association completely.
**Validates: Requirements 8.2**

### Property 24: Tag Filter Matching
*For any* set of tag filters, the system should return only resources that have all specified tags.
**Validates: Requirements 8.3**

### Property 25: Tag Preservation During Import
*For any* resource discovered from a cloud provider with existing tags, the system should preserve all original tags without modification.
**Validates: Requirements 8.4**

### Property 26: Tag Name Validation
*For any* custom tag name, the system should accept it if it contains only alphanumeric characters, hyphens, and underscores, and reject it otherwise.
**Validates: Requirements 8.5**

### Property 27: API Retry with Exponential Backoff
*For any* API call that approaches rate limits, the system should implement exponential backoff with increasing delays between retries.
**Validates: Requirements 9.2**

### Property 28: Transient Error Retry
*For any* API call that fails with a transient error, the system should retry up to 3 times before marking it as failed.
**Validates: Requirements 9.3**

### Property 29: Permanent Error Handling
*For any* API call that fails with a permanent error, the system should log the error and generate a user notification without retrying.
**Validates: Requirements 9.4**

### Property 30: Multi-Account API Distribution
*For any* set of connected cloud accounts, API calls should be distributed across accounts to avoid exceeding per-account rate limits.
**Validates: Requirements 9.5**

### Property 31: CSV Export Completeness
*For any* resource inventory, exporting to CSV should produce a file containing all resources with all metadata fields.
**Validates: Requirements 10.1**

### Property 32: JSON Export Completeness
*For any* resource inventory, exporting to JSON should produce a valid JSON file containing all resources with complete metadata.
**Validates: Requirements 10.2**

### Property 33: Metrics Export Format
*For any* time range, exporting metrics should produce a CSV file with time-series data including timestamps, metric names, values, and units.
**Validates: Requirements 10.3**

### Property 34: Export Metadata Inclusion
*For any* export operation, the generated file should include all resource metadata and current status information.
**Validates: Requirements 10.4**

## Error Handling

### Error Categories

1. **Credential Errors**
   - Invalid credentials format
   - Expired credentials
   - Insufficient permissions
   - Network connectivity issues

2. **Discovery Errors**
   - API rate limit exceeded
   - Timeout during discovery
   - Partial discovery failure
   - Resource access denied

3. **Metrics Errors**
   - Metrics API unavailable
   - Invalid metric query
   - Storage write failure
   - Data format errors

4. **System Errors**
   - Database connection failure
   - Vault access denied
   - Worker timeout
   - Queue overflow

### Error Handling Strategy

```python
# src/cloud/error_handler.py
from enum import Enum
from typing import Optional, Dict, Any
import logging

class ErrorSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class CloudError(Exception):
    """Base exception for cloud operations"""
    
    def __init__(
        self,
        message: str,
        severity: ErrorSeverity,
        provider: str,
        account_id: Optional[str] = None,
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.provider = provider
        self.account_id = account_id
        self.retryable = retryable
        self.metadata = metadata or {}

class CredentialError(CloudError):
    """Credential-related errors"""
    pass

class DiscoveryError(CloudError):
    """Resource discovery errors"""
    pass

class MetricsError(CloudError):
    """Metrics collection errors"""
    pass

class ErrorHandler:
    """Centralized error handling"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def handle_error(
        self,
        error: CloudError,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle cloud operation errors"""
        
        # Log error
        log_method = getattr(self.logger, error.severity.value)
        log_method(
            f"{error.provider} error: {error.message}",
            extra={
                "account_id": error.account_id,
                "retryable": error.retryable,
                "metadata": error.metadata,
                **context
            }
        )
        
        # Update account health if needed
        if error.severity in [ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
            self._update_account_health(error.account_id, False, error.message)
        
        # Generate notification if critical
        if error.severity == ErrorSeverity.CRITICAL:
            self._send_notification(error)
        
        return {
            "error": error.message,
            "severity": error.severity.value,
            "retryable": error.retryable,
            "reference_id": self._generate_reference_id()
        }
    
    def _update_account_health(
        self,
        account_id: str,
        healthy: bool,
        error_message: str
    ):
        """Update cloud account health status"""
        # Implementation
        pass
    
    def _send_notification(self, error: CloudError):
        """Send user notification for critical errors"""
        # Implementation
        pass
    
    def _generate_reference_id(self) -> str:
        """Generate unique error reference ID"""
        import uuid
        return str(uuid.uuid4())[:8]
```

### Retry Strategy

```python
# src/cloud/retry.py
import asyncio
from typing import Callable, TypeVar, Any
from functools import wraps

T = TypeVar('T')

def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
):
    """Decorator for retrying operations with exponential backoff"""
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if retryable
                    if hasattr(e, 'retryable') and not e.retryable:
                        raise
                    
                    # Calculate delay
                    if attempt < max_attempts - 1:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        await asyncio.sleep(delay)
            
            # All attempts failed
            raise last_exception
        
        return wrapper
    return decorator

# Usage example
@with_retry(max_attempts=3, base_delay=1.0)
async def discover_resources(connector: BaseCloudConnector):
    return await connector.discover_resources()
```



## Testing Strategy

### Overview

The Multi-Cloud Foundation will be tested using a dual approach combining unit tests for specific scenarios and property-based tests for universal correctness properties. This ensures both concrete functionality and general correctness across all inputs.

### Property-Based Testing

**Framework**: We will use **Hypothesis** for Python property-based testing.

**Configuration**: Each property-based test will run a minimum of 100 iterations to ensure thorough coverage of the input space.

**Test Tagging**: Each property-based test will be tagged with a comment explicitly referencing the correctness property from this design document using the format:
```python
# Feature: multi-cloud-foundation, Property 1: Credential Validation Consistency
```

### Property-Based Test Examples

#### Property 1: Credential Validation Consistency

```python
# tests/property/test_credential_validation.py
from hypothesis import given, strategies as st
import pytest
from src.cloud.aws_connector import AWSConnector, AWSCredentials
from src.cloud.gcp_connector import GCPConnector, GCPCredentials

# Feature: multi-cloud-foundation, Property 1: Credential Validation Consistency
@given(
    access_key=st.text(min_size=20, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Nd'))),
    secret_key=st.text(min_size=40, max_size=40),
    region=st.sampled_from(['us-east-1', 'us-west-2', 'eu-west-1'])
)
@pytest.mark.property_test
async def test_aws_credential_validation_consistency(access_key, secret_key, region, mock_aws_api):
    """
    Property: For any valid AWS credentials, validation should succeed and create an account.
    """
    # Arrange
    mock_aws_api.configure_valid_credentials(access_key, secret_key)
    credentials = AWSCredentials(
        access_key_id=access_key,
        secret_access_key=secret_key,
        region=region
    )
    connector = AWSConnector(credentials)
    
    # Act
    is_valid = await connector.validate_credentials()
    
    # Assert
    assert is_valid is True, f"Valid credentials should be accepted: {access_key}"
```

#### Property 8: Complete Resource Discovery

```python
# tests/property/test_resource_discovery.py
from hypothesis import given, strategies as st
from hypothesis.strategies import composite
import pytest

@composite
def cloud_resources(draw):
    """Generate random cloud resources"""
    resource_types = ['compute', 'database', 'storage', 'network']
    return {
        'id': draw(st.uuids()).hex,
        'name': draw(st.text(min_size=1, max_size=50)),
        'type': draw(st.sampled_from(resource_types)),
        'region': draw(st.sampled_from(['us-east-1', 'us-west-2', 'eu-west-1'])),
        'tags': draw(st.dictionaries(st.text(min_size=1, max_size=20), st.text(max_size=50), max_size=10))
    }

# Feature: multi-cloud-foundation, Property 8: Complete Resource Discovery
@given(
    resources=st.lists(cloud_resources(), min_size=1, max_size=50)
)
@pytest.mark.property_test
async def test_complete_resource_discovery(resources, mock_cloud_api, cloud_service):
    """
    Property: For any set of cloud resources, discovery should identify and store all of them
    with complete metadata.
    """
    # Arrange
    mock_cloud_api.set_resources(resources)
    account_id = "test-account-123"
    
    # Act
    discovered = await cloud_service.discover_resources(account_id)
    
    # Assert
    assert len(discovered) == len(resources), "All resources should be discovered"
    
    for original in resources:
        found = next((r for r in discovered if r['id'] == original['id']), None)
        assert found is not None, f"Resource {original['id']} should be discovered"
        assert found['name'] == original['name'], "Resource name should match"
        assert found['type'] == original['type'], "Resource type should match"
        assert found['region'] == original['region'], "Resource region should match"
        assert found['tags'] == original['tags'], "Resource tags should be preserved"
```

#### Property 20: Resource Search Filtering

```python
# tests/property/test_resource_search.py
from hypothesis import given, strategies as st, assume
import pytest

# Feature: multi-cloud-foundation, Property 20: Resource Search Filtering
@given(
    resources=st.lists(cloud_resources(), min_size=10, max_size=100),
    search_name=st.text(min_size=1, max_size=20),
    search_type=st.sampled_from(['compute', 'database', 'storage', 'network']),
    search_region=st.sampled_from(['us-east-1', 'us-west-2', 'eu-west-1'])
)
@pytest.mark.property_test
async def test_resource_search_filtering(resources, search_name, search_type, search_region, cloud_service):
    """
    Property: For any search query, only resources matching ALL criteria should be returned.
    """
    # Arrange
    await cloud_service.store_resources(resources)
    
    # Act
    results = await cloud_service.search_resources(
        name=search_name,
        type=search_type,
        region=search_region
    )
    
    # Assert
    for result in results:
        assert search_name.lower() in result['name'].lower(), "Name filter should match"
        assert result['type'] == search_type, "Type filter should match"
        assert result['region'] == search_region, "Region filter should match"
    
    # Verify no false negatives
    expected_matches = [
        r for r in resources
        if search_name.lower() in r['name'].lower()
        and r['type'] == search_type
        and r['region'] == search_region
    ]
    assert len(results) == len(expected_matches), "All matching resources should be returned"
```

#### Property 31: CSV Export Completeness

```python
# tests/property/test_export.py
from hypothesis import given, strategies as st
import pytest
import csv
import io

# Feature: multi-cloud-foundation, Property 31: CSV Export Completeness
@given(
    resources=st.lists(cloud_resources(), min_size=1, max_size=100)
)
@pytest.mark.property_test
async def test_csv_export_completeness(resources, cloud_service):
    """
    Property: For any resource inventory, CSV export should contain all resources with all fields.
    """
    # Arrange
    await cloud_service.store_resources(resources)
    
    # Act
    csv_data = await cloud_service.export_resources_csv()
    
    # Assert
    reader = csv.DictReader(io.StringIO(csv_data))
    exported_resources = list(reader)
    
    assert len(exported_resources) == len(resources), "All resources should be exported"
    
    required_fields = ['id', 'name', 'type', 'provider', 'region', 'status', 'tags']
    for row in exported_resources:
        for field in required_fields:
            assert field in row, f"Field {field} should be present in export"
            assert row[field], f"Field {field} should have a value"
```

### Unit Testing

Unit tests will cover specific scenarios, edge cases, and integration points:

#### Credential Management Tests

```python
# tests/unit/test_credential_vault.py
import pytest
from src.cloud.credential_vault import CredentialVault

class TestCredentialVault:
    
    @pytest.fixture
    def vault(self):
        return CredentialVault(project_id="test-project")
    
    def test_store_and_retrieve_aws_credentials(self, vault):
        """Test storing and retrieving AWS credentials"""
        credentials = {
            'access_key_id': 'AKIAIOSFODNN7EXAMPLE',
            'secret_access_key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            'region': 'us-east-1'
        }
        
        vault.store_credentials('test-account', 'aws', credentials)
        retrieved = vault.get_credentials('test-account', 'aws')
        
        assert retrieved == credentials
    
    def test_delete_credentials(self, vault):
        """Test credential deletion"""
        credentials = {'api_token': 'test-token'}
        vault.store_credentials('test-account', 'digitalocean', credentials)
        
        success = vault.delete_credentials('test-account', 'digitalocean')
        assert success is True
        
        retrieved = vault.get_credentials('test-account', 'digitalocean')
        assert retrieved is None
    
    def test_credentials_are_encrypted(self, vault, mock_secret_manager):
        """Test that credentials are encrypted in storage"""
        credentials = {'secret': 'sensitive-data'}
        vault.store_credentials('test-account', 'aws', credentials)
        
        # Verify the stored data is encrypted (not plaintext)
        raw_data = mock_secret_manager.get_raw_secret('cloud-aws-test-account')
        assert 'sensitive-data' not in raw_data
```

#### Resource Discovery Tests

```python
# tests/unit/test_discovery_service.py
import pytest
from src.services.discovery_service import DiscoveryService

class TestDiscoveryService:
    
    @pytest.fixture
    def discovery_service(self):
        return DiscoveryService()
    
    @pytest.mark.asyncio
    async def test_discover_empty_account(self, discovery_service, mock_aws_connector):
        """Test discovery with no resources"""
        mock_aws_connector.set_resources([])
        
        resources = await discovery_service.discover_resources('test-account')
        
        assert resources == []
    
    @pytest.mark.asyncio
    async def test_discover_mixed_resource_types(self, discovery_service, mock_aws_connector):
        """Test discovery with multiple resource types"""
        mock_resources = [
            {'id': 'i-123', 'type': 'compute'},
            {'id': 'db-456', 'type': 'database'},
            {'id': 'bucket-789', 'type': 'storage'}
        ]
        mock_aws_connector.set_resources(mock_resources)
        
        resources = await discovery_service.discover_resources('test-account')
        
        assert len(resources) == 3
        types = {r['type'] for r in resources}
        assert types == {'compute', 'database', 'storage'}
    
    @pytest.mark.asyncio
    async def test_discovery_handles_api_errors(self, discovery_service, mock_aws_connector):
        """Test discovery error handling"""
        mock_aws_connector.configure_error('RateLimitExceeded')
        
        with pytest.raises(DiscoveryError) as exc_info:
            await discovery_service.discover_resources('test-account')
        
        assert exc_info.value.retryable is True
```

#### Metrics Collection Tests

```python
# tests/unit/test_metrics_service.py
import pytest
from datetime import datetime, timedelta
from src.services.metrics_service import MetricsService

class TestMetricsService:
    
    @pytest.fixture
    def metrics_service(self):
        return MetricsService()
    
    @pytest.mark.asyncio
    async def test_collect_cpu_metrics(self, metrics_service, mock_cloudwatch):
        """Test CPU metrics collection"""
        resource_id = 'i-123456'
        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()
        
        mock_cloudwatch.set_metric_data('CPUUtilization', [
            {'timestamp': start_time, 'value': 45.5},
            {'timestamp': end_time, 'value': 52.3}
        ])
        
        metrics = await metrics_service.collect_metrics(
            resource_id,
            ['CPUUtilization'],
            start_time,
            end_time
        )
        
        assert len(metrics) == 2
        assert all(m['metric_name'] == 'CPUUtilization' for m in metrics)
        assert all(m['resource_id'] == resource_id for m in metrics)
    
    @pytest.mark.asyncio
    async def test_metrics_retry_on_failure(self, metrics_service, mock_cloudwatch):
        """Test metrics collection retry logic"""
        mock_cloudwatch.configure_transient_error(attempts_before_success=2)
        
        metrics = await metrics_service.collect_metrics('i-123', ['CPUUtilization'])
        
        assert len(metrics) > 0
        assert mock_cloudwatch.call_count == 3  # Initial + 2 retries
```

### Integration Testing

Integration tests will verify end-to-end workflows:

```python
# tests/integration/test_cloud_account_lifecycle.py
import pytest
from src.services.cloud_service import CloudService

@pytest.mark.integration
class TestCloudAccountLifecycle:
    
    @pytest.mark.asyncio
    async def test_complete_account_lifecycle(self, cloud_service, test_aws_credentials):
        """Test complete lifecycle: connect -> discover -> collect metrics -> disconnect"""
        
        # Connect account
        account = await cloud_service.connect_account(
            user_id='test-user',
            provider='aws',
            credentials=test_aws_credentials
        )
        assert account['status'] == 'active'
        
        # Wait for initial discovery
        await asyncio.sleep(5)
        
        # Verify resources discovered
        resources = await cloud_service.get_resources(account['account_id'])
        assert len(resources) > 0
        
        # Collect metrics
        metrics = await cloud_service.get_metrics(
            resources[0]['id'],
            ['CPUUtilization']
        )
        assert len(metrics) > 0
        
        # Disconnect account
        success = await cloud_service.disconnect_account(account['account_id'])
        assert success is True
        
        # Verify cleanup
        credentials = cloud_service.vault.get_credentials(
            account['account_id'],
            'aws'
        )
        assert credentials is None
```

### Test Coverage Goals

- **Unit Test Coverage**: Minimum 80% code coverage
- **Property Test Coverage**: All 34 correctness properties must have corresponding property-based tests
- **Integration Test Coverage**: All major workflows (connect, discover, collect, disconnect)
- **Edge Case Coverage**: Empty accounts, large resource sets, API failures, concurrent operations

### Continuous Testing

- Tests run on every commit via GitHub Actions
- Property-based tests run with 100 iterations in CI, 1000 iterations nightly
- Integration tests run against test cloud accounts
- Performance benchmarks tracked over time

---

## Deployment Considerations

### Infrastructure Requirements

**Compute**:
- Cloud Run for API (auto-scaling 0-10 instances)
- Cloud Functions for workers (discovery, metrics, health checks)

**Storage**:
- Firestore for hot data (sessions, accounts, resources)
- BigQuery for cold data (audit logs, history)
- TimescaleDB for metrics (Cloud SQL PostgreSQL with TimescaleDB extension)
- Secret Manager for credentials

**Networking**:
- Cloud Load Balancer for API
- VPC for secure communication
- Cloud NAT for outbound API calls

### Deployment Strategy

1. **Phase 1: Core Infrastructure** (Week 1)
   - Set up Firestore collections
   - Create BigQuery tables
   - Deploy TimescaleDB instance
   - Configure Secret Manager

2. **Phase 2: AWS Support** (Week 2-3)
   - Deploy AWS connector
   - Implement discovery worker
   - Add metrics collection
   - Test with real AWS accounts

3. **Phase 3: GCP Support** (Week 4)
   - Deploy GCP connector
   - Extend discovery worker
   - Test multi-cloud scenarios

4. **Phase 4: Additional Providers** (Week 5-6)
   - Azure connector
   - DigitalOcean connector
   - Full integration testing

5. **Phase 5: Dashboard & Polish** (Week 7-8)
   - Frontend dashboard
   - Real-time updates
   - Export functionality
   - Performance optimization

### Monitoring & Observability

**Metrics to Track**:
- API response times (p50, p95, p99)
- Discovery job duration and success rate
- Metrics collection lag
- Error rates by provider
- Credential validation failures
- Resource count by provider
- Storage usage (Firestore, BigQuery, TimescaleDB)

**Alerts**:
- Discovery job failures
- Metrics collection lag > 5 minutes
- Credential validation failures
- API error rate > 1%
- Storage quota approaching limits

### Cost Optimization

**Firestore**:
- Use TTL for old sessions (30 days)
- Batch writes where possible
- Index only necessary fields

**BigQuery**:
- Partition by date
- Cluster by account_id
- Set partition expiration (90-365 days)
- Use streaming inserts sparingly

**TimescaleDB**:
- Continuous aggregates for downsampling
- Retention policies (90 days raw, 1 year aggregated)
- Compression for old data

**Cloud Functions**:
- Optimize memory allocation
- Use minimum instances = 0
- Batch processing where possible

---

## Security Considerations

### Credential Security

1. **Encryption**: All credentials encrypted at rest using AES-256
2. **Access Control**: Credentials only accessible via service account with minimal permissions
3. **Audit Logging**: All credential access logged to BigQuery
4. **Rotation**: Support for credential rotation without downtime
5. **Expiration**: Detect and alert on expired credentials

### API Security

1. **Authentication**: Firebase Auth for user authentication
2. **Authorization**: RBAC for resource access
3. **Rate Limiting**: Per-user and per-account rate limits
4. **Input Validation**: Validate all user inputs
5. **CORS**: Restrict to known origins

### Cloud Provider Security

1. **Least Privilege**: Request minimum required permissions
2. **Read-Only Default**: Start with read-only access
3. **Permission Verification**: Verify permissions before operations
4. **Audit Trail**: Log all cloud API calls
5. **Error Handling**: Don't expose sensitive info in errors

---

## Future Enhancements

### Phase 6+: Advanced Features

1. **Cost Management**: Track and optimize cloud spending
2. **Automated Actions**: Start/stop resources, create snapshots
3. **Compliance Scanning**: Security and compliance checks
4. **AI Recommendations**: ML-powered optimization suggestions
5. **Multi-Region Support**: Deploy across multiple regions
6. **Custom Integrations**: Plugin system for additional providers
7. **Advanced Analytics**: Predictive analytics and forecasting

---

**Document Version**: 1.0  
**Created**: December 15, 2024  
**Last Updated**: December 15, 2024  
**Status**: Design Specification
