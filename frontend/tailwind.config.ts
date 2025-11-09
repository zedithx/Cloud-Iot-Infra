import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        sprout: {
          50: "#f0fdf4",
          100: "#dcfce7",
          200: "#bbf7d0",
          300: "#86efac",
          400: "#4ade80",
          500: "#22c55e",
          600: "#16a34a",
          700: "#15803d"
        },
        bloom: {
          50: "#fffbeb",
          100: "#fef3c7",
          300: "#fcd34d",
          400: "#fbbf24",
          500: "#f59e0b"
        }
      },
      boxShadow: {
        card: "0 20px 45px -20px rgba(56, 189, 248, 0.35)",
        glow: "0 15px 40px -15px rgba(34, 197, 94, 0.45)"
      },
      backgroundImage: {
        "plant-gradient":
          "radial-gradient(circle at top left, rgba(250, 250, 230, 0.9), rgba(209, 250, 229, 0.85)), radial-gradient(circle at bottom right, rgba(187, 247, 208, 0.9), rgba(253, 244, 199, 0.85))"
      }
    }
  },
  plugins: []
};

export default config;

