import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import boto3

sagemaker = boto3.client("sagemaker")

MODEL_NAME = os.environ["MODEL_NAME"]
SAGEMAKER_ROLE_ARN = os.environ["SAGEMAKER_ROLE_ARN"]
RAW_BUCKET = os.environ["RAW_BUCKET"]
BATCH_RESULTS_BUCKET = os.environ["BATCH_RESULTS_BUCKET"]
STAGE = os.environ["STAGE"]


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    # Calculate previous hour timestamp (scheduler runs at :00, batch runs at :05)
    # This ensures we process photos from the hour that just completed
    previous_hour = datetime.now(timezone.utc) - timedelta(hours=1)
    photo_timestamp = previous_hour.strftime("%Y%m%dT%H")
    
    # Job creation timestamp for output organization
    job_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Process photos from the specific hourly folder
    input_prefix = f"photos/{photo_timestamp}/"
    output_prefix = f"{STAGE}/{job_timestamp}/"

    transform_job_name = f"{STAGE}-leaf-batch-{int(time.time())}"

    response = sagemaker.create_transform_job(
        TransformJobName=transform_job_name,
        ModelName=MODEL_NAME,
        MaxConcurrentTransforms=1,
        TransformInput={
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": f"s3://{RAW_BUCKET}/{input_prefix}",
                }
            },
            "ContentType": "application/x-image",
        },
        TransformOutput={
            "S3OutputPath": f"s3://{BATCH_RESULTS_BUCKET}/{output_prefix}",
            "AssembleWith": "Line",
            "Accept": "application/json",
        },
        TransformResources={"InstanceType": "ml.m5.large", "InstanceCount": 1},
        BatchStrategy="MultiRecord",
        Tags=[
            {"Key": "Stage", "Value": STAGE},
            {"Key": "Component", "Value": "BatchTransform"},
        ],
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "transformJobName": transform_job_name,
                "response": _serialize(response),
            }
        ),
    }


def _serialize(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _serialize(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_serialize(v) for v in data]
    if isinstance(data, datetime):
        return data.isoformat()
    return data

