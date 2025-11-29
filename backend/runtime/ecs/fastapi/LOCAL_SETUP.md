# Local FastAPI Development Setup

This guide explains how to run the FastAPI service locally for testing.

## Prerequisites

1. **AWS Credentials**: Ensure your AWS CLI is configured with credentials that have access to DynamoDB:
   ```bash
   aws configure
   ```

2. **Python Dependencies**: Install the required packages:
   ```bash
   cd backend/runtime/ecs/fastapi
   pip install -r requirements.txt
   ```

## Environment Variables

The FastAPI service requires the following environment variables:

### Required Variables

- `TELEMETRY_TABLE`: The DynamoDB table name (e.g., `dev-telemetry`)
- `AWS_REGION`: AWS region where your DynamoDB table is located (e.g., `ap-southeast-1`)

### Optional Variables

- `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins (default: `*`)
- `DISEASE_THRESHOLD`: Disease detection threshold (default: `0.7`)

## Setup Methods

### Method 1: Using .env file (Recommended)

1. Create a `.env` file in `backend/runtime/ecs/fastapi/`:
   ```bash
   cd backend/runtime/ecs/fastapi
   cat > .env << EOF
   TELEMETRY_TABLE=dev-telemetry
   AWS_REGION=ap-southeast-1
   ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,https://cloud-iot-infra.vercel.app
   DISEASE_THRESHOLD=0.7
   EOF
   ```

2. Run the service using the Python script:
   ```bash
   python run_local.py
   ```

   Or using the shell script:
   ```bash
   ./run_local.sh
   ```

### Method 2: Export Environment Variables

```bash
export TELEMETRY_TABLE=dev-telemetry
export AWS_REGION=ap-southeast-1
export ALLOWED_ORIGINS="http://localhost:3000,http://localhost:3001"
export DISEASE_THRESHOLD=0.7

# Then run uvicorn directly
cd backend/runtime/ecs/fastapi
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Method 3: Inline with Command

```bash
cd backend/runtime/ecs/fastapi
TELEMETRY_TABLE=dev-telemetry AWS_REGION=ap-southeast-1 python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Finding Your Table Name

To find your DynamoDB table name:

```bash
# List all telemetry tables
aws dynamodb list-tables --region ap-southeast-1 --query "TableNames[?contains(@, 'telemetry')]" --output text

# Or check CloudFormation outputs
aws cloudformation describe-stacks \
  --stack-name dev-infrastructure \
  --region ap-southeast-1 \
  --query "Stacks[0].Outputs[?OutputKey=='TelemetryTableName'].OutputValue" \
  --output text
```

## Verifying Setup

Once the server is running, you should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Test the health endpoint:

```bash
curl http://localhost:8000/health
```

## Troubleshooting

### Error: "Environment variable TELEMETRY_TABLE is required"

- Ensure you've set the `TELEMETRY_TABLE` environment variable
- Check that your `.env` file is in the correct location (`backend/runtime/ecs/fastapi/.env`)
- Verify the `.env` file format (no spaces around `=`)

### Error: "Unable to locate credentials"

- Ensure AWS credentials are configured:
  ```bash
  aws configure
  ```
- Or set AWS credentials as environment variables:
  ```bash
  export AWS_ACCESS_KEY_ID=your-key
  export AWS_SECRET_ACCESS_KEY=your-secret
  export AWS_DEFAULT_REGION=ap-southeast-1
  ```

### Error: "ResourceNotFoundException: Requested resource not found"

- Verify the table name is correct
- Check that the table exists in the specified region:
  ```bash
  aws dynamodb describe-table --table-name dev-telemetry --region ap-southeast-1
  ```

### CORS Errors

- Ensure `ALLOWED_ORIGINS` includes your frontend URL
- For local development, include `http://localhost:3000` and `http://127.0.0.1:3000`

## Next Steps

Once the API is running locally, you can:

1. Test endpoints using curl or Postman
2. Point your frontend to `http://localhost:8000` by setting `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
3. Use the API documentation at `http://localhost:8000/docs` (Swagger UI)

