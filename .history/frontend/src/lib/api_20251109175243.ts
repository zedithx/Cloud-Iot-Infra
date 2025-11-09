import type {
  TelemetryPayload,
  TelemetryRecord
} from "@/types/telemetry";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL
  ? process.env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, "")
  : "";

type ApiError = {
  message: string;
  status?: number;
};

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.message === "string") {
        message = body.message;
      }
    } catch {
      // ignore
    }
    const error: ApiError = { message, status: response.status };
    throw error;
  }

  return (await response.json()) as T;
}

export async function submitTelemetry(
  payload: TelemetryPayload
): Promise<TelemetryRecord> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }
  const endpoint = `${API_BASE_URL}/telemetry`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  return handleResponse<TelemetryRecord>(response);
}

export async function fetchTelemetry(
  deviceId?: string | null
): Promise<TelemetryRecord[]> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }
  const suffix = deviceId ? `/${encodeURIComponent(deviceId)}` : "";
  const endpoint = `${API_BASE_URL}/telemetry${suffix}`;
  const response = await fetch(endpoint, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    },
    cache: "no-store"
  });

  return handleResponse<TelemetryRecord[]>(response);
}

