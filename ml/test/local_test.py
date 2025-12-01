import os
import json

from model.inference import model_fn, input_fn, predict_fn, output_fn

# Path setup
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(THIS_DIR, "..", "model")
IMAGES_DIR = os.path.join(THIS_DIR, "images")

def main():
    # 1. Load model
    model = model_fn(MODEL_DIR)

    # 2. Collect image files
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp"}
    files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if os.path.splitext(f)[1].lower() in valid_exts
    ])

    if not files:
        print("No valid images found in /test/images/")
        return

    # 3. Run each image through the inference pipeline
    for fname in files:
        path = os.path.join(IMAGES_DIR, fname)

        with open(path, "rb") as f:
            img_bytes = f.read()

        # Simulate SageMaker API:
        # - input_fn() preprocesses image
        # - predict_fn() runs model
        # - output_fn() formats json
        input_tensor = input_fn(img_bytes, content_type="image/jpeg")
        prediction_dict = predict_fn(input_tensor, model)
        body, _ = output_fn(prediction_dict, accept="application/json")

        result = json.loads(body)
        print(f"{fname} -> {result}")

if __name__ == "__main__":
    main()
