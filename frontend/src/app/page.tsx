"use client";

import usePlantSnapshots from "@/hooks/usePlantSnapshots";
import PlantCard from "@/components/PlantCard";

export default function HomePage() {
  const { plants, isLoading, error, refresh, isMocked } = usePlantSnapshots();

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-10 px-4 pb-16 pt-8 sm:px-6 md:gap-12 md:px-12">
      <header className="relative flex flex-col gap-6 overflow-hidden rounded-[2.5rem] border border-emerald-200/70 bg-white/90 p-6 shadow-glow sm:rounded-[3rem] sm:p-10">
        <span className="bubble-accent hidden sm:block -right-20 top-16 h-64 w-64 opacity-50" />
        <span className="bubble-accent hidden sm:block -left-24 bottom-0 h-52 w-52 opacity-40" />
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-xl space-y-3">
            <p className="text-xs font-semibold uppercase tracking-[0.25em] text-emerald-500 sm:text-sm sm:tracking-[0.35em]">
              Greenhouse overview
            </p>
            <h1 className="text-3xl font-semibold text-emerald-900 sm:text-4xl md:text-5xl">
              Plant vitality dashboard
            </h1>
            <p className="text-sm text-emerald-700 sm:text-base">
              Monitor each plant&apos;s health, moisture, and disease risk in real
              time. Tap a plant card to open detailed charts, recent activity,
              and the simulated control panel for lights, water, and airflow.
            </p>
            <div className="flex flex-wrap gap-2 text-[0.7rem] font-semibold text-emerald-600 sm:text-xs">
              <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1">
                🌼 Cartoon greenhouse aesthetic
              </span>
              <span className="inline-flex items-center gap-2 rounded-full bg-bloom-50 px-3 py-1">
                🌿 Real-time vitals (mock enabled)
              </span>
            </div>
          </div>
          <div className="flex w-full flex-col items-stretch gap-3 sm:w-auto sm:flex-row sm:items-center">
            {isMocked && (
              <span className="inline-flex items-center justify-center gap-2 rounded-full bg-bloom-100 px-4 py-2 text-xs font-bold uppercase tracking-widest text-bloom-500 shadow sm:text-[0.7rem]">
                <span aria-hidden>🎈</span> Demo data
              </span>
            )}
            <button
              onClick={refresh}
              type="button"
              className="rounded-full border border-emerald-200 bg-sprout-100 px-5 py-2 text-sm font-semibold text-emerald-700 shadow-card transition hover:-translate-y-0.5 hover:bg-sprout-200 sm:w-auto"
            >
              Refresh data
            </button>
          </div>
        </div>
      </header>

      {error && (
        <div className="rounded-3xl border border-rose-200 bg-rose-50/80 p-5 text-sm text-rose-600 shadow-card sm:p-6">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={index}
              className="h-48 animate-pulse rounded-[2rem] bg-white/60 shadow-inner sm:h-56"
            />
          ))}
        </div>
      ) : plants.length ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
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
    </main>
  );
}

