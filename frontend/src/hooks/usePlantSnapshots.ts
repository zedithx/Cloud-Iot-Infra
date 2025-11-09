import { useCallback, useEffect, useState } from "react";
import { fetchPlants, isMockApiEnabled } from "@/lib/api";
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
      const payload = await fetchPlants();
      payload.sort((a, b) => a.plantId.localeCompare(b.plantId));
      setPlants(payload);
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

