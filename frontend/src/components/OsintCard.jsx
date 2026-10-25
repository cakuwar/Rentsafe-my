import { useTranslation } from "react-i18next";
import { pick } from "../lib/present.js";

const TIER_ICON = { news: "📰", forum: "💬", social: "📱" };
const MAX_ITEMS = 5;

// "What we found online", from evidence.osint. Only `evidence` items scored;
// impersonation notices are warnings; a name-only match is reported as
// possibly someone else. A status other than ok means the search didn't run.
export default function OsintCard({ osint }) {
  const { t, i18n } = useTranslation();
  const items = osint?.status === "ok" ? osint.evidence ?? [] : [];
  const nameOnly = (osint?.context ?? []).filter((item) => item.type === "name_only_match").length;

  let status = null;
  if (!osint) status = t("result.osintReason.failed");
  else if (osint.status === "no_identifier") status = t("result.osintReason.no_identifier");
  else if (osint.status !== "ok") status = t("result.osintReason.unavailable");
  else if (!items.length) status = t("result.onlineNothing");

  return (
    <section className="rs-card p-5">
      <div className="mb-[13px] text-[15.5px] font-bold">{t("result.onlineTitle")}</div>
      <div className="flex flex-col gap-[13px]">
        {items.slice(0, MAX_ITEMS).map((item) => (
          <div key={item.link} className="flex gap-[11px]">
            <div className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg bg-navy/[.06] text-sm">
              {TIER_ICON[item.tier] ?? "🔎"}
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold uppercase tracking-[.5px] text-teal">{t(`result.tier.${item.tier}`)}</div>
              <div className="mt-0.5 break-words text-[13.5px] leading-[1.45] text-gray-600">
                “{item.snippet || item.title}” —{" "}
                <a href={item.link} target="_blank" rel="noopener noreferrer" className="font-semibold text-navy underline underline-offset-2">
                  {item.domain}
                </a>
              </div>
            </div>
          </div>
        ))}
        {status && <p className="m-0 text-[13.5px] leading-[1.45] text-gray-600">{status}</p>}
        {(osint?.warnings ?? []).map((warning, i) => (
          <div key={i} className="rounded-[10px] bg-amber/[.12] px-3 py-2.5 text-[13px] font-semibold text-amber-text">
            {pick(warning, i18n.language)}
          </div>
        ))}
        {nameOnly > 0 && (
          <p className="m-0 text-[12.5px] leading-normal text-gray-500">{t("result.onlineNameOnly", { count: nameOnly })}</p>
        )}
        {osint?.status === "ok" && osint.failedQueries > 0 && (
          <p className="m-0 text-[12.5px] leading-normal text-gray-500">{t("result.onlinePartial")}</p>
        )}
      </div>
    </section>
  );
}
