import { useCallback, useEffect, useState } from "react";
import {
  fetchPlantDetail,
  fetchPlantSeries,
  isMockApiEnabled
} from "@/lib/api";
import type {
  PlantSnapshot,
  PlantTimeSeriesPoint
} from "@/types/telemetry";

type UsePlantDetailResult = {
  snapshot?: PlantSnapshot;
  series: PlantTimeSeriesPoint[];
  isLoading: boolean;
  error?: string;
  refresh: () => Promise<void>;
  isMocked: boolean;
};

export default function usePlantDetail(
  plantId: string
): UsePlantDetailResult {
  const [snapshot, setSnapshot] = useState<PlantSnapshot>();
  const [series, setSeries] = useState<PlantTimeSeriesPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(undefined);
    try {
      const [detail, timeseries] = await Promise.all([
        fetchPlantDetail(plantId),
        fetchPlantSeries(plantId, { limit: 200 })
      ]);
      setSnapshot(detail);
      setSeries(timeseries.points ?? []);
    } catch (err) {
      const message =
        typeof err === "object" && err && "message" in err
          ? String((err as { message: unknown }).message)
          : "Failed to load plant data.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [plantId]);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    snapshot,
    series,
    isLoading,
    error,
    refresh: load,
    isMocked: isMockApiEnabled()
  };
}

