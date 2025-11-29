#!/bin/bash
set -euo pipefail

# Script to run FastAPI locally with environment variables

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and update with your values:"
    echo "  cp .env.example .env"
    echo ""
    echo "Required variables:"
    echo "  - TELEMETRY_TABLE: DynamoDB table name (e.g., dev-telemetry)"
    echo "  - AWS_REGION: AWS region (e.g., ap-southeast-1)"
    exit 1
fi

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

# Validate required variables
if [ -z "${TELEMETRY_TABLE:-}" ]; then
    echo "Error: TELEMETRY_TABLE is not set in .env file"
    exit 1
fi

if [ -z "${AWS_REGION:-}" ]; then
    echo "Error: AWS_REGION is not set in .env file"
    exit 1
fi

echo "Starting FastAPI server with:"
echo "  TELEMETRY_TABLE: $TELEMETRY_TABLE"
echo "  AWS_REGION: $AWS_REGION"
echo "  ALLOWED_ORIGINS: ${ALLOWED_ORIGINS:-*}"
echo ""

# Check if uvicorn is installed
if ! python -m uvicorn --help > /dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install -q -r requirements.txt
fi

# Run FastAPI with uvicorn
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

