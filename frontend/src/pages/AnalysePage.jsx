import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ListingForm from "../components/ListingForm.jsx";
import AnalysingSteps from "../components/AnalysingSteps.jsx";
import ResultView from "../components/ResultView.jsx";
import { revokePages } from "../components/ScreenshotUpload.jsx";
import { useAnalyze } from "../hooks/useAnalyze.js";
import { useAreas } from "../hooks/useAreas.js";
import { EMPTY_FORM, SAMPLE_FORM, fieldErrors, toRequest } from "../lib/listing.js";
import { backendMessage } from "../i18n/backendText.js";

// DECISION (author, 2026-10-15) — the design ticked its four checks off on an
// 850 ms timer. The backend is one request (NLP, OSINT and price in parallel,
// then the explanation), so per-check progress can't be known: the three
// parallel checks spin together, the explanation waits, and everything ticks
// when the response arrives. The screen stays up at least MIN_ANALYSING_MS so
// a fast response doesn't flash.
const MIN_ANALYSING_MS = 1200;
const TICK_PAUSE_MS = 450;
const MIN_TEXT_LENGTH = 20; // the API rejects shorter text with a 400

// The analyse screen: form -> analysing -> results, as in the design.
export default function AnalysePage() {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const analyze = useAnalyze();
  const areas = useAreas();

  const [form, setForm] = useState(() => (location.state?.sample ? { ...SAMPLE_FORM } : { ...EMPTY_FORM }));
  const [pages, setPages] = useState([]);
  const [phase, setPhase] = useState("form");
  const [finished, setFinished] = useState(false);
  const [submitted, setSubmitted] = useState(null);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);

  const request = useRef(0);
  const timers = useRef([]);
  const pagesRef = useRef(pages);
  pagesRef.current = pages;
  const seenKey = useRef(location.key);

  useEffect(
    () => () => {
      timers.current.forEach(clearTimeout);
      revokePages(pagesRef.current);
    },
    [],
  );

  // A nav link to /analyse while already here goes back to the form, keeping
  // what was typed (the design's goForm); a running request is abandoned.
  useEffect(() => {
    if (location.key === seenKey.current) return;
    seenKey.current = location.key;
    request.current += 1;
    timers.current.forEach(clearTimeout);
    if (location.state?.sample) setForm({ ...SAMPLE_FORM });
    setPhase("form");
  }, [location.key, location.state]);

  const show = (next) => {
    setPhase(next);
    window.scrollTo(0, 0);
  };

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => (current[key] ? { ...current, [key]: undefined } : current));
  }

  function setPageList(next) {
    setPages(next);
    setErrors((current) => (current.files || current.listingText ? { ...current, files: undefined, listingText: undefined } : current));
  }

  function fillSample() {
    revokePages(pages);
    setPages([]);
    setForm({ ...SAMPLE_FORM });
    setErrors({});
    setFormError(null);
  }

  async function submit() {
    if (!pages.length && form.listingText.trim().length < MIN_TEXT_LENGTH) {
      setErrors({ listingText: t("form.textTooShort") });
      setFormError(null);
      return;
    }

    const id = ++request.current;
    const details = toRequest(form);
    const started = Date.now();
    setErrors({});
    setFormError(null);
    setFinished(false);
    setSubmitted({ ...form, screenshots: pages.length > 0 });
    show("analysing");

    const data = pages.length
      ? await analyze.runScreenshot(pages.map((page) => page.file), details)
      : await analyze.runText(form.listingText.trim(), "auto", details);
    if (id !== request.current) return;

    if (!data) {
      show("form");
      return;
    }
    setFinished(true);
    const wait = Math.max(0, MIN_ANALYSING_MS - (Date.now() - started)) + TICK_PAUSE_MS;
    timers.current.push(
      setTimeout(() => {
        if (id === request.current) show("results");
      }, wait),
    );
  }

  // Validation errors go to their fields; anything else is one banner. The
  // backend's messages are English only; backendMessage has the known Malay.
  useEffect(() => {
    const failure = analyze.error;
    if (!failure) return;
    const language = i18n.language;
    const byField = Object.fromEntries(
      Object.entries(fieldErrors(failure.fields)).map(([field, message]) => [field, backendMessage(message, language)]),
    );
    setErrors(byField);
    if (failure.network) setFormError(t("form.errorNetwork"));
    else if (Object.keys(byField).length) setFormError(t("form.fixFields"));
    else setFormError(backendMessage(failure.message, language) ?? t("form.errorGeneric"));
  }, [analyze.error, t, i18n.language]);

  if (phase === "analysing") {
    const keys = [submitted?.screenshots ? "screenshots" : "text", "online", "price", "explanation"];
    const checks = keys.map((key, i) => ({
      key,
      label: t(`analysing.${key}`),
      state: finished ? "done" : i < 3 ? "active" : "waiting",
    }));
    return <AnalysingSteps checks={checks} />;
  }

  if (phase === "results" && analyze.result) {
    return (
      <ResultView
        result={analyze.result}
        submitted={submitted}
        onAnalyseAnother={() => show("form")}
        onDone={() => navigate("/")}
      />
    );
  }

  return (
    <ListingForm
      form={form}
      onField={setField}
      pages={pages}
      onPagesChange={setPageList}
      errors={errors}
      formError={formError}
      areas={areas}
      onSubmit={submit}
      onFillSample={fillSample}
      onBack={() => navigate("/")}
    />
  );
}
