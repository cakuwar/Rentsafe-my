import { useTranslation } from "react-i18next";
import { formatRM, pick, stratumLabel } from "../lib/present.js";

// "Price check", from evidence.price. The comparison is with the stratum's
// median (the design said "avg"; the backend uses the median). The API's
// message is shown as-is: it carries the sample size and the data note.
export default function PriceCard({ price }) {
  const { t, i18n } = useTranslation();
  if (!price) {
    return (
      <section className="rs-card p-5">
        <div className="mb-[15px] text-[15.5px] font-bold">{t("result.priceTitle")}</div>
        <p className="m-0 text-[13.5px] text-gray-600">{t("result.priceFailed")}</p>
      </section>
    );
  }

  const listed = price.listedPrice;
  const median = price.baseline?.median;
  // D10: under the minimum-rent floor — scored without any baseline, so there
  // is no median to draw and no percentage to quote.
  const floored = price.status === "ok" && price.guard === "below_floor";
  const flagged = price.status === "ok" && price.points > 0;
  const compared = (price.status === "ok" || price.status === "thin_baseline") && listed != null && median != null;
  const message = pick(price.message, i18n.language);

  return (
    <section className="rs-card p-5">
      <div className="mb-[15px] text-[15.5px] font-bold">{t("result.priceTitle")}</div>
      {compared && (
        <>
          <div className="mb-3.5 flex items-end justify-between gap-3">
            <div>
              <div className="text-xs text-muted">{t("result.listedRent")}</div>
              <div className={`font-serif text-[26px] font-bold ${flagged ? "text-danger" : ""}`}>RM{formatRM(listed)}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted">{t("result.median", { stratum: stratumLabel(t, price.stratum) })}</div>
              <div className="font-serif text-[26px] font-bold">RM{formatRM(median)}</div>
            </div>
          </div>
          <div className="relative mb-2.5 h-[9px] overflow-hidden rounded-full bg-navy/[.08]">
            <div
              className="h-full rounded-full"
              style={{ width: `${Math.min(100, (listed / median) * 100)}%`, background: flagged ? "#D64545" : "#2A9D8F" }}
            />
          </div>
        </>
      )}
      {floored ? (
        <>
          <div className="mb-3.5">
            <div className="text-xs text-muted">{t("result.listedRent")}</div>
            <div className="font-serif text-[26px] font-bold text-danger">RM{formatRM(listed)}</div>
          </div>
          <div className="rounded-[10px] bg-amber/[.12] px-3 py-2.5 text-[13px] font-semibold text-amber-text">{message}</div>
        </>
      ) : flagged ? (
        <>
          <div className="rounded-[10px] bg-amber/[.12] px-3 py-2.5 text-[13px] font-semibold text-amber-text">
            {t("result.belowMarket", { pct: Math.round(price.deviation * 100) })}
          </div>
          {message && <p className="mb-0 mt-2.5 text-xs leading-normal text-muted">{message}</p>}
        </>
      ) : (
        message && <div className="rounded-[10px] bg-navy/[.04] px-3 py-2.5 text-[13px] leading-normal text-gray-600">{message}</div>
      )}
    </section>
  );
}
