import json
import os
import time
from typing import Any, Dict

import boto3

s3_client = boto3.client("s3")


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    bucket_name = os.environ["RAW_BUCKET_NAME"]
    prefix = os.environ.get("CAPTURE_PREFIX", "scheduled-captures")
    timestamp = int(time.time())
    object_key = f"{prefix}/{timestamp}.json"

    payload = {
        "scheduledTime": event.get("time"),
        "bucket": bucket_name,
        "objectKey": object_key,
        "note": "Placeholder artifact. Replace with image capture integration.",
    }

    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
    )

    return {
        "statusCode": 200,
        "body": json.dumps(payload),
    }

