import base64
import json
import logging
import os
from typing import Any, Dict, List

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["DYNAMO_TABLE_NAME"])
THRESHOLD = float(os.environ.get("ALERT_THRESHOLD", "0.8"))
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
sns_client = boto3.client("sns") if SNS_TOPIC_ARN else None


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    processed: List[Dict[str, Any]] = []
    for record in event.get("Records", []):
        payload = _decode_record(record)
        if payload is None:
            continue

        device_id = payload.get("deviceId") or "unknown-device"
        timestamp = payload.get("timestamp") or payload.get("eventTime")
        score = float(payload.get("score", 0))

        item = {
            "deviceId": device_id,
            "timestamp": str(timestamp),
            "score": score,
            "rawPayload": payload,
            "aboveThreshold": score >= THRESHOLD,
        }

        table.put_item(Item=item)
        if item["aboveThreshold"] and sns_client:
            _publish_alert(item)
        processed.append(item)

    logger.info("Processed %s telemetry records", len(processed))
    return {"statusCode": 200, "processedCount": len(processed)}


def _decode_record(record: Dict[str, Any]) -> Dict[str, Any] | None:
    try:
        data = record.get("kinesis", {}).get("data")
        if not data:
            logger.warning("Missing data in record: %s", record)
            return None

        decoded = base64.b64decode(data)
        return json.loads(decoded.decode("utf-8"))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("Failed to decode record: %s", exc)
        return None


def _publish_alert(item: Dict[str, Any]) -> None:
    assert sns_client is not None and SNS_TOPIC_ARN is not None
    message = {
        "deviceId": item["deviceId"],
        "timestamp": item["timestamp"],
        "score": item["score"],
    }
    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"Disease threshold exceeded for {item['deviceId']}",
        Message=json.dumps(message),
    )

