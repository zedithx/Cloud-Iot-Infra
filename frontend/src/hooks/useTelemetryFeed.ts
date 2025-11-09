import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchTelemetry } from "@/lib/api";
import type { TelemetryRecord } from "@/types/telemetry";

type UseTelemetryFeedResult = {
  records: TelemetryRecord[];
  isLoading: boolean;
  lastError?: string;
  refresh: () => Promise<void>;
  selectedDevice?: string;
  setSelectedDevice: (deviceId?: string) => void;
};

export default function useTelemetryFeed(): UseTelemetryFeedResult {
  const [records, setRecords] = useState<TelemetryRecord[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>();

  const load = useCallback(
    async (deviceId?: string) => {
      setIsLoading(true);
      setError(undefined);
      try {
        const data = await fetchTelemetry(deviceId);
        // Sort descending by timestamp
        data.sort((a, b) => b.timestamp - a.timestamp);
        setRecords(data);
      } catch (err) {
        const message =
          typeof err === "object" && err && "message" in err
            ? String((err as { message: unknown }).message)
            : "Failed to load telemetry.";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    void load(selectedDevice);
  }, [selectedDevice, load]);

  const refresh = useCallback(async () => {
    await load(selectedDevice);
  }, [selectedDevice, load]);

  const sortedRecords = useMemo(() => records, [records]);

  return {
    records: sortedRecords,
    isLoading,
    lastError: error,
    refresh,
    selectedDevice,
    setSelectedDevice
  };
}

