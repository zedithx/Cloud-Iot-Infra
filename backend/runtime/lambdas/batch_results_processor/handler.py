from fileinput import filename
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

DYNAMO_TABLE_NAME = os.environ["DYNAMO_TABLE_NAME"]
TABLE = dynamodb.Table(DYNAMO_TABLE_NAME)  # This is probabably telemetry table

DISEASE_READING_TYPE = "disease"


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """
    Triggered by S3 OBJECT_CREATED event in BatchResultsBucket
    Reads NDJSON lines containing:
    {
      "filename": "device123.jpg",
      "class_idx": 19,
      "class_name": "...",
      "binary_prediction": "...",
      "confidence": 0.97
    }
    """
    records = event.get("Records", [])
    processed = 0

    for record in records:
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        key = record.get("s3", {}).get("object", {}).get("key")
        if not bucket or not key:
            logger.warning("Skipping record without bucket/key: %s", record)
            continue

        for prediction in _read_object_lines(bucket, key):
            filename = prediction.get("filename")
            binary_prediction = prediction.get("binary_prediction")
            class_name = prediction.get("class_name")
            confidence = Decimal(str(prediction.get("confidence", 0.0)))

            if not filename or not binary_prediction:
                logger.warning(f"Skipping invalid record: {prediction}")
                continue

            device_id = filename.split(".")[0]  # Assuming filename is {device_id}.jpg
            
            # DynamoDB timestamp with full precision
            dynamo_timestamp = f"DISEASE#{_current_timestamp()}"
            item = {
                "deviceId": device_id,
                "timestamp": dynamo_timestamp,
                "readingType": DISEASE_READING_TYPE,
                "metrics": {
                    "prediction": binary_prediction,
                    "className": class_name,
                    "diseaseRisk": confidence,
                    "filename": filename,
                },
                    "raw": {
                        **prediction,
                        "confidence": confidence
                    },
                "sourceKey": key,
            }
            TABLE.put_item(Item=item)
            processed += 1

    logger.info("Persisted %s disease risk results", processed)
    return {"statusCode": 200, "processed": processed}


def _read_object_lines(bucket: str, key: str) -> Iterable[Dict[str, Any]]:
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8").strip()
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            logger.exception("Failed to decode JSON line: %s", line)

def _current_timestamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")

