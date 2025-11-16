import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

DYNAMO_TABLE_NAME = os.environ["DYNAMO_TABLE_NAME"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
DEFAULT_THRESHOLD = Decimal(os.environ.get("DEFAULT_THRESHOLD", "0.8"))
ENV_WINDOW_MINUTES = int(os.environ.get("ENV_WINDOW_MINUTES", "30"))

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMO_TABLE_NAME)
sns_client = boto3.client("sns")

TELEMETRY_READING = "telemetry"
DISEASE_READING = "disease"
CONFIG_TIMESTAMP = "CONFIG"

ENVIRONMENT_KEYS = {
    "temperature": {"temperature", "temperatureC", "temperature_c"},
    "humidity": {"humidity"},
    "moisture": {"soil_moisture", "soilMoisture"},
    "lux": {"light_lux", "lightLux", "lux"},
}


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=ENV_WINDOW_MINUTES)
    alerts: List[Dict[str, Any]] = []

    for device_id in _list_device_ids():
        threshold = _load_threshold(device_id) or DEFAULT_THRESHOLD
        disease_score = _load_latest_disease_score(device_id)
        if disease_score is None:
            continue

        env_averages = _compute_environment_averages(device_id, window_start, now)

        if disease_score >= threshold:
            alert_message = _publish_alert(
                device_id, disease_score, float(threshold), env_averages, now
            )
            alerts.append(alert_message)

    return {
        "statusCode": 200,
        "alertsSent": len(alerts),
        "devicesEvaluated": len(alerts),
    }


def _list_device_ids() -> List[str]:
    response = table.scan(ProjectionExpression="deviceId")
    device_ids = {item["deviceId"] for item in response.get("Items", []) if item.get("deviceId")}

    while "LastEvaluatedKey" in response:
        response = table.scan(
            ProjectionExpression="deviceId",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        device_ids.update(
            item["deviceId"] for item in response.get("Items", []) if item.get("deviceId")
        )

    return sorted(device_ids)


def _load_threshold(device_id: str) -> Optional[Decimal]:
    try:
        resp = table.get_item(Key={"deviceId": device_id, "timestamp": CONFIG_TIMESTAMP})
        item = resp.get("Item")
        if item and "threshold" in item:
            return _to_decimal(item["threshold"])
    except ClientError:
        pass
    return None


def _load_latest_disease_score(device_id: str) -> Optional[float]:
    resp = table.query(
        KeyConditionExpression=Key("deviceId").eq(device_id)
        & Key("timestamp").begins_with("DISEASE#"),
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return None
    metrics = items[0].get("metrics", {})
    score = metrics.get("diseaseRisk")
    if score is not None:
        decimal_score = _to_decimal(score)
        return float(decimal_score) if decimal_score is not None else None
    return None


def _compute_environment_averages(
    device_id: str, window_start: datetime, window_end: datetime
) -> Dict[str, float]:
    start_key = f"TS#{_timestamp_prefix(window_start, low=True)}"
    end_key = f"TS#{_timestamp_prefix(window_end, low=False)}"

    resp = table.query(
        KeyConditionExpression=Key("deviceId").eq(device_id)
        & Key("timestamp").between(start_key, end_key),
    )

    aggregates: Dict[str, Tuple[Decimal, int]] = {metric: (Decimal("0"), 0) for metric in ENVIRONMENT_KEYS}

    for item in resp.get("Items", []):
        if item.get("readingType") != TELEMETRY_READING:
            continue
        metrics = item.get("metrics", {})
        for metric_name, aliases in ENVIRONMENT_KEYS.items():
            for alias in aliases:
                if alias in metrics and metrics[alias] is not None:
                    value = _to_decimal(metrics[alias])
                    if value is None:
                        continue
                    total, count = aggregates[metric_name]
                    aggregates[metric_name] = (total + value, count + 1)
                    break

    averages: Dict[str, float] = {}
    for metric_name, (total, count) in aggregates.items():
        if count > 0:
            averages[metric_name] = float(total / count)
    return averages


def _publish_alert(
    device_id: str,
    disease_score: float,
    threshold: float,
    env_averages: Dict[str, float],
    now: datetime,
) -> Dict[str, Any]:
    payload = {
        "deviceId": device_id,
        "diseaseRisk": disease_score,
        "threshold": threshold,
        "environmentAverages": env_averages,
        "evaluatedAt": now.isoformat(),
    }
    subject = f"Disease risk high for {device_id}"
    body_text = _build_body_text(device_id, disease_score, threshold, env_averages, now)
    body_html = _build_body_html(device_id, disease_score, threshold, env_averages, now)

    message = {
        "subject": subject,
        "bodyText": body_text,
        "bodyHtml": body_html,
        "payload": payload,
    }

    sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(message),
    )
    return message


def _build_body_text(
    device_id: str,
    disease_score: float,
    threshold: float,
    env_averages: Dict[str, float],
    now: datetime,
) -> str:
    lines = [
        f"Device ID: {device_id}",
        f"Disease risk score: {disease_score:.2f}",
        f"Threshold: {threshold:.2f}",
    ]
    if env_averages:
        lines.append("Environmental averages (last 30 minutes):")
        for metric, value in env_averages.items():
            lines.append(f"  - {metric}: {value:.2f}")
    else:
        lines.append("Environmental averages unavailable during the evaluation window.")
    lines.append(f"Evaluated at: {now.isoformat()}")
    return "\n".join(lines)


def _build_body_html(
    device_id: str,
    disease_score: float,
    threshold: float,
    env_averages: Dict[str, float],
    now: datetime,
) -> str:
    parts: List[str] = [
        f"<p><strong>Device ID:</strong> {device_id}</p>",
        f"<p><strong>Disease risk score:</strong> {disease_score:.2f}</p>",
        f"<p><strong>Threshold:</strong> {threshold:.2f}</p>",
    ]
    if env_averages:
        items = "".join(
            f"<li><strong>{metric}:</strong> {value:.2f}</li>"
            for metric, value in env_averages.items()
        )
        parts.append(
            "<p><strong>Environmental averages (last 30 minutes):</strong></p>"
            f"<ul>{items}</ul>"
        )
    else:
        parts.append(
            "<p><strong>Environmental averages:</strong> Unavailable during the evaluation window.</p>"
        )
    parts.append(f"<p><strong>Evaluated at:</strong> {now.isoformat()}</p>")
    return "".join(parts)


def _timestamp_prefix(dt: datetime, low: bool) -> str:
    base = dt.strftime("%Y%m%dT%H%M%SZ")
    return f"{base}-" if low else f"{base}~"


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except Exception:  # pylint: disable=broad-exception-caught
        return None

