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

type ChartDatum = PlantTimeSeriesPoint & { label: string };

function formatPoints(points: PlantTimeSeriesPoint[]): ChartDatum[] {
  return points.map((point) => ({
    ...point,
    label: formatTimestampSGT(point.timestamp, "MMM d, HH:mm"),
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
        Disease detection
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
                color: "#065f46",
                padding: "12px",
              }}
              labelStyle={{
                color: "#047857",
                fontWeight: 600,
                marginBottom: "8px",
              }}
              formatter={(value: number | string, name: string, props: any) => {
                if (name === "confidence") {
                  return [
                    `${Math.round((value as number) * 100)}%`,
                    "Model Confidence",
                  ];
                }
                if (name === "prediction") {
                  return [value, "Prediction"];
                }
                return [value, name];
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
              dataKey="score"
              name="Model confidence"
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
