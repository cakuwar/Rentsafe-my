import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import PageHero from "../components/PageHero.jsx";

// Each check's ceiling (backend SCORE_WEIGHTS) and the design's colour. The
// names are the result screen's breakdown labels (result.nlp, ...).
const CHECKS = [
  { key: "nlp", cap: 60, colour: "#1B2A4A", text: "#1B2A4A" },
  { key: "osint", cap: 25, colour: "#2A9D8F", text: "#1f7a6f" },
  { key: "price", cap: 15, colour: "#E9A23B", text: "#B7791F" },
];

// DECISION (author, 2026-10-30) — design revision 2. The About copy follows
// the system where the design's was looser:
// - Text analysis describes both layers (rules say why, the model gives the
//   points), as docs/NLP_LAYERS.md does; online reports also search the REN,
//   and weigh news > forum > social (osint.service.js TIER_POINTS).
// - "What keeps the score honest" is added: an excluded check isn't a zero,
//   the band cap, and the narrative can't change the score — three things a
//   result can show that the design never explained.
// - Privacy says what leaves the system: OCR (Tesseract) and the model run in
//   the NLP service; the narrative and OSINT judge never see the chat; only
//   the agent's identifiers go to the web search. The design's "what you
//   paste is used only to run the check" is not repeated: listings.repo.js
//   is meant to store results once it is written.
// - The Final Year Project note from the old About copy is kept.
export default function AboutPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <main className="mx-auto max-w-[960px] animate-rs-fade px-6 pb-[100px] pt-14">
      <PageHero badge={t("about.badge")} title={t("about.title")} lead={t("about.lead")} />

      {/* WHY */}
      <section className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))] items-start gap-7">
        <div>
          <div className="rs-kicker mb-2.5">{t("about.whyKicker")}</div>
          <h2 className="rs-h2 mb-3.5">{t("about.whyTitle")}</h2>
          <p className="m-0 text-[15.5px] leading-[1.65] text-gray-600 [text-wrap:pretty]">{t("about.whyText")}</p>
        </div>
        <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
          {[1, 2, 3].map((n) => {
            const pressure = n === 3;
            return (
              <li
                key={n}
                className={`rs-panel flex items-center gap-3.5 rounded-[14px] px-4 py-3.5 ${pressure ? "border-danger/20" : ""}`}
              >
                <div
                  className={`flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[10px] font-serif font-bold ${
                    pressure ? "bg-danger/10 text-[#D03A3F]" : "bg-navy/[.06] text-navy"
                  }`}
                >
                  {n}
                </div>
                <div>
                  <div className={`text-[15px] font-bold ${pressure ? "text-[#D03A3F]" : "text-navy"}`}>{t(`about.step${n}Title`)}</div>
                  <div className="text-sm text-gray-500">{t(`about.step${n}Text`)}</div>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <div className="rs-divider" />

      {/* HOW IT WORKS */}
      <section>
        <div className="mb-6">
          <div className="rs-kicker mb-2.5">{t("about.howKicker")}</div>
          <h2 className="rs-h2 mb-1.5">{t("about.howTitle")}</h2>
          <p className="m-0 text-[14.5px] text-gray-500">{t("about.howLead")}</p>
        </div>
        <div className="rs-panel mb-4 px-6 py-[22px]">
          <div className="grid h-4 grid-cols-[60fr_25fr_15fr] gap-1">
            {CHECKS.map((check, i) => (
              <div
                key={check.key}
                className={i === 0 ? "rounded-l-full rounded-r" : i === CHECKS.length - 1 ? "rounded-l rounded-r-full" : "rounded"}
                style={{ background: check.colour }}
              />
            ))}
          </div>
          <div className="mt-2.5 grid grid-cols-[60fr_25fr_15fr] gap-1 text-[12.5px] font-bold">
            {CHECKS.map((check) => (
              <div key={check.key} className="whitespace-nowrap" style={{ color: check.text }}>
                {check.cap}
                <span className="hidden sm:inline"> {t("about.pts")}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,250px),1fr))] gap-4">
          {CHECKS.map((check) => (
            <div key={check.key} className="rs-panel relative overflow-hidden p-[22px]">
              <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: check.colour }} />
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <h3 className="m-0 font-serif text-[19px] font-bold text-navy">{t(`result.${check.key}`)}</h3>
                <div className="flex-none text-[13px] font-bold text-gray-500">/{check.cap}</div>
              </div>
              <p className="m-0 text-[14.5px] leading-[1.6] text-gray-600 [text-wrap:pretty]">{t(`about.${check.key}Text`)}</p>
            </div>
          ))}
        </div>

        <div className="rs-panel mt-4 p-[22px]">
          <h3 className="mb-3.5 mt-0 font-serif text-[19px] font-bold text-navy">{t("about.honestTitle")}</h3>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-x-6 gap-y-4">
            {[1, 2, 3].map((n) => (
              <div key={n}>
                <div className="text-[15px] font-bold text-navy">{t(`about.honest${n}Title`)}</div>
                <div className="mt-1 text-sm leading-normal text-gray-600">{t(`about.honest${n}Text`)}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="rs-divider" />

      {/* PRIVACY + LIMITS */}
      <section className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))] gap-4">
        <div className="rs-panel p-6">
          <h3 className="mb-3.5 mt-0 font-serif text-[21px] font-bold text-navy">{t("about.privacyTitle")}</h3>
          <ul className="m-0 flex list-none flex-col gap-2.5 p-0 text-[14.5px] leading-normal text-gray-600">
            {[1, 2, 3].map((n) => (
              <li key={n} className="flex gap-2.5">
                <span className="flex-none font-bold text-teal">✓</span>
                {t(`about.privacy${n}`)}
              </li>
            ))}
          </ul>
        </div>
        <div className="rs-panel border-amber/[.35] p-6">
          <h3 className="mb-3.5 mt-0 font-serif text-[21px] font-bold text-navy">{t("about.limitsTitle")}</h3>
          <p className="m-0 text-[14.5px] leading-[1.6] text-gray-600 [text-wrap:pretty]">
            {t("about.limitsBefore")}
            <a
              href="https://lppeh.gov.my"
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-navy underline underline-offset-2"
            >
              {t("about.limitsLink")}
            </a>
            {t("about.limitsAfter")}
          </p>
          <p className="mb-0 mt-3 text-[13px] leading-normal text-gray-500">{t("about.fyp")}</p>
        </div>
      </section>

      {/* CTA */}
      <div className="mt-7 flex flex-wrap items-center justify-between gap-5 rounded-[20px] bg-navy p-7 shadow-explain">
        <div>
          <div className="mb-1 font-serif text-[22px] font-bold text-white">{t("about.ctaTitle")}</div>
          <div className="text-[14.5px] text-white/75">{t("about.ctaText")}</div>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <button
            type="button"
            onClick={() => navigate("/guide")}
            className="cursor-pointer rounded-[11px] border-[1.5px] border-white/30 bg-transparent px-[18px] py-3 font-sans text-[14.5px] font-semibold text-white"
          >
            {t("about.ctaGuide")}
          </button>
          <button
            type="button"
            onClick={() => navigate("/analyse")}
            className="cursor-pointer rounded-[11px] border-none bg-teal px-5 py-3 font-sans text-[14.5px] font-bold text-white shadow-btn-teal"
          >
            {t("about.ctaCheck")}
          </button>
        </div>
      </div>
    </main>
  );
}
