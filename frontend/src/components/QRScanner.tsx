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
  const [availableCameras, setAvailableCameras] = useState<{ id: string; label: string }[]>([]);
  const [currentCameraIndex, setCurrentCameraIndex] = useState(0);
  const [isFrontCamera, setIsFrontCamera] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const onScanSuccessRef = useRef(onScanSuccess);
  const isStoppedRef = useRef(false);

  // Update the ref when callback changes
  useEffect(() => {
    onScanSuccessRef.current = onScanSuccess;
  }, [onScanSuccess]);

  // Detect if device is mobile
  useEffect(() => {
    const checkMobile = () => {
      const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
        navigator.userAgent
      ) || window.innerWidth <= 768;
      setIsMobile(isMobileDevice);
    };
    
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

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
        
        let devices: { id: string; label: string }[] = [];
        try {
          // Try to get available cameras
          const cameraDevices = await Html5Qrcode.getCameras();
          devices = cameraDevices.map(d => ({ id: d.id, label: d.label }));
          if (devices && devices.length > 0) {
            setAvailableCameras(devices);
            // Prefer back camera if available
            const backCameraIndex = devices.findIndex((d) => {
              const label = d.label.toLowerCase();
              return label.includes("back") || label.includes("rear") || label.includes("environment");
            });
            if (backCameraIndex >= 0) {
              cameraId = devices[backCameraIndex].id;
              setCurrentCameraIndex(backCameraIndex);
              setIsFrontCamera(false);
            } else {
              // Check if it's a front camera
              const frontCameraIndex = devices.findIndex((d) => {
                const label = d.label.toLowerCase();
                return label.includes("front") || label.includes("user");
              });
              if (frontCameraIndex >= 0) {
                cameraId = devices[frontCameraIndex].id;
                setCurrentCameraIndex(frontCameraIndex);
                setIsFrontCamera(true);
              } else {
                cameraId = devices[0].id;
                setCurrentCameraIndex(0);
                // Assume front camera if we can't determine
                setIsFrontCamera(true);
              }
            }
          }
        } catch (camErr) {
          console.warn("Could not enumerate cameras, using facingMode:", camErr);
          // Fallback to facingMode (back camera)
          setIsFrontCamera(false);
        }

        // Add data attribute to container to indicate if it's front camera
        if (containerRef.current) {
          containerRef.current.setAttribute("data-front-camera", String(isFrontCamera));
        }
        
        // Store initial camera state
        setIsFrontCamera(isFrontCamera);

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

  const flipCamera = async () => {
    if (!scannerRef.current || !isScanning || availableCameras.length < 2) {
      return;
    }

    try {
      // Stop current scanner
      await scannerRef.current.stop();
      isStoppedRef.current = false;

      // Switch to next camera
      const nextIndex = (currentCameraIndex + 1) % availableCameras.length;
      const nextCamera = availableCameras[nextIndex];
      const nextCameraId = nextCamera.id;
      
      // Determine if it's a front camera
      const label = nextCamera.label.toLowerCase();
      const isFront = label.includes("front") || label.includes("user");
      setIsFrontCamera(isFront);
      setCurrentCameraIndex(nextIndex);

      // Update container attribute
      if (containerRef.current) {
        containerRef.current.setAttribute("data-front-camera", String(isFront));
      }

      // Start with new camera
      await scannerRef.current.start(
        nextCameraId,
        {
          fps: 10,
          qrbox: { width: 250, height: 250 },
          aspectRatio: 1.0,
        },
        (decodedText) => {
          const deviceId = decodedText.trim();
          if (deviceId.length > 0) {
            try {
              onScanSuccessRef.current(deviceId);
            } catch (err) {
              console.error("[QRScanner] Error in callback:", err);
            }
            
            if (!isStoppedRef.current && scannerRef.current) {
              isStoppedRef.current = true;
              scannerRef.current.stop().catch(() => {});
            }
          }
        },
        (errorMessage) => {
          if (errorMessage.includes("No QR code") || errorMessage.includes("NotFoundException")) {
            return;
          }
        }
      );
    } catch (err) {
      console.error("Failed to flip camera:", err);
      setError("Failed to switch camera. Please try again.");
    }
  };

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
            <div className="relative mb-4">
              <div
                id={SCANNER_CONTAINER_ID}
                ref={containerRef}
                className="aspect-square w-full max-w-sm mx-auto rounded-2xl overflow-hidden bg-black"
                style={{ position: "relative" }}
              />
              {isMobile && availableCameras.length > 1 && isScanning && (
                <button
                  onClick={flipCamera}
                  className="absolute bottom-4 right-4 rounded-full bg-white/90 p-3 text-emerald-600 shadow-lg transition hover:bg-white hover:scale-110"
                  aria-label="Flip camera"
                  title="Flip camera"
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
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                </button>
              )}
            </div>
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

