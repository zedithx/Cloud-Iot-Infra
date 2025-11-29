#!/usr/bin/env python3
"""
Run FastAPI locally with environment variables from .env file or environment.
"""
import os
import sys
from pathlib import Path

# Add the app directory to the path
script_dir = Path(__file__).parent
app_dir = script_dir / "app"
sys.path.insert(0, str(script_dir))

# Try to load .env file if it exists
env_file = script_dir / ".env"
if env_file.exists():
    print(f"Loading environment variables from {env_file}")
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# Validate required environment variables
required_vars = ["TELEMETRY_TABLE", "AWS_REGION"]
missing_vars = [var for var in required_vars if not os.environ.get(var)]

if missing_vars:
    print("Error: Missing required environment variables:")
    for var in missing_vars:
        print(f"  - {var}")
    print("\nPlease set these variables:")
    print("  1. Create a .env file with:")
    print("     TELEMETRY_TABLE=dev-telemetry")
    print("     AWS_REGION=ap-southeast-1")
    print("     ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001")
    print("\n  2. Or export them in your shell:")
    print("     export TELEMETRY_TABLE=dev-telemetry")
    print("     export AWS_REGION=ap-southeast-1")
    sys.exit(1)

print(f"Starting FastAPI server:")
print(f"  TELEMETRY_TABLE: {os.environ.get('TELEMETRY_TABLE')}")
print(f"  AWS_REGION: {os.environ.get('AWS_REGION')}")
print(f"  ALLOWED_ORIGINS: {os.environ.get('ALLOWED_ORIGINS', '*')}")
print(f"  DISEASE_THRESHOLD: {os.environ.get('DISEASE_THRESHOLD', '0.7')}")
print()

# Import and run uvicorn
try:
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
except ImportError:
    print("Error: uvicorn is not installed.")
    print("Please install dependencies:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

