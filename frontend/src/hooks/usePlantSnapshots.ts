import { useCallback, useEffect, useState } from "react";
import { fetchPlants, isMockApiEnabled } from "@/lib/api";
import { getScannedPlants } from "@/lib/localStorage";
import type { PlantSnapshot } from "@/types/telemetry";

type UsePlantSnapshotsResult = {
  plants: PlantSnapshot[];
  isLoading: boolean;
  error?: string;
  refresh: () => Promise<void>;
  isMocked: boolean;
};

export default function usePlantSnapshots(): UsePlantSnapshotsResult {
  const [plants, setPlants] = useState<PlantSnapshot[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(undefined);
    try {
      // Get scanned plants from localStorage (only show scanned plants)
      const scannedPlants = getScannedPlants();
      
      if (scannedPlants.length === 0) {
        setPlants([]);
        setIsLoading(false);
        return;
      }
      
      // Fetch plants from API to get data for scanned plants
      const apiPlants = await fetchPlants();
      const apiPlantsMap = new Map<string, PlantSnapshot>();
      for (const plant of apiPlants) {
        apiPlantsMap.set(plant.plantId, plant);
      }
      
      // Build list of only scanned plants, with API data if available
      const result: PlantSnapshot[] = [];
      for (const scanned of scannedPlants) {
        const apiPlant = apiPlantsMap.get(scanned.deviceId);
        if (apiPlant) {
          // Use API data if available
          result.push(apiPlant);
        } else {
          // Create placeholder for scanned plant without API data
          const placeholder: PlantSnapshot = {
            plantId: scanned.deviceId,
            lastSeen: 0,
            score: null,
            disease: null,
            temperatureC: null,
            humidity: null,
            soilMoisture: null,
            lightLux: null,
            notes: null,
          };
          result.push(placeholder);
        }
      }
      
      // Sort plants
      result.sort((a, b) => a.plantId.localeCompare(b.plantId));
      setPlants(result);
    } catch (err) {
      const message =
        typeof err === "object" && err && "message" in err
          ? String((err as { message: unknown }).message)
          : "Unable to load plants.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    plants,
    isLoading,
    error,
    refresh: load,
    isMocked: isMockApiEnabled()
  };
}

