"use client";

import { getPlantName } from "@/lib/localStorage";

type DeleteConfirmationModalProps = {
  deviceId: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function DeleteConfirmationModal({
  deviceId,
  onConfirm,
  onCancel,
}: DeleteConfirmationModalProps) {
  const plantName = getPlantName(deviceId);
  const displayName = plantName || deviceId.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-rose-900">Remove Plant</h2>
          <button
            onClick={onCancel}
            className="rounded-full p-2 text-emerald-600 transition hover:bg-emerald-50"
            aria-label="Close modal"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-4">
            <p className="text-sm text-rose-700">
              Are you sure you want to remove{" "}
              <strong className="font-semibold text-rose-900">
                &quot;{displayName}&quot;
              </strong>{" "}
              from your dashboard?
            </p>
            <p className="mt-2 text-xs text-rose-600">
              This will remove the plant from your list, but you can always scan
              the QR code again to add it back.
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={onCancel}
              className="flex-1 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 font-semibold text-emerald-700 transition hover:bg-emerald-100"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              className="flex-1 rounded-full bg-rose-600 px-4 py-2 font-semibold text-white transition hover:bg-rose-700"
            >
              Remove
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}






