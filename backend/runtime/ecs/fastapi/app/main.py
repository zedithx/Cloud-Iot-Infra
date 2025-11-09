import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


TABLE_NAME = os.environ.get("TELEMETRY_TABLE")
if not TABLE_NAME:
    raise RuntimeError("Environment variable TELEMETRY_TABLE is required.")

AWS_REGION = os.environ.get("AWS_REGION")

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
    notes: Optional[str]

    class Config:
        populate_by_name = True


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


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/telemetry", response_model=TelemetryRecord, status_code=201)
def ingest(payload: TelemetryPayload) -> TelemetryRecord:
    timestamp = payload.timestamp or int(time.time())

    item: Dict[str, Any] = {
        "deviceId": payload.device_id,
        "timestamp": str(timestamp),
        "score": _to_decimal(payload.score),
        "temperatureC": _to_decimal(payload.temperature_c),
        "humidity": _to_decimal(payload.humidity),
        "notes": payload.notes,
    }

    telemetry_table.put_item(Item=_clean_item(item))

    return TelemetryRecord(
        deviceId=payload.device_id,
        timestamp=timestamp,
        score=payload.score,
        temperatureC=payload.temperature_c,
        humidity=payload.humidity,
        notes=payload.notes,
    )


@app.get("/telemetry", response_model=List[TelemetryRecord])
def list_all(limit: int = 50) -> List[TelemetryRecord]:
    limit = max(1, min(limit, 200))
    response = telemetry_table.scan(Limit=limit)

    items = response.get("Items", [])
    cleaned = [_from_decimal(item) for item in items]
    cleaned.sort(key=lambda item: int(item["timestamp"]), reverse=True)

    return [
        TelemetryRecord(
            deviceId=item["deviceId"],
            timestamp=int(item["timestamp"]),
            score=float(item["score"]),
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
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
    cleaned = [_from_decimal(item) for item in items]
    records = [
        TelemetryRecord(
            deviceId=item["deviceId"],
            timestamp=int(item["timestamp"]),
            score=float(item["score"]),
            temperatureC=item.get("temperatureC"),
            humidity=item.get("humidity"),
            notes=item.get("notes"),
        )
        for item in cleaned
    ]
    return records


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "CloudIoT FastAPI is running"}

