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

// Request interceptor to log all API calls
apiClient.interceptors.request.use(
  (config) => {
    const method = config.method?.toUpperCase() || "GET";
    const url = config.url || "";
    const fullUrl = config.baseURL ? `${config.baseURL}${url}` : url;
    
    console.info(`[API Request] ${method} ${fullUrl}`, {
      method,
      url: fullUrl,
      params: config.params,
      data: config.data,
      headers: config.headers
    });
    
    // Add timestamp for response timing
    (config as any).metadata = { startTime: Date.now() };
    
    return config;
  },
  (error) => {
    console.error("[API Request Error]", error);
    return Promise.reject(error);
  }
);

// Response interceptor to log all API responses
apiClient.interceptors.response.use(
  (response) => {
    const config = response.config;
    const method = config.method?.toUpperCase() || "GET";
    const url = config.url || "";
    const fullUrl = config.baseURL ? `${config.baseURL}${url}` : url;
    const duration = (config as any).metadata?.startTime 
      ? Date.now() - (config as any).metadata.startTime 
      : null;
    
    console.info(`[API Response] ${method} ${fullUrl}`, {
      status: response.status,
      statusText: response.statusText,
      duration: duration ? `${duration}ms` : "unknown",
      data: response.data,
      headers: response.headers
    });
    
    return response;
  },
  (error) => {
    if (axios.isAxiosError(error)) {
      const config = error.config;
      const method = config?.method?.toUpperCase() || "GET";
      const url = config?.url || "";
      const fullUrl = config?.baseURL ? `${config.baseURL}${url}` : url;
      const duration = config ? ((config as any).metadata?.startTime 
        ? Date.now() - (config as any).metadata.startTime 
        : null) : null;
      
      console.error(`[API Error] ${method} ${fullUrl}`, {
        status: error.response?.status,
        statusText: error.response?.statusText,
        duration: duration ? `${duration}ms` : "unknown",
        error: error.message,
        responseData: error.response?.data,
        requestData: config?.data,
        requestParams: config?.params
      });
      
      const message =
        error.response?.data?.message ||
        error.message ||
        "Unexpected API error";
      return Promise.reject(new Error(message));
    }

    console.error("[API Error - Non-Axios]", error);
    return Promise.reject(error);
  }
);

export const isMockApiEnabled = () => USE_MOCK_API;

export async function submitTelemetry(
  payload: TelemetryPayload
): Promise<TelemetryRecord> {
  if (USE_MOCK_API) {
    console.info("[API Mock] POST /telemetry", { payload });
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
    console.info("[API Mock Response] POST /telemetry", { data: synthetic });
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
    const endpoint = deviceId ? `/telemetry/${deviceId}` : "/telemetry";
    console.info(`[API Mock] GET ${endpoint}`, { deviceId });
    const result = !deviceId
      ? MOCK_TELEMETRY
      : MOCK_TELEMETRY.filter((record) => record.deviceId === deviceId);
    console.info(`[API Mock Response] GET ${endpoint}`, { 
      count: result.length, 
      data: result 
    });
    return result;
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
    console.info("[API Mock] GET /plants");
    console.info("[API Mock Response] GET /plants", { 
      count: MOCK_PLANTS.length, 
      data: MOCK_PLANTS 
    });
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
    console.info(`[API Mock] GET /plants/${plantId}`, { plantId });
    const plant = MOCK_PLANTS.find((item) => item.plantId === plantId);
    if (!plant) {
      console.error(`[API Mock Error] GET /plants/${plantId} - Plant not found`);
      throw new Error("Plant not found in mock data");
    }
    console.info(`[API Mock Response] GET /plants/${plantId}`, { data: plant });
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
    console.info(`[API Mock] GET /plants/${plantId}/timeseries`, { plantId, options });
    const result = MOCK_SERIES[plantId] ?? {
        plantId,
        points: []
    };
    console.info(`[API Mock Response] GET /plants/${plantId}/timeseries`, { 
      pointsCount: result.points.length, 
      data: result 
    });
    return result;
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

export type ActuatorCommand = {
  actuator: "pump" | "fan" | "lights";
  targetValue: number;
  metric: "soilMoisture" | "temperatureC" | "lightLux";
};

export async function sendActuatorCommand(
  deviceId: string,
  command: ActuatorCommand
): Promise<{ deviceId: string; command: ActuatorCommand; topic: string; status: string }> {
  if (USE_MOCK_API) {
    console.info(`[API Mock] POST /devices/${deviceId}/actuators`, { deviceId, command });
    const result = {
      deviceId,
      command,
      topic: `leaf/commands/${deviceId}`,
      status: "sent"
    };
    console.info(`[API Mock Response] POST /devices/${deviceId}/actuators`, { data: result });
    return result;
  }

  try {
    const response = await apiClient.post<{
      deviceId: string;
      command: ActuatorCommand;
      topic: string;
      status: string;
    }>(`/devices/${deviceId}/actuators`, command);
    return response.data;
  } catch (error) {
    console.error("Failed to send actuator command", error);
    throw error;
  }
}

export type PlantMetrics = {
  plantType: string;
  temperatureC: { min: number; max: number };
  humidity: { min: number; max: number };
  soilMoisture: { min: number; max: number };
  lightLux: { min: number; max: number };
};

export async function getPlantTypeMetrics(
  plantType: string
): Promise<PlantMetrics> {
  if (USE_MOCK_API) {
    console.info(`[API Mock] GET /plant-types/${plantType}`, { plantType });
    // Mock response - use frontend plant profiles
    const profiles = await import("@/lib/plantProfiles");
    const profile = profiles.PLANT_PROFILES.find((p) => p.id === plantType);
    if (!profile) {
      console.error(`[API Mock Error] GET /plant-types/${plantType} - Plant type not found`);
      throw new Error(`Plant type '${plantType}' not found`);
    }
    const result = {
      plantType: profile.id,
      temperatureC: {
        min: profile.metrics.temperatureC.min,
        max: profile.metrics.temperatureC.max,
      },
      humidity: {
        min: profile.metrics.humidity.min,
        max: profile.metrics.humidity.max,
      },
      soilMoisture: {
        min: profile.metrics.soilMoisture.min,
        max: profile.metrics.soilMoisture.max,
      },
      lightLux: {
        min: profile.metrics.lightLux.min,
        max: profile.metrics.lightLux.max,
      },
    };
    console.info(`[API Mock Response] GET /plant-types/${plantType}`, { data: result });
    return result;
  }

  try {
    const response = await apiClient.get<PlantMetrics>(
      `/plant-types/${plantType}`
    );
    return response.data;
  } catch (error) {
    console.error("Failed to get plant type metrics", error);
    throw error;
  }
}

export async function setDevicePlantType(
  deviceId: string,
  plantType: string
): Promise<{ deviceId: string; plantType: string; status: string }> {
  if (USE_MOCK_API) {
    console.info(`[API Mock] POST /devices/${deviceId}/plant-type`, { deviceId, plantType });
    const result = {
      deviceId,
      plantType,
      status: "set",
    };
    console.info(`[API Mock Response] POST /devices/${deviceId}/plant-type`, { data: result });
    return result;
  }

  try {
    const response = await apiClient.post<{
      deviceId: string;
      plantType: string;
      status: string;
    }>(`/devices/${deviceId}/plant-type`, { plantType });
    return response.data;
  } catch (error) {
    console.error("Failed to set device plant type", error);
    throw error;
  }
}

export type ScannedPlant = {
  deviceId: string;
  plantName: string;
};

export async function fetchScannedPlants(): Promise<ScannedPlant[]> {
  if (USE_MOCK_API) {
    // Return empty array for mock - plants come from localStorage in mock mode
    return [];
  }

  try {
    const response = await apiClient.get<ScannedPlant[]>("/scanned-plants");
    return response.data;
  } catch (error) {
    console.error("Failed to fetch scanned plants", error);
    throw error;
  }
}

export async function addScannedPlantToBackend(
  deviceId: string,
  plantName: string
): Promise<ScannedPlant> {
  if (USE_MOCK_API) {
    // In mock mode, just return the data (localStorage handles it)
    return { deviceId, plantName };
  }

  try {
    const response = await apiClient.post<ScannedPlant>("/scanned-plants", {
      deviceId,
      plantName,
    });
    return response.data;
  } catch (error) {
    console.error("Failed to add scanned plant to backend", error);
    throw error;
  }
}

export async function removeScannedPlantFromBackend(
  deviceId: string
): Promise<void> {
  if (USE_MOCK_API) {
    // In mock mode, localStorage handles it
    return;
  }

  try {
    await apiClient.delete(`/scanned-plants/${deviceId}`);
  } catch (error) {
    console.error("Failed to remove scanned plant from backend", error);
    throw error;
  }
}

