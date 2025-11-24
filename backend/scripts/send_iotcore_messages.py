#!/usr/bin/env python3
"""
Send IoT Core messages for multiple devices to create telemetry records in DynamoDB.

This script publishes messages directly to AWS IoT Core, which will trigger
the Lambda function to store records in DynamoDB.

Usage:
    python scripts/send_iotcore_messages.py

Environment variables:
    AWS_REGION - AWS region (default: ap-southeast-1)
    AWS_PROFILE - AWS profile to use (optional)
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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


def generate_telemetry_data(device_id: str, base_temp: float = 25.0) -> dict:
    """Generate realistic telemetry data for a device."""
    # Add some variation to make it realistic
    temp_variation = random.uniform(-2.0, 3.0)
    humidity_variation = random.uniform(-5.0, 5.0)
    moisture_variation = random.uniform(-0.1, 0.1)
    light_variation = random.uniform(-500, 1000)
    
    return {
        "deviceId": device_id,
        "temperatureC": round(base_temp + temp_variation, 1),
        "humidity": round(60.0 + humidity_variation, 1),
        "soilMoisture": round(0.65 + moisture_variation, 2),
        "lightLux": round(15000 + light_variation, 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
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
    
    # Define multiple devices with different characteristics
    devices = [
        {"id": "rpi-01", "base_temp": 24.0, "name": "Greenhouse Zone 1"},
        {"id": "rpi-02", "base_temp": 26.0, "name": "Greenhouse Zone 2"},
        {"id": "rpi-03", "base_temp": 23.0, "name": "Greenhouse Zone 3"},
        {"id": "sensor-01", "base_temp": 25.5, "name": "Outdoor Sensor 1"},
        {"id": "sensor-02", "base_temp": 22.0, "name": "Indoor Sensor 1"},
    ]
    
    print(f"\n🚀 Sending telemetry messages for {len(devices)} devices...\n")
    
    # Send messages for each device
    for device in devices:
        device_id = device["id"]
        print(f"📤 Device: {device_id} ({device['name']})")
        
        # Send 2-3 messages per device with slight variations
        num_messages = random.randint(2, 3)
        for i in range(num_messages):
            # Stagger messages slightly
            if i > 0:
                time.sleep(0.5)
            
            telemetry = generate_telemetry_data(device_id, device["base_temp"])
            publish_telemetry_message(iot_data_client, device_id, telemetry)
            
            # Print the data being sent
            print(f"   └─ {telemetry}")
    
    print(f"\n✅ Successfully sent messages for {len(devices)} devices!")
    print(f"📊 Check your DynamoDB table to see the new records.")
    print(f"🌐 You can also view them via the API: GET /plants")


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

