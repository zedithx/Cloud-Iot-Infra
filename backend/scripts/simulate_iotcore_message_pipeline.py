"""
Simulate the IoT ingestion and metrics evaluation pipeline locally using moto.

Steps performed:
1. Create in-memory DynamoDB/SNS/S3 services.
2. Invoke the telemetry ingestion Lambda with mocked IoT Core messages.
3. Invoke the batch results processor Lambda with mocked S3 events (disease risk output).
4. Run the metrics evaluator Lambda to aggregate metrics and publish alerts.
5. Print the DynamoDB contents and SNS alert payloads.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
from moto import mock_dynamodb, mock_s3, mock_sns

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _now_iso(offset_minutes: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return dt.isoformat()


def main() -> None:
    with mock_dynamodb(), mock_sns(), mock_s3():
        _simulate()


def _simulate() -> None:
    region = "us-east-1"
    os.environ["AWS_DEFAULT_REGION"] = region

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.create_table(
        TableName="simulated-telemetry",
        KeySchema=[
            {"AttributeName": "deviceId", "KeyType": "HASH"},
            {"AttributeName": "timestamp", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "deviceId", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()

    sns_client = boto3.client("sns", region_name=region)
    topic_arn = sns_client.create_topic(Name="simulated-alerts")["TopicArn"]

    s3_client = boto3.client("s3", region_name=region)
    results_bucket = "simulated-batch-results"
    if region == "us-east-1":
        s3_client.create_bucket(Bucket=results_bucket)
    else:
        s3_client.create_bucket(
            Bucket=results_bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )

    # Set shared environment variables for the Lambdas.
    os.environ["DYNAMO_TABLE_NAME"] = table.name
    os.environ["SNS_TOPIC_ARN"] = topic_arn
    os.environ["DEFAULT_THRESHOLD"] = "0.5"
    os.environ["ENV_WINDOW_MINUTES"] = "30"

    telemetry_ingestor = _import_handler("runtime.lambdas.stream_processor.handler")
    results_processor = _import_handler("runtime.lambdas.batch_results_processor.handler")
    metrics_evaluator = _import_handler("runtime.lambdas.metrics_evaluator.handler")

    # 1. Send mocked IoT telemetry readings.
    telemetry_events = [
        {
            "deviceId": "device-1",
            "temperatureC": "26.5",
            "humidity": "61.0",
            "soilMoisture": "0.32",
            "lightLux": "1200",
            "timestamp": _now_iso(-20),
        },
        {
            "deviceId": "device-1",
            "temperatureC": "27.1",
            "humidity": "63.5",
            "soilMoisture": "0.31",
            "lightLux": "1150",
            "timestamp": _now_iso(-10),
        },
    ]
    telemetry_event_wrapper = {
        "Records": [{"body": json.dumps(payload)} for payload in telemetry_events]
    }
    telemetry_response = telemetry_ingestor(telemetry_event_wrapper, None)

    # 2. Simulate a batch transform output arriving in S3.
    disease_result_key = "dev/2025-01-01/results.jsonl"
    result_payload = {"deviceId": "device-1", "diseaseRisk": "0.92"}
    s3_client.put_object(
        Bucket=results_bucket,
        Key=disease_result_key,
        Body=json.dumps(result_payload).encode("utf-8"),
    )
    s3_event = {
        "Records": [
            {"s3": {"bucket": {"name": results_bucket}, "object": {"key": disease_result_key}}}
        ]
    }
    results_response = results_processor(s3_event, None)

    # 3. Run the metrics evaluator to aggregate readings and trigger alerts.
    metrics_response = metrics_evaluator({}, None)

    # Inspect DynamoDB contents.
    stored_items = table.scan()["Items"]
    stored_items.sort(key=lambda item: item["timestamp"])

    # Retrieve published SNS messages from moto backend.
    alerts_sent = _extract_published_messages(topic_arn)

    print("Telemetry ingestion response:", telemetry_response)
    print("Batch results response:", results_response)
    print("Metrics evaluator response:", metrics_response)
    print("\nStored DynamoDB items:")
    for item in stored_items:
        # Convert Decimal to float for better JSON display
        def decimal_to_float(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [decimal_to_float(v) for v in obj]
            return obj
        
        item_display = decimal_to_float(item)
        print(json.dumps(item_display, default=str, indent=2))
        
        # Also show metrics field specifically
        if "metrics" in item:
            print(f"  → Metrics field type: {type(item['metrics'])}")
            if isinstance(item["metrics"], dict):
                for key, value in item["metrics"].items():
                    print(f"    - {key}: {value} (type: {type(value).__name__})")

    if alerts_sent:
        print("\nSNS alerts payloads:")
        for message in alerts_sent:
            print(json.dumps(message, indent=2))
    else:
        print("\nNo SNS alerts captured (disease risk may be below threshold).")


def _import_handler(module_path: str):
    from importlib import import_module

    module = import_module(module_path)
    return getattr(module, "lambda_handler")


def _extract_published_messages(topic_arn: str) -> list[dict[str, Any]]:
    """Retrieve published SNS messages from moto backend."""
    from moto.sns.models import sns_backends  # type: ignore

    region = topic_arn.split(":")[3]
    account_id = topic_arn.split(":")[4]
    backend = sns_backends[account_id][region]
    topic = backend.topics.get(topic_arn)
    if not topic:
        return []
    messages: list[dict[str, Any]] = []
    for notification in topic.sent_notifications:
        if isinstance(notification, tuple):
            message = notification[1]
        else:
            message = getattr(notification, "message", str(notification))
        try:
            messages.append(json.loads(message))
        except json.JSONDecodeError:
            messages.append({"message": message})
    return messages


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


if __name__ == "__main__":
    main()

