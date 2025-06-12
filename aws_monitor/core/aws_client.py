"""
AWS Client Module - Core AWS API Integration
Handles all interactions with AWS services including Cost Explorer, CloudWatch, Organizations, etc.
"""

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
import logging
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

logger = logging.getLogger(__name__)


class AWSClient:
    """Main AWS client for interacting with multiple AWS services."""

    def __init__(self, profile_name: Optional[str] = None, role_arn: Optional[str] = None):
        """
        Initialize AWS client with appropriate credentials.

        Args:
            profile_name: AWS CLI profile name for local development
            role_arn: IAM role ARN for production/cross-account access
        """
        self.profile_name = profile_name
        self.role_arn = role_arn
        self._session = None
        self._org_client = None
        self._ce_client = None
        self._cloudwatch_client = None
        self._resource_groups_client = None
        self._sts_client = None

    @property
    def session(self) -> boto3.Session:
        """Get or create boto3 session."""
        if not self._session:
            if self.profile_name:
                self._session = boto3.Session(profile_name=self.profile_name)
            elif self.role_arn:
                # Assume role for cross-account access
                sts = boto3.client('sts')
                assumed_role = sts.assume_role(
                    RoleArn=self.role_arn,
                    RoleSessionName='aws-cost-monitor'
                )
                credentials = assumed_role['Credentials']
                self._session = boto3.Session(
                    aws_access_key_id=credentials['AccessKeyId'],
                    aws_secret_access_key=credentials['SecretAccessKey'],
                    aws_session_token=credentials['SessionToken']
                )
            else:
                self._session = boto3.Session()
        return self._session

    @property
    def organizations(self):
        """Get Organizations client."""
        if not self._org_client:
            self._org_client = self.session.client('organizations')
        return self._org_client

    @property
    def cost_explorer(self):
        """Get Cost Explorer client."""
        if not self._ce_client:
            self._ce_client = self.session.client('ce', region_name='us-east-1')
        return self._ce_client

    @property
    def cloudwatch(self):
        """Get CloudWatch client."""
        if not self._cloudwatch_client:
            self._cloudwatch_client = self.session.client('cloudwatch')
        return self._cloudwatch_client

    @property
    def resource_groups(self):
        """Get Resource Groups Tagging API client."""
        if not self._resource_groups_client:
            self._resource_groups_client = self.session.client('resourcegroupstaggingapi')
        return self._resource_groups_client

    def get_organization_accounts(self) -> List[Dict[str, Any]]:
        """Get all accounts in the AWS Organization."""
        try:
            accounts = []
            paginator = self.organizations.get_paginator('list_accounts')

            for page in paginator.paginate():
                accounts.extend(page['Accounts'])

            # Filter active accounts only
            active_accounts = [acc for acc in accounts if acc['Status'] == 'ACTIVE']
            logger.info(f"Found {len(active_accounts)} active accounts in organization")

            return active_accounts
        except ClientError as e:
            logger.error(f"Error fetching organization accounts: {e}")
            raise

    def get_cost_and_usage(self,
                          start_date: datetime,
                          end_date: datetime,
                          granularity: str = 'HOURLY',
                          metrics: List[str] = None,
                          group_by: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get cost and usage data from AWS Cost Explorer.

        Args:
            start_date: Start date for the query
            end_date: End date for the query
            granularity: HOURLY, DAILY, or MONTHLY
            metrics: List of metrics to retrieve (default: UnblendedCost, UsageQuantity)
            group_by: Grouping dimensions
        """
        if metrics is None:
            metrics = ['UnblendedCost', 'UsageQuantity']

        if group_by is None:
            group_by = [
                {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'},
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ]

        try:
            request = {
                'TimePeriod': {
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                'Granularity': granularity,
                'Metrics': metrics,
                'GroupBy': group_by
            }

            response = self.cost_explorer.get_cost_and_usage(**request)
            logger.info(f"Retrieved cost data from {start_date} to {end_date}")

            return response
        except ClientError as e:
            logger.error(f"Error fetching cost and usage data: {e}")
            raise

    def get_cost_forecast(self,
                         start_date: datetime,
                         end_date: datetime,
                         metric: str = 'UNBLENDED_COST',
                         granularity: str = 'DAILY') -> Dict[str, Any]:
        """Get cost forecast data."""
        try:
            response = self.cost_explorer.get_cost_forecast(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Metric=metric,
                Granularity=granularity
            )
            return response
        except ClientError as e:
            logger.error(f"Error fetching cost forecast: {e}")
            return {}

    def get_service_usage_metrics(self,
                                 service: str,
                                 account_id: str,
                                 start_time: datetime,
                                 end_time: datetime) -> List[Dict[str, Any]]:
        """
        Get detailed usage metrics for a specific service from CloudWatch.

        Args:
            service: AWS service name (e.g., 'EC2', 'Lambda')
            account_id: AWS account ID
            start_time: Start time for metrics
            end_time: End time for metrics
        """
        metrics_map = {
            'EC2': [
                {'namespace': 'AWS/EC2', 'metric': 'CPUUtilization', 'stat': 'Average'},
                {'namespace': 'AWS/EC2', 'metric': 'NetworkIn', 'stat': 'Sum'},
                {'namespace': 'AWS/EC2', 'metric': 'NetworkOut', 'stat': 'Sum'}
            ],
            'Lambda': [
                {'namespace': 'AWS/Lambda', 'metric': 'Invocations', 'stat': 'Sum'},
                {'namespace': 'AWS/Lambda', 'metric': 'Duration', 'stat': 'Average'},
                {'namespace': 'AWS/Lambda', 'metric': 'Errors', 'stat': 'Sum'}
            ],
            'RDS': [
                {'namespace': 'AWS/RDS', 'metric': 'CPUUtilization', 'stat': 'Average'},
                {'namespace': 'AWS/RDS', 'metric': 'DatabaseConnections', 'stat': 'Average'},
                {'namespace': 'AWS/RDS', 'metric': 'FreeStorageSpace', 'stat': 'Average'}
            ],
            'S3': [
                {'namespace': 'AWS/S3', 'metric': 'BucketSizeBytes', 'stat': 'Average'},
                {'namespace': 'AWS/S3', 'metric': 'NumberOfObjects', 'stat': 'Average'}
            ]
        }

        if service not in metrics_map:
            logger.warning(f"No metrics defined for service: {service}")
            return []

        results = []
        for metric_config in metrics_map[service]:
            try:
                # For cross-account access, we'd need to assume role here
                # For now, we'll use the current session
                response = self.cloudwatch.get_metric_statistics(
                    Namespace=metric_config['namespace'],
                    MetricName=metric_config['metric'],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,  # 1 hour
                    Statistics=[metric_config['stat']]
                )

                results.append({
                    'service': service,
                    'metric': metric_config['metric'],
                    'datapoints': response['Datapoints']
                })
            except ClientError as e:
                logger.error(f"Error fetching {service} metrics: {e}")

        return results

    def get_resource_inventory(self, account_ids: List[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get inventory of all tagged resources across accounts.

        Args:
            account_ids: List of account IDs to query (None for all)
        """
        inventory = {}

        try:
            paginator = self.resource_groups.get_paginator('get_resources')

            for page in paginator.paginate():
                for resource in page.get('ResourceTagMappingList', []):
                    arn = resource['ResourceARN']
                    # Parse account ID from ARN
                    account_id = arn.split(':')[4] if ':' in arn else 'unknown'

                    if account_ids and account_id not in account_ids:
                        continue

                    if account_id not in inventory:
                        inventory[account_id] = []

                    inventory[account_id].append({
                        'arn': arn,
                        'service': arn.split(':')[2] if ':' in arn else 'unknown',
                        'resource_type': arn.split(':')[5].split('/')[0] if ':' in arn and '/' in arn.split(':')[5] else 'unknown',
                        'tags': {tag['Key']: tag['Value'] for tag in resource.get('Tags', [])}
                    })

            logger.info(f"Retrieved {sum(len(resources) for resources in inventory.values())} resources")
            return inventory

        except ClientError as e:
            logger.error(f"Error fetching resource inventory: {e}")
            return {}

    def get_ec2_instances(self, account_id: str = None) -> List[Dict[str, Any]]:
        """Get EC2 instance details for an account."""
        try:
            ec2 = self.session.client('ec2')
            instances = []

            paginator = ec2.get_paginator('describe_instances')
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        instances.append({
                            'instance_id': instance['InstanceId'],
                            'instance_type': instance['InstanceType'],
                            'state': instance['State']['Name'],
                            'launch_time': instance.get('LaunchTime'),
                            'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])},
                            'account_id': account_id or instance.get('OwnerId')
                        })

            return instances
        except ClientError as e:
            logger.error(f"Error fetching EC2 instances: {e}")
            return []

    def get_lambda_functions(self, account_id: str = None) -> List[Dict[str, Any]]:
        """Get Lambda function details for an account."""
        try:
            lambda_client = self.session.client('lambda')
            functions = []

            paginator = lambda_client.get_paginator('list_functions')
            for page in paginator.paginate():
                for function in page['Functions']:
                    functions.append({
                        'function_name': function['FunctionName'],
                        'runtime': function['Runtime'],
                        'memory_size': function['MemorySize'],
                        'timeout': function['Timeout'],
                        'last_modified': function['LastModified'],
                        'account_id': account_id or function['FunctionArn'].split(':')[4]
                    })

            return functions
        except ClientError as e:
            logger.error(f"Error fetching Lambda functions: {e}")
            return []

    @lru_cache(maxsize=128)
    def get_service_last_month_cost(self, service: str, account_id: str) -> float:
        """Get last month's cost for a specific service and account (cached)."""
        try:
            end_date = datetime.now().replace(day=1)
            start_date = (end_date - timedelta(days=1)).replace(day=1)

            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                Filter={
                    'And': [
                        {'Dimensions': {'Key': 'SERVICE', 'Values': [service]}},
                        {'Dimensions': {'Key': 'LINKED_ACCOUNT', 'Values': [account_id]}}
                    ]
                }
            )

            if response['ResultsByTime']:
                return float(response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])
            return 0.0

        except ClientError as e:
            logger.error(f"Error fetching last month cost: {e}")
            return 0.0

    def parallel_fetch_metrics(self,
                             services: List[str],
                             account_ids: List[str],
                             start_time: datetime,
                             end_time: datetime,
                             max_workers: int = 10) -> Dict[str, Dict[str, Any]]:
        """
        Fetch metrics for multiple services and accounts in parallel.

        Args:
            services: List of AWS services
            account_ids: List of account IDs
            start_time: Start time for metrics
            end_time: End time for metrics
            max_workers: Maximum number of parallel threads
        """
        results = {}

        def fetch_metrics_for_service_account(service: str, account_id: str) -> Tuple[str, str, Any]:
            """Fetch metrics for a single service/account combination."""
            key = f"{account_id}:{service}"
            try:
                metrics = self.get_service_usage_metrics(service, account_id, start_time, end_time)
                return account_id, service, metrics
            except Exception as e:
                logger.error(f"Error fetching metrics for {key}: {e}")
                return account_id, service, []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for service in services:
                for account_id in account_ids:
                    future = executor.submit(fetch_metrics_for_service_account, service, account_id)
                    futures.append(future)

            for future in as_completed(futures):
                account_id, service, metrics = future.result()
                if account_id not in results:
                    results[account_id] = {}
                results[account_id][service] = metrics

        return results