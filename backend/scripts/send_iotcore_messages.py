#!/usr/bin/env python3
"""
Send IoT Core messages for testing different metric threshold scenarios.

This script publishes messages directly to AWS IoT Core, which will trigger
the Lambda function to store records in DynamoDB.

Usage:
    # Normal telemetry
    python scripts/send_iotcore_messages.py
    
    # Test low temperature threshold
    python scripts/send_iotcore_messages.py --low-temperature
    
    # Test low soil moisture threshold
    python scripts/send_iotcore_messages.py --low-moisture
    
    # Test water tank empty (sends waterTankFilled=0, which gets converted to waterTankEmpty=1)
    python scripts/send_iotcore_messages.py --water-tank-empty
    
    # Test multiple scenarios
    python scripts/send_iotcore_messages.py --low-temperature --low-humidity --device-id rpi-01 --count 5

Flags:
    --low-temperature    Send temperature below threshold (~15°C)
    --low-humidity       Send humidity below threshold (~30%)
    --low-moisture       Send soil moisture below threshold (~0.2)
    --low-light          Send light below threshold (~5000 lux)
    --high-temperature   Send high temperature for trend testing (~35°C)
    --high-humidity      Send high humidity for trend testing (~90%)
    --water-tank-empty   Send waterTankFilled=0 (tank is empty, matches real device behavior)
    --device-id ID       Specify device ID (default: rpi-01)
    --count N            Number of messages to send (default: 1)

Environment variables:
    AWS_REGION - AWS region (default: ap-southeast-1)
    AWS_PROFILE - AWS profile to use (optional)
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3

# Add parent directory to path for imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def get_iot_endpoint(region: str) -> str:
    """Get the IoT Core endpoint URL for the region."""
    iot_client = boto3.client("iot", region_name=region)
    response = iot_client.describe_endpoint(endpointType="iot:Data-ATS")
    return response["endpointAddress"]


def publish_telemetry_message(
    iot_data_client, device_id: str, telemetry_data: dict
) -> None:
    """Publish a telemetry message to IoT Core."""
    topic = f"leaf/telemetry/{device_id}/data"
    payload = json.dumps(telemetry_data)
    
    try:
        response = iot_data_client.publish(
            topic=topic,
            qos=1,
            payload=payload,
        )
        print(f"✅ Published to {topic}: {telemetry_data.get('deviceId')}")
        return response
    except Exception as e:
        print(f"❌ Failed to publish to {topic}: {e}")
        raise


def generate_telemetry_data(
    device_id: str,
    base_temp: float = 25.0,
    low_temp: bool = False,
    low_humidity: bool = False,
    low_moisture: bool = False,
    low_light: bool = False,
    high_temp: bool = False,
    high_humidity: bool = False,
    water_tank_empty: bool = False,
    set_threshold: Optional[str] = None,
) -> dict:
    """Generate telemetry data for a device with optional threshold testing flags."""
    data = {
        "deviceId": device_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Temperature
    if low_temp:
        # Below threshold: ~15°C (typical threshold might be 18-20°C)
        data["temperatureC"] = round(random.uniform(12.0, 18.0), 1)
    elif high_temp:
        # High temperature for trend testing: ~35°C
        data["temperatureC"] = round(50.0, 1)
    else:
        # Normal temperature with variation
        temp_variation = random.uniform(-2.0, 3.0)
        data["temperatureC"] = round(base_temp + temp_variation, 1)
    
    # Humidity
    if low_humidity:
        # Below threshold: ~30% (typical threshold might be 40-50%)
        data["humidity"] = round(random.uniform(25.0, 35.0), 1)
    elif high_humidity:
        # High humidity for trend testing: ~90%
        data["humidity"] = round(random.uniform(85.0, 95.0), 1)
    else:
        # Normal humidity with variation
        humidity_variation = random.uniform(-5.0, 5.0)
        data["humidity"] = round(60.0 + humidity_variation, 1)
    
    # Soil Moisture
    if low_moisture:
        # Below threshold: ~0.2 (typical threshold might be 0.3-0.4)
        data["soilMoisture"] = round(random.uniform(0.15, 0.25), 2)
    else:
        # Normal moisture with variation
        moisture_variation = random.uniform(-0.1, 0.1)
        data["soilMoisture"] = round(0.65 + moisture_variation, 2)
    
    # Light
    if low_light:
        # Below threshold: ~5000 lux (typical threshold might be 8000-10000 lux)
        data["lightLux"] = round(random.uniform(3000, 6000), 0)
    else:
        # Normal light with variation
        light_variation = random.uniform(-500, 1000)
        data["lightLux"] = round(15000 + light_variation, 0)
    
    # Water Tank Status
    # Note: Real device sends waterTankFilled (1 = filled, 0 = not filled)
    # The backend converts this to waterTankEmpty (1 = empty, 0 = has water)
    if water_tank_empty:
        data["waterTankFilled"] = 0  # Tank is empty (not filled)
    else:
        data["waterTankFilled"] = 1  # Tank has water (filled)
    
    # Set threshold if specified (format: "metric=value", e.g., "temperatureC=33")
    if set_threshold:
        try:
            metric, value_str = set_threshold.split("=", 1)
            value = float(value_str)
            
            # Map metric names to threshold keys (as stored in DynamoDB)
            threshold_key_map = {
                "temperatureC": "temperatureCThreshold",
                "soilMoisture": "soilMoistureThreshold",
                "lightLux": "lightLuxThreshold",
            }
            
            threshold_key = threshold_key_map.get(metric)
            if threshold_key:
                # Store threshold in the format expected by stream_processor
                # stream_processor's _persist_device_config stores threshold dict as-is
                # The threshold dict will be stored in DynamoDB config item
                data["threshold"] = {
                    threshold_key: value
                }
                print(f"   📊 Will set {metric} threshold to {value} ({threshold_key})")
            else:
                raise ValueError(f"Unknown metric '{metric}'. Supported: {list(threshold_key_map.keys())}")
        except (ValueError, AttributeError) as e:
            print(f"   ⚠️  Invalid threshold format '{set_threshold}': {e}")
            print(f"   Expected format: 'metric=value' (e.g., 'temperatureC=33')")
    
    return data


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Send IoT Core messages for testing different metric threshold scenarios.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Normal telemetry
  python scripts/send_iotcore_messages.py
  
  # Test low temperature threshold
  python scripts/send_iotcore_messages.py --low-temperature
  
  # Test low soil moisture threshold
  python scripts/send_iotcore_messages.py --low-moisture
  
  # Test water tank empty
  python scripts/send_iotcore_messages.py --water-tank-empty
  
  # Test multiple scenarios with multiple messages
  python scripts/send_iotcore_messages.py --low-temperature --low-humidity --device-id rpi-01 --count 5
        """,
    )
    
    # Threshold testing flags
    parser.add_argument(
        "--low-temperature",
        action="store_true",
        help="Send temperature below threshold (~15°C)",
    )
    parser.add_argument(
        "--low-humidity",
        action="store_true",
        help="Send humidity below threshold (~30%%)",
    )
    parser.add_argument(
        "--low-moisture",
        action="store_true",
        help="Send soil moisture below threshold (~0.2)",
    )
    parser.add_argument(
        "--low-light",
        action="store_true",
        help="Send light below threshold (~5000 lux)",
    )
    parser.add_argument(
        "--high-temperature",
        action="store_true",
        help="Send high temperature for trend testing (~35°C)",
    )
    parser.add_argument(
        "--high-humidity",
        action="store_true",
        help="Send high humidity for trend testing (~90%%)",
    )
    parser.add_argument(
        "--water-tank-empty",
        action="store_true",
        help="Send waterTankEmpty=1 (tank is empty)",
    )
    parser.add_argument(
        "--set-threshold",
        type=str,
        help="Set threshold for a metric. Format: 'metric=value' (e.g., 'temperatureC=33')",
    )
    
    # Device and count options
    parser.add_argument(
        "--device-id",
        type=str,
        default="rpi-01",
        help="Device ID to send messages for (default: rpi-01)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of messages to send (default: 1)",
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    region = os.getenv("AWS_REGION", "ap-southeast-1")
    profile = os.getenv("AWS_PROFILE")
    
    # Create IoT Data client
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    iot_data_client = session.client("iot-data", region_name=region)
    
    # Get IoT endpoint (for verification)
    try:
        endpoint = get_iot_endpoint(region)
        print(f"📡 IoT Core Endpoint: {endpoint}")
    except Exception as e:
        print(f"⚠️  Could not get IoT endpoint (may not be needed): {e}")
    
    # Build scenario description
    scenarios = []
    if args.low_temperature:
        scenarios.append("LOW TEMPERATURE")
    if args.low_humidity:
        scenarios.append("LOW HUMIDITY")
    if args.low_moisture:
        scenarios.append("LOW MOISTURE")
    if args.low_light:
        scenarios.append("LOW LIGHT")
    if args.high_temperature:
        scenarios.append("HIGH TEMPERATURE (trend)")
    if args.high_humidity:
        scenarios.append("HIGH HUMIDITY (trend)")
    if args.water_tank_empty:
        scenarios.append("WATER TANK EMPTY")
    
    scenario_desc = " | ".join(scenarios) if scenarios else "NORMAL"
    
    print(f"\n🚀 Sending {args.count} message(s) for device: {args.device_id}")
    print(f"📋 Scenario: {scenario_desc}\n")
    
    # Send messages
    for i in range(args.count):
        if i > 0:
            time.sleep(0.5)  # Stagger messages slightly
        
        telemetry = generate_telemetry_data(
            device_id=args.device_id,
            base_temp=25.0,
            low_temp=args.low_temperature,
            low_humidity=args.low_humidity,
            low_moisture=args.low_moisture,
            low_light=args.low_light,
            high_temp=args.high_temperature,
            high_humidity=args.high_humidity,
            water_tank_empty=args.water_tank_empty,
            set_threshold=args.set_threshold,
        )
        
        publish_telemetry_message(iot_data_client, args.device_id, telemetry)
        print(f"   [{i+1}/{args.count}] {telemetry}")
    
    print(f"\n✅ Successfully sent {args.count} message(s)!")
    print(f"📊 Check your DynamoDB table to see the new records.")
    print(f"🌐 You can also view them via the API: GET /plants")
    
    if scenarios:
        print(f"\n⚠️  Note: These messages are designed to trigger threshold alerts.")
        print(f"   Check your metrics evaluator Lambda and SNS notifications.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

