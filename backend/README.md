
# CloudIoT Platform Infrastructure

This AWS CDK (Python) project provisions the full cloud footprint for the CloudIoT leaf‑disease monitoring solution. It deploys the following subsystems:

- **Networking** – single public-subnet VPC, Internet-facing ALB, ECS/Lambda/SageMaker security groups, S3/DynamoDB gateway endpoints.
- **Data plane** – encrypted S3 buckets for raw and processed assets, Kinesis data stream, DynamoDB telemetry table, shared IAM policy, KMS CMK.
- **IoT ingest** – presigned-url Lambda, IoT Core policy/topic rule that pipes sensor telemetry into Kinesis.
- **Event scheduling** – EventBridge rule + Lambda that simulates hourly capture jobs.
- **ML inference** – SageMaker endpoint, inference Lambda, and S3 event wiring.
- **Stream processing** – Kinesis-processing Lambda that persists telemetry, evaluates alert thresholds, and publishes to SNS.
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
│      ├─ data/                 # Kinesis, DynamoDB, shared data policies
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
│  │   ├─ presign_url/
│  │   └─ stream_processor/
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
