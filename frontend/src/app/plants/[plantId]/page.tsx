"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useParams } from "next/navigation";
import { format, formatDistanceToNow } from "date-fns";
import ControlPanel from "@/components/ControlPanel";
import TimeseriesChart from "@/components/TimeseriesChart";
import usePlantDetail from "@/hooks/usePlantDetail";

function formatMetric(
  value?: number | null,
  suffix = "",
  decimals = 1
): string {
  if (value === undefined || value === null) {
    return "—";
  }
  const formatted = Number.isInteger(value)
    ? value.toString()
    : value.toFixed(decimals);
  return suffix.length ? `${formatted}${suffix}` : formatted;
}

export default function PlantDetailPage() {
  const params = useParams<{ plantId: string }>();
  const plantId = decodeURIComponent(params.plantId);
  const { snapshot, series, isLoading, error, refresh, isMocked } =
    usePlantDetail(plantId);

  const summary = useMemo(() => {
    if (!snapshot) {
      return {
        lastSeen: "Never",
        statusLabel: "Loading",
        statusTone: "bg-bloom-100 text-bloom-500"
      };
    }
    return {
      lastSeen: snapshot.lastSeen
        ? formatDistanceToNow(snapshot.lastSeen * 1000, { addSuffix: true })
        : "Unknown",
      statusLabel:
        snapshot.disease === true
          ? "Needs attention"
          : snapshot.disease === false
            ? "Healthy"
            : "Monitoring",
      statusTone:
        snapshot.disease === true
          ? "bg-rose-100 text-rose-600"
          : snapshot.disease === false
            ? "bg-emerald-100 text-emerald-700"
            : "bg-bloom-100 text-bloom-500"
    };
  }, [snapshot]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-10 p-6 md:p-12">
      <nav className="flex flex-wrap items-center justify-between gap-4 text-sm text-emerald-700">
        <Link href="/" className="hover:text-emerald-500">
          ← Back to overview
        </Link>
        <div className="flex items-center gap-3">
          {isMocked && (
            <span className="inline-flex items-center gap-2 rounded-full bg-bloom-100 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-bloom-500 shadow">
              <span aria-hidden>🎈</span> Demo mode
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            className="rounded-full border border-emerald-200 bg-sprout-100 px-4 py-1.5 font-medium text-emerald-700 hover:bg-sprout-200"
          >
            Refresh plant
          </button>
        </div>
      </nav>

      <header className="card-surface flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div>
          <span className={`pill ${summary.statusTone}`}>
            {summary.statusLabel}
          </span>
          <h1 className="mt-3 text-4xl font-semibold text-emerald-900 md:text-5xl">
            {plantId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </h1>
          <p className="mt-3 text-sm text-emerald-700">
            Latest reading: <strong>{summary.lastSeen}</strong>
          </p>
        </div>
        <div className="grid gap-4 text-sm text-emerald-700 md:grid-cols-2">
          <div className="flex flex-col gap-2 rounded-3xl border border-emerald-200 bg-white px-4 py-3">
            <p className="text-xs uppercase tracking-widest text-emerald-500">
              Disease risk
            </p>
            <p className="mt-2 text-3xl font-semibold text-emerald-900">
              {snapshot?.score !== undefined && snapshot?.score !== null
                ? `${Math.round(snapshot.score * 100)}%`
                : "—"}
            </p>
          </div>
          <div className="flex flex-col gap-2 rounded-3xl border border-emerald-200 bg-white px-4 py-3">
            <p className="text-xs uppercase tracking-widest text-emerald-500">
              Soil moisture
            </p>
            <p className="mt-2 text-3xl font-semibold text-emerald-900">
              {snapshot?.soilMoisture !== undefined &&
              snapshot?.soilMoisture !== null
                ? `${Math.round(snapshot.soilMoisture * 100)}%`
                : "—"}
            </p>
          </div>
        </div>
      </header>

      {error && (
        <div className="rounded-3xl border border-rose-200 bg-rose-50/80 p-6 text-sm text-rose-600 shadow-card">
          {error}
        </div>
      )}

      {isLoading && (
        <div className="grid gap-6">
          <div className="h-80 animate-pulse rounded-3xl bg-white/60" />
          <div className="h-48 animate-pulse rounded-3xl bg-white/60" />
        </div>
      )}

      {!isLoading && snapshot && (
        <div className="grid gap-8 lg:grid-cols-[2fr,1fr]">
          <div className="space-y-6">
            <TimeseriesChart points={series} />

            <section className="card-surface">
              <h3 className="mb-4 text-lg font-semibold text-emerald-900">
                Recent readings
              </h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-emerald-100 text-sm text-emerald-800">
                  <thead className="text-left text-xs uppercase tracking-wide text-emerald-500">
                    <tr>
                      <th className="px-3 py-2">Time</th>
                      <th className="px-3 py-2">Temp °C</th>
                      <th className="px-3 py-2">Humidity %</th>
                      <th className="px-3 py-2">Soil</th>
                      <th className="px-3 py-2">Light lux</th>
                      <th className="px-3 py-2">Disease</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-emerald-50">
                    {series
                      .slice()
                      .reverse()
                      .slice(0, 12)
                      .map((point) => (
                        <tr key={point.timestamp}>
                          <td className="px-3 py-2">
                            {format(point.timestamp * 1000, "PPpp")}
                          </td>
                          <td className="px-3 py-2">
                            {formatMetric(point.temperatureC, "°C")}
                          </td>
                          <td className="px-3 py-2">
                            {formatMetric(point.humidity, "%", 0)}
                          </td>
                          <td className="px-3 py-2">
                            {point.soilMoisture !== undefined &&
                            point.soilMoisture !== null
                              ? `${Math.round(point.soilMoisture * 100)}%`
                              : "—"}
                          </td>
                          <td className="px-3 py-2">
                            {formatMetric(point.lightLux, " lx")}
                          </td>
                          <td className="px-3 py-2">
                            {(point.disease ?? false) ? "⚠︎" : "✓"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
          <ControlPanel plantId={plantId} />
        </div>
      )}
    </main>
  );
}

