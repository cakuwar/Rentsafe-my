import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageToggle from "./LanguageToggle.jsx";
import Logo from "./Logo.jsx";

// The light top bar (every page but the Guide, which has its own dark bar).
// Text links appear from 720px; the Guide button is always shown, as in the
// design, which colours the Guide link teal.
export default function Navbar() {
  const { t } = useTranslation();

  return (
    <header className="sticky top-0 z-20 border-b border-navy/[.08] bg-cream/90 backdrop-blur-[8px]">
      <div className="mx-auto flex max-w-[920px] items-center justify-between px-5 py-3.5">
        <Link to="/" aria-label={t("appName")}>
          <Logo />
        </Link>
        <div className="flex items-center gap-[22px]">
          <nav className="hidden gap-[22px] text-sm font-semibold min-[720px]:flex">
            <Link to="/" className="text-navy">{t("nav.home")}</Link>
            <Link to="/analyse" className="text-navy">{t("nav.analyse")}</Link>
            <Link to="/guide" className="text-teal">{t("nav.guide")}</Link>
            <Link to="/about" className="text-navy">{t("nav.about")}</Link>
          </nav>
          <LanguageToggle />
          <Link
            to="/guide"
            className="rounded-[9px] border border-navy/[.12] bg-navy/[.06] px-[13px] py-[7px] text-[13px] font-semibold text-navy"
          >
            {t("nav.guide")}
          </Link>
        </div>
      </div>
    </header>
  );
}
