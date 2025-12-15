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
ALERT_COOLDOWN_HOURS = int(os.environ.get("ALERT_COOLDOWN_HOURS", "24"))  # 24 hours cooldown between same alerts
MAX_ALERT_COUNT = int(os.environ.get("MAX_ALERT_COUNT", "3"))  # Maximum 3 alerts per alert type per device

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMO_TABLE_NAME)
sns_client = boto3.client("sns")

TELEMETRY_READING = "telemetry"
DISEASE_READING = "disease"
USER_PLANTS_DEVICE_ID = "USER_PLANTS"

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
    resolutions: List[Dict[str, Any]] = []
    device_ids = _list_device_ids()
    
    # Load previous alert states for resolution detection
    previous_states = _load_previous_alert_states()
    
    # Track new states to save at the end
    new_states: Dict[str, Dict[str, bool]] = {}

    for device_id in device_ids:
        # Skip system device IDs
        if device_id in [USER_PLANTS_DEVICE_ID, "ALERT_STATES", "ALERT_TRACKING"]:
            continue
        
        # Skip device IDs that are disease-related (safety check)
        if device_id.lower() in ["disease", "diseased", "healthy"]:
            continue
            
        plant_name = _get_plant_name(device_id)
        
        # Check current alert states (before generating alerts)
        has_disease = _check_disease_label(device_id, window_start, now) is not None
        has_water_tank_empty = _check_water_tank_status(device_id, now) is not None
        trend_alerts_list = _check_unusual_trends(device_id, trend_window_start, now)
        has_trends = len(trend_alerts_list) > 0
        
        current_states = {
            "disease": has_disease,
            "water_tank_empty": has_water_tank_empty,
            "trends": has_trends,
        }
        
        # Check for resolutions (previous alert cleared)
        device_key = device_id
        if device_key in previous_states:
            prev = previous_states[device_key]
            # Disease resolution
            if prev.get("disease") and not current_states["disease"]:
                resolutions.append(_publish_resolution(device_id, plant_name, "disease", now))
            # Water tank resolution
            if prev.get("water_tank_empty") and not current_states["water_tank_empty"]:
                resolutions.append(_publish_resolution(device_id, plant_name, "water_tank_empty", now))
            # Trends resolution
            if prev.get("trends") and not current_states["trends"]:
                resolutions.append(_publish_resolution(device_id, plant_name, "trends", now))
        
        # Check for disease label (triggers alert regardless of confidence/score)
        # Pass plant_name so it can be included in the alert
        disease_alert = _check_disease_label(device_id, window_start, now, plant_name)
        if disease_alert:
            alerts.append(disease_alert)
        
        # Check unusual trends/spiking trends
        trend_alerts_list = _check_unusual_trends(device_id, trend_window_start, now, plant_name)
        alerts.extend(trend_alerts_list)
        
        # Check water tank status
        water_tank_alert = _check_water_tank_status(device_id, now, plant_name)
        if water_tank_alert:
            alerts.append(water_tank_alert)
        
        # Store current state for next evaluation
        new_states[device_id] = current_states
    
    # Save all states at once
    _save_alert_states(new_states)

    return {
        "statusCode": 200,
        "alertsSent": len(alerts),
        "resolutionsSent": len(resolutions),
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


def _get_plant_name(device_id: str) -> str:
    """Get plant name from USER_PLANTS table, fallback to device ID if not found."""
    try:
        response = table.query(
            KeyConditionExpression=Key("deviceId").eq(USER_PLANTS_DEVICE_ID)
        )
        
        for item in response.get("Items", []):
            plant_name_full = item.get("plantName", "")
            if "|" in plant_name_full:
                parts = plant_name_full.split("|", 1)
                if len(parts) >= 1 and parts[0] == device_id:
                    # Found the plant name - extract the part after the pipe
                    if len(parts) >= 2 and parts[1] and parts[1].strip():
                        plant_name = parts[1].strip()
                        # Safety check: ensure we're not returning disease-related values
                        if plant_name.lower() not in ["disease", "diseased", "healthy"]:
                            return plant_name
                        # If somehow it is, fallback to device_id
                        return device_id
                    return device_id  # Fallback if name is empty
        
        # Not found in USER_PLANTS, return device ID
        return device_id
    except Exception:
        # On any error, return device ID as fallback
        return device_id


def _load_previous_alert_states() -> Dict[str, Dict[str, bool]]:
    """Load previous alert states from a simple in-memory cache or DynamoDB."""
    # For simplicity, we'll use a DynamoDB item to store previous states
    # Using a single item with deviceId="ALERT_STATES" and timestamp="CURRENT"
    try:
        response = table.get_item(
            Key={
                "deviceId": "ALERT_STATES",
                "timestamp": "CURRENT"
            }
        )
        if "Item" in response:
            states = response["Item"].get("states", {})
            return states if isinstance(states, dict) else {}
    except Exception:
        pass
    return {}


def _save_alert_states(states: Dict[str, Dict[str, bool]]) -> None:
    """Save current alert states for resolution detection."""
    try:
        table.put_item(
            Item={
                "deviceId": "ALERT_STATES",
                "timestamp": "CURRENT",
                "states": states,
            }
        )
    except Exception:
        # Fail silently - resolution detection is optional
        pass


def _publish_resolution(device_id: str, plant_name: str, alert_type: str, now: datetime) -> Dict[str, Any]:
    """Publish resolution notification when alert condition is cleared."""
    alert_type_labels = {
        "disease": "Disease",
        "water_tank_empty": "Water Tank Empty",
        "trends": "Unusual Trends",
    }
    
    label = alert_type_labels.get(alert_type, alert_type.replace("_", " ").title())
    subject = f"✅ Resolved: {label} - {plant_name}"
    
    body_text = f"""✅ ALERT RESOLVED

The {label.lower()} condition for your plant '{plant_name}' has been cleared.

Your plant is now back to normal operating conditions.
"""
    
    body_html = f"""
    <p><strong style="color: green; font-size: 18px;">✅ ALERT RESOLVED</strong></p>
    <p>The {label.lower()} condition for your plant <strong>{plant_name}</strong> has been cleared.</p>
    <p>Your plant is now back to normal operating conditions.</p>
    """
    
    payload = {
        "deviceId": device_id,
        "plantName": plant_name,
        "alertType": alert_type,
        "resolution": True,
        "resolvedAt": now.isoformat(),
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
    
    # Record that alert was sent
    _record_alert_sent(device_id, alert_type, now)
    
    return message




def _check_disease_label(device_id: str, window_start: datetime, window_end: datetime, plant_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        latest.get("raw", {}).get("label")
    )
    
    # If no explicit label, check binary_prediction
    if label is None:
        binary_pred = latest.get("metrics", {}).get("binary_prediction") or latest.get("raw", {}).get("binary_prediction")
        if binary_pred:
            # Convert binary_prediction to normalized label format
            # "Diseased", "diseased", "Disease" -> "disease"
            # "Healthy", "healthy" -> "healthy"
            binary_pred_str = str(binary_pred).lower()
            if binary_pred_str in ["diseased", "disease"]:
                label = "disease"
            elif binary_pred_str == "healthy":
                label = "healthy"
            else:
                # Default: if not "healthy", treat as "disease"
                label = "disease"
    
    # Normalize label to lowercase for comparison
    # Handle both "disease" and "diseased" as valid disease labels
    normalized_label = str(label).lower() if label else None
    
    # Trigger alert if label indicates disease (handles both "disease" and "diseased")
    if normalized_label and (normalized_label == "disease" or normalized_label == "diseased"):
        metrics = latest.get("metrics", {})
        score = metrics.get("diseaseRisk") or metrics.get("confidence")
        disease_score = None
        if score is not None:
            decimal_score = _to_decimal(score)
            disease_score = float(decimal_score) if decimal_score is not None else None
        
        env_averages = _compute_environment_averages(device_id, window_start, window_end)
        
        # Get plant name if not provided - ensure we always have it
        actual_plant_name = plant_name if plant_name else _get_plant_name(device_id)
        
        alert_data = {
            "label": str(label),
            "diseaseRisk": disease_score,
            "environmentAverages": env_averages,
            "plantName": actual_plant_name,  # Always include plant name
        }
        return _publish_alert(
            device_id,
            "disease_detected",
            alert_data,
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
    plant_name: Optional[str] = None,
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
        alert_data = {
            "trend": trends.get("temperature_trend"),
            "rate": trends.get("temperature_rate", 0),
            "start": trends.get("temperature_start"),
            "end": trends.get("temperature_end"),
            "period_hours": trends.get("temperature_period_hours", 0),
        }
        if plant_name:
            alert_data["plantName"] = plant_name
        alert_message = _publish_alert(
            device_id,
            "unusual_temperature_trend",
            alert_data,
            window_end,
        )
        alerts.append(alert_message)
    
    # Check for rapid humidity drop (>10% in 6 hours)
    if trends.get("humidity_trend") in ["decreasing_very_rapidly", "decreasing_rapidly"]:
        alert_data = {
            "trend": trends.get("humidity_trend"),
            "change": trends.get("humidity_change", 0),
            "start": trends.get("humidity_start"),
            "end": trends.get("humidity_end"),
            "period_hours": trends.get("humidity_period_hours", 0),
        }
        if plant_name:
            alert_data["plantName"] = plant_name
        alert_message = _publish_alert(
            device_id,
            "unusual_humidity_trend",
            alert_data,
            window_end,
        )
        alerts.append(alert_message)
    
    # Check for rapid light drop (>30% in 6 hours)
    if trends.get("light_trend") in ["decreasing_very_rapidly", "decreasing_rapidly"]:
        alert_data = {
            "trend": trends.get("light_trend"),
            "change": trends.get("light_change", 0),
            "start": trends.get("light_start"),
            "end": trends.get("light_end"),
            "period_hours": trends.get("light_period_hours", 0),
        }
        if plant_name:
            alert_data["plantName"] = plant_name
        alert_message = _publish_alert(
            device_id,
            "unusual_light_trend",
            alert_data,
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


def _check_water_tank_status(device_id: str, now: datetime, plant_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
            alert_data = {
                "status": "empty",
                "message": "Water tank is empty and requires refill",
            }
            if plant_name:
                alert_data["plantName"] = plant_name
            return _publish_alert(
                device_id,
                "water_tank_empty",
                alert_data,
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


def _should_send_alert(device_id: str, alert_type: str, now: datetime) -> bool:
    """Check if alert should be sent based on cooldown and max count."""
    try:
        # Query alert tracking records for this device and alert type
        alert_key = f"ALERT_{alert_type}_{device_id}"
        response = table.get_item(
            Key={
                "deviceId": "ALERT_TRACKING",
                "timestamp": alert_key,
            }
        )
        
        if "Item" not in response:
            # No previous alert sent - allow it
            return True
        
        item = response["Item"]
        sent_count = item.get("count", 0)
        last_sent = item.get("lastSent")
        
        # Check max count limit
        if sent_count >= MAX_ALERT_COUNT:
            return False
        
        # Check cooldown period
        if last_sent:
            try:
                # Parse ISO format timestamp
                last_sent_dt = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
                if last_sent_dt.tzinfo is None:
                    last_sent_dt = last_sent_dt.replace(tzinfo=timezone.utc)
                
                hours_since_last = (now - last_sent_dt).total_seconds() / 3600
                if hours_since_last < ALERT_COOLDOWN_HOURS:
                    # Still in cooldown period
                    return False
            except (ValueError, TypeError):
                # If parsing fails, allow the alert (better to send than miss)
                pass
        
        return True
    except Exception:
        # On any error, allow the alert (fail open)
        return True


def _record_alert_sent(device_id: str, alert_type: str, now: datetime) -> None:
    """Record that an alert was sent for tracking purposes."""
    try:
        alert_key = f"ALERT_{alert_type}_{device_id}"
        
        # Get current count
        response = table.get_item(
            Key={
                "deviceId": "ALERT_TRACKING",
                "timestamp": alert_key,
            }
        )
        
        current_count = 0
        if "Item" in response:
            current_count = response["Item"].get("count", 0)
        
        # Update or create alert tracking record
        table.put_item(
            Item={
                "deviceId": "ALERT_TRACKING",
                "timestamp": alert_key,
                "count": current_count + 1,
                "lastSent": now.isoformat(),
                "deviceId_ref": device_id,  # For easier querying
                "alertType": alert_type,
            }
        )
    except Exception:
        # Fail silently - tracking is best effort
        pass


def _publish_alert(
    device_id: str,
    alert_type: str,
    alert_data: Dict[str, Any],
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """Publish alert to SNS with different message formats based on alert type."""
    
    # Check if we should send this alert (rate limiting)
    if not _should_send_alert(device_id, alert_type, now):
        return None
    
    # Get plant name from alert_data if provided, otherwise fetch it
    plant_name = alert_data.pop("plantName", None) or _get_plant_name(device_id)
    
    if alert_type == "disease_detected":
        subject = f"⚠️ Disease Detected: {plant_name}"
        body_text = _build_disease_alert_text(plant_name, device_id, alert_data, now)
        body_html = _build_disease_alert_html(plant_name, device_id, alert_data, now)
    elif alert_type.startswith("unusual_"):
        metric_name = alert_type.replace("unusual_", "").replace("_trend", "").replace("_", " ").title()
        subject = f"🌡️ Unusual Trend Detected: {plant_name} - {metric_name}"
        body_text = _build_trend_alert_text(plant_name, device_id, alert_type, alert_data, now)
        body_html = _build_trend_alert_html(plant_name, device_id, alert_type, alert_data, now)
    elif alert_type == "water_tank_empty":
        subject = f"💧 Water Tank Empty: {plant_name}"
        body_text = _build_water_tank_alert_text(plant_name, device_id, alert_data, now)
        body_html = _build_water_tank_alert_html(plant_name, device_id, alert_data, now)
    else:
        subject = f"Alert: {plant_name}"
        body_text = f"An alert has been triggered for your plant '{plant_name}'."
        body_html = f"<p>An alert has been triggered for your plant <strong>{plant_name}</strong>.</p>"
    
    payload = {
        "deviceId": device_id,
        "plantName": plant_name,
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
    
    # Record that alert was sent
    _record_alert_sent(device_id, alert_type, now)
    
    return message


def _build_disease_alert_text(plant_name: str, device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build text body for disease detection alert."""
    lines = [
        f"⚠️ DISEASE DETECTED",
        f"",
        f"Your plant '{plant_name}' has been detected with a disease.",
    ]
    if data.get("diseaseRisk") is not None:
        confidence_pct = int(data['diseaseRisk'] * 100)
        lines.append(f"Detection confidence: {confidence_pct}%")
    lines.append("")
    lines.append("Please check your plant and consider isolating it to prevent spread to other plants.")
    return "\n".join(lines)


def _build_disease_alert_html(plant_name: str, device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build HTML body for disease detection alert."""
    parts = [
        f'<p><strong style="color: red; font-size: 18px;">⚠️ DISEASE DETECTED</strong></p>',
        f"<p>Your plant <strong>{plant_name}</strong> has been detected with a disease.</p>",
    ]
    if data.get("diseaseRisk") is not None:
        confidence_pct = int(data['diseaseRisk'] * 100)
        parts.append(f"<p><strong>Detection confidence:</strong> {confidence_pct}%</p>")
    parts.append("<p>Please check your plant and consider isolating it to prevent spread to other plants.</p>")
    return "".join(parts)




def _build_trend_alert_text(plant_name: str, device_id: str, alert_type: str, data: Dict[str, Any], now: datetime) -> str:
    """Build text body for unusual trend alert."""
    metric_name = alert_type.replace("unusual_", "").replace("_trend", "").replace("_", " ").title()
    lines = [
        f"🌡️ UNUSUAL {metric_name.upper()} TREND DETECTED",
        f"",
        f"Your plant '{plant_name}' is experiencing rapid changes in {metric_name.lower()}.",
        f"",
    ]
    
    if "temperature" in alert_type:
        start_temp = data.get('start', 0)
        end_temp = data.get('end', 0)
        lines.append(f"Temperature changed from {start_temp:.1f}°C to {end_temp:.1f}°C.")
    elif "humidity" in alert_type:
        start_humidity = data.get('start', 0)
        end_humidity = data.get('end', 0)
        change = data.get('change', 0)
        lines.append(f"Humidity changed from {start_humidity:.0f}% to {end_humidity:.0f}% ({abs(change):.0f}% change).")
    elif "light" in alert_type:
        start_light = data.get('start', 0)
        end_light = data.get('end', 0)
        change = data.get('change', 0)
        lines.append(f"Light intensity changed from {start_light:.0f} lux to {end_light:.0f} lux ({abs(change):.0f}% change).")
    
    lines.append("")
    lines.append("Please check your plant's environment and adjust conditions if needed.")
    return "\n".join(lines)


def _build_trend_alert_html(plant_name: str, device_id: str, alert_type: str, data: Dict[str, Any], now: datetime) -> str:
    """Build HTML body for unusual trend alert."""
    metric_name = alert_type.replace("unusual_", "").replace("_trend", "").replace("_", " ").title()
    parts = [
        f'<p><strong style="color: orange; font-size: 18px;">🌡️ UNUSUAL {metric_name.upper()} TREND DETECTED</strong></p>',
        f"<p>Your plant <strong>{plant_name}</strong> is experiencing rapid changes in {metric_name.lower()}.</p>",
    ]
    
    if "temperature" in alert_type:
        start_temp = data.get('start', 0)
        end_temp = data.get('end', 0)
        parts.append(f"<p><strong>Temperature changed:</strong> {start_temp:.1f}°C → {end_temp:.1f}°C</p>")
    elif "humidity" in alert_type:
        start_humidity = data.get('start', 0)
        end_humidity = data.get('end', 0)
        change = data.get('change', 0)
        parts.append(f"<p><strong>Humidity changed:</strong> {start_humidity:.0f}% → {end_humidity:.0f}% ({abs(change):.0f}% change)</p>")
    elif "light" in alert_type:
        start_light = data.get('start', 0)
        end_light = data.get('end', 0)
        change = data.get('change', 0)
        parts.append(f"<p><strong>Light intensity changed:</strong> {start_light:.0f} lux → {end_light:.0f} lux ({abs(change):.0f}% change)</p>")
    
    parts.append("<p>Please check your plant's environment and adjust conditions if needed.</p>")
    return "".join(parts)


def _build_water_tank_alert_text(plant_name: str, device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build text body for water tank empty alert."""
    lines = [
        f"💧 WATER TANK EMPTY",
        f"",
        f"The water tank for your plant '{plant_name}' is empty and needs to be refilled.",
        f"",
        f"Please refill the water tank so the automatic watering system can continue to function properly.",
    ]
    return "\n".join(lines)


def _build_water_tank_alert_html(plant_name: str, device_id: str, data: Dict[str, Any], now: datetime) -> str:
    """Build HTML body for water tank empty alert."""
    return f"""
    <p><strong style="color: red; font-size: 18px;">💧 WATER TANK EMPTY</strong></p>
    <p>The water tank for your plant <strong>{plant_name}</strong> is empty and needs to be refilled.</p>
    <p>Please refill the water tank so the automatic watering system can continue to function properly.</p>
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

