#!/usr/bin/env bash
# Simulate the end-to-end telemetry pipeline for device-2 with staged scenarios.
#
# Requirements:
#   - AWS CLI v2 configured with credentials that can access the deployed stack.
#   - Environment variables set prior to execution:
#       REGION            AWS region (e.g., ap-southeast-1)
#       ACCOUNT_ID        AWS account ID
#       TELEMETRY_TABLE   DynamoDB table name (auto-discovered if unset)
#       METRICS_LAMBDA    Metrics evaluator Lambda function name (auto-discovered if unset)
#   - Optional overrides:
#       DEVICE_ID (default: device-2)
#       TELEMETRY_TOPIC (default: leaf/telemetry/$DEVICE_ID/data)
#       PLANT_TYPE (default: simulation)
#       THRESHOLD (default: 0.75)
#       READINGS_PER_BATCH (default: 30)
#       PUBLISH_DELAY (default: 0.2 seconds)
#       RESULTS_KEY_PREFIX (default: manual-tests/$DEVICE_ID)
#
# Usage:
#   REGION=ap-southeast-1 ACCOUNT_ID=123456789012 \
#   TELEMETRY_TABLE=<auto|optional> METRICS_LAMBDA=<auto|optional> \
#   ./scripts/simulate_device2_pipeline.sh

set -Eeuo pipefail

REQUIRED_VARS=(
  REGION
  ACCOUNT_ID
)

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Environment variable ${name} must be set." >&2
    exit 1
  fi
}

for var in "${REQUIRED_VARS[@]}"; do
  require_env "${var}"
done

# -----------------------------------------------------------------------------
# Auto-discover TELEMETRY_TABLE, METRICS_LAMBDA if not provided
# -----------------------------------------------------------------------------
discover_telemetry_table() {
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
  local fn=""
  fn=$(aws lambda list-functions \
    --region "${REGION}" \
    --query "Functions[?contains(FunctionName,'MetricsEvaluator')].FunctionName | [0]" \
    --output text 2>/dev/null || true)
  if [[ -n "${fn}" && "${fn}" != "None" ]]; then
    echo "${fn}"
    return 0
  fi
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

if [[ -z "${TELEMETRY_TABLE:-}" ]]; then
  if tt=$(discover_telemetry_table); then
    TELEMETRY_TABLE="${tt}"
    echo "Auto-discovered TELEMETRY_TABLE=${TELEMETRY_TABLE}"
  else
    echo "ERROR: Could not auto-discover TELEMETRY_TABLE. Set TELEMETRY_TABLE env var." >&2
    exit 1
  fi
fi

if [[ -z "${METRICS_LAMBDA:-}" ]]; then
  if ml=$(discover_metrics_lambda); then
    METRICS_LAMBDA="${ml}"
    echo "Auto-discovered METRICS_LAMBDA=${METRICS_LAMBDA}"
  else
    echo "ERROR: Could not auto-discover METRICS_LAMBDA. Set METRICS_LAMBDA env var." >&2
    exit 1
  fi
fi

DEVICE_ID=${DEVICE_ID:-device-2}
TELEMETRY_TOPIC=${TELEMETRY_TOPIC:-"leaf/telemetry/${DEVICE_ID}/data"}
PLANT_TYPE=${PLANT_TYPE:-simulation}
THRESHOLD=${THRESHOLD:-0.75}
READINGS_PER_BATCH=${READINGS_PER_BATCH:-30}
PUBLISH_DELAY=${PUBLISH_DELAY:-0.2}
RESULTS_KEY_PREFIX=${RESULTS_KEY_PREFIX:-"manual-tests/${DEVICE_ID}"}

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

log_section() {
  echo
  echo "===================================================================="
  echo "$1"
  echo "===================================================================="
}

put_device_config() {
  log_section "Seeding device configuration in DynamoDB"
  aws dynamodb put-item \
    --region "${REGION}" \
    --table-name "${TELEMETRY_TABLE}" \
    --item "{
        \"deviceId\": {\"S\": \"${DEVICE_ID}\"},
        \"timestamp\": {\"S\": \"CONFIG\"},
        \"threshold\": {\"N\": \"${THRESHOLD}\"},
        \"plantType\": {\"S\": \"${PLANT_TYPE}\"}
      }"
}

publish_telemetry_batch() {
  local label="$1"
  local base_temp="$2"
  local base_humidity="$3"
  local base_moisture="$4"
  local base_lux="$5"

  log_section "Publishing ${READINGS_PER_BATCH} telemetry readings (${label})"
  for offset in $(seq 1 "${READINGS_PER_BATCH}"); do
    payload=$(python - "${DEVICE_ID}" "${THRESHOLD}" "${PLANT_TYPE}" "${READINGS_PER_BATCH}" "${base_temp}" "${base_humidity}" "${base_moisture}" "${base_lux}" "${offset}" <<'PY'
import json
import random
import sys
from datetime import datetime, timedelta, timezone

device_id = sys.argv[1]
threshold = float(sys.argv[2])
plant_type = sys.argv[3]
count = int(sys.argv[4])
base_temp = float(sys.argv[5])
base_humidity = float(sys.argv[6])
base_moisture = float(sys.argv[7])
base_lux = float(sys.argv[8])
offset = int(sys.argv[9])

start = datetime.now(timezone.utc) - timedelta(minutes=count - offset)
payload = {
    "deviceId": device_id,
    "temperatureC": round(random.normalvariate(base_temp, 0.3), 2),
    "humidity": round(random.normalvariate(base_humidity, 1.5), 2),
    "soilMoisture": round(random.normalvariate(base_moisture, 0.02), 2),
    "lightLux": round(random.normalvariate(base_lux, 50), 2),
    "plantType": plant_type,
    "threshold": threshold,
    "timestamp": start.isoformat()
}

print(json.dumps(payload))
PY
    )
    aws iot-data publish \
      --region "${REGION}" \
      --topic "${TELEMETRY_TOPIC}" \
      --cli-binary-format raw-in-base64-out \
      --payload "${payload}"
    sleep "${PUBLISH_DELAY}"
  done
}

upload_disease_result() {
  local score="$1"
  local label="$2"
  log_section "Writing disease result to DynamoDB (${label}, score=${score})"
  local ts="$(date -u +%Y%m%dT%H%M%SZ)"
  aws dynamodb put-item \
    --region "${REGION}" \
    --table-name "${TELEMETRY_TABLE}" \
    --item "{
      \"deviceId\": {\"S\": \"${DEVICE_ID}\"},
      \"timestamp\": {\"S\": \"DISEASE#${ts}\"},
      \"readingType\": {\"S\": \"disease\"},
      \"metrics\": {\"M\": {\"diseaseRisk\": {\"N\": \"${score}\"}}},
      \"source\": {\"S\": \"simulation\"},
      \"label\": {\"S\": \"${label}\"}
    }"
}

invoke_metrics_evaluator() {
  local label="$1"
  log_section "Invoking metrics evaluator (${label})"
  local output="${TMP_DIR}/metrics-${label}.json"
  aws lambda invoke \
    --region "${REGION}" \
    --function-name "${METRICS_LAMBDA}" \
    --payload '{}' \
    "${output}" >/dev/null
  cat "${output}"
  echo
}

# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

put_device_config

publish_telemetry_batch "baseline (below threshold)" 26.5 60.0 0.30 1100
upload_disease_result 0.35 "baseline"
invoke_metrics_evaluator "baseline"

publish_telemetry_batch "alert scenario (above threshold)" 27.5 64.0 0.36 1250
upload_disease_result 0.92 "alert"
invoke_metrics_evaluator "alert"

publish_telemetry_batch "recovery (below threshold)" 26.2 59.0 0.29 1080
upload_disease_result 0.25 "recovery"
invoke_metrics_evaluator "recovery"

log_section "Simulation complete for ${DEVICE_ID}"

