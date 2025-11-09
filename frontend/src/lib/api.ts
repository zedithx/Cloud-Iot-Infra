import axios from "axios";
import type {
  PlantSnapshot,
  PlantTimeSeries,
  TelemetryPayload,
  TelemetryRecord
} from "@/types/telemetry";
import {
  MOCK_PLANTS,
  MOCK_SERIES,
  MOCK_TELEMETRY
} from "@/lib/mockData";

const ENV_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
const LOCAL_FALLBACK = process.env.NEXT_PUBLIC_LOCAL_API_BASE_URL;
const DEFAULT_LOCALHOST = "http://localhost:8000";

const API_BASE_URL = (ENV_BASE_URL ?? LOCAL_FALLBACK ?? DEFAULT_LOCALHOST).replace(
  /\/$/,
  ""
);

const explicitMockFlag = process.env.NEXT_PUBLIC_USE_MOCK_API;
const USE_MOCK_API =
  explicitMockFlag === "true" ||
  (!ENV_BASE_URL && explicitMockFlag !== "false");

export const apiBaseUrl = USE_MOCK_API ? "mock" : API_BASE_URL;

export const apiClient = axios.create({
  baseURL: USE_MOCK_API ? undefined : API_BASE_URL,
  timeout: 10_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json"
  }
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error)) {
      const message =
        error.response?.data?.message ||
        error.message ||
        "Unexpected API error";
      return Promise.reject(new Error(message));
    }

    return Promise.reject(error);
  }
);

export const isMockApiEnabled = () => USE_MOCK_API;

export async function submitTelemetry(
  payload: TelemetryPayload
): Promise<TelemetryRecord> {
  if (USE_MOCK_API) {
    const synthetic: TelemetryRecord = {
      deviceId: payload.deviceId,
      timestamp: Math.floor(Date.now() / 1000),
      score: payload.score,
      temperatureC: payload.temperatureC ?? null,
      humidity: payload.humidity ?? null,
      soilMoisture: payload.soilMoisture ?? null,
      lightLux: payload.lightLux ?? null,
      disease:
        payload.disease !== undefined
          ? payload.disease
          : payload.score >= 0.7,
      notes: payload.notes ?? null
    };
    return synthetic;
  }

  try {
    const response = await apiClient.post<TelemetryRecord>(
      "/telemetry",
      payload
    );
    return response.data;
  } catch (error) {
    console.warn("Falling back to mock telemetry submission", error);
    return {
      deviceId: payload.deviceId,
      timestamp: Math.floor(Date.now() / 1000),
      score: payload.score,
      temperatureC: payload.temperatureC ?? null,
      humidity: payload.humidity ?? null,
      soilMoisture: payload.soilMoisture ?? null,
      lightLux: payload.lightLux ?? null,
      disease:
        payload.disease !== undefined
          ? payload.disease
          : payload.score >= 0.7,
      notes: payload.notes ?? null
    };
  }
}

export async function fetchTelemetry(
  deviceId?: string | null
): Promise<TelemetryRecord[]> {
  if (USE_MOCK_API) {
    if (!deviceId) {
      return MOCK_TELEMETRY;
    }
    return MOCK_TELEMETRY.filter(
      (record) => record.deviceId === deviceId
    );
  }

  try {
    const endpoint = deviceId ? `/telemetry/${deviceId}` : "/telemetry";
    const response = await apiClient.get<TelemetryRecord[]>(endpoint, {
      params: deviceId ? undefined : { limit: 50 }
    });
    return response.data;
  } catch (error) {
    console.warn("Falling back to mock telemetry list", error);
    return deviceId
      ? MOCK_TELEMETRY.filter((record) => record.deviceId === deviceId)
      : MOCK_TELEMETRY;
  }
}

export async function fetchPlants(): Promise<PlantSnapshot[]> {
  if (USE_MOCK_API) {
    return MOCK_PLANTS;
  }
  try {
    const response = await apiClient.get<PlantSnapshot[]>("/plants");
    return response.data;
  } catch (error) {
    console.warn("Falling back to mock plant snapshots", error);
    return MOCK_PLANTS;
  }
}

export async function fetchPlantDetail(
  plantId: string
): Promise<PlantSnapshot> {
  if (USE_MOCK_API) {
    const plant = MOCK_PLANTS.find((item) => item.plantId === plantId);
    if (!plant) {
      throw new Error("Plant not found in mock data");
    }
    return plant;
  }
  try {
    const response = await apiClient.get<PlantSnapshot>(`/plants/${plantId}`);
    return response.data;
  } catch (error) {
    console.warn("Falling back to mock plant detail", error);
    const fallback =
      MOCK_PLANTS.find((item) => item.plantId === plantId) ??
      MOCK_PLANTS[0];
    return fallback;
  }
}

export async function fetchPlantSeries(
  plantId: string,
  options?: { limit?: number; start?: number; end?: number }
): Promise<PlantTimeSeries> {
  if (USE_MOCK_API) {
    return (
      MOCK_SERIES[plantId] ?? {
        plantId,
        points: []
      }
    );
  }
  try {
    const response = await apiClient.get<PlantTimeSeries>(
      `/plants/${plantId}/timeseries`,
      {
        params: {
          limit: options?.limit,
          start: options?.start,
          end: options?.end
        }
      }
    );
    return response.data;
  } catch (error) {
    console.warn("Falling back to mock plant series", error);
    return (
      MOCK_SERIES[plantId] ?? {
        plantId,
        points: []
      }
    );
  }
}

