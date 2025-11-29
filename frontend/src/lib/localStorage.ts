import { 
  fetchScannedPlants, 
  addScannedPlantToBackend, 
  removeScannedPlantFromBackend,
  isMockApiEnabled,
  type ScannedPlant 
} from "@/lib/api";

const STORAGE_KEY = "scanned_plants";

/**
 * Retrieves all scanned plants from backend (or localStorage as fallback).
 * @returns Array of scanned plants with deviceId and plantName
 */
export async function getScannedPlants(): Promise<ScannedPlant[]> {
  // Get localStorage plants first (as fallback)
  let localStoragePlants: ScannedPlant[] = [];
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as ScannedPlant[];
        if (Array.isArray(parsed)) {
          localStoragePlants = parsed;
        }
      }
    } catch (error) {
      console.error("Failed to read scanned plants from localStorage:", error);
    }
  }
  
  // Try backend first (unless mock mode)
  if (!isMockApiEnabled()) {
    try {
      const backendPlants = await fetchScannedPlants();
      // If backend has plants, use them and sync to localStorage
      if (backendPlants.length > 0) {
        if (typeof window !== "undefined") {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(backendPlants));
        }
        return backendPlants;
      }
      // If backend returns empty but we have localStorage plants, keep localStorage
      // (might be a new device that hasn't synced yet)
      if (localStoragePlants.length > 0) {
        console.info("Backend returned empty, using localStorage plants");
        return localStoragePlants;
      }
      // Both are empty
      return [];
    } catch (error) {
      console.warn("Failed to fetch from backend, using localStorage:", error);
      // Fallback to localStorage if backend fails
      return localStoragePlants;
    }
  }
  
  // Mock mode or SSR - use localStorage only
  return localStoragePlants;
}

/**
 * Adds or updates a scanned plant in backend and localStorage.
 * @param deviceId - The device ID from the QR code
 * @param plantName - The custom name for the plant
 */
export async function addScannedPlant(deviceId: string, plantName: string): Promise<void> {
  // Save to backend first (unless mock mode)
  if (!isMockApiEnabled()) {
    try {
      await addScannedPlantToBackend(deviceId, plantName);
    } catch (error) {
      console.error("Failed to save to backend, saving to localStorage only:", error);
      // Continue to save to localStorage as fallback
    }
  }
  
  // Also save to localStorage (for cache/offline support)
  if (typeof window === "undefined") {
    return;
  }
  try {
    const plants = await getScannedPlants();
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
    throw error;
  }
}

/**
 * Removes a scanned plant from backend and localStorage.
 * @param deviceId - The device ID to remove
 */
export async function removeScannedPlant(deviceId: string): Promise<void> {
  // Remove from backend first (unless mock mode)
  if (!isMockApiEnabled()) {
    try {
      await removeScannedPlantFromBackend(deviceId);
    } catch (error) {
      console.error("Failed to remove from backend, removing from localStorage only:", error);
      // Continue to remove from localStorage as fallback
    }
  }
  
  // Also remove from localStorage
  if (typeof window === "undefined") {
    return;
  }
  try {
    const plants = await getScannedPlants();
    const filtered = plants.filter((p) => p.deviceId !== deviceId);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error("Failed to remove scanned plant from localStorage:", error);
    throw error;
  }
}

/**
 * Gets the custom plant name for a device ID (synchronous, from localStorage cache).
 * @param deviceId - The device ID to look up
 * @returns The custom plant name, or null if not found
 */
export function getPlantName(deviceId: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return null;
    }
    const plants = JSON.parse(stored) as ScannedPlant[];
    const plant = plants.find((p) => p.deviceId === deviceId);
    return plant?.plantName ?? null;
  } catch (error) {
    console.error("Failed to read plant name from localStorage:", error);
    return null;
  }
}

