import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import boto3
from boto3.dynamodb.conditions import Key

DYNAMO_TABLE_NAME = os.environ["DYNAMO_TABLE_NAME"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
ENV_WINDOW_MINUTES = int(os.environ.get("ENV_WINDOW_MINUTES", "30"))
TREND_WINDOW_HOURS = int(os.environ.get("TREND_WINDOW_HOURS", "3"))  # 3 hours for trend detection

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMO_TABLE_NAME)
sns_client = boto3.client("sns")

TELEMETRY_READING = "telemetry"
DISEASE_READING = "disease"

ENVIRONMENT_KEYS = {
    "temperature": {"temperature", "temperatureC", "temperature_c"},
    "humidity": {"humidity"},
    "moisture": {"soil_moisture", "soilMoisture"},
    "lux": {"light_lux", "lightLux", "lux"},
}



def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=ENV_WINDOW_MINUTES)
    trend_window_start = now - timedelta(hours=TREND_WINDOW_HOURS)
    
    alerts: List[Dict[str, Any]] = []
    device_ids = _list_device_ids()

    for device_id in device_ids:
        # Check for disease label (triggers alert regardless of confidence/score)
        disease_alert = _check_disease_label(device_id, window_start, now)
        if disease_alert:
            alerts.append(disease_alert)
        
        # Check unusual trends/spiking trends
        trend_alerts = _check_unusual_trends(device_id, trend_window_start, now)
        alerts.extend(trend_alerts)
        
        # Check water tank status
        water_tank_alert = _check_water_tank_status(device_id, now)
        if water_tank_alert:
            alerts.append(water_tank_alert)

    return {
        "statusCode": 200,
        "alertsSent": len(alerts),
        "devicesEvaluated": len(device_ids),
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




def _check_disease_label(device_id: str, window_start: datetime, window_end: datetime) -> Optional[Dict[str, Any]]:
    """Check if latest disease record has label='disease' and trigger alert regardless of confidence/score."""
    # Query all records for this device, then filter by readingType
    resp = table.query(
        KeyConditionExpression=Key("deviceId").eq(device_id),
        ScanIndexForward=False,
    )
    items = resp.get("Items", [])
    
    # Filter to only disease records and get the latest one
    disease_items = [
        item for item in items 
        if item.get("readingType") == DISEASE_READING
    ]
    
    if not disease_items:
        return None
    
    # Get the latest disease record (already sorted by ScanIndexForward=False)
    latest = disease_items[0]
    
    # Check for label field - can be in metrics, raw, or top-level
    label = (
        latest.get("label") or 
        latest.get("metrics", {}).get("label") or 
        latest.get("raw", {}).get("label") or
        latest.get("metrics", {}).get("binary_prediction")
    )
    
    # Convert binary_prediction to label format if needed
    if label is None:
        binary_pred = latest.get("metrics", {}).get("binary_prediction") or latest.get("raw", {}).get("binary_prediction")
        if binary_pred:
            label = "disease" if str(binary_pred).lower() != "healthy" else "healthy"
    
    # Trigger alert if label is "disease" (regardless of confidence/score)
    if label and str(label).lower() == "disease":
        metrics = latest.get("metrics", {})
        score = metrics.get("diseaseRisk") or metrics.get("confidence")
        disease_score = None
        if score is not None:
            decimal_score = _to_decimal(score)
            disease_score = float(decimal_score) if decimal_score is not None else None
        
        env_averages = _compute_environment_averages(device_id, window_start, window_end)
        return _publish_alert(
            device_id,
            "disease_detected",
            {
                "label": str(label),
                "diseaseRisk": disease_score,
                "environmentAverages": env_averages,
            },
            window_end,
        )
    
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




def _check_unusual_trends(
    device_id: str,
    window_start: datetime,
    window_end: datetime,
) -> List[Dict[str, Any]]:
    """Check for unusual trends (rapid changes) in environmental conditions."""
    alerts = []
    
    # Get telemetry data for trend analysis
    start_key = f"TS#{_timestamp_prefix(window_start, low=True)}"
    end_key = f"TS#{_timestamp_prefix(window_end, low=False)}"
    
    resp = table.query(
        KeyConditionExpression=Key("deviceId").eq(device_id)
        & Key("timestamp").between(start_key, end_key),
    )
    
    items = sorted(
        [item for item in resp.get("Items", []) if item.get("readingType") == TELEMETRY_READING],
        key=lambda x: x.get("timestamp", "")
    )
    
    if len(items) < 2:
        return alerts
    
    # Analyze trends (similar to recommendation system)
    trends = _analyze_trends_from_items(items, window_start, window_end)
    
    # Check for rapid temperature increase (>3°C/hour or >7°C in 3 hours)
    if trends.get("temperature_trend") in ["increasing_very_rapidly", "increasing_rapidly"]:
        alert_message = _publish_alert(
            device_id,
            "unusual_temperature_trend",
            {
                "trend": trends.get("temperature_trend"),
                "rate": trends.get("temperature_rate", 0),
                "start": trends.get("temperature_start"),
                "end": trends.get("temperature_end"),
                "period_hours": trends.get("temperature_period_hours", 0),
            },
            window_end,
        )
        alerts.append(alert_message)
    
    # Check for rapid humidity drop (>10% in 6 hours)
    if trends.get("humidity_trend") in ["decreasing_very_rapidly", "decreasing_rapidly"]:
        alert_message = _publish_alert(
            device_id,
            "unusual_humidity_trend",
            {
                "trend": trends.get("humidity_trend"),
                "change": trends.get("humidity_change", 0),
                "start": trends.get("humidity_start"),
                "end": trends.get("humidity_end"),
                "period_hours": trends.get("humidity_period_hours", 0),
            },
            window_end,
        )
        alerts.append(alert_message)
    
    # Check for rapid light drop (>30% in 6 hours)
    if trends.get("light_trend") in ["decreasing_very_rapidly", "decreasing_rapidly"]:
        alert_message = _publish_alert(
            device_id,
            "unusual_light_trend",
            {
                "trend": trends.get("light_trend"),
                "change": trends.get("light_change", 0),
                "start": trends.get("light_start"),
                "end": trends.get("light_end"),
                "period_hours": trends.get("light_period_hours", 0),
            },
            window_end,
        )
        alerts.append(alert_message)
    
    return alerts


def _analyze_trends_from_items(
    items: List[Dict[str, Any]],
    window_start: datetime,
    window_end: datetime,
) -> Dict[str, Any]:
    """Analyze trends from telemetry items (similar to recommendation system)."""
    trends = {
        "temperature_trend": "stable",
        "humidity_trend": "stable",
        "light_trend": "stable",
        "temperature_rate": 0.0,
        "temperature_start": None,
        "temperature_end": None,
        "temperature_period_hours": 0.0,
        "humidity_change": 0.0,
        "humidity_start": None,
        "humidity_end": None,
        "humidity_period_hours": 0.0,
        "light_change": 0.0,
        "light_start": None,
        "light_end": None,
        "light_period_hours": 0.0,
    }
    
    # Extract data points with timestamps
    temp_points = []
    humidity_points = []
    light_points = []
    
    for item in items:
        metrics = item.get("metrics", {})
        timestamp_str = item.get("timestamp", "")
        
        # Parse timestamp - convert from TS# format to epoch seconds
        timestamp = _parse_timestamp_from_item(timestamp_str)
        if timestamp is None:
            continue
        
        if "temperatureC" in metrics or "temperature" in metrics:
            temp = metrics.get("temperatureC") or metrics.get("temperature")
            if temp is not None:
                temp_value = _to_decimal(temp)
                if temp_value is not None:
                    temp_points.append((timestamp, float(temp_value)))
        
        if "humidity" in metrics:
            humidity = metrics.get("humidity")
            if humidity is not None:
                humidity_value = _to_decimal(humidity)
                if humidity_value is not None:
                    humidity_points.append((timestamp, float(humidity_value)))
        
        if "lightLux" in metrics or "light_lux" in metrics:
            light = metrics.get("lightLux") or metrics.get("light_lux")
            if light is not None:
                light_value = _to_decimal(light)
                if light_value is not None:
                    light_points.append((timestamp, float(light_value)))
    
    # Analyze temperature trend (last 3 hours)
    if len(temp_points) >= 2:
        three_hours_ago = window_end - timedelta(hours=3)
        recent_temps = [(t, v) for t, v in temp_points if t >= three_hours_ago]
        if len(recent_temps) >= 2:
            first_temp = recent_temps[0][1]
            last_temp = recent_temps[-1][1]
            time_diff = (recent_temps[-1][0] - recent_temps[0][0]).total_seconds() / 3600.0
            if time_diff > 0:
                temp_rate = (last_temp - first_temp) / time_diff
                trends["temperature_rate"] = temp_rate
                trends["temperature_start"] = first_temp
                trends["temperature_end"] = last_temp
                trends["temperature_period_hours"] = time_diff
                
                if temp_rate > 4.0 or (last_temp - first_temp) > 10.0:
                    trends["temperature_trend"] = "increasing_very_rapidly"
                elif temp_rate > 3.0 or (last_temp - first_temp) > 7.0:
                    trends["temperature_trend"] = "increasing_rapidly"
    
    # Analyze humidity trend (last 6 hours)
    if len(humidity_points) >= 2:
        six_hours_ago = window_end - timedelta(hours=6)
        recent_humidity = [(t, v) for t, v in humidity_points if t >= six_hours_ago]
        if len(recent_humidity) >= 2:
            first_humidity = recent_humidity[0][1]
            last_humidity = recent_humidity[-1][1]
            time_diff = (recent_humidity[-1][0] - recent_humidity[0][0]).total_seconds() / 3600.0
            humidity_change = last_humidity - first_humidity
            trends["humidity_change"] = humidity_change
            trends["humidity_start"] = first_humidity
            trends["humidity_end"] = last_humidity
            trends["humidity_period_hours"] = time_diff
            
            if humidity_change < -15.0:
                trends["humidity_trend"] = "decreasing_very_rapidly"
            elif humidity_change < -10.0:
                trends["humidity_trend"] = "decreasing_rapidly"
    
    # Analyze light trend (last 6 hours)
    if len(light_points) >= 2:
        six_hours_ago = window_end - timedelta(hours=6)
        recent_light = [(t, v) for t, v in light_points if t >= six_hours_ago]
        if len(recent_light) >= 2:
            first_light = recent_light[0][1]
            last_light = recent_light[-1][1]
            time_diff = (recent_light[-1][0] - recent_light[0][0]).total_seconds() / 3600.0
            if first_light > 0 and time_diff > 0:
                light_change_pct = ((last_light - first_light) / first_light) * 100
                trends["light_change"] = light_change_pct
                trends["light_start"] = first_light
                trends["light_end"] = last_light
                trends["light_period_hours"] = time_diff
                
                if light_change_pct < -40.0:
                    trends["light_trend"] = "decreasing_very_rapidly"
                elif light_change_pct < -30.0:
                    trends["light_trend"] = "decreasing_rapidly"
    
    return trends


def _check_water_tank_status(device_id: str, now: datetime) -> Optional[Dict[str, Any]]:
    """Check if water tank is empty and alert if needed."""
    # Get the latest telemetry reading
    window_start = now - timedelta(minutes=ENV_WINDOW_MINUTES)
    start_key = f"TS#{_timestamp_prefix(window_start, low=True)}"
    end_key = f"TS#{_timestamp_prefix(now, low=False)}"
    
    resp = table.query(
        KeyConditionExpression=Key("deviceId").eq(device_id)
        & Key("timestamp").between(start_key, end_key),
        ScanIndexForward=False,
        Limit=1,
    )
    
    items = [item for item in resp.get("Items", []) if item.get("readingType") == TELEMETRY_READING]
    if not items:
        return None
    
    # Check latest reading for waterTankFilled or waterTankEmpty
    latest_item = items[0]
    metrics = latest_item.get("metrics", {})
    water_tank_empty = None
    
    # First check for waterTankFilled (invert logic: 1=filled -> 0=empty, 0=not filled -> 1=empty)
    if "waterTankFilled" in metrics:
        water_tank_filled = metrics.get("waterTankFilled")
        if water_tank_filled is not None:
            try:
                filled_value = float(water_tank_filled)
                water_tank_empty = 0 if filled_value == 1 else 1
            except (ValueError, TypeError):
                pass
    # Otherwise check for waterTankEmpty directly
    elif "waterTankEmpty" in metrics:
        water_tank_empty = metrics.get("waterTankEmpty")
    
    # Convert to int if it's a Decimal or string
    if water_tank_empty is not None:
        if isinstance(water_tank_empty, Decimal):
            water_tank_empty = int(water_tank_empty)
        elif isinstance(water_tank_empty, (int, float)):
            water_tank_empty = int(water_tank_empty)
        elif isinstance(water_tank_empty, str):
            try:
                water_tank_empty = int(water_tank_empty)
            except (ValueError, TypeError):
                return None
        
        # Alert if tank is empty (value is 1)
        if water_tank_empty == 1:
            return _publish_alert(
                device_id,
                "water_tank_empty",
                {
                    "status": "empty",
                    "message": "Water tank is empty and requires refill",
                },
                now,
            )
    
    return None


def _parse_timestamp_from_item(timestamp_str: str) -> Optional[datetime]:
    """Parse timestamp from DynamoDB item timestamp field."""
    if not timestamp_str:
        return None
    
    # Handle TS# prefix format: TS#20240101T120000Z-abc123
    if timestamp_str.startswith("TS#"):
        timestamp_str = timestamp_str[3:]
    
    # Remove suffix after first dash
    if "-" in timestamp_str:
        timestamp_str = timestamp_str.split("-")[0]
    
    # Try to parse ISO-like format: YYYYMMDDTHHMMSSZ
    try:
        return datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # Fallback: try to parse as epoch seconds (if stored as number)
        try:
            epoch_seconds = int(timestamp_str)
            return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        except (ValueError, TypeError):
            return None


def _publish_alert(
    device_id: str,
    alert_type: str,
    alert_data: Dict[str, Any],
    now: datetime,
) -> Dict[str, Any]:
    """Publish alert to SNS with different message formats based on alert type."""
    
    if alert_type == "disease_detected":
        subject = f"⚠️ Disease Detected: {device_id}"
        body_text = _build_disease_alert_text(device_id, alert_data, now)
        body_html = _build_disease_alert_html(device_id, alert_data, now)
    elif alert_type.startswith("unusual_"):
        metric_name = alert_type.replace("unusual_", "").replace("_trend", "").replace("_", " ").title()
        subject = f"🌡️ Unusual Trend Detected: {device_id} - {metric_name}"
        body_text = _build_trend_alert_text(device_id, alert_type, alert_data, now)
        body_html = _build_trend_alert_html(device_id, alert_type, alert_data, now)
    elif alert_type == "water_tank_empty":
        subject = f"💧 Water Tank Empty: {device_id}"
        body_text = _build_water_tank_alert_text(device_id, alert_data, now)
        body_html = _build_water_tank_alert_html(device_id, alert_data, now)
    else:
        subject = f"Alert: {device_id}"
        body_text = json.dumps(alert_data, indent=2)
        body_html = f"<pre>{json.dumps(alert_data, indent=2)}</pre>"
    
    payload = {
        "deviceId": device_id,
        "alertType": alert_type,
        "alertData": alert_data,
        "evaluatedAt": now.isoformat(),
    }
    
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


def _build_disease_alert_text(device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build text body for disease detection alert."""
    lines = [
        f"Device ID: {device_id}",
        f"⚠️ DISEASE DETECTED",
        f"",
        f"Label: {data.get('label', 'disease')}",
    ]
    if data.get("diseaseRisk") is not None:
        lines.append(f"Disease risk score: {data['diseaseRisk']:.2f}")
    if data.get("environmentAverages"):
        lines.append("")
        lines.append("Environmental averages (last 30 minutes):")
        for metric, value in data["environmentAverages"].items():
            lines.append(f"  - {metric}: {value:.2f}")
    else:
        lines.append("")
        lines.append("Environmental averages unavailable during the evaluation window.")
    lines.append("")
    lines.append(f"Evaluated at: {now.isoformat()}")
    return "\n".join(lines)


def _build_disease_alert_html(device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build HTML body for disease detection alert."""
    parts = [
        f"<p><strong>Device ID:</strong> {device_id}</p>",
        f'<p><strong style="color: red;">⚠️ DISEASE DETECTED</strong></p>',
        f"<p><strong>Label:</strong> {data.get('label', 'disease')}</p>",
    ]
    if data.get("diseaseRisk") is not None:
        parts.append(f"<p><strong>Disease risk score:</strong> {data['diseaseRisk']:.2f}</p>")
    if data.get("environmentAverages"):
        items = "".join(
            f"<li><strong>{metric}:</strong> {value:.2f}</li>"
            for metric, value in data["environmentAverages"].items()
        )
        parts.append("<p><strong>Environmental averages (last 30 minutes):</strong></p>")
        parts.append(f"<ul>{items}</ul>")
    else:
        parts.append(
            "<p><strong>Environmental averages:</strong> Unavailable during the evaluation window.</p>"
        )
    parts.append(f"<p><strong>Evaluated at:</strong> {now.isoformat()}</p>")
    return "".join(parts)




def _build_trend_alert_text(device_id: str, alert_type: str, data: Dict[str, Any], now: datetime) -> str:
    """Build text body for unusual trend alert."""
    metric_name = alert_type.replace("unusual_", "").replace("_trend", "").replace("_", " ").title()
    lines = [
        f"Device ID: {device_id}",
        f"🌡️ UNUSUAL {metric_name.upper()} TREND DETECTED",
        f"",
    ]
    
    if "temperature" in alert_type:
        lines.extend([
            f"Trend: {data.get('trend', 'unknown')}",
            f"Rate of change: {data.get('rate', 0):.1f}°C/hour",
            f"Temperature change: {data.get('start', 0):.1f}°C → {data.get('end', 0):.1f}°C",
            f"Time period: {data.get('period_hours', 0):.1f} hours",
        ])
    elif "humidity" in alert_type:
        lines.extend([
            f"Trend: {data.get('trend', 'unknown')}",
            f"Humidity change: {data.get('start', 0):.1f}% → {data.get('end', 0):.1f}%",
            f"Change: {data.get('change', 0):.1f}%",
            f"Time period: {data.get('period_hours', 0):.1f} hours",
        ])
    elif "light" in alert_type:
        lines.extend([
            f"Trend: {data.get('trend', 'unknown')}",
            f"Light change: {data.get('start', 0):.0f} lux → {data.get('end', 0):.0f} lux",
            f"Change: {data.get('change', 0):.1f}%",
            f"Time period: {data.get('period_hours', 0):.1f} hours",
        ])
    
    lines.extend([
        f"",
        f"This rapid change may require manual intervention or threshold adjustment.",
        f"Evaluated at: {now.isoformat()}",
    ])
    return "\n".join(lines)


def _build_trend_alert_html(device_id: str, alert_type: str, data: Dict[str, Any], now: datetime) -> str:
    """Build HTML body for unusual trend alert."""
    metric_name = alert_type.replace("unusual_", "").replace("_trend", "").replace("_", " ").title()
    parts = [
        f"<p><strong>Device ID:</strong> {device_id}</p>",
        f'<p><strong style="color: orange;">🌡️ UNUSUAL {metric_name.upper()} TREND DETECTED</strong></p>',
    ]
    
    if "temperature" in alert_type:
        parts.extend([
            f"<p><strong>Trend:</strong> {data.get('trend', 'unknown')}</p>",
            f"<p><strong>Rate of change:</strong> {data.get('rate', 0):.1f}°C/hour</p>",
            f"<p><strong>Temperature change:</strong> {data.get('start', 0):.1f}°C → {data.get('end', 0):.1f}°C</p>",
            f"<p><strong>Time period:</strong> {data.get('period_hours', 0):.1f} hours</p>",
        ])
    elif "humidity" in alert_type:
        parts.extend([
            f"<p><strong>Trend:</strong> {data.get('trend', 'unknown')}</p>",
            f"<p><strong>Humidity change:</strong> {data.get('start', 0):.1f}% → {data.get('end', 0):.1f}%</p>",
            f"<p><strong>Change:</strong> {data.get('change', 0):.1f}%</p>",
            f"<p><strong>Time period:</strong> {data.get('period_hours', 0):.1f} hours</p>",
        ])
    elif "light" in alert_type:
        parts.extend([
            f"<p><strong>Trend:</strong> {data.get('trend', 'unknown')}</p>",
            f"<p><strong>Light change:</strong> {data.get('start', 0):.0f} lux → {data.get('end', 0):.0f} lux</p>",
            f"<p><strong>Change:</strong> {data.get('change', 0):.1f}%</p>",
            f"<p><strong>Time period:</strong> {data.get('period_hours', 0):.1f} hours</p>",
        ])
    
    parts.extend([
        f"<p><em>This rapid change may require manual intervention or threshold adjustment.</em></p>",
        f"<p><strong>Evaluated at:</strong> {now.isoformat()}</p>",
    ])
    return "".join(parts)


def _build_water_tank_alert_text(device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build text body for water tank empty alert."""
    lines = [
        f"Device ID: {device_id}",
        f"💧 WATER TANK EMPTY",
        f"",
        f"Status: {data.get('status', 'empty')}",
        f"Message: {data.get('message', 'Water tank is empty and requires refill')}",
        f"",
        f"Please refill the water tank to ensure the auto-heal system can function properly.",
        f"",
        f"Evaluated at: {now.isoformat()}",
    ]
    return "\n".join(lines)


def _build_water_tank_alert_html(device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build HTML body for water tank empty alert."""
    return f"""
    <p><strong>Device ID:</strong> {device_id}</p>
    <p><strong style="color: red;">💧 WATER TANK EMPTY</strong></p>
    <p><strong>Status:</strong> {data.get('status', 'empty')}</p>
    <p><strong>Message:</strong> {data.get('message', 'Water tank is empty and requires refill')}</p>
    <p><em>Please refill the water tank to ensure the auto-heal system can function properly.</em></p>
    <p><strong>Evaluated at:</strong> {now.isoformat()}</p>
    """


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

