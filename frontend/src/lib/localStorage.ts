import { 
  fetchScannedPlants, 
  addScannedPlantToBackend, 
  removeScannedPlantFromBackend,
  isMockApiEnabled,
  type ScannedPlant 
} from "@/lib/api";

const STORAGE_KEY = "scanned_plants";
const LAST_SYNC_KEY = "scanned_plants_last_sync";

/**
 * Retrieves all scanned plants from backend (or localStorage as fallback).
 * Always fetches from backend to ensure cross-device sync.
 * @param forceRefresh - If true, bypasses any caching and always fetches from backend
 * @returns Array of scanned plants with deviceId and plantName
 */
export async function getScannedPlants(forceRefresh: boolean = true): Promise<ScannedPlant[]> {
  // Always prioritize backend (DynamoDB) over localStorage for cross-device sync
  if (!isMockApiEnabled()) {
    try {
      console.info("[getScannedPlants] Fetching from backend (forceRefresh=%s)", forceRefresh);
      const backendPlants = await fetchScannedPlants();
      // Always sync backend data to localStorage (even if empty)
      // This ensures localStorage is up-to-date with DynamoDB
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(backendPlants));
        localStorage.setItem(LAST_SYNC_KEY, Date.now().toString());
        console.info("[getScannedPlants] Synced %d plants from backend to localStorage: %s", 
                     backendPlants.length, 
                     backendPlants.map(p => p.deviceId).join(", ") || "none");
      }
      return backendPlants;
    } catch (error) {
      console.warn("Failed to fetch from backend, falling back to localStorage:", error);
      // Only use localStorage as fallback if backend fails (network error, etc.)
      // This allows offline access but backend is always the source of truth
    }
  }
  
  // Fallback to localStorage (for mock mode or if backend fails)
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
 * Adds or updates a scanned plant in backend and localStorage.
 * @param deviceId - The device ID from the QR code
 * @param plantName - The custom name for the plant
 * @param plantType - Optional plant type (e.g., "basil", "strawberry")
 */
export async function addScannedPlant(deviceId: string, plantName: string, plantType?: string | null): Promise<void> {
  const newPlant: ScannedPlant = { deviceId, plantName, plantType: plantType || null };
  
  // Save to backend first (unless mock mode)
  if (!isMockApiEnabled()) {
    try {
      await addScannedPlantToBackend(deviceId, plantName, plantType);
      console.info("Successfully saved plant to backend:", { deviceId, plantName, plantType });
    } catch (error) {
      console.error("Failed to save to backend, saving to localStorage only:", error);
      // Continue to save to localStorage as fallback
    }
  }
  
  // Always update localStorage (for cache/offline support)
  if (typeof window === "undefined") {
    return;
  }
  try {
    // Get current plants from localStorage
    let plants: ScannedPlant[] = [];
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as ScannedPlant[];
        if (Array.isArray(parsed)) {
          plants = parsed;
        }
      } catch (parseError) {
        console.warn("Failed to parse localStorage, starting fresh:", parseError);
      }
    }
    
    // Update or add the plant
    const existingIndex = plants.findIndex((p) => p.deviceId === deviceId);
    if (existingIndex >= 0) {
      plants[existingIndex] = newPlant;
    } else {
      plants.push(newPlant);
    }
    
    // Save back to localStorage
    localStorage.setItem(STORAGE_KEY, JSON.stringify(plants));
    console.info("Successfully saved plant to localStorage:", { deviceId, plantName, plantType });
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
      console.info("Successfully removed plant from backend:", { deviceId });
      
      // After successful backend removal, refresh from backend to ensure sync
      // This ensures localStorage matches backend state
      // Add a small delay to ensure backend has processed the deletion
      await new Promise(resolve => setTimeout(resolve, 200));
      try {
        const updatedPlants = await fetchScannedPlants();
        if (typeof window !== "undefined") {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedPlants));
          localStorage.setItem(LAST_SYNC_KEY, Date.now().toString());
          console.info("Synced updated plant list from backend after deletion: %d plants", updatedPlants.length);
        }
        return; // Successfully synced from backend, no need to update localStorage manually
      } catch (syncError) {
        console.warn("Failed to sync from backend after deletion, updating localStorage manually:", syncError);
        // Fall through to manual localStorage update
      }
    } catch (error) {
      console.error("Failed to remove from backend, removing from localStorage only:", error);
      // Continue to remove from localStorage as fallback
    }
  }
  
  // Always remove from localStorage (fallback or mock mode)
  if (typeof window === "undefined") {
    return;
  }
  try {
    // Get current plants from localStorage directly
    let plants: ScannedPlant[] = [];
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as ScannedPlant[];
        if (Array.isArray(parsed)) {
          plants = parsed;
        }
      } catch (parseError) {
        console.warn("Failed to parse localStorage:", parseError);
      }
    }
    
    // Filter out the plant
    const filtered = plants.filter((p) => p.deviceId !== deviceId);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
    console.info("Successfully removed plant from localStorage:", { deviceId });
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

/**
 * Gets the plant type for a device ID (synchronous, from localStorage cache).
 * @param deviceId - The device ID to look up
 * @returns The plant type, or null if not found
 */
export function getPlantType(deviceId: string): string | null {
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
    return plant?.plantType ?? null;
  } catch (error) {
    console.error("Failed to read plant type from localStorage:", error);
    return null;
  }
}
