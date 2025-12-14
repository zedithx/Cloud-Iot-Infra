import hashlib
import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Literal, Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# Parse allowed origins from environment variable
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
# Split by comma and strip whitespace, filter out empty strings
allowed_origins_list = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
# If only "*" is present, use ["*"] for CORS middleware
if allowed_origins_list == ["*"]:
    cors_origins = ["*"]
else:
    cors_origins = allowed_origins_list

# Log CORS configuration for debugging
logger = logging.getLogger(__name__)
logger.info("CORS Configuration - ALLOWED_ORIGINS env: %s", allowed_origins_env)
logger.info("CORS Configuration - Parsed origins: %s", cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Exception handler to ensure CORS headers are always present, even on errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensure CORS headers are present on HTTP exceptions."""
    origin = request.headers.get("origin")
    
    # Determine the CORS origin to use
    if cors_origins == ["*"]:
        cors_origin = "*"
    elif origin and origin in cors_origins:
        cors_origin = origin
    elif cors_origins:
        cors_origin = cors_origins[0]
    else:
        cors_origin = "*"
    
    response = JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )
    return response


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., alias="deviceId", min_length=1)
    score: float = Field(..., ge=0.0, le=1.0)
    temperature_c: Optional[float] = Field(None, alias="temperatureC")
    humidity: Optional[float] = Field(None, ge=0.0, le=100.0)
    soil_moisture: Optional[float] = Field(None, alias="soilMoisture", ge=0.0, le=1.0)
    light_lux: Optional[float] = Field(None, alias="lightLux", ge=0.0)
    water_tank_empty: Optional[int] = Field(None, alias="waterTankEmpty", ge=0, le=1, description="0 = tank has water, 1 = tank is empty")
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
    water_tank_empty: Optional[int] = Field(None, alias="waterTankEmpty", ge=0, le=1)
    notes: Optional[str]

    class Config:
        populate_by_name = True


class PlantTimeSeriesPoint(BaseModel):
    timestamp: int
    score: Optional[float]
    disease: Optional[bool]
    reading_type: Optional[str] = Field(None, alias="readingType")
    temperature_c: Optional[float] = Field(None, alias="temperatureC")
    humidity: Optional[float]
    soil_moisture: Optional[float] = Field(None, alias="soilMoisture")
    light_lux: Optional[float] = Field(None, alias="lightLux")
    water_tank_empty: Optional[int] = Field(None, alias="waterTankEmpty", ge=0, le=1)


class PlantTimeSeriesResponse(BaseModel):
    plant_id: str = Field(..., alias="plantId")
    points: List[PlantTimeSeriesPoint]


class ActuatorCommand(BaseModel):
    actuator: Literal["pump", "fan", "lights"]
    targetValue: float = Field(..., alias="targetValue")
    metric: Literal["soilMoisture", "temperatureC", "lightLux"]

    class Config:
        populate_by_name = True


class ScannedPlantRequest(BaseModel):
    deviceId: str = Field(..., alias="deviceId")
    plantName: str = Field(..., alias="plantName", min_length=1, max_length=50)
    plantType: Optional[str] = Field(None, alias="plantType")


class ScannedPlantResponse(BaseModel):
    deviceId: str = Field(..., alias="deviceId")
    plantName: str = Field(..., alias="plantName")
    plantType: Optional[str] = Field(None, alias="plantType")

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


class ThresholdRecommendation(BaseModel):
    actuator: Literal["pump", "fan", "lights"]
    currentThreshold: Optional[float] = Field(None, alias="currentThreshold")
    recommendedThreshold: float = Field(..., alias="recommendedThreshold")
    reasoning: List[str]
    confidence: Literal["low", "medium", "high"]
    trends: List[str]

    class Config:
        populate_by_name = True


class ThresholdRecommendationResponse(BaseModel):
    deviceId: str = Field(..., alias="deviceId")
    plantType: Optional[str] = Field(None, alias="plantType")
    recommendations: List[ThresholdRecommendation]
    timeWindowHours: int = Field(..., alias="timeWindowHours")
    dataPoints: int = Field(..., alias="dataPoints")

    class Config:
        populate_by_name = True


# Pre-established plant type values
PLANT_TYPE_METRICS: Dict[str, Dict[str, Dict[str, float]]] = {
    "basil": {
        "temperatureC": {"min": 22.0, "max": 28.0},
        "humidity": {"min": 55.0, "max": 75.0},
        "soilMoisture": {"min": 0.65, "max": 0.85},
        "lightLux": {"min": 100.0, "max": 200.0},
    },
    "strawberry": {
        "temperatureC": {"min": 18.0, "max": 24.0},
        "humidity": {"min": 55.0, "max": 70.0},
        "soilMoisture": {"min": 0.55, "max": 0.7},
        "lightLux": {"min": 100.0, "max": 200.0},
    },
    "mint": {
        "temperatureC": {"min": 18.0, "max": 24.0},
        "humidity": {"min": 60.0, "max": 80.0},
        "soilMoisture": {"min": 0.6, "max": 0.8},
        "lightLux": {"min": 100.0, "max": 200.0},
    },
    "lettuce": {
        "temperatureC": {"min": 16.0, "max": 22.0},
        "humidity": {"min": 60.0, "max": 75.0},
        "soilMoisture": {"min": 0.65, "max": 0.9},
        "lightLux": {"min": 100.0, "max": 200.0},
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
    - typed keys like 'TS#20240101T120000Z-abc123' or 'DISEASE#20240101T120000Z-abc123'
      (parses the ISO-like core and ignores suffix/prefix)
    - ISO-like 'YYYYMMDDTHHMMSSZ' with optional '-suffix'
    Falls back to 0 on failure.
    Note: New records use TS# prefix, but old disease records may still have DISEASE# prefix.
    """
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value)
    # Strip TS# or DISEASE# prefix (handle both old and new formats)
    if s.startswith("TS#"):
        s = s[3:]  # Remove "TS#" prefix
    elif s.startswith("DISEASE#"):
        s = s[8:]  # Remove "DISEASE#" prefix
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
    # Preserve readingType from original item before any processing
    reading_type = item.get("readingType")
    
    data = _from_decimal(item.copy())
    plant_id = data.get("plantId") or data.get("deviceId")
    if not plant_id:
        raise ValueError("Record missing plant/device identifier")
    data["plantId"] = plant_id
    if "deviceId" not in data:
        data["deviceId"] = plant_id
    if "timestamp" in data:
        data["timestamp"] = _to_epoch_seconds(data["timestamp"])
    
    # Preserve readingType from original item
    if reading_type is not None:
        data["readingType"] = str(reading_type)
    
    # Extract metrics from the metrics map if it exists
    metrics = data.get("metrics", {})
    if isinstance(metrics, dict):
        # Handle waterTankFilled -> waterTankEmpty conversion BEFORE flattening (invert logic)
        # waterTankFilled: 1 = filled, 0 = not filled
        # waterTankEmpty: 1 = empty, 0 = full (has water)
        if "waterTankFilled" in metrics:
            water_tank_filled = metrics.get("waterTankFilled")
            if water_tank_filled is not None:
                # Convert: filled=1 -> empty=0, not filled=0 -> empty=1
                try:
                    filled_value = float(water_tank_filled)
                    metrics["waterTankEmpty"] = 0 if filled_value == 1 else 1
                except (ValueError, TypeError):
                    pass
        
        # Flatten metrics to top level for API compatibility
        for key, value in metrics.items():
            if key not in data:  # Don't overwrite existing top-level fields
                data[key] = value
        # Handle confidence from disease records - map to score
        if "confidence" in metrics and "score" not in data:
            confidence_value = metrics.get("confidence")
            if confidence_value is not None:
                data["score"] = float(confidence_value)
                data["confidence"] = float(confidence_value)
        # Handle binary_prediction from disease records
        if "binary_prediction" in metrics:
            data["binaryPrediction"] = metrics.get("binary_prediction")
        # Handle old diseaseRisk from disease records - map to score (backward compatibility)
        elif "diseaseRisk" in metrics and "score" not in data:
            disease_risk = metrics.get("diseaseRisk")
            if disease_risk is not None:
                data["score"] = float(disease_risk)
    
    # Handle score - could be in metrics (as confidence or diseaseRisk) or at top level
    if "score" not in data or data.get("score") is None:
        # Try to get from metrics.confidence first (new format)
        if isinstance(metrics, dict) and "confidence" in metrics:
            confidence_value = metrics.get("confidence")
            if confidence_value is not None:
                data["score"] = float(confidence_value)
        # Try to get from metrics.diseaseRisk if it exists (old format)
        elif isinstance(metrics, dict) and "diseaseRisk" in metrics:
            disease_risk = metrics.get("diseaseRisk")
            if disease_risk is not None:
                data["score"] = float(disease_risk)
    
    score = float(data["score"]) if "score" in data and data["score"] is not None else None
    data["score"] = score
    
    # Derive disease flag - prioritize binary_prediction if available
    if "binaryPrediction" in data and data["binaryPrediction"] is not None:
        # Use binary_prediction to determine disease status
        binary_pred = str(data["binaryPrediction"]).lower()
        data["disease"] = binary_pred != "healthy"
    else:
        # Fall back to score-based logic for backward compatibility
        data["disease"] = _derive_disease_flag(score, data.get("disease"))
    
    # Ensure readingType is set - infer from data if not present
    if "readingType" not in data or data.get("readingType") is None:
        # Infer readingType: if it has telemetry fields, it's telemetry; if only diseaseRisk/score, it's disease
        has_telemetry_fields = any(
            data.get(key) is not None 
            for key in ["temperatureC", "humidity", "soilMoisture", "lightLux", "waterTankEmpty"]
        )
        if has_telemetry_fields:
            data["readingType"] = "telemetry"
        elif score is not None:
            data["readingType"] = "disease"
        else:
            data["readingType"] = "telemetry"  # Default fallback
    
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
    
    # Separate telemetry and disease records
    telemetry_by_plant: Dict[str, Dict[str, Any]] = {}
    disease_by_plant: Dict[str, Dict[str, Any]] = {}
    
    for raw in items:
        normalised = _normalise_item(raw)
        plant_id = normalised["plantId"]
        reading_type = raw.get("readingType", "")
        
        if reading_type == "telemetry":
            existing = telemetry_by_plant.get(plant_id)
            if not existing or normalised.get("timestamp", 0) > existing.get("timestamp", 0):
                telemetry_by_plant[plant_id] = normalised
        elif reading_type == "disease":
            existing = disease_by_plant.get(plant_id)
            if not existing or normalised.get("timestamp", 0) > existing.get("timestamp", 0):
                disease_by_plant[plant_id] = normalised
    
    # Merge telemetry and disease data for each plant
    all_plant_ids = set(telemetry_by_plant.keys()) | set(disease_by_plant.keys())
    snapshots = []
    
    for plant_id in sorted(all_plant_ids):
        telemetry = telemetry_by_plant.get(plant_id, {})
        disease = disease_by_plant.get(plant_id, {})
        
        # Use telemetry data as base, merge disease score if available
        # If telemetry is empty, use disease as base
        if telemetry:
            merged = telemetry.copy()
        else:
            merged = disease.copy()
        
        # Ensure plantId is always set (use the loop variable as fallback)
        if "plantId" not in merged:
            merged["plantId"] = plant_id
        
        # Merge disease data if available
        if disease.get("score") is not None:
            merged["score"] = disease.get("score")
        if disease.get("disease") is not None:
            merged["disease"] = disease.get("disease")
        # Use the most recent timestamp
        merged["timestamp"] = max(
            telemetry.get("timestamp", 0),
            disease.get("timestamp", 0)
        )
        
        snapshots.append(
        PlantSnapshot(
                plantId=merged["plantId"],
                lastSeen=merged.get("timestamp", 0),
                disease=merged.get("disease"),
                score=merged.get("score"),
                temperatureC=merged.get("temperatureC"),
                humidity=merged.get("humidity"),
                soilMoisture=merged.get("soilMoisture"),
                lightLux=merged.get("lightLux"),
                waterTankEmpty=merged.get("waterTankEmpty"),
                notes=merged.get("notes"),
        )
        )
    
    return snapshots


@app.get("/plants/{plant_id}", response_model=PlantSnapshot)
def plant_detail(plant_id: str) -> PlantSnapshot:
    # Query all items for this device to get both telemetry and disease records
    response = telemetry_table.query(
        KeyConditionExpression=Key("deviceId").eq(plant_id),
    )
    items = response.get("Items", [])
    if not items:
        raise HTTPException(status_code=404, detail="Plant not found")
    
    # Separate telemetry and disease records (similar to /plants endpoint)
    telemetry_data: Optional[Dict[str, Any]] = None
    disease_data: Optional[Dict[str, Any]] = None
    
    for raw in items:
        normalised = _normalise_item(raw)
        reading_type = raw.get("readingType", "")
        
        if reading_type == "telemetry":
            if not telemetry_data or normalised.get("timestamp", 0) > telemetry_data.get("timestamp", 0):
                telemetry_data = normalised
        elif reading_type == "disease":
            if not disease_data or normalised.get("timestamp", 0) > disease_data.get("timestamp", 0):
                disease_data = normalised
    
    # Use telemetry data as base, merge disease score if available
    merged = telemetry_data.copy() if telemetry_data else {}
    if disease_data:
        if disease_data.get("score") is not None:
            merged["score"] = disease_data.get("score")
        if disease_data.get("disease") is not None:
            merged["disease"] = disease_data.get("disease")
        # Use the most recent timestamp
        merged["timestamp"] = max(
            merged.get("timestamp", 0),
            disease_data.get("timestamp", 0)
        )
    
    # If no telemetry data but we have disease data, use disease data as base
    if not telemetry_data and disease_data:
        merged = disease_data.copy()
    
    # Ensure plantId is set
    if "plantId" not in merged:
        merged["plantId"] = plant_id
    
    return PlantSnapshot(
        plantId=merged["plantId"],
        lastSeen=merged.get("timestamp", 0),
        disease=merged.get("disease"),
        score=merged.get("score"),
        temperatureC=merged.get("temperatureC"),
        humidity=merged.get("humidity"),
        soilMoisture=merged.get("soilMoisture"),
        lightLux=merged.get("lightLux"),
        waterTankEmpty=merged.get("waterTankEmpty"),
        notes=merged.get("notes"),
    )


@app.get("/plants/{plant_id}/timeseries", response_model=PlantTimeSeriesResponse)
def plant_timeseries(
    plant_id: str,
    limit: int = Query(100, ge=1, le=500),
    start: Optional[int] = Query(None, description="Inclusive unix epoch seconds"),
    end: Optional[int] = Query(None, description="Inclusive unix epoch seconds"),
) -> PlantTimeSeriesResponse:
    """
    Get time series data for a plant, including both telemetry and disease records.
    Both telemetry and disease records use TS# prefix format, distinguished by readingType.
    We query all records and filter by timestamp range after normalization.
    """
    # Query all records for this device (both TS# and DISEASE# prefixed timestamps)
    # We can't use timestamp range in KeyConditionExpression because of prefixes,
    # so we query all and filter after normalization
    response = telemetry_table.query(
        KeyConditionExpression=Key("deviceId").eq(plant_id),
        ScanIndexForward=False,
    )
    
    items = response.get("Items", [])
    
    # Normalize all items (converts timestamp prefixes to epoch seconds)
    normalised = []
    for item in items:
        try:
            normalised_item = _normalise_item(item)
            # Apply timestamp filtering after normalization
            timestamp = normalised_item.get("timestamp", 0)
            if start is not None and timestamp < start:
                continue
            if end is not None and timestamp > end:
                continue
            normalised.append(normalised_item)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to normalize item: %s, error: %s", item, e)
            continue
    
    # Sort by timestamp (ascending for time series)
    normalised.sort(key=lambda item: item.get("timestamp", 0))
    
    # Apply limit after sorting
    if limit and len(normalised) > limit:
        normalised = normalised[-limit:]  # Take the most recent N items
    
    points = [
        PlantTimeSeriesPoint(
            timestamp=item.get("timestamp", 0),
            score=item.get("score"),
            disease=item.get("disease"),
            readingType=item.get("readingType"),
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
            soilMoisture=item.get("soilMoisture"),
            lightLux=item.get("lightLux"),
            waterTankEmpty=item.get("waterTankEmpty"),
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


def _device_id_to_timestamp(device_id: str) -> int:
    """Convert device ID string to a numeric timestamp for DynamoDB sort key.
    Uses SHA256 for deterministic hashing (Python's hash() is not deterministic across processes).
    """
    # Use SHA256 for deterministic hashing
    hash_bytes = hashlib.sha256(device_id.encode('utf-8')).digest()
    # Convert first 8 bytes to integer and take modulo to keep it within reasonable range
    hash_int = int.from_bytes(hash_bytes[:8], byteorder='big')
    return hash_int % (10 ** 10)  # Keep it within reasonable int range


def _timestamp_to_device_id(items: List[Dict[str, Any]]) -> Dict[int, str]:
    """Extract device IDs from items by checking plantName field format."""
    device_id_map = {}
    for item in items:
        plant_name = item.get("plantName", "")
        # Check if plantName contains deviceId|plantName format
        if "|" in plant_name:
            parts = plant_name.split("|", 1)
            if len(parts) == 2:
                device_id_map[item.get("timestamp", 0)] = parts[0]
    return device_id_map


@app.get("/scanned-plants", response_model=List[ScannedPlantResponse])
def get_scanned_plants() -> List[ScannedPlantResponse]:
    """
    Get all scanned plants (user's plant list).
    Uses a special partition key 'USER_PLANTS' to store user preferences.
    """
    try:
        # Query for all items with partition key 'USER_PLANTS'
        response = telemetry_table.query(
            KeyConditionExpression=Key("deviceId").eq("USER_PLANTS")
        )
        
        plants = []
        device_id_map = _timestamp_to_device_id(response.get("Items", []))
        
        for item in response.get("Items", []):
            timestamp = item.get("timestamp", 0)
            plant_name_full = item.get("plantName", "")
            
            # Extract deviceId and plantName from the stored format
            if "|" in plant_name_full:
                parts = plant_name_full.split("|", 1)
                if len(parts) == 2:
                    actual_device_id = parts[0]
                    plant_name = parts[1]
                    plant_type = item.get("plantType")
                    plants.append(ScannedPlantResponse(
                        deviceId=actual_device_id,
                        plantName=plant_name,
                        plantType=plant_type
                    ))
        
        return plants
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Failed to get scanned plants: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve scanned plants")


@app.post("/scanned-plants", response_model=ScannedPlantResponse, status_code=201)
def add_scanned_plant(plant: ScannedPlantRequest) -> ScannedPlantResponse:
    """
    Add or update a scanned plant.
    Uses deviceId='USER_PLANTS' as partition key and hash(deviceId) as sort key.
    Note: DynamoDB table expects timestamp as STRING, so we convert the hash to string.
    """
    logger = logging.getLogger(__name__)
    try:
        logger.info("Adding/updating scanned plant: deviceId=%s, plantName=%s, plantType=%s", 
                    plant.deviceId, plant.plantName, plant.plantType)
        
        # Convert deviceId to numeric timestamp for sort key, then to string (DynamoDB expects STRING)
        timestamp_key_int = _device_id_to_timestamp(plant.deviceId)
        timestamp_key = str(timestamp_key_int)  # Convert to string for DynamoDB
        logger.debug("Converted deviceId to timestamp key: %s -> %s (string)", plant.deviceId, timestamp_key)
        
        # Check if item already exists by querying all USER_PLANTS and finding matching deviceId
        # This ensures we find existing records even if hash changed (e.g., from old hash function)
        is_update = False
        existing_timestamp_key = timestamp_key
        try:
            # Query all USER_PLANTS records
            response = telemetry_table.query(
                KeyConditionExpression=Key("deviceId").eq("USER_PLANTS")
            )
            
            # Look for existing record with matching deviceId in plantName field
            for item in response.get("Items", []):
                plant_name_full = item.get("plantName", "")
                if "|" in plant_name_full:
                    parts = plant_name_full.split("|", 1)
                    if len(parts) >= 1 and parts[0] == plant.deviceId:
                        # Found existing record for this deviceId
                        existing_timestamp_key = item.get("timestamp")
                        is_update = True
                        logger.info("Found EXISTING record for deviceId=%s (timestamp_key=%s), will UPDATE. Existing plantName=%s, plantType=%s", 
                                   plant.deviceId, existing_timestamp_key, plant_name_full, item.get("plantType"))
                        break
            
            if not is_update:
                logger.info("No existing record found for deviceId=%s, will CREATE new record with timestamp_key=%s", 
                           plant.deviceId, timestamp_key)
        except Exception as e:
            logger.warning("Could not check for existing item: %s", e, exc_info=True)
            is_update = False
            existing_timestamp_key = timestamp_key
        
        if is_update:
            # Use update_item for existing records to properly handle plantType updates (including None)
            # Use the existing timestamp_key (which might be different from the new hash if hash function changed)
            set_parts = ["plantName = :plantName"]
            expression_attribute_values = {
                ":plantName": f"{plant.deviceId}|{plant.plantName}"
            }
            
            # Handle plantType: if None, remove it; otherwise set it
            if plant.plantType is None:
                # Remove plantType attribute
                update_expression = "SET " + ", ".join(set_parts) + " REMOVE plantType"
                logger.debug("Updating existing item (removing plantType) with expression: %s, values: %s", update_expression, expression_attribute_values)
                telemetry_table.update_item(
                    Key={
                        "deviceId": "USER_PLANTS",
                        "timestamp": existing_timestamp_key  # Use existing timestamp key
                    },
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values
                )
            elif plant.plantType != "":
                # Set plantType
                set_parts.append("plantType = :plantType")
                expression_attribute_values[":plantType"] = plant.plantType
                update_expression = "SET " + ", ".join(set_parts)
                logger.debug("Updating existing item (setting plantType) with expression: %s, values: %s", update_expression, expression_attribute_values)
                telemetry_table.update_item(
                    Key={
                        "deviceId": "USER_PLANTS",
                        "timestamp": existing_timestamp_key  # Use existing timestamp key
                    },
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values
                )
            else:
                # Empty string - just update plantName, leave plantType as is
                update_expression = "SET " + ", ".join(set_parts)
                logger.debug("Updating existing item (no plantType change) with expression: %s, values: %s", update_expression, expression_attribute_values)
                telemetry_table.update_item(
                    Key={
                        "deviceId": "USER_PLANTS",
                        "timestamp": existing_timestamp_key  # Use existing timestamp key
                    },
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values
                )
            logger.info("Successfully updated scanned plant in DynamoDB (used existing timestamp_key=%s)", existing_timestamp_key)
        else:
            # Use put_item for new records
            item = {
                "deviceId": "USER_PLANTS",
                "timestamp": timestamp_key,  # Must be string per table schema
                "plantName": f"{plant.deviceId}|{plant.plantName}",  # Store both with delimiter
            }
            
            # Include plantType only if it's not None and not empty
            if plant.plantType is not None and plant.plantType != "":
                item["plantType"] = plant.plantType
            
            logger.debug("Creating new item: %s", item)
            telemetry_table.put_item(Item=item)
            logger.info("Successfully created scanned plant in DynamoDB")
        
        return ScannedPlantResponse(
            deviceId=plant.deviceId,
            plantName=plant.plantName,
            plantType=plant.plantType
        )
    except Exception as e:
        logger.error("Failed to add scanned plant: %s", e, exc_info=True)
        error_detail = f"Failed to save scanned plant: {str(e)}"
        raise HTTPException(status_code=500, detail=error_detail)


@app.delete("/scanned-plants/{device_id}", status_code=204)
def remove_scanned_plant(device_id: str) -> None:
    """
    Remove a scanned plant from the user's list.
    Note: DynamoDB table expects timestamp as STRING, so we convert the hash to string.
    FastAPI automatically URL-decodes path parameters.
    This function queries all USER_PLANTS records to find the one with matching deviceId
    in the plantName field, then deletes using that record's actual timestamp key.
    This ensures deletion works even if the hash function changed or there were collisions.
    """
    logger = logging.getLogger(__name__)
    try:
        # FastAPI automatically URL-decodes the device_id from the path
        logger.info("Removing scanned plant: deviceId=%s", device_id)
        
        # Query all USER_PLANTS records to find the one with matching deviceId
        # This ensures we find the record even if hash function changed or there was a collision
        response = telemetry_table.query(
            KeyConditionExpression=Key("deviceId").eq("USER_PLANTS")
        )
        
        # Look for existing record with matching deviceId in plantName field
        timestamp_key_to_delete = None
        for item in response.get("Items", []):
            plant_name_full = item.get("plantName", "")
            if "|" in plant_name_full:
                parts = plant_name_full.split("|", 1)
                if len(parts) >= 1 and parts[0] == device_id:
                    # Found existing record for this deviceId
                    timestamp_key_to_delete = item.get("timestamp")
                    logger.info("Found record to delete for deviceId=%s (timestamp_key=%s)", 
                               device_id, timestamp_key_to_delete)
                    break
        
        if timestamp_key_to_delete is None:
            # Try fallback: use hash-based timestamp key (for backward compatibility)
            timestamp_key_int = _device_id_to_timestamp(device_id)
            timestamp_key_to_delete = str(timestamp_key_int)
            logger.warning("No record found with deviceId=%s in plantName, trying hash-based key: %s", 
                          device_id, timestamp_key_to_delete)
        
        # Delete the item using the found timestamp key
        telemetry_table.delete_item(
            Key={
                "deviceId": "USER_PLANTS",
                "timestamp": timestamp_key_to_delete,  # Must be string per table schema
            }
        )
        logger.info("Successfully removed scanned plant: deviceId=%s (timestamp_key=%s)", 
                   device_id, timestamp_key_to_delete)
    except Exception as e:
        logger.error("Failed to remove scanned plant: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to remove scanned plant")


def _get_device_config(device_id: str) -> Dict[str, Any]:
    """Get device configuration (plant type, thresholds) from DynamoDB."""
    try:
        response = telemetry_table.query(
            KeyConditionExpression=Key("deviceId").eq(device_id) & Key("timestamp").eq("CONFIG"),
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            item = items[0]
            return {
                "plantType": item.get("plantType"),
                "thresholds": {
                    "soilMoisture": item.get("soilMoistureThreshold"),
                    "temperatureC": item.get("temperatureCThreshold"),
                    "lightLux": item.get("lightLuxThreshold"),
                }
            }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning("Failed to get device config: %s", e)
    return {"plantType": None, "thresholds": {}}


def _analyze_trends(telemetry_points: List[PlantTimeSeriesPoint], time_window_hours: int) -> Dict[str, Any]:
    """Analyze trends in telemetry data to detect rapid changes with detailed context."""
    if not telemetry_points or len(telemetry_points) < 2:
        return {
            "temperature_trend": "insufficient_data",
            "humidity_trend": "insufficient_data",
            "light_trend": "insufficient_data",
            "soil_moisture_trend": "insufficient_data",
            "temperature_rate": 0.0,
            "temperature_start": None,
            "temperature_end": None,
            "temperature_period_hours": 0.0,
            "temperature_current": None,
            "humidity_change": 0.0,
            "humidity_start": None,
            "humidity_end": None,
            "humidity_period_hours": 0.0,
            "humidity_current": None,
            "light_change": 0.0,
            "light_start": None,
            "light_end": None,
            "light_period_hours": 0.0,
            "light_current": None,
            "soil_moisture_change": 0.0,
            "soil_moisture_start": None,
            "soil_moisture_end": None,
            "soil_moisture_period_hours": 0.0,
            "soil_moisture_current": None,
        }
    
    # Sort by timestamp (oldest first)
    sorted_points = sorted(telemetry_points, key=lambda p: p.timestamp)
    
    # Filter out None values and get valid data points
    temp_points = [(p.timestamp, p.temperature_c) for p in sorted_points if p.temperature_c is not None]
    humidity_points = [(p.timestamp, p.humidity) for p in sorted_points if p.humidity is not None]
    light_points = [(p.timestamp, p.light_lux) for p in sorted_points if p.light_lux is not None]
    soil_moisture_points = [(p.timestamp, p.soil_moisture) for p in sorted_points if p.soil_moisture is not None]
    
    trends = {
        "temperature_trend": "stable",
        "humidity_trend": "stable",
        "light_trend": "stable",
        "soil_moisture_trend": "stable",
        "temperature_rate": 0.0,
        "temperature_start": None,
        "temperature_end": None,
        "temperature_period_hours": 0.0,
        "temperature_current": sorted_points[-1].temperature_c if sorted_points[-1].temperature_c is not None else None,
        "humidity_change": 0.0,
        "humidity_start": None,
        "humidity_end": None,
        "humidity_period_hours": 0.0,
        "humidity_current": sorted_points[-1].humidity if sorted_points[-1].humidity is not None else None,
        "light_change": 0.0,
        "light_start": None,
        "light_end": None,
        "light_period_hours": 0.0,
        "light_current": sorted_points[-1].light_lux if sorted_points[-1].light_lux is not None else None,
        "soil_moisture_change": 0.0,
        "soil_moisture_start": None,
        "soil_moisture_end": None,
        "soil_moisture_period_hours": 0.0,
        "soil_moisture_current": sorted_points[-1].soil_moisture if sorted_points[-1].soil_moisture is not None else None,
    }
    
    # Analyze temperature trend
    if len(temp_points) >= 2:
        # Calculate rate of change over last 3 hours
        current_time = sorted_points[-1].timestamp
        three_hours_ago = current_time - (3 * 3600)
        
        recent_temps = [(t, v) for t, v in temp_points if t >= three_hours_ago]
        if len(recent_temps) >= 2:
            first_temp = recent_temps[0][1]
            last_temp = recent_temps[-1][1]
            time_diff_seconds = recent_temps[-1][0] - recent_temps[0][0]
            time_diff_hours = time_diff_seconds / 3600.0
            if time_diff_hours > 0:
                temp_rate = (last_temp - first_temp) / time_diff_hours
                trends["temperature_rate"] = temp_rate
                trends["temperature_start"] = first_temp
                trends["temperature_end"] = last_temp
                trends["temperature_period_hours"] = round(time_diff_hours, 1)
                
                # Detect SHARP/rapid changes only (>3°C/hour or >7°C in 3 hours for rapid, >4°C/hour or >10°C in 3 hours for very rapid)
                # Only flag trends that are rapid enough to require proactive action before auto-heal kicks in
                if temp_rate > 4.0 or (last_temp - first_temp) > 10.0:
                    trends["temperature_trend"] = "increasing_very_rapidly"
                elif temp_rate > 3.0 or (last_temp - first_temp) > 7.0:
                    trends["temperature_trend"] = "increasing_rapidly"
                elif temp_rate < -3.0 or (last_temp - first_temp) < -7.0:
                    trends["temperature_trend"] = "decreasing_rapidly"
                # Don't flag moderate increases - auto-heal can handle those
    
    # Analyze humidity trend (last 6 hours)
    if len(humidity_points) >= 2:
        current_time = sorted_points[-1].timestamp
        six_hours_ago = current_time - (6 * 3600)
        
        recent_humidity = [(t, v) for t, v in humidity_points if t >= six_hours_ago]
        if len(recent_humidity) >= 2:
            first_humidity = recent_humidity[0][1]
            last_humidity = recent_humidity[-1][1]
            humidity_change = last_humidity - first_humidity
            time_diff_seconds = recent_humidity[-1][0] - recent_humidity[0][0]
            time_diff_hours = time_diff_seconds / 3600.0
            trends["humidity_change"] = humidity_change
            trends["humidity_start"] = first_humidity
            trends["humidity_end"] = last_humidity
            trends["humidity_period_hours"] = round(time_diff_hours, 1)
            
            # Only flag sharp humidity changes (>10% in 6 hours for rapid drop, >15% for very rapid)
            if humidity_change < -15.0:
                trends["humidity_trend"] = "decreasing_very_rapidly"
            elif humidity_change < -10.0:
                trends["humidity_trend"] = "decreasing_rapidly"
            # Don't flag moderate changes - auto-heal can handle those
    
    # Analyze light trend (last 6 hours)
    if len(light_points) >= 2:
        current_time = sorted_points[-1].timestamp
        six_hours_ago = current_time - (6 * 3600)
        
        recent_light = [(t, v) for t, v in light_points if t >= six_hours_ago]
        if len(recent_light) >= 2:
            first_light = recent_light[0][1]
            last_light = recent_light[-1][1]
            time_diff_seconds = recent_light[-1][0] - recent_light[0][0]
            time_diff_hours = time_diff_seconds / 3600.0
            if first_light > 0:
                light_change_pct = ((last_light - first_light) / first_light) * 100
                trends["light_change"] = light_change_pct
                trends["light_start"] = first_light
                trends["light_end"] = last_light
                trends["light_period_hours"] = round(time_diff_hours, 1)
                
                # Only flag sharp light changes (>30% drop for rapid, >40% for very rapid)
                if light_change_pct < -40.0:
                    trends["light_trend"] = "decreasing_very_rapidly"
                elif light_change_pct < -30.0:
                    trends["light_trend"] = "decreasing_rapidly"
                # Don't flag moderate changes - auto-heal can handle those
    
    # Analyze soil moisture trend (last 6 hours)
    if len(soil_moisture_points) >= 2:
        current_time = sorted_points[-1].timestamp
        six_hours_ago = current_time - (6 * 3600)
        
        recent_moisture = [(t, v) for t, v in soil_moisture_points if t >= six_hours_ago]
        if len(recent_moisture) >= 2:
            first_moisture = recent_moisture[0][1]
            last_moisture = recent_moisture[-1][1]
            moisture_change = last_moisture - first_moisture
            time_diff_seconds = recent_moisture[-1][0] - recent_moisture[0][0]
            time_diff_hours = time_diff_seconds / 3600.0
            trends["soil_moisture_change"] = moisture_change
            trends["soil_moisture_start"] = first_moisture
            trends["soil_moisture_end"] = last_moisture
            trends["soil_moisture_period_hours"] = round(time_diff_hours, 1)
            
            # Detect SHARP decrease only (moisture dropping very fast - >15% drop for rapid, >20% for very rapid)
            if moisture_change < -0.20:  # More than 20% drop
                trends["soil_moisture_trend"] = "decreasing_very_rapidly"
            elif moisture_change < -0.15:  # More than 15% drop
                trends["soil_moisture_trend"] = "decreasing_rapidly"
            # Don't flag moderate changes - auto-heal can handle those
    
    return trends


def _calculate_recommendations(
    plant_type: str,
    trends: Dict[str, Any],
    current_values: Dict[str, Optional[float]],
    current_thresholds: Dict[str, Optional[float]]
) -> List[ThresholdRecommendation]:
    """Calculate threshold recommendations only when there are concerning trends."""
    if plant_type not in PLANT_TYPE_METRICS:
        # Default to basil if plant type not found
        plant_type = "basil"
    
    metrics = PLANT_TYPE_METRICS[plant_type]
    recommendations = []
    
    # Base threshold calculation (30% above min for pump, 20% for fan, 30% for lights)
    base_soil_moisture = metrics["soilMoisture"]["min"] + (metrics["soilMoisture"]["max"] - metrics["soilMoisture"]["min"]) * 0.3
    base_temperature = metrics["temperatureC"]["min"] + (metrics["temperatureC"]["max"] - metrics["temperatureC"]["min"]) * 0.2
    base_light = metrics["lightLux"]["min"] + (metrics["lightLux"]["max"] - metrics["lightLux"]["min"]) * 0.3
    
    # PUMP (soilMoisture) recommendation - only for SHARP trends that need proactive action
    has_concerning_trends = False
    recommended_soil_moisture = base_soil_moisture
    reasoning = []
    trends_detected = []
    confidence = "medium"
    
    # Very rapid or rapid temp increase → increase soil moisture threshold proactively
    if trends["temperature_trend"] in ["increasing_very_rapidly", "increasing_rapidly"] and trends.get("temperature_start") is not None:
        has_concerning_trends = True
        # More aggressive adjustment for very rapid increases
        if trends["temperature_trend"] == "increasing_very_rapidly":
            temp_adjustment = min(0.08 + (trends["temperature_rate"] * 0.03), 0.20)
        else:
            temp_adjustment = min(0.05 + (trends["temperature_rate"] * 0.02), 0.15)
        recommended_soil_moisture += temp_adjustment
        
        temp_start = trends["temperature_start"]
        temp_end = trends["temperature_end"]
        temp_period = trends["temperature_period_hours"]
        temp_rate = trends["temperature_rate"]
        temp_current = trends.get("temperature_current")
        
        # Create alarming, contextual explanation emphasizing time-to-absorption
        if temp_current and temp_current > metrics["temperatureC"]["max"]:
            reasoning.append(f"⚠️ Temperature is very high at {temp_current:.1f}°C, exceeding the optimal range for {plant_type} ({metrics['temperatureC']['min']:.0f}-{metrics['temperatureC']['max']:.0f}°C).")
        else:
            reasoning.append(f"⚠️ Temperature is rising sharply from {temp_start:.1f}°C to {temp_end:.1f}°C over just {temp_period:.1f} hours (rate: {temp_rate:.1f}°C/hour).")
        
        reasoning.append(f"This sharp temperature increase causes rapid transpiration. Since plants need time to absorb moisture (typically 15-30 minutes), increasing soil moisture threshold by {temp_adjustment:.2f} NOW ensures water is available before the plant experiences stress. Your auto-heal system will maintain this higher threshold.")
        trends_detected.append("temperature_increasing_rapidly")
        confidence = "high"
    
    # Rapid humidity drop → increase soil moisture threshold proactively
    if trends["humidity_trend"] in ["decreasing_very_rapidly", "decreasing_rapidly"] and trends.get("humidity_start") is not None:
        has_concerning_trends = True
        # More aggressive for very rapid drops
        if trends["humidity_trend"] == "decreasing_very_rapidly":
            humidity_adjustment = 0.08 + (abs(trends["humidity_change"]) / 100.0) * 0.08
        else:
            humidity_adjustment = 0.05 + (abs(trends["humidity_change"]) / 100.0) * 0.05
        recommended_soil_moisture += min(humidity_adjustment, 0.15)
        
        humidity_start = trends["humidity_start"]
        humidity_end = trends["humidity_end"]
        humidity_change = trends["humidity_change"]
        humidity_period = trends["humidity_period_hours"]
        
        reasoning.append(f"⚠️ Humidity is dropping sharply from {humidity_start:.1f}% to {humidity_end:.1f}% over {humidity_period:.1f} hours (change: {humidity_change:.1f}%). This rapid drop significantly increases evaporation. Increasing soil moisture threshold by {min(humidity_adjustment, 0.15):.2f} proactively to account for the time needed for water absorption (15-30 minutes) before the plant shows stress.")
        trends_detected.append("humidity_decreasing_rapidly")
        confidence = "high" if confidence == "medium" else confidence
    
    # Soil moisture dropping very rapidly → urgent action needed
    if trends["soil_moisture_trend"] in ["decreasing_very_rapidly", "decreasing_rapidly"] and trends.get("soil_moisture_start") is not None:
        has_concerning_trends = True
        moisture_start = trends["soil_moisture_start"]
        moisture_end = trends["soil_moisture_end"]
        moisture_change = trends["soil_moisture_change"]
        moisture_period = trends["soil_moisture_period_hours"]
        
        # More aggressive adjustment for very rapid drops
        if trends["soil_moisture_trend"] == "decreasing_very_rapidly":
            moisture_adjustment = min(abs(moisture_change) * 2.0, 0.20)
        else:
            moisture_adjustment = min(abs(moisture_change) * 1.5, 0.15)
        recommended_soil_moisture += moisture_adjustment
        
        reasoning.append(f"⚠️ Soil moisture is dropping way faster than normal - from {moisture_start:.2f} to {moisture_end:.2f} ({abs(moisture_change)*100:.1f}% drop) over just {moisture_period:.1f} hours. This indicates the plant is losing water much faster than expected. Increasing threshold by {moisture_adjustment:.2f} proactively to ensure water is available before the plant shows signs of dehydration (plants need 15-30 minutes to absorb moisture).")
        trends_detected.append("soil_moisture_decreasing_rapidly")
        confidence = "high"
    
    # Only add recommendation if there are concerning trends
    if has_concerning_trends:
        # Ensure within bounds
        recommended_soil_moisture = max(metrics["soilMoisture"]["min"], min(recommended_soil_moisture, metrics["soilMoisture"]["max"]))
        
        recommendations.append(ThresholdRecommendation(
            actuator="pump",
            currentThreshold=current_thresholds.get("soilMoisture"),
            recommendedThreshold=round(recommended_soil_moisture, 3),
            reasoning=reasoning,
            confidence=confidence,
            trends=trends_detected
        ))
    
    # FAN (temperatureC) recommendation - only for SHARP temperature increases
    if trends["temperature_trend"] in ["increasing_very_rapidly", "increasing_rapidly"] and trends.get("temperature_start") is not None:
        recommended_temperature = base_temperature
        reasoning = []
        trends_detected = []
        confidence = "high"
        
        temp_start = trends["temperature_start"]
        temp_end = trends["temperature_end"]
        temp_period = trends["temperature_period_hours"]
        temp_rate = trends["temperature_rate"]
        temp_current = trends.get("temperature_current")
        
        if trends["temperature_trend"] == "increasing_rapidly":
            # Increase fan threshold to maintain cooling
            temp_adjustment = min(trends["temperature_rate"] * 0.5, 2.0)
            recommended_temperature += temp_adjustment
            
            if temp_current and temp_current > metrics["temperatureC"]["max"]:
                reasoning.append(f"⚠️ Temperature is very high at {temp_current:.1f}°C, exceeding optimal range. The plant is experiencing heat stress.")
            else:
                reasoning.append(f"⚠️ Temperature is rising rapidly from {temp_start:.1f}°C to {temp_end:.1f}°C over {temp_period:.1f} hours (rate: {temp_rate:.1f}°C/hour).")
            
            reasoning.append(f"You should adjust fan threshold by {temp_adjustment:.1f}°C to activate cooling earlier and prevent further temperature increase.")
            trends_detected.append("temperature_increasing_rapidly")
        else:
            # Moderate increase
            temp_adjustment = min(trends["temperature_rate"] * 0.3, 1.0)
            recommended_temperature += temp_adjustment
            reasoning.append(f"Temperature is gradually increasing from {temp_start:.1f}°C to {temp_end:.1f}°C. You should adjust fan threshold to maintain optimal conditions.")
            trends_detected.append("temperature_increasing")
            confidence = "medium"
        
        recommended_temperature = max(metrics["temperatureC"]["min"], min(recommended_temperature, metrics["temperatureC"]["max"]))
        
        recommendations.append(ThresholdRecommendation(
            actuator="fan",
            currentThreshold=current_thresholds.get("temperatureC"),
            recommendedThreshold=round(recommended_temperature, 1),
            reasoning=reasoning,
            confidence=confidence,
            trends=trends_detected
        ))
    
    # LIGHTS (lightLux) recommendation - only for SHARP light decreases
    if trends["light_trend"] in ["decreasing_very_rapidly", "decreasing_rapidly"] and trends.get("light_start") is not None:
        recommended_light = base_light
        reasoning = []
        trends_detected = []
        confidence = "high"
        
        light_start = trends["light_start"]
        light_end = trends["light_end"]
        light_change = trends["light_change"]
        light_period = trends["light_period_hours"]
        
        # More aggressive for very rapid drops
        if trends["light_trend"] == "decreasing_very_rapidly":
            light_adjustment = (metrics["lightLux"]["max"] - metrics["lightLux"]["min"]) * 0.20
        else:
            light_adjustment = (metrics["lightLux"]["max"] - metrics["lightLux"]["min"]) * 0.15
        recommended_light += light_adjustment
        
        reasoning.append(f"⚠️ Light levels are dropping sharply from {light_start:.0f} lux to {light_end:.0f} lux over {light_period:.1f} hours (change: {abs(light_change):.1f}%). Insufficient light reduces photosynthesis immediately.")
        reasoning.append(f"Increasing light threshold by {light_adjustment:.0f} lux proactively. Since plants need time to adjust to light changes (10-20 minutes for optimal photosynthesis), activating lights earlier ensures the plant receives adequate light before growth is affected.")
        trends_detected.append("light_decreasing_rapidly")
        
        recommended_light = max(metrics["lightLux"]["min"], min(recommended_light, metrics["lightLux"]["max"]))
        
        recommendations.append(ThresholdRecommendation(
            actuator="lights",
            currentThreshold=current_thresholds.get("lightLux"),
            recommendedThreshold=round(recommended_light, 0),
            reasoning=reasoning,
            confidence=confidence,
            trends=trends_detected
        ))
    
    return recommendations


@app.get("/devices/{device_id}/threshold-recommendations", response_model=ThresholdRecommendationResponse)
def get_threshold_recommendations(
    device_id: str,
    timeWindow: int = Query(24, ge=1, le=168, description="Time window in hours to analyze"),
    plantType: Optional[str] = Query(None, description="Plant type (if not provided, fetched from device config, defaults to 'basil')")
) -> ThresholdRecommendationResponse:
    """Get threshold recommendations for a device based on plant type and telemetry trends."""
    logger = logging.getLogger(__name__)
    
    # Get device config (plant type, current thresholds)
    config = _get_device_config(device_id)
    device_plant_type = plantType or config.get("plantType") or "basil"
    
    # Validate plant type
    if device_plant_type.lower() not in PLANT_TYPE_METRICS:
        logger.warning("Invalid plant type '%s' for device '%s', defaulting to 'basil'", device_plant_type, device_id)
        device_plant_type = "basil"
    
    # Fetch telemetry data for the time window
    end_time = int(time.time())
    start_time = end_time - (timeWindow * 3600)
    
    try:
        # Query all items for this device (timestamps are stored in ISO format with TS# prefix)
        # We'll filter by timestamp in memory since DynamoDB stores them as "TS#YYYYMMDDTHHMMSSZ-suffix"
        response = telemetry_table.query(
            KeyConditionExpression=Key("deviceId").eq(device_id),
            Limit=500,
            ScanIndexForward=False,
        )
        items = response.get("Items", [])
        
        # Filter items by timestamp range and normalize
        filtered_items = []
        for item in items:
            # Skip CONFIG items
            if item.get("timestamp") == "CONFIG":
                continue
            # Normalize and check if timestamp is within range
            normalised = _normalise_item(item)
            item_timestamp = normalised.get("timestamp", 0)
            if start_time <= item_timestamp <= end_time:
                filtered_items.append(normalised)
        
        # Sort by timestamp
        filtered_items.sort(key=lambda item: item.get("timestamp", 0))
        
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
            for item in filtered_items
        ]
    except Exception as e:
        logger.error("Failed to fetch telemetry data: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch telemetry data")
    
    # Analyze trends
    trends = _analyze_trends(points, timeWindow)
    
    # Get current values (latest reading)
    current_values = {}
    if points:
        latest = points[-1]
        current_values = {
            "temperatureC": latest.temperature_c,
            "humidity": latest.humidity,
            "soilMoisture": latest.soil_moisture,
            "lightLux": latest.light_lux,
        }
    
    # Calculate recommendations
    recommendations = _calculate_recommendations(
        device_plant_type.lower(),
        trends,
        current_values,
        config.get("thresholds", {})
    )
    
    # Determine overall confidence based on data points
    data_points = len(points)
    if data_points < 5:
        # Lower confidence for all recommendations if insufficient data
        for rec in recommendations:
            if rec.confidence == "high":
                rec.confidence = "medium"
            elif rec.confidence == "medium":
                rec.confidence = "low"
    elif data_points < 10:
        # Medium confidence if moderate data
        for rec in recommendations:
            if rec.confidence == "high":
                rec.confidence = "medium"
    
    return ThresholdRecommendationResponse(
        deviceId=device_id,
        plantType=device_plant_type,
        recommendations=recommendations,
        timeWindowHours=timeWindow,
        dataPoints=data_points
    )


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "CloudIoT FastAPI is running"}

