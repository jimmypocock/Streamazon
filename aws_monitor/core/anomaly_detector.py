"""
Anomaly Detector Module - Detects unusual patterns in costs and usage
Uses statistical methods to identify anomalies
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from collections import defaultdict
import logging
from scipy import stats

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detects anomalies in AWS costs and usage patterns."""

    def __init__(self, aws_client, threshold_multiplier: float = 2.0):
        """
        Initialize anomaly detector.

        Args:
            aws_client: Instance of AWSClient for API calls
            threshold_multiplier: Multiplier for standard deviation threshold
        """
        self.aws_client = aws_client
        self.threshold_multiplier = threshold_multiplier

    def detect_all_anomalies(self,
                           lookback_hours: int = 168,
                           sensitivity: str = 'medium') -> Dict[str, List[Dict[str, Any]]]:
        """
        Detect all types of anomalies across costs and usage.

        Args:
            lookback_hours: Hours to look back for baseline
            sensitivity: 'low', 'medium', or 'high'

        Returns:
            Dictionary with different types of anomalies
        """
        # Set threshold based on sensitivity
        sensitivity_map = {
            'low': 3.0,
            'medium': 2.0,
            'high': 1.5
        }
        self.threshold_multiplier = sensitivity_map.get(sensitivity, 2.0)

        anomalies = {
            'cost_anomalies': self.detect_cost_anomalies(lookback_hours),
            'usage_anomalies': self.detect_usage_anomalies(lookback_hours),
            'new_resources': self.detect_new_resources(lookback_hours),
            'stopped_resources': self.detect_stopped_resources(lookback_hours),
            'pattern_changes': self.detect_pattern_changes(lookback_hours)
        }

        # Calculate overall severity score
        total_anomalies = sum(len(v) for v in anomalies.values())

        anomalies['summary'] = {
            'total_anomalies': total_anomalies,
            'severity_score': self._calculate_severity_score(anomalies),
            'recommended_actions': self._get_recommended_actions(anomalies)
        }

        return anomalies

    def detect_cost_anomalies(self, lookback_hours: int = 168) -> List[Dict[str, Any]]:
        """
        Detect cost anomalies using statistical analysis.

        Args:
            lookback_hours: Hours to analyze for baseline

        Returns:
            List of detected cost anomalies
        """
        anomalies = []

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(hours=lookback_hours)

            # Get hourly cost data for more granular analysis
            response = self.aws_client.get_cost_and_usage(
                start_date=start_date,
                end_date=end_date,
                granularity='HOURLY' if lookback_hours <= 48 else 'DAILY',
                group_by=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
                ]
            )

            # Process data by service and account
            time_series_data = defaultdict(list)

            for result in response.get('ResultsByTime', []):
                timestamp = result['TimePeriod']['Start']

                for group in result.get('Groups', []):
                    service = group['Keys'][0]
                    account_id = group['Keys'][1]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])

                    key = f"{service}:{account_id}"
                    time_series_data[key].append({
                        'timestamp': timestamp,
                        'cost': cost
                    })

            # Analyze each service/account combination
            for key, data_points in time_series_data.items():
                if len(data_points) < 10:  # Need minimum data points
                    continue

                service, account_id = key.split(':')
                costs = [dp['cost'] for dp in data_points]

                # Calculate statistics
                mean_cost = np.mean(costs)
                std_cost = np.std(costs)

                if std_cost == 0:  # No variation
                    continue

                # Check recent values for anomalies
                recent_hours = min(24, len(data_points) // 4)
                recent_costs = costs[-recent_hours:]

                for i, cost in enumerate(recent_costs):
                    z_score = (cost - mean_cost) / std_cost

                    if abs(z_score) > self.threshold_multiplier:
                        # Calculate percentage change
                        baseline = mean_cost if mean_cost > 0 else 1
                        change_pct = ((cost - mean_cost) / baseline) * 100

                        anomalies.append({
                            'type': 'cost_spike' if z_score > 0 else 'cost_drop',
                            'service': service,
                            'account_id': account_id,
                            'timestamp': data_points[-(recent_hours-i)]['timestamp'],
                            'cost': cost,
                            'baseline_cost': mean_cost,
                            'z_score': z_score,
                            'change_percentage': change_pct,
                            'severity': self._calculate_anomaly_severity(z_score, change_pct),
                            'confidence': self._calculate_confidence(len(costs), std_cost)
                        })

            # Sort by severity and recency
            anomalies.sort(key=lambda x: (
                0 if x['severity'] == 'critical' else 1 if x['severity'] == 'high' else 2,
                -abs(x['z_score'])
            ))

            # Limit to top anomalies
            return anomalies[:20]

        except Exception as e:
            logger.error(f"Error detecting cost anomalies: {e}")
            return []

    def detect_usage_anomalies(self, lookback_hours: int = 168) -> List[Dict[str, Any]]:
        """
        Detect anomalies in resource usage patterns.

        Args:
            lookback_hours: Hours to analyze

        Returns:
            List of usage anomalies
        """
        anomalies = []

        # Services and metrics to check
        service_metrics = {
            'EC2': ['CPUUtilization', 'NetworkIn', 'NetworkOut'],
            'Lambda': ['Invocations', 'Errors', 'Duration'],
            'RDS': ['CPUUtilization', 'DatabaseConnections']
        }

        try:
            # Get current account list
            accounts = self.aws_client.get_organization_accounts()
            account_ids = [acc['Id'] for acc in accounts][:5]  # Limit for performance

            for service, metrics in service_metrics.items():
                for metric in metrics:
                    for account_id in account_ids:
                        anomaly = self._check_metric_anomaly(
                            service, account_id, metric, lookback_hours
                        )
                        if anomaly:
                            anomalies.append(anomaly)

            # Sort by severity
            anomalies.sort(key=lambda x: (
                0 if x.get('severity') == 'critical' else 1 if x.get('severity') == 'high' else 2,
                -abs(x.get('deviation', 0))
            ))

            return anomalies[:15]

        except Exception as e:
            logger.error(f"Error detecting usage anomalies: {e}")
            return []

    def _check_metric_anomaly(self,
                            service: str,
                            account_id: str,
                            metric: str,
                            lookback_hours: int) -> Optional[Dict[str, Any]]:
        """Check a specific metric for anomalies."""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=lookback_hours)

            # Get metric namespace
            namespace_map = {
                'EC2': 'AWS/EC2',
                'Lambda': 'AWS/Lambda',
                'RDS': 'AWS/RDS'
            }

            namespace = namespace_map.get(service)
            if not namespace:
                return None

            # Get metric data
            response = self.aws_client.cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric,
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['Average', 'Maximum']
            )

            datapoints = response.get('Datapoints', [])
            if len(datapoints) < 10:
                return None

            # Sort by timestamp
            datapoints.sort(key=lambda x: x['Timestamp'])

            # Extract values
            values = [dp['Average'] for dp in datapoints]

            # Calculate statistics
            mean_val = np.mean(values)
            std_val = np.std(values)

            if std_val == 0:
                return None

            # Check recent value
            recent_value = values[-1]
            z_score = (recent_value - mean_val) / std_val

            if abs(z_score) > self.threshold_multiplier:
                return {
                    'type': 'usage_anomaly',
                    'service': service,
                    'account_id': account_id,
                    'metric': metric,
                    'current_value': recent_value,
                    'baseline_value': mean_val,
                    'deviation': z_score,
                    'timestamp': datapoints[-1]['Timestamp'].isoformat(),
                    'severity': self._calculate_anomaly_severity(z_score, 0),
                    'description': f"{metric} for {service} is {z_score:.1f} standard deviations from normal"
                }

            return None

        except Exception as e:
            logger.error(f"Error checking metric anomaly: {e}")
            return None

    def detect_new_resources(self, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """
        Detect newly created resources that might indicate unexpected activity.

        Args:
            lookback_hours: Hours to look back

        Returns:
            List of new resources
        """
        new_resources = []

        try:
            # Check for new cost entries (services that weren't billed before)
            end_date = datetime.now()
            recent_start = end_date - timedelta(hours=lookback_hours)
            baseline_start = recent_start - timedelta(hours=lookback_hours * 2)

            # Get recent costs
            recent_response = self.aws_client.get_cost_and_usage(
                start_date=recent_start,
                end_date=end_date,
                granularity='DAILY',
                group_by=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
                ]
            )

            # Get baseline costs
            baseline_response = self.aws_client.get_cost_and_usage(
                start_date=baseline_start,
                end_date=recent_start,
                granularity='DAILY',
                group_by=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
                ]
            )

            # Extract service/account combinations
            recent_services = set()
            baseline_services = set()
            recent_costs = {}

            for result in recent_response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    key = f"{group['Keys'][0]}:{group['Keys'][1]}"
                    recent_services.add(key)
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    recent_costs[key] = recent_costs.get(key, 0) + cost

            for result in baseline_response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    key = f"{group['Keys'][0]}:{group['Keys'][1]}"
                    baseline_services.add(key)

            # Find new services
            new_service_keys = recent_services - baseline_services

            for key in new_service_keys:
                service, account_id = key.split(':')
                cost = recent_costs.get(key, 0)

                if cost > 1:  # Ignore tiny costs
                    new_resources.append({
                        'type': 'new_service',
                        'service': service,
                        'account_id': account_id,
                        'first_seen': recent_start.isoformat(),
                        'cost_since_start': cost,
                        'daily_rate': cost / (lookback_hours / 24),
                        'severity': 'high' if cost > 100 else 'medium',
                        'description': f"New service {service} detected in account {account_id}"
                    })

            # Sort by cost
            new_resources.sort(key=lambda x: x['cost_since_start'], reverse=True)

            return new_resources[:10]

        except Exception as e:
            logger.error(f"Error detecting new resources: {e}")
            return []

    def detect_stopped_resources(self, lookback_hours: int = 48) -> List[Dict[str, Any]]:
        """
        Detect resources that have stopped incurring costs.

        Args:
            lookback_hours: Hours to look back

        Returns:
            List of stopped resources
        """
        stopped_resources = []

        try:
            end_date = datetime.now()
            recent_start = end_date - timedelta(hours=24)
            baseline_end = recent_start
            baseline_start = baseline_end - timedelta(hours=lookback_hours)

            # Get baseline costs
            baseline_response = self.aws_client.get_cost_and_usage(
                start_date=baseline_start,
                end_date=baseline_end,
                granularity='DAILY',
                group_by=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
                ]
            )

            # Get recent costs
            recent_response = self.aws_client.get_cost_and_usage(
                start_date=recent_start,
                end_date=end_date,
                granularity='DAILY',
                group_by=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'}
                ]
            )

            # Process responses
            baseline_costs = defaultdict(float)
            recent_costs = defaultdict(float)

            for result in baseline_response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    key = f"{group['Keys'][0]}:{group['Keys'][1]}"
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    baseline_costs[key] += cost

            for result in recent_response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    key = f"{group['Keys'][0]}:{group['Keys'][1]}"
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    recent_costs[key] += cost

            # Find stopped services
            for key, baseline_cost in baseline_costs.items():
                recent_cost = recent_costs.get(key, 0)

                if baseline_cost > 10 and recent_cost < baseline_cost * 0.1:
                    service, account_id = key.split(':')

                    stopped_resources.append({
                        'type': 'stopped_service',
                        'service': service,
                        'account_id': account_id,
                        'baseline_daily_cost': baseline_cost / (lookback_hours / 24),
                        'current_daily_cost': recent_cost,
                        'savings': baseline_cost - recent_cost,
                        'severity': 'info',
                        'description': f"Service {service} appears to have stopped in account {account_id}"
                    })

            # Sort by savings
            stopped_resources.sort(key=lambda x: x['savings'], reverse=True)

            return stopped_resources[:10]

        except Exception as e:
            logger.error(f"Error detecting stopped resources: {e}")
            return []

    def detect_pattern_changes(self, lookback_hours: int = 168) -> List[Dict[str, Any]]:
        """
        Detect changes in usage patterns (e.g., different time-of-day usage).

        Args:
            lookback_hours: Hours to analyze

        Returns:
            List of pattern changes
        """
        pattern_changes = []

        # This is a simplified implementation
        # A full implementation would use more sophisticated time series analysis

        try:
            # Check for services with changing usage patterns
            services_to_check = ['EC2', 'Lambda', 'RDS']

            for service in services_to_check:
                # Get hourly data for pattern analysis
                # In a real implementation, we'd analyze hourly patterns
                # and look for changes in peak hours, weekend vs weekday, etc.

                # Placeholder for pattern detection
                logger.info(f"Checking usage patterns for {service}")

            return pattern_changes

        except Exception as e:
            logger.error(f"Error detecting pattern changes: {e}")
            return []

    def _calculate_anomaly_severity(self, z_score: float, change_pct: float) -> str:
        """Calculate severity level of an anomaly."""
        abs_z = abs(z_score)
        abs_change = abs(change_pct)

        if abs_z > 4 or abs_change > 100:
            return 'critical'
        elif abs_z > 3 or abs_change > 50:
            return 'high'
        elif abs_z > 2 or abs_change > 25:
            return 'medium'
        else:
            return 'low'

    def _calculate_confidence(self, sample_size: int, std_dev: float) -> float:
        """Calculate confidence score for anomaly detection."""
        # Higher sample size and lower variance = higher confidence
        size_factor = min(sample_size / 100, 1.0)
        variance_factor = 1.0 / (1.0 + std_dev)

        return round(size_factor * variance_factor, 2)

    def _calculate_severity_score(self, anomalies: Dict[str, List]) -> float:
        """Calculate overall severity score from all anomalies."""
        severity_weights = {
            'critical': 10,
            'high': 5,
            'medium': 2,
            'low': 1,
            'info': 0.5
        }

        total_score = 0
        for anomaly_type, anomaly_list in anomalies.items():
            if anomaly_type == 'summary':
                continue

            for anomaly in anomaly_list:
                severity = anomaly.get('severity', 'low')
                total_score += severity_weights.get(severity, 1)

        return round(total_score, 2)

    def _get_recommended_actions(self, anomalies: Dict[str, List]) -> List[str]:
        """Get recommended actions based on detected anomalies."""
        actions = []

        # Check for critical anomalies
        critical_count = sum(
            1 for anomaly_list in anomalies.values()
            if isinstance(anomaly_list, list)
            for anomaly in anomaly_list
            if anomaly.get('severity') == 'critical'
        )

        if critical_count > 0:
            actions.append(f"URGENT: Review {critical_count} critical anomalies immediately")

        # Check for cost spikes
        cost_anomalies = anomalies.get('cost_anomalies', [])
        if any(a['type'] == 'cost_spike' for a in cost_anomalies):
            actions.append("Review and investigate unexpected cost increases")

        # Check for new resources
        new_resources = anomalies.get('new_resources', [])
        if new_resources:
            actions.append(f"Verify {len(new_resources)} newly detected services are authorized")

        # Check for usage anomalies
        usage_anomalies = anomalies.get('usage_anomalies', [])
        if usage_anomalies:
            actions.append("Monitor resource usage patterns for potential issues")

        if not actions:
            actions.append("No immediate actions required - continue monitoring")

        return actions