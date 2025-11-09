"use client";

import { useMemo } from "react";
import TelemetryForm from "@/components/TelemetryForm";
import TelemetryTable from "@/components/TelemetryTable";
import useTelemetryFeed from "@/hooks/useTelemetryFeed";

export default function HomePage() {
  const {
    records,
    isLoading,
    lastError,
    refresh,
    selectedDevice,
    setSelectedDevice
  } = useTelemetryFeed();

  const devices = useMemo(() => {
    const unique = new Set<string>();
    records.forEach((record) => unique.add(record.deviceId));
    return Array.from(unique).sort();
  }, [records]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-12 p-6 md:p-12">
      <header className="flex flex-col gap-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-8 shadow-card">
        <div className="flex items-center justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
            CloudIoT Telemetry Console
          </h1>
          <button
            onClick={refresh}
            className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-white shadow hover:bg-sky-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            Refresh
          </button>
        </div>
        <p className="text-sm text-slate-300 md:text-base">
          Submit new telemetry events, monitor anomaly scores, and keep tabs on
          greenhouse conditions in real time. Data is persisted to DynamoDB via
          the FastAPI service running on ECS Fargate.
        </p>
      </header>

      <section className="grid gap-8 md:grid-cols-5 md:items-start">
        <div className="md:col-span-2">
          <TelemetryForm onSubmitted={refresh} />
        </div>

        <div className="md:col-span-3 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="device-filter" className="text-sm font-medium">
              Filter device
            </label>
            <select
              id="device-filter"
              value={selectedDevice ?? ""}
              onChange={(event) =>
                setSelectedDevice(
                  event.target.value.length ? event.target.value : undefined
                )
              }
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-400 md:w-64"
            >
              <option value="">All devices</option>
              {devices.map((deviceId) => (
                <option key={deviceId} value={deviceId}>
                  {deviceId}
                </option>
              ))}
            </select>
          </div>

          <TelemetryTable
            records={records}
            isLoading={isLoading}
            lastError={lastError}
          />
        </div>
      </section>
    </main>
  );
}

