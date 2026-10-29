import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

// Below 720px the top bar hides its text links, so the footer carries them;
// otherwise About could only be reached from a wide screen.
export default function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="border-t border-navy/[.07] px-5 py-[22px] text-center text-xs text-muted">
      <nav className="mb-2.5 flex justify-center gap-5 text-[13px] font-semibold text-navy/70 min-[720px]:hidden">
        <Link to="/">{t("nav.home")}</Link>
        <Link to="/analyse">{t("nav.analyse")}</Link>
        <Link to="/guide">{t("nav.guide")}</Link>
        <Link to="/about">{t("nav.about")}</Link>
      </nav>
      {t("footer")}
    </footer>
  );
}
