## FastAPI Service

This directory contains the FastAPI application that runs inside the ECS Fargate service.

### Structure

- `app/main.py` – FastAPI entrypoint with DynamoDB integrations
- `requirements.txt` – Python dependencies for the API container
- `Dockerfile` – Builds a slim image that runs `uvicorn app.main:app`

### DynamoDB schema

Each telemetry reading is stored as a single item with the composite key:

- **Partition key**: `deviceId` (aliased as `plantId` in the API)
- **Sort key**: `timestamp` (ISO epoch seconds, stored as a string in DynamoDB)

Additional attributes that may be present on a record:

| Attribute        | Description                                           |
| ---------------- | ----------------------------------------------------- |
| `score`          | Disease probability (0-1)                             |
| `disease`        | Boolean flag; if omitted, derived from `score`        |
| `temperatureC`   | Ambient temperature                                   |
| `humidity`       | Relative humidity (0-100)                             |
| `soilMoisture`   | Soil moisture fraction (0-1)                          |
| `lightLux`       | Light intensity in lux                                |
| `notes`          | Optional note captured with the event                 |

### API reference

- `POST /telemetry` – ingest a reading (legacy ingestion path; accepts `deviceId` but stores both `deviceId` and `plantId`).
- `GET /telemetry` – fetch the most recent events across all plants.
- `GET /telemetry/{plantId}` – fetch the most recent events for a specific plant.
- `GET /plants` – returns the latest snapshot for every plant (used by the dashboard grid).
- `GET /plants/{plantId}` – returns the latest snapshot for a single plant.
- `GET /plants/{plantId}/timeseries` – returns up to 500 chronological points for charting (`limit`, `start`, and `end` query parameters are optional).

### Building & Publishing

```bash
cd backend/runtime/ecs/fastapi
docker build -t fastapi-leaf:latest .
docker tag fastapi-leaf:latest <account>.dkr.ecr.<region>.amazonaws.com/fastapi-leaf:latest
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/fastapi-leaf:latest
```

After pushing, update `fastapi_image_uri` in `infra/config/app_context.py` to use the new image URI and deploy with `cdk deploy`.

