export type PlantMetricRange = {
  min: number;
  max: number;
  unit: string;
};

export type PlantProfile = {
  id: string;
  label: string;
  description: string;
  keywords: string[];
  metrics: {
    temperatureC: PlantMetricRange;
    humidity: PlantMetricRange;
    soilMoisture: PlantMetricRange;
    lightLux: PlantMetricRange;
  };
};

export const PLANT_PROFILES: PlantProfile[] = [
  {
    id: "basil",
    label: "Sweet Basil",
    description: "Loves warm air, bright indirect light, and evenly moist soil.",
    keywords: ["basil"],
    metrics: {
      temperatureC: { min: 22, max: 28, unit: "°C" },
      humidity: { min: 55, max: 75, unit: "%" },
      soilMoisture: { min: 0.65, max: 0.85, unit: "%" },
      lightLux: { min: 100, max: 200, unit: "lux" }
    }
  },
  {
    id: "strawberry",
    label: "Strawberry",
    description: "Prefers cooler temperatures with consistent humidity.",
    keywords: ["strawberry"],
    metrics: {
      temperatureC: { min: 18, max: 24, unit: "°C" },
      humidity: { min: 55, max: 70, unit: "%" },
      soilMoisture: { min: 0.55, max: 0.7, unit: "%" },
      lightLux: { min: 100, max: 200, unit: "lux" }
    }
  },
  {
    id: "mint",
    label: "Garden Mint",
    description: "Thrives in high humidity and slightly cooler conditions.",
    keywords: ["mint"],
    metrics: {
      temperatureC: { min: 18, max: 24, unit: "°C" },
      humidity: { min: 60, max: 80, unit: "%" },
      soilMoisture: { min: 0.6, max: 0.8, unit: "%" },
      lightLux: { min: 100, max: 200, unit: "lux" }
    }
  },
  {
    id: "lettuce",
    label: "Leafy Lettuce",
    description: "Cool-loving crop; keep soil moist and light moderate.",
    keywords: ["lettuce", "leaf"],
    metrics: {
      temperatureC: { min: 16, max: 22, unit: "°C" },
      humidity: { min: 60, max: 75, unit: "%" },
      soilMoisture: { min: 0.65, max: 0.9, unit: "%" },
      lightLux: { min: 100, max: 200, unit: "lux" }
    }
  }
];

export function guessProfileId(plantId: string): string | undefined {
  const normalized = plantId.toLowerCase();
  for (const profile of PLANT_PROFILES) {
    if (profile.keywords.some((keyword) => normalized.includes(keyword))) {
      return profile.id;
    }
  }
  return undefined;
}

