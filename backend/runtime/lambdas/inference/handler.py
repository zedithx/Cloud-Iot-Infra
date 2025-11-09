import json
import logging
import os
from typing import Any, Dict, List

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
sagemaker_runtime = boto3.client("sagemaker-runtime")


ENDPOINT_NAME = os.environ["SAGEMAKER_ENDPOINT_NAME"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = event.get("Records", [])
    results = []

    for record in records:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        key = s3_info.get("object", {}).get("key")

        if not bucket or not key:
            logger.warning("Invalid record structure: %s", record)
            continue

        logger.info("Processing object s3://%s/%s", bucket, key)
        payload = json.dumps({"s3Bucket": bucket, "s3Key": key}).encode("utf-8")

        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Body=payload,
        )

        body = response["Body"].read().decode("utf-8")
        inference_result = json.loads(body) if body else {"status": "empty"}

        result_key = key.replace("scheduled/", "inference/") + ".json"
        result_payload = {
            "sourceBucket": bucket,
            "sourceKey": key,
            "endpoint": ENDPOINT_NAME,
            "prediction": inference_result,
        }

        s3_client.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=result_key,
            Body=json.dumps(result_payload).encode("utf-8"),
            ContentType="application/json",
        )

        results.append(result_payload)

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": len(results)}),
    }

