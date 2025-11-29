"use client";

export default function LoadingScreen() {
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/20 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-6">
        {/* Animated plant emoji */}
        <div className="relative">
          <div className="text-8xl animate-bounce" style={{ animationDuration: "1.5s" }}>
            🌱
          </div>
          <div className="absolute -top-2 -right-2 text-4xl animate-pulse" style={{ animationDuration: "2s", animationDelay: "0.5s" }}>
            ✨
          </div>
        </div>
        
        {/* Loading text */}
        <div className="flex flex-col items-center gap-2">
          <p className="text-xl font-semibold text-emerald-900 animate-pulse">
            PlantPulse
          </p>
        </div>
      </div>
    </div>
  );
}

