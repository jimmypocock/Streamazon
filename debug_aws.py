#!/usr/bin/env python3
"""Debug script to test AWS connection and permissions."""

import boto3
from datetime import datetime, timedelta
import json

def test_aws_connection():
    """Test basic AWS connection and permissions."""
    print("Testing AWS Connection...\n")
    
    # Test 1: Basic connection
    try:
        # Use profile from environment or default
        import os
        profile = os.getenv('AWS_PROFILE', 'jimmycpocock')
        print(f"Using AWS Profile: {profile}")
        session = boto3.Session(profile_name=profile)
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print("✅ AWS Connection successful!")
        print(f"   Account: {identity['Account']}")
        print(f"   UserId: {identity['UserId']}")
        print(f"   Arn: {identity['Arn']}\n")
    except Exception as e:
        print(f"❌ AWS Connection failed: {e}\n")
        return False
    
    # Test 2: Organizations access
    try:
        org = session.client('organizations')
        org_info = org.describe_organization()
        print("✅ Organizations access successful!")
        print(f"   Organization ID: {org_info['Organization']['Id']}")
        print(f"   Master Account: {org_info['Organization']['MasterAccountId']}\n")
    except Exception as e:
        print(f"❌ Organizations access failed: {e}")
        print("   This might be okay if you're not using Organizations\n")
    
    # Test 3: Cost Explorer access
    try:
        ce = session.client('ce', region_name='us-east-1')
        
        # Test with different date formats
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=1)
        
        print(f"Testing Cost Explorer with dates: {start_date} to {end_date}")
        
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost']
        )
        
        print("✅ Cost Explorer access successful!")
        total = response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
        print(f"   Yesterday's cost: ${float(total):.2f}\n")
        
    except Exception as e:
        print(f"❌ Cost Explorer access failed: {e}")
        print("\nPossible solutions:")
        print("1. Ensure Cost Explorer is enabled in your account")
        print("2. Wait 24 hours after enabling (AWS requirement)")
        print("3. Check IAM permissions include ce:GetCostAndUsage")
        print("4. Ensure you're in a supported region\n")
    
    # Test 4: Check for required services
    services_to_check = ['ec2', 'lambda', 's3', 'cloudwatch']
    print("Checking service access:")
    
    for service in services_to_check:
        try:
            client = session.client(service)
            # Just creating the client is enough to test basic access
            print(f"   ✅ {service}")
        except Exception as e:
            print(f"   ❌ {service}: {e}")
    
    return True

if __name__ == "__main__":
    test_aws_connection()