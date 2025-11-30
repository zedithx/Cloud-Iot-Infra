# Plant Disease Classification — ML Inference (ResNet9)

This folder contains the machine learning model, inference code, and testing utilities for the IoT Leaf Disease Monitoring System.

### 📁 Folder Structure
```
ml/
├── model/
│   ├── inference.py         # SageMaker-compatible inference handler
│   ├── requirements.txt     # Python dependencies
│   └── model.pth            # Trained ResNet9 weights (state_dict)
│
├── test/
│   ├── local_test.py        # Offline testing of inference pipeline
│   └── images/              # Optional local test images
│
└── notebooks/
    └── training_notebook.ipynb   # Complete training workflow
```

## 🧪 Local Testing

From the project root:
```
cd ml
python -m venv .venv
.venv\Scripts\Activate (Windows)
pip install -r model/requirements.txt
python -m test.local_test.py
```

Sample output:
```
healthy.jpg -> Healthy
diseased.jpg -> Diseased
```

## ☁️ AWS SageMaker Deployment

1. Package the model:
```
cd model
tar -czvf ../model.tar.gz model.pth inference.py
```
2. Upload model.tar.gz to S3
3. Deploy via SageMaker PyTorch inference container
4. Set entrypoint to inference.py