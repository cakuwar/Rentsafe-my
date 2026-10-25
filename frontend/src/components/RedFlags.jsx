import { useTranslation } from "react-i18next";
import { legitSignalText } from "../i18n/backendText.js";

// DECISION (author, 2026-10-15) — chips come only from layer 1's evidence
// (evidence.details, most severe first). The design's "No REN number" chip is
// not shown: the backend never scores a missing REN.
// Legitimacy signals are listed as things to verify, never as reassurance,
// and only when no red flag fired (layer 1 withholds them otherwise).
export default function RedFlags({ evidence }) {
  const { t, i18n } = useTranslation();
  const ms = i18n.language === "ms";
  const details = evidence?.details ?? [];
  const patterns = evidence?.patterns ?? [];
  const legit = evidence?.legitSignals ?? [];

  return (
    <section className="rs-card mt-6 p-5">
      <div className="mb-[13px] flex items-center gap-2 text-[15.5px] font-bold">
        {details.length ? t("result.flagsTitle") : t("result.flagsTitleNone")}
      </div>
      {details.length > 0 ? (
        <>
          <div className="flex flex-wrap gap-[9px]">
            {details.map((flag) => (
              <div
                key={flag.id}
                title={ms ? flag.advice_ms : flag.advice_en}
                className="rounded-full border border-danger/20 bg-danger/[.08] px-[13px] py-[7px] text-[13px] font-semibold text-danger-text"
              >
                {ms ? flag.label_ms : flag.label_en}
              </div>
            ))}
          </div>
          {patterns.length > 0 && (
            <p className="mb-0 mt-3 text-[13px] text-gray-500">
              {t("result.tactics")} {patterns.map((p) => (ms ? p.label_ms : p.label_en)).join(" · ")}
            </p>
          )}
        </>
      ) : (
        <p className="m-0 text-[13.5px] text-gray-600">{t("result.flagsNone")}</p>
      )}
      {details.length === 0 && legit.length > 0 && (
        <div className="mt-3.5">
          <div className="mb-1.5 text-[13px] font-bold">{t("result.verifyTitle")}</div>
          <ul className="m-0 list-disc pl-5 text-[13px] leading-normal text-gray-600">
            {legit.map((signal) => {
              const { label, note } = legitSignalText(signal, i18n.language);
              return (
                <li key={signal.id}>
                  <b className="font-semibold text-navy">{label}</b> — {note}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
