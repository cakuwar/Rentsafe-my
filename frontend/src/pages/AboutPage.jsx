import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

// The design's About link had no screen behind it; this keeps the existing
// About copy in the light layout of the form page.
export default function AboutPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <main className="mx-auto max-w-[720px] animate-rs-fade px-5 pb-20 pt-10">
      <button type="button" onClick={() => navigate("/")} className="rs-back">
        {t("form.back")}
      </button>
      <h2 className="mb-3.5 font-serif text-[30px] font-bold tracking-[-.5px]">{t("about.title")}</h2>
      <p className="text-[15px] leading-relaxed text-gray-600">{t("about.body")}</p>
    </main>
  );
}
