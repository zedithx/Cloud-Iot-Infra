/* eslint-disable react/jsx-props-no-spreading */
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatTimestampSGT } from "@/lib/dateUtils";
import type { PlantTimeSeriesPoint } from "@/types/telemetry";

type DiseaseRiskChartProps = {
  points: PlantTimeSeriesPoint[];
};

type ChartDatum = PlantTimeSeriesPoint & { label: string; yValue: number };

function formatPoints(points: PlantTimeSeriesPoint[]): ChartDatum[] {
  return points.map((point) => {
    const confidence = Math.max(
      0,
      Math.min(1, (point.confidence ?? point.score ?? 0) as number)
    );
    // Map to vertical axis: 0 = Disease (high confidence), 0.5 = Uncertain, 1 = Healthy (high confidence)
    // - Diseased: higher confidence → lower y (towards 0)
    // - Healthy: higher confidence → higher y (towards 1)
    // - Unknown disease flag: center at 0.5
    let yValue = 0.5;
    if (point.disease === true) {
      yValue = 0.5 - confidence * 0.5;
    } else if (point.disease === false) {
      yValue = 0.5 + confidence * 0.5;
    }

    return {
      ...point,
      label: formatTimestampSGT(point.timestamp, "MMM d, HH:mm"),
      yValue,
    };
  });
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
        Disease detection
      </h3>
      <div className="h-[18rem] w-full sm:h-80">
        <ResponsiveContainer>
          <LineChart data={data}>
            <defs>
              <linearGradient id="statusGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" stopOpacity={1} />
                <stop offset="50%" stopColor="#f59e0b" stopOpacity={1} />
                <stop offset="100%" stopColor="#ef4444" stopOpacity={1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="6 6" stroke="#bbf7d0" />
            <XAxis dataKey="label" tick={{ fill: "#047857", fontSize: 12 }} />
            <YAxis
              tick={{ fill: "#047857", fontSize: 12 }}
              domain={[0, 1]}
              ticks={[0, 0.5, 1]}
              tickFormatter={(value: number) =>
                value <= 0.25
                  ? "Diseased"
                  : value >= 0.75
                    ? "Healthy"
                    : "Uncertain"
              }
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255,255,255,0.95)",
                borderRadius: "16px",
                border: "1px solid #86efac",
                color: "#065f46",
                padding: "12px",
              }}
              labelStyle={{
                color: "#047857",
                fontWeight: 600,
                marginBottom: "8px",
              }}
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  const point = payload[0].payload as PlantTimeSeriesPoint;
                  const prediction =
                    point.disease !== undefined
                      ? point.disease
                        ? "Diseased"
                        : "Healthy"
                      : "Unknown";
                  const conf = point.confidence ?? point.score ?? 0;
                  return (
                    <div
                      style={{
                        backgroundColor: "rgba(255,255,255,0.95)",
                        borderRadius: "16px",
                        border: "1px solid #86efac",
                        color: "#065f46",
                        padding: "12px",
                      }}
                    >
                      <p
                        style={{
                          color: "#047857",
                          fontWeight: 600,
                          marginBottom: "8px",
                        }}
                      >
                        {label}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "14px" }}>
                        <strong>Prediction:</strong> {prediction}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "14px" }}>
                        <strong>Confidence:</strong> {Math.round(conf * 100)}%
                      </p>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Line
              type="monotone"
              dataKey="yValue"
              name="Status index"
              stroke="url(#statusGradient)"
              strokeWidth={3}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
