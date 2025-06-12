#!/bin/bash

# AWS Cost Monitor - Setup Script
# This script helps set up the AWS Cost Monitor for first-time users

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Banner
print_status "$BLUE" "
╔═══════════════════════════════════════╗
║     AWS Cost & Usage Monitor Setup    ║
╚═══════════════════════════════════════╝
"

# Check prerequisites
print_status "$YELLOW" "Checking prerequisites..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    print_status "$RED" "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
else
    python_version=$(python3 --version | cut -d' ' -f2)
    print_status "$GREEN" "✓ Python $python_version found"
fi

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    print_status "$RED" "❌ AWS CLI is not installed. Please install AWS CLI v2."
    exit 1
else
    aws_version=$(aws --version | cut -d' ' -f1 | cut -d'/' -f2)
    print_status "$GREEN" "✓ AWS CLI $aws_version found"
fi

# Check Docker (optional)
if command -v docker &> /dev/null; then
    docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
    print_status "$GREEN" "✓ Docker $docker_version found (optional)"
else
    print_status "$YELLOW" "⚠ Docker not found (optional for containerized deployment)"
fi

# Create virtual environment
print_status "$YELLOW" "\nSetting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_status "$GREEN" "✓ Virtual environment created"
else
    print_status "$GREEN" "✓ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
print_status "$YELLOW" "\nInstalling Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
print_status "$GREEN" "✓ Dependencies installed"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_status "$YELLOW" "\nCreating .env file from template..."
    cp .env.example .env
    print_status "$GREEN" "✓ .env file created"
    print_status "$YELLOW" "⚠ Please edit .env file with your configuration"
else
    print_status "$GREEN" "✓ .env file already exists"
fi

# Check AWS credentials
print_status "$YELLOW" "\nChecking AWS credentials..."
if aws sts get-caller-identity &> /dev/null; then
    account_id=$(aws sts get-caller-identity --query Account --output text)
    print_status "$GREEN" "✓ AWS credentials configured (Account: $account_id)"
else
    print_status "$RED" "❌ AWS credentials not configured"
    print_status "$YELLOW" "Please run: aws configure"
    exit 1
fi

# Check if this is a management account
print_status "$YELLOW" "\nChecking AWS Organizations access..."
if aws organizations describe-organization &> /dev/null; then
    org_id=$(aws organizations describe-organization --query Organization.Id --output text)
    print_status "$GREEN" "✓ AWS Organizations access confirmed (Org ID: $org_id)"

    # Count accounts
    account_count=$(aws organizations list-accounts --query 'length(Accounts)' --output text)
    print_status "$GREEN" "✓ Found $account_count accounts in organization"
else
    print_status "$YELLOW" "⚠ No AWS Organizations access detected"
    print_status "$YELLOW" "  This tool works best with AWS Organizations management account access"
fi

# Create necessary directories
print_status "$YELLOW" "\nCreating project directories..."
mkdir -p logs
mkdir -p data
print_status "$GREEN" "✓ Directories created"

# Test imports
print_status "$YELLOW" "\nTesting Python imports..."
python3 -c "from aws_monitor.core import AWSClient, CostAnalyzer, UsageTracker, AnomalyDetector" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "$GREEN" "✓ Python modules imported successfully"
else
    print_status "$RED" "❌ Failed to import Python modules"
    exit 1
fi

# Setup complete
print_status "$GREEN" "\n
╔═══════════════════════════════════════╗
║        Setup Complete! 🎉             ║
╚═══════════════════════════════════════╝"

print_status "$BLUE" "
Next steps:
1. Edit .env file with your configuration
2. Run the web dashboard:
   ${GREEN}streamlit run aws_monitor/web/streamlit_app.py${BLUE}

3. Or use the CLI:
   ${GREEN}python -m aws_monitor.cli.cli --help${BLUE}

For Docker deployment:
   ${GREEN}docker-compose up -d${BLUE}

For production deployment on ECS:
   See the README for detailed instructions
"

# Offer to start the web dashboard
echo ""
read -p "Would you like to start the web dashboard now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "$GREEN" "\nStarting AWS Cost Monitor dashboard..."
    print_status "$YELLOW" "Press Ctrl+C to stop the server\n"
    streamlit run aws_monitor/web/streamlit_app.py
fi