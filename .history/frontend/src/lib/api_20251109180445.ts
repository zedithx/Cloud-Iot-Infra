import axios from "axios";
import type { TelemetryPayload, TelemetryRecord } from "@/types/telemetry";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL
  ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, "")
  : "";

export const apiClient = axios.create({
  baseURL: API_BASE_URL || undefined,
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

export async function submitTelemetry(
  payload: TelemetryPayload
): Promise<TelemetryRecord> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }

  const response = await apiClient.post<TelemetryRecord>(
    "/telemetry",
    payload
  );
  return response.data;
}

export async function fetchTelemetry(
  deviceId?: string | null
): Promise<TelemetryRecord[]> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }

  const endpoint = deviceId ? `/telemetry/${deviceId}` : "/telemetry";
  const response = await apiClient.get<TelemetryRecord[]>(endpoint, {
    params: deviceId ? undefined : { limit: 50 }
  });
  return response.data;
}

