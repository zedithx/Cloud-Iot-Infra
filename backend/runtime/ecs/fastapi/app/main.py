import os
import time
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


TABLE_NAME = os.environ.get("TELEMETRY_TABLE")
if not TABLE_NAME:
    raise RuntimeError("Environment variable TELEMETRY_TABLE is required.")

AWS_REGION = os.environ.get("AWS_REGION")
DISEASE_THRESHOLD = float(os.environ.get("DISEASE_THRESHOLD", "0.7"))

dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
telemetry_table = dynamodb_resource.Table(TABLE_NAME)

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
        data["timestamp"] = int(data["timestamp"])
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


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "CloudIoT FastAPI is running"}

