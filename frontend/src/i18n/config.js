import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import ms from "./ms.json";

const STORAGE_KEY = "rentsafe.lang";

// The chosen language is a per-browser convenience; storage can be blocked
// (private windows), so every access is guarded and English is the fallback.
function savedLanguage() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "ms" || value === "en" ? value : null;
  } catch {
    return null;
  }
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ms: { translation: ms } },
  lng: savedLanguage() ?? "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

function syncDocument(lng) {
  document.documentElement.lang = lng === "ms" ? "ms" : "en";
  try {
    window.localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    // Not persisted; the toggle still works for this visit.
  }
}

syncDocument(i18n.language);
i18n.on("languageChanged", syncDocument);

export default i18n;
