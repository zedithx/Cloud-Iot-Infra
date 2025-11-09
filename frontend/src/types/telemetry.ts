export type TelemetryRecord = {
  deviceId: string;
  timestamp: number;
  score: number;
  temperatureC?: number | null;
  humidity?: number | null;
  notes?: string | null;
};

export type TelemetryPayload = {
  deviceId: string;
  score: number;
  temperatureC?: number;
  humidity?: number;
  notes?: string;
};

