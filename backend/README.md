
# CloudIoT Platform Infrastructure

This AWS CDK (Python) project provisions the full cloud footprint for the CloudIoT leaf‑disease monitoring solution. It deploys the following subsystems:

- **Networking** – single public-subnet VPC, Internet-facing ALB, ECS/Lambda/SageMaker security groups, S3/DynamoDB gateway endpoints.
- **Data plane** – encrypted S3 buckets for raw images, batch results, processed artifacts, DynamoDB telemetry table, shared IAM policy, KMS CMK.
- **IoT ingest** – IoT Core policy/topic rule that delivers telemetry into Lambda and DynamoDB, plus device policies for secure connectivity.
- **Event scheduling** – EventBridge rules for hourly capture simulation, hourly+5min SageMaker batch transform launches, and a 5-minute telemetry evaluator.
- **ML inference** – SageMaker Batch Transform job triggered every hour at :05, with outputs pushed to an S3 bucket and processed by Lambda before landing in DynamoDB.
- **Telemetry processing** – Lambda invoked by IoT Core that stores readings/thresholds in DynamoDB, plus a scheduled evaluator that raises SNS alerts using recent metrics and the latest disease risk.
- **Notifications** – SNS topic with default email subscription driven by environment context.
- **API service** – ECS Fargate FastAPI service behind an ALB, surfaced via API Gateway HTTP API.
- **Operations** – SSM parameter for alert thresholds, Secrets Manager secret for FastAPI API key, CloudWatch alarms for critical workloads.

> **Note:** The synthetic Lambdas create placeholder artifacts (JSON) instead of live photos. Replace handler logic with real device integrations when ready.

## Repository Layout

```
backend/
├─ infra/                       # CDK app + constructs (pure infrastructure code)
│  ├─ app.py                    # CDK entrypoint (referenced by cdk.json)
│  ├─ config/                   # Stage/environment configuration helpers
│  └─ stacks/                   # Domain-oriented construct modules
│      ├─ api/                  # ECS/ALB/API Gateway wiring
│      ├─ data/                 # DynamoDB and shared data policies
│      ├─ iot/                  # IoT Core + ingest Lambda
│      ├─ ml/                   # SageMaker + inference Lambda
│      ├─ networking/           # VPC and security groups
│      ├─ scheduling/           # EventBridge scheduler
│      ├─ notifications.py
│      └─ operations.py
├─ runtime/                     # Artifacts deployed by the infrastructure
│  ├─ lambdas/                  # Each function packaged independently
│  │   ├─ capture_scheduler/
│  │   ├─ inference/
│  │   ├─ stream_processor/
│  │   ├─ batch_launcher/
│  │   ├─ batch_results_processor/
│  │   └─ metrics_evaluator/
│  └─ ecs/
│      └─ fastapi/              # Placeholder for the FastAPI container source
├─ tests/                       # CDK unit tests
└─ requirements.txt             # CDK dependency pins
```

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the CDK CLI)
- AWS CLI configured with an account/region that has been bootstrapped for CDK (`cdk bootstrap`)

## Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Install CDK CLI once globally (optional but recommended)
npm install -g aws-cdk
```

## Synth & Deploy

The stack uses a single environment (`dev` by default). If you ever need to tweak configuration, you can still pass context overrides (see `infra/config/app_context.py`), but there’s no multi-environment branching to worry about.

```bash
# List stacks
cd backend
cdk ls -c stage=dev

# Synthesize CloudFormation template
npx cdk@latest synth

# Deploy (adjust stage/account/region/profile as needed)
npx cdk@latest deploy \
  --profile <aws-profile> \
  --require-approval never

# Compare local vs deployed infrastructure
npx cdk@latest diff
```

If synthesis fails with missing Python packages, re-run `python -m pip install -r requirements.txt`.

## Runtime Artifacts

- **FastAPI service (`runtime/ecs/fastapi`)**: Build and push the container to ECR, then set `fastapi_image_uri` in `infra/config/app_context.py`.
- **Lambda handlers (`runtime/lambdas/*`)**: Update the code to match real ingestion, inference, and processing logic.
- **Frontend dashboard (`../frontend`)**: Next.js + Tailwind UI for operators; see the package README for setup instructions.

The FastAPI service now exposes plant-centric endpoints used by the dashboard:

| Endpoint | Purpose |
| -------- | ------- |
| `GET /plants` | Latest snapshot for every plant (aggregated scan). |
| `GET /plants/{plantId}` | Most recent reading for a single plant. |
| `GET /plants/{plantId}/timeseries` | Chronological series (supports `limit`, `start`, `end`). |
| `POST /telemetry` | Legacy ingestion path; accepts `deviceId` (alias of `plantId`). |

## Checklist: What to customise before deployment

1. **FastAPI container image**
   - Implement the real API in `runtime/ecs/fastapi/app/main.py`.
   - Build and push the Docker image to ECR using `runtime/ecs/fastapi/push_image.sh`.
   - Update `fastapi_image_uri` in `infra/config/app_context.py` (or supply via `cdk -c config='{"fastapi_image_uri":"..."}'`).

2. **IoT / Data pipeline Lambdas**
   - Review `runtime/lambdas/stream_processor`, `runtime/lambdas/batch_launcher`, `runtime/lambdas/batch_results_processor`, `runtime/lambdas/metrics_evaluator`, `runtime/lambdas/inference` (if re-enabled), and `runtime/lambdas/capture_scheduler`; replace placeholder logic with production-ready code.

3. **Alerting & environment variables**
   - Set `alert_email` and any other stage-specific overrides in `infra/config/app_context.py`.
   - Adjust `allowed_origins` if the FastAPI service should only serve specific frontend domains.

4. **Frontend configuration**
   - In `frontend`, run `npm install`, copy `.env.local.example` to `.env.local`, and set `NEXT_PUBLIC_API_BASE_URL` to the API Gateway endpoint created after deployment.

5. **Secrets / credentials**
   - Store API keys or other secrets outside the repo (e.g., AWS Secrets Manager, SSM Parameter Store).
   - Local `.env` files are ignored (see `.gitignore`), but don’t commit real secrets.

6. **Deployment workflow**
   - Use `runtime/ecs/fastapi/push_image.sh` to build, push, and redeploy the ECS task automatically.
   - For CI/CD, ensure the workflow has access to AWS credentials and passes the FastAPI image URI via CDK context.

## Operational Outputs

- SNS alert topic (`Notifications`) for subscribing additional endpoints.
- API Gateway base URL emitted after `cdk deploy`.
- Secrets Manager secret `/<stage>/fastapi/api-key` injected into the Fargate container.
- SSM parameter `/<stage>/alert-threshold`.
- CloudWatch alarms covering Lambda errors and ALB health.

## Next Steps

- Replace placeholder logic with real device integrations, model artifacts, and FastAPI code.
- Expand unit/integration tests under `tests/`.
- Harden IAM roles once application requirements are known (least privilege, condition keys, etc.).

Happy building! 🎉
