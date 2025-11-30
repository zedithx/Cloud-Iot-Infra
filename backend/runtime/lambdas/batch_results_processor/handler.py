import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

DYNAMO_TABLE_NAME = os.environ["DYNAMO_TABLE_NAME"]
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")
TABLE = dynamodb.Table(DYNAMO_TABLE_NAME)

DISEASE_READING_TYPE = "disease"


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    records = event.get("Records", [])
    processed = 0

    for record in records:
        bucket = record.get("s3", {}).get("bucket", {}).get("name")
        key = record.get("s3", {}).get("object", {}).get("key")
        if not bucket or not key:
            logger.warning("Skipping record without bucket/key: %s", record)
            continue

        # Extract photo timestamp from batch job output path or calculate from current time
        # Batch runs at :05, processing photos from previous hour
        photo_timestamp = _extract_photo_timestamp(key)
        
        lines = _read_object_lines(bucket, key)
        for payload in lines:
            device_id = _extract_device_id(payload, key)
            if not device_id:
                logger.warning("Unable to determine deviceId for payload %s from %s", payload, key)
                continue
            disease_score = _extract_score(payload)
            
            # DynamoDB timestamp with full precision
            dynamo_timestamp = f"DISEASE#{_current_timestamp()}"
            item = {
                "deviceId": device_id,
                "timestamp": dynamo_timestamp,
                "readingType": DISEASE_READING_TYPE,
                "metrics": {"diseaseRisk": disease_score},
                "raw": payload,
                "sourceKey": key,
            }
            TABLE.put_item(Item=item)
            
            # Store result in S3 as disease_results/{device_id}/{photo_timestamp}.json
            if PROCESSED_BUCKET:
                _store_result_in_s3(device_id, photo_timestamp, payload, disease_score)
            
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


def _extract_device_id(payload: Dict[str, Any], key: str) -> Optional[str]:
    if "deviceId" in payload:
        return str(payload["deviceId"])
    parts = key.split("/")
    for part in reversed(parts):
        if part and not part.endswith(".json"):
            return part
    return None


def _extract_score(payload: Dict[str, Any]) -> Decimal:
    value = (
        payload.get("diseaseRisk")
        or payload.get("score")
        or payload.get("prediction")
        or payload.get("probability")
        or payload.get("risk")
        or 0
    )
    try:
        return Decimal(str(value))
    except Exception:  # pylint: disable=broad-exception-caught
        return Decimal("0")


def _current_timestamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def _extract_photo_timestamp(key: str) -> str:
    """
    Extract photo timestamp from batch job output key.
    Batch runs at :05, processing photos from previous hour.
    If unable to extract from key, calculate from current time - 1 hour.
    """
    # Try to extract from key path structure: {STAGE}/{job_timestamp}/...
    # Since batch processes photos from previous hour, calculate that
    previous_hour = datetime.now(timezone.utc) - timedelta(hours=1)
    return previous_hour.strftime("%Y%m%dT%H")


def _store_result_in_s3(device_id: str, photo_timestamp: str, payload: Dict[str, Any], disease_score: Decimal) -> None:
    """Store disease result in S3 as disease_results/{device_id}/{photo_timestamp}.json"""
    if not PROCESSED_BUCKET:
        return
    
    try:
        result_key = f"disease_results/{device_id}/{photo_timestamp}.json"
        result_data = {
            "deviceId": device_id,
            "photoTimestamp": photo_timestamp,
            "diseaseRisk": float(disease_score),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        
        s3_client.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=result_key,
            Body=json.dumps(result_data, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Stored disease result to s3://%s/%s", PROCESSED_BUCKET, result_key)
    except Exception as e:
        logger.error("Failed to store disease result in S3 for device %s: %s", device_id, e)

