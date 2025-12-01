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

type TimeseriesChartProps = {
  points: PlantTimeSeriesPoint[];
};

type ChartDatum = PlantTimeSeriesPoint & { label: string };

function formatPoints(points: PlantTimeSeriesPoint[]): ChartDatum[] {
  return points.map((point) => {
    try {
      return {
        ...point,
        label: formatTimestampSGT(point.timestamp, "MMM d, HH:mm")
      };
    } catch (error) {
      // Fallback if formatting fails
      console.warn("Failed to format point timestamp:", error, point);
      return {
    ...point,
        label: new Date(point.timestamp * 1000).toLocaleString("en-SG", { 
          timeZone: "Asia/Singapore",
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit"
        })
      };
    }
  });
}

export default function TimeseriesChart({ points }: TimeseriesChartProps) {
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
        <span aria-hidden>📈</span>
        Growth conditions
      </h3>
      <div className="h-[18rem] w-full sm:h-80">
        <ResponsiveContainer>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="6 6" stroke="#bbf7d0" />
            <XAxis dataKey="label" tick={{ fill: "#047857", fontSize: 12 }} />
            <YAxis
              yAxisId="left"
              tick={{ fill: "#047857", fontSize: 12 }}
              domain={["auto", "auto"]}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fill: "#047857", fontSize: 12 }}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255,255,255,0.95)",
                borderRadius: "16px",
                border: "1px solid #86efac",
                color: "#065f46"
              }}
              labelStyle={{ color: "#047857", fontWeight: 600 }}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="temperatureC"
              name="Temperature °C"
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="humidity"
              name="Humidity %"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="soilMoisture"
              name="Soil moisture"
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="lightLux"
              name="Light intensity (lux)"
              stroke="#eab308"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

