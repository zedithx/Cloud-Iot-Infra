"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import { sendActuatorCommand, type ThresholdRecommendation } from "@/lib/api";

type ThresholdRecommendationsProps = {
  plantId: string;
  plantType?: string | null;
  recommendations: ThresholdRecommendation[];
};

const ACTUATOR_META: Record<
  "pump" | "fan" | "lights",
  { label: string; icon: string; unit: string; metric: "soilMoisture" | "temperatureC" | "lightLux" }
> = {
  pump: {
    label: "Water Pump",
    icon: "💧",
    unit: "%",
    metric: "soilMoisture",
  },
  fan: {
    label: "Fan",
    icon: "🌀",
    unit: "°C",
    metric: "temperatureC",
  },
  lights: {
    label: "Grow Lights",
    icon: "💡",
    unit: " lux",
    metric: "lightLux",
  },
};

const CONFIDENCE_STYLES: Record<"low" | "medium" | "high", string> = {
  low: "bg-amber-100 text-amber-700 border-amber-200",
  medium: "bg-blue-100 text-blue-700 border-blue-200",
  high: "bg-emerald-100 text-emerald-700 border-emerald-200",
};

const CONFIDENCE_LABELS: Record<"low" | "medium" | "high", string> = {
  low: "Low Confidence",
  medium: "Medium Confidence",
  high: "High Confidence",
};

function formatValue(value: number, actuator: "pump" | "fan" | "lights"): string {
  if (actuator === "pump") {
    return `${Math.round(value * 100)}%`;
  }
  if (actuator === "fan") {
    return `${value.toFixed(1)}°C`;
  }
  return `${Math.round(value).toLocaleString()} lux`;
}

export default function ThresholdRecommendations({
  plantId,
  plantType,
  recommendations,
}: ThresholdRecommendationsProps) {
  const [applying, setApplying] = useState<Set<string>>(new Set());

  const handleApply = async (recommendation: ThresholdRecommendation) => {
    const actuator = recommendation.actuator;
    setApplying((prev) => new Set(prev).add(actuator));

    try {
      const meta = ACTUATOR_META[actuator];
      await sendActuatorCommand(plantId, {
        actuator,
        targetValue: recommendation.recommendedThreshold,
        metric: meta.metric,
      });

      toast.success(
        `${meta.icon} ${meta.label} threshold set to ${formatValue(recommendation.recommendedThreshold, actuator)}`
      );
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Failed to apply recommendation";
      toast.error(`Failed to apply ${ACTUATOR_META[actuator].label} recommendation: ${errorMessage}`);
    } finally {
      setApplying((prev) => {
        const next = new Set(prev);
        next.delete(actuator);
        return next;
      });
    }
  };

  if (recommendations.length === 0) {
    return (
      <div className="rounded-3xl border border-emerald-200 bg-emerald-50/50 p-8 text-center">
        <div className="mb-3 text-4xl" aria-hidden>✅</div>
        <p className="text-base font-semibold text-emerald-900 mb-2">
          No Action Needed
        </p>
        <p className="text-sm text-emerald-700">
          All environmental conditions are stable. No alarming trends detected that require threshold adjustments.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {recommendations.map((rec) => {
        const meta = ACTUATOR_META[rec.actuator];
        const isApplying = applying.has(rec.actuator);
        const hasCurrent = rec.currentThreshold !== null && rec.currentThreshold !== undefined;

        return (
          <div
            key={rec.actuator}
            className="rounded-3xl border border-emerald-200 bg-white p-6 shadow-sm"
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="mb-2 flex items-center gap-3">
                  <span className="text-2xl" aria-hidden>
                    {meta.icon}
                  </span>
                  <h4 className="text-lg font-semibold text-emerald-900">
                    {meta.label}
                  </h4>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${CONFIDENCE_STYLES[rec.confidence]}`}
                  >
                    {CONFIDENCE_LABELS[rec.confidence]}
                  </span>
                  {rec.trends.length > 0 && (
                    <span className="text-xs text-emerald-600">
                      Trends: {rec.trends.join(", ").replace(/_/g, " ")}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="mb-4 grid gap-4 sm:grid-cols-2">
              {hasCurrent && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                    Current Threshold
                  </p>
                  <p className="text-2xl font-semibold text-slate-900">
                    {formatValue(rec.currentThreshold!, rec.actuator)}
                  </p>
                </div>
              )}
              <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-emerald-600">
                  Recommended Threshold
                </p>
                <p className="text-2xl font-semibold text-emerald-900">
                  {formatValue(rec.recommendedThreshold, rec.actuator)}
                </p>
              </div>
            </div>

            <div className="mb-4 rounded-2xl border border-emerald-100 bg-emerald-50/50 p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                Reasoning
              </p>
              <ul className="space-y-2 text-sm text-emerald-800">
                {rec.reasoning.map((reason, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="mt-1 text-emerald-500" aria-hidden>
                      •
                    </span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>

            <button
              onClick={() => handleApply(rec)}
              disabled={isApplying}
              className="w-full rounded-full bg-emerald-600 px-6 py-3 font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-50"
            >
              {isApplying
                ? `Applying ${meta.label}...`
                : `Apply ${meta.label} Recommendation`}
            </button>
          </div>
        );
      })}
    </div>
  );
}

