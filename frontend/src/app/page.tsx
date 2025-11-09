"use client";

import usePlantSnapshots from "@/hooks/usePlantSnapshots";
import PlantCard from "@/components/PlantCard";

export default function HomePage() {
  const { plants, isLoading, error, refresh, isMocked } = usePlantSnapshots();

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-12 p-6 md:p-12">
      <header className="relative flex flex-col gap-6 overflow-hidden rounded-[3rem] border border-emerald-200/70 bg-white/85 p-10 shadow-glow">
        <span className="bubble-accent -right-20 top-16 h-64 w-64 opacity-50" />
        <span className="bubble-accent -left-24 bottom-0 h-52 w-52 opacity-40" />
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.35em] text-emerald-500">
              Greenhouse overview
            </p>
          </div>
            <h1 className="mt-2 text-4xl font-semibold text-emerald-900 md:text-5xl">
              Plant vitality dashboard
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {isMocked && (
              <span className="inline-flex items-center gap-2 rounded-full bg-bloom-100 px-4 py-2 text-xs font-bold uppercase tracking-widest text-bloom-500 shadow">
                <span aria-hidden>🎈</span> Demo data
              </span>
            )}
            <button
              onClick={refresh}
              type="button"
              className="rounded-full border border-emerald-200 bg-sprout-100 px-6 py-2 text-sm font-semibold text-emerald-700 shadow-card transition hover:-translate-y-0.5 hover:bg-sprout-200"
            >
              Refresh data
            </button>
          </div>
        <p className="max-w-2xl text-sm text-emerald-700 md:text-base">
          Monitor each plant&apos;s health, moisture, and disease risk in real
          time. Tap a plant card to open detailed charts, recent activity, and
          the simulated control panel for lights, water, and airflow.
        </p>
        <div className="flex flex-wrap gap-3 text-xs text-emerald-600">
          <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 font-semibold">
            🌼 Cartoon greenhouse aesthetic
          </span>
          <span className="inline-flex items-center gap-2 rounded-full bg-bloom-50 px-3 py-1 font-semibold">
            🌿 Real-time vitals (mock enabled)
          </span>
        </div>
      </header>

      {error && (
        <div className="rounded-3xl border border-rose-200 bg-rose-50/80 p-6 text-sm text-rose-600 shadow-card">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-6 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="h-56 animate-pulse rounded-3xl bg-white/60 shadow-inner"
            />
          ))}
        </div>
      ) : plants.length ? (
        <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {plants.map((plant) => (
            <PlantCard key={plant.plantId} plant={plant} />
          ))}
        </section>
      ) : (
        <div className="card-surface text-emerald-700">
          <h2 className="text-lg font-semibold text-emerald-900">
            No plants yet
          </h2>
          <p className="mt-2 text-sm">
            Once your devices begin streaming telemetry into DynamoDB you&apos;ll
            see each plant appear here with the latest vitals.
          </p>
        </div>
      )}
    </div>
  );
}

