# Machine Learning Model

This folder is for the development of a plant disease detection ML model using the [New Plant Disease Dataset on Kaggle](https://www.kaggle.com/datasets/vipoooool/new-plant-diseases-dataset/data)

Workflow:
1. ESP32-S3-CAM → S3 bucket (leaf images)
2. S3 event → Lambda (LeafInferenceLambda)
3. Lambda does one of two things:
    - Option A (simple / small model): Load ONNX model locally (Lambda + ONNX Runtime) and run inference.
    - Option B (heavier model): Call a SageMaker endpoint to run inference.
4. Lambda:
    - Writes result to DynamoDB
    - Publishes alert via SNS if diseased