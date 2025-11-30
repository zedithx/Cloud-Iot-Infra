"use client";

import { useEffect, useState } from "react";
import { PLANT_PROFILES } from "@/lib/plantProfiles";
import { getPlantName, getPlantType } from "@/lib/localStorage";

type EditPlantModalProps = {
  deviceId: string;
  onConfirm: (deviceId: string, plantName: string, plantType?: string | null) => void;
  onCancel: () => void;
};

export default function EditPlantModal({
  deviceId,
  onConfirm,
  onCancel,
}: EditPlantModalProps) {
  const [plantName, setPlantName] = useState("");
  const [selectedPlantType, setSelectedPlantType] = useState<string>("");
  const [nameError, setNameError] = useState<string | null>(null);

  useEffect(() => {
    // Load current values
    const currentName = getPlantName(deviceId);
    const currentType = getPlantType(deviceId);
    
    if (currentName) {
      setPlantName(currentName);
    }
    if (currentType) {
      setSelectedPlantType(currentType);
    } else {
      setSelectedPlantType(PLANT_PROFILES[0].id);
    }
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

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-emerald-900">
            Edit Plant
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
          <div>
            <label className="block text-sm font-medium text-emerald-700 mb-1">
              Device ID
            </label>
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 px-4 py-2 text-sm font-mono text-emerald-900">
              {deviceId}
            </div>
          </div>

          <div>
            <label
              htmlFor="edit-plant-name"
              className="block text-sm font-medium text-emerald-700 mb-1"
            >
              Plant Name <span className="text-rose-500">*</span>
            </label>
            <input
              id="edit-plant-name"
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
              htmlFor="edit-plant-type"
              className="block text-sm font-medium text-emerald-700 mb-1"
            >
              Plant Type
            </label>
            <select
              id="edit-plant-type"
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
              Save Changes
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

