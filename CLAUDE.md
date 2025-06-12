# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Development:**
- `make setup` - Set up the development environment
- `make install` - Install dependencies
- `make run-web` - Run the Streamlit web dashboard at http://localhost:8501
- `make run-cli` - Show CLI help

**Testing & Quality:**
- `make test` - Run tests with pytest
- `make test-coverage` - Run tests with coverage report
- `make lint` - Run linting checks (flake8, mypy)
- `make format` - Format code with black and isort

**Docker:**
- `make docker-build` - Build Docker image
- `make docker-run` - Run Docker container via docker-compose
- `make docker-stop` - Stop Docker container
- `make docker-logs` - View Docker logs

**AWS:**
- `make check-aws` - Check AWS credentials and configuration
- `python -m aws_monitor.cli.cli costs --hours 24` - Show costs for last 24 hours
- `python -m aws_monitor.cli.cli inventory` - Show resource inventory
- `python -m aws_monitor.cli.cli usage --service ec2 --hours 24` - Show usage metrics
- `python -m aws_monitor.cli.cli anomalies --days 7` - Detect anomalies

## Architecture

This is an AWS cost and usage monitoring tool with two interfaces:

1. **Web Dashboard** (Streamlit): Interactive visualizations for cost analysis
2. **CLI Tool**: Command-line interface for quick queries

### Core Modules

**aws_monitor/core/**
- `aws_client.py` - AWS API integration using boto3
- `cost_analyzer.py` - Cost analysis logic using Cost Explorer API
- `usage_tracker.py` - Usage metrics collection from CloudWatch
- `anomaly_detector.py` - Anomaly detection for spending patterns

**aws_monitor/web/**
- `streamlit_app.py` - Web dashboard implementation

**aws_monitor/cli/**
- `cli.py` - CLI interface using Click

### Key Design Patterns

1. **AWS Authentication**: Supports both local development (AWS CLI profiles) and production (IAM Task Roles)
2. **Multi-Account Access**: Uses AWS Organizations API and cross-account IAM roles
3. **Data Latency Handling**: Combines Cost Explorer (1-24hr delay) with CloudWatch (near real-time) for best available data
4. **Cost-Effective Deployment**: Designed to run on-demand on ECS Fargate to minimize costs

### Important Considerations

- Cost Explorer must be enabled in the AWS management account
- Requires IAM roles with specific permissions (see iam_policies/ directory)
- Environment variables configured in .env file (AWS_REGION, AWS_PROFILE, etc.)
- Uses Python 3.9+ with type hints where applicable