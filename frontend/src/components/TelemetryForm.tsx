"use client";

import { useCallback, useMemo, useState } from "react";
import { submitTelemetry } from "@/lib/api";
import type { TelemetryPayload } from "@/types/telemetry";

type TelemetryFormProps = {
  onSubmitted?: () => void;
};

type FormState = TelemetryPayload & {
  humidity?: number | "";
  temperatureC?: number | "";
};

const API_READY = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

const initialState: FormState = {
  deviceId: "",
  score: 0.5,
  temperatureC: "",
  humidity: "",
  notes: ""
};

export default function TelemetryForm({ onSubmitted }: TelemetryFormProps) {
  const [form, setForm] = useState<FormState>(initialState);
  const [isSubmitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string>();
  const [error, setError] = useState<string>();

  const isValid = useMemo(() => {
    if (!form.deviceId.trim()) {
      return false;
    }
    return form.score >= 0 && form.score <= 1;
  }, [form.deviceId, form.score]);

  const handleChange = useCallback(
    (key: keyof FormState) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value = event.target.value;
      if (key === "score") {
        setForm((prev) => ({ ...prev, [key]: Number(value) }));
        return;
      }
      if (key === "temperatureC" || key === "humidity") {
        setForm((prev) => ({
          ...prev,
          [key]: value === "" ? "" : Number(value)
        }));
        return;
      }

      setForm((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!isValid || isSubmitting) {
        return;
      }

      setSubmitting(true);
      setMessage(undefined);
      setError(undefined);

      const payload: TelemetryPayload = {
        deviceId: form.deviceId.trim(),
        score: Number(form.score),
        temperatureC:
          form.temperatureC === "" ? undefined : Number(form.temperatureC),
        humidity: form.humidity === "" ? undefined : Number(form.humidity),
        notes: form.notes?.trim() || undefined
      };

      try {
        await submitTelemetry(payload);
        setMessage("Telemetry submitted successfully.");
        setForm(initialState);
        if (onSubmitted) {
          onSubmitted();
        }
      } catch (err) {
        const description =
          typeof err === "object" && err && "message" in err
            ? String((err as { message: unknown }).message)
            : "Failed to submit telemetry.";
        setError(description);
      } finally {
        setSubmitting(false);
      }
    },
    [form, isSubmitting, isValid, onSubmitted]
  );

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-6 shadow-card"
    >
      <div>
        <h2 className="text-xl font-semibold">Submit telemetry</h2>
        <p className="mt-1 text-sm text-slate-300">
          Values are forwarded to the FastAPI service which persists them in
          DynamoDB.
        </p>
      </div>

      <label className="flex flex-col gap-2 text-sm">
        <span className="font-medium">Device ID</span>
        <input
          name="deviceId"
          required
          autoComplete="off"
          placeholder="e.g. rpi-01"
          value={form.deviceId}
          onChange={handleChange("deviceId")}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-400"
        />
      </label>

      <label className="flex flex-col gap-2 text-sm">
        <span className="font-medium flex items-center justify-between">
          <span>Anomaly score</span>
          <span className="text-xs text-slate-400">
            {Math.round(form.score * 100)}%
          </span>
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={form.score}
          onChange={handleChange("score")}
          className="accent-sky-400"
        />
      </label>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="flex flex-col gap-2 text-sm">
          <span className="font-medium">Temperature (°C)</span>
          <input
          type="number"
          inputMode="decimal"
          placeholder="Optional"
          value={form.temperatureC}
          onChange={handleChange("temperatureC")}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-400"
        />
        </label>
        <label className="flex flex-col gap-2 text-sm">
          <span className="font-medium">Humidity (%)</span>
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={100}
            placeholder="Optional"
            value={form.humidity}
            onChange={handleChange("humidity")}
            className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-400"
          />
        </label>
      </div>

      <label className="flex flex-col gap-2 text-sm">
        <span className="font-medium">Notes</span>
        <textarea
          rows={3}
          placeholder="Optional description or experiment notes"
          value={form.notes}
          onChange={handleChange("notes")}
          className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-400"
        />
      </label>

      <button
        type="submit"
        disabled={!isValid || isSubmitting || !API_READY}
        className="mt-2 inline-flex items-center justify-center rounded-md bg-sky-500 px-4 py-2 text-sm font-medium text-white shadow hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700"
      >
        {isSubmitting ? "Submitting..." : "Submit telemetry"}
      </button>

      {message && (
        <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300">
          {message}
        </p>
      )}
      {error && (
        <p className="rounded-md border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-300">
          {error}
        </p>
      )}
      {!API_READY && (
        <p className="text-xs text-amber-300">
          Set <code className="font-mono">NEXT_PUBLIC_API_BASE_URL</code> in{" "}
          <code className="font-mono">.env.local</code> to enable submissions.
        </p>
      )}
    </form>
  );
}

