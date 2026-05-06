import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      screens: {
        // sidebar visible when it takes ≤30% of viewport (256px / 0.30 ≈ 853px)
        wide: "860px",
      },
      colors: {
        // primary surfaces
        canvas: "#212121",        // main chat area
        sidebar: "#171717",       // sidebar background
        elevated: "#2f2f2f",      // cards, user bubbles
        border: "#3f3f3f",        // dividers
        hover: "#373737",         // hover state
        input: "#404040",         // input background
        // text
        primary: "#ececec",       // main text
        secondary: "#9ca3af",     // subtext
        muted: "#6b7280",         // placeholder, hints
        // accent
        accent: "#10a37f",        // ChatGPT green
        "accent-hover": "#0d8a6b",
        // status
        "tool-bg": "#2a2a2a",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          '"Cascadia Code"',
          '"Fira Code"',
          "Consolas",
          "monospace",
        ],
      },
      keyframes: {
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        fadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        blink: "blink 1s step-end infinite",
        "fade-in": "fadeIn 0.15s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
