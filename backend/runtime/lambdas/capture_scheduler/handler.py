import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

import boto3

iot_client = boto3.client("iot-data")
dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    table_name = os.environ["DYNAMO_TABLE_NAME"]
    table = dynamodb.Table(table_name)

    # Get all device IDs from DynamoDB
    device_ids = _list_device_ids(table)

    if not device_ids:
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "No devices found", "sent": 0}),
        }

    # Get S3 bucket and prefix from environment
    raw_bucket = os.environ["RAW_BUCKET_NAME"]
    photo_prefix = os.environ.get("PHOTO_PREFIX", "photos")
    presigned_url_expiry = int(os.environ.get("PRESIGNED_URL_EXPIRY", "3600"))  # Default 1 hour

    # Generate shared hourly timestamp for all devices in this capture batch
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H")

    # Publish photo capture command with presigned URL to each device
    sent_count = 0
    for device_id in device_ids:
        # Generate S3 key with shared timestamp: photos/{timestamp}/{device_id}.jpg
        s3_key = f"{photo_prefix}/{timestamp}/{device_id}.jpg"

        # Generate presigned URL for PUT operation
        try:
            presigned_url = s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": raw_bucket,
                    "Key": s3_key,
                    "ContentType": "image/jpeg",
                },
                ExpiresIn=presigned_url_expiry,
            )

            topic = f"leaf/commands/{device_id}/photo"
            payload = {
                "command": "capture",
                "uploadUrl": presigned_url,
                "s3Key": s3_key,
                "expiresIn": presigned_url_expiry,
            }

            iot_client.publish(
                topic=topic,
                qos=1,
                payload=json.dumps(payload),
            )
            sent_count += 1
        except Exception as e:
            # Log error but continue with other devices
            print(f"Failed to generate presigned URL or publish to {device_id}: {e}")

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": f"Sent photo capture commands to {sent_count} device(s)",
                "sent": sent_count,
                "devices": list(device_ids),
            }
        ),
    }


def _list_device_ids(table: Any) -> List[str]:
    """Get all unique device IDs from DynamoDB."""
    device_ids: Set[str] = set()
    response = table.scan(ProjectionExpression="deviceId")
    device_ids.update(
        item["deviceId"] for item in response.get("Items", []) if item.get("deviceId")
    )

    while "LastEvaluatedKey" in response:
        response = table.scan(
            ProjectionExpression="deviceId",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        device_ids.update(
            item["deviceId"] for item in response.get("Items", []) if item.get("deviceId")
        )

    return sorted(device_ids)

