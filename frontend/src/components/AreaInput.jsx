import { useTranslation } from "react-i18next";

// DECISION (author, 2026-10-15) — the design's Area field is free text, but
// the price check accepts only a canonical name from GET /price/areas
// (anything else is unknown_area). This stays a text box, with the list as
// suggestions and a hint when the typed name isn't one of them. If the list
// can't be loaded the field still accepts text and the backend decides.
// props: { id, value, onChange(value), areas, failed, error }
export default function AreaInput({ id, value, onChange, areas, failed, error }) {
  const { t } = useTranslation();
  const typed = value.trim().toLowerCase();
  const exact = areas.find((area) => area.name.toLowerCase() === typed);

  let hint = null;
  if (failed) hint = t("form.areaListUnavailable");
  else if (typed && areas.length && !exact) {
    // "Cheras" is in both states: name the choices, as the backend would.
    const states = areas.filter((area) => area.name.toLowerCase().startsWith(`${typed} (`));
    hint = states.length > 1
      ? t("form.areaTwoState", { name: value.trim(), options: states.map((area) => area.name).join(" / ") })
      : t("form.areaPick");
  }

  return (
    <>
      <input
        id={id}
        list={`${id}-list`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        // Any case is accepted; show the canonical spelling once it matches.
        onBlur={() => exact && exact.name !== value && onChange(exact.name)}
        placeholder={t("form.areaPlaceholder")}
        autoComplete="off"
        className={`rs-input ${error ? "rs-input-error" : ""}`}
      />
      <datalist id={`${id}-list`}>
        {areas.map((area) => (
          <option key={area.name} value={area.name} label={area.state} />
        ))}
      </datalist>
      {error ? (
        <p className="rs-field-error">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-[12.5px] text-gray-500">{hint}</p>
      ) : null}
    </>
  );
}
