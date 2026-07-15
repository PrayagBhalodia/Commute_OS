import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Inter", "ui-sans-serif", "system-ui"],
      },
      colors: {
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        card: "hsl(var(--card))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        accent: "hsl(var(--accent))",
        // Periwinkle-violet brand scale for the white + purple theme.
        brand: {
          50: "#f4f3ff",
          100: "#ebe8ff",
          200: "#dad5ff",
          300: "#beb2ff",
          400: "#9e86fc",
          500: "#7f5af6",
          600: "#6d47ef",
          700: "#5b34d6",
          800: "#4a2bab",
          900: "#3c2586",
        },
      },
      boxShadow: {
        soft: "0 16px 50px rgba(76, 40, 130, 0.10)",
        brand: "0 10px 30px rgba(109, 71, 239, 0.30)",
      },
    },
  },
  plugins: [],
};

export default config;
