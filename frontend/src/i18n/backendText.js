// Malay for the API text that only comes back in English.
//
// DECISION (author, 2026-10-16) — conflict 5, a stopgap. Two kinds of API
// text have no Malay version:
// - legitimacy signals (evidence.legitSignals): nlp-service layer 1 returns
//   only label_en / note_en (red_flags.py LEGIT_SIGNALS);
// - validation and error messages from the backend (zod messages in
//   backend/src/validation, analyze.controller.js, errorHandler.js).
// Until the backend returns { en, ms } for these, the known strings are
// looked up here; an unknown string is shown in English, as before. The
// proper fix is backend-side, and this file goes when it lands.

const LEGIT_MS = {
  ren_number: {
    label: "Nombor pendaftaran REN disebut",
    note: "Sahkan di lppeh.gov.my — nombor REN kadang-kadang disalin daripada ejen sebenar.",
  },
  registered_firm: {
    label: "Agensi berdaftar dinamakan",
    note: "Semak nombor firma dengan senarai awam agensi itu.",
  },
  viewing_first: {
    label: "Lawatan unit ditawarkan sebelum sebarang bayaran",
    note: "Tanda tunggal paling kuat bagi iklan yang tulen.",
  },
  formal_documents: {
    label: "Dokumen pemilikan atau penyewaan disebut",
    note: "Minta untuk melihatnya; dokumen boleh dipalsukan.",
  },
  stamping_mentioned: {
    label: "Setem perjanjian disebut",
    note: "Perjanjian sewa yang disetem boleh dikuatkuasakan; minta salinan yang disetem.",
  },
  company_account: {
    label: "Bayaran ke akaun syarikat",
    note: "Lebih baik daripada akaun peribadi, tetapi pastikan syarikat itu ialah agensi yang anda berurusan.",
  },
  viewing_arranged: {
    label: "Lawatan unit telah diatur",
    note: "Mengatur untuk melihat unit secara bersemuka ialah tanda paling kuat bagi iklan yang tulen — dengan syarat lawatan berlaku sebelum sebarang wang dibayar.",
  },
  in_person_handover: {
    label: "Kunci diserahkan secara bersemuka",
    note: "Bertentangan dengan kunci melalui kurier: orang yang berjumpa anda untuk menyerahkan kunci boleh disahkan.",
  },
  payment_at_handover: {
    label: "Bayaran dikaitkan dengan menandatangani atau serahan kunci",
    note: "Membayar semasa menandatangani atau serahan kunci, selepas melihat unit, adalah bertentangan dengan penipuan bayar-sebelum-lihat.",
  },
  platform_agreement: {
    label: "Perjanjian bertulis melalui platform atau agensi",
    note: "Perjanjian yang dikeluarkan melalui platform yang dinamakan meninggalkan rekod di luar sembang. Pastikan platform itu yang sebenar.",
  },
};

const MESSAGES_MS = {
  // analyze.controller.js
  "text is required": "Teks diperlukan.",
  "text is too short to analyse — paste the conversation": "Teks terlalu pendek untuk dianalisis — tampal perbualan itu.",
  "No screenshot uploaded": "Tiada tangkapan skrin dimuat naik.",
  "Attach at least one screenshot.": "Lampirkan sekurang-kurangnya satu tangkapan skrin.",
  "No text could be read from the screenshots": "Tiada teks dapat dibaca daripada tangkapan skrin.",
  // validation/agent.schema.js, validation/property.schema.js
  "phone must be a Malaysian mobile number, e.g. 012-345 6789":
    "Nombor telefon mesti nombor mudah alih Malaysia, cth. 012-345 6789.",
  "price must be a monthly rent in RM, e.g. 1500 or RM1,500": "Harga mesti sewa bulanan dalam RM, cth. 1500 atau RM1,500.",
  "price must be more than 0": "Harga mesti lebih daripada 0.",
  "price must be at most RM100,000 a month": "Harga mesti tidak melebihi RM100,000 sebulan.",
  "bedrooms must be a whole number from 0 to 20 (0 = studio)": "Bilik tidur mesti nombor bulat dari 0 hingga 20 (0 = studio).",
  "roomType must be master or common (single and middle count as common)":
    "Jenis bilik mesti bilik utama atau bilik biasa (bilik single dan tengah dikira sebagai bilik biasa).",
  // middleware/errorHandler.js, app.js, price.controller.js
  "Validation failed": "Pengesahan gagal.",
  "Screenshot too large (max 5MB).": "Tangkapan skrin terlalu besar (maksimum 5MB).",
  "Too many screenshots (max 20).": "Terlalu banyak tangkapan skrin (maksimum 20).",
  "Analysis service unavailable": "Perkhidmatan analisis tidak tersedia.",
  "The NLP service is not responding. Try again shortly.": "Perkhidmatan NLP tidak bertindak balas. Cuba lagi sebentar lagi.",
  "Internal server error": "Ralat pelayan dalaman.",
  "Request failed": "Permintaan gagal.",
  "Route not found": "Laluan tidak ditemui.",
  "Price data is unavailable right now": "Data harga tidak tersedia buat masa ini.",
};

// Messages with a value in them: the propertyType list, and zod's defaults
// for the max lengths in agent.schema.js and the bedrooms range.
const PATTERNS_MS = [
  [/^propertyType must be one of /, () => "Pilih jenis hartanah daripada senarai."],
  [/^String must contain at most (\d+) character\(s\)$/, (n) => `Mesti tidak melebihi ${n} aksara.`],
  [/^Number must be greater than or equal to (\d+)$/, (n) => `Mesti sekurang-kurangnya ${n}.`],
  [/^Number must be less than or equal to (\d+)$/, (n) => `Mesti tidak melebihi ${n}.`],
];

/** backendMessage(message, language) -> the message in Malay when known, else as given. */
export function backendMessage(message, language) {
  if (language !== "ms" || typeof message !== "string") return message;
  if (MESSAGES_MS[message]) return MESSAGES_MS[message];
  for (const [pattern, build] of PATTERNS_MS) {
    const match = message.match(pattern);
    if (match) return build(match[1]);
  }
  return message;
}

/** legitSignalText(signal, language) -> { label, note } */
export function legitSignalText(signal, language) {
  const ms = language === "ms" ? LEGIT_MS[signal?.id] : null;
  return { label: ms?.label ?? signal?.label_en, note: ms?.note ?? signal?.note_en };
}
