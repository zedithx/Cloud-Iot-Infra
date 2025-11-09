import json
import os
import time
from typing import Any, Dict

import boto3

s3_client = boto3.client("s3")


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    bucket_name = os.environ["RAW_BUCKET_NAME"]
    default_ttl = int(os.environ.get("PRESIGN_TTL_SECONDS", "900"))

    device_id = event.get("deviceId") or "unknown-device"
    extension = event.get("extension", "jpg")
    content_type = event.get("contentType", "image/jpeg")
    timestamp = int(time.time())
    object_key = f"{device_id}/{timestamp}.{extension}"

    presigned_url = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": bucket_name,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=default_ttl,
    )

    body = {
        "uploadUrl": presigned_url,
        "objectKey": object_key,
        "expiresIn": default_ttl,
        "bucket": bucket_name,
    }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }

