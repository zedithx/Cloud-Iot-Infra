#!/usr/bin/env python3
"""Generate a QR code for the given text."""
import sys

try:
    import qrcode
except ImportError:
    print("Installing qrcode library...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]"])
    import qrcode

# Generate QR code
text = "esp32s3_cam_01"
qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)
qr.add_data(text)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
img.save("qr_code.png")
print(f"✅ QR code generated successfully!")
print(f"   Text: {text}")
print(f"   File: qr_code.png")

