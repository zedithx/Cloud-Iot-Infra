#!/usr/bin/env bash
# Trigger the IoT → DynamoDB pipeline end-to-end against the live AWS environment.
# Usage:
#   STAGE=dev REGION=ap-southeast-1 ACCOUNT_ID=123456789012 \
#     RESULTS_BUCKET=my-batch-results-bucket \
#     METRICS_LAMBDA=dev-infrastructure-Scheduling-MetricsEvaluatorFunctionXYZ \
#     ./scripts/run_live_pipeline.sh device-1
#
# Required environment variables:
#   STAGE               - Deployment stage (e.g., dev, prod)
#   REGION              - AWS region (e.g., ap-southeast-1)
#   ACCOUNT_ID          - AWS account ID
#   RESULTS_BUCKET      - Batch results S3 bucket name
#   METRICS_LAMBDA      - Metrics evaluator Lambda function name
#
# Optional:
#   TELEMETRY_TOPIC - Override IoT topic (defaults to leaf/telemetry/$STAGE/$DEVICE/data)

set -euo pipefail

DEVICE_ID=${1:-}

if [[ -z "${DEVICE_ID}" ]]; then
  echo "Usage: DEVICE_ID=<id> ./scripts/run_live_pipeline.sh <device-id>" >&2
  exit 1
fi

: "${STAGE:?STAGE must be set}"
: "${REGION:?REGION must be set}"
: "${ACCOUNT_ID:?ACCOUNT_ID must be set}"
: "${RESULTS_BUCKET:?RESULTS_BUCKET must be set}"
: "${METRICS_LAMBDA:?METRICS_LAMBDA must be set}"

TOPIC=${TELEMETRY_TOPIC:-"leaf/telemetry/${STAGE}/${DEVICE_ID}/data"}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
RESULT_KEY="${STAGE}/$(date -u +%Y-%m-%d)/mock-result-${DEVICE_ID}.jsonl"

echo "Publishing telemetry to IoT topic: ${TOPIC}"
aws iot-data publish \
  --region "${REGION}" \
  --topic "${TOPIC}" \
  --cli-binary-format raw-in-base64-out \
  --payload "{
    \"deviceId\": \"${DEVICE_ID}\",
    \"temperatureC\": 26.5,
    \"humidity\": 61.0,
    \"soilMoisture\": 0.32,
    \"lightLux\": 1200,
    \"plantType\": \"tomato\",
    \"threshold\": 0.75,
    \"timestamp\": \"${TIMESTAMP}\"
  }"

sleep 2

echo "Publishing second telemetry reading for trend window"
aws iot-data publish \
  --region "${REGION}" \
  --topic "${TOPIC}" \
  --cli-binary-format raw-in-base64-out \
  --payload "{
    \"deviceId\": \"${DEVICE_ID}\",
    \"temperatureC\": 27.1,
    \"humidity\": 63.5,
    \"soilMoisture\": 0.31,
    \"lightLux\": 1150,
    \"timestamp\": \"${TIMESTAMP}\"
  }"

sleep 2

echo "Uploading mock batch transform result to s3://${RESULTS_BUCKET}/${RESULT_KEY}"
echo "{\"deviceId\":\"${DEVICE_ID}\",\"diseaseRisk\":0.92}" > /tmp/mock-result.jsonl
aws s3 cp /tmp/mock-result.jsonl "s3://${RESULTS_BUCKET}/${RESULT_KEY}" --region "${REGION}"
rm /tmp/mock-result.jsonl

echo "Invoking metrics evaluator Lambda: ${METRICS_LAMBDA}"
aws lambda invoke \
  --region "${REGION}" \
  --function-name "${METRICS_LAMBDA}" \
  --payload '{}' \
  /tmp/metrics-output.json >/dev/null

echo "Metrics evaluator response:"
cat /tmp/metrics-output.json
echo

echo "Done. Check DynamoDB table ${STAGE}-telemetry and SNS/Email for alerts."

