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

