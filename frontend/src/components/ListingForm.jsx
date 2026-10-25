import { useTranslation } from "react-i18next";
import ScreenshotUpload from "./ScreenshotUpload.jsx";
import AreaInput from "./AreaInput.jsx";
import {
  BEDROOM_OPTIONS,
  BEDROOM_TYPES,
  PROPERTY_TYPES,
  ROOM_TYPES,
  hasSearchableIdentity,
} from "../lib/listing.js";

// DECISION (author, 2026-10-15) — where the design and the backend disagree
// the form follows the backend (docs/API_SPEC.md):
// - Property type: the design's Studio / Room / Whole unit becomes the API's
//   studio, condo, apartment, flat, landed, room. Nothing is preselected (the
//   design defaulted to Studio, which would compare rooms as studios).
//   Bedrooms (1, 2, 3, 4+) shows only for whole units; a room asks master or
//   common instead.
// - Phone and agent name are optional in the API (it falls back to the chat),
//   so the design's red asterisks become "(recommended)", with a note when
//   neither is searchable rather than a blocked submit.
// - The rent is read only from these fields (D8), never from the chat.
// props: { form, onField(key, value), pages, onPagesChange, errors, formError,
//          areas: { areas, failed }, onSubmit, onFillSample, onBack }

function Field({ id, label, note, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="rs-label">
        {label} {note && <span className="font-normal text-muted">{note}</span>}
      </label>
      {children}
      {error && <p className="rs-field-error">{error}</p>}
    </div>
  );
}

export default function ListingForm({
  form, onField, pages, onPagesChange, errors, formError, areas, onSubmit, onFillSample, onBack,
}) {
  const { t } = useTranslation();
  const usingScreenshots = pages.length > 0;
  const hasInput = form.listingText.trim() !== "" || usingScreenshots;
  const input = (key) => ({
    id: `rs-${key}`,
    value: form[key],
    onChange: (event) => onField(key, event.target.value),
    className: `rs-input ${errors[key] ? "rs-input-error" : ""}`,
  });

  return (
    <main className="mx-auto max-w-[720px] animate-rs-fade px-5 pb-20 pt-10">
      <button type="button" onClick={onBack} className="rs-back">
        {t("form.back")}
      </button>
      <h2 className="mb-1.5 font-serif text-[30px] font-bold tracking-[-.5px]">{t("form.title")}</h2>
      <p className="mb-7 text-[15px] text-gray-500">{t("form.subtitle")}</p>

      {formError && (
        <div role="alert" className="mb-5 rounded-xl border border-danger/20 bg-danger/[.08] px-4 py-3 text-sm font-semibold text-danger-text">
          {formError}
        </div>
      )}

      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        {/* PASTE */}
        <label htmlFor="rs-listingText" className="mb-2 block text-sm font-semibold">
          {t("form.textLabel")}
        </label>
        <textarea
          id="rs-listingText"
          value={form.listingText}
          onChange={(event) => onField("listingText", event.target.value)}
          placeholder={t("form.placeholder")}
          className={`block min-h-[110px] w-full resize-y rounded-xl border-[1.5px] border-navy/[.15] bg-white p-3.5 font-sans text-[15px] leading-normal text-navy outline-none transition-colors focus:border-teal ${
            usingScreenshots ? "opacity-50" : ""
          } ${errors.listingText ? "rs-input-error" : ""}`}
        />
        {usingScreenshots && <p className="mt-1.5 text-[12.5px] text-gray-500">{t("form.textIgnored")}</p>}
        {errors.listingText && <p className="rs-field-error">{errors.listingText}</p>}

        {/* UPLOAD */}
        <ScreenshotUpload pages={pages} onChange={onPagesChange} error={errors.files} />

        {/* AGENT */}
        <div className="rs-eyebrow mt-[30px]">{t("form.agentDetails")}</div>
        {hasInput && !hasSearchableIdentity(form) && (
          <p className="mb-0 mt-3 rounded-[10px] bg-amber/[.12] px-3 py-2.5 text-[13px] font-semibold text-amber-text">
            {t("form.noIdentity")}
          </p>
        )}
        <div className="mt-3.5 grid grid-cols-2 gap-3.5">
          <Field id="rs-phone" label={t("form.phone")} note={t("form.recommended")} error={errors.phone}>
            <input {...input("phone")} type="tel" placeholder={t("form.phonePlaceholder")} />
          </Field>
          <Field id="rs-agentName" label={t("form.agentName")} note={t("form.recommended")} error={errors.agentName}>
            <input {...input("agentName")} placeholder={t("form.agentNamePlaceholder")} />
          </Field>
          <Field id="rs-ren" label={t("form.ren")} note={t("form.optional")} error={errors.ren}>
            <input {...input("ren")} placeholder={t("form.renPlaceholder")} />
          </Field>
          <Field id="rs-company" label={t("form.company")} note={t("form.optional")} error={errors.company}>
            <input {...input("company")} placeholder={t("form.companyPlaceholder")} />
          </Field>
        </div>

        {/* LISTING */}
        <div className="rs-eyebrow mt-7">{t("form.listingDetails")}</div>
        <div className="mt-3.5 grid grid-cols-2 gap-3.5">
          <Field id="rs-rent" label={t("form.rent")} error={errors.rent}>
            <input {...input("rent")} inputMode="decimal" placeholder={t("form.rentPlaceholder")} />
          </Field>
          <div>
            <label htmlFor="rs-area" className="rs-label">{t("form.area")}</label>
            <AreaInput
              id="rs-area"
              value={form.area}
              onChange={(value) => onField("area", value)}
              areas={areas.areas}
              failed={areas.failed}
              error={errors.area}
            />
          </div>
          <Field id="rs-propertyType" label={t("form.propertyType")} error={errors.propertyType}>
            <select {...input("propertyType")}>
              <option value="">{t("form.choose")}</option>
              {PROPERTY_TYPES.map((type) => (
                <option key={type} value={type}>{t(`form.types.${type}`)}</option>
              ))}
            </select>
          </Field>
          {BEDROOM_TYPES.includes(form.propertyType) && (
            <Field id="rs-bedrooms" label={t("form.bedrooms")} error={errors.bedrooms}>
              <select {...input("bedrooms")}>
                <option value="">{t("form.choose")}</option>
                {BEDROOM_OPTIONS.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </Field>
          )}
          {form.propertyType === "room" && (
            <Field id="rs-roomType" label={t("form.roomType")} error={errors.roomType}>
              <select {...input("roomType")}>
                <option value="">{t("form.choose")}</option>
                {ROOM_TYPES.map((room) => (
                  <option key={room} value={room}>{t(`form.roomTypes.${room}`)}</option>
                ))}
              </select>
            </Field>
          )}
        </div>

        <button
          type="submit"
          className="mt-7 w-full cursor-pointer rounded-xl border-none bg-teal p-4 font-sans text-[16.5px] font-bold text-white shadow-cta-teal"
        >
          {t("form.submit")}
        </button>
        <button
          type="button"
          onClick={onFillSample}
          className="mt-2.5 w-full cursor-pointer border-none bg-transparent p-1.5 text-[13.5px] font-semibold text-gray-500"
        >
          {t("form.fillSample")}
        </button>
      </form>
    </main>
  );
}
