import { useState } from "react";

type ToggleState = "idle" | "pending" | "success";

type ControlPanelProps = {
  plantId: string;
  profileLabel?: string;
};

type ActionKey = "lights" | "pump" | "fan";

const ACTION_META: Record<
  ActionKey,
  { label: string; icon: string; accent: string }
> = {
  lights: {
    label: "Toggle Grow Lights",
    icon: "💡",
    accent: "from-amber-200 to-amber-100"
  },
  pump: {
    label: "Water Boost",
    icon: "💧",
    accent: "from-sky-200 to-sky-100"
  },
  fan: {
    label: "Cooling Breeze",
    icon: "🌀",
    accent: "from-emerald-200 to-emerald-100"
  }
};

export default function ControlPanel({ plantId, profileLabel }: ControlPanelProps) {
  const [state, setState] = useState<Record<ActionKey, ToggleState>>({
    lights: "idle",
    pump: "idle",
    fan: "idle"
  });

  function trigger(action: ActionKey) {
    setState((prev) => ({ ...prev, [action]: "pending" }));
    setTimeout(() => {
      setState((prev) => ({ ...prev, [action]: "success" }));
      setTimeout(
        () => setState((prev) => ({ ...prev, [action]: "idle" })),
        1500
      );
    }, 800);
  }

  return (
    <section className="card-surface space-y-4">
      <header className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-emerald-900 sm:text-xl">
              Remote actions
            </h3>
            <p className="text-xs text-emerald-700/70 sm:text-sm">
              Command relays are not wired yet—these buttons simulate how you will
              trigger actuators for <strong>{plantId}</strong>.
            </p>
          </div>
          {profileLabel && (
            <span className="pill bg-bloom-100 text-bloom-600 text-[0.65rem] sm:text-xs">
              {profileLabel} profile
            </span>
          )}
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-3 sm:grid-cols-2">
        {(Object.entries(ACTION_META) as [ActionKey, (typeof ACTION_META)[ActionKey]][]).map(([action, meta]) => {
          const status = state[action];
          const isPending = status === "pending";
          const isSuccess = status === "success";
          return (
            <button
              key={action}
              type="button"
              onClick={() => trigger(action)}
              disabled={isPending}
              className={`flex h-20 w-full items-center justify-between rounded-3xl border px-5 py-4 text-left shadow transition ${
                isSuccess
                  ? "border-emerald-400 bg-emerald-100 text-emerald-800"
                  : `border-emerald-200 bg-gradient-to-br ${meta.accent} text-emerald-700 hover:-translate-y-1 hover:shadow-card disabled:cursor-wait`
              }`}
            >
              <div className="flex items-center gap-3 text-sm font-semibold sm:text-base">
                <span aria-hidden className="text-xl sm:text-2xl">{meta.icon}</span>
                <span className="leading-tight">{meta.label}</span>
              </div>
              <span className="rounded-full bg-white/70 px-3 py-1 text-[0.65rem] text-emerald-600/90 shadow sm:text-xs">
                {status === "idle" && "Ready"}
                {isPending && "Contacting controller..."}
                {isSuccess && "Simulated run complete"}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

