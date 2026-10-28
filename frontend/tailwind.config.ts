import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0b0f14",
        surface: "#111822",
        "surface-2": "#161f2b",
        border: "#223042",
        muted: "#8aa0b6",
        fg: "#e6edf3",
        accent: "#38bdf8",
        "accent-dim": "#0ea5e9",
        danger: "#f87171",
        success: "#4ade80",
        warn: "#fbbf24",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
