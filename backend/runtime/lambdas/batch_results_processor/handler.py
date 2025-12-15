import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

DYNAMO_TABLE_NAME = os.environ["DYNAMO_TABLE_NAME"]
TABLE = dynamodb.Table(DYNAMO_TABLE_NAME)

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
            s3_key = prediction.get("s3_key")  # Full S3 key from batch inference
            binary_prediction = prediction.get("binary_prediction")
            class_name = prediction.get("class_name")
            confidence = Decimal(str(prediction.get("confidence", 0.0)))

            if not filename or not binary_prediction:
                logger.warning(f"Skipping invalid record: {prediction}")
                continue

            # Extract deviceId from S3 key path: photos/{timestamp}/{device_id}.jpg
            # Fallback to filename if s3_key not available (backward compatibility)
            if s3_key:
                # Extract filename from full S3 key path
                s3_filename = s3_key.split("/")[-1]
                device_id = s3_filename.rsplit(".", 1)[0]  # Remove extension
            else:
                # Fallback: extract from filename (backward compatibility)
                device_id = filename.split(".")[0]
                logger.warning(f"Using filename-based deviceId extraction for {filename}. Consider updating batch_inference to include s3_key.")
            
            # Use same timestamp format as telemetry: TS#{YYYYMMDDTHHMMSSZ}-{suffix}
            now = datetime.now(timezone.utc)
            iso = now.strftime("%Y%m%dT%H%M%SZ")
            unique_suffix = uuid.uuid4().hex[:6]
            timestamp = f"TS#{iso}-{unique_suffix}"
            
            metrics = {
                "binary_prediction": binary_prediction,
                "confidence": confidence,
            }
            
            # Build raw dict (convert values to Decimal for numeric fields)
            raw_data = {
                **prediction,
            }
            
            item = {
                "deviceId": device_id,
                "timestamp": timestamp,
                "readingType": DISEASE_READING_TYPE,
                "metrics": _convert_to_decimal_dict(metrics),
                "raw": _convert_to_decimal_dict(raw_data),
            }
            
            # Add sourceKey if available
            if key:
                item["sourceKey"] = key
            
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


def _convert_to_decimal_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert numeric values to Decimal, matching stream_processor behavior."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = _convert_to_decimal_dict(value)
        elif isinstance(value, list):
            result[key] = [_convert_to_decimal(v) if isinstance(v, (int, float)) else v for v in value]
        elif isinstance(value, (int, float)):
            result[key] = Decimal(str(value))
        else:
            result[key] = value
    return result


def _convert_to_decimal(value: Any) -> Decimal:
    """Convert a value to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

