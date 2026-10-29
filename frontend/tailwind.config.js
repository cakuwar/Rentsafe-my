/** @type {import('tailwindcss').Config} */
// Tokens from the Claude Design file "RentSafe MY.dc.html": navy / teal / cream,
// the four risk colours, Source Serif 4 + Source Sans 3, and its animations.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#1B2A4A", hover: "#243a63", deep: "#23365c" },
        teal: { DEFAULT: "#2A9D8F", dark: "#1f7a6f" },
        cream: "#F7F5F0",
        muted: "#9aa0ac",
        // Bands as the API names them (scoring.service.js RISK_BANDS).
        risk: {
          low: "#34C77B",
          moderate: "#E9A23B",
          high: "#E07B39",
          critical: "#D64545",
          unknown: "#9aa0ac",
        },
        danger: { DEFAULT: "#D64545", text: "#b23a3a" },
        amber: { DEFAULT: "#E9A23B", text: "#9c6a16" },
      },
      fontFamily: {
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"Source Sans 3"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 2px 10px rgba(27,42,74,.04)",
        "card-sm": "0 2px 8px rgba(27,42,74,.04)",
        cta: "0 6px 18px rgba(27,42,74,.22)",
        "cta-teal": "0 6px 18px rgba(42,157,143,.3)",
        "btn-teal": "0 8px 20px rgba(42,157,143,.35)",
        hero: "0 14px 40px rgba(27,42,74,.28)",
        explain: "0 10px 30px rgba(27,42,74,.22)",
        // Guide and About cards, step tiles and the phone mock.
        panel: "0 2px 12px rgba(27,42,74,.05)",
        tile: "0 8px 22px rgba(42,157,143,.35), inset 0 1px 0 rgba(255,255,255,.25)",
        phone: "0 20px 44px rgba(27,42,74,.22)",
      },
      keyframes: {
        rsSpin: { to: { transform: "rotate(360deg)" } },
        rsFade: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // Only a start frame: the ring animates to its own stroke-dashoffset,
        // which RiskGauge sets from the score.
        rsDraw: { from: { strokeDashoffset: "502.65" } },
      },
      animation: {
        "rs-fade": "rsFade .4s ease",
        "rs-fade-fast": "rsFade .3s ease",
        "rs-spin": "rsSpin .9s linear infinite",
        "rs-spin-fast": "rsSpin .8s linear infinite",
        "rs-draw": "rsDraw 1.1s cubic-bezier(.4,0,.2,1) both",
      },
    },
  },
  plugins: [],
};
