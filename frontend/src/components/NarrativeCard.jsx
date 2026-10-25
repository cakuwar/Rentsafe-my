import { useTranslation } from "react-i18next";
import { asSentence, bandOf, formatRM, pick, stratumLabel } from "../lib/present.js";

// DECISION (author, 2026-10-15) — "What this means". The backend's LLM
// narrative (llm.service.js generateNarrative) is still a TODO, so `narrative`
// is null today. Until it exists, the explanation is assembled here from the
// result itself: the band's advice, then up to three reasons — layer 1's red
// flags (label + its own advice), and a scored OSINT hit and price anomaly
// when there are any. Nothing is invented: every reason is a field in the
// response. When the backend sends a narrative, it is shown instead.
// The NSRC box appears only for HIGH and CRITICAL, as the design's copy says.
function buildReasons(t, result, ms) {
  const evidence = result.evidence ?? {};
  const extras = [];

  const osint = evidence.osint;
  if (osint?.status === "ok" && osint.points > 0) {
    extras.push({
      key: "osint",
      title: t("explain.osintTitle"),
      body: t("explain.osintBody", { domain: osint.evidence?.[0]?.domain ?? "" }),
    });
  }
  const price = evidence.price;
  if (price?.status === "ok" && price.points > 0) {
    extras.push({
      key: "price",
      title: t("explain.priceTitleReason"),
      // Under the minimum-rent floor (D10) there is no median: the API's own
      // message says why instead.
      body: price.guard === "below_floor"
        ? pick(price.message, ms ? "ms" : "en")
        : t("explain.priceBody", {
          price: formatRM(price.listedPrice),
          stratum: stratumLabel(t, price.stratum),
          pct: Math.round(price.deviation * 100),
        }),
    });
  }

  const flags = (evidence.details ?? []).map((flag) => ({
    key: flag.id,
    title: asSentence(ms ? flag.label_ms : flag.label_en),
    body: ms ? flag.advice_ms : flag.advice_en,
  }));
  return [...flags.slice(0, Math.max(0, 3 - extras.length)), ...extras].slice(0, 3);
}

export default function NarrativeCard({ result }) {
  const { t, i18n } = useTranslation();
  if (!result) return null;
  const ms = i18n.language === "ms";
  const band = bandOf(result);
  const narrative = pick(result.narrative, i18n.language);
  const reasons = narrative ? [] : buildReasons(t, result, ms);
  if (band === "UNKNOWN" && !narrative && !reasons.length) return null;

  return (
    <section className="mt-6 rounded-[18px] bg-gradient-to-b from-navy to-navy-deep p-[26px] text-white shadow-explain">
      <div className="mb-3.5 font-serif text-[21px] font-bold">{t("explain.title")}</div>
      {narrative ? (
        narrative
          .split(/\n{2,}/)
          .map((paragraph, i) => (
            <p key={i} className="mb-4 mt-0 text-[15px] leading-[1.6] text-white/85">{paragraph}</p>
          ))
      ) : (
        <>
          {band !== "UNKNOWN" && (
            <p className="mb-4 mt-0 text-[15px] leading-[1.6] text-white/85">
              {t("explain.carriesBefore")}
              <b className="text-white">{t("explain.carriesBand", { band: t(`result.bandWord.${band}`) })}</b>
              {t("explain.carriesAfter")}
              {t(`explain.advice.${band}`)}
              {reasons.length > 0 && ` ${t("explain.reasons", { count: reasons.length })}`}
            </p>
          )}
          {reasons.length > 0 && (
            <ol className="mb-[18px] mt-0 list-decimal pl-5 text-[14.5px] leading-[1.65] text-white/85">
              {reasons.map((reason, i) => (
                <li key={reason.key} className={i < reasons.length - 1 ? "mb-[7px]" : ""}>
                  <b className="text-white">{reason.title}</b> {reason.body}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
      {(band === "HIGH" || band === "CRITICAL") && (
        <div className="rounded-xl border border-amber/40 bg-amber/[.16] px-[17px] py-[15px]">
          <div className="mb-[5px] text-sm font-bold text-amber">{t("explain.reportTitle")}</div>
          <div className="text-sm leading-[1.55] text-white/90">
            {t("explain.reportBefore")}
            <b>{t("explain.reportNsrc")}</b>
            {t("explain.reportMiddle")}
            <b className="text-white">997</b>
            {t("explain.reportAfter")}
          </div>
        </div>
      )}
    </section>
  );
}
