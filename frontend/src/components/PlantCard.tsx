import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import type { PlantSnapshot } from "@/types/telemetry";

type PlantCardProps = {
  plant: PlantSnapshot;
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

export default function PlantCard({ plant }: PlantCardProps) {
  const status = statusLabel(plant);
  const lastSeen = plant.lastSeen
    ? formatDistanceToNow(plant.lastSeen * 1000, { addSuffix: true })
    : "Unknown";

  return (
    <Link
      href={`/plants/${plant.plantId}`}
      className="group relative flex h-full flex-col gap-4 overflow-hidden rounded-[2rem] border border-emerald-200/80 bg-white/90 p-5 shadow-card transition hover:-translate-y-1.5 hover:shadow-glow sm:rounded-[2.5rem] sm:p-6"
    >
      <span className="bubble-accent hidden sm:block -right-24 top-8 h-56 w-56 opacity-40" />
      <span className="bubble-accent hidden sm:block -left-32 bottom-0 h-44 w-44 opacity-30" />
      <div className="absolute inset-0 bg-gradient-to-br from-white/85 via-emerald-50/70 to-bloom-50/70 opacity-0 transition group-hover:opacity-100" />
      <div className="relative z-10 flex items-center justify-between">
        <span className={`pill ${status.tone}`}>
          {status.label}
          <span aria-hidden className="text-base">
            {plant.disease ? "🌧️" : "🌼"}
          </span>
        </span>
        <span className="rounded-full bg-emerald-50/80 px-3 py-1 text-[0.65rem] font-medium text-emerald-600 shadow-sm sm:text-xs">
          {lastSeen}
        </span>
      </div>
      <div className="relative z-10 space-y-3">
        <h2 className="flex items-center gap-2 text-xl font-semibold text-emerald-900 sm:text-2xl">
          <span className="text-2xl sm:text-3xl" aria-hidden>
            🌱
          </span>
          {plant.plantId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
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
      <div className="relative z-10 mt-auto flex items-center justify-between pt-4 text-sm font-medium text-emerald-700">
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
  );
}

