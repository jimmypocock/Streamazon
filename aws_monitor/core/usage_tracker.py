"""
Usage Tracker Module - Monitors and tracks AWS resource usage metrics
Provides real-time usage data that often precedes cost data
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .aws_client import AWSClient
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class UsageTracker:
    """Tracks and analyzes AWS resource usage metrics."""

    def __init__(self, aws_client: 'AWSClient') -> None:
        """
        Initialize usage tracker with AWS client.

        Args:
            aws_client: Instance of AWSClient for API calls
        """
        self.aws_client = aws_client

    def get_current_usage_summary(
        self, account_ids: Optional[List[str]] = None, services: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get current usage summary across services and accounts.

        Args:
            account_ids: List of account IDs to check (None for all)
            services: List of services to check (None for all common services)

        Returns:
            Dictionary with usage summary by service and account
        """
        if services is None:
            services = ["EC2", "Lambda", "RDS", "S3", "ECS", "DynamoDB"]

        if account_ids is None:
            accounts = self.aws_client.get_organization_accounts()
            account_ids = [acc["Id"] for acc in accounts]

        usage_summary = defaultdict(lambda: defaultdict(dict))

        # Get usage for each service
        for service in services:
            logger.info(f"Fetching usage for service: {service}")

            if service == "EC2":
                usage_summary[service] = self._get_ec2_usage(account_ids)
            elif service == "Lambda":
                usage_summary[service] = self._get_lambda_usage(account_ids)
            elif service == "RDS":
                usage_summary[service] = self._get_rds_usage(account_ids)
            elif service == "S3":
                usage_summary[service] = self._get_s3_usage(account_ids)
            elif service == "ECS":
                usage_summary[service] = self._get_ecs_usage(account_ids)
            elif service == "DynamoDB":
                usage_summary[service] = self._get_dynamodb_usage(account_ids)

        # Calculate totals
        total_usage = {
            "total_instances": 0,
            "total_functions": 0,
            "total_databases": 0,
            "total_storage_gb": 0,
            "services_in_use": len([s for s in usage_summary if usage_summary[s]]),
            "accounts_active": len(
                set(
                    account_id
                    for service_data in usage_summary.values()
                    for account_id in service_data.keys()
                )
            ),
        }

        return {
            "timestamp": datetime.now().isoformat(),
            "usage_by_service": dict(usage_summary),
            "summary": total_usage,
        }

    def _get_ec2_usage(self, account_ids: List[str]) -> Dict[str, Any]:
        """Get EC2 usage metrics for specified accounts."""
        ec2_usage = {}

        for account_id in account_ids:
            try:
                instances = self.aws_client.get_ec2_instances(account_id)

                # Count instances by state and type
                instance_counts = defaultdict(int)
                instance_types = defaultdict(int)

                for instance in instances:
                    state = instance["state"]
                    instance_type = instance["instance_type"]

                    if state == "running":
                        instance_counts["running"] += 1
                        instance_types[instance_type] += 1
                    else:
                        instance_counts[state] += 1

                # Get CloudWatch metrics for running instances
                if instance_counts["running"] > 0:
                    metrics = self._get_ec2_cloudwatch_metrics(account_id)
                else:
                    metrics = {}

                ec2_usage[account_id] = {
                    "instance_counts": dict(instance_counts),
                    "instance_types": dict(instance_types),
                    "total_instances": len(instances),
                    "running_instances": instance_counts["running"],
                    "metrics": metrics,
                }

            except Exception as e:
                logger.error(f"Error fetching EC2 usage for account {account_id}: {e}")
                ec2_usage[account_id] = {"error": str(e)}

        return ec2_usage

    def _get_lambda_usage(self, account_ids: List[str]) -> Dict[str, Any]:
        """Get Lambda usage metrics for specified accounts."""
        lambda_usage = {}

        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        for account_id in account_ids:
            try:
                functions = self.aws_client.get_lambda_functions(account_id)

                # Get invocation metrics
                total_invocations = 0
                total_errors = 0
                total_duration = 0

                # Use CloudWatch to get aggregated metrics
                metrics = self.aws_client.get_service_usage_metrics(
                    "Lambda", account_id, start_time, end_time
                )

                for metric_data in metrics:
                    if metric_data["metric"] == "Invocations":
                        total_invocations = sum(
                            dp["Sum"] for dp in metric_data.get("datapoints", [])
                        )
                    elif metric_data["metric"] == "Errors":
                        total_errors = sum(dp["Sum"] for dp in metric_data.get("datapoints", []))
                    elif metric_data["metric"] == "Duration":
                        total_duration = sum(
                            dp["Average"] * dp.get("SampleCount", 1)
                            for dp in metric_data.get("datapoints", [])
                        )

                lambda_usage[account_id] = {
                    "function_count": len(functions),
                    "invocations_24h": total_invocations,
                    "errors_24h": total_errors,
                    "average_duration_ms": (
                        total_duration / total_invocations if total_invocations > 0 else 0
                    ),
                    "error_rate": (
                        (total_errors / total_invocations * 100) if total_invocations > 0 else 0
                    ),
                    "functions": [
                        {
                            "name": f["function_name"],
                            "runtime": f["runtime"],
                            "memory": f["memory_size"],
                        }
                        for f in functions[:10]  # Top 10 functions
                    ],
                }

            except Exception as e:
                logger.error(f"Error fetching Lambda usage for account {account_id}: {e}")
                lambda_usage[account_id] = {"error": str(e)}

        return lambda_usage

    def _get_rds_usage(self, account_ids: List[str]) -> Dict[str, Any]:
        """Get RDS usage metrics for specified accounts."""
        rds_usage = {}

        for account_id in account_ids:
            try:
                # For now, using CloudWatch metrics
                # In a full implementation, we'd also call describe_db_instances
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=1)

                metrics = self.aws_client.get_service_usage_metrics(
                    "RDS", account_id, start_time, end_time
                )

                cpu_utilization = 0
                connections = 0
                free_storage = 0

                for metric_data in metrics:
                    if metric_data["metric"] == "CPUUtilization":
                        datapoints = metric_data.get("datapoints", [])
                        if datapoints:
                            cpu_utilization = sum(dp["Average"] for dp in datapoints) / len(
                                datapoints
                            )
                    elif metric_data["metric"] == "DatabaseConnections":
                        datapoints = metric_data.get("datapoints", [])
                        if datapoints:
                            connections = sum(dp["Average"] for dp in datapoints) / len(datapoints)
                    elif metric_data["metric"] == "FreeStorageSpace":
                        datapoints = metric_data.get("datapoints", [])
                        if datapoints:
                            free_storage = min(dp["Average"] for dp in datapoints) / (
                                1024**3
                            )  # Convert to GB

                rds_usage[account_id] = {
                    "average_cpu_percent": round(cpu_utilization, 2),
                    "average_connections": round(connections, 2),
                    "min_free_storage_gb": round(free_storage, 2),
                }

            except Exception as e:
                logger.error(f"Error fetching RDS usage for account {account_id}: {e}")
                rds_usage[account_id] = {"error": str(e)}

        return rds_usage

    def _get_s3_usage(self, account_ids: List[str]) -> Dict[str, Any]:
        """Get S3 usage metrics for specified accounts."""
        s3_usage = {}

        for account_id in account_ids:
            try:
                # Get S3 metrics from CloudWatch
                end_time = datetime.now()
                start_time = end_time - timedelta(days=1)

                metrics = self.aws_client.get_service_usage_metrics(
                    "S3", account_id, start_time, end_time
                )

                total_size_bytes = 0
                total_objects = 0

                for metric_data in metrics:
                    if metric_data["metric"] == "BucketSizeBytes":
                        datapoints = metric_data.get("datapoints", [])
                        if datapoints:
                            total_size_bytes = max(dp["Average"] for dp in datapoints)
                    elif metric_data["metric"] == "NumberOfObjects":
                        datapoints = metric_data.get("datapoints", [])
                        if datapoints:
                            total_objects = max(dp["Average"] for dp in datapoints)

                s3_usage[account_id] = {
                    "total_size_gb": round(total_size_bytes / (1024**3), 2),
                    "total_objects": int(total_objects),
                    "average_object_size_mb": round(
                        (total_size_bytes / total_objects / (1024**2)) if total_objects > 0 else 0,
                        2,
                    ),
                }

            except Exception as e:
                logger.error(f"Error fetching S3 usage for account {account_id}: {e}")
                s3_usage[account_id] = {"error": str(e)}

        return s3_usage

    def _get_ecs_usage(self, account_ids: List[str]) -> Dict[str, Any]:
        """Get ECS usage metrics for specified accounts."""
        ecs_usage = {}

        for account_id in account_ids:
            try:
                # Basic ECS metrics
                # In a full implementation, we'd call describe_clusters and describe_services
                ecs_usage[account_id] = {"clusters": 0, "services": 0, "running_tasks": 0}

            except Exception as e:
                logger.error(f"Error fetching ECS usage for account {account_id}: {e}")
                ecs_usage[account_id] = {"error": str(e)}

        return ecs_usage

    def _get_dynamodb_usage(self, account_ids: List[str]) -> Dict[str, Any]:
        """Get DynamoDB usage metrics for specified accounts."""
        dynamodb_usage = {}

        for account_id in account_ids:
            try:
                # Basic DynamoDB metrics
                # In a full implementation, we'd call list_tables and describe_table
                dynamodb_usage[account_id] = {
                    "table_count": 0,
                    "total_read_capacity": 0,
                    "total_write_capacity": 0,
                }

            except Exception as e:
                logger.error(f"Error fetching DynamoDB usage for account {account_id}: {e}")
                dynamodb_usage[account_id] = {"error": str(e)}

        return dynamodb_usage

    def _get_ec2_cloudwatch_metrics(self, account_id: str) -> Dict[str, float]:
        """Get aggregated EC2 CloudWatch metrics for an account."""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)

            metrics = self.aws_client.get_service_usage_metrics(
                "EC2", account_id, start_time, end_time
            )

            result = {
                "average_cpu_utilization": 0,
                "total_network_in_gb": 0,
                "total_network_out_gb": 0,
            }

            for metric_data in metrics:
                datapoints = metric_data.get("datapoints", [])
                if not datapoints:
                    continue

                if metric_data["metric"] == "CPUUtilization":
                    result["average_cpu_utilization"] = sum(
                        dp["Average"] for dp in datapoints
                    ) / len(datapoints)
                elif metric_data["metric"] == "NetworkIn":
                    result["total_network_in_gb"] = sum(dp["Sum"] for dp in datapoints) / (1024**3)
                elif metric_data["metric"] == "NetworkOut":
                    result["total_network_out_gb"] = sum(dp["Sum"] for dp in datapoints) / (1024**3)

            return result

        except Exception as e:
            logger.error(f"Error fetching EC2 CloudWatch metrics: {e}")
            return {}

    def get_usage_trends(
        self, service: str, account_id: str, metric: str, hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get usage trends for a specific service and metric.

        Args:
            service: AWS service name
            account_id: AWS account ID
            metric: Metric name to track
            hours: Number of hours to look back

        Returns:
            Usage trend data with timestamps and values
        """
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)

            # Determine period based on hours
            if hours <= 24:
                period = 300  # 5 minutes
            elif hours <= 168:  # 7 days
                period = 3600  # 1 hour
            else:
                period = 86400  # 1 day

            # Map metric names to CloudWatch namespaces and metric names
            metric_mapping = {
                "EC2": {
                    "cpu": ("AWS/EC2", "CPUUtilization", "Average"),
                    "network_in": ("AWS/EC2", "NetworkIn", "Sum"),
                    "network_out": ("AWS/EC2", "NetworkOut", "Sum"),
                },
                "Lambda": {
                    "invocations": ("AWS/Lambda", "Invocations", "Sum"),
                    "errors": ("AWS/Lambda", "Errors", "Sum"),
                    "duration": ("AWS/Lambda", "Duration", "Average"),
                },
                "RDS": {
                    "cpu": ("AWS/RDS", "CPUUtilization", "Average"),
                    "connections": ("AWS/RDS", "DatabaseConnections", "Average"),
                    "storage": ("AWS/RDS", "FreeStorageSpace", "Average"),
                },
            }

            if service not in metric_mapping or metric not in metric_mapping[service]:
                raise ValueError(f"Unsupported service/metric combination: {service}/{metric}")

            namespace, metric_name, statistic = metric_mapping[service][metric]

            # Get metric data
            response = self.aws_client.cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
                Statistics=[statistic],
            )

            # Process datapoints
            datapoints = response.get("Datapoints", [])
            datapoints.sort(key=lambda x: x["Timestamp"])

            timestamps = [dp["Timestamp"].isoformat() for dp in datapoints]
            values = [dp[statistic] for dp in datapoints]

            # Calculate statistics
            if values:
                avg_value = sum(values) / len(values)
                max_value = max(values)
                min_value = min(values)
            else:
                avg_value = max_value = min_value = 0

            return {
                "service": service,
                "account_id": account_id,
                "metric": metric,
                "period_seconds": period,
                "timestamps": timestamps,
                "values": values,
                "statistics": {
                    "average": avg_value,
                    "maximum": max_value,
                    "minimum": min_value,
                    "datapoint_count": len(values),
                },
            }

        except Exception as e:
            logger.error(f"Error getting usage trends: {e}")
            raise
