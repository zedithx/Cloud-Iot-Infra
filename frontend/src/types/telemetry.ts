export type TelemetryRecord = {
  deviceId: string;
  timestamp: number;
  score: number;
  temperatureC?: number | null;
  humidity?: number | null;
  soilMoisture?: number | null;
  lightLux?: number | null;
  disease?: boolean | null;
  notes?: string | null;
};

export type TelemetryPayload = {
  deviceId: string;
  score: number;
  temperatureC?: number;
  humidity?: number;
  soilMoisture?: number;
  lightLux?: number;
  disease?: boolean;
  notes?: string;
};

export type PlantSnapshot = {
  plantId: string;
  lastSeen: number;
  score?: number | null;
  disease?: boolean | null;
  temperatureC?: number | null;
  humidity?: number | null;
  soilMoisture?: number | null;
  lightLux?: number | null;
  notes?: string | null;
};

export type PlantTimeSeriesPoint = {
  timestamp: number;
  score?: number | null;
  disease?: boolean | null;
  temperatureC?: number | null;
  humidity?: number | null;
  soilMoisture?: number | null;
  lightLux?: number | null;
};

export type PlantTimeSeries = {
  plantId: string;
  points: PlantTimeSeriesPoint[];
};

