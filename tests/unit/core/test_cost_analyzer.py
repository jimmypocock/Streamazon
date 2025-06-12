"""Unit tests for Cost Analyzer module."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from aws_monitor.core.cost_analyzer import CostAnalyzer


class TestCostAnalyzer:
    """Test cases for CostAnalyzer class."""

    def test_initialization(self, mock_aws_client):
        """Test cost analyzer initialization."""
        analyzer = CostAnalyzer(mock_aws_client)
        assert analyzer.aws_client == mock_aws_client

    def test_get_cost_breakdown(self, cost_analyzer, mock_aws_client, sample_cost_data, sample_organization_accounts):
        """Test getting cost breakdown."""
        # Setup mocks
        mock_aws_client.get_cost_and_usage.return_value = sample_cost_data
        mock_aws_client.get_organization_accounts.return_value = sample_organization_accounts
        
        # Call method
        breakdown = cost_analyzer.get_cost_breakdown(hours=24)
        
        # Assertions
        assert breakdown['total_cost'] == 110.75  # 100.50 + 10.25
        assert len(breakdown['breakdown']) == 2
        assert breakdown['breakdown'][0]['service'] == 'Amazon EC2'
        assert breakdown['breakdown'][0]['cost'] == 100.50
        assert breakdown['breakdown'][0]['percentage'] == pytest.approx(90.74, 0.01)

    def test_get_cost_breakdown_empty_data(self, cost_analyzer, mock_aws_client):
        """Test cost breakdown with empty data."""
        mock_aws_client.get_cost_and_usage.return_value = {'ResultsByTime': []}
        mock_aws_client.get_organization_accounts.return_value = []
        
        breakdown = cost_analyzer.get_cost_breakdown(hours=24)
        
        assert breakdown['total_cost'] == 0
        assert len(breakdown['breakdown']) == 0

    def test_detect_anomalies(self, cost_analyzer, mock_aws_client):
        """Test anomaly detection."""
        # Create mock data with anomaly
        current_data = {
            'ResultsByTime': [{
                'TimePeriod': {'Start': '2024-01-02', 'End': '2024-01-03'},
                'Groups': [{
                    'Keys': ['Amazon EC2', '123456789012'],
                    'Metrics': {'UnblendedCost': {'Amount': '500.00'}}
                }]
            }]
        }
        
        baseline_data = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                    'Groups': [{
                        'Keys': ['Amazon EC2', '123456789012'],
                        'Metrics': {'UnblendedCost': {'Amount': '100.00'}}
                    }]
                }
            ] * 7  # 7 days of baseline
        }
        
        mock_aws_client.get_cost_and_usage.side_effect = [current_data, baseline_data]
        
        anomalies = cost_analyzer.detect_anomalies(lookback_days=7, threshold_percentage=20.0)
        
        assert len(anomalies) == 1
        assert anomalies[0]['service'] == 'Amazon EC2'
        assert anomalies[0]['type'] == 'increase'
        assert anomalies[0]['change_percentage'] == 400.0

    def test_get_cost_trends(self, cost_analyzer, mock_aws_client):
        """Test getting cost trends."""
        # Create trend data
        trend_data = {
            'ResultsByTime': []
        }
        
        for i in range(30):
            date = datetime.now() - timedelta(days=29-i)
            trend_data['ResultsByTime'].append({
                'TimePeriod': {
                    'Start': date.strftime('%Y-%m-%d'),
                    'End': (date + timedelta(days=1)).strftime('%Y-%m-%d')
                },
                'Total': {
                    'UnblendedCost': {'Amount': str(100 + i * 2)}  # Increasing trend
                }
            })
        
        mock_aws_client.cost_explorer.get_cost_and_usage.return_value = trend_data
        
        trends = cost_analyzer.get_cost_trends(days=30)
        
        assert len(trends['dates']) == 30
        assert len(trends['daily_costs']) == 30
        assert trends['statistics']['trend'] == 'increasing'
        assert trends['statistics']['total'] == sum(100 + i * 2 for i in range(30))
        assert 'forecast' in trends

    def test_get_cost_trends_with_filters(self, cost_analyzer, mock_aws_client):
        """Test getting cost trends with service and account filters."""
        mock_aws_client.cost_explorer.get_cost_and_usage.return_value = {
            'ResultsByTime': [{
                'TimePeriod': {'Start': '2024-01-01', 'End': '2024-01-02'},
                'Total': {'UnblendedCost': {'Amount': '50.00'}}
            }]
        }
        
        trends = cost_analyzer.get_cost_trends(
            days=1,
            service='EC2',
            account_id='123456789012'
        )
        
        # Verify filter was applied
        call_args = mock_aws_client.cost_explorer.get_cost_and_usage.call_args
        assert 'Filter' in call_args[1]
        assert call_args[1]['Filter']['And'][0]['Dimensions']['Values'] == ['EC2']
        assert call_args[1]['Filter']['And'][1]['Dimensions']['Values'] == ['123456789012']

    def test_get_top_cost_drivers(self, cost_analyzer, mock_aws_client, sample_cost_data, sample_organization_accounts):
        """Test getting top cost drivers."""
        mock_aws_client.get_cost_and_usage.return_value = sample_cost_data
        mock_aws_client.get_organization_accounts.return_value = sample_organization_accounts
        mock_aws_client.get_service_last_month_cost.return_value = 2000.0
        
        top_drivers = cost_analyzer.get_top_cost_drivers(hours=24, top_n=5)
        
        assert len(top_drivers) == 2  # We only have 2 items in sample data
        assert top_drivers[0]['service'] == 'Amazon EC2'
        assert 'change_from_last_month' in top_drivers[0]

    def test_process_cost_response(self, cost_analyzer):
        """Test processing cost explorer response."""
        response = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01T00:00:00Z'},
                    'Groups': [
                        {
                            'Keys': ['123456789012', 'Amazon EC2'],
                            'Metrics': {
                                'UnblendedCost': {'Amount': '50.00'},
                                'UsageQuantity': {'Amount': '100.0'}
                            }
                        },
                        {
                            'Keys': ['123456789012', 'Amazon EC2'],
                            'Metrics': {
                                'UnblendedCost': {'Amount': '25.00'},
                                'UsageQuantity': {'Amount': '50.0'}
                            }
                        }
                    ]
                }
            ]
        }
        
        processed = cost_analyzer._process_cost_response(
            response, 
            ['LINKED_ACCOUNT', 'SERVICE']
        )
        
        assert len(processed['items']) == 1
        assert processed['items'][0]['cost'] == 75.0  # 50 + 25
        assert processed['items'][0]['usage'] == 150.0  # 100 + 50
        assert '123456789012:Amazon EC2' in processed['time_series']

    def test_extract_service_costs(self, cost_analyzer):
        """Test extracting service costs from response."""
        cost_data = {
            'ResultsByTime': [
                {
                    'Groups': [
                        {
                            'Keys': ['Amazon EC2', '123456789012'],
                            'Metrics': {'UnblendedCost': {'Amount': '100.00'}}
                        },
                        {
                            'Keys': ['AWS Lambda', '123456789012'],
                            'Metrics': {'UnblendedCost': {'Amount': '50.00'}}
                        }
                    ]
                }
            ]
        }
        
        costs = cost_analyzer._extract_service_costs(cost_data)
        
        assert costs['Amazon EC2:123456789012'] == 100.0
        assert costs['AWS Lambda:123456789012'] == 50.0

    def test_error_handling(self, cost_analyzer, mock_aws_client):
        """Test error handling in cost analyzer."""
        mock_aws_client.get_cost_and_usage.side_effect = Exception("API Error")
        
        with pytest.raises(Exception):
            cost_analyzer.get_cost_breakdown(hours=24)

    @patch('aws_monitor.core.cost_analyzer.datetime')
    def test_date_range_calculation(self, mock_datetime, cost_analyzer, mock_aws_client):
        """Test correct date range calculation for different hour values."""
        mock_now = datetime(2024, 1, 15, 12, 0, 0)
        mock_datetime.now.return_value = mock_now
        
        mock_aws_client.get_cost_and_usage.return_value = {'ResultsByTime': []}
        mock_aws_client.get_organization_accounts.return_value = []
        
        # Test different hour ranges
        test_cases = [
            (24, 'HOURLY'),
            (168, 'DAILY'),  # 7 days
            (720, 'DAILY')   # 30 days
        ]
        
        for hours, expected_granularity in test_cases:
            cost_analyzer.get_cost_breakdown(hours=hours)
            
            call_args = mock_aws_client.get_cost_and_usage.call_args
            assert call_args[1]['granularity'] == expected_granularity