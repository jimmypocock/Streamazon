"""
AWS Cost & Usage Monitor - Streamlit Web Dashboard
Main web interface for monitoring AWS costs and usage across accounts
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.anomaly_detector import AnomalyDetector  # noqa: E402
from core.aws_client import AWSClient  # noqa: E402
from core.cost_analyzer import CostAnalyzer  # noqa: E402
from core.usage_tracker import UsageTracker  # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AWS Cost & Usage Monitor",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better styling
st.markdown(
    """
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .anomaly-critical {
        background-color: #ff4b4b;
        color: white;
        padding: 0.5rem;
        border-radius: 0.25rem;
        margin: 0.25rem 0;
    }
    .anomaly-high {
        background-color: #ffa500;
        color: white;
        padding: 0.5rem;
        border-radius: 0.25rem;
        margin: 0.25rem 0;
    }
    .anomaly-medium {
        background-color: #ffcc00;
        color: black;
        padding: 0.5rem;
        border-radius: 0.25rem;
        margin: 0.25rem 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "aws_client" not in st.session_state:
    st.session_state.aws_client = None
    st.session_state.cost_analyzer = None
    st.session_state.usage_tracker = None
    st.session_state.anomaly_detector = None
    st.session_state.last_refresh = None
    st.session_state.data_cache = {}


def initialize_clients() -> bool:
    """Initialize AWS clients and analyzers."""
    try:
        # Get AWS profile from environment or use default
        profile_name = os.getenv("AWS_PROFILE", "default")

        # Initialize clients
        aws_client = AWSClient(profile_name=profile_name)
        cost_analyzer = CostAnalyzer(aws_client)
        usage_tracker = UsageTracker(aws_client)
        anomaly_detector = AnomalyDetector(aws_client)

        # Store in session state
        st.session_state.aws_client = aws_client
        st.session_state.cost_analyzer = cost_analyzer
        st.session_state.usage_tracker = usage_tracker
        st.session_state.anomaly_detector = anomaly_detector
        st.session_state.last_refresh = datetime.now()

        return True
    except Exception as e:
        st.error(f"Failed to initialize AWS clients: {str(e)}")
        st.info("Please ensure your AWS credentials are properly configured.")
        return False


def format_currency(value: float) -> str:
    """Format value as currency."""
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Format value as percentage."""
    return f"{value:+.1f}%"


def render_cost_breakdown_chart(breakdown_data: Dict[str, Any]) -> None:
    """Render cost breakdown chart."""
    if not breakdown_data["breakdown"]:
        st.warning("No cost data available for the selected period.")
        return

    # Prepare data for visualization
    df = pd.DataFrame(breakdown_data["breakdown"])

    # Create treemap for hierarchical view
    if "account_id" in df.columns and "service" in df.columns:
        fig = px.treemap(
            df,
            path=["account_name", "service"],
            values="cost",
            title=(
                f"Cost Breakdown by Account and Service "
                f"(Total: {format_currency(breakdown_data['total_cost'])})"
            ),
            color="cost",
            color_continuous_scale="RdYlBu_r",
            hover_data={"cost": ":,.2f", "percentage": ":.1f"},
        )
    else:
        # Simple bar chart if no hierarchy
        fig = px.bar(
            df.head(20),
            x="service",
            y="cost",
            title=(
                f"Top 20 Services by Cost "
                f"(Total: {format_currency(breakdown_data['total_cost'])})"
            ),
            color="cost",
            color_continuous_scale="RdYlBu_r",
        )

    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)


def render_cost_timeline(breakdown_data: Dict[str, Any]) -> None:
    """Render cost timeline chart."""
    if not breakdown_data.get("time_series"):
        return

    # Prepare time series data
    all_series = []
    for key, series in breakdown_data["time_series"].items():
        for point in series:
            all_series.append(
                {"timestamp": point["timestamp"], "cost": point["cost"], "key": key}
            )

    if not all_series:
        return

    df_series = pd.DataFrame(all_series)
    df_series["timestamp"] = pd.to_datetime(df_series["timestamp"])

    # Group by timestamp and sum costs
    df_timeline = df_series.groupby("timestamp")["cost"].sum().reset_index()

    # Create line chart
    fig = px.line(
        df_timeline,
        x="timestamp",
        y="cost",
        title=f"Cost Timeline ({breakdown_data['granularity']})",
        labels={"cost": "Cost ($)", "timestamp": "Time"},
    )

    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


def render_anomaly_card(anomaly: Dict[str, Any]) -> None:
    """Render an anomaly card with appropriate styling."""
    severity_class = f"anomaly-{anomaly.get('severity', 'medium')}"

    if anomaly["type"] == "cost_spike":
        icon = "📈"
        title = f"Cost Spike: {anomaly['service']}"
        message = (
            f"Cost increased by {format_percentage(anomaly['change_percentage'])} "
            f"from baseline"
        )
    elif anomaly["type"] == "cost_drop":
        icon = "📉"
        title = f"Cost Drop: {anomaly['service']}"
        message = (
            f"Cost decreased by {format_percentage(anomaly['change_percentage'])} "
            f"from baseline"
        )
    elif anomaly["type"] == "new_service":
        icon = "🆕"
        title = f"New Service: {anomaly['service']}"
        message = (
            f"First detected {anomaly.get('first_seen', 'recently')}, "
            f"costing {format_currency(anomaly.get('cost_since_start', 0))}"
        )
    elif anomaly["type"] == "usage_anomaly":
        icon = "⚠️"
        title = f"Usage Anomaly: {anomaly['service']}"
        message = anomaly.get("description", "Unusual usage pattern detected")
    else:
        icon = "ℹ️"
        title = anomaly.get("type", "Anomaly")
        message = anomaly.get("description", "Anomaly detected")

    st.markdown(
        f"""
    <div class="{severity_class}">
        <strong>{icon} {title}</strong><br>
        Account: {anomaly.get('account_id', 'N/A')}<br>
        {message}
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_usage_metrics(usage_data: Dict[str, Any]) -> None:
    """Render usage metrics dashboard."""
    if not usage_data.get("usage_by_service"):
        st.warning("No usage data available.")
        return

    # Create tabs for different services
    services = list(usage_data["usage_by_service"].keys())
    if not services:
        st.info("No services with usage data found.")
        return

    tabs = st.tabs(services)

    for i, service in enumerate(services):
        with tabs[i]:
            service_data = usage_data["usage_by_service"][service]

            if service == "EC2":
                render_ec2_usage(service_data)
            elif service == "Lambda":
                render_lambda_usage(service_data)
            elif service == "RDS":
                render_rds_usage(service_data)
            elif service == "S3":
                render_s3_usage(service_data)
            else:
                st.json(service_data)


def render_ec2_usage(ec2_data: Dict[str, Any]) -> None:
    """Render EC2 usage metrics."""
    total_instances = sum(
        acc.get("total_instances", 0) for acc in ec2_data.values() if isinstance(acc, dict)
    )
    running_instances = sum(
        acc.get("running_instances", 0) for acc in ec2_data.values() if isinstance(acc, dict)
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Instances", total_instances)
    with col2:
        st.metric("Running Instances", running_instances)
    with col3:
        st.metric("Stopped Instances", total_instances - running_instances)
    with col4:
        utilization = (running_instances / total_instances * 100) if total_instances > 0 else 0
        st.metric("Utilization", f"{utilization:.1f}%")

    # Instance type distribution
    instance_types: Dict[str, int] = {}
    for account_data in ec2_data.values():
        if isinstance(account_data, dict) and "instance_types" in account_data:
            for itype, count in account_data["instance_types"].items():
                instance_types[itype] = instance_types.get(itype, 0) + count

    if instance_types:
        df_types = pd.DataFrame(list(instance_types.items()), columns=["Type", "Count"])
        fig = px.pie(df_types, values="Count", names="Type", title="Instance Type Distribution")
        st.plotly_chart(fig, use_container_width=True)


def render_lambda_usage(lambda_data: Dict[str, Any]) -> None:
    """Render Lambda usage metrics."""
    total_functions = sum(
        acc.get("function_count", 0) for acc in lambda_data.values() if isinstance(acc, dict)
    )
    total_invocations = sum(
        acc.get("invocations_24h", 0) for acc in lambda_data.values() if isinstance(acc, dict)
    )
    total_errors = sum(
        acc.get("errors_24h", 0) for acc in lambda_data.values() if isinstance(acc, dict)
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Functions", total_functions)
    with col2:
        st.metric("Invocations (24h)", f"{total_invocations:,}")
    with col3:
        st.metric("Errors (24h)", f"{total_errors:,}")
    with col4:
        error_rate = (total_errors / total_invocations * 100) if total_invocations > 0 else 0
        st.metric("Error Rate", f"{error_rate:.2f}%")


def render_rds_usage(rds_data: Dict[str, Any]) -> None:
    """Render RDS usage metrics."""
    avg_cpu = []
    for acc_data in rds_data.values():
        if isinstance(acc_data, dict) and "average_cpu_percent" in acc_data:
            avg_cpu.append(acc_data["average_cpu_percent"])

    if avg_cpu:
        overall_avg_cpu = sum(avg_cpu) / len(avg_cpu)
        st.metric("Average CPU Utilization", f"{overall_avg_cpu:.1f}%")


def render_s3_usage(s3_data: Dict[str, Any]) -> None:
    """Render S3 usage metrics."""
    total_size = sum(
        acc.get("total_size_gb", 0) for acc in s3_data.values() if isinstance(acc, dict)
    )
    total_objects = sum(
        acc.get("total_objects", 0) for acc in s3_data.values() if isinstance(acc, dict)
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Storage", f"{total_size:,.1f} GB")
    with col2:
        st.metric("Total Objects", f"{total_objects:,}")
    with col3:
        avg_size = (total_size * 1024 / total_objects) if total_objects > 0 else 0
        st.metric("Avg Object Size", f"{avg_size:.1f} MB")


def main() -> None:
    """Main application function."""
    st.title("🔍 AWS Cost & Usage Monitor")
    st.markdown(
        "Real-time monitoring of AWS costs and resource usage across "
        "your organization"
    )

    # Sidebar configuration
    with st.sidebar:
        st.header("Configuration")

        # Initialize button
        if st.button("🔄 Initialize/Refresh", type="primary"):
            with st.spinner("Initializing AWS clients..."):
                if initialize_clients():
                    st.success("Successfully connected to AWS!")
                    # Clear cache on refresh
                    st.session_state.data_cache = {}

        # Time range selector
        st.subheader("Time Range")
        time_range = st.selectbox(
            "Select period", ["Last 24 hours", "Last 7 days", "Last 30 days", "Custom"], index=0
        )

        if time_range == "Custom":
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start date", datetime.now() - timedelta(days=7))
            with col2:
                end_date = st.date_input("End date", datetime.now())
            hours = int((end_date - start_date).total_seconds() / 3600)
        else:
            hours_map = {"Last 24 hours": 24, "Last 7 days": 168, "Last 30 days": 720}
            hours = hours_map[time_range]

        # Refresh interval
        st.subheader("Auto Refresh")
        auto_refresh = st.checkbox("Enable auto-refresh")
        if auto_refresh:
            refresh_interval = st.slider("Refresh interval (minutes)", 5, 60, 15)
            st.info(f"Data will refresh every {refresh_interval} minutes")

        # Display last refresh time
        if st.session_state.last_refresh:
            st.caption(
                f"Last refresh: "
                f"{st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}"
            )

    # Main content area
    if not st.session_state.aws_client:
        st.warning("Please initialize AWS connection using the button in the sidebar.")
        st.info(
            """
        **Getting Started:**
        1. Ensure your AWS credentials are configured
        2. Click 'Initialize/Refresh' in the sidebar
        3. Select your desired time range
        4. Explore the cost and usage data
        """
        )
        return

    # Create tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "📊 Cost Overview",
            "📈 Usage Metrics",
            "🚨 Anomalies",
            "📋 Resource Inventory",
            "📉 Trends & Forecast",
        ]
    )

    with tab1:
        st.header("Cost Overview")

        # Check cache
        cache_key = f"cost_breakdown_{hours}"
        if cache_key in st.session_state.data_cache:
            breakdown_data = st.session_state.data_cache[cache_key]
        else:
            with st.spinner("Fetching cost data..."):
                try:
                    breakdown_data = st.session_state.cost_analyzer.get_cost_breakdown(hours=hours)
                    st.session_state.data_cache[cache_key] = breakdown_data
                except Exception as e:
                    st.error(f"Error fetching cost data: {str(e)}")
                    return

        # Display key metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Cost",
                format_currency(breakdown_data["total_cost"]),
                help=f"Total cost for the last {hours} hours",
            )

        with col2:
            daily_rate = breakdown_data["total_cost"] * (24 / hours)
            st.metric(
                "Daily Rate",
                format_currency(daily_rate),
                help="Extrapolated daily cost based on current rate",
            )

        with col3:
            monthly_estimate = daily_rate * 30
            st.metric(
                "Monthly Estimate",
                format_currency(monthly_estimate),
                help="Estimated monthly cost at current rate",
            )

        with col4:
            # Get accounts
            accounts = st.session_state.aws_client.get_organization_accounts()
            st.metric("Active Accounts", len(accounts))

        # Cost breakdown visualization
        st.subheader("Cost Breakdown")
        render_cost_breakdown_chart(breakdown_data)

        # Cost timeline
        st.subheader("Cost Timeline")
        render_cost_timeline(breakdown_data)

        # Top cost drivers
        st.subheader("Top Cost Drivers")
        if breakdown_data["breakdown"]:
            top_items = breakdown_data["breakdown"][:10]
            df_top = pd.DataFrame(top_items)

            # Format the dataframe for display
            display_columns = ["service", "account_name", "cost", "percentage"]
            if all(col in df_top.columns for col in display_columns):
                df_display = df_top[display_columns].copy()
                df_display["cost"] = df_display["cost"].apply(format_currency)
                df_display["percentage"] = df_display["percentage"].apply(lambda x: f"{x:.1f}%")
                df_display.columns = ["Service", "Account", "Cost", "% of Total"]
                st.dataframe(df_display, use_container_width=True, hide_index=True)

    with tab2:
        st.header("Usage Metrics")

        # Fetch usage data
        cache_key = f"usage_summary_{hours}"
        if cache_key in st.session_state.data_cache:
            usage_data = st.session_state.data_cache[cache_key]
        else:
            with st.spinner("Fetching usage metrics..."):
                try:
                    usage_data = st.session_state.usage_tracker.get_current_usage_summary()
                    st.session_state.data_cache[cache_key] = usage_data
                except Exception as e:
                    st.error(f"Error fetching usage data: {str(e)}")
                    usage_data = {}

        if usage_data:
            # Summary metrics
            summary = usage_data.get("summary", {})
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Services in Use", summary.get("services_in_use", 0))
            with col2:
                st.metric("Active Accounts", summary.get("accounts_active", 0))
            with col3:
                st.metric("Data Timestamp", usage_data.get("timestamp", "N/A")[:19])

            # Service-specific metrics
            st.subheader("Service Usage Details")
            render_usage_metrics(usage_data)

    with tab3:
        st.header("Anomaly Detection")

        # Anomaly detection settings
        col1, col2 = st.columns([3, 1])
        with col1:
            sensitivity = st.select_slider(
                "Detection Sensitivity",
                options=["low", "medium", "high"],
                value="medium",
                help=(
                    "Higher sensitivity detects more anomalies but may include "
                    "more false positives"
                ),
            )
        with col2:
            if st.button("🔍 Detect Anomalies"):
                st.session_state.data_cache.pop("anomalies", None)

        # Fetch anomalies
        cache_key = "anomalies"
        if cache_key in st.session_state.data_cache:
            all_anomalies = st.session_state.data_cache[cache_key]
        else:
            with st.spinner("Detecting anomalies..."):
                try:
                    all_anomalies = st.session_state.anomaly_detector.detect_all_anomalies(
                        lookback_hours=hours, sensitivity=sensitivity
                    )
                    st.session_state.data_cache[cache_key] = all_anomalies
                except Exception as e:
                    st.error(f"Error detecting anomalies: {str(e)}")
                    all_anomalies = {}

        if all_anomalies:
            # Summary
            summary = all_anomalies.get("summary", {})
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Anomalies", summary.get("total_anomalies", 0))
            with col2:
                st.metric("Severity Score", summary.get("severity_score", 0))
            with col3:
                st.metric("Detection Time", datetime.now().strftime("%H:%M:%S"))

            # Recommended actions
            st.subheader("Recommended Actions")
            for action in summary.get("recommended_actions", []):
                st.info(f"• {action}")

            # Anomaly details
            st.subheader("Detected Anomalies")

            # Create tabs for different anomaly types
            anomaly_types = [k for k in all_anomalies.keys() if k != "summary" and all_anomalies[k]]

            if anomaly_types:
                anomaly_tabs = st.tabs([t.replace("_", " ").title() for t in anomaly_types])

                for i, anomaly_type in enumerate(anomaly_types):
                    with anomaly_tabs[i]:
                        anomalies = all_anomalies[anomaly_type]

                        if anomalies:
                            st.caption(f"Found {len(anomalies)} {anomaly_type.replace('_', ' ')}")

                            for anomaly in anomalies[:10]:  # Show top 10
                                render_anomaly_card(anomaly)
                        else:
                            st.info(f"No {anomaly_type.replace('_', ' ')} detected")
            else:
                st.success("No anomalies detected! Your AWS usage appears normal.")

    with tab4:
        st.header("Resource Inventory")

        with st.spinner("Fetching resource inventory..."):
            try:
                inventory = st.session_state.aws_client.get_resource_inventory()

                if inventory:
                    # Summary
                    total_resources = sum(len(resources) for resources in inventory.values())
                    st.metric("Total Tagged Resources", total_resources)

                    # Resources by account
                    st.subheader("Resources by Account")

                    for account_id, resources in inventory.items():
                        with st.expander(f"Account {account_id} ({len(resources)} resources)"):
                            # Group by service
                            service_counts = {}
                            for resource in resources:
                                service = resource.get("service", "unknown")
                                service_counts[service] = service_counts.get(service, 0) + 1

                            # Display service counts
                            df_services = pd.DataFrame(
                                list(service_counts.items()), columns=["Service", "Count"]
                            ).sort_values("Count", ascending=False)

                            st.dataframe(df_services, use_container_width=True, hide_index=True)
                else:
                    st.info("No tagged resources found")

            except Exception as e:
                st.error(f"Error fetching inventory: {str(e)}")

    with tab5:
        st.header("Trends & Forecast")

        # Service selector
        col1, col2 = st.columns([2, 1])
        with col1:
            service_filter = st.text_input("Filter by service (optional)", "")
        with col2:
            forecast_days = st.number_input("Forecast days", 1, 30, 7)  # noqa: F841

        with st.spinner("Analyzing trends..."):
            try:
                trend_data = st.session_state.cost_analyzer.get_cost_trends(
                    days=30, service=service_filter if service_filter else None
                )

                if trend_data:
                    # Statistics
                    stats = trend_data["statistics"]
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("30-Day Total", format_currency(stats["total"]))
                    with col2:
                        st.metric("Daily Average", format_currency(stats["average"]))
                    with col3:
                        st.metric("Trend", stats["trend"].title())
                    with col4:
                        st.metric("Std Deviation", format_currency(stats["std_dev"]))

                    # Create trend chart with forecast
                    fig = go.Figure()

                    # Actual data
                    fig.add_trace(
                        go.Scatter(
                            x=pd.to_datetime(trend_data["dates"]),
                            y=trend_data["daily_costs"],
                            mode="lines+markers",
                            name="Actual Cost",
                            line=dict(color="blue"),
                        )
                    )

                    # Moving averages
                    fig.add_trace(
                        go.Scatter(
                            x=pd.to_datetime(trend_data["dates"]),
                            y=trend_data["moving_average_7"],
                            mode="lines",
                            name="7-Day MA",
                            line=dict(color="orange", dash="dash"),
                        )
                    )

                    # Forecast
                    if trend_data.get("forecast"):
                        forecast = trend_data["forecast"]
                        fig.add_trace(
                            go.Scatter(
                                x=pd.to_datetime(forecast["dates"]),
                                y=forecast["values"],
                                mode="lines+markers",
                                name="Forecast",
                                line=dict(color="red", dash="dot"),
                            )
                        )

                    fig.update_layout(
                        title="Cost Trend Analysis",
                        xaxis_title="Date",
                        yaxis_title="Cost ($)",
                        height=500,
                        hovermode="x unified",
                    )

                    st.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                st.error(f"Error analyzing trends: {str(e)}")


if __name__ == "__main__":
    main()
