"""
AWS Cost & Usage Monitor - CLI Interface
Command-line tool for quick AWS cost and usage queries
"""

import json
import os
import sys
from typing import Dict, Optional

import click
from dotenv import load_dotenv
from tabulate import tabulate

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.anomaly_detector import AnomalyDetector  # noqa: E402
from core.aws_client import AWSClient  # noqa: E402
from core.cost_analyzer import CostAnalyzer  # noqa: E402
from core.usage_tracker import UsageTracker  # noqa: E402

# Load environment variables
load_dotenv()

# Color formatting


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def format_currency(value: float) -> str:
    """Format value as currency."""
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Format value as percentage."""
    return f"{value:+.1f}%"


def print_colored(text: str, color: Optional[str] = None, bold: bool = False) -> None:
    """Print text with optional color and bold."""
    if color:
        text = f"{color}{text}{Colors.END}"
    if bold:
        text = f"{Colors.BOLD}{text}{Colors.END}"
    click.echo(text)


@click.group()
@click.option("--profile", default="default", help="AWS profile to use")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.pass_context
def cli(ctx: click.Context, profile: str, output_json: bool) -> None:
    """AWS Cost & Usage Monitor CLI.

    Quick access to AWS cost and usage data.
    """
    ctx.ensure_object(dict)

    # Initialize AWS clients
    try:
        aws_client = AWSClient(profile_name=profile)
        ctx.obj["aws_client"] = aws_client
        ctx.obj["cost_analyzer"] = CostAnalyzer(aws_client)
        ctx.obj["usage_tracker"] = UsageTracker(aws_client)
        ctx.obj["anomaly_detector"] = AnomalyDetector(aws_client)
        ctx.obj["output_json"] = output_json
    except Exception as e:
        click.echo(f"Error initializing AWS clients: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--hours", default=24, help="Number of hours to look back")
@click.option("--by-account", is_flag=True, help="Group by account")
@click.option("--by-service", is_flag=True, help="Group by service")
@click.option("--top", default=10, help="Number of top items to show")
@click.pass_context
def costs(ctx: click.Context, hours: int, by_account: bool, by_service: bool, top: int) -> None:
    """Show AWS costs for the specified time period."""
    cost_analyzer = ctx.obj["cost_analyzer"]
    output_json = ctx.obj["output_json"]

    try:
        # Determine grouping
        group_by = []
        if by_account or (not by_account and not by_service):
            group_by.append("LINKED_ACCOUNT")
        if by_service or (not by_account and not by_service):
            group_by.append("SERVICE")

        # Get cost breakdown
        print_colored(f"Fetching cost data for the last {hours} hours...", Colors.BLUE)
        breakdown = cost_analyzer.get_cost_breakdown(hours=hours, group_by=group_by)

        if output_json:
            click.echo(json.dumps(breakdown, indent=2, default=str))
            return

        # Display summary
        print_colored("\n=== Cost Summary ===", Colors.BOLD, bold=True)
        print_colored(f"Time Period: {breakdown['start_date']} to " f"{breakdown['end_date']}")
        print_colored(
            f"Total Cost: {format_currency(breakdown['total_cost'])}", Colors.GREEN, bold=True
        )

        daily_rate = breakdown["total_cost"] * (24 / hours)
        print_colored(f"Daily Rate: {format_currency(daily_rate)}")
        print_colored(f"Monthly Estimate: {format_currency(daily_rate * 30)}")

        # Display top cost drivers
        if breakdown["breakdown"]:
            print_colored(
                f"\n=== Top {min(top, len(breakdown['breakdown']))} " f"Cost Drivers ===",
                Colors.BOLD,
                bold=True,
            )

            # Prepare table data
            table_data = []
            for item in breakdown["breakdown"][:top]:
                row = []

                if "service" in item:
                    row.append(item["service"])
                if "account_id" in item:
                    row.append(item.get("account_name", item["account_id"])[:30])

                row.extend([format_currency(item["cost"]), f"{item['percentage']:.1f}%"])

                table_data.append(row)

            # Determine headers
            headers = []
            if by_service or (not by_account and not by_service):
                headers.append("Service")
            if by_account or (not by_account and not by_service):
                headers.append("Account")
            headers.extend(["Cost", "% of Total"])

            click.echo(tabulate(table_data, headers=headers, tablefmt="simple"))

    except Exception as e:
        click.echo(f"Error fetching costs: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--service", help="Filter by service (EC2, Lambda, RDS, S3)")
@click.option("--account", help="Filter by account ID")
@click.pass_context
def inventory(ctx: click.Context, service: Optional[str], account: Optional[str]) -> None:
    """Show resource inventory across accounts."""
    aws_client = ctx.obj["aws_client"]
    output_json = ctx.obj["output_json"]

    try:
        print_colored("Fetching resource inventory...", Colors.BLUE)

        # Get inventory
        account_ids = [account] if account else None
        inventory = aws_client.get_resource_inventory(account_ids=account_ids)

        if output_json:
            click.echo(json.dumps(inventory, indent=2, default=str))
            return

        # Display summary
        total_resources = sum(len(resources) for resources in inventory.values())
        print_colored("\n=== Resource Inventory ===", Colors.BOLD, bold=True)
        print_colored(f"Total Resources: {total_resources}")
        print_colored(f"Accounts: {len(inventory)}")

        # Group by service across all accounts
        service_totals = {}
        for account_id, resources in inventory.items():
            for resource in resources:
                svc = resource.get("service", "unknown")
                if not service or svc == service:
                    service_totals[svc] = service_totals.get(svc, 0) + 1

        if service_totals:
            print_colored("\n=== Resources by Service ===", Colors.BOLD, bold=True)

            # Sort by count
            sorted_services = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)

            table_data = [[svc, count] for svc, count in sorted_services[:20]]
            click.echo(tabulate(table_data, headers=["Service", "Count"], tablefmt="simple"))

    except Exception as e:
        click.echo(f"Error fetching inventory: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--service", required=True, help="AWS service (EC2, Lambda, RDS, S3)")
@click.option("--hours", default=24, help="Number of hours to look back")
@click.pass_context
def usage(ctx: click.Context, service: str, hours: int) -> None:
    """Show usage metrics for a specific service."""
    usage_tracker = ctx.obj["usage_tracker"]
    output_json = ctx.obj["output_json"]

    try:
        print_colored(f"Fetching {service} usage metrics...", Colors.BLUE)

        # Get usage summary
        usage_data = usage_tracker.get_current_usage_summary(services=[service])

        if output_json:
            click.echo(json.dumps(usage_data, indent=2, default=str))
            return

        # Display service-specific metrics
        service_data = usage_data.get("usage_by_service", {}).get(service, {})

        if not service_data:
            print_colored(f"No usage data available for {service}", Colors.YELLOW)
            return

        print_colored(f"\n=== {service} Usage Metrics ===", Colors.BOLD, bold=True)

        if service == "EC2":
            # EC2 metrics
            total_instances = sum(
                acc.get("total_instances", 0)
                for acc in service_data.values()
                if isinstance(acc, dict)
            )
            running_instances = sum(
                acc.get("running_instances", 0)
                for acc in service_data.values()
                if isinstance(acc, dict)
            )

            print_colored(f"Total Instances: {total_instances}")
            print_colored(f"Running Instances: {running_instances}", Colors.GREEN)
            print_colored(
                f"Stopped Instances: {total_instances - running_instances}", Colors.YELLOW
            )

            # Instance types
            instance_types: Dict[str, int] = {}
            for account_data in service_data.values():
                if isinstance(account_data, dict) and "instance_types" in account_data:
                    for itype, count in account_data["instance_types"].items():
                        instance_types[itype] = instance_types.get(itype, 0) + count

            if instance_types:
                print_colored("\nInstance Types:", Colors.BOLD)
                sorted_types = sorted(
                    instance_types.items(), key=lambda x: x[1], reverse=True
                )[:10]
                for itype, count in sorted_types:
                    print_colored(f"  {itype}: {count}")

        elif service == "Lambda":
            # Lambda metrics
            total_functions = sum(
                acc.get("function_count", 0)
                for acc in service_data.values()
                if isinstance(acc, dict)
            )
            total_invocations = sum(
                acc.get("invocations_24h", 0)
                for acc in service_data.values()
                if isinstance(acc, dict)
            )
            total_errors = sum(
                acc.get("errors_24h", 0) for acc in service_data.values() if isinstance(acc, dict)
            )

            print_colored(f"Total Functions: {total_functions}")
            print_colored(f"Invocations (24h): {total_invocations:,}", Colors.GREEN)
            print_colored(
                f"Errors (24h): {total_errors:,}", Colors.RED if total_errors > 0 else Colors.GREEN
            )

            if total_invocations > 0:
                error_rate = (total_errors / total_invocations) * 100
                print_colored(
                    f"Error Rate: {error_rate:.2f}%", Colors.RED if error_rate > 1 else Colors.GREEN
                )

        elif service == "S3":
            # S3 metrics
            total_size = sum(
                acc.get("total_size_gb", 0)
                for acc in service_data.values()
                if isinstance(acc, dict)
            )
            total_objects = sum(
                acc.get("total_objects", 0)
                for acc in service_data.values()
                if isinstance(acc, dict)
            )

            print_colored(f"Total Storage: {total_size:,.1f} GB", Colors.GREEN)
            print_colored(f"Total Objects: {total_objects:,}")

            if total_objects > 0:
                avg_size = total_size * 1024 / total_objects
                print_colored(f"Average Object Size: {avg_size:.1f} MB")

        # Show per-account breakdown
        print_colored("\n=== By Account ===", Colors.BOLD, bold=True)
        for account_id, account_data in service_data.items():
            if isinstance(account_data, dict) and "error" not in account_data:
                click.echo(f"\nAccount {account_id}:")
                for key, value in account_data.items():
                    if key not in ["functions", "metrics"]:
                        # Skip detailed lists
                        click.echo(f"  {key}: {value}")

    except Exception as e:
        click.echo(f"Error fetching usage data: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--days", default=7, help="Number of days to analyze")
@click.option(
    "--sensitivity",
    type=click.Choice(["low", "medium", "high"]),
    default="medium",
    help="Detection sensitivity",
)
@click.pass_context
def anomalies(ctx: click.Context, days: int, sensitivity: str) -> None:
    """Detect cost and usage anomalies."""
    anomaly_detector = ctx.obj["anomaly_detector"]
    output_json = ctx.obj["output_json"]

    try:
        print_colored(f"Detecting anomalies (sensitivity: {sensitivity})...", Colors.BLUE)

        # Detect anomalies
        all_anomalies = anomaly_detector.detect_all_anomalies(
            lookback_hours=days * 24, sensitivity=sensitivity
        )

        if output_json:
            click.echo(json.dumps(all_anomalies, indent=2, default=str))
            return

        # Display summary
        summary = all_anomalies.get("summary", {})
        print_colored("\n=== Anomaly Detection Summary ===", Colors.BOLD, bold=True)
        print_colored(
            f"Total Anomalies: {summary.get('total_anomalies', 0)}",
            Colors.RED if summary.get("total_anomalies", 0) > 0 else Colors.GREEN,
        )
        print_colored(f"Severity Score: {summary.get('severity_score', 0)}")

        # Display recommended actions
        if summary.get("recommended_actions"):
            print_colored("\n=== Recommended Actions ===", Colors.BOLD, bold=True)
            for action in summary["recommended_actions"]:
                print_colored(f"• {action}", Colors.YELLOW)

        # Display anomalies by type
        for anomaly_type, anomalies in all_anomalies.items():
            if anomaly_type == "summary" or not anomalies:
                continue

            print_colored(
                f"\n=== {anomaly_type.replace('_', ' ').title()} ===", Colors.BOLD, bold=True
            )

            for anomaly in anomalies[:5]:  # Show top 5 of each type
                # Format based on type
                if anomaly["type"] == "cost_spike":
                    print_colored(
                        f"⚠️  {anomaly['service']} in "
                        f"{anomaly.get('account_id', 'N/A')}: "
                        f"Cost increased by "
                        f"{format_percentage(anomaly['change_percentage'])} "
                        f"({format_currency(anomaly['baseline_cost'])} → "
                        f"{format_currency(anomaly['cost'])})",
                        Colors.RED,
                    )
                elif anomaly["type"] == "new_service":
                    print_colored(
                        f"🆕 New service detected: {anomaly['service']} in "
                        f"{anomaly.get('account_id', 'N/A')} "
                        f"(Cost: {format_currency(anomaly.get('cost_since_start', 0))})",
                        Colors.YELLOW,
                    )
                elif anomaly["type"] == "usage_anomaly":
                    print_colored(
                        f"📊 {anomaly.get('description', 'Usage anomaly detected')}", Colors.YELLOW
                    )
                else:
                    print_colored(f"• {anomaly.get('description', str(anomaly))}", Colors.YELLOW)

        if summary.get("total_anomalies", 0) == 0:
            print_colored(
                "\n✅ No anomalies detected! Your AWS usage appears normal.", Colors.GREEN
            )

    except Exception as e:
        click.echo(f"Error detecting anomalies: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--days", default=30, help="Number of days to analyze")
@click.option("--service", help="Filter by specific service")
@click.pass_context
def trends(ctx: click.Context, days: int, service: Optional[str]) -> None:
    """Show cost trends over time."""
    cost_analyzer = ctx.obj["cost_analyzer"]
    output_json = ctx.obj["output_json"]

    try:
        print_colored(f"Analyzing cost trends for the last {days} days...", Colors.BLUE)

        # Get trend data
        trend_data = cost_analyzer.get_cost_trends(days=days, service=service)

        if output_json:
            click.echo(json.dumps(trend_data, indent=2, default=str))
            return

        # Display statistics
        stats = trend_data["statistics"]
        print_colored("\n=== Cost Trend Analysis ===", Colors.BOLD, bold=True)
        if service:
            print_colored(f"Service: {service}")
        print_colored(f"Period: Last {days} days")
        print_colored(f"Total Cost: {format_currency(stats['total'])}", Colors.GREEN)
        print_colored(f"Daily Average: {format_currency(stats['average'])}")
        print_colored(f"Minimum: {format_currency(stats['min'])}")
        print_colored(f"Maximum: {format_currency(stats['max'])}")
        print_colored(
            f"Trend: {stats['trend'].upper()}",
            Colors.RED if stats["trend"] == "increasing" else Colors.GREEN,
        )

        # Show simple daily cost chart
        print_colored("\n=== Daily Costs ===", Colors.BOLD, bold=True)

        # Get last 10 days for display
        recent_days = min(10, len(trend_data["dates"]))
        for i in range(-recent_days, 0):
            date = trend_data["dates"][i][:10]
            cost = trend_data["daily_costs"][i]

            # Simple bar chart
            bar_length = int(cost / stats["max"] * 40) if stats["max"] > 0 else 0
            bar = "█" * bar_length

            print_colored(f"{date}: {bar} {format_currency(cost)}")

        # Show forecast if available
        if trend_data.get("forecast"):
            print_colored("\n=== 7-Day Forecast ===", Colors.BOLD, bold=True)
            forecast = trend_data["forecast"]

            for date, value in zip(forecast["dates"][:7], forecast["values"][:7]):
                print_colored(f"{date}: {format_currency(value)}", Colors.BLUE)

    except Exception as e:
        click.echo(f"Error analyzing trends: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def accounts(ctx: click.Context) -> None:
    """List all AWS accounts in the organization."""
    aws_client = ctx.obj["aws_client"]
    output_json = ctx.obj["output_json"]

    try:
        print_colored("Fetching organization accounts...", Colors.BLUE)

        # Get accounts
        accounts = aws_client.get_organization_accounts()

        if output_json:
            click.echo(json.dumps(accounts, indent=2, default=str))
            return

        print_colored("\n=== AWS Organization Accounts ===", Colors.BOLD, bold=True)
        print_colored(f"Total Accounts: {len(accounts)}")

        # Display account table
        table_data = []
        for acc in accounts:
            table_data.append(
                [acc["Id"], acc["Name"][:40], acc.get("Email", "N/A")[:30], acc["Status"]]
            )

        click.echo(
            "\n"
            + tabulate(
                table_data, headers=["Account ID", "Name", "Email", "Status"], tablefmt="simple"
            )
        )

    except Exception as e:
        click.echo(f"Error fetching accounts: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli(obj={})
