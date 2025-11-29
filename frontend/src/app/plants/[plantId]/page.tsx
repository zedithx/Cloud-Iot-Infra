"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { format, formatDistanceToNow } from "date-fns";
import toast from "react-hot-toast";
import ControlPanel from "@/components/ControlPanel";
import TimeseriesChart from "@/components/TimeseriesChart";
import DiseaseRiskChart from "@/components/DiseaseRiskChart";
import usePlantDetail from "@/hooks/usePlantDetail";
import {
  PLANT_PROFILES,
  guessProfileId,
  type PlantMetricRange,
  type PlantProfile
} from "@/lib/plantProfiles";
import { setDevicePlantType } from "@/lib/api";
import { getPlantName } from "@/lib/localStorage";

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
  const [selectedProfileId, setSelectedProfileId] = useState<string>(
    guessProfileId(plantId) ?? PLANT_PROFILES[0].id
  );
  const [isLocked, setIsLocked] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [lockError, setLockError] = useState<string | null>(null);
  const [lockSuccess, setLockSuccess] = useState<boolean>(false);
  const [recentReadingsTab, setRecentReadingsTab] = useState<"disease" | "metrics">("metrics");

  // Get custom plant name from localStorage, fallback to formatted device ID
  const displayName = useMemo(() => {
    const customName = getPlantName(plantId);
    if (customName) {
      return customName;
    }
    return plantId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }, [plantId]);

  const selectedProfile: PlantProfile = useMemo(
    () =>
      PLANT_PROFILES.find((profile) => profile.id === selectedProfileId) ??
      PLANT_PROFILES[0],
    [selectedProfileId]
  );

  // Filter series into metrics (telemetry) and disease points
  const metricsSeries = useMemo(() => {
    return series.filter(
      (point) =>
        (point.temperatureC !== null && point.temperatureC !== undefined) ||
        (point.humidity !== null && point.humidity !== undefined) ||
        (point.soilMoisture !== null && point.soilMoisture !== undefined) ||
        (point.lightLux !== null && point.lightLux !== undefined)
    );
  }, [series]);

  const diseaseSeries = useMemo(() => {
    return series.filter(
      (point) =>
        point.score !== null && point.score !== undefined
    );
  }, [series]);

  const recentAverages = useMemo(() => {
    if (!metricsSeries.length) {
      return {};
    }
    const lookback = metricsSeries.slice(-8);
    const averageFor = (key: keyof typeof lookback[number]) => {
      const values = lookback
        .map((point) => point[key])
        .filter(
          (value): value is number =>
            typeof value === "number" && Number.isFinite(value)
        );
      if (!values.length) {
        return undefined;
      }
      return (
        values.reduce((total, value) => total + value, 0) / values.length
      );
    };

    return {
      temperatureC: averageFor("temperatureC"),
      humidity: averageFor("humidity"),
      soilMoisture: averageFor("soilMoisture"),
      lightLux: averageFor("lightLux")
    } as Record<string, number | undefined>;
  }, [metricsSeries]);

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

  const metricComparisons = useMemo(() => {
    const asDisplay = (
      key: "temperatureC" | "humidity" | "soilMoisture" | "lightLux",
      value?: number | null
    ): string => {
      if (value === undefined || value === null) {
        return "No data";
      }
      if (key === "temperatureC") {
        return `${value.toFixed(1)} °C`;
      }
      if (key === "humidity") {
        return `${Math.round(value)} %`;
      }
      if (key === "soilMoisture") {
        return `${Math.round(value * 100)} %`;
      }
      return `${Math.round(value).toLocaleString()} lux`;
    };

    const withinRange = (
      key: "temperatureC" | "humidity" | "soilMoisture" | "lightLux",
      range: PlantMetricRange,
      value?: number | null
    ): "ideal" | "low" | "high" | "unknown" => {
      if (value === undefined || value === null) {
        return "unknown";
      }
      const effectiveValue =
        key === "soilMoisture" ? value : value; // stored as fraction already
      if (effectiveValue < range.min) {
        return "low";
      }
      if (effectiveValue > range.max) {
        return "high";
      }
      return "ideal";
    };

    const sourceValue = (
      key: "temperatureC" | "humidity" | "soilMoisture" | "lightLux"
    ) =>
      snapshot?.[key] ??
      (recentAverages as Record<string, number | undefined>)[key] ??
      null;

    return [
      {
        key: "temperatureC" as const,
        label: "Temperature",
        rangeDisplay: `${selectedProfile.metrics.temperatureC.min.toFixed(0)}–${selectedProfile.metrics.temperatureC.max.toFixed(0)} °C`,
        status: withinRange(
          "temperatureC",
          selectedProfile.metrics.temperatureC,
          sourceValue("temperatureC")
        ),
        displayValue: asDisplay("temperatureC", sourceValue("temperatureC"))
      },
      {
        key: "humidity" as const,
        label: "Humidity",
        rangeDisplay: `${selectedProfile.metrics.humidity.min.toFixed(0)}–${selectedProfile.metrics.humidity.max.toFixed(0)} %`,
        status: withinRange(
          "humidity",
          selectedProfile.metrics.humidity,
          sourceValue("humidity")
        ),
        displayValue: asDisplay("humidity", sourceValue("humidity"))
      },
      {
        key: "soilMoisture" as const,
        label: "Soil moisture",
        rangeDisplay: `${Math.round(selectedProfile.metrics.soilMoisture.min * 100)}–${Math.round(selectedProfile.metrics.soilMoisture.max * 100)} %`,
        status: withinRange(
          "soilMoisture",
          selectedProfile.metrics.soilMoisture,
          sourceValue("soilMoisture")
        ),
        displayValue: asDisplay("soilMoisture", sourceValue("soilMoisture"))
      },
      {
        key: "lightLux" as const,
        label: "Light intensity",
        rangeDisplay: `${Math.round(selectedProfile.metrics.lightLux.min / 1000)}–${Math.round(selectedProfile.metrics.lightLux.max / 1000)}k lux`,
        status: withinRange(
          "lightLux",
          selectedProfile.metrics.lightLux,
          sourceValue("lightLux")
        ),
        displayValue: asDisplay("lightLux", sourceValue("lightLux"))
      }
    ];
  }, [recentAverages, selectedProfile, snapshot]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-4 pb-16 pt-8 sm:px-6 md:gap-10 md:px-12">
      <nav
        className="flex flex-wrap items-center justify-between gap-4 text-xs text-emerald-700 sm:text-sm"
        data-aos="fade-up"
      >
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

      <header
        className="card-surface flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between"
        data-aos="fade-up"
        data-aos-delay="100"
      >
        <div className="space-y-3">
          <span className={`pill ${summary.statusTone} text-[0.65rem] sm:text-xs`}>
            {summary.statusLabel}
          </span>
          <h1 className="text-3xl font-semibold text-emerald-900 sm:text-4xl md:text-5xl">
            {displayName}
          </h1>
          <p className="text-sm text-emerald-700">
            Latest reading: <strong>{summary.lastSeen}</strong>
          </p>
        </div>
        {/* <div className="grid gap-3 text-sm text-emerald-700 min-[460px]:grid-cols-2"> */}
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
          {/* <div className="flex flex-col gap-1.5 rounded-3xl border border-emerald-200 bg-white px-4 py-3">
            <p className="text-[0.65rem] uppercase tracking-[0.28em] text-emerald-500 sm:text-xs">
              Soil moisture
            </p>
            <p className="text-3xl font-semibold text-emerald-900">
              {snapshot?.soilMoisture !== undefined &&
              snapshot?.soilMoisture !== null
                ? `${Math.round(snapshot.soilMoisture * 100)}%`
                : "—"}
            </p>
          </div> */}
        {/* </div> */}
      </header>

      <section
        className="card-surface space-y-5"
        data-aos="fade-up"
        data-aos-delay="150"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-base font-semibold text-emerald-900 sm:text-lg">
              Recommended growing profile
            </h3>
            <p className="text-xs text-emerald-600 sm:text-sm">
              Compare live readings against horticulture guidelines for each crop.
              {isLocked && (
                <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-700">
                  <span aria-hidden>🔒</span> Locked
                </span>
              )}
            </p>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-end">
            <label className="flex flex-col gap-2 text-xs font-medium text-emerald-700 sm:w-48 sm:text-sm">
              Plant type
              <select
                value={selectedProfileId}
                onChange={(event) => {
                  if (!isLocked) {
                    setSelectedProfileId(event.target.value);
                    setLockError(null);
                    setLockSuccess(false);
                  }
                }}
                disabled={isLocked || isSubmitting}
                className="rounded-full border border-emerald-200 bg-white px-4 py-2 text-sm text-emerald-800 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 disabled:cursor-not-allowed disabled:bg-emerald-50 disabled:text-emerald-500"
              >
                {PLANT_PROFILES.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.label}
                  </option>
                ))}
              </select>
            </label>
            {!isLocked ? (
              <button
                type="button"
                onClick={async () => {
                  setIsSubmitting(true);
                  setLockError(null);
                  setLockSuccess(false);
                  try {
                    await setDevicePlantType(plantId, selectedProfileId);
                    setIsLocked(true);
                    setLockSuccess(true);
                    const profileLabel = PLANT_PROFILES.find(p => p.id === selectedProfileId)?.label || selectedProfileId;
                    toast.success(`🔒 Plant type locked to "${profileLabel}"`);
                    setTimeout(() => setLockSuccess(false), 3000);
                  } catch (err) {
                    const errorMessage = err instanceof Error
                      ? err.message
                      : "Failed to set plant type";
                    setLockError(errorMessage);
                    toast.error(`Failed to lock plant type: ${errorMessage}`);
                  } finally {
                    setIsSubmitting(false);
                  }
                }}
                disabled={isSubmitting}
                className="rounded-full border border-emerald-300 bg-emerald-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-wait disabled:opacity-50 sm:text-sm"
              >
                {isSubmitting ? "Submitting..." : "Lock Selection"}
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setIsLocked(false);
                  setLockError(null);
                  setLockSuccess(false);
                }}
                className="rounded-full border border-amber-300 bg-amber-100 px-4 py-2 text-xs font-semibold text-amber-700 transition hover:bg-amber-200 sm:text-sm"
              >
                Reset
              </button>
            )}
          </div>
        </div>

        {(lockError || lockSuccess) && (
          <div
            className={`rounded-2xl border px-4 py-3 text-xs sm:text-sm ${
              lockError
                ? "border-rose-200 bg-rose-50 text-rose-600"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
            }`}
          >
            {lockError || "Plant type locked successfully!"}
          </div>
        )}

        <p className="text-xs text-emerald-600 sm:text-sm">
          {selectedProfile.description}
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          {metricComparisons.map((metric) => {
            const statusStyles: Record<
              typeof metric.status,
              string
            > = {
              ideal:
                "bg-emerald-100 text-emerald-700 border border-emerald-200",
              low: "bg-amber-100 text-amber-700 border border-amber-200",
              high: "bg-rose-100 text-rose-700 border border-rose-200",
              unknown:
                "bg-slate-100 text-slate-500 border border-slate-200"
            };
            const statusLabel: Record<typeof metric.status, string> = {
              ideal: "Within range",
              low: "Too low",
              high: "Too high",
              unknown: "No data"
            };

            return (
              <div
                key={metric.key}
                className="flex flex-col gap-3 rounded-3xl bg-white/90 p-4 shadow-inner"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-emerald-900">
                      {metric.label}
                    </p>
                    <p className="text-xs text-emerald-600">
                      Ideal: {metric.rangeDisplay}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-[0.65rem] font-semibold ${statusStyles[metric.status]}`}
                  >
                    {statusLabel[metric.status]}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm text-emerald-800">
                  <span className="text-xs uppercase tracking-wide text-emerald-500">
                    Current
                  </span>
                  <span className="font-semibold text-emerald-900">
                    {metric.displayValue}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

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
        <>
          <div data-aos="fade-up">
            <ControlPanel
              plantId={plantId}
              profileLabel={selectedProfile.label}
              currentValues={{
                soilMoisture: snapshot.soilMoisture,
                temperatureC: snapshot.temperatureC,
                lightLux: snapshot.lightLux,
              }}
            />
          </div>

          <div className="space-y-6" data-aos="fade-up">
            <div className="grid gap-6 sm:grid-cols-2">
              <TimeseriesChart points={metricsSeries} />
              <DiseaseRiskChart points={diseaseSeries} />
            </div>

            <section className="card-surface">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-base font-semibold text-emerald-900 sm:text-lg">
                <span aria-hidden>📋</span>
                Recent readings
              </h3>
                <div className="flex gap-2 rounded-full border border-emerald-200 bg-emerald-50 p-1">
                  <button
                    type="button"
                    onClick={() => setRecentReadingsTab("metrics")}
                    className={`rounded-full px-4 py-1.5 text-xs font-medium transition sm:text-sm ${
                      recentReadingsTab === "metrics"
                        ? "bg-emerald-500 text-white shadow-sm"
                        : "text-emerald-700 hover:bg-emerald-100"
                    }`}
                  >
                    Metrics
                  </button>
                  <button
                    type="button"
                    onClick={() => setRecentReadingsTab("disease")}
                    className={`rounded-full px-4 py-1.5 text-xs font-medium transition sm:text-sm ${
                      recentReadingsTab === "disease"
                        ? "bg-emerald-500 text-white shadow-sm"
                        : "text-emerald-700 hover:bg-emerald-100"
                    }`}
                  >
                    Disease
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto">
                {recentReadingsTab === "metrics" ? (
                <table className="min-w-full divide-y divide-emerald-100 text-xs text-emerald-800 sm:text-sm">
                  <thead className="text-left text-[0.65rem] uppercase tracking-wide text-emerald-500 sm:text-xs">
                    <tr>
                      <th className="px-2 py-2 sm:px-3">Time</th>
                      <th className="px-2 py-2 sm:px-3">Temp °C</th>
                      <th className="px-2 py-2 sm:px-3">Humidity %</th>
                      <th className="px-2 py-2 sm:px-3">Soil</th>
                      <th className="px-2 py-2 sm:px-3">Light lux</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-emerald-50">
                      {metricsSeries
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
                          </tr>
                        ))}
                    </tbody>
                  </table>
                ) : (
                  <table className="min-w-full divide-y divide-emerald-100 text-xs text-emerald-800 sm:text-sm">
                    <thead className="text-left text-[0.65rem] uppercase tracking-wide text-emerald-500 sm:text-xs">
                      <tr>
                        <th className="px-2 py-2 sm:px-3">Time</th>
                        <th className="px-2 py-2 sm:px-3">Disease Risk</th>
                        <th className="px-2 py-2 sm:px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-emerald-50">
                      {diseaseSeries
                        .slice()
                        .reverse()
                        .slice(0, 12)
                        .map((point) => (
                          <tr key={point.timestamp}>
                            <td className="whitespace-nowrap px-2 py-2 sm:px-3">
                              {format(point.timestamp * 1000, "PPpp")}
                            </td>
                            <td className="px-2 py-2 sm:px-3">
                              {point.score !== undefined && point.score !== null
                                ? `${Math.round(point.score * 100)}%`
                                : "—"}
                            </td>
                          <td className="px-2 py-2 sm:px-3">
                              <span
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[0.65rem] font-semibold ${
                                  point.disease === true
                                    ? "bg-rose-100 text-rose-700"
                                    : point.disease === false
                                      ? "bg-emerald-100 text-emerald-700"
                                      : "bg-slate-100 text-slate-500"
                                }`}
                              >
                                {point.disease === true
                                  ? "⚠︎ Needs attention"
                                  : point.disease === false
                                    ? "✓ Healthy"
                                    : "— Unknown"}
                              </span>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                )}
              </div>
            </section>
          </div>
        </>
      )}
    </main>
  );
}

