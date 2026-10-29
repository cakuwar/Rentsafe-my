import { Link, NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageToggle from "./LanguageToggle.jsx";
import Logo from "./Logo.jsx";

const linkClass = ({ isActive }) => (isActive ? "text-teal" : "text-navy");

// The top bar. Text links appear from 720px and the current page is teal, as
// in the design. The button beside them is always shown: Guide, or — on the
// Guide itself, where that would go nowhere — Check Listing.
export default function Navbar() {
  const { t } = useTranslation();
  const onGuide = useLocation().pathname === "/guide";

  return (
    <header className="sticky top-0 z-20 border-b border-navy/[.08] bg-cream/90 backdrop-blur-[8px]">
      <div className="mx-auto flex max-w-[920px] items-center justify-between px-5 py-3.5">
        <Link to="/" aria-label={t("appName")}>
          <Logo />
        </Link>
        <div className="flex items-center gap-[22px]">
          <nav className="hidden gap-[22px] text-sm font-semibold min-[720px]:flex">
            <NavLink to="/" end className={linkClass}>{t("nav.home")}</NavLink>
            <NavLink to="/analyse" className={linkClass}>{t("nav.analyse")}</NavLink>
            <NavLink to="/guide" className={linkClass}>{t("nav.guide")}</NavLink>
            <NavLink to="/about" className={linkClass}>{t("nav.about")}</NavLink>
          </nav>
          <LanguageToggle />
          {onGuide ? (
            <Link
              to="/analyse"
              className="whitespace-nowrap rounded-[9px] bg-teal px-[13px] py-[7px] text-[13px] font-semibold text-white"
            >
              {t("nav.checkListing")}
            </Link>
          ) : (
            <Link
              to="/guide"
              className="rounded-[9px] border border-navy/[.12] bg-navy/[.06] px-[13px] py-[7px] text-[13px] font-semibold text-navy"
            >
              {t("nav.guide")}
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
