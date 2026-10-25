import { useTranslation } from "react-i18next";
import { BAND_COLOUR } from "../lib/present.js";

const CIRCUMFERENCE = 502.65; // 2π × 80

// props: { score, band }. The design's 0-100 ring, coloured by band. A null
// score (band UNKNOWN) draws no arc and shows a dash, never 0: zero would
// read as "safe", which is the opposite of "couldn't judge".
export default function RiskGauge({ score, band }) {
  const { t } = useTranslation();
  const hasScore = typeof score === "number";
  const pct = hasScore ? Math.min(100, Math.max(0, score)) : 0;

  return (
    <div
      className="relative h-[172px] w-[172px] flex-none"
      role="img"
      aria-label={hasScore ? `${score} / 100 — ${t(`result.band.${band}`)}` : t("result.band.UNKNOWN")}
    >
      <svg width="172" height="172" viewBox="0 0 172 172" className="-rotate-90">
        <circle cx="86" cy="86" r="80" fill="none" stroke="rgba(255,255,255,.12)" strokeWidth="12" />
        {pct > 0 && (
          <circle
            cx="86"
            cy="86"
            r="80"
            fill="none"
            stroke={BAND_COLOUR[band]}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - pct / 100)}
            className="animate-rs-draw"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-serif text-[50px] font-bold leading-none">{hasScore ? score : "–"}</div>
        <div className="mt-0.5 text-xs tracking-[1px] text-white/60">{t("result.outOf")}</div>
      </div>
    </div>
  );
}
