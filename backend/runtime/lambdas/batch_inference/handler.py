import os
import io
import json
import boto3
import logging
from PIL import Image
import torch
from torchvision import transforms

# ---------------- Logging Setup ----------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------- Environment -------------------
RAW_BUCKET = os.environ["RAW_BUCKET"]
BATCH_RESULTS_BUCKET = os.environ["BATCH_RESULTS_BUCKET"]
STAGE = os.environ["STAGE"]

s3 = boto3.client("s3")

# ---------------- Load Model --------------------
MODEL_PATH = "/var/task/model.pt"
logger.debug(f"Loading TorchScript model from {MODEL_PATH}...")
model = torch.jit.load(MODEL_PATH)
model.eval()
logger.debug("Model loaded successfully.")

# ---------------- Transforms --------------------
TRANSFORM = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.ToTensor()
])

# ---------------- Class List --------------------
CLASSES = [
    'Apple___Apple_scab',
    'Apple___Black_rot',
    'Apple___Cedar_apple_rust',
    'Apple___healthy',
    'Blueberry___healthy',
    'Cherry_(including_sour)___Powdery_mildew',
    'Cherry_(including_sour)___healthy',
    'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot',
    'Corn_(maize)___Common_rust_',
    'Corn_(maize)___Northern_Leaf_Blight',
    'Corn_(maize)___healthy',
    'Grape___Black_rot',
    'Grape___Esca_(Black_Measles)',
    'Grape___Leaf_blight_(Isariopsis_Leaf_Spot)',
    'Grape___healthy',
    'Orange___Haunglongbing_(Citrus_greening)',
    'Peach___Bacterial_spot',
    'Peach___healthy',
    'Pepper,_bell___Bacterial_spot',
    'Pepper,_bell___healthy',
    'Potato___Early_blight',
    'Potato___Late_blight',
    'Potato___healthy',
    'Raspberry___healthy',
    'Soybean___healthy',
    'Squash___Powdery_mildew',
    'Strawberry___Leaf_scorch',
    'Strawberry___healthy',
    'Tomato___Bacterial_spot',
    'Tomato___Early_blight',
    'Tomato___Late_blight',
    'Tomato___Leaf_Mold',
    'Tomato___Septoria_leaf_spot',
    'Tomato___Spider_mites Two-spotted_spider_mite',
    'Tomato___Target_Spot',
    'Tomato___Tomato_Yellow_Leaf_Curl_Virus',
    'Tomato___Tomato_mosaic_virus',
    'Tomato___healthy',
]

# ---------------- Helper Functions ----------------

def predict_health(class_name: str):
    return "Healthy" if "healthy" in class_name.lower() else "Diseased"


def load_image(bucket, key):
    obj = s3.get_object(Bucket=bucket, Key=key)
    img = Image.open(io.BytesIO(obj["Body"].read())).convert("RGB")
    return TRANSFORM(img).unsqueeze(0)

# ---------------- Lambda Handler ------------------

def lambda_handler(event, context):
    import datetime
    from datetime import timezone, timedelta

    logger.info(f"Incoming event: {json.dumps(event)}")

    # Allow manual prefix
    prefix = event.get("prefix")
    if prefix:
        logger.info(f"Manual prefix override: {prefix}")
    else:
        prev_hour = datetime.datetime.now(timezone.utc) - timedelta(hours=1)
        prefix = f"photos/{prev_hour.strftime('%Y%m%dT%H')}/"
        logger.info(f"No prefix provided. Automatically using previous hour prefix: {prefix}")

    # List images in S3
    logger.debug(f"Listing images in s3://{RAW_BUCKET}/{prefix}")
    response = s3.list_objects_v2(Bucket=RAW_BUCKET, Prefix=prefix)
    contents = response.get("Contents", [])

    if not contents:
        logger.warning("No images found for this prefix. Exiting.")
        return {"processed": 0, "output": None}

    results = []

    for obj in contents:
        key = obj["Key"]

        if not key.endswith(".jpg"):
            logger.warning(f"Skipping non-image object: {key}")
            continue

        logger.debug(f"Processing: {key}")
        tensor = load_image(RAW_BUCKET, key)

        with torch.no_grad():
            out = model(tensor)
            idx = out.argmax(1).item()
            confidence = torch.softmax(out, dim=1)[0, idx].item()

        class_name = CLASSES[idx]
        binary_prediction = predict_health(class_name)

        logger.debug(
            f"Prediction for {key}: idx={idx}, class={class_name}, "
            f"binary={binary_prediction}, confidence={confidence:.4f}"
        )

        results.append(json.dumps({
            "filename": key.split("/")[-1],  # Keep filename for backward compatibility
            "s3_key": key,  # Include full S3 key to extract deviceId
            "class_idx": idx,
            "class_name": class_name,
            "binary_prediction": binary_prediction,
            "confidence": confidence
        }))

    timestamp = datetime.datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_key = f"{STAGE}/{timestamp}/results.ndjson"

    logger.info(f"Writing NDJSON to s3://{BATCH_RESULTS_BUCKET}/{output_key}")

    s3.put_object(
        Bucket=BATCH_RESULTS_BUCKET,
        Key=output_key,
        Body="\n".join(results),
        ContentType="application/json",
    )

    logger.info(f"Completed inference. Processed {len(results)} images.")

    return {
        "processed": len(results),
        "output": output_key
    }
