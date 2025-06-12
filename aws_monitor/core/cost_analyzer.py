"""
Cost Analyzer Module - Processes and analyzes AWS cost data
Provides cost breakdowns, trends, and insights
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .aws_client import AWSClient
import pandas as pd
import numpy as np
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class CostAnalyzer:
    """Analyzes AWS cost data and provides insights."""

    def __init__(self, aws_client: 'AWSClient') -> None:
        """
        Initialize cost analyzer with AWS client.

        Args:
            aws_client: Instance of AWSClient for API calls
        """
        self.aws_client = aws_client

    def get_cost_breakdown(self, hours: int = 24, group_by: List[str] = None) -> Dict[str, Any]:
        """
        Get cost breakdown for specified time period.

        Args:
            hours: Number of hours to look back (default: 24)
            group_by: Dimensions to group by (default: account and service)

        Returns:
            Dictionary with cost breakdown data
        """
        if group_by is None:
            group_by = ["LINKED_ACCOUNT", "SERVICE"]

        # Calculate time range
        # Cost Explorer requires dates to be in the past and in UTC
        end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(hours=hours)
        
        # For hourly granularity, we can include today's partial data
        if hours <= 24:
            end_date = datetime.now()  # Include today's data for hourly view

        # Determine granularity based on time range
        # Note: HOURLY granularity requires opt-in from payer account
        # Using DAILY as default for better compatibility
        if hours <= 24:
            granularity = "DAILY"  # Changed from HOURLY for compatibility
        elif hours <= 168:  # 7 days
            granularity = "DAILY"
        else:
            granularity = "DAILY"

        # Build group by dimensions
        group_by_dims = [{"Type": "DIMENSION", "Key": dim} for dim in group_by]

        try:
            logger.info(f"Fetching costs from {start_date} to {end_date} with granularity {granularity}")
            
            # Get cost data
            response = self.aws_client.get_cost_and_usage(
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
                metrics=["UnblendedCost", "UsageQuantity"],
                group_by=group_by_dims,
            )

            # Process the response
            processed_data = self._process_cost_response(response, group_by)

            # Add account names
            accounts = self.aws_client.get_organization_accounts()
            account_map = {acc["Id"]: acc["Name"] for acc in accounts}

            # Calculate totals and percentages
            total_cost = sum(item["cost"] for item in processed_data["items"])

            for item in processed_data["items"]:
                item["percentage"] = (item["cost"] / total_cost * 100) if total_cost > 0 else 0
                if "account_id" in item:
                    item["account_name"] = account_map.get(item["account_id"], "Unknown")

            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_cost": total_cost,
                "currency": "USD",
                "breakdown": processed_data["items"],
                "time_series": processed_data["time_series"],
                "granularity": granularity,
            }

        except Exception as e:
            logger.error(f"Error getting cost breakdown: {e}")
            raise

    def _process_cost_response(
        self, response: Dict[str, Any], group_by: List[str]
    ) -> Dict[str, Any]:
        """Process Cost Explorer response into structured data."""
        items = defaultdict(lambda: {"cost": 0, "usage": 0})
        time_series = defaultdict(list)

        for result in response.get("ResultsByTime", []):
            timestamp = result["TimePeriod"]["Start"]

            for group in result.get("Groups", []):
                # Parse group keys
                key_parts = {}
                for i, dim in enumerate(group_by):
                    key_parts[dim.lower()] = group["Keys"][i]

                # Get metrics
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                usage = (
                    float(group["Metrics"]["UsageQuantity"]["Amount"])
                    if "UsageQuantity" in group["Metrics"]
                    else 0
                )

                # Create composite key
                if "linked_account" in key_parts and "service" in key_parts:
                    key = f"{key_parts['linked_account']}:{key_parts['service']}"
                    items[key]["account_id"] = key_parts["linked_account"]
                    items[key]["service"] = key_parts["service"]
                elif "service" in key_parts:
                    key = key_parts["service"]
                    items[key]["service"] = key_parts["service"]
                else:
                    key = str(group["Keys"])

                items[key]["cost"] += cost
                items[key]["usage"] += usage

                # Add to time series
                time_series[key].append({"timestamp": timestamp, "cost": cost, "usage": usage})

        # Convert to list and sort by cost
        items_list = []
        for key, data in items.items():
            item = data.copy()
            item["key"] = key
            items_list.append(item)

        items_list.sort(key=lambda x: x["cost"], reverse=True)

        return {"items": items_list, "time_series": dict(time_series)}

    def detect_anomalies(
        self, lookback_days: int = 7, threshold_percentage: float = 20.0
    ) -> List[Dict[str, Any]]:
        """
        Detect cost anomalies by comparing recent costs to historical baseline.

        Args:
            lookback_days: Number of days to analyze
            threshold_percentage: Percentage threshold for anomaly detection

        Returns:
            List of detected anomalies
        """
        anomalies = []

        try:
            # Get current period data
            current_end = datetime.now()
            current_start = current_end - timedelta(days=1)

            # Get historical baseline (same period last week)
            baseline_end = current_end - timedelta(days=7)
            baseline_start = baseline_end - timedelta(days=lookback_days)

            # Fetch both periods
            current_data = self.aws_client.get_cost_and_usage(
                start_date=current_start,
                end_date=current_end,
                granularity="DAILY",
                group_by=[
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                    {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
                ],
            )

            baseline_data = self.aws_client.get_cost_and_usage(
                start_date=baseline_start,
                end_date=baseline_end,
                granularity="DAILY",
                group_by=[
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                    {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
                ],
            )

            # Process and compare
            current_costs = self._extract_service_costs(current_data)
            baseline_costs = self._extract_service_costs(baseline_data)

            # Calculate daily averages for baseline
            baseline_daily_avg = {}
            for key, cost in baseline_costs.items():
                baseline_daily_avg[key] = cost / lookback_days

            # Compare and find anomalies
            for key, current_cost in current_costs.items():
                baseline_avg = baseline_daily_avg.get(key, 0)

                if baseline_avg > 0:
                    change_percentage = ((current_cost - baseline_avg) / baseline_avg) * 100

                    if abs(change_percentage) > threshold_percentage:
                        service, account_id = key.split(":")
                        anomalies.append(
                            {
                                "service": service,
                                "account_id": account_id,
                                "current_cost": current_cost,
                                "baseline_cost": baseline_avg,
                                "change_percentage": change_percentage,
                                "severity": "high" if abs(change_percentage) > 50 else "medium",
                                "type": "increase" if change_percentage > 0 else "decrease",
                            }
                        )
                elif current_cost > 10:  # New service with significant cost
                    service, account_id = key.split(":")
                    anomalies.append(
                        {
                            "service": service,
                            "account_id": account_id,
                            "current_cost": current_cost,
                            "baseline_cost": 0,
                            "change_percentage": 100,
                            "severity": "medium",
                            "type": "new_service",
                        }
                    )

            # Sort by severity and change percentage
            anomalies.sort(
                key=lambda x: (0 if x["severity"] == "high" else 1, -abs(x["change_percentage"]))
            )

            return anomalies

        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            return []

    def _extract_service_costs(self, cost_data: Dict[str, Any]) -> Dict[str, float]:
        """Extract service costs from Cost Explorer response."""
        costs = defaultdict(float)

        for result in cost_data.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]  # SERVICE dimension
                account_id = group["Keys"][1]  # LINKED_ACCOUNT dimension
                cost = float(group["Metrics"]["UnblendedCost"]["Amount"])

                key = f"{service}:{account_id}"
                costs[key] += cost

        return dict(costs)

    def get_cost_trends(
        self, days: int = 30, service: Optional[str] = None, account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get cost trends over time.

        Args:
            days: Number of days to analyze
            service: Specific service to filter (optional)
            account_id: Specific account to filter (optional)

        Returns:
            Cost trend data including daily costs and statistics
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Build filter if specified
        filter_dict = None
        if service or account_id:
            filters = []
            if service:
                filters.append({"Dimensions": {"Key": "SERVICE", "Values": [service]}})
            if account_id:
                filters.append({"Dimensions": {"Key": "LINKED_ACCOUNT", "Values": [account_id]}})

            if len(filters) > 1:
                filter_dict = {"And": filters}
            else:
                filter_dict = filters[0]

        try:
            # Get daily cost data without grouping for total costs
            request = {
                "TimePeriod": {
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                "Granularity": "DAILY",
                "Metrics": ["UnblendedCost"],
            }
            
            # Add filter if specified
            if filter_dict:
                request["Filter"] = filter_dict
            
            response = self.aws_client.cost_explorer.get_cost_and_usage(**request)

            # Extract daily costs
            daily_costs = []
            dates = []

            for result in response.get("ResultsByTime", []):
                date = result["TimePeriod"]["Start"]
                # Handle both response formats
                if "Total" in result:
                    cost = float(result["Total"]["UnblendedCost"]["Amount"])
                elif "Groups" in result and result["Groups"]:
                    # Sum all groups if grouped data
                    cost = sum(
                        float(group["Metrics"]["UnblendedCost"]["Amount"])
                        for group in result["Groups"]
                    )
                else:
                    cost = 0.0

                dates.append(date)
                daily_costs.append(cost)

            # Calculate statistics
            costs_array = np.array(daily_costs)

            # Calculate moving averages
            ma_7 = pd.Series(daily_costs).rolling(window=7, min_periods=1).mean().tolist()
            ma_30 = pd.Series(daily_costs).rolling(window=30, min_periods=1).mean().tolist()

            # Forecast next 7 days (simple linear regression)
            if len(daily_costs) >= 7:
                # Use last 7 days for trend
                x = np.arange(7)
                y = costs_array[-7:]

                # Linear regression
                coeffs = np.polyfit(x, y, 1)

                # Forecast
                forecast_days = 7
                forecast_x = np.arange(7, 7 + forecast_days)
                forecast_y = np.polyval(coeffs, forecast_x)

                forecast = {
                    "dates": [
                        (datetime.now() + timedelta(days=i + 1)).strftime("%Y-%m-%d")
                        for i in range(forecast_days)
                    ],
                    "values": forecast_y.tolist(),
                }
            else:
                forecast = None

            return {
                "dates": dates,
                "daily_costs": daily_costs,
                "moving_average_7": ma_7,
                "moving_average_30": ma_30,
                "statistics": {
                    "total": float(costs_array.sum()),
                    "average": float(costs_array.mean()),
                    "min": float(costs_array.min()),
                    "max": float(costs_array.max()),
                    "std_dev": float(costs_array.std()),
                    "trend": (
                        "increasing"
                        if len(daily_costs) >= 2 and daily_costs[-1] > daily_costs[-7]
                        else "decreasing"
                    ),
                },
                "forecast": forecast,
            }

        except Exception as e:
            logger.error(f"Error getting cost trends: {e}")
            raise

    def get_top_cost_drivers(self, hours: int = 24, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get top cost drivers (services/accounts with highest costs).

        Args:
            hours: Time period to analyze
            top_n: Number of top items to return

        Returns:
            List of top cost drivers
        """
        breakdown = self.get_cost_breakdown(hours=hours)

        # Get top N items
        top_items = breakdown["breakdown"][:top_n]

        # Enhance with additional context
        for item in top_items:
            # Add last month comparison if available
            if "service" in item and "account_id" in item:
                last_month_cost = self.aws_client.get_service_last_month_cost(
                    item["service"], item["account_id"]
                )

                if last_month_cost > 0:
                    daily_avg_last_month = last_month_cost / 30
                    current_daily_rate = item["cost"] * (24 / hours)
                    item["change_from_last_month"] = (
                        (current_daily_rate - daily_avg_last_month) / daily_avg_last_month * 100
                    )

        return top_items
