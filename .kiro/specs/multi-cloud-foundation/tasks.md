# Implementation Plan: Multi-Cloud Foundation

## Overview

This implementation plan breaks down the Multi-Cloud Foundation into discrete, manageable tasks that build incrementally. Each task includes specific requirements references and integrates property-based testing to ensure correctness.

---

## Task List

- [ ] 1. Set up infrastructure and data models
  - Create Firestore collections for cloud accounts, resources, and changes
  - Create BigQuery tables for audit logs and resource history
  - Set up TimescaleDB instance for metrics storage
  - Configure Secret Manager for credential vault
  - _Requirements: 1.6, 2.1, 2.2_

- [ ] 1.1 Write unit tests for data model schemas
  - Test Firestore document validation
  - Test BigQuery schema compliance
  - Test TimescaleDB table creation
  - _Requirements: 1.6, 2.1, 2.2_

- [ ] 2. Implement base cloud connector interface
  - Create `BaseCloudConnector` abstract class with required methods
  - Define `CloudCredentials`, `Resource`, and `Metric` data models
  - Implement credential validation interface
  - Implement resource discovery interface
  - Implement metrics collection interface
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.2, 5.1_

- [ ] 2.1 Write unit tests for base connector interface
  - Test abstract method enforcement
  - Test data model validation
  - Test interface contracts
  - _Requirements: 1.1, 3.2, 5.1_

- [ ] 3. Implement credential vault service
  - Create `CredentialVault` class using Google Secret Manager
  - Implement `store_credentials()` method with encryption
  - Implement `get_credentials()` method with decryption
  - Implement `delete_credentials()` method
  - Implement `rotate_credentials()` method
  - _Requirements: 1.6, 2.2, 2.4_

- [ ] 3.1 Write property test for credential encryption
  - **Property 3: Credential Encryption at Rest**
  - **Validates: Requirements 1.6, 2.2**

- [ ] 3.2 Write unit tests for credential vault
  - Test credential storage and retrieval
  - Test credential deletion
  - Test encryption verification
  - Test error handling
  - _Requirements: 1.6, 2.2, 2.4_

- [ ] 4. Implement AWS connector
  - Create `AWSConnector` class extending `BaseCloudConnector`
  - Implement `validate_credentials()` using STS GetCallerIdentity
  - Implement `discover_resources()` for EC2, RDS, S3
  - Implement `get_metrics()` using CloudWatch
  - Implement `check_health()` method
  - Add tag parsing utilities
  - _Requirements: 1.1, 1.7, 3.2, 3.3, 3.4, 5.1, 6.2_

- [ ] 4.1 Write property test for AWS credential validation
  - **Property 1: Credential Validation Consistency (AWS)**
  - **Validates: Requirements 1.1**

- [ ] 4.2 Write property test for AWS resource discovery
  - **Property 8: Complete Resource Discovery (AWS)**
  - **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6**

- [ ] 4.3 Write unit tests for AWS connector
  - Test EC2 instance discovery
  - Test RDS instance discovery
  - Test S3 bucket discovery
  - Test CloudWatch metrics collection
  - Test error handling for API failures
  - _Requirements: 1.1, 3.2, 3.3, 3.4, 5.1_

- [ ] 5. Implement GCP connector
  - Create `GCPConnector` class extending `BaseCloudConnector`
  - Implement `validate_credentials()` using service account
  - Implement `discover_resources()` for Compute Engine, Cloud SQL, GCS
  - Implement `get_metrics()` using Cloud Monitoring
  - Implement `check_health()` method
  - Add label parsing utilities
  - _Requirements: 1.2, 1.7, 3.2, 3.3, 3.4, 5.1, 6.2_

- [ ] 5.1 Write property test for GCP credential validation
  - **Property 1: Credential Validation Consistency (GCP)**
  - **Validates: Requirements 1.2**

- [ ] 5.2 Write property test for GCP resource discovery
  - **Property 8: Complete Resource Discovery (GCP)**
  - **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6**

- [ ] 5.3 Write unit tests for GCP connector
  - Test Compute Engine instance discovery
  - Test Cloud SQL instance discovery
  - Test GCS bucket discovery
  - Test Cloud Monitoring metrics collection
  - Test error handling
  - _Requirements: 1.2, 3.2, 3.3, 3.4, 5.1_

- [ ] 6. Implement error handling and retry logic
  - Create `CloudError` exception hierarchy
  - Create `ErrorHandler` class for centralized error handling
  - Implement `with_retry` decorator with exponential backoff
  - Add error logging and notification
  - Implement account health status updates on errors
  - _Requirements: 1.5, 2.5, 5.8, 9.2, 9.3, 9.4_

- [ ] 6.1 Write property test for invalid credential rejection
  - **Property 2: Invalid Credential Rejection**
  - **Validates: Requirements 1.5**

- [ ] 6.2 Write property test for retry with exponential backoff
  - **Property 27: API Retry with Exponential Backoff**
  - **Validates: Requirements 9.2**

- [ ] 6.3 Write property test for transient error retry
  - **Property 28: Transient Error Retry**
  - **Validates: Requirements 9.3**

- [ ] 6.4 Write property test for permanent error handling
  - **Property 29: Permanent Error Handling**
  - **Validates: Requirements 9.4**

- [ ] 6.5 Write unit tests for error handling
  - Test error severity classification
  - Test retry logic with various error types
  - Test error logging
  - Test notification generation
  - _Requirements: 1.5, 2.5, 5.8, 9.2, 9.3, 9.4_

- [ ] 7. Implement cloud service (API layer)
  - Create `CloudService` class for account management
  - Implement `connect_account()` method
  - Implement `disconnect_account()` method
  - Implement `get_connector()` method with caching
  - Add connector factory for provider-specific connectors
  - Integrate with credential vault
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7, 1.8_

- [ ] 7.1 Write property test for permission verification
  - **Property 4: Permission Verification**
  - **Validates: Requirements 1.7**

- [ ] 7.2 Write property test for account disconnection cleanup
  - **Property 5: Account Disconnection Cleanup**
  - **Validates: Requirements 1.8**

- [ ] 7.3 Write property test for credential rotation
  - **Property 6: Credential Rotation Continuity**
  - **Validates: Requirements 2.4**

- [ ] 7.4 Write property test for failed validation health update
  - **Property 7: Failed Validation Health Update**
  - **Validates: Requirements 2.5**

- [ ] 7.5 Write unit tests for cloud service
  - Test account connection flow
  - Test account disconnection flow
  - Test connector caching
  - Test multi-provider support
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7, 1.8_

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement discovery service and worker
  - Create `DiscoveryService` class
  - Implement resource discovery orchestration
  - Create Cloud Function for discovery worker
  - Implement Pub/Sub trigger for scheduled discovery
  - Store discovered resources in Firestore
  - Log discovery events to BigQuery
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ] 9.1 Write property test for discovery timestamp update
  - **Property 9: Discovery Timestamp Update**
  - **Validates: Requirements 3.7**

- [ ] 9.2 Write unit tests for discovery service
  - Test discovery orchestration
  - Test resource storage
  - Test error handling during discovery
  - Test partial discovery scenarios
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ] 10. Implement change detection
  - Create `ChangeDetectionService` class
  - Implement resource comparison logic
  - Detect created, modified, and deleted resources
  - Store changes in Firestore `resource_changes` collection
  - Update resource inventory with current state
  - Handle concurrent changes
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 10.1 Write property test for change detection recording
  - **Property 10: Change Detection Recording**
  - **Validates: Requirements 4.4**

- [ ] 10.2 Write property test for inventory state consistency
  - **Property 11: Inventory State Consistency**
  - **Validates: Requirements 4.5**

- [ ] 10.3 Write property test for concurrent change processing
  - **Property 12: Concurrent Change Processing**
  - **Validates: Requirements 4.6**

- [ ] 10.4 Write unit tests for change detection
  - Test resource creation detection
  - Test resource modification detection
  - Test resource deletion detection
  - Test change history storage
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 11. Implement metrics collection service
  - Create `MetricsService` class
  - Implement metrics collection orchestration
  - Create Cloud Function for metrics worker
  - Collect CPU, memory, disk, network metrics
  - Store metrics in TimescaleDB
  - Implement retry logic for failed collections
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.8_

- [ ] 11.1 Write property test for metrics collection initiation
  - **Property 13: Metrics Collection Initiation**
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [ ] 11.2 Write property test for metrics storage format
  - **Property 14: Metrics Storage Format**
  - **Validates: Requirements 5.5**

- [ ] 11.3 Write property test for metrics collection retry
  - **Property 15: Metrics Collection Retry**
  - **Validates: Requirements 5.8**

- [ ] 11.4 Write unit tests for metrics service
  - Test metrics collection for different resource types
  - Test TimescaleDB storage
  - Test retry logic
  - Test error handling
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.8_

- [ ] 12. Implement health monitoring
  - Create `HealthMonitorService` class
  - Create Cloud Function for health check worker
  - Implement periodic health checks (5-minute interval)
  - Update account health status in Firestore
  - Generate notifications for unhealthy accounts
  - Detect stopped resources based on missing metrics
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 12.1 Write property test for health check state updates
  - **Property 16: Health Check State Updates**
  - **Validates: Requirements 6.2, 6.3**

- [ ] 12.2 Write unit tests for health monitoring
  - Test health check execution
  - Test status updates
  - Test notification generation
  - Test resource health inference
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Implement FastAPI endpoints for cloud management
  - Create `/api/cloud/accounts` endpoints (POST, GET, DELETE)
  - Create `/api/cloud/accounts/{id}/resources` endpoint
  - Create `/api/cloud/accounts/{id}/health` endpoint
  - Create `/api/cloud/resources` endpoint with filtering
  - Create `/api/cloud/resources/{id}` endpoint
  - Create `/api/cloud/resources/{id}/metrics` endpoint
  - Add authentication and authorization
  - Add rate limiting
  - _Requirements: 1.1, 1.8, 3.2, 5.1, 6.2, 7.6, 7.7_

- [ ] 14.1 Write integration tests for API endpoints
  - Test account connection flow
  - Test resource listing and filtering
  - Test metrics retrieval
  - Test authentication and authorization
  - Test rate limiting
  - _Requirements: 1.1, 1.8, 3.2, 5.1, 6.2, 7.6, 7.7_

- [ ] 15. Implement dashboard backend services
  - Create dashboard aggregation service
  - Implement resource grouping by provider and type
  - Implement activity feed generation
  - Implement search and filter logic
  - Add caching for dashboard queries
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 15.1 Write property test for dashboard resource aggregation
  - **Property 17: Dashboard Resource Aggregation**
  - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ] 15.2 Write property test for dashboard health display
  - **Property 18: Dashboard Health Display**
  - **Validates: Requirements 7.4**

- [ ] 15.3 Write property test for activity feed display
  - **Property 19: Activity Feed Display**
  - **Validates: Requirements 7.5**

- [ ] 15.4 Write property test for resource search filtering
  - **Property 20: Resource Search Filtering**
  - **Validates: Requirements 7.6**

- [ ] 15.5 Write property test for resource detail display
  - **Property 21: Resource Detail Display**
  - **Validates: Requirements 7.7**

- [ ] 15.6 Write unit tests for dashboard services
  - Test aggregation logic
  - Test grouping algorithms
  - Test activity feed generation
  - Test search and filter
  - Test caching behavior
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 16. Implement resource tagging
  - Create tagging service
  - Implement `add_tag()` method
  - Implement `remove_tag()` method
  - Implement tag filtering logic
  - Preserve cloud provider tags during discovery
  - Validate custom tag names
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 16.1 Write property test for tag association
  - **Property 22: Tag Association**
  - **Validates: Requirements 8.1**

- [ ] 16.2 Write property test for tag removal
  - **Property 23: Tag Removal**
  - **Validates: Requirements 8.2**

- [ ] 16.3 Write property test for tag filter matching
  - **Property 24: Tag Filter Matching**
  - **Validates: Requirements 8.3**

- [ ] 16.4 Write property test for tag preservation during import
  - **Property 25: Tag Preservation During Import**
  - **Validates: Requirements 8.4**

- [ ] 16.5 Write property test for tag name validation
  - **Property 26: Tag Name Validation**
  - **Validates: Requirements 8.5**

- [ ] 16.6 Write unit tests for tagging service
  - Test tag addition and removal
  - Test tag filtering
  - Test tag preservation
  - Test tag name validation
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 17. Implement export functionality
  - Create export service
  - Implement CSV export for resources
  - Implement JSON export for resources
  - Implement CSV export for metrics
  - Add async processing for large exports
  - Generate notifications on export completion
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 17.1 Write property test for CSV export completeness
  - **Property 31: CSV Export Completeness**
  - **Validates: Requirements 10.1**

- [ ] 17.2 Write property test for JSON export completeness
  - **Property 32: JSON Export Completeness**
  - **Validates: Requirements 10.2**

- [ ] 17.3 Write property test for metrics export format
  - **Property 33: Metrics Export Format**
  - **Validates: Requirements 10.3**

- [ ] 17.4 Write property test for export metadata inclusion
  - **Property 34: Export Metadata Inclusion**
  - **Validates: Requirements 10.4**

- [ ] 17.5 Write unit tests for export service
  - Test CSV generation
  - Test JSON generation
  - Test async processing
  - Test large dataset handling
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 18. Implement rate limiting and API distribution
  - Create rate limiter service
  - Implement per-account rate limiting
  - Implement API call distribution across accounts
  - Add rate limit monitoring
  - Implement backoff when approaching limits
  - _Requirements: 9.1, 9.2, 9.5_

- [ ] 18.1 Write property test for multi-account API distribution
  - **Property 30: Multi-Account API Distribution**
  - **Validates: Requirements 9.5**

- [ ] 18.2 Write unit tests for rate limiting
  - Test rate limit enforcement
  - Test API distribution
  - Test backoff behavior
  - Test rate limit monitoring
  - _Requirements: 9.1, 9.2, 9.5_

- [ ] 19. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 20. Create MCP tools for cloud management
  - Create `list_cloud_accounts.yaml` MCP tool spec
  - Create `list_resources.yaml` MCP tool spec
  - Create `get_resource_details.yaml` MCP tool spec
  - Create `get_resource_metrics.yaml` MCP tool spec
  - Create `search_resources.yaml` MCP tool spec
  - Generate Python implementations using MCP generator
  - Register tools with LangGraph agent
  - _Requirements: 3.2, 5.1, 7.6, 7.7_

- [ ] 20.1 Write integration tests for MCP tools
  - Test tool registration
  - Test tool execution via agent
  - Test tool error handling
  - Test tool output formatting
  - _Requirements: 3.2, 5.1, 7.6, 7.7_

- [ ] 21. Build React dashboard UI
  - Create cloud accounts management page
  - Create resource browser with filters
  - Create resource detail view with metrics charts
  - Create activity feed component
  - Add real-time updates via SSE
  - Implement search and filtering UI
  - Add export functionality UI
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 10.1, 10.2_

- [ ] 21.1 Write frontend component tests
  - Test cloud account connection flow
  - Test resource browser
  - Test resource detail view
  - Test activity feed
  - Test search and filters
  - Test export UI
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 10.1, 10.2_

- [ ] 22. Implement Azure connector (optional)
  - Create `AzureConnector` class extending `BaseCloudConnector`
  - Implement credential validation
  - Implement resource discovery
  - Implement metrics collection
  - Add unit and property tests
  - _Requirements: 1.3, 3.2, 5.1_

- [ ] 23. Implement DigitalOcean connector (optional)
  - Create `DOConnector` class extending `BaseCloudConnector`
  - Implement credential validation
  - Implement resource discovery
  - Implement metrics collection
  - Add unit and property tests
  - _Requirements: 1.4, 3.2, 5.1_

- [ ] 24. Performance optimization
  - Add caching for frequently accessed data
  - Optimize database queries with indexes
  - Implement connection pooling
  - Add batch processing for bulk operations
  - Profile and optimize slow endpoints
  - _Requirements: All_

- [ ] 24.1 Write performance tests
  - Test dashboard load time
  - Test resource discovery performance
  - Test metrics query performance
  - Test concurrent user load
  - _Requirements: All_

- [ ] 25. Documentation and deployment
  - Write API documentation
  - Create user guide for connecting cloud accounts
  - Document MCP tool usage
  - Create deployment scripts
  - Set up monitoring and alerting
  - Configure CI/CD pipeline
  - _Requirements: All_

- [ ] 26. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- All tasks are required for comprehensive implementation
- Property-based tests ensure correctness across all inputs
- Each checkpoint ensures system stability before proceeding
- Azure and DigitalOcean connectors (tasks 22-23) can be deferred to post-MVP
- Integration with existing LangGraph agent happens in task 20
