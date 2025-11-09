"use client";

import { formatDistanceToNow } from "date-fns";
import type { TelemetryRecord } from "@/types/telemetry";

type TelemetryTableProps = {
  records: TelemetryRecord[];
  isLoading: boolean;
  lastError?: string;
};

export default function TelemetryTable({
  records,
  isLoading,
  lastError
}: TelemetryTableProps) {
  if (isLoading) {
    return (
      <div className="flex h-48 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/40">
        <p className="text-sm text-slate-300">Loading telemetry...</p>
      </div>
    );
  }

  if (lastError) {
    return (
      <div className="flex h-48 items-center justify-center rounded-2xl border border-rose-700/40 bg-rose-500/10">
        <p className="text-sm text-rose-200">{lastError}</p>
      </div>
    );
  }

  if (!records.length) {
    return (
      <div className="flex h-48 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900/40">
        <p className="text-sm text-slate-300">
          No telemetry events yet. Submit one using the form.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/40 shadow-card">
      <table className="min-w-full divide-y divide-slate-800">
        <thead className="bg-slate-900/60 text-left text-xs uppercase tracking-wider text-slate-400">
          <tr>
            <th className="px-4 py-3">Device</th>
            <th className="px-4 py-3">Score</th>
            <th className="px-4 py-3">Temperature</th>
            <th className="px-4 py-3">Humidity</th>
            <th className="px-4 py-3">Captured</th>
            <th className="px-4 py-3">Notes</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800 text-sm">
          {records.map((record) => (
            <tr key={`${record.deviceId}-${record.timestamp}`}>
              <td className="px-4 py-3 font-mono text-xs text-slate-200">
                {record.deviceId}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                    record.score >= 0.7
                      ? "bg-rose-500/20 text-rose-200"
                      : "bg-emerald-500/20 text-emerald-200"
                  }`}
                >
                  {(record.score * 100).toFixed(0)}%
                </span>
              </td>
              <td className="px-4 py-3 text-slate-200">
                {record.temperatureC !== undefined &&
                record.temperatureC !== null
                  ? `${record.temperatureC.toFixed(1)} °C`
                  : "—"}
              </td>
              <td className="px-4 py-3 text-slate-200">
                {record.humidity !== undefined && record.humidity !== null
                  ? `${record.humidity.toFixed(1)} %`
                  : "—"}
              </td>
              <td className="px-4 py-3 text-slate-300">
                {formatDistanceToNow(record.timestamp * 1000, {
                  addSuffix: true
                })}
              </td>
              <td className="px-4 py-3 text-slate-300">
                {record.notes ? (
                  <span className="line-clamp-2 max-w-xs">{record.notes}</span>
                ) : (
                  <span className="text-slate-500">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

