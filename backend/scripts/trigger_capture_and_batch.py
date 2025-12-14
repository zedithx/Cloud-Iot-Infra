#!/usr/bin/env python3
"""
Trigger capture scheduler lambda, wait, then process batch inference for diseased/non-diseased folders.

This script:
1. Invokes the capture scheduler lambda to trigger photo captures
2. Waits for a specified duration (to allow photos to be captured and uploaded)
3. Invokes batch inference lambda for diseased and/or non-diseased folders

Usage:
    # Process both folders
    python scripts/trigger_capture_and_batch.py --diseased --non-diseased
    
    # Process only diseased folder
    python scripts/trigger_capture_and_batch.py --diseased
    
    # Process only non-diseased folder
    python scripts/trigger_capture_and_batch.py --non-diseased
    
    # Custom wait time (default: 10 seconds)
    python scripts/trigger_capture_and_batch.py --diseased --non-diseased --wait 30

Environment variables:
    AWS_REGION - AWS region (default: ap-southeast-1)
    AWS_PROFILE - AWS profile to use (optional)
    CAPTURE_SCHEDULER_LAMBDA - Lambda function name (auto-discovered if unset)
    BATCH_INFERENCE_LAMBDA - Lambda function name (auto-discovered if unset)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import boto3


def discover_capture_scheduler_lambda(region: str) -> Optional[str]:
    """Auto-discover capture scheduler lambda function name."""
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.list_functions()
        
        for func in response.get("Functions", []):
            func_name = func.get("FunctionName", "")
            if "CaptureScheduler" in func_name or "capture" in func_name.lower():
                return func_name
        
        # Try CloudFormation stacks
        cf_client = boto3.client("cloudformation", region_name=region)
        stacks = cf_client.list_stacks(
            StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"]
        )
        
        for stack in stacks.get("StackSummaries", []):
            stack_name = stack["StackName"]
            resources = cf_client.list_stack_resources(StackName=stack_name)
            for resource in resources.get("StackResourceSummaries", []):
                if (resource.get("ResourceType") == "AWS::Lambda::Function" and
                    ("CaptureScheduler" in resource.get("LogicalResourceId", "") or
                     "capture" in resource.get("LogicalResourceId", "").lower())):
                    return resource.get("PhysicalResourceId")
    except Exception as e:
        print(f"⚠️  Could not auto-discover capture scheduler lambda: {e}")
    return None


def discover_batch_inference_lambda(region: str) -> Optional[str]:
    """Auto-discover batch inference lambda function name."""
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.list_functions()
        
        for func in response.get("Functions", []):
            func_name = func.get("FunctionName", "")
            if "BatchInference" in func_name or "batch" in func_name.lower():
                return func_name
        
        # Try CloudFormation stacks
        cf_client = boto3.client("cloudformation", region_name=region)
        stacks = cf_client.list_stacks(
            StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"]
        )
        
        for stack in stacks.get("StackSummaries", []):
            stack_name = stack["StackName"]
            resources = cf_client.list_stack_resources(StackName=stack_name)
            for resource in resources.get("StackResourceSummaries", []):
                if (resource.get("ResourceType") == "AWS::Lambda::Function" and
                    ("BatchInference" in resource.get("LogicalResourceId", "") or
                     "batch" in resource.get("LogicalResourceId", "").lower())):
                    return resource.get("PhysicalResourceId")
    except Exception as e:
        print(f"⚠️  Could not auto-discover batch inference lambda: {e}")
    return None


def invoke_capture_scheduler(lambda_client, function_name: str) -> dict:
    """Invoke the capture scheduler lambda."""
    print(f"\n📸 Invoking capture scheduler: {function_name}")
    
    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",  # Synchronous invocation
            Payload=json.dumps({}),
        )
        
        # Read response
        response_payload = json.loads(response["Payload"].read())
        
        if "FunctionError" in response:
            error_message = response_payload.get("errorMessage", "Unknown error")
            print(f"❌ Error invoking capture scheduler: {error_message}")
            return {"success": False, "error": error_message}
        
        result = json.loads(response_payload.get("body", "{}"))
        print(f"✅ Capture scheduler completed:")
        print(f"   Message: {result.get('message', 'N/A')}")
        print(f"   Devices: {result.get('sent', 0)} device(s)")
        print(f"   Device list: {', '.join(result.get('devices', []))}")
        
        return {"success": True, "result": result}
    except Exception as e:
        print(f"❌ Failed to invoke capture scheduler: {e}")
        return {"success": False, "error": str(e)}


def invoke_batch_inference(lambda_client, function_name: str, prefix: str, folder_type: str) -> dict:
    """Invoke the batch inference lambda for a specific folder."""
    print(f"\n🤖 Invoking batch inference for {folder_type} folder: {prefix}")
    
    try:
        payload = {"prefix": prefix}
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",  # Synchronous invocation
            Payload=json.dumps(payload),
        )
        
        # Read response
        response_payload = json.loads(response["Payload"].read())
        
        if "FunctionError" in response:
            error_message = response_payload.get("errorMessage", "Unknown error")
            print(f"❌ Error invoking batch inference: {error_message}")
            return {"success": False, "error": error_message}
        
        result = response_payload
        processed = result.get("processed", 0)
        output = result.get("output", "N/A")
        
        print(f"✅ Batch inference completed for {folder_type}:")
        print(f"   Processed: {processed} image(s)")
        print(f"   Output: {output}")
        
        return {"success": True, "result": result}
    except Exception as e:
        print(f"❌ Failed to invoke batch inference: {e}")
        return {"success": False, "error": str(e)}


def main():
    # Default folder paths (edit these as needed)
    DEFAULT_DISEASED_FOLDER = "photos/20251203T16/"
    DEFAULT_NON_DISEASED_FOLDER = "photos/20251203T19/"
    
    parser = argparse.ArgumentParser(
        description="Trigger capture scheduler and batch inference for diseased/non-diseased folders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process both folders
  python scripts/trigger_capture_and_batch.py --diseased --non-diseased
  
  # Process only diseased folder
  python scripts/trigger_capture_and_batch.py --diseased
  
  # Custom wait time (default: 10 seconds)
  python scripts/trigger_capture_and_batch.py --diseased --non-diseased --wait 30
        """,
    )
    
    parser.add_argument(
        "--diseased",
        action="store_true",
        help="Process diseased folder",
    )
    parser.add_argument(
        "--non-diseased",
        action="store_true",
        help="Process non-diseased/healthy folder",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip triggering capture scheduler (only run batch inference)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=10,
        help="Wait time in seconds between capture and batch processing (default: 10)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=os.environ.get("AWS_REGION", "ap-southeast-1"),
        help="AWS region (default: ap-southeast-1 or AWS_REGION env var)",
    )
    parser.add_argument(
        "--capture-lambda",
        type=str,
        default=os.environ.get("CAPTURE_SCHEDULER_LAMBDA"),
        help="Capture scheduler lambda function name (auto-discovered if unset)",
    )
    parser.add_argument(
        "--batch-lambda",
        type=str,
        default=os.environ.get("BATCH_INFERENCE_LAMBDA"),
        help="Batch inference lambda function name (auto-discovered if unset)",
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.diseased and not args.non_diseased:
        print("❌ Error: Must specify at least one of --diseased or --non-diseased")
        sys.exit(1)
    
    if not args.skip_capture and not args.capture_lambda:
        print("🔍 Auto-discovering capture scheduler lambda...")
        args.capture_lambda = discover_capture_scheduler_lambda(args.region)
        if not args.capture_lambda:
            print("❌ Error: Could not find capture scheduler lambda. Set CAPTURE_SCHEDULER_LAMBDA env var or --capture-lambda")
            sys.exit(1)
        print(f"✅ Found: {args.capture_lambda}")
    
    if not args.batch_lambda:
        print("🔍 Auto-discovering batch inference lambda...")
        args.batch_lambda = discover_batch_inference_lambda(args.region)
        if not args.batch_lambda:
            print("❌ Error: Could not find batch inference lambda. Set BATCH_INFERENCE_LAMBDA env var or --batch-lambda")
            sys.exit(1)
        print(f"✅ Found: {args.batch_lambda}")
    
    # Create Lambda client
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    lambda_client = session.client("lambda", region_name=args.region)
    
    print("=" * 70)
    print("🚀 Starting capture and batch processing pipeline")
    print("=" * 70)
    
    # Step 1: Trigger capture scheduler
    if not args.skip_capture:
        capture_result = invoke_capture_scheduler(lambda_client, args.capture_lambda)
        if not capture_result.get("success"):
            print(f"\n❌ Capture scheduler failed. Exiting.")
            sys.exit(1)
        
        # Step 2: Wait for photos to be captured and uploaded
        print(f"\n⏳ Waiting {args.wait} seconds for photos to be captured and uploaded...")
        for i in range(args.wait, 0, -5):
            if i <= 5:
                print(f"   {i} second(s) remaining...")
                time.sleep(i)
                break
            else:
                print(f"   {i} seconds remaining...")
                time.sleep(5)
        print("✅ Wait complete")
    else:
        print("\n⏭️  Skipping capture scheduler (--skip-capture)")
    
    # Step 3: Process diseased folder
    if args.diseased:
        diseased_result = invoke_batch_inference(
            lambda_client,
            args.batch_lambda,
            DEFAULT_DISEASED_FOLDER,
            "diseased"
        )
        if not diseased_result.get("success"):
            print(f"\n⚠️  Warning: Batch inference for diseased folder failed")
    
    # Step 4: Process non-diseased folder
    if args.non_diseased:
        non_diseased_result = invoke_batch_inference(
            lambda_client,
            args.batch_lambda,
            DEFAULT_NON_DISEASED_FOLDER,
            "non-diseased"
        )
        if not non_diseased_result.get("success"):
            print(f"\n⚠️  Warning: Batch inference for non-diseased folder failed")
    
    print("\n" + "=" * 70)
    print("✅ Pipeline completed successfully!")
    print("=" * 70)
    print("\n📊 Check your S3 batch results bucket and DynamoDB for processed results.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

