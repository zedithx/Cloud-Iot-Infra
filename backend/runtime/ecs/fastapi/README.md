## FastAPI Service

This directory contains the FastAPI application that runs inside the ECS Fargate service.

### Structure

- `app/main.py` – FastAPI entrypoint with DynamoDB integrations
- `requirements.txt` – Python dependencies for the API container
- `Dockerfile` – Builds a slim image that runs `uvicorn app.main:app`

### Building & Publishing

```bash
cd backend/runtime/ecs/fastapi
docker build -t fastapi-leaf:latest .
docker tag fastapi-leaf:latest <account>.dkr.ecr.<region>.amazonaws.com/fastapi-leaf:latest
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker push <account>.dkr.ecr.<region>.amazonaws.com/fastapi-leaf:latest
```

After pushing, update `fastapi_image_uri` in `infra/config/app_context.py` to use the new image URI and deploy with `cdk deploy`.

