import Link from "next/link";
import { getPlantName } from "@/lib/localStorage";
import type { PlantSnapshot } from "@/types/telemetry";

type PlantCardProps = {
  plant: PlantSnapshot;
  onRemove?: (deviceId: string) => void;
};

function statusLabel(plant: PlantSnapshot): { label: string; tone: string } {
  if (plant.disease === true) {
    return { label: "Needs attention", tone: "bg-rose-100 text-rose-600" };
  }
  if (plant.disease === false) {
    return { label: "Healthy", tone: "bg-emerald-100 text-emerald-700" };
  }
  return { label: "Monitoring", tone: "bg-bloom-100 text-bloom-500" };
}

function getDisplayName(plant: PlantSnapshot): string {
  const customName = getPlantName(plant.plantId);
  if (customName) {
    return customName;
  }
  // Fallback to formatted device ID
  return plant.plantId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function PlantCard({ plant, onRemove }: PlantCardProps) {
  const status = statusLabel(plant);
  const displayName = getDisplayName(plant);

  const handleRemove = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onRemove) {
      onRemove(plant.plantId);
    }
  };

  return (
    <div className="group relative flex h-full flex-col gap-4 overflow-hidden rounded-[2rem] border border-emerald-200/80 bg-white/90 p-5 shadow-card transition hover:-translate-y-1.5 hover:shadow-glow sm:rounded-[2.5rem] sm:p-6">
      <span className="bubble-accent hidden sm:block -right-24 top-8 h-56 w-56 opacity-40" />
      <span className="bubble-accent hidden sm:block -left-32 bottom-0 h-44 w-44 opacity-30" />
      <div className="absolute inset-0 bg-gradient-to-br from-white/85 via-emerald-50/70 to-bloom-50/70 opacity-0 transition group-hover:opacity-100" />
      
      {/* Remove button - positioned absolutely to avoid interfering with card click */}
      {onRemove && (
        <button
          onClick={handleRemove}
          className="absolute right-3 top-3 z-20 rounded-full bg-white/95 p-2.5 text-rose-500 shadow-md transition hover:bg-rose-50 hover:text-rose-600 hover:shadow-lg"
          aria-label="Remove plant"
          title="Remove plant"
        >
          <svg
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2.5}
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
            />
          </svg>
        </button>
      )}
      
      <Link
        href={`/plants/${plant.plantId}`}
        className="relative z-10 flex h-full flex-col gap-4"
      >
        <div className="flex items-center pr-12">
          <span className={`pill ${status.tone}`}>
            {status.label}
            <span aria-hidden className="text-base">
              {plant.disease ? "🌧️" : "🌼"}
            </span>
          </span>
        </div>
        <div className="space-y-3">
          <h2 className="flex items-center gap-2 text-xl font-semibold text-emerald-900 sm:text-2xl">
            <span className="text-2xl sm:text-3xl" aria-hidden>
              🌱
            </span>
            {displayName}
          </h2>
          <p className="text-sm text-emerald-700">
            Soil moisture{" "}
            <strong className="font-semibold text-emerald-900">
              {plant.soilMoisture !== undefined && plant.soilMoisture !== null
                ? `${Math.round(plant.soilMoisture * 100)}%`
                : "—"}
            </strong>{" "}
            · humidity{" "}
            <strong className="font-semibold text-emerald-900">
              {plant.humidity !== undefined && plant.humidity !== null
                ? `${Math.round(plant.humidity)}%`
                : "—"}
            </strong>
          </p>
          <div className="grid grid-cols-2 gap-3 text-sm text-emerald-700 max-[420px]:grid-cols-1">
            <div className="flex items-center gap-2 rounded-3xl bg-emerald-100/80 px-4 py-2 font-medium">
              <span aria-hidden>🌤️</span>
              <span className="text-emerald-900">
                {plant.temperatureC !== undefined && plant.temperatureC !== null
                  ? `${plant.temperatureC.toFixed(1)}°C`
                  : "—"}
              </span>
            </div>
            <div className="flex items-center gap-2 rounded-3xl bg-bloom-100/80 px-4 py-2 font-medium">
              <span aria-hidden>🔆</span>
              <span className="text-bloom-600">
                {plant.lightLux !== undefined && plant.lightLux !== null
                  ? `${Math.round(plant.lightLux)} lux`
                  : "—"}
              </span>
            </div>
          </div>
        </div>
        <div className="mt-auto flex items-center justify-between pt-4 text-sm font-medium text-emerald-700">
          <span>
            Disease probability:{" "}
            <strong className="text-emerald-900">
              {plant.score !== undefined && plant.score !== null
                ? `${Math.round(plant.score * 100)}%`
                : "unknown"}
            </strong>
          </span>
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 shadow transition group-hover:bg-emerald-500 group-hover:text-white sm:h-11 sm:w-11">
            →
          </span>
        </div>
      </Link>
    </div>
  );
}

