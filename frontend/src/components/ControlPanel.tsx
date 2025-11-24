import { useEffect, useState } from "react";
import { sendActuatorCommand, type ActuatorCommand } from "@/lib/api";

// localStorage key prefix for persisting actuator state
const getStorageKey = (plantId: string, action: ActionKey, type: "loading" | "cooldown") =>
  `actuator_${plantId}_${action}_${type}`;

type ToggleState = "idle" | "pending" | "success" | "error";

type ControlPanelProps = {
  plantId: string;
  profileLabel?: string;
  currentValues?: {
    soilMoisture?: number | null;
    temperatureC?: number | null;
    lightLux?: number | null;
  };
};

type ActionKey = "lights" | "pump" | "fan";

const COOLDOWN_SECONDS = 5 * 60; // 5 minutes
const LOADING_SECONDS = 20; // 20 seconds loading state after command sent

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

export default function ControlPanel({
  plantId,
  profileLabel,
  currentValues = {},
}: ControlPanelProps) {
  const [state, setState] = useState<Record<ActionKey, ToggleState>>({
    lights: "idle",
    pump: "idle",
    fan: "idle",
  });
  const [targetValues, setTargetValues] = useState<Record<ActionKey, string>>({
    lights: "",
    pump: "",
    fan: "",
  });
  const [errors, setErrors] = useState<Record<ActionKey, string>>({
    lights: "",
    pump: "",
    fan: "",
  });
  const [lastActivationTime, setLastActivationTime] = useState<
    Record<ActionKey, number | null>
  >({
    lights: null,
    pump: null,
    fan: null,
  });
  const [cooldownRemaining, setCooldownRemaining] = useState<
    Record<ActionKey, number>
  >({
    lights: 0,
    pump: 0,
    fan: 0,
  });
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

  // Load persisted state from localStorage on mount
  useEffect(() => {
    const now = Date.now();
    const loadedLoadingStartTime: Record<ActionKey, number | null> = {
      lights: null,
      pump: null,
      fan: null,
    };
    const loadedLastActivationTime: Record<ActionKey, number | null> = {
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

      // Load cooldown start time
      const cooldownKey = getStorageKey(plantId, action, "cooldown");
      const storedCooldown = localStorage.getItem(cooldownKey);
      if (storedCooldown) {
        const cooldownStart = parseInt(storedCooldown, 10);
        const elapsed = Math.floor((now - cooldownStart) / 1000);
        if (elapsed < COOLDOWN_SECONDS) {
          // Still in cooldown period
          loadedLastActivationTime[action] = cooldownStart;
        } else {
          // Cooldown completed, clear it
          localStorage.removeItem(cooldownKey);
        }
      }
    });

    setLoadingStartTime(loadedLoadingStartTime);
    setLastActivationTime(loadedLastActivationTime);
  }, [plantId]);

  // Update loading and cooldown timers every second
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      
      // Update loading timers
      setLoadingRemaining((prev) => {
        const updated: Record<ActionKey, number> = { ...prev };
        (Object.keys(ACTION_META) as ActionKey[]).forEach((action) => {
          const startTime = loadingStartTime[action];
          if (startTime !== null) {
            const elapsed = Math.floor((now - startTime) / 1000);
            const remaining = Math.max(0, LOADING_SECONDS - elapsed);
            updated[action] = remaining;
            
            // When loading completes, start cooldown
            if (remaining === 0) {
              setLastActivationTime((prevTime) => {
                // Only set if not already set (to avoid overwriting)
                if (prevTime[action] === null) {
                  const cooldownKey = getStorageKey(plantId, action, "cooldown");
                  localStorage.setItem(cooldownKey, now.toString());
                  return {
                    ...prevTime,
                    [action]: now,
                  };
                }
                return prevTime;
              });
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
      
      // Update cooldown timers
      setCooldownRemaining((prev) => {
        const updated: Record<ActionKey, number> = { ...prev };
        (Object.keys(ACTION_META) as ActionKey[]).forEach((action) => {
          const lastTime = lastActivationTime[action];
          if (lastTime !== null) {
            const elapsed = Math.floor((now - lastTime) / 1000);
            const remaining = Math.max(0, COOLDOWN_SECONDS - elapsed);
            updated[action] = remaining;
            
            // Clean up localStorage when cooldown completes
            if (remaining === 0) {
              const cooldownKey = getStorageKey(plantId, action, "cooldown");
              localStorage.removeItem(cooldownKey);
              setLastActivationTime((prevTime) => ({
                ...prevTime,
                [action]: null,
              }));
            }
          } else {
            updated[action] = 0;
          }
        });
        return updated;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [lastActivationTime, loadingStartTime]);

  function getCurrentValue(action: ActionKey): number | null {
    const meta = ACTION_META[action];
    const rawValue = currentValues[meta.metric];
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
    meta: (typeof ACTION_META)[ActionKey]
  ): Array<{ value: string; label: string }> {
    const options: Array<{ value: string; label: string }> = [];
    
    if (meta.metric === "soilMoisture") {
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
    } else if (meta.metric === "temperatureC") {
      // Temperature: current ± 1°C, 2°C, 3°C, 5°C, 10°C
      const ranges = [-10, -5, -3, -2, -1, 1, 2, 3, 5, 10];
      ranges.forEach((delta) => {
        const target = currentValue + delta;
        if (target >= meta.min && target <= meta.max) {
          options.push({
            value: target.toFixed(1),
            label: `${target}°C ${delta > 0 ? `(+${delta}°C)` : `(${delta}°C)`}`,
          });
        }
      });
    } else if (meta.metric === "lightLux") {
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
    
    // Sort by value
    return options.sort((a, b) => parseFloat(a.value) - parseFloat(b.value));
  }

  async function trigger(action: ActionKey) {
    const meta = ACTION_META[action];
    const targetValueStr = targetValues[action].trim();

    // Check cooldown and loading state
    if (cooldownRemaining[action] > 0 || loadingRemaining[action] > 0) {
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

    setErrors((prev) => ({ ...prev, [action]: "" }));
    setState((prev) => ({ ...prev, [action]: "pending" }));

    try {
      // For soil moisture, if the value is already in 0-1 range (from dropdown), use it directly
      // Otherwise, parse it (for manual input in percentage)
      let parsedValue: number;
      if (meta.metric === "soilMoisture" && targetValueNum <= 1.0) {
        // Value is already in 0-1 range (from dropdown)
        parsedValue = targetValueNum;
      } else {
        // Value is in percentage or other format, use parseValue
        parsedValue = meta.parseValue(targetValueNum);
      }
      const command: ActuatorCommand = {
        actuator: action,
        targetValue: parsedValue,
        metric: meta.metric,
      };

      await sendActuatorCommand(plantId, command);
      setState((prev) => ({ ...prev, [action]: "success" }));
      
      // Start loading state (20 seconds)
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

      // After loading completes, cooldown will start automatically via useEffect
      setTimeout(
        () => setState((prev) => ({ ...prev, [action]: "idle" })),
        2000
      );
    } catch (error) {
      setState((prev) => ({ ...prev, [action]: "error" }));
      setErrors((prev) => ({
        ...prev,
        [action]:
          error instanceof Error ? error.message : "Failed to send command",
      }));
      setTimeout(
        () => setState((prev) => ({ ...prev, [action]: "idle" })),
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
              Remote actuator control
            </h3>
            <p className="text-xs text-emerald-700/70 sm:text-sm">
              Set target sensor values to activate actuators for <strong>{plantId}</strong>.
              Actuators will run until the sensor reaches the target value.
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
        {(Object.entries(ACTION_META) as [ActionKey, (typeof ACTION_META)[ActionKey]][]).map(
          ([action, meta]) => {
            const status = state[action];
            const isPending = status === "pending";
            const isSuccess = status === "success";
            const isError = status === "error";
            const currentValue = getCurrentValue(action);
            const error = errors[action];
            const cooldown = cooldownRemaining[action];
            const isOnCooldown = cooldown > 0;
            const loading = loadingRemaining[action];
            const isLoading = loading > 0;

            return (
              <div
                key={action}
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
                    {currentValue !== null && (
                      <p className="text-xs text-emerald-700">
                        Current: {currentValue.toFixed(meta.metric === "lightLux" ? 0 : 1)}{" "}
                        {meta.unit}
                      </p>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  {/* Show which metric is being controlled */}
                  <div className="flex items-center gap-2 text-xs text-emerald-600">
                    <span className="font-medium">Controlling:</span>
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5">
                      {meta.metric === "soilMoisture" && "Soil Moisture"}
                      {meta.metric === "temperatureC" && "Temperature"}
                      {meta.metric === "lightLux" && "Light Intensity"}
                    </span>
                  </div>
                  
                  {/* Range selector based on current value */}
                  {currentValue !== null ? (
                    <div className="space-y-2">
                      <label className="text-xs font-medium text-emerald-700">
                        Select target value (current: {currentValue.toFixed(meta.metric === "lightLux" ? 0 : 1)} {meta.unit})
                      </label>
                      <select
                        value={targetValues[action]}
                        onChange={(e) =>
                          setTargetValues((prev) => ({
                            ...prev,
                            [action]: e.target.value,
                          }))
                        }
                        disabled={isPending || isLoading || isOnCooldown}
                        className="w-full rounded-full border border-emerald-200 bg-white px-3 py-2 text-sm text-emerald-800 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 disabled:bg-emerald-50 disabled:text-emerald-500"
                      >
                        <option value="">Select target value...</option>
                        {generateRangeOptions(currentValue, meta).map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <label className="text-xs font-medium text-emerald-700">
                        Target {meta.unit}
                      </label>
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          min={meta.min}
                          max={meta.max}
                          step={meta.step}
                          value={targetValues[action]}
                          onChange={(e) =>
                            setTargetValues((prev) => ({
                              ...prev,
                              [action]: e.target.value,
                            }))
                          }
                          placeholder={`Target ${meta.unit}`}
                          disabled={isPending || isLoading || isOnCooldown}
                          className="flex-1 rounded-full border border-emerald-200 bg-white px-3 py-2 text-sm text-emerald-800 outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-200 disabled:bg-emerald-50 disabled:text-emerald-500"
                        />
                        <span className="text-xs text-emerald-600">{meta.unit}</span>
                      </div>
                    </div>
                  )}
                  {error && (
                    <p className="text-xs text-rose-600">{error}</p>
                  )}
                  {isLoading && (
                    <p className="text-xs text-blue-600 font-medium">
                      Processing: {formatCooldown(loading)}
                    </p>
                  )}
                  {!isLoading && isOnCooldown && (
                    <p className="text-xs text-amber-600 font-medium">
                      Cooldown: {formatCooldown(cooldown)}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={() => trigger(action)}
                    disabled={isPending || isLoading || isOnCooldown}
                    className={`w-full rounded-full px-4 py-2 text-sm font-semibold transition ${
                      isSuccess && !isLoading
                        ? "bg-emerald-500 text-white"
                        : isError
                          ? "bg-rose-500 text-white"
                          : isLoading
                            ? "bg-blue-200 text-blue-700 cursor-wait"
                            : isOnCooldown
                              ? "bg-slate-200 text-slate-500 cursor-not-allowed"
                              : "bg-white text-emerald-700 hover:bg-emerald-50 disabled:cursor-wait disabled:opacity-50"
                    }`}
                  >
                    {isLoading && `Processing: ${formatCooldown(loading)}`}
                    {!isLoading && isOnCooldown && `Cooldown: ${formatCooldown(cooldown)}`}
                    {!isLoading && !isOnCooldown && status === "idle" && "Activate"}
                    {!isLoading && !isOnCooldown && isPending && "Sending..."}
                    {!isLoading && !isOnCooldown && isSuccess && "Command sent!"}
                    {!isLoading && !isOnCooldown && isError && "Failed"}
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

