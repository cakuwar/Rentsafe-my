import { useTranslation } from "react-i18next";

export default function Footer({ dark = false }) {
  const { t } = useTranslation();
  return (
    <footer
      className={`border-t px-5 py-[22px] text-center text-xs ${
        dark ? "border-white/[.07] text-white/40" : "border-navy/[.07] text-muted"
      }`}
    >
      {t("footer")}
    </footer>
  );
}
