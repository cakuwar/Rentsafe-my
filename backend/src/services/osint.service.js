// OSINT / web-intelligence module (FYP2 — P7).
// Searches the public web for negative evidence about an agent — one query
// per identifier (phone, name, REN, company) — and scores what it finds by
// the kind of source it appeared on. Research doc §5.3 is the source of truth;
// the PRD's per-identifier points table is superseded.
//
// Scoring is evidence-only. Points come from what was found; nothing is ever
// added for something missing (no REN, unknown company). A search that could
// not run is reported as excluded (riskFraction null), never as a clean 0.
//
// Each result is classified in two layers:
//   1. rules (always on): identifier + keyword, negation, impersonation
//      notices, social-media company mentions. What survives is a candidate.
//   2. an LLM judge (services/llmVerifier.js), when configured: only a
//      "complaint" at confidence >= 0.6 scores. If the judge is off or fails,
//      the candidates are scored as the rules left them.
// The motivating case: a real agency (Vigor Properties Sdn Bhd) scored 5
// points from four false positives — marketing reels, "bukan scam", and the
// company's own notice that someone was impersonating its agents.
import { createHmac, randomBytes } from "node:crypto";
import { config } from "../config/index.js";
import { cacheGet, cacheSet, counterIncrBy } from "./cache.service.js";
import { search } from "./searchProviders.js";
import { verifierSettings, verifyCandidates } from "./llmVerifier.js";
import { VERIFIER_PROMPT_VERSION } from "../prompts/osintVerifier.prompt.js";
import {
  companyCore,
  findRens,
  normalisePhone,
  normaliseRen,
  phonePattern,
  phoneVariants,
  renDisplay,
} from "./metadata.service.js";
import { isRealKey } from "../utils/keys.js";
import { logger } from "../utils/logger.js";

const MAX_POINTS = 25;

// Each tier scores once, however many hits it has: 12 + 8 + 5 = 25.
const TIER_POINTS = { news: 12, forum: 8, social: 5 };

const TIER_DOMAINS = {
  news: [
    "thestar.com.my", "nst.com.my", "bharian.com.my", "hmetro.com.my",
    "malaysiakini.com", "freemalaysiatoday.com", "malaymail.com", "bernama.com",
    "sinarharian.com.my",
  ],
  forum: ["lowyat.net", "reddit.com", "forum.cari.com.my", "carigold.com"],
  social: [
    "facebook.com", "twitter.com", "x.com", "tiktok.com", "instagram.com",
    "threads.com", "threads.net",
  ],
  // Listing portals print anti-scam boilerplate on every page, so a hit there
  // only shows the number is advertised. Kept as context, never scored.
  portal: [
    "propertyguru.com.my", "iproperty.com.my", "mudah.my", "ibilik.my",
    "edgeprop.my", "speedhome.com",
  ],
};

// Matched on word START (\bterm\w*), so "scam" also catches scams / scammed /
// scammer. Malay affixes come before the stem, so those forms are listed.
// Known noise, accepted: "scampi" matches "scam". It is rare in a rental
// context, and a hit still needs the identifier in the same snippet.
const KEYWORDS = [
  "scam", "scammer", "penipu", "penipuan", "tipu", "ditipu", "menipu",
  "tertipu", "kena tipu", "fraud", "complaint", "aduan", "warning", "amaran",
  "berhati-hati", "hati-hati", "hati hati", "awas", "beware", "victim",
  "mangsa", "blacklist", "senarai hitam", "agen palsu", "fake agent",
  "syarikat tipu",
];

// A keyword hit is ignored when one of these appears within the 3 tokens
// before it: "bukan scam", "risiko scam", "anti-scam", "National Scam
// Response Centre 997" mention scams without accusing anyone.
const NEGATION_WORDS = new Set([
  "bukan", "tak", "tidak", "not", "no", "anti", "elak", "elakkan", "avoid",
  "risiko", "risk", "prevent", "national", "997",
]);
// Checked across the window and the keyword itself ("the scam centre").
const NEGATION_PHRASES = ["response centre", "scam centre"];
// In Malay, "no" is also "number": "no ni scammer", "no 012-345 6789 penipu".
// It negates only when not followed by a number or one of these words.
const NUMBER_WORDS = new Set(["ni", "ini", "tel", "telefon", "hp"]);
const NEGATION_WINDOW = 3;

// Someone warning that OTHERS are posing as them. For a company or REN that is
// the victim speaking; see classify() for why phone and name differ.
const IMPERSONATION_RE =
  /\bimpersonat\w*|\bmenyamar\b|\bmengaku\b|冒充|\bnot\s+affiliated\b|\btiada\s+kaitan\b|\bbukan\s+ejen\s+kami\b/i;

const COMPLAINT_MIN_CONFIDENCE = 0.6;

// The judge sees at most this many candidates, strongest queries first; the
// rest are listed as "unjudged" and score nothing.
const MAX_JUDGE_CANDIDATES = 10;

// Phone and REN identify one person. A name or company can be shared — the
// common name "Muhammad Adam" matched a Nigerian fraud trial, a law firm and a
// government group — so without the judge those never score, and they never
// count toward corroboration.
const UNIQUE_QUERIES = new Set(["phone", "ren"]);

// Complaints about the same phone / REN from this many independent social
// sources (distinct groups or accounts) count as a strong hit.
const SOCIAL_CORROBORATION_MIN = 3;

// The notice names this agent personally (their name, REN or phone): a real
// Vivahomes post warned that scammers were posing as its agent "KEVIN CHEN
// KHAI WEN" with false contact details. The renter's real question is then
// whether the number they are talking to is the agent's.
const AGENT_WARNING = {
  en: "A public notice warns that scammers are pretending to be this agent, using fake "
    + "contact details. Call the agency's official number to confirm this phone number "
    + "really belongs to the agent before paying.",
  ms: "Terdapat notis awam bahawa penipu menyamar sebagai ejen ini menggunakan butiran "
    + "hubungan palsu. Hubungi nombor rasmi agensi untuk memastikan nombor telefon ini "
    + "benar-benar milik ejen tersebut sebelum membuat bayaran.",
};
// The notice is about the company in general.
const COMPANY_WARNING = {
  en: "This company has publicly warned that people are impersonating its agents. "
    + "Verify this agent through the company's official phone line before paying.",
  ms: "Syarikat ini telah memberi amaran awam bahawa ada pihak menyamar sebagai ejennya. "
    + "Sahkan ejen ini melalui talian rasmi syarikat sebelum membuat bayaran.",
};

// Strongest first. A link found by several queries is attributed to the
// strongest one whose own evidence test it passes.
const QUERY_STRENGTH = ["phone", "ren", "name", "company"];
const TIER_ORDER = ["news", "forum", "social"];

const FULL_TTL_SECONDS = 24 * 60 * 60;
const PARTIAL_TTL_SECONDS = 60 * 60;
const QUOTA_TTL_SECONDS = 48 * 60 * 60;

const PROVIDERS = [
  { name: "serper", key: () => config.serperApiKey, limit: () => config.serperDailyLimit },
  { name: "serpapi", key: () => config.serpapiApiKey, limit: () => config.serpapiDailyLimit },
];

const escapeRegex = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const KEYWORD_SOURCE = String.raw`\b(?:${KEYWORDS.map((term) =>
  escapeRegex(term).replace(/ /g, String.raw`\s+`),
).join("|")})\w*`;

/** Whole-word, case-insensitive; tolerant of punctuation like "(M)". */
function wordPattern(text) {
  return new RegExp(
    String.raw`(?<!\w)${escapeRegex(text).replace(/\s+/g, String.raw`\s+`)}(?!\w)`,
    "i",
  );
}

/** NFKC first: titles use Unicode bold ("𝐓𝐀𝐊𝐔𝐓") that no pattern would match. */
function normaliseText(text) {
  return String(text ?? "").normalize("NFKC");
}

function nameTokens(name) {
  return typeof name === "string" ? name.split(" ").filter(Boolean) : [];
}

function maskPhone(phone) {
  return phone ? `${phone.slice(0, 3)}****${phone.slice(-3)}` : "-";
}

/** classifyDomain(link) -> { domain, tier }; exact or subdomain match only. */
export function classifyDomain(link) {
  let host;
  try {
    host = new URL(link).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return { domain: null, tier: "unknown" };
  }
  for (const [tier, domains] of Object.entries(TIER_DOMAINS)) {
    if (domains.some((domain) => host === domain || host.endsWith(`.${domain}`))) {
      return { domain: host, tier };
    }
  }
  return { domain: host, tier: "unknown" };
}

function tokenize(text) {
  return [...text.matchAll(/[\p{L}\p{N}]+/gu)].map((match) => ({
    value: match[0].toLowerCase(),
    start: match.index,
    end: match.index + match[0].length,
  }));
}

/** The cue that negates the keyword at [start, end), or null. */
function negationCue(text, tokens, start, end) {
  const before = tokens.filter((token) => token.end <= start);
  const window = before.slice(-NEGATION_WINDOW);
  for (const token of window) {
    if (token.value === "no") {
      const next = tokens[tokens.indexOf(token) + 1];
      if (next && (/\d/.test(next.value) || NUMBER_WORDS.has(next.value))) continue;
      return "no";
    }
    if (NEGATION_WORDS.has(token.value)) return token.value;
  }
  const after = tokens.find((token) => token.start >= end);
  const span = text
    .slice(window[0]?.start ?? start, after?.end ?? end)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ");
  return NEGATION_PHRASES.find((phrase) => ` ${span} `.includes(` ${phrase} `)) ?? null;
}

/**
 * keywordHits(text) -> { terms, ignored }
 * terms: keyword forms that count, lowercased and de-duplicated.
 * ignored: [{ term, cue }] hits dropped by the negation window.
 */
export function keywordHits(text) {
  const normalised = normaliseText(text);
  const tokens = tokenize(normalised);
  const terms = new Set();
  const ignored = new Map();
  for (const match of normalised.matchAll(new RegExp(KEYWORD_SOURCE, "gi"))) {
    const term = match[0].toLowerCase().replace(/\s+/g, " ");
    const cue = negationCue(normalised, tokens, match.index, match.index + match[0].length);
    if (cue) ignored.set(`${term}|${cue}`, { term, cue });
    else terms.add(term);
  }
  return { terms: [...terms], ignored: [...ignored.values()] };
}

/** matchedTerms(text) -> the keyword forms that count (negated hits excluded). */
export function matchedTerms(text) {
  return keywordHits(text).terms;
}

// The URL slug is read for the impersonation cue ONLY — never for identifier
// or keyword evidence. A Facebook post's slug carries its opening text, and
// that is the only place the Vigor notice says 冒充 ("impersonate").
function decodedPath(link) {
  try {
    return decodeURIComponent(new URL(link).pathname).replace(/[-_/]+/g, " ");
  } catch {
    return "";
  }
}

function hasImpersonationCue(text, link) {
  return IMPERSONATION_RE.test(text) || IMPERSONATION_RE.test(decodedPath(link));
}

// Each query's own identifier test. A result only counts for the query whose
// identifier it actually contains.
const IDENTIFIER_TESTS = {
  phone: (text, identity) =>
    [...text.matchAll(phonePattern())].some((match) => normalisePhone(match[0]) === identity.phone),
  name: (text, identity) => nameTokens(identity.name).every((token) => wordPattern(token).test(text)),
  ren: (text, identity) => findRens(text).includes(identity.ren),
  company: (text, identity) => wordPattern(identity.companyCore).test(text),
};

/**
 * Layer 1 for one (result, query) pair -> null (not about this identifier,
 * or no keyword at all), a context item, or a candidate.
 */
// Which identifiers this search has: the same rules that decide whether a
// query is sent.
const SEARCHABLE = {
  phone: (identity) => Boolean(identity.phone),
  ren: (identity) => Boolean(identity.ren),
  name: (identity) => nameTokens(identity.name).length >= 2,
  company: (identity) => Boolean(identity.companyCore),
};

/**
 * Keywords in the title and the snippet, checked separately. Joined, the end
 * of a truncated title negated the start of the snippet: a PDRM post titled
 * "…TAWAR RUMAH TIDAK …" (a house that does not exist) lost "PENIPUAN RUMAH
 * SEWA" to "tidak".
 */
function fieldHits(title, snippet) {
  const parts = [keywordHits(title), keywordHits(snippet)];
  const ignored = new Map();
  for (const item of parts.flatMap((part) => part.ignored)) ignored.set(`${item.term}|${item.cue}`, item);
  return {
    terms: [...new Set(parts.flatMap((part) => part.terms))],
    ignored: [...ignored.values()],
  };
}

/**
 * Layer 1 for one (result, query) pair -> null (not about this agent, or no
 * keyword at all), a context item, or a candidate.
 *
 * A result is attributed to the strongest identifier that appears in its own
 * text (phone > ren > name > company), whichever query happened to find it
 * (`foundBy`). Google returned a post with "No tel : 01169340728" for the name
 * query only; filed under the name, it could neither corroborate nor survive
 * the rules-only fallback.
 */
function classify(result, kind, identity) {
  const { domain, tier } = classifyDomain(result.link);
  if (tier === "unknown") return null;

  // " | " keeps the title's last digits and the snippet's first from reading
  // as one phone number.
  const text = normaliseText(`${result.title} | ${result.snippet}`);
  const query = QUERY_STRENGTH.find(
    (key) => SEARCHABLE[key](identity) && IDENTIFIER_TESTS[key](text, identity),
  );
  if (!query) return null;

  const base = {
    title: result.title,
    link: result.link,
    snippet: result.snippet,
    domain,
    tier,
    query,
    foundBy: kind,
  };
  if (tier === "portal") return { ...base, class: "context", type: "listing_portal" };

  const matched = fieldHits(normaliseText(result.title), normaliseText(result.snippet));
  if (matched.terms.length === 0 && matched.ignored.length === 0) return null;

  // For a company or REN the impersonation notice is the victim speaking: a
  // real REN is exactly what an impersonator borrows. For a phone or name the
  // same words describe the accused ("Lelaki menyamar ejen hartanah
  // ditahan"), so those go to the judge — or, without one, to context.
  const impersonation = hasImpersonationCue(text, result.link);
  if (impersonation && (query === "company" || query === "ren")) {
    return { ...base, matched, class: "context", type: "impersonation_notice" };
  }
  if (matched.terms.length === 0) {
    return { ...base, matched, class: "context", type: "generic_mention" };
  }
  if (query === "company" && tier === "social") {
    return { ...base, matched, class: "context", type: "social_mention" };
  }
  return { ...base, matched, class: "candidate", impersonationCue: impersonation };
}

/** Layer 1 over every answered query, one item per link. */
function applyRules(answered, identity) {
  const best = new Map();
  for (const { kind, results } of answered) {
    for (const result of results) {
      const item = classify(result, kind, identity);
      if (!item) continue;
      // A candidate beats a context item; then the stronger identifier wins.
      const rank = (item.class === "candidate" ? 0 : 10) + QUERY_STRENGTH.indexOf(item.query);
      const existing = best.get(item.link);
      if (existing && existing.rank <= rank) continue;
      best.set(item.link, { rank, item });
    }
  }
  const items = [...best.values()].map(({ item }) => item);
  return {
    candidates: items.filter((item) => item.class === "candidate"),
    context: items.filter((item) => item.class === "context"),
  };
}

function publicItem(item) {
  const { class: _class, impersonationCue: _cue, id: _id, ...rest } = item;
  return rest;
}

/**
 * Candidates scored by the rules alone (judge off, or it failed). Only the
 * unique identifiers can score: a name or company hit is held back as
 * "unverified_mention" because nothing can tell it apart from a namesake.
 */
function rulesOnly(candidates) {
  const evidence = [];
  const context = [];
  for (const item of candidates) {
    if (!UNIQUE_QUERIES.has(item.query)) {
      context.push({ ...publicItem(item), type: "unverified_mention" });
    } else if (item.impersonationCue) {
      context.push({ ...publicItem(item), type: "impersonation_mention" });
    } else {
      evidence.push(publicItem(item));
    }
  }
  return { evidence, context };
}

// Collapses the URL forms of one social account or group into one key, so
// five posts in one Facebook group count as one source. Forms that carry no
// account (instagram.com/reel/<id>, facebook.com/story.php?…) all share one
// key per form: that under-counts, it never over-counts. x.com and
// twitter.com are the same accounts under two domains, so they share "x:".
const keyed = (prefix, part) => (part ? `${prefix}:${part}` : prefix);
const account = (segment) => (segment ?? "").replace(/^@/, "");
const SOURCE_KEYS = {
  "facebook.com": (segments) =>
    segments[0] === "groups" && segments[1]
      ? `facebook:group:${segments[1]}`
      : keyed("facebook", segments[0]),
  "threads.com": (segments) => keyed("threads", account(segments[0])),
  "threads.net": (segments) => keyed("threads", account(segments[0])),
  "x.com": (segments) => keyed("x", account(segments[0])),
  "twitter.com": (segments) => keyed("x", account(segments[0])),
  "instagram.com": (segments) => keyed("instagram.com", account(segments[0])),
  "tiktok.com": (segments) => keyed("tiktok.com", account(segments[0])),
};

/** sourceKeyFor(link) -> "facebook:group:<id>", "threads:<user>", a hostname… */
export function sourceKeyFor(link) {
  let url;
  try {
    url = new URL(link);
  } catch {
    return null;
  }
  const host = url.hostname.toLowerCase().replace(/^(?:www|m|web|mobile)\./, "");
  const platform = Object.keys(SOURCE_KEYS).find((domain) => host === domain || host.endsWith(`.${domain}`));
  if (!platform) return host;
  const segments = url.pathname
    .split("/")
    .filter(Boolean)
    .map((segment) => {
      try {
        return decodeURIComponent(segment).toLowerCase();
      } catch {
        return segment.toLowerCase();
      }
    });
  return SOURCE_KEYS[platform](segments);
}

function identifierFor(kind, identity) {
  if (kind === "phone") return phoneVariants(identity.phone)[0] ?? identity.phone;
  if (kind === "ren") return renDisplay(identity.ren);
  if (kind === "name") return identity.name;
  return identity.company;
}

/**
 * Layer 2 -> { evidence, context, verifier, verifierProvider, verifierError,
 *              verifierRetried, judgeCandidates, judgeFailed }
 * Only a "complaint" at confidence >= 0.6 scores; everything else is context.
 */
async function applyJudge(candidates, identity, settings) {
  const report = { verifierError: null, verifierRetried: false, judgeCandidates: 0, judgeFailed: false };
  if (!settings.enabled) {
    return { ...rulesOnly(candidates), ...report, verifier: "rules_only", verifierProvider: null };
  }
  if (candidates.length === 0) {
    return { evidence: [], context: [], ...report, verifier: "llm", verifierProvider: settings.provider };
  }

  // Strongest queries first, search-rank order within each (sort is stable).
  const ordered = [...candidates].sort(
    (a, b) => QUERY_STRENGTH.indexOf(a.query) - QUERY_STRENGTH.indexOf(b.query),
  );
  const tagged = ordered
    .slice(0, MAX_JUDGE_CANDIDATES)
    .map((item, index) => ({ ...item, id: `c${index + 1}` }));
  const unjudged = ordered.slice(MAX_JUDGE_CANDIDATES);

  let verdicts;
  let retried;
  try {
    ({ verdicts, retried } = await verifyCandidates(
      tagged.map((item) => ({
        id: item.id,
        queryType: item.query,
        identifier: identifierFor(item.query, identity),
        domain: item.domain,
        title: normaliseText(item.title),
        snippet: normaliseText(item.snippet),
      })),
      settings,
    ));
  } catch (error) {
    // error is a JudgeError: classified, redacted and truncated already.
    logger.warn(
      `OSINT judge (${settings.provider}) failed: ${error.verifierError} status=${error.status ?? "-"}` +
        `${error.retried ? " (after one retry)" : ""}: ${error.message}; using rules only`,
    );
    return {
      ...rulesOnly(candidates),
      verifier: "rules_only",
      verifierProvider: settings.provider,
      verifierError: error.verifierError ?? "other",
      verifierRetried: Boolean(error.retried),
      judgeCandidates: tagged.length,
      judgeFailed: true,
    };
  }

  const byId = new Map(verdicts.map((verdict) => [verdict.id, verdict]));
  const evidence = [];
  const context = unjudged.map((item) => ({ ...publicItem(item), type: "unjudged" }));
  for (const item of tagged) {
    const verdict = byId.get(item.id);
    const judged = verdict
      ? { ...publicItem(item), label: verdict.label, confidence: verdict.confidence, reason: verdict.reason }
      : { ...publicItem(item), label: "unrelated", confidence: null, reason: null, judgeMissing: true };

    if (judged.label === "complaint" && judged.confidence >= COMPLAINT_MIN_CONFIDENCE) {
      // DECISION (author, 2026-10-11) — a complaint that matches only the
      // agent's NAME never scores. The judge is shown just the name, so it
      // cannot tell a namesake from the agent: it rated "Syed Ahmad Razali bin
      // Wan Yusof … SCAMMER jugak" a complaint at 0.9 with no phone in sight.
      // Shown as "same name reported, may be a different person". A post that
      // also carries the phone or REN is attributed to that instead (classify).
      if (item.query === "name") context.push({ ...judged, type: "name_only_match" });
      else evidence.push(judged);
    } else {
      context.push({
        ...judged,
        type: judged.label === "complaint" ? "low_confidence_complaint" : judged.label,
      });
    }
  }
  return {
    evidence,
    context,
    verifier: "llm",
    verifierProvider: settings.provider,
    verifierError: null,
    verifierRetried: retried,
    judgeCandidates: tagged.length,
    judgeFailed: false,
  };
}

/**
 * strongHit and why. Only phone / REN evidence counts:
 *   news_or_forum         a phone / REN complaint on a news site or forum
 *   social_corroboration  phone / REN complaints from >= 3 distinct social
 *                         sources (several posts in one group = one source)
 */
function assessStrength(evidence) {
  const unique = evidence.filter((item) => UNIQUE_QUERIES.has(item.query));
  const keys = [
    ...new Set(unique.filter((item) => item.tier === "social").map((item) => item.sourceKey).filter(Boolean)),
  ];
  const newsOrForum = unique.some((item) => item.tier === "news" || item.tier === "forum");
  const corroborated = keys.length >= SOCIAL_CORROBORATION_MIN;
  return {
    strongHit: newsOrForum || corroborated,
    strongHitReason: newsOrForum ? "news_or_forum" : corroborated ? "social_corroboration" : null,
    corroboration: { sources: keys.length, threshold: SOCIAL_CORROBORATION_MIN, keys },
  };
}

/** One warning per company, listing every impersonation notice found. */
/**
 * One impersonation warning at most, listing every notice found.
 * scope "agent": a notice is about this agent personally (attributed to their
 * phone, REN or name); "company": the notices are about the company only.
 */
function buildWarnings(context, identity) {
  const notices = context.filter((item) => item.type === "impersonation_notice");
  if (notices.length === 0) return [];
  const scope = notices.some((item) => item.query !== "company") ? "agent" : "company";
  return [{
    type: "impersonation_notice",
    scope,
    company: identity.company,
    links: notices.map((item) => item.link),
    ...(scope === "agent" ? AGENT_WARNING : COMPANY_WARNING),
  }];
}

function buildIdentity(meta) {
  const name = typeof meta?.agentName === "string"
    ? meta.agentName.replace(/["\s]+/g, " ").trim() || null
    : null;
  const company = typeof meta?.company === "string"
    ? meta.company.replace(/["\s]+/g, " ").trim() || null
    : null;
  return {
    phone: normalisePhone(meta?.phone ?? ""),
    name,
    ren: normaliseRen(meta?.renNumber ?? ""),
    company,
    companyCore: companyCore(company ?? ""),
    source: meta?.identitySource ?? null,
  };
}

function buildQueries(identity) {
  const queries = [];
  if (identity.phone) {
    const variants = phoneVariants(identity.phone).map((variant) => `"${variant}"`).join(" OR ");
    queries.push({ kind: "phone", q: `(${variants}) scam OR penipu OR penipuan OR tipu` });
  }
  if (nameTokens(identity.name).length >= 2) {
    queries.push({ kind: "name", q: `"${identity.name}" scam OR penipu OR "agen palsu" OR fraud property` });
  }
  if (identity.ren) {
    queries.push({ kind: "ren", q: `"${renDisplay(identity.ren)}" scam OR penipu OR "fake agent" OR penipuan` });
  }
  if (identity.companyCore) {
    queries.push({
      kind: "company",
      q: `"${identity.company}" scam OR penipu OR fraud OR "syarikat tipu" property Malaysia`,
    });
  }
  return queries;
}

// Cache keys are HMACs, not plain hashes: a sha256 of a phone number can be
// reversed by hashing every Malaysian mobile number, which is personal data
// under the PDPA. Without a configured secret, a per-process one keeps keys
// private at the cost of a cache that does not survive a restart.
let processSecret = null;
function cacheSecret() {
  if (config.osintCacheSecret) return config.osintCacheSecret;
  if (!processSecret) {
    processSecret = randomBytes(32).toString("hex");
    logger.warn("OSINT_CACHE_SECRET is not set; OSINT cache will not survive a restart");
  }
  return processSecret;
}

// The prompt version and the judge mode are in the key, so a prompt change —
// or turning the judge on — never serves labels made under the old setup.
function cacheKeyFor(identity, settings) {
  const material = [identity.phone, identity.name, identity.ren, identity.company]
    .map((value) => (value ?? "").toLowerCase())
    .join("|");
  const mode = settings.enabled ? settings.provider : "rules";
  const digest = createHmac("sha256", cacheSecret()).update(material).digest("hex");
  return `osint:v3:${VERIFIER_PROMPT_VERSION}:${mode}:${digest}`;
}

// ---------------------------------------------------------------------------
// Daily quota, per provider. Reserved before the queries are sent; queries
// that were sent stay counted even if they failed. If Redis is down the count
// is kept in memory instead — per process, but still a ceiling.
// ---------------------------------------------------------------------------

const memoryQuota = new Map();

function quotaDate() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kuala_Lumpur",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

async function reserveQuota(provider, count) {
  const date = quotaDate();
  const key = `osint:quota:${provider.name}:${date}`;
  const limit = provider.limit();

  const used = await counterIncrBy(key, count, QUOTA_TTL_SECONDS);
  if (used !== null) {
    if (used <= limit) return true;
    await counterIncrBy(key, -count, QUOTA_TTL_SECONDS);
    return false;
  }

  for (const stored of memoryQuota.keys()) {
    if (!stored.endsWith(date)) memoryQuota.delete(stored);
  }
  const next = (memoryQuota.get(key) ?? 0) + count;
  if (next > limit) return false;
  memoryQuota.set(key, next);
  return true;
}

async function runQueries(provider, queries) {
  const settled = await Promise.allSettled(queries.map(({ q }) => search(provider.name, q)));
  const answered = [];
  let failed = 0;
  settled.forEach((outcome, index) => {
    if (outcome.status === "fulfilled") {
      answered.push({ kind: queries[index].kind, results: outcome.value.results });
    } else {
      failed += 1;
      // Provider, status and query kind only: never the error object (it can
      // carry the API key) and never the query text (it carries the phone).
      logger.warn(
        `OSINT ${provider.name} ${queries[index].kind} query failed: status=${outcome.reason?.status ?? "network"}`,
      );
    }
  });
  return { answered, failed };
}

function publicIdentity(identity) {
  return {
    phone: identity.phone,
    name: identity.name,
    ren: renDisplay(identity.ren),
    company: identity.company,
    source: identity.source,
  };
}

function outcome(status, identity, extra = {}) {
  return {
    status,
    provider: null,
    riskFraction: null,
    points: null,
    max: MAX_POINTS,
    breakdown: { news: 0, forum: 0, social: 0 },
    strongHit: false,
    strongHitReason: null,
    corroboration: { sources: 0, threshold: SOCIAL_CORROBORATION_MIN, keys: [] },
    warnings: [],
    verifier: null,
    verifierProvider: null,
    verifierVersion: VERIFIER_PROMPT_VERSION,
    verifierError: null,
    verifierRetried: false,
    judgeCandidates: 0,
    identity: publicIdentity(identity),
    queries: [],
    failedQueries: 0,
    evidence: [],
    context: [],
    cached: false,
    fetchedAt: null,
    ...extra,
  };
}

/**
 * searchAgentReputation(meta) -> osint result (see docs/API_SPEC.md)
 *
 * status:
 *   no_identifier   no valid phone and no full (2+ word) name     -> excluded
 *   not_configured  no real Serper or SerpApi key                 -> excluded
 *   quota_exceeded  every configured provider is over its daily limit -> excluded
 *   search_failed   every query failed, after the SerpApi fallback -> excluded
 *   ok              at least one query answered; riskFraction = points / 25
 *
 * Provider: Serper if configured and within quota, else SerpApi. If every
 * Serper query fails, the whole set is retried once on SerpApi; a partial
 * failure is not retried. One result set never mixes providers.
 *
 * verifier: "llm" when the judge ran (or had no candidates to judge),
 * "rules_only" when it is off (verifierProvider null) or failed
 * (verifierProvider and verifierError set). Under rules_only only phone and
 * REN hits can score.
 *
 * strongHit: a phone / REN complaint on a news site or forum, or from >= 3
 * distinct social sources (strongHitReason, corroboration).
 *
 * Never throws.
 */
export async function searchAgentReputation(meta) {
  const identity = buildIdentity(meta);
  if (!identity.phone && nameTokens(identity.name).length < 2) {
    return outcome("no_identifier", identity);
  }

  const queries = buildQueries(identity);
  const kinds = queries.map((query) => query.kind);
  const settings = verifierSettings();

  const cacheKey = cacheKeyFor(identity, settings);
  const cached = await cacheGet(cacheKey);
  if (cached) return { ...cached, cached: true };

  const configured = PROVIDERS.filter((provider) => isRealKey(provider.key()));
  if (configured.length === 0) return outcome("not_configured", identity, { queries: kinds });

  let provider = null;
  for (const candidate of configured) {
    if (await reserveQuota(candidate, queries.length)) {
      provider = candidate;
      break;
    }
  }
  if (!provider) return outcome("quota_exceeded", identity, { queries: kinds });

  let run = await runQueries(provider, queries);

  if (run.failed === queries.length && provider.name === "serper") {
    const fallback = configured.find((candidate) => candidate.name === "serpapi");
    if (fallback && (await reserveQuota(fallback, queries.length))) {
      logger.warn("OSINT: every serper query failed; retrying the set on serpapi");
      provider = fallback;
      run = await runQueries(provider, queries);
    }
  }

  if (run.failed === queries.length) {
    return outcome("search_failed", identity, {
      provider: provider.name,
      queries: kinds,
      failedQueries: run.failed,
    });
  }

  const rules = applyRules(run.answered, identity);
  const judged = await applyJudge(rules.candidates, identity, settings);
  const evidence = judged.evidence
    .map((item) => ({ ...item, sourceKey: sourceKeyFor(item.link) }))
    .sort((a, b) => TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier));
  const context = [...rules.context.map(publicItem), ...judged.context];

  const tiersHit = new Set(evidence.map((item) => item.tier));
  const breakdown = Object.fromEntries(
    TIER_ORDER.map((tier) => [tier, tiersHit.has(tier) ? TIER_POINTS[tier] : 0]),
  );
  const points = Math.min(
    MAX_POINTS,
    Object.values(breakdown).reduce((sum, value) => sum + value, 0),
  );
  // strongHit lifts the band cap in scoring.service.js; a name or company can
  // belong to someone else, so only phone / REN evidence counts toward it.
  const strength = assessStrength(evidence);

  const result = outcome("ok", identity, {
    provider: provider.name,
    riskFraction: points / MAX_POINTS,
    points,
    breakdown,
    ...strength,
    warnings: buildWarnings(context, identity),
    verifier: judged.verifier,
    verifierProvider: judged.verifierProvider,
    verifierError: judged.verifierError,
    verifierRetried: judged.verifierRetried,
    judgeCandidates: judged.judgeCandidates,
    queries: kinds,
    failedQueries: run.failed,
    evidence,
    context,
    fetchedAt: new Date().toISOString(),
  });

  logger.info(
    `OSINT ${maskPhone(identity.phone)} via ${provider.name} (${judged.verifier}): ${points}/${MAX_POINTS}` +
      `${run.failed ? ` (${run.failed} of ${queries.length} queries failed)` : ""}`,
  );
  // A partial search, or a judge that failed, is cached briefly so the full
  // answer replaces it soon.
  const brief = run.failed > 0 || judged.judgeFailed;
  await cacheSet(cacheKey, result, brief ? PARTIAL_TTL_SECONDS : FULL_TTL_SECONDS);
  return result;
}
