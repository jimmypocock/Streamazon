# Streamazon - AWS Cost & Usage Monitor

An open-source tool for real-time monitoring of AWS costs and resource usage across multiple accounts in an AWS Organization. Features both a web dashboard (Streamlit) and CLI interface.

## Features

- **Real-time Monitoring**: Get the latest cost and usage data AWS provides (typically 1-4 hours delayed for costs, near real-time for usage metrics)
- **Multi-Account Support**: View costs and resources across all accounts in your AWS Organization
- **Cost Breakdown**: Analyze costs by service and account with interactive visualizations
- **Usage Metrics**: Track EC2 hours, Lambda invocations, S3 storage, and more
- **Anomaly Detection**: Identify unusual spending patterns or resource usage
- **Resource Inventory**: See what's running where across all accounts
- **Time Range Flexibility**: View last 24 hours, 7 days, 30 days, or custom ranges
- **Cost-Effective Deployment**: Run on-demand on ECS Fargate to minimize costs

## Architecture

```
├── aws_monitor/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── aws_client.py      # AWS API integration
│   │   ├── cost_analyzer.py   # Cost analysis logic
│   │   ├── usage_tracker.py   # Usage metrics collection
│   │   └── anomaly_detector.py # Anomaly detection
│   ├── web/
│   │   └── streamlit_app.py   # Web dashboard
│   └── cli/
│       └── cli.py             # CLI interface
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── iam_policies/
│   ├── monitor_role_policy.json
│   └── cross_account_role.json
└── README.md
```

## Prerequisites

- Python 3.9+
- AWS CLI configured with appropriate credentials
- AWS Organization with management account access
- Docker (for containerized deployment)

## Installation

### Local Development

1. Clone the repository:

```bash
git clone https://github.com/yourusername/aws-cost-usage-monitor.git
cd aws-cost-usage-monitor
```

2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## AWS IAM Setup

### Management Account Permissions

1. Create an IAM role in your management account with the policy from `iam_policies/monitor_role_policy.json`

2. For cross-account access, create a role in each member account using `iam_policies/cross_account_role.json`

### Required Permissions:

- Cost Explorer read access
- CloudWatch read access
- Organizations read access
- Resource Groups Tagging read access
- EC2, Lambda, S3, RDS describe permissions

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_PROFILE=default  # For local development

# Optional: Custom settings
COST_ANOMALY_THRESHOLD=20  # Percentage threshold for anomaly detection
DATA_REFRESH_INTERVAL=300   # Seconds between data refreshes
```

### AWS Authentication

#### Local Development

Uses AWS CLI profiles. Ensure your AWS CLI is configured:

```bash
aws configure --profile your-profile-name
```

#### Production (ECS/Fargate)

Uses IAM Task Role. No additional configuration needed when properly deployed.

#### Future Enhancement: AWS SSO

AWS SSO integration is planned for a future release. This will allow:

- Browser-based authentication
- No long-term credentials
- Seamless multi-account access

To prepare for SSO:

1. Enable AWS SSO in your organization
2. Configure permission sets with necessary read permissions
3. Note your SSO start URL and region for future configuration

## Usage

### Web Dashboard

1. **Local Development**:

```bash
streamlit run aws_monitor/web/streamlit_app.py
```

2. **Production (Docker)**:

```bash
docker-compose up -d
```

Access at http://localhost:8501

### CLI Tool

Basic usage:

```bash
# Show costs for last 24 hours
python -m aws_monitor.cli.cli costs --hours 24

# Show resource inventory
python -m aws_monitor.cli.cli inventory

# Show usage metrics
python -m aws_monitor.cli.cli usage --service ec2 --hours 24

# Detect anomalies
python -m aws_monitor.cli.cli anomalies --days 7
```

## Deployment on AWS ECS Fargate

### Cost-Effective On-Demand Deployment

1. **Build and push Docker image**:

```bash
# Build image
docker build -t aws-cost-monitor .

# Tag for ECR
docker tag aws-cost-monitor:latest YOUR_ECR_REPO_URL:latest

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ECR_REPO_URL
docker push YOUR_ECR_REPO_URL:latest
```

2. **Deploy to ECS Fargate**:

```bash
# Use provided CloudFormation template
aws cloudformation create-stack \
  --stack-name aws-cost-monitor \
  --template-body file://ecs-fargate-template.yaml \
  --parameters ParameterKey=ImageUri,ParameterValue=YOUR_ECR_REPO_URL:latest \
  --capabilities CAPABILITY_IAM
```

3. **Start/Stop for Cost Savings**:

Start in the morning:

```bash
aws ecs update-service --cluster aws-cost-monitor --service aws-cost-monitor-service --desired-count 1
```

Stop in the evening:

```bash
aws ecs update-service --cluster aws-cost-monitor --service aws-cost-monitor-service --desired-count 0
```

Alternatively, use the provided start/stop scripts or set up Lambda functions for automated scheduling.

## Understanding the Data

### Cost Data Latency

- **Cost Explorer**: 1-24 hours delayed (most granular: daily by default)
- **Usage Metrics**: Near real-time via CloudWatch (5-minute granularity)
- **Strategy**: We combine both to provide the most current view possible

**Note**: Hourly cost granularity requires opt-in from the AWS management (payer) account. By default, the tool uses daily granularity which is available to all accounts.

### Time Ranges

- **Last 24 hours**: Hourly granularity where available
- **Last 7 days**: Daily granularity
- **Last 30 days**: Daily granularity
- **Custom ranges**: Up to 90 days (AWS Cost Explorer limitation)

## Key Features Explained

### 1. Cost Breakdown by Service by Account

View costs hierarchically: Organization → Account → Service → Resource Type

### 2. Anomaly Detection

- Compares current spending patterns to historical baselines
- Alerts on services with >20% deviation (configurable)
- Identifies new services or resources

### 3. Resource Inventory

- Lists all active resources across accounts
- Shows resource tags, creation time, and estimated costs
- Helps identify forgotten or unused resources

## Development

### Adding New Features

1. **New AWS Service Support**: Add to `aws_monitor/core/aws_client.py`
2. **New Visualizations**: Modify `aws_monitor/web/streamlit_app.py`
3. **New CLI Commands**: Extend `aws_monitor/cli/cli.py`

### Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=aws_monitor tests/
```

## Troubleshooting

### Common Issues

1. **"Access Denied" errors**

   - Verify IAM role has necessary permissions
   - Check trust relationships for cross-account access

2. **No cost data showing**

   - Cost Explorer must be enabled in management account
   - Wait 24 hours after enabling for data to populate

3. **Missing usage metrics**
   - Ensure CloudWatch is enabled for services
   - Some services require additional configuration

## Roadmap

- [ ] AWS SSO integration
- [ ] Cost allocation tag support
- [ ] Savings recommendations
- [ ] Reserved Instance/Savings Plan tracking
- [ ] Slack/Email notifications for anomalies
- [ ] Historical data export
- [ ] Multi-region support
- [ ] Cost forecasting with ML

## Contributing

Contributions are welcome! Please read CONTRIBUTING.md for guidelines.

## License

MIT License - see LICENSE file for details

## Security Considerations

- Never commit AWS credentials to version control
- Use IAM roles with least privilege principle
- Enable MFA on AWS accounts
- Regularly rotate access keys if used
- Consider VPC endpoints for production deployments
- Enable CloudTrail for audit logging

## Support

- Create an issue for bugs or feature requests
- Check existing issues before creating new ones
- For security issues, please email directly (don't create public issues)

## Acknowledgments

Built with:

- Streamlit for the web interface
- Boto3 for AWS integration
- Plotly for visualizations
- Click for CLI interface
