#!/usr/bin/env bash
# Simulate the end-to-end telemetry pipeline for device-2 with staged scenarios.
#
# Requirements:
#   - AWS CLI v2 configured with credentials that can access the deployed stack.
#   - Environment variables set prior to execution:
#       STAGE             Deployment stage (e.g., dev)
#       REGION            AWS region (e.g., ap-southeast-1)
#       ACCOUNT_ID        AWS account ID
#       TELEMETRY_TABLE   DynamoDB table name (e.g., dev-telemetry)
#       RESULTS_BUCKET    S3 bucket for SageMaker batch results
#       METRICS_LAMBDA    Metrics evaluator Lambda function name
#   - Optional overrides:
#       DEVICE_ID (default: device-2)
#       TELEMETRY_TOPIC (default: leaf/telemetry/$STAGE/$DEVICE_ID/data)
#       PLANT_TYPE (default: simulation)
#       THRESHOLD (default: 0.75)
#       READINGS_PER_BATCH (default: 30)
#       PUBLISH_DELAY (default: 0.2 seconds)
#       RESULTS_KEY_PREFIX (default: $STAGE/manual-tests/$DEVICE_ID)
#
# Usage:
#   STAGE=dev REGION=ap-southeast-1 ACCOUNT_ID=123456789012 \
#   TELEMETRY_TABLE=dev-telemetry RESULTS_BUCKET=my-batch-results \
#   METRICS_LAMBDA=dev-infrastructure-Scheduling-MetricsEvaluatorFunctionXYZ \
#   ./scripts/simulate_device2_pipeline.sh

set -Eeuo pipefail

REQUIRED_VARS=(
  STAGE
  REGION
  ACCOUNT_ID
  TELEMETRY_TABLE
  RESULTS_BUCKET
  METRICS_LAMBDA
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

DEVICE_ID=${DEVICE_ID:-device-2}
TELEMETRY_TOPIC=${TELEMETRY_TOPIC:-"leaf/telemetry/${STAGE}/${DEVICE_ID}/data"}
PLANT_TYPE=${PLANT_TYPE:-simulation}
THRESHOLD=${THRESHOLD:-0.75}
READINGS_PER_BATCH=${READINGS_PER_BATCH:-30}
PUBLISH_DELAY=${PUBLISH_DELAY:-0.2}
RESULTS_KEY_PREFIX=${RESULTS_KEY_PREFIX:-"${STAGE}/manual-tests/${DEVICE_ID}"}

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
  log_section "Uploading batch transform result (${label}, score=${score})"
  local key="${RESULTS_KEY_PREFIX}/${label}-$(date -u +%Y%m%dT%H%M%S).jsonl"
  local tmp_file="${TMP_DIR}/result.jsonl"
  printf '{"deviceId":"%s","diseaseRisk":%.2f}\n' "${DEVICE_ID}" "${score}" >"${tmp_file}"

  aws s3 cp "${tmp_file}" "s3://${RESULTS_BUCKET}/${key}" --region "${REGION}"
  echo "Uploaded to s3://${RESULTS_BUCKET}/${key}"
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

