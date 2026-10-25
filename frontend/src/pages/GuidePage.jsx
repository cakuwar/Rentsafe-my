import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageToggle from "../components/LanguageToggle.jsx";
import Logo from "../components/Logo.jsx";
import Footer from "../components/Footer.jsx";

const BACKGROUND =
  "radial-gradient(120% 90% at 90% 110%, rgba(124,77,255,.28), transparent 55%), " +
  "linear-gradient(160deg,#141d33 0%,#0c1220 60%,#080c16 100%)";

// DECISION (author, 2026-10-15) — the score ranges follow the backend's
// RISK_BANDS (LOW 0–24, MODERATE 25–49, HIGH 50–74, CRITICAL 75–100), not
// the design's 0–25 / 26–50 / 51–75 / 76–100.
const BANDS = [
  { key: "low", colour: "#34C77B" },
  { key: "moderate", colour: "#E9A23B" },
  { key: "high", colour: "#E07B39" },
  { key: "critical", colour: "#E5484D" },
];

export default function GuidePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen flex-col font-sans" style={{ background: BACKGROUND }}>
      <header className="sticky top-0 z-20 border-b border-white/[.07] bg-[rgba(12,18,32,.6)] backdrop-blur-[10px]">
        <div className="mx-auto flex max-w-[1080px] items-center justify-between gap-5 px-6 py-[15px]">
          <Link to="/" aria-label={t("appName")}>
            <Logo dark />
          </Link>
          <nav className="hidden gap-[26px] text-sm font-semibold min-[720px]:flex">
            <Link to="/" className="text-white/65">{t("nav.home")}</Link>
            <Link to="/analyse" className="text-white/65">{t("nav.analyse")}</Link>
            <span className="text-white" aria-current="page">{t("nav.guide")}</span>
            <Link to="/about" className="text-white/65">{t("nav.about")}</Link>
          </nav>
          <div className="flex items-center gap-3.5">
            <LanguageToggle dark />
            <button
              type="button"
              onClick={() => navigate("/analyse")}
              className="cursor-pointer whitespace-nowrap rounded-[10px] border-none bg-teal px-4 py-[9px] text-[13.5px] font-semibold text-white shadow-btn-teal"
            >
              {t("nav.checkListing")}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[840px] flex-1 px-6 pb-[90px] pt-12">
        <div className="rounded-3xl border border-white/[.09] bg-guide-card p-7 shadow-guide sm:p-12">
          <h1 className="mb-8 font-serif text-[42px] font-bold tracking-[-1px] text-white">{t("guide.title")}</h1>

          <h2 className="mb-[18px] font-serif text-[22px] font-bold text-white">{t("guide.howTo")}</h2>
          <ol className="m-0 list-decimal pl-[22px] text-[15.5px] leading-[1.7] text-white/[.72]">
            <li className="mb-3">
              {t("guide.step1Before")}
              <Link to="/analyse" className="font-semibold text-teal underline underline-offset-2">
                {t("guide.step1Link")}
              </Link>
              {t("guide.step1After")}
            </li>
            <li className="mb-3">{t("guide.step2")}</li>
            <li className="mb-3">{t("guide.step3")}</li>
            <li className="mb-3">{t("guide.step4")}</li>
            <li>{t("guide.step5")}</li>
          </ol>

          <div className="my-[34px] h-px bg-white/10" />

          <h2 className="mb-[18px] font-serif text-[22px] font-bold text-white">{t("guide.scoreTitle")}</h2>
          <ul className="m-0 list-none pl-0 text-[15.5px] leading-[1.7] text-white/[.72]">
            {BANDS.map((band, i) => (
              <li key={band.key} className={`flex gap-2.5 ${i < BANDS.length - 1 ? "mb-3.5" : ""}`}>
                <span className="flex-none font-bold" style={{ color: band.colour }}>
                  {t(`guide.${band.key}Label`)}
                </span>
                <span>{t(`guide.${band.key}Text`)}</span>
              </li>
            ))}
          </ul>
        </div>
      </main>

      <Footer dark />
    </div>
  );
}
