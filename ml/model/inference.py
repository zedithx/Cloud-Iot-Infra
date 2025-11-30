import io
import json
import os

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

# ============================================================
# Class list (must match training's train.classes order exactly)
# ============================================================

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


# ============================================================
# Model architecture (ResNet9 from your notebook)
# ============================================================

def ConvBlock(in_channels, out_channels, pool=False):
    layers = [
        nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
    ]
    if pool:
        layers.append(nn.MaxPool2d(4))
    return nn.Sequential(*layers)


class ImageClassificationBase(nn.Module):
    def training_step(self, batch):
        images, labels = batch
        out = self(images)
        loss = F.cross_entropy(out, labels)
        return loss

    def validation_step(self, batch):
        images, labels = batch
        out = self(images)
        loss = F.cross_entropy(out, labels)
        _, preds = torch.max(out, dim=1)
        acc = torch.tensor(torch.sum(preds == labels).item() / len(preds))
        return {"val_loss": loss.detach(), "val_accuracy": acc}

    def validation_epoch_end(self, outputs):
        batch_losses = [x["val_loss"] for x in outputs]
        batch_accuracy = [x["val_accuracy"] for x in outputs]
        epoch_loss = torch.stack(batch_losses).mean()
        epoch_accuracy = torch.stack(batch_accuracy).mean()
        return {"val_loss": epoch_loss, "val_accuracy": epoch_accuracy}

    def epoch_end(self, epoch, result):
        print(
            "Epoch [{}], last_lr: {:.5f}, train_loss: {:.4f}, val_loss: {:.4f}, val_acc: {:.4f}".format(
                epoch, result["lrs"][-1], result["train_loss"], result["val_loss"], result["val_accuracy"]
            )
        )


class ResNet9(ImageClassificationBase):
    def __init__(self, in_channels, num_classes):
        super().__init__()

        self.conv1 = ConvBlock(in_channels, 64)
        self.conv2 = ConvBlock(64, 128, pool=True)   # out: 128 x 64 x 64
        self.res1 = nn.Sequential(
            ConvBlock(128, 128),
            ConvBlock(128, 128),
        )

        self.conv3 = ConvBlock(128, 256, pool=True)  # out: 256 x 16 x 16
        self.conv4 = ConvBlock(256, 512, pool=True)  # out: 512 x 4 x 4
        self.res2 = nn.Sequential(
            ConvBlock(512, 512),
            ConvBlock(512, 512),
        )

        self.classifier = nn.Sequential(
            nn.MaxPool2d(4),
            nn.Flatten(),
            nn.Linear(512, num_classes),
        )

    def forward(self, xb):
        out = self.conv1(xb)
        out = self.conv2(out)
        out = self.res1(out) + out
        out = self.conv3(out)
        out = self.conv4(out)
        out = self.res2(out) + out
        out = self.classifier(out)
        return out


# ============================================================
# Device & preprocessing
# ============================================================

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# We use the same logic as your notebook: ToTensor() only, but we add Resize(256x256)
TRANSFORM = transforms.Compose([
    transforms.Resize((256, 256)),
    transforms.ToTensor(),
])


def preprocess_image_from_bytes(image_bytes: bytes) -> torch.Tensor:
    """Convert raw image bytes into a preprocessed tensor."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = TRANSFORM(image)  # shape: [3, 256, 256]
    return tensor


def predict_image_tensor(img_tensor: torch.Tensor, model: nn.Module) -> str:
    """
    img_tensor: shape [3, 256, 256] on CPU
    Return: full class name string (e.g., 'Apple___Black_rot')
    """
    model.eval()
    with torch.no_grad():
        xb = img_tensor.unsqueeze(0).to(DEVICE)  # [1, 3, 256, 256]
        outputs = model(xb)
        _, preds = torch.max(outputs, dim=1)
        class_idx = preds[0].item()
        return CLASSES[class_idx]


def predict_health_from_class_name(class_name: str) -> str:
    """Map full class name to binary Healthy/Diseased."""
    if "healthy" in class_name.lower():
        return "Healthy"
    else:
        return "Diseased"


# ============================================================
# SageMaker entry points
# ============================================================

def model_fn(model_dir: str):
    """
    Load the model for inference.
    This is called once when the container starts.
    """
    model_path = os.path.join(model_dir, "model.pth")

    model = ResNet9(in_channels=3, num_classes=len(CLASSES))
    state_dict = torch.load(model_path, map_location=DEVICE)
    model.load_state_dict(state_dict)
    model.to(DEVICE)
    model.eval()

    print(f"Model loaded from {model_path} onto {DEVICE}")
    return model


def input_fn(request_body, content_type: str):
    """
    Deserialize the request body into an input tensor.
    We'll accept raw image bytes as:
      - 'application/x-image' (SageMaker default)
      - 'image/jpeg', 'image/png'
    """
    if content_type in ("application/x-image", "image/jpeg", "image/png", "image/jpg"):
        if isinstance(request_body, (bytes, bytearray)):
            image_bytes = request_body
        else:
            # In some modes, request_body can be a stream
            image_bytes = request_body.read()
        img_tensor = preprocess_image_from_bytes(image_bytes)
        return img_tensor

    raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(input_data, model):
    """
    Run prediction on the preprocessed tensor.
    input_data: torch.Tensor [3, 256, 256] on CPU
    """
    class_name = predict_image_tensor(input_data, model)
    binary_prediction = predict_health_from_class_name(class_name)

    # Only return binary prediction as requested
    return {"binary_prediction": binary_prediction}


def output_fn(prediction, accept: str):
    """
    Serialize prediction output.
    We'll always return JSON.
    """
    if accept in ("application/json", "application/json; charset=utf-8", "*/*"):
        body = json.dumps(prediction)
        return body, "application/json"

    raise ValueError(f"Unsupported accept type: {accept}")
