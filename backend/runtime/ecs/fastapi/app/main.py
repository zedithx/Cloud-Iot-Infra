import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Literal, Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, timezone


TABLE_NAME = os.environ.get("TELEMETRY_TABLE")
if not TABLE_NAME:
    raise RuntimeError("Environment variable TELEMETRY_TABLE is required.")

AWS_REGION = os.environ.get("AWS_REGION")
DISEASE_THRESHOLD = float(os.environ.get("DISEASE_THRESHOLD", "0.7"))

dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
telemetry_table = dynamodb_resource.Table(TABLE_NAME)
iot_client = boto3.client("iot-data", region_name=AWS_REGION)

app = FastAPI(title="CloudIoT FastAPI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., alias="deviceId", min_length=1)
    score: float = Field(..., ge=0.0, le=1.0)
    temperature_c: Optional[float] = Field(None, alias="temperatureC")
    humidity: Optional[float] = Field(None, ge=0.0, le=100.0)
    soil_moisture: Optional[float] = Field(None, alias="soilMoisture", ge=0.0, le=1.0)
    light_lux: Optional[float] = Field(None, alias="lightLux", ge=0.0)
    disease: Optional[bool] = Field(
        None,
        description="If omitted, derived from score >= DISEASE_THRESHOLD.",
    )
    notes: Optional[str] = Field(None, max_length=1024)
    timestamp: Optional[int] = Field(None, description="Unix epoch seconds")

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "deviceId": "rpi-01",
                "score": 0.42,
                "temperatureC": 28.5,
                "humidity": 63.0,
                "notes": "Captured via greenhouse sensor",
            }
        }


class TelemetryRecord(BaseModel):
    device_id: str = Field(..., alias="deviceId")
    timestamp: int
    score: float
    temperature_c: Optional[float] = Field(None, alias="temperatureC")
    humidity: Optional[float]
    soil_moisture: Optional[float] = Field(None, alias="soilMoisture")
    light_lux: Optional[float] = Field(None, alias="lightLux")
    disease: Optional[bool]
    notes: Optional[str]

    class Config:
        populate_by_name = True


class PlantSnapshot(BaseModel):
    plant_id: str = Field(..., alias="plantId")
    last_seen: int = Field(..., alias="lastSeen")
    disease: Optional[bool]
    score: Optional[float]
    temperature_c: Optional[float] = Field(None, alias="temperatureC")
    humidity: Optional[float]
    soil_moisture: Optional[float] = Field(None, alias="soilMoisture")
    light_lux: Optional[float] = Field(None, alias="lightLux")
    notes: Optional[str]

    class Config:
        populate_by_name = True


class PlantTimeSeriesPoint(BaseModel):
    timestamp: int
    score: Optional[float]
    disease: Optional[bool]
    temperature_c: Optional[float] = Field(None, alias="temperatureC")
    humidity: Optional[float]
    soil_moisture: Optional[float] = Field(None, alias="soilMoisture")
    light_lux: Optional[float] = Field(None, alias="lightLux")


class PlantTimeSeriesResponse(BaseModel):
    plant_id: str = Field(..., alias="plantId")
    points: List[PlantTimeSeriesPoint]


class ActuatorCommand(BaseModel):
    actuator: Literal["pump", "fan", "lights"]
    targetValue: float = Field(..., alias="targetValue")
    metric: Literal["soilMoisture", "temperatureC", "lightLux"]

    class Config:
        populate_by_name = True


class PlantTypeRequest(BaseModel):
    plantType: str = Field(..., min_length=1)


class PlantMetricsResponse(BaseModel):
    plantType: str
    temperatureC: Dict[str, float] = Field(..., alias="temperatureC")
    humidity: Dict[str, float]
    soilMoisture: Dict[str, float] = Field(..., alias="soilMoisture")
    lightLux: Dict[str, float] = Field(..., alias="lightLux")

    class Config:
        populate_by_name = True


# Pre-established plant type values
PLANT_TYPE_METRICS: Dict[str, Dict[str, Dict[str, float]]] = {
    "basil": {
        "temperatureC": {"min": 22.0, "max": 28.0},
        "humidity": {"min": 55.0, "max": 75.0},
        "soilMoisture": {"min": 0.65, "max": 0.85},
        "lightLux": {"min": 10000.0, "max": 20000.0},
    },
    "strawberry": {
        "temperatureC": {"min": 18.0, "max": 24.0},
        "humidity": {"min": 55.0, "max": 70.0},
        "soilMoisture": {"min": 0.55, "max": 0.7},
        "lightLux": {"min": 16000.0, "max": 22000.0},
    },
    "mint": {
        "temperatureC": {"min": 18.0, "max": 24.0},
        "humidity": {"min": 60.0, "max": 80.0},
        "soilMoisture": {"min": 0.6, "max": 0.8},
        "lightLux": {"min": 9000.0, "max": 16000.0},
    },
    "lettuce": {
        "temperatureC": {"min": 16.0, "max": 22.0},
        "humidity": {"min": 60.0, "max": 75.0},
        "soilMoisture": {"min": 0.65, "max": 0.9},
        "lightLux": {"min": 8000.0, "max": 15000.0},
    },
}


def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))


def _clean_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if v is not None}


def _from_decimal(value: Any) -> Any:
    if isinstance(value, list):
        return [_from_decimal(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_decimal(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    return value


def _to_epoch_seconds(value: Any) -> int:
    """
    Convert various timestamp representations to epoch seconds (int).
    Accepts:
    - int or numeric strings
    - typed keys like 'TS#20240101T120000Z-abc123' or 'DISEASE#20240101T120000Z'
      (parses the ISO-like core and ignores suffix/prefix)
    - ISO-like 'YYYYMMDDTHHMMSSZ' with optional '-suffix'
    Falls back to 0 on failure.
    """
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value)
    # Strip type prefixes
    for prefix in ("TS#", "DISEASE#"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    # Remove suffix after first '-' if present
    core = s.split("-", 1)[0]
    # Try plain integer
    try:
        return int(core)
    except ValueError:
        pass
    # Try ISO-like format YYYYMMDDTHHMMSSZ
    try:
        dt = datetime.strptime(core, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def _derive_disease_flag(score: Optional[float], explicit: Optional[bool]) -> Optional[bool]:
    if explicit is not None:
        return explicit
    if score is None:
        return None
    return score >= DISEASE_THRESHOLD


def _normalise_item(item: Dict[str, Any]) -> Dict[str, Any]:
    data = _from_decimal(item.copy())
    plant_id = data.get("plantId") or data.get("deviceId")
    if not plant_id:
        raise ValueError("Record missing plant/device identifier")
    data["plantId"] = plant_id
    if "deviceId" not in data:
        data["deviceId"] = plant_id
    if "timestamp" in data:
        data["timestamp"] = _to_epoch_seconds(data["timestamp"])
    score = float(data["score"]) if "score" in data and data["score"] is not None else None
    data["score"] = score
    data["disease"] = _derive_disease_flag(score, data.get("disease"))
    return data


def _latest_by_plant(items: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for raw in items:
        normalised = _normalise_item(raw)
        plant_id = normalised["plantId"]
        existing = latest.get(plant_id)
        if not existing or normalised.get("timestamp", 0) > existing.get("timestamp", 0):
            latest[plant_id] = normalised
    return latest


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/telemetry", response_model=TelemetryRecord, status_code=201)
def ingest(payload: TelemetryPayload) -> TelemetryRecord:
    timestamp = payload.timestamp or int(time.time())

    item: Dict[str, Any] = {
        "deviceId": payload.device_id,
        "plantId": payload.device_id,
        "timestamp": str(timestamp),
        "score": _to_decimal(payload.score),
        "temperatureC": _to_decimal(payload.temperature_c),
        "humidity": _to_decimal(payload.humidity),
        "soilMoisture": _to_decimal(payload.soil_moisture),
        "lightLux": _to_decimal(payload.light_lux),
        "disease": payload.disease
        if payload.disease is not None
        else _derive_disease_flag(payload.score, None),
        "notes": payload.notes,
    }

    telemetry_table.put_item(Item=_clean_item(item))

    return TelemetryRecord(
        deviceId=payload.device_id,
        timestamp=timestamp,
        score=payload.score,
        temperatureC=payload.temperature_c,
        humidity=payload.humidity,
        soilMoisture=payload.soil_moisture,
        lightLux=payload.light_lux,
        disease=item.get("disease"),
        notes=payload.notes,
    )


@app.get("/telemetry", response_model=List[TelemetryRecord])
def list_all(limit: int = 50) -> List[TelemetryRecord]:
    limit = max(1, min(limit, 200))
    response = telemetry_table.scan(Limit=limit)

    items = response.get("Items", [])
    cleaned = [_normalise_item(item) for item in items]
    cleaned.sort(key=lambda item: item.get("timestamp", 0), reverse=True)

    return [
        TelemetryRecord(
            deviceId=item["deviceId"],
            timestamp=int(item["timestamp"]),
            score=item.get("score") or 0.0,
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
            soilMoisture=item.get("soilMoisture"),
            lightLux=item.get("lightLux"),
            disease=item.get("disease"),
            notes=item.get("notes"),
        )
        for item in cleaned
    ]


@app.get("/telemetry/{device_id}", response_model=List[TelemetryRecord])
def list_telemetry(device_id: str, limit: int = 25) -> List[TelemetryRecord]:
    limit = max(1, min(limit, 100))

    response = telemetry_table.query(
        KeyConditionExpression=Key("deviceId").eq(device_id),
        Limit=limit,
        ScanIndexForward=False,
    )

    items = response.get("Items", [])
    cleaned = [_normalise_item(item) for item in items]
    records = [
        TelemetryRecord(
            deviceId=item["deviceId"],
            timestamp=int(item["timestamp"]),
            score=item.get("score") or 0.0,
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
            soilMoisture=item.get("soilMoisture"),
            lightLux=item.get("lightLux"),
            disease=item.get("disease"),
            notes=item.get("notes"),
        )
        for item in cleaned
    ]
    return records


@app.get("/plants", response_model=List[PlantSnapshot])
def list_plants() -> List[PlantSnapshot]:
    response = telemetry_table.scan()
    items = response.get("Items", [])
    latest = _latest_by_plant(items).values()
    snapshots = sorted(latest, key=lambda item: item.get("plantId", ""))
    return [
        PlantSnapshot(
            plantId=item["plantId"],
            lastSeen=item.get("timestamp", 0),
            disease=item.get("disease"),
            score=item.get("score"),
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
            soilMoisture=item.get("soilMoisture"),
            lightLux=item.get("lightLux"),
            notes=item.get("notes"),
        )
        for item in snapshots
    ]


@app.get("/plants/{plant_id}", response_model=PlantSnapshot)
def plant_detail(plant_id: str) -> PlantSnapshot:
    response = telemetry_table.query(
        KeyConditionExpression=Key("deviceId").eq(plant_id),
        Limit=1,
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Plant not found")
    item = _normalise_item(items[0])
    return PlantSnapshot(
        plantId=item["plantId"],
        lastSeen=item.get("timestamp", 0),
        disease=item.get("disease"),
        score=item.get("score"),
        temperatureC=item.get("temperatureC"),
        humidity=item.get("humidity"),
        soilMoisture=item.get("soilMoisture"),
        lightLux=item.get("lightLux"),
        notes=item.get("notes"),
    )


@app.get("/plants/{plant_id}/timeseries", response_model=PlantTimeSeriesResponse)
def plant_timeseries(
    plant_id: str,
    limit: int = Query(100, ge=1, le=500),
    start: Optional[int] = Query(None, description="Inclusive unix epoch seconds"),
    end: Optional[int] = Query(None, description="Inclusive unix epoch seconds"),
) -> PlantTimeSeriesResponse:
    expression = Key("deviceId").eq(plant_id)
    if start is not None and end is not None:
        expression = expression & Key("timestamp").between(str(start), str(end))
    elif start is not None:
        expression = expression & Key("timestamp").gte(str(start))
    elif end is not None:
        expression = expression & Key("timestamp").lte(str(end))

    response = telemetry_table.query(
        KeyConditionExpression=expression,
        Limit=limit,
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    normalised = [_normalise_item(item) for item in items]
    normalised.sort(key=lambda item: item.get("timestamp", 0))

    points = [
        PlantTimeSeriesPoint(
            timestamp=item.get("timestamp", 0),
            score=item.get("score"),
            disease=item.get("disease"),
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
            soilMoisture=item.get("soilMoisture"),
            lightLux=item.get("lightLux"),
        )
        for item in normalised
    ]

    return PlantTimeSeriesResponse(plantId=plant_id, points=points)


@app.post("/devices/{device_id}/actuators", status_code=200)
def send_actuator_command(device_id: str, command: ActuatorCommand) -> Dict[str, Any]:
    """Send an actuator command to a device via IoT Core."""
    # Validate actuator-to-metric mapping
    actuator_metric_map = {
        "pump": "soilMoisture",
        "fan": "temperatureC",
        "lights": "lightLux",
    }
    expected_metric = actuator_metric_map.get(command.actuator)
    if command.metric != expected_metric:
        raise HTTPException(
            status_code=400,
            detail=f"Actuator '{command.actuator}' must use metric '{expected_metric}', not '{command.metric}'",
        )

    # Validate target value ranges
    if command.actuator == "pump":
        # soilMoisture: 0.0-1.0
        if not (0.0 <= command.targetValue <= 1.0):
            raise HTTPException(
                status_code=400,
                detail="Target value for pump (soilMoisture) must be between 0.0 and 1.0",
            )
    elif command.actuator == "fan":
        # temperatureC: reasonable range -50 to 100
        if not (-50.0 <= command.targetValue <= 100.0):
            raise HTTPException(
                status_code=400,
                detail="Target value for fan (temperatureC) must be between -50.0 and 100.0",
            )
    elif command.actuator == "lights":
        # lightLux: 0 to reasonable max
        if not (0.0 <= command.targetValue <= 100000.0):
            raise HTTPException(
                status_code=400,
                detail="Target value for lights (lightLux) must be between 0.0 and 100000.0",
            )

    # Publish to IoT Core
    topic = f"leaf/commands/{device_id}/{command.actuator}"
    payload = {
        "targetValue": command.targetValue,
    }

    try:
        iot_client.publish(
            topic=topic,
            qos=1,
            payload=json.dumps(payload),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish command to IoT Core: {str(e)}",
        )

    return {
        "deviceId": device_id,
        "command": payload,
        "topic": topic,
        "status": "sent",
    }


@app.get("/plant-types/{plant_type}", response_model=PlantMetricsResponse)
def get_plant_type_metrics(plant_type: str) -> PlantMetricsResponse:
    """Get pre-established best values for a plant type."""
    plant_type_lower = plant_type.lower()
    if plant_type_lower not in PLANT_TYPE_METRICS:
        raise HTTPException(
            status_code=404,
            detail=f"Plant type '{plant_type}' not found. Available types: {', '.join(PLANT_TYPE_METRICS.keys())}",
        )

    metrics = PLANT_TYPE_METRICS[plant_type_lower]
    return PlantMetricsResponse(
        plantType=plant_type_lower,
        temperatureC=metrics["temperatureC"],
        humidity=metrics["humidity"],
        soilMoisture=metrics["soilMoisture"],
        lightLux=metrics["lightLux"],
    )


@app.get("/plant-types", response_model=List[str])
def list_plant_types() -> List[str]:
    """List all available plant types."""
    return list(PLANT_TYPE_METRICS.keys())


@app.post("/devices/{device_id}/plant-type", status_code=200)
def set_device_plant_type(device_id: str, request: PlantTypeRequest) -> Dict[str, Any]:
    """Set the plant type for a device and store it in DynamoDB."""
    plant_type_lower = request.plantType.lower()
    if plant_type_lower not in PLANT_TYPE_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Plant type '{request.plantType}' not found. Available types: {', '.join(PLANT_TYPE_METRICS.keys())}",
        )

    # Get plant type metrics
    metrics = PLANT_TYPE_METRICS[plant_type_lower]

    # Store plant type and metrics in DynamoDB (similar to how threshold is stored)
    config_item: Dict[str, Any] = {
        "deviceId": device_id,
        "timestamp": "CONFIG",
        "plantType": plant_type_lower,
        # Store the metrics for easy retrieval
        "plantTypeMetrics": {
            "temperatureC": {
                "min": _to_decimal(metrics["temperatureC"]["min"]),
                "max": _to_decimal(metrics["temperatureC"]["max"]),
            },
            "humidity": {
                "min": _to_decimal(metrics["humidity"]["min"]),
                "max": _to_decimal(metrics["humidity"]["max"]),
            },
            "soilMoisture": {
                "min": _to_decimal(metrics["soilMoisture"]["min"]),
                "max": _to_decimal(metrics["soilMoisture"]["max"]),
            },
            "lightLux": {
                "min": _to_decimal(metrics["lightLux"]["min"]),
                "max": _to_decimal(metrics["lightLux"]["max"]),
            },
        },
    }

    telemetry_table.put_item(Item=config_item)

    # Also publish to IoT Core so the device can receive it
    topic = f"leaf/commands/{device_id}"
    payload = {
        "plantType": plant_type_lower,
        "timestamp": int(time.time()),
    }

    try:
        iot_client.publish(
            topic=topic,
            qos=1,
            payload=json.dumps(payload),
        )
    except Exception as e:
        # Log but don't fail - DynamoDB write succeeded
        logger = logging.getLogger(__name__)
        logger.warning("Failed to publish plant type to IoT Core: %s", e)

    return {
        "deviceId": device_id,
        "plantType": plant_type_lower,
        "status": "set",
    }


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "CloudIoT FastAPI is running"}

