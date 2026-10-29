import { useTranslation } from "react-i18next";

// Toggles i18n.language between "en" and "ms". Shows the current language, as
// the design's "🌐 EN" does; the tooltip names the one you'd switch to.
export default function LanguageToggle() {
  const { t, i18n } = useTranslation();
  const next = i18n.language === "ms" ? "en" : "ms";

  return (
    <button
      type="button"
      onClick={() => i18n.changeLanguage(next)}
      title={t("nav.switchLanguage")}
      aria-label={t("nav.switchLanguage")}
      className="flex cursor-pointer items-center gap-1.5 border-none bg-transparent p-0 text-[13px] font-semibold text-navy/70"
    >
      <span className="text-sm">🌐</span> {t("nav.language")}
    </button>
  );
}
