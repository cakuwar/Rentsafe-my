import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import PageHero from "../components/PageHero.jsx";

// DECISION (author, 2026-10-15) — the score ranges follow the backend's
// RISK_BANDS (LOW 0–24, MODERATE 25–49, HIGH 50–74, CRITICAL 75–100), not
// the design's 0–25 / 26–50 / 51–75 / 76–100. Band names are the result
// screen's (result.band.*), so the Guide and a result never disagree.
const BANDS = [
  { key: "LOW", min: 0, max: 24, colour: "#34C77B", text: "#1E9E5A", icon: "✓" },
  { key: "MODERATE", min: 25, max: 49, colour: "#E9A23B", text: "#B7791F", icon: "!" },
  { key: "HIGH", min: 50, max: 74, colour: "#E07B39", text: "#C2611F", icon: "⚠" },
  { key: "CRITICAL", min: 75, max: 100, colour: "#E5484D", text: "#D03A3F", icon: "✕" },
];
// One column per score: 25 / 25 / 25 / 26 of the 101 values 0–100.
const SPECTRUM_COLUMNS = "grid-cols-[25fr_25fr_25fr_26fr]";

// DECISION (author, 2026-10-30) — design revision 2 (light Guide). Where the
// design's copy describes something the system doesn't do, the Guide says
// what it does:
// - The OCR drops the WhatsApp header bar (bubbles.py HEADER_FRACTION,
//   ocr.py _strip_page_chrome), so the agent's name and number there are
//   never read: the tip says to type them into Agent details instead of
//   "must be visible — we check them".
// - Phone and name are recommended, not required (see ListingForm), so the
//   step 3 chips carry the form's own "(recommended)" / "(optional)".
// - Timestamps only split one bubble from the next; nothing times the chat.
//   "So we can spot rushed timelines" became that.
// - Text inside photos is skipped, so "include any photos the agent sent"
//   became an Avoid; layer 2 needs 6 messages, which the design never said.
// - The rent comes only from the form (D8), so the tips say so.
// - "Other results you may see" explains UNKNOWN, the band cap and a partial
//   score, which the result screen can show and the design's Guide didn't.
const SHORTFORMS = [
  ["byr dlu", "bayar dulu"],
  ["tgk", "tengok"],
];
const AGENT_FIELDS = [
  ["📞", "phone", "recommended"],
  ["👤", "agentName", "recommended"],
  ["🪪", "ren", "optional"],
  ["🏢", "company", "optional"],
];
const LISTING_FIELDS = [
  ["💰", "rent"],
  ["📍", "area"],
  ["🏠", "propertyType"],
];
// The sample listing's chat, in its Manglish in both languages.
const CHAT = [
  { text: "Studio KLCC still available. RM750 only, fast deal ya", time: "10:42", marker: 2 },
  { text: "Boleh tgk unit dulu?", time: "10:44", mine: true },
  { text: "Tak boleh, owner oversea. Byr dlu deposit RM1,500 to hold", time: "10:45", marker: 3 },
];
const JUMPS = [
  ["rs-howto", "howTo", "①"],
  ["rs-shots", "shots", "②"],
  ["rs-score", "score", "③"],
];
const OTHER_RESULTS = [
  ["unknown", "–"],
  ["capped", "49"],
  ["partial", "<100"],
];

const BODY = "m-0 text-[15px] leading-[1.6] text-gray-600 [text-wrap:pretty]";
const CHIP = "rounded-[10px] border border-navy/10 bg-navy/[.04] px-[11px] py-[7px] text-[13px]";
// A form field as a chip: plain text, so on a phone it wraps like a sentence.
const FIELD_CHIP = `${CHIP} font-semibold text-gray-700`;

// In-page links scroll instead of changing the URL, so they add no history
// entries for the router to see.
function JumpLink({ to, className, children }) {
  function jump(event) {
    event.preventDefault();
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(to)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
  }
  return (
    <a href={`#${to}`} onClick={jump} className={className}>
      {children}
    </a>
  );
}

function Step({ n, title, last = false, children }) {
  const { t } = useTranslation();
  return (
    <li className="grid grid-cols-[46px_minmax(0,1fr)] gap-3.5 sm:grid-cols-[52px_minmax(0,1fr)] sm:gap-[18px]">
      <div className="flex flex-col items-center">
        <div className="flex h-[46px] w-[46px] flex-none items-center justify-center rounded-[14px] bg-gradient-to-br from-[#2fb3a3] to-teal-dark font-serif text-xl font-bold text-white shadow-tile">
          {n}
        </div>
        {!last && <div className="my-2 w-0.5 flex-1 rounded-sm bg-gradient-to-b from-teal/[.55] to-teal/[.08]" />}
      </div>
      <div className={`rs-panel min-w-0 px-[18px] py-5 sm:px-[22px] ${last ? "" : "mb-[18px]"}`}>
        <div className="rs-kicker mb-1.5">{t("guide.stepLabel", { n })}</div>
        <h3 className="mb-1.5 mt-0 font-serif text-[19px] font-bold text-navy">{title}</h3>
        {children}
      </div>
    </li>
  );
}

function Marker({ n, pinned = "" }) {
  const size = pinned ? `h-7 w-7 border-[3px] border-cream ${pinned}` : "h-[26px] w-[26px]";
  return (
    <span className={`flex flex-none items-center justify-center rounded-full bg-amber text-[13px] font-bold text-navy ${size}`}>
      {n}
    </span>
  );
}

// The design's annotated WhatsApp screenshot. Each marker hangs 14px past the
// frame's right edge, level with what it points at: -23px from the header
// (9px frame), -35px from a bubble row (plus 12px padding).
function PhoneMock() {
  const { t } = useTranslation();
  const pin = "absolute top-1/2 -translate-y-1/2";
  return (
    <div className="flex justify-center">
      <div role="img" aria-label={t("guide.shots.mockLabel")} className="relative w-full max-w-[290px]">
        <div className="rounded-[34px] border-[9px] border-navy bg-[#EFEAE2] shadow-phone">
          <div className="relative rounded-t-[25px] bg-[#1f4a45]">
            <div className="flex h-5 items-end justify-center">
              <div className="mb-1 h-1.5 w-[70px] rounded-md bg-black/[.35]" />
            </div>
            <div className="flex items-center gap-2.5 px-3 pb-3 pt-2">
              <div className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-full bg-[#c9d3d1] text-sm font-bold text-[#1f4a45]">
                R
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-white">Encik Razak</div>
                <div className="text-[11.5px] text-white/75">+60 12-345 6789</div>
              </div>
            </div>
            <Marker n={1} pinned={`${pin} -right-[23px]`} />
          </div>
          <div className="flex flex-col gap-2 px-3 pb-[18px] pt-3.5 text-[13px] leading-[1.4]">
            <div className="self-center rounded-md bg-white/75 px-[9px] py-[3px] text-[10.5px] font-semibold text-gray-500">
              {t("guide.shots.today")}
            </div>
            {CHAT.map((bubble) => (
              <div key={bubble.time} className={`relative flex ${bubble.mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[82%] rounded-[10px] px-2.5 py-[7px] text-gray-800 ${
                    bubble.mine ? "rounded-br-[2px] bg-[#D6F0E3]" : "rounded-bl-[2px] bg-white shadow-[0_1px_1px_rgba(0,0,0,.06)]"
                  }`}
                >
                  {bubble.text}
                  <div className="mt-0.5 text-right text-[10px] text-muted">{bubble.time}</div>
                </div>
                {bubble.marker && <Marker n={bubble.marker} pinned={`${pin} -right-[35px]`} />}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function TipList({ good, title, items }) {
  return (
    <div className="rs-panel relative overflow-hidden p-[22px]">
      <div className={`absolute inset-x-0 top-0 h-[3px] ${good ? "bg-[#34C77B]" : "bg-[#E5484D]"}`} />
      <h3 className={`mb-3 mt-0 text-base font-bold ${good ? "text-[#1E9E5A]" : "text-[#D03A3F]"}`}>{title}</h3>
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0 text-[14.5px] leading-normal text-gray-600">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function GuidePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const tips = (kind) => [1, 2, 3, 4].map((n) => t(`guide.shots.${kind}${n}`));

  return (
    <main className="mx-auto max-w-[960px] animate-rs-fade px-6 pb-[100px] pt-14">
      <PageHero badge={t("guide.badge")} title={t("guide.title")} lead={t("guide.lead")}>
        <div className="mt-6 flex flex-wrap justify-center gap-2.5">
          {JUMPS.map(([id, key, mark]) => (
            <JumpLink
              key={id}
              to={id}
              className="rounded-full border border-navy/[.12] bg-white px-4 py-[9px] text-[13.5px] font-semibold text-navy shadow-card-sm"
            >
              {mark} {t(`guide.jump.${key}`)}
            </JumpLink>
          ))}
        </div>
      </PageHero>

      {/* HOW TO USE */}
      <section id="rs-howto" className="rs-anchor">
        <div className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="rs-h2">{t("guide.howTo")}</h2>
          <div className="text-[13px] text-gray-500">{t("guide.duration")}</div>
        </div>
        <ol className="m-0 list-none p-0">
          <Step n={1} title={t("guide.step1Title")}>
            <p className={BODY}>
              {t("guide.step1Before")}
              <Link to="/analyse" className="font-bold text-teal underline underline-offset-[3px]">
                {t("guide.step1Link")}
              </Link>
              {t("guide.step1After")}
            </p>
          </Step>
          <Step n={2} title={t("guide.step2Title")}>
            <p className={BODY}>{t("guide.step2")}</p>
            <div className="mt-3.5 flex flex-wrap gap-2">
              {SHORTFORMS.map(([short, full]) => (
                <div key={short} className={`${CHIP} flex items-center gap-2`}>
                  <span className="font-mono text-[#B7791F]">{short}</span>
                  <span className="text-muted">→</span>
                  <span className="text-gray-700">{full}</span>
                </div>
              ))}
            </div>
            <JumpLink to="rs-shots" className="mt-3 inline-block text-[13.5px] font-semibold text-teal-dark">
              {t("guide.step2Shots")}
            </JumpLink>
          </Step>
          <Step n={3} title={t("guide.step3Title")}>
            <p className={BODY}>{t("guide.step3")}</p>
            <div className="mt-3.5 flex flex-wrap gap-2">
              {AGENT_FIELDS.map(([icon, field, note]) => (
                <div key={field} className={FIELD_CHIP}>
                  {icon} {t(`form.${field}`)} <span className="font-normal text-muted">{t(`form.${note}`)}</span>
                </div>
              ))}
            </div>
          </Step>
          <Step n={4} title={t("guide.step4Title")}>
            <p className={BODY}>{t("guide.step4")}</p>
            <div className="mt-3.5 flex flex-wrap gap-2">
              {LISTING_FIELDS.map(([icon, field]) => (
                <div key={field} className={FIELD_CHIP}>
                  {icon} {t(`form.${field}`)}
                </div>
              ))}
            </div>
          </Step>
          <Step n={5} title={t("guide.step5Title")} last>
            <p className={BODY}>{t("guide.step5")}</p>
            <button
              type="button"
              onClick={() => navigate("/analyse")}
              className="mt-4 cursor-pointer rounded-[10px] border-none bg-teal px-[18px] py-[11px] font-sans text-sm font-bold text-white shadow-btn-teal"
            >
              {t("guide.cta")}
            </button>
          </Step>
        </ol>
      </section>

      <div className="rs-divider" />

      {/* SCREENSHOT TIPS */}
      <section id="rs-shots" className="rs-anchor">
        <div className="mb-6">
          <h2 className="rs-h2 mb-1.5">{t("guide.shots.title")}</h2>
          <p className="m-0 max-w-[620px] text-[14.5px] leading-[1.55] text-gray-500">{t("guide.shots.lead")}</p>
        </div>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))] items-center gap-7">
          <PhoneMock />
          <div className="flex flex-col gap-3">
            <div className="rs-kicker">{t("guide.shots.legendTitle")}</div>
            {[1, 2, 3].map((n) => (
              <div key={n} className="rs-panel flex items-start gap-3 rounded-[14px] px-4 py-3.5">
                <Marker n={n} />
                <div>
                  <div className="text-[15px] font-bold text-navy">{t(`guide.shots.point${n}Title`)}</div>
                  <div className="mt-0.5 text-sm leading-normal text-gray-600">{t(`guide.shots.point${n}Text`)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-7 grid grid-cols-[repeat(auto-fit,minmax(min(100%,300px),1fr))] gap-4">
          <TipList good title={t("guide.shots.doTitle")} items={tips("do")} />
          <TipList title={t("guide.shots.avoidTitle")} items={tips("avoid")} />
        </div>
      </section>

      <div className="rs-divider" />

      {/* UNDERSTANDING THE SCORE */}
      <section id="rs-score" className="rs-anchor">
        <div className="mb-6">
          <h2 className="rs-h2 mb-1.5">{t("guide.scoreTitle")}</h2>
          <p className="m-0 text-[14.5px] text-gray-500">{t("guide.scoreLead")}</p>
        </div>

        <div className="rs-panel mb-[18px] px-[26px] pb-5 pt-[26px]">
          <div className={`grid h-3.5 gap-1 ${SPECTRUM_COLUMNS}`}>
            {BANDS.map((band, i) => (
              <div
                key={band.key}
                className={i === 0 ? "rounded-l-full rounded-r" : i === BANDS.length - 1 ? "rounded-l rounded-r-full" : "rounded"}
                style={{ background: band.colour, boxShadow: `0 0 16px ${band.colour}59` }}
              />
            ))}
          </div>
          <div className={`mt-2.5 grid gap-1 ${SPECTRUM_COLUMNS}`}>
            {BANDS.map((band) => (
              <div key={band.key} className="min-w-0">
                <div className="text-xs font-bold capitalize" style={{ color: band.text }}>
                  {t(`result.bandWord.${band.key}`)}
                </div>
                <div className="text-[11.5px] tabular-nums text-muted">
                  {band.min}–{band.max}
                </div>
              </div>
            ))}
          </div>
          <p className="mb-0 mt-4 text-[13px] leading-normal text-gray-500">{t("guide.boundary")}</p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {BANDS.map((band) => (
            <div key={band.key} className="rs-panel relative overflow-hidden p-[22px]">
              <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: band.colour }} />
              <div
                className="pointer-events-none absolute -right-[60px] -top-[60px] h-40 w-40 rounded-full"
                style={{ background: `radial-gradient(circle, ${band.colour}2e, transparent 70%)` }}
              />
              <div className="relative mb-2.5 flex items-baseline justify-between gap-2.5">
                <div className="font-serif text-[28px] font-bold tracking-[-.5px] text-navy">
                  {band.min} – {band.max}
                </div>
                <div className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: band.colour, boxShadow: `0 0 12px ${band.colour}` }} />
              </div>
              <p className="relative m-0 text-[15px] leading-[1.6] text-gray-600 [text-wrap:pretty]">
                <span className="font-bold" style={{ color: band.text }}>
                  {t(`result.band.${band.key}`)}:
                </span>{" "}
                {t(`guide.bands.${band.key}`)}
              </p>
              <div
                className="relative mt-3.5 inline-flex items-center gap-1.5 rounded-full border border-navy/10 bg-navy/[.03] px-[11px] py-1.5 text-[12.5px] font-bold"
                style={{ color: band.text }}
              >
                {band.icon} {t(`guide.actions.${band.key}`)}
              </div>
            </div>
          ))}
        </div>

        <div className="rs-panel mt-4 p-[22px]">
          <h3 className="mb-3.5 mt-0 font-serif text-[19px] font-bold text-navy">{t("guide.other.title")}</h3>
          <div className="flex flex-col gap-3.5">
            {OTHER_RESULTS.map(([key, mark]) => (
              <div key={key} className="flex gap-3">
                <div className="flex h-[30px] min-w-[30px] flex-none items-center justify-center rounded-lg bg-navy/[.06] px-1.5 font-serif text-sm font-bold text-navy">
                  {mark}
                </div>
                <div>
                  <div className="text-[15px] font-bold text-navy">{t(`guide.other.${key}Title`)}</div>
                  <div className="mt-0.5 text-sm leading-normal text-gray-600">{t(`guide.other.${key}Text`)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* NSRC */}
        <div className="mt-7 flex flex-wrap items-center justify-between gap-5 rounded-[20px] bg-navy px-7 py-[26px] shadow-explain">
          <div>
            <div className="mb-1 font-serif text-xl font-bold text-white">{t("guide.nsrcTitle")}</div>
            <div className="text-[14.5px] text-white/70">{t("guide.nsrcText")}</div>
          </div>
          <a
            href="tel:997"
            aria-label={t("guide.nsrcCall")}
            className="flex items-center gap-3 rounded-[14px] border border-amber/[.45] bg-white/[.08] px-[18px] py-2.5"
          >
            <span className="text-[11.5px] font-bold tracking-[1px] text-white/[.55]">NSRC</span>
            <span className="font-serif text-[30px] font-bold tracking-[1px] text-white">997</span>
          </a>
        </div>
      </section>
    </main>
  );
}
