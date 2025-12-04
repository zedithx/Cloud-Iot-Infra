"use client";

import Link from "next/link";
import { useMemo, useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { formatTimestampSGT, formatDistanceToNowSGT } from "@/lib/dateUtils";
import toast from "react-hot-toast";
import ControlPanel from "@/components/ControlPanel";
import TimeseriesChart from "@/components/TimeseriesChart";
import DiseaseRiskChart from "@/components/DiseaseRiskChart";
import usePlantDetail from "@/hooks/usePlantDetail";
import {
  PLANT_PROFILES,
  guessProfileId,
  type PlantMetricRange,
  type PlantProfile,
} from "@/lib/plantProfiles";
import {
  fetchThresholdRecommendations,
  type ThresholdRecommendationResponse,
} from "@/lib/api";
import { getPlantName, getPlantType } from "@/lib/localStorage";

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
  // Get plant type from localStorage (set during QR scan or edit)
  const [selectedProfileId, setSelectedProfileId] = useState<string>(() => {
    const storedType = getPlantType(plantId);
    return storedType || guessProfileId(plantId) || PLANT_PROFILES[0].id;
  });
  const [recentReadingsTab, setRecentReadingsTab] = useState<
    "disease" | "metrics"
  >("metrics");
  const [recommendations, setRecommendations] =
    useState<ThresholdRecommendationResponse | null>(null);
  const [isLoadingRecommendations, setIsLoadingRecommendations] =
    useState(false);

  // Get custom plant name from localStorage, fallback to formatted device ID
  // Use state to avoid hydration mismatch (localStorage is only available on client)
  const defaultDisplayName = plantId
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const [displayName, setDisplayName] = useState(defaultDisplayName);

  useEffect(() => {
    // Update display name from localStorage after mount (client-side only)
    const customName = getPlantName(plantId);
    if (customName) {
      setDisplayName(customName);
    }

    // Update plant type from localStorage
    const storedType = getPlantType(plantId);
    if (storedType) {
      setSelectedProfileId(storedType);
    }
  }, [plantId]);

  // Fetch recommendations when plant data is available
  useEffect(() => {
    if (!snapshot || isLoading) return;

    const loadRecommendations = async () => {
      setIsLoadingRecommendations(true);
      try {
        const recs = await fetchThresholdRecommendations(plantId, 24);
        setRecommendations(recs);
      } catch (err) {
        // Silently fail - recommendations are optional
        console.warn("Failed to load recommendations:", err);
      } finally {
        setIsLoadingRecommendations(false);
      }
    };

    void loadRecommendations();
  }, [plantId, snapshot, isLoading]);

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
        point.readingType === "telemetry" ||
        (point.temperatureC !== null && point.temperatureC !== undefined) ||
        (point.humidity !== null && point.humidity !== undefined) ||
        (point.soilMoisture !== null && point.soilMoisture !== undefined) ||
        (point.lightLux !== null && point.lightLux !== undefined)
    );
  }, [series]);

  const diseaseSeries = useMemo(() => {
    return series.filter(
      (point) =>
        point.readingType === "disease" ||
        (point.score !== null && point.score !== undefined)
    );
  }, [series]);

  const recentAverages = useMemo(() => {
    if (!metricsSeries.length) {
      return {};
    }
    const lookback = metricsSeries.slice(-8);
    const averageFor = (key: keyof (typeof lookback)[number]) => {
      const values = lookback
        .map((point) => point[key])
        .filter(
          (value): value is number =>
            typeof value === "number" && Number.isFinite(value)
        );
      if (!values.length) {
        return undefined;
      }
      return values.reduce((total, value) => total + value, 0) / values.length;
    };

    return {
      temperatureC: averageFor("temperatureC"),
      humidity: averageFor("humidity"),
      soilMoisture: averageFor("soilMoisture"),
      lightLux: averageFor("lightLux"),
    } as Record<string, number | undefined>;
  }, [metricsSeries]);

  const summary = useMemo(() => {
    if (!snapshot) {
      return {
        lastSeen: "Never",
        statusLabel: "Loading",
        statusTone: "bg-bloom-100 text-bloom-500",
      };
    }
    const isDiseased = snapshot.disease === true;
    const isHealthy = snapshot.disease === false;

    return {
      lastSeen: snapshot.lastSeen
        ? formatDistanceToNowSGT(snapshot.lastSeen, { addSuffix: true })
        : "Unknown",
      statusLabel: isDiseased
        ? "Needs attention"
        : isHealthy
          ? "Healthy"
          : "Monitoring",
      statusTone: isDiseased
        ? "bg-rose-100 text-rose-600"
        : isHealthy
          ? "bg-emerald-100 text-emerald-700"
          : "bg-bloom-100 text-bloom-500",
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
      const effectiveValue = key === "soilMoisture" ? value : value; // stored as fraction already
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
        displayValue: asDisplay("temperatureC", sourceValue("temperatureC")),
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
        displayValue: asDisplay("humidity", sourceValue("humidity")),
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
        displayValue: asDisplay("soilMoisture", sourceValue("soilMoisture")),
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
        displayValue: asDisplay("lightLux", sourceValue("lightLux")),
      },
    ];
  }, [recentAverages, selectedProfile, snapshot]);

  // Water tank status (separate from metric comparisons since it's binary)
  const waterTankStatus = snapshot?.waterTankEmpty ?? null;
  const isWaterTankEmpty = waterTankStatus === 1;

  // Determine if disease risk is high based on disease boolean and confidence
  // High risk only when: disease is true AND confidence >= 80%
  const confidence = snapshot?.confidence ?? snapshot?.score ?? null;
  const isDiseased = snapshot?.disease === true;
  const isHighDiseaseRisk =
    isDiseased && confidence !== null && confidence >= 0.8;

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
        </div>
      </nav>

      <header
        className="card-surface flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between"
        data-aos="fade-up"
        data-aos-delay="100"
      >
        <div className="space-y-3">
          <span
            className={`pill ${summary.statusTone} text-[0.65rem] sm:text-xs`}
          >
            {summary.statusLabel}
          </span>
          <h1 className="text-3xl font-semibold text-emerald-900 sm:text-4xl md:text-5xl">
            {displayName}
          </h1>
          <p className="text-sm text-emerald-700">
            Latest reading: <strong>{summary.lastSeen}</strong>
          </p>
        </div>
        <div className="grid gap-3 text-sm text-emerald-700 min-[460px]:grid-cols-2">
          <div
            className={`flex flex-col gap-1.5 rounded-3xl border px-4 py-3 ${
              isHighDiseaseRisk
                ? "border-rose-300 bg-rose-50"
                : "border-emerald-200 bg-white"
            }`}
          >
            <p
              className={`text-[0.65rem] uppercase tracking-[0.28em] sm:text-xs ${
                isHighDiseaseRisk ? "text-rose-600" : "text-emerald-500"
              }`}
            >
              Disease Status
            </p>
            <p
              className={`text-xl font-semibold ${
                isHighDiseaseRisk ? "text-rose-700" : "text-emerald-900"
              }`}
            >
              {snapshot?.disease !== undefined
                ? `Leaf: ${snapshot.disease ? "Diseased" : "Healthy"}`
                : "—"}
            </p>
            <p
              className={`text-sm font-medium ${
                isHighDiseaseRisk ? "text-rose-600" : "text-emerald-700"
              }`}
            >
              {confidence !== undefined && confidence !== null
                ? `Confidence: ${Math.round(confidence * 100)}%`
                : ""}
            </p>
          </div>
          <div
            className={`flex flex-col gap-1.5 rounded-3xl border px-4 py-3 ${
              isWaterTankEmpty
                ? "border-amber-300 bg-amber-50"
                : "border-emerald-200 bg-white"
            }`}
          >
            <p
              className={`text-[0.65rem] uppercase tracking-[0.28em] sm:text-xs ${
                isWaterTankEmpty ? "text-amber-600" : "text-emerald-500"
              }`}
            >
              Water Tank Status
            </p>
            <p
              className={`text-2xl font-semibold ${
                isWaterTankEmpty ? "text-amber-700" : "text-emerald-900"
              }`}
            >
              {waterTankStatus === null
                ? "—"
                : waterTankStatus === 1
                  ? "⚠️ Empty"
                  : "✅ Full"}
            </p>
          </div>
        </div>
      </header>

      {/* Alert Banners - Show side by side if both are present, otherwise full width */}
      {(isHighDiseaseRisk || isWaterTankEmpty) && (
        <div
          className={`grid gap-4 ${isHighDiseaseRisk && isWaterTankEmpty ? "md:grid-cols-2" : ""}`}
          data-aos="fade-up"
          data-aos-delay="120"
        >
          {/* Disease Risk Alert Banner */}
          {isHighDiseaseRisk && (
            <div className="card-surface border-2 border-rose-500 bg-gradient-to-r from-rose-50 to-orange-50 shadow-lg">
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl" aria-hidden="true">
                      🚨
                    </span>
                    <h2 className="text-xl font-bold text-rose-900 sm:text-2xl">
                      High Disease Risk Detected
                    </h2>
                  </div>
                  <div className="flex-shrink-0">
                    <div className="rounded-lg bg-rose-100 px-4 py-3 text-center">
                      <p className="text-xs font-semibold uppercase tracking-wide text-rose-600">
                        Confidence
                      </p>
                      <p className="text-3xl font-bold text-rose-700">
                        {confidence !== null
                          ? `${Math.round(confidence * 100)}%`
                          : "—"}
                      </p>
                    </div>
                  </div>
                </div>
                <p className="text-sm font-semibold text-rose-800 sm:text-base">
                  Disease detected with{" "}
                  <strong>
                    {confidence !== null
                      ? `${Math.round(confidence * 100)}%`
                      : "high"}
                  </strong>{" "}
                  confidence - Immediate action recommended
                </p>
                <div className="space-y-2 rounded-lg bg-white/60 p-4">
                  <p className="text-sm font-semibold text-rose-900">
                    Recommended Actions:
                  </p>
                  <ul className="ml-5 list-disc space-y-1.5 text-sm text-rose-800">
                    <li>
                      <strong>Isolate the plant</strong> to prevent disease
                      spread to other plants
                    </li>
                    <li>
                      <strong>Improve air circulation</strong> by adjusting fan
                      settings to reduce humidity
                    </li>
                    <li>
                      <strong>Reduce watering frequency</strong> to lower soil
                      moisture and prevent fungal growth
                    </li>
                    <li>
                      <strong>Apply appropriate treatment</strong> based on the
                      specific disease type (fungicide, bactericide, etc.)
                    </li>
                    <li>
                      <strong>Monitor closely</strong> and check back in 24-48
                      hours to assess improvement
                    </li>
                    <li>
                      <strong>
                        Consider removing severely affected leaves
                      </strong>{" "}
                      to prevent further spread
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Water Tank Empty Alert Banner */}
          {isWaterTankEmpty && (
            <div className="card-surface border-2 border-amber-500 bg-gradient-to-r from-amber-50 to-orange-50 shadow-lg">
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <span className="text-3xl" aria-hidden="true">
                      ⚠️
                    </span>
                    <h2 className="text-xl font-bold text-amber-900 sm:text-2xl">
                      Water Tank Empty
                    </h2>
                  </div>
                  <div className="flex-shrink-0">
                    <div className="rounded-lg bg-amber-100 px-4 py-3 text-center">
                      <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">
                        Status
                      </p>
                      <p className="text-3xl font-bold text-amber-700">EMPTY</p>
                    </div>
                  </div>
                </div>
                <p className="text-sm font-semibold text-amber-800 sm:text-base">
                  The water tank for <strong>{displayName}</strong> is empty
                </p>
                <div className="space-y-2 rounded-lg bg-white/60 p-4">
                  <p className="text-sm font-semibold text-amber-900">
                    Action Required:
                  </p>
                  <ul className="ml-5 list-disc space-y-1.5 text-sm text-amber-800">
                    <li>
                      <strong>Refill the water tank immediately</strong> to
                      ensure continuous irrigation
                    </li>
                    <li>
                      <strong>Check for leaks or blockages</strong> that may
                      have caused rapid water depletion
                    </li>
                    <li>
                      <strong>Verify the water level sensor</strong> is
                      functioning correctly after refilling
                    </li>
                    <li>
                      <strong>Monitor soil moisture levels</strong> to ensure
                      plants receive adequate hydration
                    </li>
                    <li>
                      <strong>Consider setting up automated alerts</strong> for
                      future low water level events
                    </li>
                    <li>
                      <strong>Check the irrigation system</strong> to ensure
                      it&apos;s operating efficiently
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

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
              Compare live readings against horticulture guidelines for{" "}
              {selectedProfile.label.toLowerCase()}.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-emerald-600 uppercase tracking-wide">
                Plant Type
              </span>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-emerald-100 px-4 py-2 text-sm font-semibold text-emerald-900">
                  {selectedProfile.label}
                </span>
              </div>
            </div>
          </div>
        </div>

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
              unknown: "No data",
            };

            // Get recommendation for this metric if available
            const getRecommendationForMetric = (key: string) => {
              if (!recommendations?.recommendations) return null;

              const actuatorMap: Record<string, "pump" | "fan" | "lights"> = {
                soilMoisture: "pump",
                temperatureC: "fan",
                lightLux: "lights",
              };

              const actuator = actuatorMap[key];
              if (!actuator) return null;

              return (
                recommendations.recommendations.find(
                  (r) => r.actuator === actuator
                ) || null
              );
            };

            const recommendation = getRecommendationForMetric(metric.key);
            const hasRecommendation = recommendation !== null;

            return (
              <div
                key={metric.key}
                className={`flex flex-col gap-3 rounded-3xl bg-white/90 p-4 shadow-inner ${hasRecommendation ? "border-2 border-amber-200" : ""}`}
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

                {isLoadingRecommendations ? (
                  <div className="mt-2 rounded-2xl border border-emerald-200 bg-emerald-50/30 p-3">
                    <p className="text-xs text-emerald-600">
                      Analyzing trends...
                    </p>
                  </div>
                ) : hasRecommendation ? (
                  <div className="mt-2 rounded-2xl border border-amber-200 bg-amber-50/50 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-semibold text-amber-900">
                        ⚠️ Threshold Recommendation
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[0.65rem] font-semibold ${
                          recommendation.confidence === "high"
                            ? "bg-emerald-100 text-emerald-700"
                            : recommendation.confidence === "medium"
                              ? "bg-blue-100 text-blue-700"
                              : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {recommendation.confidence === "high"
                          ? "High"
                          : recommendation.confidence === "medium"
                            ? "Medium"
                            : "Low"}{" "}
                        Confidence
                      </span>
                    </div>
                    <div className="mb-2 text-xs text-amber-800">
                      <p className="font-medium mb-1">
                        Recommended:{" "}
                        {metric.key === "soilMoisture"
                          ? `${Math.round(recommendation.recommendedThreshold * 100)}%`
                          : metric.key === "temperatureC"
                            ? `${recommendation.recommendedThreshold.toFixed(1)}°C`
                            : `${Math.round(recommendation.recommendedThreshold).toLocaleString()} lux`}
                      </p>
                      {recommendation.reasoning.length > 0 && (
                        <p className="text-amber-700 mt-1">
                          {recommendation.reasoning[0]}
                        </p>
                      )}
                    </div>
                  </div>
                ) : metric.status === "ideal" ? (
                  <div className="mt-2 rounded-2xl border border-emerald-200 bg-emerald-50/30 p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-emerald-600" aria-hidden>
                        ✅
                      </span>
                      <p className="text-xs text-emerald-700">
                        Conditions are stable. No threshold adjustment needed.
                      </p>
                    </div>
                  </div>
                ) : metric.status === "low" || metric.status === "high" ? (
                  <div className="mt-2 rounded-2xl border border-blue-200 bg-blue-50/30 p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-blue-600" aria-hidden>
                        ℹ️
                      </span>
                      <p className="text-xs text-blue-700">
                        Value is {metric.status === "low" ? "below" : "above"}{" "}
                        optimal range, but no alarming trends detected. Your
                        auto-heal system will maintain thresholds.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="mt-2 rounded-2xl border border-slate-200 bg-slate-50/30 p-3">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-500" aria-hidden>
                        —
                      </span>
                      <p className="text-xs text-slate-600">
                        No data available for trend analysis.
                      </p>
                    </div>
                  </div>
                )}
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
              plantName={displayName}
              profileLabel={selectedProfile.label}
              selectedProfile={selectedProfile}
              currentValues={{
                soilMoisture: snapshot.soilMoisture,
                humidity: snapshot.humidity,
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
                <div className="flex items-center gap-2">
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
                  <button
                    type="button"
                    onClick={refresh}
                    className="rounded-full border border-emerald-200 bg-sprout-100 px-4 py-1.5 text-xs font-medium text-emerald-700 hover:bg-sprout-200 sm:text-sm"
                  >
                    Refresh
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
                        <th className="px-2 py-2 sm:px-3">Moisture %</th>
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
                              {formatTimestampSGT(point.timestamp, "PPpp")}
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
                        <th className="px-2 py-2 sm:px-3">Prediction</th>
                        <th className="px-2 py-2 sm:px-3">Confidence</th>
                        <th className="px-2 py-2 sm:px-3">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-emerald-50">
                      {diseaseSeries
                        .slice()
                        .reverse()
                        .slice(0, 12)
                        .map((point) => {
                          const pointConfidence =
                            point.confidence ?? point.score ?? null;
                          const pointIsDiseased = point.disease === true;
                          const pointIsHealthy = point.disease === false;

                          return (
                            <tr key={point.timestamp}>
                              <td className="whitespace-nowrap px-2 py-2 sm:px-3">
                                {formatTimestampSGT(point.timestamp, "PPpp")}
                              </td>
                              <td className="px-2 py-2 sm:px-3">
                                {point.disease !== undefined
                                  ? point.disease
                                    ? "Diseased"
                                    : "Healthy"
                                  : "—"}
                              </td>
                              <td className="px-2 py-2 sm:px-3">
                                {pointConfidence !== undefined &&
                                pointConfidence !== null
                                  ? `${Math.round(pointConfidence * 100)}%`
                                  : "—"}
                              </td>
                              <td className="px-2 py-2 sm:px-3">
                                <span
                                  className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[0.65rem] font-semibold ${
                                    pointIsDiseased
                                      ? "bg-rose-100 text-rose-700"
                                      : pointIsHealthy
                                        ? "bg-emerald-100 text-emerald-700"
                                        : "bg-slate-100 text-slate-500"
                                  }`}
                                >
                                  {pointIsDiseased
                                    ? "⚠︎ Needs attention"
                                    : pointIsHealthy
                                      ? "✓ Healthy"
                                      : "— Unknown"}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
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
