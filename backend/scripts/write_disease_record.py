#!/usr/bin/env python3
"""
Write disease risk records to DynamoDB for testing.

This script writes a disease record with a specified risk score to DynamoDB
to test the metrics evaluator and alert system.

Usage:
    python scripts/write_disease_record.py <device_id> [--score SCORE] [--alarming]

Examples:
    # Write an alarming record (score 0.85, above default threshold 0.8)
    python scripts/write_disease_record.py yang_si_jun_from_bytedance --alarming
    
    # Write a non-alarming record (score 0.5)
    python scripts/write_disease_record.py yang_si_jun_from_bytedance --score 0.5
    
    # Write a specific score
    python scripts/write_disease_record.py yang_si_jun_from_bytedance --score 0.92

Environment variables:
    AWS_REGION - AWS region (default: ap-southeast-1)
    TELEMETRY_TABLE - DynamoDB table name (default: dev-telemetry)
    AWS_PROFILE - AWS profile to use (optional)
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3

# Add parent directory to path for imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def write_disease_record(device_id: str, disease_score: float, table_name: str, region: str = "ap-southeast-1") -> None:
    """Write a disease risk record to DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    
    # Generate timestamp in the format: DISEASE#YYYYMMDDTHHMMSSZ-suffix
    now = datetime.now(timezone.utc)
    timestamp_base = now.strftime("%Y%m%dT%H%M%SZ")
    unique_suffix = uuid.uuid4().hex[:6]
    dynamo_timestamp = f"DISEASE#{timestamp_base}-{unique_suffix}"
    
    # Create the disease record item
    # Note: DynamoDB requires Decimal types for all numeric values
    disease_score_decimal = Decimal(str(disease_score))
    item = {
        "deviceId": device_id,
        "timestamp": dynamo_timestamp,
        "readingType": "disease",
        "metrics": {
            "diseaseRisk": disease_score_decimal
        },
        "raw": {
            "deviceId": device_id,
            "diseaseRisk": disease_score_decimal,  # Must be Decimal, not float
            "timestamp": int(now.timestamp()),
            "source": "test_script"
        }
    }
    
    # Write to DynamoDB
    table.put_item(Item=item)
    
    print(f"✅ Successfully wrote disease record:")
    print(f"   Device ID: {device_id}")
    print(f"   Disease Risk Score: {disease_score}")
    print(f"   Timestamp: {dynamo_timestamp}")
    print(f"   Record will be evaluated by metrics evaluator on next run (every 5 minutes)")


def main():
    parser = argparse.ArgumentParser(
        description="Write disease risk records to DynamoDB for testing"
    )
    parser.add_argument(
        "device_id",
        type=str,
        help="Device ID to write the disease record for"
    )
    parser.add_argument(
        "--score",
        type=float,
        help="Disease risk score (0.0 to 1.0). If not provided, uses --alarming flag to determine score."
    )
    parser.add_argument(
        "--alarming",
        action="store_true",
        help="Write an alarming record (score 0.85, above default threshold 0.8). Ignored if --score is provided."
    )
    parser.add_argument(
        "--region",
        type=str,
        default=os.environ.get("AWS_REGION", "ap-southeast-1"),
        help="AWS region (default: ap-southeast-1 or AWS_REGION env var)"
    )
    parser.add_argument(
        "--table",
        type=str,
        default=os.environ.get("TELEMETRY_TABLE", "dev-telemetry"),
        help="DynamoDB table name (default: dev-telemetry or TELEMETRY_TABLE env var)"
    )
    
    args = parser.parse_args()
    
    # Determine the disease score
    if args.score is not None:
        disease_score = args.score
        if not 0.0 <= disease_score <= 1.0:
            print("❌ Error: Disease score must be between 0.0 and 1.0", file=sys.stderr)
            sys.exit(1)
    elif args.alarming:
        disease_score = 0.85  # Above default threshold of 0.8
    else:
        disease_score = 0.5  # Non-alarming default
    
    # Get table name (defaults to dev-telemetry)
    table_name = args.table
    
    try:
        write_disease_record(args.device_id, disease_score, table_name, args.region)
    except Exception as e:
        print(f"❌ Error writing disease record: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

