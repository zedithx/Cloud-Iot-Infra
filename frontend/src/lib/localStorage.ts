const STORAGE_KEY = "scanned_plants";

export type ScannedPlant = {
  deviceId: string;
  plantName: string;
};

/**
 * Retrieves all scanned plants from localStorage.
 * @returns Array of scanned plants with deviceId and plantName
 */
export function getScannedPlants(): ScannedPlant[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return [];
    }
    const parsed = JSON.parse(stored) as ScannedPlant[];
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.error("Failed to read scanned plants from localStorage:", error);
    return [];
  }
}

/**
 * Adds or updates a scanned plant in localStorage.
 * @param deviceId - The device ID from the QR code
 * @param plantName - The custom name for the plant
 */
export function addScannedPlant(deviceId: string, plantName: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const plants = getScannedPlants();
    const existingIndex = plants.findIndex((p) => p.deviceId === deviceId);
    const newPlant: ScannedPlant = { deviceId, plantName };
    
    if (existingIndex >= 0) {
      plants[existingIndex] = newPlant;
    } else {
      plants.push(newPlant);
    }
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(plants));
  } catch (error) {
    console.error("Failed to save scanned plant to localStorage:", error);
  }
}

/**
 * Removes a scanned plant from localStorage.
 * @param deviceId - The device ID to remove
 */
export function removeScannedPlant(deviceId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const plants = getScannedPlants();
    const filtered = plants.filter((p) => p.deviceId !== deviceId);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error("Failed to remove scanned plant from localStorage:", error);
  }
}

/**
 * Gets the custom plant name for a device ID.
 * @param deviceId - The device ID to look up
 * @returns The custom plant name, or null if not found
 */
export function getPlantName(deviceId: string): string | null {
  const plants = getScannedPlants();
  const plant = plants.find((p) => p.deviceId === deviceId);
  return plant?.plantName ?? null;
}

