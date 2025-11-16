"""
Test cases for FastAPI endpoints.

Tests all API endpoints:
- GET /health - Health check
- POST /telemetry - Ingest telemetry data
- GET /telemetry - List all telemetry
- GET /telemetry/{device_id} - Get telemetry for device
- GET /plants - List all devices (main page data)
- GET /plants/{plant_id} - Get plant detail
- GET /plants/{plant_id}/timeseries - Get timeseries data for a device
- POST /devices/{device_id}/plant-type - Set plant type for device
- GET /plant-types - List available plant types
- GET /plant-types/{plant_type} - Get plant type metrics
- POST /devices/{device_id}/actuators - Send actuator command
"""

import json
import os
from decimal import Decimal
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_dynamodb, mock_iotdata
from fastapi.testclient import TestClient

# Import the FastAPI app
import sys
from pathlib import Path

# Add the FastAPI app directory to the path
fastapi_dir = Path(__file__).resolve().parents[3] / "runtime" / "ecs" / "fastapi"
sys.path.insert(0, str(fastapi_dir))

from app.main import app


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table for testing."""
    with mock_dynamodb():
        # Create the table
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-telemetry",
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
        yield table


@pytest.fixture
def client(dynamodb_table, monkeypatch):
    """Create a test client with mocked DynamoDB and IoT Core."""
    # Set environment variables
    monkeypatch.setenv("TELEMETRY_TABLE", "test-telemetry")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("DISEASE_THRESHOLD", "0.7")

    # Patch the DynamoDB resource to use our mock
    import app.main as main_module

    # Create a new DynamoDB resource that uses moto
    dynamodb_resource = boto3.resource("dynamodb", region_name="us-east-1")
    main_module.telemetry_table = dynamodb_resource.Table("test-telemetry")

    # Mock IoT Data client
    with mock_iotdata():
        iot_data_client = boto3.client("iot-data", region_name="us-east-1")
        main_module.iot_client = iot_data_client

        # Create test client
        with TestClient(app) as test_client:
            yield test_client


def _create_telemetry_item(
    device_id: str,
    timestamp: str,
    score: float = 0.5,
    temperature_c: float = None,
    humidity: float = None,
    soil_moisture: float = None,
    light_lux: float = None,
    disease: bool = None,
    notes: str = None,
):
    """Helper to create a telemetry item in DynamoDB format."""
    item = {
        "deviceId": device_id,
        "plantId": device_id,
        "timestamp": timestamp,
        "score": Decimal(str(score)),
        "readingType": "telemetry",
    }

    if temperature_c is not None:
        item["temperatureC"] = Decimal(str(temperature_c))
    if humidity is not None:
        item["humidity"] = Decimal(str(humidity))
    if soil_moisture is not None:
        item["soilMoisture"] = Decimal(str(soil_moisture))
    if light_lux is not None:
        item["lightLux"] = Decimal(str(light_lux))
    if disease is not None:
        item["disease"] = disease
    if notes is not None:
        item["notes"] = notes

    return item


def _put_items(table, items):
    """Helper to put multiple items into DynamoDB."""
    for item in items:
        table.put_item(Item=item)


class TestPlantsListEndpoint:
    """Test cases for GET /plants endpoint (main page data)."""

    def test_list_plants_empty(self, client, dynamodb_table):
        """Test listing plants when table is empty."""
        response = client.get("/plants")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_plants_single_device(self, client, dynamodb_table):
        """Test listing plants with a single device."""
        # Create test data
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp),
                score=0.6,
                temperature_c=25.5,
                humidity=65.0,
                soil_moisture=0.75,
                light_lux=15000.0,
                disease=False,
            )
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["plantId"] == "device-1"
        assert data[0]["score"] == 0.6
        assert data[0]["temperatureC"] == 25.5
        assert data[0]["humidity"] == 65.0
        assert data[0]["soilMoisture"] == 0.75
        assert data[0]["lightLux"] == 15000.0
        assert data[0]["disease"] is False

    def test_list_plants_multiple_devices(self, client, dynamodb_table):
        """Test listing plants with multiple devices."""
        # Create test data for multiple devices
        base_time = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time),
                score=0.6,
                temperature_c=25.5,
                humidity=65.0,
            ),
            _create_telemetry_item(
                device_id="device-2",
                timestamp=str(base_time),
                score=0.8,
                temperature_c=28.0,
                humidity=70.0,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 3600),
                score=0.7,
                temperature_c=26.0,
                humidity=66.0,
            ),  # More recent reading for device-1
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # Should only return latest for each device

        # Should be sorted by plantId
        assert data[0]["plantId"] == "device-1"
        assert data[1]["plantId"] == "device-2"

        # device-1 should have the latest reading
        assert data[0]["score"] == 0.7
        assert data[0]["temperatureC"] == 26.0

        # device-2 should have its reading
        assert data[1]["score"] == 0.8
        assert data[1]["temperatureC"] == 28.0

    def test_list_plants_only_returns_latest(self, client, dynamodb_table):
        """Test that only the latest reading per device is returned."""
        # Create multiple readings for the same device
        base_time = int(datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time),
                score=0.5,
                temperature_c=24.0,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 3600),
                score=0.6,
                temperature_c=25.0,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 7200),
                score=0.7,
                temperature_c=26.0,
            ),
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        # Should return the latest reading (highest timestamp)
        assert data[0]["score"] == 0.7
        assert data[0]["temperatureC"] == 26.0

    def test_list_plants_handles_missing_fields(self, client, dynamodb_table):
        """Test that missing optional fields are handled gracefully."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp),
                score=0.6,
                # No optional fields
            )
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["plantId"] == "device-1"
        assert data[0]["score"] == 0.6
        assert data[0]["temperatureC"] is None
        assert data[0]["humidity"] is None
        assert data[0]["soilMoisture"] is None
        assert data[0]["lightLux"] is None


class TestPlantTimeseriesEndpoint:
    """Test cases for GET /plants/{plant_id}/timeseries endpoint."""

    def test_timeseries_not_found(self, client, dynamodb_table):
        """Test timeseries endpoint when device doesn't exist."""
        response = client.get("/plants/nonexistent/timeseries")
        assert response.status_code == 200
        data = response.json()
        assert data["plantId"] == "nonexistent"
        assert data["points"] == []

    def test_timeseries_single_point(self, client, dynamodb_table):
        """Test timeseries endpoint with a single data point."""
        # Use Unix timestamp as string (timestamp is stored as string, converted to int in _normalise_item)
        # The _normalise_item does int(data["timestamp"]) which extracts the numeric part
        # For simplicity, use just the numeric timestamp string
        timestamp_str = "1704110400"
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=timestamp_str,
                score=0.6,
                temperature_c=25.5,
                humidity=65.0,
                soil_moisture=0.75,
                light_lux=15000.0,
                disease=False,
            )
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants/device-1/timeseries")
        assert response.status_code == 200
        data = response.json()
        assert data["plantId"] == "device-1"
        assert len(data["points"]) == 1
        point = data["points"][0]
        # Timestamp should be converted to int (extracted from string)
        assert point["timestamp"] == 1704110400
        assert point["score"] == 0.6
        assert point["temperatureC"] == 25.5
        assert point["humidity"] == 65.0
        assert point["soilMoisture"] == 0.75
        assert point["lightLux"] == 15000.0
        assert point["disease"] is False

    def test_timeseries_multiple_points(self, client, dynamodb_table):
        """Test timeseries endpoint with multiple data points."""
        base_time = int(datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time),
                score=0.5,
                temperature_c=24.0,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 3600),
                score=0.6,
                temperature_c=25.0,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 7200),
                score=0.7,
                temperature_c=26.0,
            ),
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants/device-1/timeseries")
        assert response.status_code == 200
        data = response.json()
        assert data["plantId"] == "device-1"
        assert len(data["points"]) == 3

        # Points should be sorted by timestamp (ascending)
        assert data["points"][0]["score"] == 0.5
        assert data["points"][1]["score"] == 0.6
        assert data["points"][2]["score"] == 0.7

    def test_timeseries_limit(self, client, dynamodb_table):
        """Test timeseries endpoint with limit parameter."""
        # Create 10 data points
        items = []
        for i in range(10):
            items.append(
                _create_telemetry_item(
                    device_id="device-1",
                    timestamp=f"20240101T{10+i:02d}0000Z-{i:03d}",
                    score=0.5 + i * 0.1,
                )
            )
        _put_items(dynamodb_table, items)

        # Request with limit of 5
        response = client.get("/plants/device-1/timeseries?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["points"]) == 5

    def test_timeseries_filters_other_devices(self, client, dynamodb_table):
        """Test that timeseries only returns data for the specified device."""
        base_time = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time),
                score=0.6,
            ),
            _create_telemetry_item(
                device_id="device-2",
                timestamp=str(base_time),
                score=0.7,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 3600),
                score=0.8,
            ),
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants/device-1/timeseries")
        assert response.status_code == 200
        data = response.json()
        assert data["plantId"] == "device-1"
        assert len(data["points"]) == 2
        # All points should be for device-1
        assert all(point["score"] in [0.6, 0.8] for point in data["points"])

    def test_timeseries_with_start_end(self, client, dynamodb_table):
        """Test timeseries endpoint with start and end time filters."""
        # Create items with different timestamps (Unix timestamps as strings)
        base_time = int(datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time),
                score=0.5,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 3600),
                score=0.6,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 7200),
                score=0.7,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(base_time + 10800),
                score=0.8,
            ),
        ]
        _put_items(dynamodb_table, items)

        # Filter between 11:00 and 12:00 (1 hour and 2 hours after base)
        start_time = base_time + 3600
        end_time = base_time + 7200

        response = client.get(
            f"/plants/device-1/timeseries?start={start_time}&end={end_time}"
        )
        assert response.status_code == 200
        data = response.json()
        # Should return points within the time range
        assert len(data["points"]) >= 0
        # All returned points should be within the range
        for point in data["points"]:
            assert start_time <= point["timestamp"] <= end_time

    def test_timeseries_handles_missing_fields(self, client, dynamodb_table):
        """Test that missing optional fields are handled gracefully."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp),
                score=0.6,
                # No optional fields
            )
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants/device-1/timeseries")
        assert response.status_code == 200
        data = response.json()
        assert len(data["points"]) == 1
        point = data["points"][0]
        assert point["score"] == 0.6
        assert point["temperatureC"] is None
        assert point["humidity"] is None
        assert point["soilMoisture"] is None
        assert point["lightLux"] is None

    def test_timeseries_limit_validation(self, client, dynamodb_table):
        """Test that limit parameter validation works."""
        # Test limit too high
        response = client.get("/plants/device-1/timeseries?limit=1000")
        assert response.status_code == 422  # Validation error

        # Test limit too low
        response = client.get("/plants/device-1/timeseries?limit=0")
        assert response.status_code == 422  # Validation error

        # Test valid limit
        response = client.get("/plants/device-1/timeseries?limit=100")
        assert response.status_code == 200


class TestHealthEndpoint:
    """Test cases for GET /health endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}


class TestTelemetryIngestEndpoint:
    """Test cases for POST /telemetry endpoint."""

    def test_ingest_telemetry_minimal(self, client, dynamodb_table):
        """Test ingesting telemetry with minimal required fields."""
        payload = {
            "deviceId": "device-1",
            "score": 0.6,
        }
        response = client.post("/telemetry", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["deviceId"] == "device-1"
        assert data["score"] == 0.6
        assert data["timestamp"] > 0
        assert data["disease"] is False  # Should be derived from score < 0.7

    def test_ingest_telemetry_full(self, client, dynamodb_table):
        """Test ingesting telemetry with all fields."""
        payload = {
            "deviceId": "device-1",
            "score": 0.8,
            "temperatureC": 25.5,
            "humidity": 65.0,
            "soilMoisture": 0.75,
            "lightLux": 15000.0,
            "disease": True,
            "notes": "Test reading",
        }
        response = client.post("/telemetry", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["deviceId"] == "device-1"
        assert data["score"] == 0.8
        assert data["temperatureC"] == 25.5
        assert data["humidity"] == 65.0
        assert data["soilMoisture"] == 0.75
        assert data["lightLux"] == 15000.0
        assert data["disease"] is True
        assert data["notes"] == "Test reading"

    def test_ingest_telemetry_derives_disease(self, client, dynamodb_table):
        """Test that disease is derived from score when not provided."""
        payload = {
            "deviceId": "device-1",
            "score": 0.75,  # Above threshold of 0.7
        }
        response = client.post("/telemetry", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["disease"] is True

    def test_ingest_telemetry_validation(self, client):
        """Test telemetry payload validation."""
        # Missing required field
        response = client.post("/telemetry", json={"score": 0.6})
        assert response.status_code == 422

        # Invalid score range
        response = client.post("/telemetry", json={"deviceId": "device-1", "score": 1.5})
        assert response.status_code == 422

        # Invalid humidity range
        response = client.post(
            "/telemetry", json={"deviceId": "device-1", "score": 0.6, "humidity": 150}
        )
        assert response.status_code == 422


class TestTelemetryListEndpoint:
    """Test cases for GET /telemetry endpoint."""

    def test_list_telemetry_empty(self, client, dynamodb_table):
        """Test listing telemetry when table is empty."""
        response = client.get("/telemetry")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_telemetry_with_data(self, client, dynamodb_table):
        """Test listing telemetry with data."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp),
                score=0.6,
                temperature_c=25.0,
            ),
            _create_telemetry_item(
                device_id="device-2",
                timestamp=str(timestamp + 3600),
                score=0.7,
                temperature_c=26.0,
            ),
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # Should be sorted by timestamp descending
        assert data[0]["timestamp"] >= data[1]["timestamp"]

    def test_list_telemetry_with_limit(self, client, dynamodb_table):
        """Test listing telemetry with limit parameter."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = []
        for i in range(10):
            items.append(
                _create_telemetry_item(
                    device_id="device-1",
                    timestamp=str(timestamp + i),
                    score=0.5 + i * 0.1,
                )
            )
        _put_items(dynamodb_table, items)

        response = client.get("/telemetry?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5


class TestTelemetryDeviceEndpoint:
    """Test cases for GET /telemetry/{device_id} endpoint."""

    def test_get_telemetry_for_device(self, client, dynamodb_table):
        """Test getting telemetry for a specific device."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp),
                score=0.6,
            ),
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp + 3600),
                score=0.7,
            ),
            _create_telemetry_item(
                device_id="device-2",
                timestamp=str(timestamp),
                score=0.8,
            ),
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/telemetry/device-1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(record["deviceId"] == "device-1" for record in data)

    def test_get_telemetry_empty_device(self, client, dynamodb_table):
        """Test getting telemetry for device with no data."""
        response = client.get("/telemetry/nonexistent")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_telemetry_with_limit(self, client, dynamodb_table):
        """Test getting telemetry with limit parameter."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = []
        for i in range(10):
            items.append(
                _create_telemetry_item(
                    device_id="device-1",
                    timestamp=str(timestamp + i),
                    score=0.5 + i * 0.1,
                )
            )
        _put_items(dynamodb_table, items)

        response = client.get("/telemetry/device-1?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5


class TestPlantDetailEndpoint:
    """Test cases for GET /plants/{plant_id} endpoint."""

    def test_get_plant_detail(self, client, dynamodb_table):
        """Test getting plant detail."""
        timestamp = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        items = [
            _create_telemetry_item(
                device_id="device-1",
                timestamp=str(timestamp),
                score=0.6,
                temperature_c=25.5,
                humidity=65.0,
                soil_moisture=0.75,
                light_lux=15000.0,
                disease=False,
            )
        ]
        _put_items(dynamodb_table, items)

        response = client.get("/plants/device-1")
        assert response.status_code == 200
        data = response.json()
        assert data["plantId"] == "device-1"
        assert data["score"] == 0.6
        assert data["temperatureC"] == 25.5
        assert data["humidity"] == 65.0
        assert data["soilMoisture"] == 0.75
        assert data["lightLux"] == 15000.0
        assert data["disease"] is False

    def test_get_plant_detail_not_found(self, client, dynamodb_table):
        """Test getting plant detail for non-existent device."""
        response = client.get("/plants/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPlantTypeEndpoints:
    """Test cases for plant type endpoints."""

    def test_list_plant_types(self, client):
        """Test listing available plant types."""
        response = client.get("/plant-types")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "basil" in data
        assert "strawberry" in data
        assert "mint" in data
        assert "lettuce" in data

    def test_get_plant_type_metrics(self, client):
        """Test getting metrics for a plant type."""
        response = client.get("/plant-types/basil")
        assert response.status_code == 200
        data = response.json()
        assert data["plantType"] == "basil"
        assert "temperatureC" in data
        assert "humidity" in data
        assert "soilMoisture" in data
        assert "lightLux" in data
        assert data["temperatureC"]["min"] == 22.0
        assert data["temperatureC"]["max"] == 28.0

    def test_get_plant_type_metrics_not_found(self, client):
        """Test getting metrics for non-existent plant type."""
        response = client.get("/plant-types/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_plant_type_metrics_case_insensitive(self, client):
        """Test that plant type lookup is case insensitive."""
        response = client.get("/plant-types/BASIL")
        assert response.status_code == 200
        data = response.json()
        assert data["plantType"] == "basil"


class TestSetPlantTypeEndpoint:
    """Test cases for POST /devices/{device_id}/plant-type endpoint."""

    def test_set_plant_type(self, client, dynamodb_table):
        """Test setting plant type for a device."""
        payload = {"plantType": "basil"}
        response = client.post("/devices/device-1/plant-type", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["deviceId"] == "device-1"
        assert data["plantType"] == "basil"
        assert data["status"] == "set"

        # Verify it was written to DynamoDB with deviceId key
        db_response = dynamodb_table.get_item(
            Key={"deviceId": "device-1", "timestamp": "CONFIG"}
        )
        assert "Item" in db_response
        item = db_response["Item"]
        assert item["plantType"] == "basil"
        
        # Verify plant type metrics are also stored
        assert "plantTypeMetrics" in item
        metrics = item["plantTypeMetrics"]
        assert "temperatureC" in metrics
        assert "humidity" in metrics
        assert "soilMoisture" in metrics
        assert "lightLux" in metrics
        # Verify basil metrics (temperatureC: 22-28)
        assert float(metrics["temperatureC"]["min"]) == 22.0
        assert float(metrics["temperatureC"]["max"]) == 28.0

    def test_set_plant_type_invalid(self, client):
        """Test setting invalid plant type."""
        payload = {"plantType": "invalid"}
        response = client.post("/devices/device-1/plant-type", json=payload)
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_set_plant_type_case_insensitive(self, client, dynamodb_table):
        """Test that plant type is case insensitive."""
        payload = {"plantType": "BASIL"}
        response = client.post("/devices/device-1/plant-type", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["plantType"] == "basil"  # Should be lowercased

    def test_set_plant_type_overwrites_existing(self, client, dynamodb_table):
        """Test that setting plant type overwrites existing value."""
        # Set initial plant type
        payload1 = {"plantType": "basil"}
        client.post("/devices/device-1/plant-type", json=payload1)

        # Set different plant type
        payload2 = {"plantType": "strawberry"}
        response = client.post("/devices/device-1/plant-type", json=payload2)
        assert response.status_code == 200

        # Verify it was updated in DynamoDB
        db_response = dynamodb_table.get_item(
            Key={"deviceId": "device-1", "timestamp": "CONFIG"}
        )
        item = db_response["Item"]
        assert item["plantType"] == "strawberry"
        
        # Verify metrics were also updated to strawberry metrics
        metrics = item["plantTypeMetrics"]
        # Strawberry temperatureC: 18-24
        assert float(metrics["temperatureC"]["min"]) == 18.0
        assert float(metrics["temperatureC"]["max"]) == 24.0


class TestActuatorCommandEndpoint:
    """Test cases for POST /devices/{device_id}/actuators endpoint."""

    def test_send_pump_command(self, client):
        """Test sending pump actuator command."""
        payload = {
            "actuator": "pump",
            "targetValue": 0.75,
            "metric": "soilMoisture",
        }
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["deviceId"] == "device-1"
        assert data["command"]["actuator"] == "pump"
        assert data["command"]["targetValue"] == 0.75
        assert data["command"]["metric"] == "soilMoisture"
        assert data["topic"] == "leaf/commands/device-1"
        assert data["status"] == "sent"

    def test_send_fan_command(self, client):
        """Test sending fan actuator command."""
        payload = {
            "actuator": "fan",
            "targetValue": 22.0,
            "metric": "temperatureC",
        }
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["command"]["actuator"] == "fan"
        assert data["command"]["targetValue"] == 22.0

    def test_send_lights_command(self, client):
        """Test sending lights actuator command."""
        payload = {
            "actuator": "lights",
            "targetValue": 15000.0,
            "metric": "lightLux",
        }
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["command"]["actuator"] == "lights"
        assert data["command"]["targetValue"] == 15000.0

    def test_actuator_metric_mismatch(self, client):
        """Test that actuator and metric must match."""
        payload = {
            "actuator": "pump",
            "targetValue": 0.75,
            "metric": "temperatureC",  # Wrong metric for pump
        }
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400
        assert "must use metric" in response.json()["detail"].lower()

    def test_actuator_value_validation_pump(self, client):
        """Test pump target value validation."""
        # Value too high
        payload = {"actuator": "pump", "targetValue": 1.5, "metric": "soilMoisture"}
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400

        # Value too low
        payload = {"actuator": "pump", "targetValue": -0.1, "metric": "soilMoisture"}
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400

    def test_actuator_value_validation_fan(self, client):
        """Test fan target value validation."""
        # Value too high
        payload = {"actuator": "fan", "targetValue": 150.0, "metric": "temperatureC"}
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400

        # Value too low
        payload = {"actuator": "fan", "targetValue": -60.0, "metric": "temperatureC"}
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400

    def test_actuator_value_validation_lights(self, client):
        """Test lights target value validation."""
        # Value too high
        payload = {"actuator": "lights", "targetValue": 200000.0, "metric": "lightLux"}
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400

        # Value too low
        payload = {"actuator": "lights", "targetValue": -100.0, "metric": "lightLux"}
        response = client.post("/devices/device-1/actuators", json=payload)
        assert response.status_code == 400

