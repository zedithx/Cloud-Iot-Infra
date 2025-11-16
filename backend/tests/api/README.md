# API Tests

Test cases for FastAPI endpoints using pytest and moto (for DynamoDB and IoT Core mocking).

## Test Coverage

### GET /health
- ✅ Health check returns OK status

### POST /telemetry (Ingest Telemetry)
- ✅ Minimal required fields work
- ✅ All fields work correctly
- ✅ Disease flag derived from score
- ✅ Payload validation (missing fields, invalid ranges)

### GET /telemetry (List All Telemetry)
- ✅ Empty table returns empty list
- ✅ Returns all telemetry sorted by timestamp
- ✅ Limit parameter works

### GET /telemetry/{device_id} (Device Telemetry)
- ✅ Returns telemetry for specific device
- ✅ Filters out other devices
- ✅ Empty device returns empty list
- ✅ Limit parameter works

### GET /plants (Main Page Data)
- ✅ Empty table returns empty list
- ✅ Single device returns correct data
- ✅ Multiple devices returns latest reading for each
- ✅ Only latest reading per device is returned
- ✅ Handles missing optional fields gracefully

### GET /plants/{plant_id} (Plant Detail)
- ✅ Returns plant detail correctly
- ✅ Returns 404 for non-existent device

### GET /plants/{plant_id}/timeseries (Timeseries Data)
- ✅ Non-existent device returns empty points
- ✅ Single data point returns correctly
- ✅ Multiple data points are sorted correctly
- ✅ Limit parameter works
- ✅ Filters out other devices' data
- ✅ Start/end time filters work
- ✅ Handles missing optional fields gracefully
- ✅ Limit validation works

### POST /devices/{device_id}/plant-type (Set Plant Type)
- ✅ Sets plant type correctly
- ✅ Writes to DynamoDB with deviceId key
- ✅ Invalid plant type returns 400
- ✅ Case insensitive plant type
- ✅ Overwrites existing plant type

### GET /plant-types (List Plant Types)
- ✅ Returns list of available plant types

### GET /plant-types/{plant_type} (Plant Type Metrics)
- ✅ Returns metrics for valid plant type
- ✅ Returns 404 for invalid plant type
- ✅ Case insensitive lookup

### POST /devices/{device_id}/actuators (Actuator Commands)
- ✅ Pump command works
- ✅ Fan command works
- ✅ Lights command works
- ✅ Actuator-metric mismatch validation
- ✅ Target value validation for all actuators

## Running Tests

### Prerequisites

Install test dependencies:
```bash
cd backend/runtime/ecs/fastapi
pip install -r requirements.txt
```

Or install from backend root:
```bash
cd backend
pip install pytest httpx moto[boto3]
```

### Run All Tests

From the backend directory:
```bash
pytest tests/api/
```

### Run Specific Test Class

```bash
pytest tests/api/test_fastapi_endpoints.py::TestPlantsListEndpoint
pytest tests/api/test_fastapi_endpoints.py::TestPlantTimeseriesEndpoint
```

### Run Specific Test

```bash
pytest tests/api/test_fastapi_endpoints.py::TestPlantsListEndpoint::test_list_plants_single_device
```

### Verbose Output

```bash
pytest tests/api/ -v
```

## Test Structure

- Uses `moto` to mock DynamoDB (no real AWS resources needed)
- Uses FastAPI's `TestClient` for HTTP testing
- Each test is isolated with its own DynamoDB table fixture
- Helper functions create test data in the correct DynamoDB format

## Notes

- Timestamps are stored as numeric strings (Unix timestamps) for compatibility with `int()` conversion in `_normalise_item`
- All tests use mocked DynamoDB, so no AWS credentials are required
- Tests verify both the data structure and business logic (e.g., latest reading per device)

