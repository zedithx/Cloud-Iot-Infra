import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["DYNAMO_TABLE_NAME"])

TELEMETRY_READING_TYPE = "telemetry"
CONFIG_TIMESTAMP = "CONFIG"


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    messages = list(_extract_messages(event))
    if not messages:
        logger.warning("Received event with no payload: %s", json.dumps(event))
        return {"statusCode": 200, "processedCount": 0}

    processed: List[Dict[str, Any]] = []
    for message in messages:
        device_id = message.get("deviceId")
        if not device_id:
            logger.warning("Skipping payload without deviceId: %s", message)
            continue

        timestamp = _resolve_timestamp(message)
        reading_item = _build_reading_item(device_id, timestamp, message)
        table.put_item(Item=reading_item)
        processed.append(reading_item)

        if "threshold" in message or "plantType" in message:
            _persist_device_config(device_id, message)

    logger.info("Persisted %s telemetry records", len(processed))
    return {"statusCode": 200, "processedCount": len(processed)}


def _extract_messages(event: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if "Records" in event:
        for record in event["Records"]:
            payload = record.get("body") or record
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("Unable to parse payload string: %s", payload)
                    continue
            if isinstance(payload, dict):
                yield payload
        return

    # IoT Core -> Lambda invokes with {"message": {...}, "topic": "...", ...}
    if "message" in event:
        payload = event["message"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("Unable to parse IoT message string: %s", payload)
                payload = None
        if isinstance(payload, dict):
            yield payload
        return

    if "detail" in event and isinstance(event["detail"], dict):
        yield event["detail"]
        return

    if isinstance(event, dict):
        yield event


def _resolve_timestamp(message: Dict[str, Any]) -> str:
    provided = message.get("timestamp") or message.get("eventTime") or message.get("reportedAt")
    if provided is not None:
        try:
            as_float = float(provided)
            dt = datetime.fromtimestamp(as_float, tz=timezone.utc)
        except (ValueError, TypeError):
            try:
                dt = datetime.fromisoformat(str(provided).replace("Z", "+00:00"))
            except ValueError:
                dt = _now()
    else:
        dt = _now()

    iso = dt.strftime("%Y%m%dT%H%M%SZ")
    unique_suffix = uuid.uuid4().hex[:6]
    return f"{iso}-{unique_suffix}"


def _build_reading_item(device_id: str, timestamp: str, message: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _extract_metrics(message)
    sanitized_raw = _convert_value(message)
    return {
        "deviceId": device_id,
        "timestamp": f"TS#{timestamp}",
        "readingType": TELEMETRY_READING_TYPE,
        "metrics": metrics,
        "raw": sanitized_raw,
    }


def _extract_metrics(message: Dict[str, Any]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    for key, value in message.items():
        if key in {"deviceId", "threshold", "plantType"}:
            continue
        metrics[key] = _convert_value(value)
    return metrics


def _persist_device_config(device_id: str, message: Dict[str, Any]) -> None:
    config_item: Dict[str, Any] = {
        "deviceId": device_id,
        "timestamp": CONFIG_TIMESTAMP,
    }
    if "threshold" in message:
        config_item["threshold"] = _convert_value(message["threshold"])
    if "plantType" in message:
        config_item["plantType"] = message["plantType"]

    table.put_item(Item=config_item)


def _convert_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _convert_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_value(v) for v in value]
    return _to_decimal(value)


def _to_decimal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        return Decimal(value)
    except Exception:  # pylint: disable=broad-exception-caught
        return value


def _now() -> datetime:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc)

