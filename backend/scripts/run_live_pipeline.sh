#!/usr/bin/env bash
# Trigger the IoT → DynamoDB pipeline end-to-end against the live AWS environment.
# Usage:
#   STAGE=dev REGION=ap-southeast-1 ACCOUNT_ID=123456789012 \
#     RESULTS_BUCKET=my-batch-results-bucket \
#     METRICS_LAMBDA=dev-infrastructure-Scheduling-MetricsEvaluatorFunctionXYZ \
#     ./scripts/run_live_pipeline.sh device-1
#
# Required environment variables:
#   REGION              - AWS region (e.g., ap-southeast-1)
#   ACCOUNT_ID          - AWS account ID
#   TELEMETRY_TABLE     - DynamoDB telemetry table name (auto-discovered if unset)
#   RESULTS_BUCKET      - Batch results S3 bucket name (auto-discovered if unset)
#   METRICS_LAMBDA      - Metrics evaluator Lambda function name (auto-discovered if unset)
#
# Optional:
#   TELEMETRY_TOPIC - Override IoT topic (defaults to leaf/telemetry/$DEVICE/data)

set -euo pipefail

DEVICE_ID=${1:-}

if [[ -z "${DEVICE_ID}" ]]; then
  echo "Usage: DEVICE_ID=<id> ./scripts/run_live_pipeline.sh <device-id>" >&2
  exit 1
fi

: "${REGION:?REGION must be set}"
: "${ACCOUNT_ID:?ACCOUNT_ID must be set}"

# -----------------------------------------------------------------------------
# Auto-discover TELEMETRY_TABLE, RESULTS_BUCKET and METRICS_LAMBDA if not provided
# -----------------------------------------------------------------------------
discover_telemetry_table() {
  # Prefer CloudFormation logical id 'TelemetryTable'
  local table=""
  local stacks
  stacks=$(aws cloudformation list-stacks \
    --region "${REGION}" \
    --query "StackSummaries[?StackStatus=='CREATE_COMPLETE'||StackStatus=='UPDATE_COMPLETE'].StackName" \
    --output text 2>/dev/null || true)
  for s in ${stacks}; do
    table=$(aws cloudformation list-stack-resources \
      --region "${REGION}" \
      --stack-name "${s}" \
      --query "StackResourceSummaries[?LogicalResourceId=='TelemetryTable' && ResourceType=='AWS::DynamoDB::Table'].PhysicalResourceId" \
      --output text 2>/dev/null || true)
    if [[ -n "${table}" && "${table}" != "None" ]]; then
      echo "${table}"
      return 0
    fi
  done
  # Fallback: pick a table that ends with '-telemetry'
  table=$(aws dynamodb list-tables \
    --region "${REGION}" \
    --query "TableNames[?ends_with(@, '-telemetry')]|[0]" \
    --output text 2>/dev/null || true)
  if [[ -n "${table}" && "${table}" != "None" ]]; then
    echo "${table}"
    return 0
  fi
  return 1
}

discover_metrics_lambda() {
  # Try Lambda list-functions by name pattern
  local fn=""
  fn=$(aws lambda list-functions \
    --region "${REGION}" \
    --query "Functions[?contains(FunctionName,'MetricsEvaluator')].FunctionName | [0]" \
    --output text 2>/dev/null || true)
  if [[ -n "${fn}" && "${fn}" != "None" ]]; then
    echo "${fn}"
    return 0
  fi
  # Try CloudFormation: look for Lambda function with logical id containing MetricsEvaluator
  local stacks
  stacks=$(aws cloudformation list-stacks \
    --region "${REGION}" \
    --query "StackSummaries[?StackStatus=='CREATE_COMPLETE'||StackStatus=='UPDATE_COMPLETE'].StackName" \
    --output text 2>/dev/null || true)
  for s in ${stacks}; do
    fn=$(aws cloudformation list-stack-resources \
      --region "${REGION}" \
      --stack-name "${s}" \
      --query "StackResourceSummaries[?ResourceType=='AWS::Lambda::Function' && contains(LogicalResourceId,'MetricsEvaluator')].PhysicalResourceId" \
      --output text 2>/dev/null || true)
    if [[ -n "${fn}" && "${fn}" != "None" ]]; then
      echo "${fn}"
      return 0
    fi
  done
  return 1
}

if [[ -z "${METRICS_LAMBDA:-}" ]]; then
  if ml=$(discover_metrics_lambda); then
    METRICS_LAMBDA="${ml}"
    echo "Auto-discovered METRICS_LAMBDA=${METRICS_LAMBDA}"
  else
    echo "ERROR: Could not auto-discover METRICS_LAMBDA. Set METRICS_LAMBDA env var." >&2
    exit 1
  fi
fi

if [[ -z "${TELEMETRY_TABLE:-}" ]]; then
  if tt=$(discover_telemetry_table); then
    TELEMETRY_TABLE="${tt}"
    echo "Auto-discovered TELEMETRY_TABLE=${TELEMETRY_TABLE}"
  else
    echo "ERROR: Could not auto-discover TELEMETRY_TABLE. Set TELEMETRY_TABLE env var." >&2
    exit 1
  fi
fi

TOPIC=${TELEMETRY_TOPIC:-"leaf/telemetry/${DEVICE_ID}/data"}
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
RESULT_KEY="$(date -u +%Y-%m-%d)/mock-result-${DEVICE_ID}.jsonl"

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

# echo "Uploading mock batch transform result to s3://${RESULTS_BUCKET}/${RESULT_KEY}"
# echo "{\"deviceId\":\"${DEVICE_ID}\",\"diseaseRisk\":0.92}" > /tmp/mock-result.jsonl
# aws s3 cp /tmp/mock-result.jsonl "s3://${RESULTS_BUCKET}/${RESULT_KEY}" --region "${REGION}"
# rm /tmp/mock-result.jsonl

echo "Invoking metrics evaluator Lambda: ${METRICS_LAMBDA}"
aws lambda invoke \
  --region "${REGION}" \
  --function-name "${METRICS_LAMBDA}" \
  --payload '{}' \
  /tmp/metrics-output.json >/dev/null

echo "Metrics evaluator response:"
cat /tmp/metrics-output.json
echo
echo "Done. Check DynamoDB table ${TELEMETRY_TABLE} and SNS/Email for alerts."

