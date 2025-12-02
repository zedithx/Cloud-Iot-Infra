import torch
import torch.nn as nn
from torchvision import transforms
import os

# ----------------------------------------------------------
# 1. Copy EXACT ResNet9 + ConvBlock from your training code
# ----------------------------------------------------------

def ConvBlock(in_channels, out_channels, pool=False):
    layers = [
        nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
    ]
    if pool:
        layers.append(nn.MaxPool2d(4))
    return nn.Sequential(*layers)


class ResNet9(nn.Module):
    def __init__(self, in_channels, num_classes):
        super().__init__()
        self.conv1 = ConvBlock(in_channels, 64)
        self.conv2 = ConvBlock(64, 128, pool=True)
        self.res1 = nn.Sequential(
            ConvBlock(128, 128),
            ConvBlock(128, 128),
        )
        self.conv3 = ConvBlock(128, 256, pool=True)
        self.conv4 = ConvBlock(256, 512, pool=True)
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

# ----------------------------------------------------------
# 2. Load your *state_dict* model
# ----------------------------------------------------------

# Path to your saved state_dict from training
STATE_DICT_PATH = "model/model.pth"   # <-- your file here

# Number of classes must match training
NUM_CLASSES = 38  # based on your CLASSES list

model = ResNet9(3, NUM_CLASSES)
state_dict = torch.load(STATE_DICT_PATH, map_location="cpu")
model.load_state_dict(state_dict)
model.eval()

print("Loaded state_dict successfully.")

# ----------------------------------------------------------
# 3. Create a dummy input matching training shape (1x3x256x256)
# ----------------------------------------------------------

dummy_input = torch.randn(1, 3, 256, 256)

# ----------------------------------------------------------
# 4. Convert model → TorchScript
# ----------------------------------------------------------

scripted_model = torch.jit.trace(model, dummy_input)

# Output file
TORCHSCRIPT_PATH = "model/model.pt"
scripted_model.save(TORCHSCRIPT_PATH)

print(f"TorchScript model saved at: {TORCHSCRIPT_PATH}")
