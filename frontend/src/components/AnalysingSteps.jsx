import { useTranslation } from "react-i18next";

// The "Analysing…" screen. props: { checks: [{ key, label, state }] } where
// state is "done" | "active" | "waiting".
export default function AnalysingSteps({ checks }) {
  const { t } = useTranslation();

  return (
    <main className="mx-auto max-w-[560px] animate-rs-fade-fast px-5 py-20" aria-live="polite">
      <div className="mb-9 flex justify-center">
        <div className="h-[54px] w-[54px] animate-rs-spin rounded-full border-4 border-teal/[.18] border-t-teal" />
      </div>
      <h2 className="mb-1.5 text-center font-serif text-[25px] font-bold">{t("analysing.title")}</h2>
      <p className="mb-[34px] text-center text-[14.5px] text-gray-500">{t("analysing.subtitle")}</p>
      <div className="flex flex-col gap-3">
        {checks.map((check) => (
          <div
            key={check.key}
            className="flex items-center gap-[13px] rounded-xl border border-navy/[.07] bg-white px-4 py-3.5 shadow-card-sm"
          >
            <div className="flex h-6 w-6 flex-none items-center justify-center">
              {check.state === "done" && (
                <div className="flex h-[22px] w-[22px] items-center justify-center rounded-full bg-teal text-[13px] font-bold text-white">✓</div>
              )}
              {check.state === "active" && (
                <div className="h-[18px] w-[18px] animate-rs-spin-fast rounded-full border-[2.5px] border-teal/25 border-t-teal" />
              )}
              {check.state === "waiting" && <div className="h-4 w-4 rounded-full border-2 border-navy/[.15]" />}
            </div>
            <div className={`text-[14.5px] font-medium ${check.state === "waiting" ? "text-muted" : "text-navy"}`}>
              {check.label}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
