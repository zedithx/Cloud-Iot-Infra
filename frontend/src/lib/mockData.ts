import type {
  PlantSnapshot,
  PlantTimeSeries,
  PlantTimeSeriesPoint,
  TelemetryRecord
} from "@/types/telemetry";

const now = Math.floor(Date.now() / 1000);

export const MOCK_PLANTS: PlantSnapshot[] = [
  {
    plantId: "mint-princess",
    lastSeen: now - 90,
    score: 0.18,
    disease: false,
    temperatureC: 23.4,
    humidity: 68,
    soilMoisture: 0.72,
    lightLux: 15000,
    notes: "Leaves perky and aromatic."
  },
  {
    plantId: "strawberry-dream",
    lastSeen: now - 120,
    score: 0.42,
    disease: false,
    temperatureC: 25.1,
    humidity: 62,
    soilMoisture: 0.55,
    lightLux: 18000,
    notes: "Blossoms forming, keep light high."
  },
  {
    plantId: "basil-buddy",
    lastSeen: now - 45,
    score: 0.73,
    disease: true,
    temperatureC: 24.0,
    humidity: 75,
    soilMoisture: 0.88,
    lightLux: 12000,
    notes: "Yellow spots detected on lower leaves."
  }
];

function buildSeries(seed: number): PlantTimeSeriesPoint[] {
  return Array.from({ length: 24 }).map((_, index) => {
    const timestamp = now - (23 - index) * 900;
    const base = seed + index * 0.02;
    return {
      timestamp,
      temperatureC: 22 + Math.sin(index / 4) * 1.8,
      humidity: 60 + Math.cos(index / 3) * 10,
      soilMoisture: Math.min(0.95, Math.max(0.35, base % 1)),
      lightLux: 14000 + Math.sin(index / 5) * 2000,
      score: (seed + index * 0.01) % 1,
      disease: index > 18 ? true : undefined
    };
  });
}

export const MOCK_SERIES: Record<string, PlantTimeSeries> = {
  "mint-princess": {
    plantId: "mint-princess",
    points: buildSeries(0.16)
  },
  "strawberry-dream": {
    plantId: "strawberry-dream",
    points: buildSeries(0.32)
  },
  "basil-buddy": {
    plantId: "basil-buddy",
    points: buildSeries(0.68)
  }
};

export const MOCK_TELEMETRY: TelemetryRecord[] = MOCK_PLANTS.flatMap(
  (snapshot) =>
    (MOCK_SERIES[snapshot.plantId]?.points ?? []).slice(-5).map((point) => ({
      deviceId: snapshot.plantId,
      timestamp: point.timestamp,
      score: point.score ?? snapshot.score ?? 0,
      temperatureC: point.temperatureC ?? snapshot.temperatureC,
      humidity: point.humidity ?? snapshot.humidity,
      soilMoisture: point.soilMoisture ?? snapshot.soilMoisture,
      lightLux: point.lightLux ?? snapshot.lightLux,
      disease: point.disease ?? snapshot.disease ?? false,
      notes: snapshot.notes ?? null
    }))
);

