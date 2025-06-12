#!/bin/bash

# AWS Cost Monitor - Start/Stop Script
# Usage: ./start_stop_service.sh [start|stop|status]

set -e

# Configuration
CLUSTER_NAME="${ECS_CLUSTER_NAME:-aws-cost-monitor}"
SERVICE_NAME="${ECS_SERVICE_NAME:-aws-cost-monitor-service}"
REGION="${AWS_REGION:-us-east-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check service status
check_status() {
    local status=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$REGION" \
        --query 'services[0].{desired:desiredCount,running:runningCount,status:status}' \
        --output json)

    local desired=$(echo "$status" | jq -r '.desired')
    local running=$(echo "$status" | jq -r '.running')
    local service_status=$(echo "$status" | jq -r '.status')

    print_status "$GREEN" "Service Status:"
    echo "  Cluster: $CLUSTER_NAME"
    echo "  Service: $SERVICE_NAME"
    echo "  Status: $service_status"
    echo "  Desired Count: $desired"
    echo "  Running Count: $running"

    if [ "$desired" -eq 0 ]; then
        print_status "$YELLOW" "  State: STOPPED"
    elif [ "$running" -eq "$desired" ]; then
        print_status "$GREEN" "  State: RUNNING"
    else
        print_status "$YELLOW" "  State: STARTING/STOPPING"
    fi
}

# Function to start the service
start_service() {
    print_status "$GREEN" "Starting AWS Cost Monitor service..."

    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --desired-count 1 \
        --region "$REGION" \
        --no-cli-pager > /dev/null

    print_status "$GREEN" "Service start command sent successfully!"
    echo "It may take a few minutes for the service to be fully operational."
    echo ""

    # Wait a moment and check status
    sleep 5
    check_status
}

# Function to stop the service
stop_service() {
    print_status "$YELLOW" "Stopping AWS Cost Monitor service..."

    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --desired-count 0 \
        --region "$REGION" \
        --no-cli-pager > /dev/null

    print_status "$GREEN" "Service stop command sent successfully!"
    echo "The service will stop shortly to save costs."
    echo ""

    # Wait a moment and check status
    sleep 5
    check_status
}

# Main script logic
case "$1" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    status)
        check_status
        ;;
    *)
        echo "Usage: $0 {start|stop|status}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the AWS Cost Monitor service"
        echo "  stop    - Stop the service to save costs"
        echo "  status  - Check the current service status"
        echo ""
        echo "Environment Variables:"
        echo "  ECS_CLUSTER_NAME - ECS cluster name (default: aws-cost-monitor)"
        echo "  ECS_SERVICE_NAME - ECS service name (default: aws-cost-monitor-service)"
        echo "  AWS_REGION       - AWS region (default: us-east-1)"
        exit 1
        ;;
esac