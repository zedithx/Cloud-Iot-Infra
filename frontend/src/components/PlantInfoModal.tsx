"use client";

import { useEffect, useState } from "react";
import { fetchPlantDetail } from "@/lib/api";
import { getScannedPlants, getPlantType } from "@/lib/localStorage";
import { PLANT_PROFILES, guessProfileId } from "@/lib/plantProfiles";
import type { PlantSnapshot } from "@/types/telemetry";

type PlantInfoModalProps = {
  deviceId: string;
  onConfirm: (deviceId: string, plantName: string, plantType?: string | null) => void;
  onCancel: () => void;
};

export default function PlantInfoModal({
  deviceId,
  onConfirm,
  onCancel,
}: PlantInfoModalProps) {
  const [plantData, setPlantData] = useState<PlantSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [plantName, setPlantName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [isDuplicate, setIsDuplicate] = useState(false);
  const [selectedPlantType, setSelectedPlantType] = useState<string>("");

  useEffect(() => {
    const loadPlantData = async () => {
      setIsLoading(true);
      setError(null);
      const startTime = Date.now();
      const MIN_LOADING_TIME = 1000; // 1 second minimum
      
      try {
        const data = await fetchPlantDetail(deviceId);
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, MIN_LOADING_TIME - elapsed);
        
        // Wait for minimum loading time if needed
        if (remaining > 0) {
          await new Promise(resolve => setTimeout(resolve, remaining));
        }
        
        setPlantData(data);
      } catch (err) {
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, MIN_LOADING_TIME - elapsed);
        
        // Wait for minimum loading time even on error
        if (remaining > 0) {
          await new Promise(resolve => setTimeout(resolve, remaining));
        }
        
        console.error(`[PlantInfoModal] Error fetching plant detail:`, err);
        const message =
          err instanceof Error ? err.message : String(err);
        // Check for network errors, database errors, etc.
        if (message.includes("not found") || message.includes("404")) {
          setError("Device not found in database");
        } else if (message.includes("Network") || message.includes("fetch") || message.includes("ECONNREFUSED")) {
          setError("Network error: Could not connect to the API. Please check your connection.");
        } else if (message.includes("500") || message.includes("Internal Server Error")) {
          setError("Server error: The database may be unavailable. Please try again later.");
        } else if (message.includes("403") || message.includes("Forbidden")) {
          setError("Access denied: You may not have permission to access this device.");
        } else {
          setError(`Failed to load device: ${message}`);
        }
      } finally {
        setIsLoading(false);
      }
    };

    void loadPlantData();

    // Check for duplicate device ID
    const checkDuplicate = async () => {
      try {
        const scannedPlants = await getScannedPlants();
        const existing = scannedPlants.find((p) => p.deviceId === deviceId);
        if (existing) {
          setIsDuplicate(true);
          setPlantName(existing.plantName);
          if (existing.plantType) {
            setSelectedPlantType(existing.plantType);
          }
        } else {
          // Try to guess plant type from device ID
          const guessedType = guessProfileId(deviceId);
          if (guessedType) {
            setSelectedPlantType(guessedType);
          } else {
            // Default to first profile
            setSelectedPlantType(PLANT_PROFILES[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to check for duplicate:", err);
        // Default to first profile on error
        setSelectedPlantType(PLANT_PROFILES[0].id);
      }
    };
    void checkDuplicate();
  }, [deviceId]);

  const handleConfirm = () => {
    const trimmedName = plantName.trim();
    if (!trimmedName) {
      setNameError("Plant name is required");
      return;
    }
    if (trimmedName.length < 2) {
      setNameError("Plant name must be at least 2 characters");
      return;
    }
    if (trimmedName.length > 50) {
      setNameError("Plant name must be less than 50 characters");
      return;
    }
    setNameError(null);
    onConfirm(deviceId, trimmedName, selectedPlantType || null);
  };

  if (isLoading && !plantData && !error) {
    // Show loading screen while fetching plant data
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4">
        <div className="relative w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl">
          <div className="flex flex-col items-center gap-6 py-8">
            <div className="relative">
              <div className="text-6xl animate-bounce" style={{ animationDuration: "1.5s" }}>
                🌱
              </div>
              <div className="absolute -top-2 -right-2 text-3xl animate-pulse" style={{ animationDuration: "2s", animationDelay: "0.5s" }}>
                ✨
              </div>
            </div>
            <div className="flex flex-col items-center gap-2">
              <p className="text-lg font-semibold text-emerald-900 animate-pulse">
                Loading plant data...
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-emerald-900">
            Add Plant
          </h2>
          <button
            onClick={onCancel}
            className="rounded-full p-2 text-emerald-600 transition hover:bg-emerald-50"
            aria-label="Close modal"
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

        <div className="space-y-4">
          {isLoading ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-4 text-center text-sm text-emerald-700">
              Loading plant information...
            </div>
          ) : error ? (
            <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4 text-sm text-amber-700">
              <p className="font-medium mb-1">⚠️ {error}</p>
              <p className="text-xs">
                You can still add this plant with a custom name. It will appear
                as a placeholder until data is available.
              </p>
            </div>
          ) : plantData ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 p-4 space-y-2">
              <h3 className="font-semibold text-emerald-900">Plant Information</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-emerald-600">Temperature:</span>{" "}
                  <span className="font-medium text-emerald-900">
                    {plantData.temperatureC !== null && plantData.temperatureC !== undefined
                      ? `${plantData.temperatureC.toFixed(1)}°C`
                      : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-emerald-600">Humidity:</span>{" "}
                  <span className="font-medium text-emerald-900">
                    {plantData.humidity !== null && plantData.humidity !== undefined
                      ? `${Math.round(plantData.humidity)}%`
                      : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-emerald-600">Soil Moisture:</span>{" "}
                  <span className="font-medium text-emerald-900">
                    {plantData.soilMoisture !== null && plantData.soilMoisture !== undefined
                      ? `${Math.round(plantData.soilMoisture * 100)}%`
                      : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-emerald-600">Light:</span>{" "}
                  <span className="font-medium text-emerald-900">
                    {plantData.lightLux !== null && plantData.lightLux !== undefined
                      ? `${Math.round(plantData.lightLux)} lux`
                      : "—"}
                  </span>
                </div>
              </div>
              {plantData.disease !== null && plantData.disease !== undefined && (
                <div className="pt-2">
                  <span className="text-emerald-600">Disease Status:</span>{" "}
                  <span
                    className={`font-medium ${
                      plantData.disease ? "text-rose-600" : "text-emerald-700"
                    }`}
                  >
                    {plantData.disease ? "⚠️ Needs attention" : "✅ Healthy"}
                  </span>
                </div>
              )}
            </div>
          ) : null}

          {isDuplicate && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-3 text-sm text-amber-700">
              ⚠️ This device is already in your list. Updating will replace the
              existing entry.
            </div>
          )}

          <div>
            <label
              htmlFor="plant-name"
              className="block text-sm font-medium text-emerald-700 mb-1"
            >
              Plant Name <span className="text-rose-500">*</span>
            </label>
            <input
              id="plant-name"
              type="text"
              value={plantName}
              onChange={(e) => {
                setPlantName(e.target.value);
                setNameError(null);
              }}
              placeholder="e.g., Basil Plant #1"
              className="w-full rounded-2xl border border-emerald-200 bg-white px-4 py-2 text-emerald-900 placeholder-emerald-400 focus:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-200"
              maxLength={50}
            />
            {nameError && (
              <p className="mt-1 text-xs text-rose-600">{nameError}</p>
            )}
            <p className="mt-1 text-xs text-emerald-600">
              {plantName.length}/50 characters
            </p>
          </div>

          <div>
            <label
              htmlFor="plant-type"
              className="block text-sm font-medium text-emerald-700 mb-1"
            >
              Plant Type
            </label>
            <select
              id="plant-type"
              value={selectedPlantType}
              onChange={(e) => setSelectedPlantType(e.target.value)}
              className="w-full rounded-2xl border border-emerald-200 bg-white px-4 py-2 text-emerald-900 focus:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-200"
            >
              {PLANT_PROFILES.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-emerald-600">
              Select the type of plant for optimal monitoring
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={onCancel}
              className="flex-1 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 font-semibold text-emerald-700 transition hover:bg-emerald-100"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              className="flex-1 rounded-full bg-emerald-600 px-4 py-2 font-semibold text-white transition hover:bg-emerald-700"
            >
              Add Plant
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

