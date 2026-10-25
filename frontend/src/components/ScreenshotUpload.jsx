import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const MAX_FILES = 20;
const MAX_BYTES = 5 * 1024 * 1024;
let nextId = 0;

/** A page: { id, file, url } — `url` is an object URL for the thumbnail. */
export function revokePages(pages) {
  for (const page of pages) URL.revokeObjectURL(page.url);
}

function kb(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// The design's drop zone, accepting several pages (the API takes up to 20,
// 5MB each). Pages are kept in the order chosen and can be moved: the NLP
// service stitches them in upload order and never sorts them, and a file
// picker's order — or IMG_10 before IMG_2 — is not the chat's order.
// props: { pages, onChange(pages), error, disabled }
export default function ScreenshotUpload({ pages, onChange, error, disabled = false }) {
  const { t } = useTranslation();
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [problems, setProblems] = useState([]);

  function add(fileList) {
    const found = [];
    const added = [];
    for (const file of Array.from(fileList ?? [])) {
      if (!file.type.startsWith("image/")) found.push(t("form.notImage", { name: file.name }));
      else if (file.size > MAX_BYTES) found.push(t("form.tooLarge", { name: file.name }));
      else if (pages.length + added.length >= MAX_FILES) {
        found.push(t("form.tooMany"));
        break;
      } else added.push({ id: ++nextId, file, url: URL.createObjectURL(file) });
    }
    setProblems(found);
    if (added.length) onChange([...pages, ...added]);
  }

  function move(index, by) {
    const next = [...pages];
    const [page] = next.splice(index, 1);
    next.splice(index + by, 0, page);
    onChange(next);
  }

  function remove(index) {
    revokePages([pages[index]]);
    onChange(pages.filter((_, i) => i !== index));
  }

  const iconButton =
    "flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg border border-navy/[.12] bg-white text-[13px] font-bold text-navy disabled:cursor-default disabled:opacity-30";

  return (
    <div className="mt-3.5">
      <div
        role="button"
        tabIndex={0}
        aria-disabled={disabled}
        onClick={() => !disabled && input.current?.click()}
        onKeyDown={(event) => {
          if (!disabled && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) add(event.dataTransfer.files);
        }}
        className={`cursor-pointer rounded-xl border-[1.5px] border-dashed p-[22px] text-center transition-colors ${
          dragging ? "border-teal bg-teal/[.06]" : "border-navy/20 bg-navy/[.02]"
        } ${error ? "border-danger/60" : ""}`}
      >
        <div className="mb-1.5 text-[22px]">📷</div>
        <div className="text-sm font-semibold">{pages.length ? t("form.uploadMore") : t("form.uploadTitle")}</div>
        <div className="mt-[3px] text-[12.5px] text-muted">{t("form.uploadHint")}</div>
        <input
          ref={input}
          type="file"
          accept="image/*"
          multiple
          hidden
          disabled={disabled}
          onChange={(event) => {
            add(event.target.files);
            event.target.value = "";
          }}
        />
      </div>

      {pages.length > 0 && (
        <div className="mt-3">
          <p className="mb-2 text-[12.5px] text-gray-500">{t("form.uploadOrder")}</p>
          <ol className="m-0 flex list-none flex-col gap-2 p-0">
            {pages.map((page, i) => (
              <li key={page.id} className="flex items-center gap-3 rounded-xl border border-navy/[.07] bg-white p-2 pr-3 shadow-card-sm">
                <img src={page.url} alt="" className="h-11 w-11 flex-none rounded-lg object-cover" />
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-semibold">{t("form.page", { n: i + 1 })}</div>
                  <div className="truncate text-[12.5px] text-muted">
                    {page.file.name} · {kb(page.file.size)}
                  </div>
                </div>
                <div className="flex flex-none gap-1.5">
                  <button type="button" className={iconButton} disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("form.moveUp")} title={t("form.moveUp")}>
                    ↑
                  </button>
                  <button type="button" className={iconButton} disabled={i === pages.length - 1} onClick={() => move(i, 1)} aria-label={t("form.moveDown")} title={t("form.moveDown")}>
                    ↓
                  </button>
                  <button type="button" className={iconButton} onClick={() => remove(i)} aria-label={t("form.remove")} title={t("form.remove")}>
                    ✕
                  </button>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {[...problems, ...(error ? [error] : [])].map((message) => (
        <p key={message} className="rs-field-error">{message}</p>
      ))}
    </div>
  );
}
