/* eslint-disable react/jsx-props-no-spreading */
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { formatTimestampSGT } from "@/lib/dateUtils";
import type { PlantTimeSeriesPoint } from "@/types/telemetry";

type DiseaseRiskChartProps = {
  points: PlantTimeSeriesPoint[];
};

type ChartDatum = PlantTimeSeriesPoint & { label: string };

function formatPoints(points: PlantTimeSeriesPoint[]): ChartDatum[] {
  return points.map((point) => ({
    ...point,
    label: formatTimestampSGT(point.timestamp, "MMM d, HH:mm")
  }));
}

export default function DiseaseRiskChart({ points }: DiseaseRiskChartProps) {
  if (!points.length) {
    return (
      <div className="card-surface text-sm text-emerald-700/80">
        No readings recorded yet.
      </div>
    );
  }

  const data = formatPoints(points);

  return (
    <div className="card-surface border-dashed border-emerald-200/80 bg-white/95">
      <h3 className="mb-3 flex items-center gap-2 text-base font-semibold text-emerald-900 sm:mb-4 sm:text-lg">
        <span aria-hidden>🦠</span>
        Disease risk
      </h3>
      <div className="h-[18rem] w-full sm:h-80">
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="6 6" stroke="#bbf7d0" />
            <XAxis dataKey="label" tick={{ fill: "#047857", fontSize: 12 }} />
            <YAxis
              tick={{ fill: "#047857", fontSize: 12 }}
              domain={[0, 1]}
              tickFormatter={(value) => `${Math.round(value * 100)}%`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255,255,255,0.95)",
                borderRadius: "16px",
                border: "1px solid #86efac",
                color: "#065f46"
              }}
              labelStyle={{ color: "#047857", fontWeight: 600 }}
              formatter={(value: number) => [
                `${Math.round((value ?? 0) * 100)}%`,
                "Disease risk"
              ]}
            />
            <Line
              type="monotone"
              dataKey="score"
              name="Disease risk"
              stroke="#f97316"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

