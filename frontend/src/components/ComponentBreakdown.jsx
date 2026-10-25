import { useTranslation } from "react-i18next";
import { pick } from "../lib/present.js";

// Each signal's ceiling (backend SCORE_WEIGHTS) and the design's bar colour.
// The ceiling is shown even for a signal that wasn't scored, whose
// components entry then carries max 0.
const ROWS = [
  { key: "nlp", cap: 60, colour: "#D64545" },
  { key: "osint", cap: 25, colour: "#E07B39" },
  { key: "price", cap: 15, colour: "#E9A23B" },
];

/** Why a signal is excluded from the score, in the renter's language. */
function exclusionReason(t, key, result, language) {
  const evidence = result.evidence ?? {};
  if (key === "nlp") {
    return t(`result.nlpReason.${result.nlpStatus}`, { defaultValue: t("result.nlpReason.failed") });
  }
  if (key === "osint") {
    const osint = evidence.osint;
    if (!osint) return t("result.osintReason.failed");
    return osint.status === "no_identifier" ? t("result.osintReason.no_identifier") : t("result.osintReason.unavailable");
  }
  return evidence.price ? pick(evidence.price.message, language) : t("result.priceFailed");
}

// "How the score was built": one bar per signal, points out of its ceiling.
// A signal that couldn't be scored says so — it is excluded, not a 0.
export default function ComponentBreakdown({ result }) {
  const { t, i18n } = useTranslation();
  const components = result?.components;
  if (!components) return null;

  return (
    <section>
      <div className="rs-eyebrow mt-6">{t("result.breakdown")}</div>
      <div className="mt-3.5 flex flex-col gap-3.5">
        {ROWS.map(({ key, cap, colour }) => {
          const part = components[key] ?? {};
          const included = part.included === true;
          const max = included && part.max ? part.max : cap;
          const points = included ? Math.round(part.points ?? 0) : null;
          const width = included ? `${Math.min(100, Math.max(0, ((part.points ?? 0) / max) * 100))}%` : "0%";
          return (
            <div key={key} className="rounded-[14px] border border-navy/[.07] bg-white px-[18px] py-4 shadow-card-sm">
              <div className="mb-[9px] flex items-baseline justify-between gap-3">
                <div className="text-[15px] font-semibold">
                  {t(`result.${key}`)} <span className="text-[12.5px] font-normal text-muted">{t(`result.${key}Note`)}</span>
                </div>
                {included ? (
                  <div className="flex-none font-serif text-base font-bold">
                    {points}
                    <span className="font-sans text-[13px] font-normal text-muted">/{max}</span>
                  </div>
                ) : (
                  <div className="flex-none text-[13px] font-semibold text-muted">{t("result.notScored")}</div>
                )}
              </div>
              <div className="h-[9px] overflow-hidden rounded-full bg-navy/[.08]">
                <div className="h-full rounded-full" style={{ width, background: colour }} />
              </div>
              {!included && (
                <p className="mb-0 mt-2 text-[12.5px] leading-normal text-gray-500">
                  {exclusionReason(t, key, result, i18n.language)}
                </p>
              )}
            </div>
          );
        })}
      </div>
      {result.bandCap?.applied && <p className="mb-0 mt-2.5 text-[12.5px] text-gray-500">{t("result.capFootnote")}</p>}
    </section>
  );
}
