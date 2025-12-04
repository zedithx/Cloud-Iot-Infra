import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { sendActuatorCommand, fetchThresholdRecommendations, type ActuatorCommand } from "@/lib/api";
import type { PlantProfile } from "@/lib/plantProfiles";

// localStorage key prefix for persisting actuator state
const getStorageKey = (plantId: string, action: ActionKey, type: "loading" | "cooldown") =>
  `actuator_${plantId}_${action}_${type}`;

// localStorage key for persisting current target values
const getTargetStorageKey = (plantId: string, metric: MetricKey) =>
  `target_${plantId}_${metric}`;

// Helper functions to save/load target values from localStorage
function saveTargetToStorage(plantId: string, metric: MetricKey, value: number): void {
  if (typeof window === "undefined") return;
  try {
    const key = getTargetStorageKey(plantId, metric);
    localStorage.setItem(key, value.toString());
  } catch (error) {
    console.error(`Failed to save target for ${metric}:`, error);
  }
}

function loadTargetFromStorage(plantId: string, metric: MetricKey): number | null {
  if (typeof window === "undefined") return null;
  try {
    const key = getTargetStorageKey(plantId, metric);
    const stored = localStorage.getItem(key);
    if (!stored) return null;
    const value = parseFloat(stored);
    return isNaN(value) ? null : value;
  } catch (error) {
    console.error(`Failed to load target for ${metric}:`, error);
    return null;
  }
}

type ToggleState = "idle" | "pending" | "success" | "error";

type ControlPanelProps = {
  plantId: string;
  plantName?: string;
  profileLabel?: string;
  selectedProfile?: PlantProfile;
  currentValues?: {
    soilMoisture?: number | null;
    humidity?: number | null;
    temperatureC?: number | null;
    lightLux?: number | null;
  };
};

type ActionKey = "lights" | "pump" | "fan";

const LOADING_SECONDS = 5; // 5 seconds loading state after command sent

// Metric-focused configuration (instead of actuator-focused)
// Focus on soil moisture, temperature, and light lux
const METRIC_META: Record<
  "soilMoisture" | "temperatureC" | "lightLux",
  {
    label: string;
    icon: string;
    accent: string;
    actuator: "pump" | "fan" | "lights";
    unit: string;
    min: number;
    max: number;
    step: number;
    formatValue: (val: number) => number;
    parseValue: (val: number) => number;
  }
> = {
  soilMoisture: {
    label: "Soil Moisture",
    icon: "💧",
    accent: "from-sky-200 to-sky-100",
    actuator: "pump",
    unit: "%",
    min: 0,
    max: 100,
    step: 1,
    formatValue: (val) => Math.round(val * 100),
    parseValue: (val) => val / 100,
  },
  temperatureC: {
    label: "Temperature",
    icon: "🌡️",
    accent: "from-emerald-200 to-emerald-100",
    actuator: "fan",
    unit: "°C",
    min: 10,
    max: 40,
    step: 1,
    formatValue: (val) => Math.round(val),
    parseValue: (val) => val,
  },
  lightLux: {
    label: "Light Intensity",
    icon: "💡",
    accent: "from-amber-200 to-amber-100",
    actuator: "lights",
    unit: "lux",
    min: 0,
    max: 100000,
    step: 100,
    formatValue: (val) => val,
    parseValue: (val) => val,
  },
};

// Keep ACTION_META for backward compatibility with existing code
const ACTION_META: Record<
  ActionKey,
  {
    label: string;
    icon: string;
    accent: string;
    metric: "soilMoisture" | "temperatureC" | "lightLux";
    unit: string;
    min: number;
    max: number;
    step: number;
    formatValue: (val: number) => number;
    parseValue: (val: number) => number;
  }
> = {
  lights: {
    label: "Grow Lights",
    icon: "💡",
    accent: "from-amber-200 to-amber-100",
    metric: "lightLux",
    unit: "lux",
    min: 0,
    max: 100000,
    step: 100,
    formatValue: (val) => val,
    parseValue: (val) => val,
  },
  pump: {
    label: "Water Pump",
    icon: "💧",
    accent: "from-sky-200 to-sky-100",
    metric: "soilMoisture",
    unit: "%",
    min: 0,
    max: 100,
    step: 1,
    formatValue: (val) => Math.round(val * 100),
    parseValue: (val) => val / 100,
  },
  fan: {
    label: "Cooling Fan",
    icon: "🌀",
    accent: "from-emerald-200 to-emerald-100",
    metric: "temperatureC",
    unit: "°C",
    min: -50,
    max: 100,
    step: 0.1,
    formatValue: (val) => val,
    parseValue: (val) => val,
  },
};

type MetricKey = "soilMoisture" | "temperatureC" | "lightLux";

export default function ControlPanel({
  plantId,
  plantName,
  profileLabel,
  selectedProfile,
  currentValues = {},
}: ControlPanelProps) {
  // Calculate default target values from plant profile averages
  const getDefaultTargetValue = (metric: MetricKey): string => {
    if (!selectedProfile) return "";
    const profileMetric = selectedProfile.metrics[metric];
    if (!profileMetric) return "";
    const average = (profileMetric.min + profileMetric.max) / 2;
    // Format based on metric type
    if (metric === "soilMoisture") {
      // Profile values are in 0-1 range, convert to percentage (0-100) for display
      return Math.round(average * 100).toString();
    } else if (metric === "lightLux") {
      return Math.round(average).toString();
    } else {
      // temperatureC - already in °C, round to whole number
      return Math.round(average).toString();
    }
  };

  // State for metrics (soil moisture, temperature, light lux)
  const [state, setState] = useState<Record<MetricKey, ToggleState>>({
    soilMoisture: "idle",
    temperatureC: "idle",
    lightLux: "idle",
  });
  const [targetValues, setTargetValues] = useState<Record<MetricKey, string>>({
    soilMoisture: getDefaultTargetValue("soilMoisture"),
    temperatureC: getDefaultTargetValue("temperatureC"),
    lightLux: getDefaultTargetValue("lightLux"),
  });
  const [errors, setErrors] = useState<Record<MetricKey, string>>({
    soilMoisture: "",
    temperatureC: "",
    lightLux: "",
  });
  const [currentThresholds, setCurrentThresholds] = useState<Record<MetricKey, number | null>>({
    soilMoisture: null,
    temperatureC: null,
    lightLux: null,
  });
  const [isLoadingThresholds, setIsLoadingThresholds] = useState(true);
  const [loadingStartTime, setLoadingStartTime] = useState<
    Record<ActionKey, number | null>
  >({
    lights: null,
    pump: null,
    fan: null,
  });
  const [loadingRemaining, setLoadingRemaining] = useState<
    Record<ActionKey, number>
  >({
    lights: 0,
    pump: 0,
    fan: 0,
  });

  // Update default target values when profile changes (only if no persisted values exist)
  useEffect(() => {
    if (selectedProfile) {
      // Check if we have persisted values first
      // For soil moisture, if value is <= 1, it's in old format (0-1), convert to percentage
      const rawSoil = loadTargetFromStorage(plantId, "soilMoisture");
      const persistedSoil = rawSoil !== null && rawSoil <= 1 ? rawSoil * 100 : rawSoil;
      // Check for old humidity key first, then temperatureC (for migration)
      const oldHumidityKey = `target_${plantId}_humidity`;
      const oldHumidity = typeof window !== "undefined" ? (() => {
        try {
          const stored = localStorage.getItem(oldHumidityKey);
          return stored ? parseFloat(stored) : null;
        } catch {
          return null;
        }
      })() : null;
      const persistedTemperature = loadTargetFromStorage(plantId, "temperatureC") ?? oldHumidity;
      const persistedLight = loadTargetFromStorage(plantId, "lightLux");
      
      // Only set defaults if no persisted values exist
      if (persistedSoil === null && persistedTemperature === null && persistedLight === null) {
        const getDefault = (metric: MetricKey): string => {
          const profileMetric = selectedProfile.metrics[metric];
          if (!profileMetric) return "";
          const average = (profileMetric.min + profileMetric.max) / 2;
          if (metric === "soilMoisture") {
            return average.toFixed(2);
          } else if (metric === "lightLux") {
            return Math.round(average).toString();
          } else {
            return Math.round(average).toString();
          }
        };
        
        const defaultValues = {
          soilMoisture: getDefault("soilMoisture"),
          temperatureC: getDefault("temperatureC"),
          lightLux: getDefault("lightLux"),
        };
        
        setTargetValues(defaultValues);
        
        // Persist the default values
        // For soil moisture, defaultValues is already in percentage (from profile min/max which are in 0-1 range, converted to percentage)
        if (defaultValues.soilMoisture) {
          // defaultValues.soilMoisture is already in percentage format (0-100)
          saveTargetToStorage(plantId, "soilMoisture", parseFloat(defaultValues.soilMoisture));
        }
        if (defaultValues.temperatureC) {
          saveTargetToStorage(plantId, "temperatureC", parseFloat(defaultValues.temperatureC));
        }
        if (defaultValues.lightLux) {
          saveTargetToStorage(plantId, "lightLux", parseFloat(defaultValues.lightLux));
        }
      } else {
        // Use persisted values in the target input fields and currentThresholds
        // For soil moisture, convert from percentage to display value (already handled in persistedSoil conversion above)
        setTargetValues({
          soilMoisture: persistedSoil !== null ? Math.round(persistedSoil).toString() : "",
          temperatureC: persistedTemperature !== null ? Math.round(persistedTemperature).toString() : "",
          lightLux: persistedLight !== null ? Math.round(persistedLight).toString() : "",
        });
        // Also update currentThresholds to show persisted values (already in percentage for soil moisture)
        setCurrentThresholds({
          soilMoisture: persistedSoil,
          temperatureC: persistedTemperature,
          lightLux: persistedLight,
        });
      }
    }
  }, [selectedProfile, plantId]);

  // Load current thresholds from localStorage first, then from API
  useEffect(() => {
    // First, load from localStorage (persisted values)
    // For soil moisture, if value is <= 1, it's in old format (0-1), convert to percentage
    const rawSoil = loadTargetFromStorage(plantId, "soilMoisture");
    const persistedSoil = rawSoil !== null && rawSoil <= 1 ? rawSoil * 100 : rawSoil;
    // Check for old humidity key first, then temperatureC (for migration)
    const oldHumidityKey = `target_${plantId}_humidity`;
    const oldHumidity = typeof window !== "undefined" ? (() => {
      try {
        const stored = localStorage.getItem(oldHumidityKey);
        return stored ? parseFloat(stored) : null;
      } catch {
        return null;
      }
    })() : null;
    const persistedTemperature = loadTargetFromStorage(plantId, "temperatureC") ?? oldHumidity;
    
    const persistedThresholds: Record<MetricKey, number | null> = {
      soilMoisture: persistedSoil,
      temperatureC: persistedTemperature,
      lightLux: loadTargetFromStorage(plantId, "lightLux"),
    };
    
    // Always set persisted values immediately (even if null)
    setCurrentThresholds(persistedThresholds);
    const hasPersistedValues = Object.values(persistedThresholds).some(v => v !== null);
    if (hasPersistedValues) {
      setIsLoadingThresholds(false);
    }
    
    // Then try to fetch from API to update if available
    async function loadThresholds() {
      try {
        if (!hasPersistedValues) {
          setIsLoadingThresholds(true);
        }
        const recommendations = await fetchThresholdRecommendations(plantId, 24);
        
        // Map recommendations to metrics
        const apiThresholds: Record<MetricKey, number | null> = {
          soilMoisture: null,
          temperatureC: null,
          lightLux: null,
        };
        
        recommendations.recommendations.forEach((rec) => {
          if (rec.actuator === "pump" && rec.currentThreshold !== null && rec.currentThreshold !== undefined) {
            // API returns soil moisture in 0-1 range, convert to percentage (0-100) for display
            apiThresholds.soilMoisture = rec.currentThreshold <= 1 ? rec.currentThreshold * 100 : rec.currentThreshold;
          } else if (rec.actuator === "fan" && rec.currentThreshold !== null && rec.currentThreshold !== undefined) {
            apiThresholds.temperatureC = rec.currentThreshold;
          } else if (rec.actuator === "lights" && rec.currentThreshold !== null && rec.currentThreshold !== undefined) {
            apiThresholds.lightLux = rec.currentThreshold;
          }
        });
        
        // Merge: use API values if available, otherwise keep persisted values
        const mergedThresholds: Record<MetricKey, number | null> = {
          soilMoisture: apiThresholds.soilMoisture ?? persistedThresholds.soilMoisture,
          temperatureC: apiThresholds.temperatureC ?? persistedThresholds.temperatureC,
          lightLux: apiThresholds.lightLux ?? persistedThresholds.lightLux,
        };
        
        setCurrentThresholds(mergedThresholds);
        
        // Persist any API values that we got (they override localStorage)
        Object.entries(mergedThresholds).forEach(([metric, value]) => {
          if (value !== null) {
            saveTargetToStorage(plantId, metric as MetricKey, value);
          }
        });
      } catch (error) {
        console.error("Failed to load thresholds from API:", error);
        // Keep persisted values if API fails
      } finally {
        setIsLoadingThresholds(false);
      }
    }
    
    void loadThresholds();
  }, [plantId]);

  // Load persisted state from localStorage on mount
  useEffect(() => {
    const now = Date.now();
    const loadedLoadingStartTime: Record<ActionKey, number | null> = {
      lights: null,
      pump: null,
      fan: null,
    };

    (Object.keys(ACTION_META) as ActionKey[]).forEach((action) => {
      // Load loading start time
      const loadingKey = getStorageKey(plantId, action, "loading");
      const storedLoading = localStorage.getItem(loadingKey);
      if (storedLoading) {
        const loadingStart = parseInt(storedLoading, 10);
        const elapsed = Math.floor((now - loadingStart) / 1000);
        if (elapsed < LOADING_SECONDS) {
          // Still in loading period
          loadedLoadingStartTime[action] = loadingStart;
        } else {
          // Loading completed, clear it
          localStorage.removeItem(loadingKey);
        }
      }

    });
    
    // Also initialize state for metrics
    const loadedState: Record<MetricKey, ToggleState> = {
      soilMoisture: "idle",
      temperatureC: "idle",
      lightLux: "idle",
    };
    setState(loadedState);

    setLoadingStartTime(loadedLoadingStartTime);
  }, [plantId]);

  // Update loading timers every second
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      
      // Update loading timers
      setLoadingRemaining((prev) => {
        const updated: Record<ActionKey, number> = { ...prev };
        const metricToAction: Record<MetricKey, ActionKey> = {
          soilMoisture: "pump",
          temperatureC: "fan",
          lightLux: "lights",
        };
        (Object.keys(METRIC_META) as MetricKey[]).forEach((metric) => {
          const action = metricToAction[metric];
          const startTime = loadingStartTime[action];
          if (startTime !== null) {
            const elapsed = Math.floor((now - startTime) / 1000);
            const remaining = Math.max(0, LOADING_SECONDS - elapsed);
            updated[action] = remaining;
            
            // When loading completes, clean up
            if (remaining === 0) {
              setLoadingStartTime((prevTime) => {
                const loadingKey = getStorageKey(plantId, action, "loading");
                localStorage.removeItem(loadingKey);
                  return {
                    ...prevTime,
                  [action]: null,
                  };
              });
            }
          } else {
            updated[action] = 0;
          }
        });
        return updated;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [loadingStartTime, plantId]);

  function getCurrentValue(metric: MetricKey): number | null {
    const meta = METRIC_META[metric];
    const rawValue = currentValues[metric];
    if (rawValue === null || rawValue === undefined) {
      return null;
    }
    return meta.formatValue(rawValue);
  }

  function formatCooldown(seconds: number): string {
    if (seconds <= 0) return "";
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  }

  function generateRangeOptions(
    currentValue: number,
    meta: (typeof METRIC_META)[MetricKey]
  ): Array<{ value: string; label: string }> {
    const options: Array<{ value: string; label: string }> = [];
    
    if (meta.actuator === "pump") {
      // Soil moisture: current ± 10%, 20%, 30% in 5% increments
      const currentPercent = currentValue;
      const ranges = [-30, -25, -20, -15, -10, -5, 5, 10, 15, 20, 25, 30];
      ranges.forEach((delta) => {
        const target = Math.max(0, Math.min(100, currentPercent + delta));
        if (target >= 0 && target <= 100) {
          options.push({
            value: (target / 100).toFixed(2), // Convert to 0-1 range for API
            label: `${target}% ${delta > 0 ? `(+${delta}%)` : `(${delta}%)`}`,
          });
        }
      });
    } else if (meta.actuator === "fan") {
      // Temperature: current ± 2°C, 3°C, 4°C, 5°C
      const ranges = [-5, -4, -3, -2, 2, 3, 4, 5];
      ranges.forEach((delta) => {
        const target = Math.max(0, Math.min(100, currentValue + delta));
        if (target >= 0 && target <= 100) {
          options.push({
            value: target.toFixed(1),
            label: `${target}% ${delta > 0 ? `(+${delta}%)` : `(${delta}%)`}`,
          });
        }
      });
    } else if (meta.actuator === "lights") {
      // Light: current ± 10%, 20%, 30%, 50% in 5% increments
      const ranges = [-50, -40, -30, -25, -20, -15, -10, -5, 5, 10, 15, 20, 25, 30, 40, 50];
      ranges.forEach((delta) => {
        const target = Math.round(currentValue * (1 + delta / 100));
        if (target >= meta.min && target <= meta.max) {
          options.push({
            value: target.toString(),
            label: `${target.toLocaleString()} lux ${delta > 0 ? `(+${delta}%)` : `(${delta}%)`}`,
          });
        }
      });
    }
    
    // Remove duplicates based on value, keeping the first occurrence
    const uniqueOptions: Array<{ value: string; label: string }> = [];
    const seenValues = new Set<string>();
    for (const option of options) {
      if (!seenValues.has(option.value)) {
        seenValues.add(option.value);
        uniqueOptions.push(option);
      }
    }
    
    // Sort by value
    return uniqueOptions.sort((a, b) => parseFloat(a.value) - parseFloat(b.value));
  }

  async function trigger(metric: MetricKey) {
    const meta = METRIC_META[metric];
    const targetValueStr = targetValues[metric].trim();
    
      // Map metric to action for loading checks
      const metricToAction: Record<MetricKey, ActionKey> = {
        soilMoisture: "pump",
        temperatureC: "fan",
        lightLux: "lights",
      };
      const action = metricToAction[metric];

    // Check loading state
    if (loadingRemaining[action] > 0) {
      return;
    }

    if (!targetValueStr) {
      setErrors((prev) => ({
        ...prev,
        [action]: "Please enter a target value",
      }));
      return;
    }

    const targetValueNum = parseFloat(targetValueStr);
    if (isNaN(targetValueNum)) {
      setErrors((prev) => ({
        ...prev,
        [action]: "Invalid number",
      }));
      return;
    }

    if (targetValueNum < meta.min || targetValueNum > meta.max) {
      setErrors((prev) => ({
        ...prev,
        [action]: `Value must be between ${meta.min} and ${meta.max} ${meta.unit}`,
      }));
      return;
    }

    setErrors((prev) => ({ ...prev, [metric]: "" }));
    setState((prev) => ({ ...prev, [metric]: "pending" }));

    try {
      // Parse the value based on metric type
      let parsedValue: number;
      if (metric === "soilMoisture") {
        // Soil moisture: input is percentage (0-100), convert to 0-1 range
        // Round to whole number percentage first
        const roundedPercent = Math.round(targetValueNum);
        parsedValue = roundedPercent / 100;
      } else if (metric === "temperatureC") {
        // Temperature: input is in °C, round to whole number
        parsedValue = Math.round(targetValueNum);
      } else {
        // Light lux: use parseValue as-is
        parsedValue = meta.parseValue(targetValueNum);
      }
      
      // Map metric to the correct API metric name
      const metricToApiMetric: Record<MetricKey, "soilMoisture" | "temperatureC" | "lightLux"> = {
        soilMoisture: "soilMoisture",
        temperatureC: "temperatureC",
        lightLux: "lightLux",
      };
      
      const command: ActuatorCommand = {
        actuator: action,
        targetValue: parsedValue,
        metric: metricToApiMetric[metric],
      };

      await sendActuatorCommand(plantId, command);
      setState((prev) => ({ ...prev, [metric]: "success" }));
      
      // Start loading state (5 seconds)
      const now = Date.now();
      const loadingKey = getStorageKey(plantId, action, "loading");
      localStorage.setItem(loadingKey, now.toString());
      setLoadingStartTime((prev) => ({
        ...prev,
        [action]: now,
      }));
      setLoadingRemaining((prev) => ({
        ...prev,
        [action]: LOADING_SECONDS,
      }));

      // Show success notification after loading completes
      setTimeout(() => {
        const displayValue = meta.formatValue(parsedValue);
        // Format display value: whole numbers for temperature and soil moisture, decimals for light lux
        const formattedDisplayValue = 
          metric === "temperatureC" || metric === "soilMoisture"
            ? Math.round(displayValue).toString()
            : metric === "lightLux"
            ? Math.round(displayValue).toLocaleString()
            : displayValue.toFixed(1);
        const actuatorName = meta.actuator === "pump" ? "Water Pump" : meta.actuator === "fan" ? "Cooling Fan" : "Grow Lights";
        const deviceName = plantName || plantId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
        toast.success(
          `${meta.label} target (${formattedDisplayValue} ${meta.unit}) set successfully on ${deviceName}. ${actuatorName} activated.`,
          {
            duration: 5000,
            icon: "✅",
          }
        );
      }, LOADING_SECONDS * 1000);
      
      // Update current threshold after setting and persist to localStorage
      // For soil moisture, store as percentage (0-100) in localStorage, but keep parsedValue (0-1) for API
      const valueToStore = metric === "soilMoisture" ? parsedValue * 100 : parsedValue;
      setCurrentThresholds((prev) => ({
        ...prev,
        [metric]: valueToStore, // Store percentage for display
      }));
      saveTargetToStorage(plantId, metric, valueToStore);
      setTimeout(
        () => setState((prev) => ({ ...prev, [metric]: "idle" })),
        2000
      );
    } catch (error) {
      setState((prev) => ({ ...prev, [metric]: "error" }));
      const errorMessage = error instanceof Error ? error.message : "Failed to send command";
      setErrors((prev) => ({
        ...prev,
        [metric]: errorMessage,
      }));
      toast.error(`${meta.icon} Failed to set target value for ${meta.label}: ${errorMessage}`);
      setTimeout(
        () => setState((prev) => ({ ...prev, [metric]: "idle" })),
        3000
      );
    }
  }

  return (
    <section className="card-surface space-y-4">
      <header className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-emerald-900 sm:text-xl">
              Target Value Control
            </h3>
            <p className="text-xs text-emerald-700/70 sm:text-sm">
              Set target values for soil moisture, temperature, and light intensity for <strong>{plantName || plantId}</strong>.
              The system will automatically activate actuators to maintain these target values.
            </p>
          </div>
          {profileLabel && (
            <span className="pill bg-bloom-100 text-bloom-600 text-[0.65rem] sm:text-xs">
              {profileLabel} profile
            </span>
          )}
        </div>
      </header>

      <div className="grid gap-4 md:grid-cols-3 sm:grid-cols-2">
        {(Object.entries(METRIC_META) as [MetricKey, (typeof METRIC_META)[MetricKey]][]).map(
          ([metric, meta]) => {
            const status = state[metric];
            const isPending = status === "pending";
            const isSuccess = status === "success";
            const isError = status === "error";
            const currentValue = getCurrentValue(metric);
            const error = errors[metric];
            const currentThreshold = currentThresholds[metric];
            
            // Map metric to action for loading
            const metricToAction: Record<MetricKey, ActionKey> = {
              soilMoisture: "pump",
              temperatureC: "fan",
              lightLux: "lights",
            };
            const action = metricToAction[metric];
            const loading = loadingRemaining[action];
            const isLoading = loading > 0;

            return (
              <div
                key={metric}
                className={`flex flex-col gap-3 rounded-3xl border p-4 shadow transition ${
                  isSuccess
                    ? "border-emerald-400 bg-emerald-50"
                    : isError
                      ? "border-rose-300 bg-rose-50"
                      : `border-emerald-200 bg-gradient-to-br ${meta.accent}`
                }`}
              >
                <div className="flex items-center gap-2">
                  <span aria-hidden className="text-xl sm:text-2xl">
                    {meta.icon}
                  </span>
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-emerald-900 sm:text-base">
                      {meta.label}
                    </h4>
                    {currentThreshold !== null && (
                      <p className="text-xs text-emerald-600 font-medium">
                        Current target: {
                          metric === "lightLux" 
                            ? Math.round(currentThreshold).toFixed(0)
                            : metric === "temperatureC" || metric === "soilMoisture"
                            ? Math.round(currentThreshold).toFixed(0)
                            : currentThreshold.toFixed(1)
                        } {meta.unit}
                      </p>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  {/* Range selector based on current value */}
                  <div className="space-y-2">
                    <label className="text-xs font-medium text-emerald-700">
                      Set target value:
                    </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={meta.min}
                      max={meta.max}
                      step={meta.step}
                        value={targetValues[metric]}
                      onChange={(e) =>
                        setTargetValues((prev) => ({
                          ...prev,
                            [metric]: e.target.value,
                        }))
                      }
                      placeholder={`Target ${meta.unit}`}
                        disabled={isPending || isLoading}
                      className="flex-1 rounded-full border border-emerald-200 bg-white px-3 py-2 text-sm text-emerald-800 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 disabled:bg-emerald-50 disabled:text-emerald-500"
                    />
                    <span className="text-xs text-emerald-600">{meta.unit}</span>
                    </div>
                  </div>
                  {error && (
                    <p className="text-xs text-rose-600">{error}</p>
                  )}
                  {isLoading && (
                    <p className="text-xs text-blue-600 font-medium">
                      Setting target value on device: {formatCooldown(loading)}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={() => trigger(metric)}
                    disabled={isPending || isLoading}
                    className={`w-full rounded-full px-4 py-2 text-sm font-semibold transition ${
                      isSuccess && !isLoading
                        ? "bg-emerald-500 text-white"
                        : isError
                          ? "bg-rose-500 text-white"
                          : isLoading
                            ? "bg-blue-200 text-blue-700 cursor-wait"
                              : "bg-white text-emerald-700 hover:bg-emerald-50 disabled:cursor-wait disabled:opacity-50"
                    }`}
                  >
                    {isLoading && `Setting target value on device: ${formatCooldown(loading)}`}
                    {!isLoading && status === "idle" && "Set Target Value"}
                    {!isLoading && isPending && "Setting..."}
                    {!isLoading && isSuccess && "Target Set!"}
                    {!isLoading && isError && "Failed"}
                  </button>
                </div>
              </div>
            );
          }
        )}
      </div>
    </section>
  );
}

