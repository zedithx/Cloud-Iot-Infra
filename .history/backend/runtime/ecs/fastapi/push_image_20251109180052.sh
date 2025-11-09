#!/usr/bin/env bash
set -euo pipefail

# Optional: load .env alongside this script for local convenience
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Required environment variables
: "${AWS_REGION:?Need to set AWS_REGION (e.g. ap-southeast-1)}"
: "${ACCOUNT_ID:?Need to set ACCOUNT_ID (your AWS account number)}"
: "${ECR_REPO_NAME:?Need to set ECR_REPO_NAME (e.g. cloud-iot-fastapi)}"

IMAGE_TAG=$(date +%Y%m%d-%H%M%S)
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
FULL_IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}:${IMAGE_TAG}"

echo "➡️  Building Docker image ${FULL_IMAGE_URI}"
docker build --platform linux/amd64 -t "${ECR_REPO_NAME}:${IMAGE_TAG}" .

echo "➡️  Ensuring ECR repository ${ECR_REPO_NAME} exists"
aws ecr describe-repositories \
  --repository-names "${ECR_REPO_NAME}" \
  --region "${AWS_REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository \
      --repository-name "${ECR_REPO_NAME}" \
      --image-scanning-configuration scanOnPush=true \
      --region "${AWS_REGION}" >/dev/null

echo "➡️  Logging into ECR"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "➡️  Tagging and pushing image"
docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${FULL_IMAGE_URI}"
docker push "${FULL_IMAGE_URI}"

cat <<EOF

✅ Image pushed: ${FULL_IMAGE_URI}

Next steps:
1. Update fastapi_image_uri in backend/infra/config/app_context.py (or supply it via CDK context) to:
     "${FULL_IMAGE_URI}"
2. Redeploy the infrastructure:
     cd ../../..
     cdk deploy

EOF