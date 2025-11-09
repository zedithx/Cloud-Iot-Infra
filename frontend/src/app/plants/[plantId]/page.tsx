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
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-4 pb-16 pt-8 sm:px-6 md:gap-10 md:px-12">
      <nav className="flex flex-wrap items-center justify-between gap-4 text-xs text-emerald-700 sm:text-sm">
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
            className="rounded-full border border-emerald-200 bg-sprout-100 px-4 py-1.5 text-xs font-medium text-emerald-700 hover:bg-sprout-200 sm:text-sm"
          >
            Refresh plant
          </button>
        </div>
      </nav>

      <header className="card-surface flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-3">
          <span className={`pill ${summary.statusTone} text-[0.65rem] sm:text-xs`}>
            {summary.statusLabel}
          </span>
          <h1 className="text-3xl font-semibold text-emerald-900 sm:text-4xl md:text-5xl">
            {plantId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </h1>
          <p className="text-sm text-emerald-700">
            Latest reading: <strong>{summary.lastSeen}</strong>
          </p>
        </div>
        <div className="grid gap-3 text-sm text-emerald-700 min-[460px]:grid-cols-2">
          <div className="flex flex-col gap-1.5 rounded-3xl border border-emerald-200 bg-white px-4 py-3">
            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-emerald-500 sm:text-xs">
              Disease risk
            </p>
            <p className="text-3xl font-semibold text-emerald-900">
              {snapshot?.score !== undefined && snapshot?.score !== null
                ? `${Math.round(snapshot.score * 100)}%`
                : "—"}
            </p>
          </div>
          <div className="flex flex-col gap-1.5 rounded-3xl border border-emerald-200 bg-white px-4 py-3">
            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-emerald-500 sm:text-xs">
              Soil moisture
            </p>
            <p className="text-3xl font-semibold text-emerald-900">
              {snapshot?.soilMoisture !== undefined &&
              snapshot?.soilMoisture !== null
                ? `${Math.round(snapshot.soilMoisture * 100)}%`
                : "—"}
            </p>
          </div>
        </div>
      </header>

      {error && (
        <div className="rounded-3xl border border-rose-200 bg-rose-50/80 p-5 text-sm text-rose-600 shadow-card sm:p-6">
          {error}
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:gap-6">
          <div className="h-64 animate-pulse rounded-3xl bg-white/60 sm:h-80" />
          <div className="h-40 animate-pulse rounded-3xl bg-white/60 sm:h-48" />
        </div>
      )}

      {!isLoading && snapshot && (
        <div className="grid gap-6 lg:grid-cols-[2fr,1fr]">
          <div className="space-y-6">
            <TimeseriesChart points={series} />

            <section className="card-surface">
              <h3 className="mb-4 flex items-center gap-2 text-base font-semibold text-emerald-900 sm:text-lg">
                <span aria-hidden>📋</span>
                Recent readings
              </h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-emerald-100 text-xs text-emerald-800 sm:text-sm">
                  <thead className="text-left text-[0.65rem] uppercase tracking-wide text-emerald-500 sm:text-xs">
                    <tr>
                      <th className="px-2 py-2 sm:px-3">Time</th>
                      <th className="px-2 py-2 sm:px-3">Temp °C</th>
                      <th className="px-2 py-2 sm:px-3">Humidity %</th>
                      <th className="px-2 py-2 sm:px-3">Soil</th>
                      <th className="px-2 py-2 sm:px-3">Light lux</th>
                      <th className="px-2 py-2 sm:px-3">Disease</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-emerald-50">
                    {series
                      .slice()
                      .reverse()
                      .slice(0, 12)
                      .map((point) => (
                        <tr key={point.timestamp}>
                          <td className="whitespace-nowrap px-2 py-2 sm:px-3">
                            {format(point.timestamp * 1000, "PPpp")}
                          </td>
                          <td className="px-2 py-2 sm:px-3">
                            {formatMetric(point.temperatureC, "°C")}
                          </td>
                          <td className="px-2 py-2 sm:px-3">
                            {formatMetric(point.humidity, "%", 0)}
                          </td>
                          <td className="px-2 py-2 sm:px-3">
                            {point.soilMoisture !== undefined &&
                            point.soilMoisture !== null
                              ? `${Math.round(point.soilMoisture * 100)}%`
                              : "—"}
                          </td>
                          <td className="px-2 py-2 sm:px-3">
                            {formatMetric(point.lightLux, " lx")}
                          </td>
                          <td className="px-2 py-2 sm:px-3">
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

