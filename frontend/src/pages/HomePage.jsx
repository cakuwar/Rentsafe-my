import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

// The landing screen: pitch, the two calls to action and "How it works".
export default function HomePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const steps = [1, 2, 3].map((n) => ({
    n,
    title: t(`landing.step${n}Title`),
    desc: t(`landing.step${n}Desc`),
  }));

  return (
    <main className="mx-auto max-w-[920px] animate-rs-fade px-5 pb-20 pt-14">
      <div className="mb-[26px] inline-flex items-center gap-[7px] rounded-full bg-teal/10 px-[13px] py-1.5 text-[12.5px] font-semibold text-teal-dark">
        <span className="h-[7px] w-[7px] rounded-full bg-teal" /> {t("landing.badge")}
      </div>
      <h1 className="mb-[18px] max-w-[680px] font-serif text-[46px] font-bold leading-[1.08] tracking-[-1px]">
        {t("landing.title")}
      </h1>
      <p className="mb-8 max-w-[580px] text-lg leading-[1.55] text-gray-600">{t("landing.lead")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/analyse")}
          className="cursor-pointer rounded-xl border-none bg-navy px-7 py-[15px] font-sans text-base font-semibold text-white shadow-cta hover:bg-navy-hover"
        >
          {t("landing.cta")}
        </button>
        <button
          type="button"
          onClick={() => navigate("/analyse", { state: { sample: true } })}
          className="cursor-pointer rounded-xl border-[1.5px] border-navy/20 bg-transparent px-[22px] py-3.5 text-[15px] font-semibold text-navy"
        >
          {t("landing.sample")}
        </button>
      </div>

      <section className="mt-16">
        <div className="mb-5 text-[12.5px] font-bold uppercase tracking-[1.5px] text-teal">{t("landing.howItWorks")}</div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
          {steps.map((step) => (
            <div key={step.n} className="rs-card p-[22px]">
              <div className="mb-3.5 flex h-[34px] w-[34px] items-center justify-center rounded-[9px] bg-navy/[.06] font-serif font-bold text-navy">
                {step.n}
              </div>
              <div className="mb-1.5 text-[15.5px] font-semibold">{step.title}</div>
              <div className="text-[13.5px] leading-normal text-gray-500">{step.desc}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-10 flex flex-wrap gap-[22px] text-[13px] text-gray-500">
        <div>{t("landing.noLogin")}</div>
        <div>{t("landing.builtFor")}</div>
      </div>
    </main>
  );
}
