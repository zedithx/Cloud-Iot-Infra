"use client";

import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";

type QRScannerProps = {
  onScanSuccess: (deviceId: string) => void;
  onClose: () => void;
};

const SCANNER_CONTAINER_ID = "qr-scanner-container";

export default function QRScanner({ onScanSuccess, onClose }: QRScannerProps) {
  const [error, setError] = useState<string | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const onScanSuccessRef = useRef(onScanSuccess);
  const isStoppedRef = useRef(false);

  // Update the ref when callback changes
  useEffect(() => {
    onScanSuccessRef.current = onScanSuccess;
  }, [onScanSuccess]);

  useEffect(() => {
    let isMounted = true;
    
    const startScanning = async () => {
      if (!containerRef.current) {
        console.error("Container ref is null");
        return;
      }

      // Ensure container has the ID
      if (!containerRef.current.id) {
        containerRef.current.id = SCANNER_CONTAINER_ID;
      }

      try {
        const scanner = new Html5Qrcode(containerRef.current.id);
        scannerRef.current = scanner;

        // Try back camera first, then fallback to any available camera
        let cameraId: string | { facingMode: string } = { facingMode: "environment" };
        let isFrontCamera = false;
        
        try {
          // Try to get available cameras
          const devices = await Html5Qrcode.getCameras();
          if (devices && devices.length > 0) {
            // Prefer back camera if available
            const backCamera = devices.find((d) => {
              const label = d.label.toLowerCase();
              return label.includes("back") || label.includes("rear") || label.includes("environment");
            });
            if (backCamera) {
              cameraId = backCamera.id;
              isFrontCamera = false;
            } else {
              // Check if it's a front camera
              const frontCamera = devices.find((d) => {
                const label = d.label.toLowerCase();
                return label.includes("front") || label.includes("user");
              });
              if (frontCamera) {
                cameraId = frontCamera.id;
                isFrontCamera = true;
              } else {
                cameraId = devices[0].id;
                // Assume front camera if we can't determine
                isFrontCamera = true;
              }
            }
          }
        } catch (camErr) {
          console.warn("Could not enumerate cameras, using facingMode:", camErr);
          // Fallback to facingMode (back camera)
          isFrontCamera = false;
        }

        // Add data attribute to container to indicate if it's front camera
        if (containerRef.current) {
          containerRef.current.setAttribute("data-front-camera", String(isFrontCamera));
        }

        // Reset stopped flag when starting
        isStoppedRef.current = false;
        
        await scanner.start(
          cameraId,
          {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            aspectRatio: 1.0,
          },
          (decodedText) => {
            // Validate that decoded text looks like a device ID
            const deviceId = decodedText.trim();
            if (deviceId.length > 0 && isMounted) {
              // Call the success callback FIRST, before stopping scanner
              // This ensures the callback executes before component unmounts
              try {
                onScanSuccessRef.current(deviceId);
              } catch (err) {
                console.error("[QRScanner] Error in callback:", err);
              }
              
              // Then stop scanning (guard against double-stop)
              if (!isStoppedRef.current && scannerRef.current) {
                isStoppedRef.current = true;
                scanner.stop()
                  .then(() => {
                    if (isMounted) {
                      setIsScanning(false);
                    }
                  })
                  .catch((err) => {
                    // Ignore "not running" errors - scanner may have already stopped
                    const errorMsg = err instanceof Error ? err.message : String(err);
                    if (!errorMsg.includes("not running") && !errorMsg.includes("not started") && !errorMsg.includes("not paused")) {
                      console.error("[QRScanner] Error stopping scanner:", err);
                    }
                    if (isMounted) {
                      setIsScanning(false);
                    }
                  });
              }
            } else if (deviceId.length === 0) {
              setError("Invalid QR code format. Please scan a valid device ID.");
            }
          },
          (errorMessage) => {
            // Ignore continuous scanning errors (they're normal while looking for QR codes)
            if (errorMessage.includes("No QR code") || errorMessage.includes("NotFoundException")) {
              return;
            }
          }
        );
        setIsScanning(true);
        setError(null);
      } catch (err) {
        console.error("Failed to start QR scanner:", err);
        const errorMessage =
          err instanceof Error ? err.message : String(err);
        if (errorMessage.includes("Permission denied") || errorMessage.includes("NotAllowedError")) {
          setError("Camera permission denied. Please allow camera access to scan QR codes.");
        } else if (errorMessage.includes("NotFoundError") || errorMessage.includes("DevicesNotFoundError")) {
          setError("No camera found. Please use a device with a camera.");
        } else {
          setError(`Failed to start camera: ${errorMessage}`);
        }
        setIsScanning(false);
      }
    };

    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      void startScanning();
    }, 100);

    return () => {
      isMounted = false;
      clearTimeout(timer);
      // Guard against double-stop
      if (scannerRef.current && !isStoppedRef.current) {
        isStoppedRef.current = true;
        scannerRef.current
          .stop()
          .then(() => {
            scannerRef.current?.clear();
          })
          .catch((err) => {
            // Ignore ALL errors during cleanup - scanner may already be stopped
            // This is expected and harmless
          });
      }
    };
  }, []); // Empty deps - callback is stored in ref

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-emerald-900">Scan QR Code</h2>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-emerald-600 transition hover:bg-emerald-50"
            aria-label="Close scanner"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {error ? (
          <div className="space-y-4">
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-600">
              {error}
            </div>
            <button
              onClick={onClose}
              className="w-full rounded-full bg-emerald-600 px-4 py-2 font-semibold text-white transition hover:bg-emerald-700"
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <div
              id={SCANNER_CONTAINER_ID}
              ref={containerRef}
              className="mb-4 aspect-square w-full max-w-sm mx-auto rounded-2xl overflow-hidden bg-black"
              style={{ position: "relative" }}
            />
            {isScanning ? (
              <p className="text-center text-sm text-emerald-700">
                Point your camera at a QR code
              </p>
            ) : (
              <p className="text-center text-sm text-amber-600">
                Starting camera...
              </p>
            )}
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 font-semibold text-emerald-700 transition hover:bg-emerald-100"
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}

