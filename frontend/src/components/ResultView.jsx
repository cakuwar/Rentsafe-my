import { useTranslation } from "react-i18next";
import RiskGauge from "./RiskGauge.jsx";
import ComponentBreakdown from "./ComponentBreakdown.jsx";
import RedFlags from "./RedFlags.jsx";
import OsintCard from "./OsintCard.jsx";
import PriceCard from "./PriceCard.jsx";
import NarrativeCard from "./NarrativeCard.jsx";
import { BEDROOM_TYPES } from "../lib/listing.js";
import { BAND_COLOUR, BAND_ICON, BAND_TEXT, bandOf, findingsSentence, formatPhone, pick } from "../lib/present.js";

// DECISION (author, 2026-10-15) — the hero follows the API, not the design's
// fixed "76 / VERY HIGH RISK". Bands keep the design's names (LOW → Low,
// MODERATE → Medium, HIGH → High, CRITICAL → Very high); UNKNOWN is grey with
// no number. Alongside the number the hero shows what the API says must be
// shown with it: `message`, a `bandCap`, and a ceiling below 100 when a
// signal couldn't be scored.
// DECISION (author, 2026-10-16) — conflict 3: the paragraph under the
// headline is two lines, as in the design's paragraph: which checks flagged
// something (findingsSentence, from the result), then the band's Guide
// advice. The LOW and HIGH headlines were reworded so they can't contradict
// or repeat those lines (LOW said "No strong scam signals found.", which is
// wrong when only the price flagged).
function Hero({ result }) {
  const { t, i18n } = useTranslation();
  const band = bandOf(result);
  const message = pick(result.message, i18n.language);
  const findings = findingsSentence(t, result);
  const included = Object.values(result.components ?? {}).filter((part) => part?.included).length;
  const cap = result.bandCap?.applied ? result.bandCap : null;

  return (
    <div className="flex flex-wrap items-center gap-[34px] rounded-[22px] bg-navy p-[34px] text-white shadow-hero">
      <RiskGauge score={result.riskScore} band={band} />
      <div className="min-w-[230px] flex-1">
        <div
          className="mb-3.5 inline-flex items-center gap-[7px] rounded-full px-3.5 py-1.5 text-[12.5px] font-bold uppercase tracking-[.5px]"
          style={{ background: BAND_COLOUR[band], color: BAND_TEXT[band] }}
        >
          {BAND_ICON[band]} {t(`result.band.${band}`)}
        </div>
        <h2 className="mb-2 mt-0 font-serif text-[25px] font-bold leading-[1.2]">{t(`result.headline.${band}`)}</h2>
        {findings && <p className="m-0 text-[14.5px] leading-normal text-white/[.72]">{findings}</p>}
        {band !== "UNKNOWN" && (
          <p className="mb-0 mt-1 text-[14.5px] leading-normal text-white/[.72]">{t(`result.advice.${band}`)}</p>
        )}
        {band === "UNKNOWN" && !findings && !message && (
          <p className="m-0 text-[14.5px] leading-normal text-white/[.72]">{t("result.findings.nothingScored")}</p>
        )}
        {message && (
          <p className="mb-0 mt-3 rounded-[10px] bg-white/10 px-3 py-2.5 text-[13.5px] leading-normal text-white/90">{message}</p>
        )}
        {cap && (
          <p className="mb-0 mt-2 text-[13px] leading-normal text-white/60">
            {t("result.capped", { score: result.riskScore, uncapped: cap.uncappedScore })}
          </p>
        )}
        {band !== "UNKNOWN" && result.maxPossibleScore < 100 && (
          <p className="mb-0 mt-2 text-[13px] leading-normal text-white/60">
            {t("result.partial", { n: included, max: result.maxPossibleScore })}
          </p>
        )}
      </div>
    </div>
  );
}

// What was checked: the form's values, or what the backend parsed from the
// chat when a field was left blank (result.metadata).
function ListingSummary({ result, submitted }) {
  const { t } = useTranslation();
  const meta = result.metadata ?? {};
  const form = submitted ?? {};

  let areaType = [form.area, form.propertyType && t(`form.types.${form.propertyType}`)].filter(Boolean);
  if (BEDROOM_TYPES.includes(form.propertyType) && form.bedrooms) {
    areaType.push(t("result.bedroomsCount", { count: form.bedrooms === "1" ? 1 : 2, n: form.bedrooms }));
  }
  if (form.propertyType === "room" && form.roomType) areaType.push(t(`form.roomTypes.${form.roomType}`));
  areaType = areaType.join(" · ");

  const items = [
    ["agent", form.agentName?.trim() || meta.agentName],
    ["phone", formatPhone(form.phone?.trim() || meta.phone)],
    ["ren", form.ren?.trim() || meta.renNumber],
    ["company", form.company?.trim() || meta.company],
    ["areaType", areaType],
  ];

  return (
    <div className="rs-card mt-[18px] flex flex-wrap gap-6 px-5 py-[18px] text-[13.5px]">
      {items.map(([key, value]) => (
        <div key={key}>
          <span className="text-muted">{t(`result.${key}`)}</span>
          <br />
          {value ? <b>{value}</b> : <b className="font-semibold text-muted">{t("result.notProvided")}</b>}
        </div>
      ))}
    </div>
  );
}

function OcrText({ result }) {
  const { t } = useTranslation();
  if (!result.ocrText) return null;
  const pages = result.ocr?.pageCount;
  return (
    <details className="rs-card mt-4 p-5">
      <summary className="cursor-pointer text-[15.5px] font-bold">
        {t("result.ocrTitle")}
        {pages ? <span className="font-normal text-muted"> · {t("result.ocrPages", { count: pages })}</span> : null}
      </summary>
      <pre className="mb-0 mt-3 max-h-80 overflow-auto whitespace-pre-wrap font-sans text-[13.5px] leading-normal text-gray-600">
        {result.ocrText}
      </pre>
    </details>
  );
}

// props: { result, submitted, onAnalyseAnother, onDone } — the results screen.
export default function ResultView({ result, submitted, onAnalyseAnother, onDone }) {
  const { t } = useTranslation();
  if (!result) return null;

  return (
    <main className="mx-auto max-w-[920px] animate-rs-fade px-5 pb-[90px] pt-8">
      <button type="button" onClick={onAnalyseAnother} className="rs-back">
        {t("result.back")}
      </button>
      <Hero result={result} />
      <ListingSummary result={result} submitted={submitted} />
      <ComponentBreakdown result={result} />
      <RedFlags evidence={result.evidence} />
      <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
        <OsintCard osint={result.evidence?.osint} />
        <PriceCard price={result.evidence?.price} />
      </div>
      <NarrativeCard result={result} />
      <OcrText result={result} />
      <div className="mt-[22px] text-center">
        <button
          type="button"
          onClick={onDone}
          className="cursor-pointer rounded-[11px] border-[1.5px] border-navy/20 bg-transparent px-6 py-3 text-[14.5px] font-semibold text-navy"
        >
          {t("result.done")}
        </button>
      </div>
    </main>
  );
}
