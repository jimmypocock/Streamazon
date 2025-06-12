"""Pytest configuration and shared fixtures."""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aws_monitor.core.aws_client import AWSClient
from aws_monitor.core.cost_analyzer import CostAnalyzer
from aws_monitor.core.usage_tracker import UsageTracker
from aws_monitor.core.anomaly_detector import AnomalyDetector


@pytest.fixture
def mock_boto3_session():
    """Mock boto3 session."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_aws_client(mock_boto3_session):
    """Mock AWS client with basic setup."""
    client = AWSClient()
    client._session = mock_boto3_session
    
    # Mock clients
    client._org_client = Mock()
    client._ce_client = Mock()
    client._cloudwatch_client = Mock()
    client._resource_groups_client = Mock()
    
    return client


@pytest.fixture
def sample_cost_data():
    """Sample cost data for testing."""
    return {
        'ResultsByTime': [
            {
                'TimePeriod': {
                    'Start': '2024-01-01',
                    'End': '2024-01-02'
                },
                'Groups': [
                    {
                        'Keys': ['Amazon EC2', '123456789012'],
                        'Metrics': {
                            'UnblendedCost': {'Amount': '100.50'},
                            'UsageQuantity': {'Amount': '24.0'}
                        }
                    },
                    {
                        'Keys': ['AWS Lambda', '123456789012'],
                        'Metrics': {
                            'UnblendedCost': {'Amount': '10.25'},
                            'UsageQuantity': {'Amount': '1000000.0'}
                        }
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_organization_accounts():
    """Sample organization accounts data."""
    return [
        {
            'Id': '123456789012',
            'Name': 'Production Account',
            'Email': 'prod@example.com',
            'Status': 'ACTIVE'
        },
        {
            'Id': '234567890123',
            'Name': 'Development Account',
            'Email': 'dev@example.com',
            'Status': 'ACTIVE'
        }
    ]


@pytest.fixture
def sample_ec2_instances():
    """Sample EC2 instances data."""
    return [
        {
            'instance_id': 'i-1234567890abcdef0',
            'instance_type': 't3.medium',
            'state': 'running',
            'launch_time': datetime.now() - timedelta(days=30),
            'tags': {'Name': 'WebServer', 'Environment': 'Production'},
            'account_id': '123456789012'
        },
        {
            'instance_id': 'i-0987654321fedcba0',
            'instance_type': 't3.small',
            'state': 'stopped',
            'launch_time': datetime.now() - timedelta(days=60),
            'tags': {'Name': 'TestServer', 'Environment': 'Development'},
            'account_id': '123456789012'
        }
    ]


@pytest.fixture
def sample_cloudwatch_metrics():
    """Sample CloudWatch metrics data."""
    return {
        'Datapoints': [
            {
                'Timestamp': datetime.now() - timedelta(hours=1),
                'Average': 45.5,
                'Sum': 1000.0,
                'SampleCount': 12
            },
            {
                'Timestamp': datetime.now() - timedelta(hours=2),
                'Average': 52.3,
                'Sum': 1200.0,
                'SampleCount': 12
            }
        ]
    }


@pytest.fixture
def cost_analyzer(mock_aws_client):
    """Cost analyzer instance with mocked AWS client."""
    return CostAnalyzer(mock_aws_client)


@pytest.fixture
def usage_tracker(mock_aws_client):
    """Usage tracker instance with mocked AWS client."""
    return UsageTracker(mock_aws_client)


@pytest.fixture
def anomaly_detector(mock_aws_client):
    """Anomaly detector instance with mocked AWS client."""
    return AnomalyDetector(mock_aws_client)