"""Unit tests for AWS Client module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

from aws_monitor.core.aws_client import AWSClient


class TestAWSClient:
    """Test cases for AWSClient class."""

    def test_initialization_with_profile(self):
        """Test AWS client initialization with profile name."""
        client = AWSClient(profile_name='test-profile')
        assert client.profile_name == 'test-profile'
        assert client.role_arn is None
        assert client._session is None

    def test_initialization_with_role_arn(self):
        """Test AWS client initialization with role ARN."""
        client = AWSClient(role_arn='arn:aws:iam::123456789012:role/TestRole')
        assert client.profile_name is None
        assert client.role_arn == 'arn:aws:iam::123456789012:role/TestRole'

    @patch('boto3.Session')
    def test_session_creation_with_profile(self, mock_session):
        """Test session creation with profile name."""
        client = AWSClient(profile_name='test-profile')
        session = client.session
        
        mock_session.assert_called_once_with(profile_name='test-profile')
        assert session == mock_session.return_value

    @patch('boto3.Session')
    @patch('boto3.client')
    def test_session_creation_with_role(self, mock_client, mock_session):
        """Test session creation with role assumption."""
        # Setup mocks
        mock_sts = Mock()
        mock_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'AKIATEST',
                'SecretAccessKey': 'SECRET',
                'SessionToken': 'TOKEN'
            }
        }
        
        client = AWSClient(role_arn='arn:aws:iam::123456789012:role/TestRole')
        session = client.session
        
        mock_sts.assume_role.assert_called_once_with(
            RoleArn='arn:aws:iam::123456789012:role/TestRole',
            RoleSessionName='aws-cost-monitor'
        )
        mock_session.assert_called_once_with(
            aws_access_key_id='AKIATEST',
            aws_secret_access_key='SECRET',
            aws_session_token='TOKEN'
        )

    def test_get_organization_accounts(self, mock_aws_client, sample_organization_accounts):
        """Test fetching organization accounts."""
        # Setup mock
        mock_aws_client._org_client.get_paginator.return_value.paginate.return_value = [
            {'Accounts': sample_organization_accounts}
        ]
        
        accounts = mock_aws_client.get_organization_accounts()
        
        assert len(accounts) == 2
        assert accounts[0]['Name'] == 'Production Account'
        assert accounts[1]['Status'] == 'ACTIVE'

    def test_get_organization_accounts_error(self, mock_aws_client):
        """Test error handling when fetching organization accounts."""
        mock_aws_client._org_client.get_paginator.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            'ListAccounts'
        )
        
        with pytest.raises(ClientError):
            mock_aws_client.get_organization_accounts()

    def test_get_cost_and_usage(self, mock_aws_client, sample_cost_data):
        """Test fetching cost and usage data."""
        mock_aws_client._ce_client.get_cost_and_usage.return_value = sample_cost_data
        
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 2)
        
        result = mock_aws_client.get_cost_and_usage(
            start_date=start_date,
            end_date=end_date,
            granularity='DAILY'
        )
        
        assert 'ResultsByTime' in result
        assert len(result['ResultsByTime']) == 1
        assert len(result['ResultsByTime'][0]['Groups']) == 2

    def test_get_cost_forecast(self, mock_aws_client):
        """Test fetching cost forecast data."""
        forecast_data = {
            'Total': {'Amount': '3000.00'},
            'ForecastResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-02', 'End': '2024-01-03'},
                    'MeanValue': '100.00'
                }
            ]
        }
        mock_aws_client._ce_client.get_cost_forecast.return_value = forecast_data
        
        start_date = datetime(2024, 1, 2)
        end_date = datetime(2024, 1, 31)
        
        result = mock_aws_client.get_cost_forecast(
            start_date=start_date,
            end_date=end_date
        )
        
        assert result == forecast_data
        mock_aws_client._ce_client.get_cost_forecast.assert_called_once()

    def test_get_service_usage_metrics(self, mock_aws_client, sample_cloudwatch_metrics):
        """Test fetching service usage metrics."""
        mock_aws_client._cloudwatch_client.get_metric_statistics.return_value = sample_cloudwatch_metrics
        
        metrics = mock_aws_client.get_service_usage_metrics(
            service='EC2',
            account_id='123456789012',
            start_time=datetime.now() - timedelta(hours=24),
            end_time=datetime.now()
        )
        
        assert len(metrics) == 3  # EC2 has 3 metrics defined
        assert metrics[0]['service'] == 'EC2'
        assert 'datapoints' in metrics[0]

    def test_get_resource_inventory(self, mock_aws_client):
        """Test fetching resource inventory."""
        mock_resources = {
            'ResourceTagMappingList': [
                {
                    'ResourceARN': 'arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890',
                    'Tags': [{'Key': 'Name', 'Value': 'WebServer'}]
                },
                {
                    'ResourceARN': 'arn:aws:s3:::my-bucket',
                    'Tags': [{'Key': 'Environment', 'Value': 'Production'}]
                }
            ]
        }
        
        mock_aws_client._resource_groups_client.get_paginator.return_value.paginate.return_value = [
            mock_resources
        ]
        
        inventory = mock_aws_client.get_resource_inventory()
        
        assert '123456789012' in inventory
        assert len(inventory['123456789012']) == 1
        assert inventory['123456789012'][0]['service'] == 'ec2'

    def test_get_ec2_instances(self, mock_aws_client):
        """Test fetching EC2 instances."""
        mock_instances = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'i-1234567890abcdef0',
                            'InstanceType': 't3.medium',
                            'State': {'Name': 'running'},
                            'LaunchTime': datetime.now() - timedelta(days=30),
                            'Tags': [{'Key': 'Name', 'Value': 'WebServer'}]
                        }
                    ]
                }
            ]
        }
        
        mock_ec2 = Mock()
        mock_aws_client.session.client.return_value = mock_ec2
        mock_ec2.get_paginator.return_value.paginate.return_value = [mock_instances]
        
        instances = mock_aws_client.get_ec2_instances()
        
        assert len(instances) == 1
        assert instances[0]['instance_id'] == 'i-1234567890abcdef0'
        assert instances[0]['state'] == 'running'

    def test_get_lambda_functions(self, mock_aws_client):
        """Test fetching Lambda functions."""
        mock_functions = {
            'Functions': [
                {
                    'FunctionName': 'test-function',
                    'Runtime': 'python3.9',
                    'MemorySize': 128,
                    'Timeout': 60,
                    'LastModified': '2024-01-01T00:00:00Z',
                    'FunctionArn': 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
                }
            ]
        }
        
        mock_lambda = Mock()
        mock_aws_client.session.client.return_value = mock_lambda
        mock_lambda.get_paginator.return_value.paginate.return_value = [mock_functions]
        
        functions = mock_aws_client.get_lambda_functions()
        
        assert len(functions) == 1
        assert functions[0]['function_name'] == 'test-function'
        assert functions[0]['memory_size'] == 128

    def test_get_service_last_month_cost(self, mock_aws_client):
        """Test fetching last month's cost for a service."""
        mock_response = {
            'ResultsByTime': [
                {
                    'Total': {
                        'UnblendedCost': {'Amount': '500.00'}
                    }
                }
            ]
        }
        mock_aws_client._ce_client.get_cost_and_usage.return_value = mock_response
        
        cost = mock_aws_client.get_service_last_month_cost('EC2', '123456789012')
        
        assert cost == 500.0

    def test_parallel_fetch_metrics(self, mock_aws_client):
        """Test parallel fetching of metrics."""
        mock_aws_client.get_service_usage_metrics = Mock(return_value=[
            {'metric': 'CPUUtilization', 'datapoints': []}
        ])
        
        services = ['EC2', 'Lambda']
        account_ids = ['123456789012', '234567890123']
        start_time = datetime.now() - timedelta(hours=24)
        end_time = datetime.now()
        
        results = mock_aws_client.parallel_fetch_metrics(
            services=services,
            account_ids=account_ids,
            start_time=start_time,
            end_time=end_time,
            max_workers=2
        )
        
        assert len(results) == 2  # Two accounts
        assert all(account_id in results for account_id in account_ids)
        assert mock_aws_client.get_service_usage_metrics.call_count == 4  # 2 services × 2 accounts