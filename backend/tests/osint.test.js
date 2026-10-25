// OSINT web search: source tiers, the evidence test, query selection, cache,
// quota, and the Serper -> SerpApi fallback. The search providers and Redis
// are mocked; everything else is the real module.
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockSearch, cache, counters } = vi.hoisted(() => ({
  mockSearch: vi.fn(),
  cache: { get: vi.fn(), set: vi.fn(), incr: vi.fn() },
  counters: new Map(),
}));
vi.mock("../src/services/searchProviders.js", () => ({ search: mockSearch }));
vi.mock("../src/services/cache.service.js", () => ({
  cacheGet: cache.get,
  cacheSet: cache.set,
  counterIncrBy: cache.incr,
}));

import { config } from "../src/config/index.js";
import { logger } from "../src/utils/logger.js";
import {
  classifyDomain,
  keywordHits,
  matchedTerms,
  searchAgentReputation,
  sourceKeyFor,
} from "../src/services/osint.service.js";
import { aggregateScore, capUnsupportedScore } from "../src/services/scoring.service.js";
import { VIGOR_META, VIGOR_RESULTS } from "./fixtures/vigor.js";
import { ADAM_META, ADAM_NAME_RESULTS, ADAM_PHONE_RESULTS, ADAM_SOURCE_KEYS } from "./fixtures/adam.js";
import { FUAD_META, FUAD_NAME_RESULTS, RAZALI_META, RAZALI_NAME_RESULTS } from "./fixtures/run1.js";

const SERPER_KEY = `serperkey${"1".repeat(31)}`;
const SERPAPI_KEY = `serpapikey${"2".repeat(54)}`;
const PHONE = "012-345 6789";

const hit = (link, title, snippet) => ({ link, title, snippet });
const LOWYAT = hit("https://forum.lowyat.net/topic/123", "Rental scam warning", "Agent 012-345 6789 scammed me RM1500 deposit");
const STAR = hit("https://www.thestar.com.my/news/2026/01/01/rental", "Police probe rental scam", "Victims paid deposits to 0123456789 for units that did not exist");
const FB = hit("https://www.facebook.com/groups/1/posts/2", "Beware", "This guy +60 12-345 6789 is a penipu");
const FB2 = hit("https://m.facebook.com/story.php?id=3", "Hati-hati", "012-345 6789 kena tipu");

// Which query a search string is, from the terms only that query uses.
const kindOf = (q) =>
  q.startsWith("(") ? "phone"
    : q.includes('"agen palsu"') ? "name"
      : q.includes('"fake agent"') ? "ren"
        : "company";

/** Answer each query kind with fixed results (or throw an Error given). */
function respond(byKind) {
  mockSearch.mockImplementation(async (provider, q) => {
    const answer = byKind[kindOf(q)];
    if (answer instanceof Error) throw answer;
    return { provider, results: answer ?? [] };
  });
}

const providerError = (status, message = "failed") => Object.assign(new Error(message), { status });

const logged = () =>
  [...logger.warn.mock.calls, ...logger.info.mock.calls].map((args) => args.join(" ")).join("\n");

beforeEach(() => {
  mockSearch.mockReset();
  cache.get.mockReset().mockResolvedValue(null);
  cache.set.mockReset().mockResolvedValue(undefined);
  counters.clear();
  // A working Redis counter.
  cache.incr.mockReset().mockImplementation(async (key, by) => {
    const value = (counters.get(key) ?? 0) + by;
    counters.set(key, value);
    return value;
  });
  config.serperApiKey = SERPER_KEY;
  config.serpapiApiKey = undefined;
  config.serperDailyLimit = 80;
  config.serpapiDailyLimit = 8;
  config.osintCacheSecret = "test-secret";
  // Rules only in this file; the judge has its own suite (osintJudge.test.js).
  config.osintLlmVerify = false;
  vi.spyOn(logger, "warn").mockImplementation(() => {});
  vi.spyOn(logger, "info").mockImplementation(() => {});
});

describe("source tiers", () => {
  it("scores a Lowyat phone complaint as forum, 8 points, strong", async () => {
    respond({ phone: [LOWYAT] });
    const result = await searchAgentReputation({ phone: PHONE });

    expect(result.status).toBe("ok");
    expect(result.provider).toBe("serper");
    expect(result.points).toBe(8);
    expect(result.riskFraction).toBeCloseTo(8 / 25);
    expect(result.breakdown).toEqual({ news: 0, forum: 8, social: 0 });
    expect(result.strongHit).toBe(true);
    expect(result.evidence).toHaveLength(1);
    expect(result.evidence[0]).toMatchObject({
      domain: "forum.lowyat.net", tier: "forum", query: "phone",
    });
    expect(result.evidence[0].matched.terms).toEqual(["scam", "warning", "scammed"]);
  });

  it("scores each tier once: news + forum + two Facebook posts = 25", async () => {
    respond({ phone: [FB, STAR, LOWYAT, FB2] });
    const result = await searchAgentReputation({ phone: PHONE });

    expect(result.points).toBe(25);
    expect(result.riskFraction).toBe(1);
    expect(result.breakdown).toEqual({ news: 12, forum: 8, social: 5 });
    expect(result.evidence.map((item) => item.tier)).toEqual(["news", "forum", "social", "social"]);
  });

  it("scores a Facebook-only hit at 5, not strong, and it does not lift the band cap", async () => {
    respond({ phone: [FB] });
    const osint = await searchAgentReputation({ phone: PHONE });
    expect(osint.points).toBe(5);
    expect(osint.strongHit).toBe(false);

    const nlp = { scamProbability: 0.95, status: "ok", confidence: "high" };
    const scoring = capUnsupportedScore(aggregateScore({ nlp, osint }), {
      scamProbability: 0.95, status: "ok", redFlags: [], osint,
    });
    expect(scoring.band).toBe("MODERATE");
    expect(scoring.bandCap?.applied).toBe(true);
  });

  it("holds a name-query news hit back without the judge", async () => {
    // Scored by the judge suite; on rules alone a name could be anyone's.
    respond({
      name: [hit("https://www.nst.com.my/news/crime/1", "Fake agent held", "Ahmad Faizal, a fake agent, cheated 12 students")],
    });
    const result = await searchAgentReputation({ agentName: "Ahmad Faizal" });

    expect(result.points).toBe(0);
    expect(result.strongHit).toBe(false);
    expect(result.context[0]).toMatchObject({ tier: "news", query: "name", type: "unverified_mention" });
  });

  it("ignores unknown domains, including caller-ID sites", async () => {
    respond({
      phone: [hit("https://www.truecaller.com/search/my/0123456789", "0123456789", "Reported as scam by 40 users")],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.status).toBe("ok");
    expect(result.points).toBe(0);
    expect(result.riskFraction).toBe(0);
    expect(result.evidence).toEqual([]);
  });

  it("keeps listing-portal boilerplate as context, never evidence", async () => {
    const guru = hit(
      "https://www.propertyguru.com.my/property-listing/123",
      "Room for rent, Cheras",
      "Call 012-345 6789. Beware of scams: never pay before viewing.",
    );
    respond({ phone: [guru] });
    const result = await searchAgentReputation({ phone: PHONE });

    expect(result.points).toBe(0);
    expect(result.evidence).toEqual([]);
    expect(result.context).toHaveLength(1);
    expect(result.context[0]).toMatchObject({
      title: guru.title, link: guru.link, domain: "propertyguru.com.my", type: "listing_portal",
    });
  });

  it("does not substring-match domains", async () => {
    respond({
      phone: [
        hit("https://notx.com/a", "scam", "012-345 6789 scam"),
        hit("https://caribbean.com/b", "scam", "012-345 6789 scam"),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(0);

    expect(classifyDomain("https://notx.com/a").tier).toBe("unknown");
    expect(classifyDomain("https://caribbean.com/b").tier).toBe("unknown");
    expect(classifyDomain("https://x.com/user/1").tier).toBe("social");
    expect(classifyDomain("https://mobile.twitter.com/u").tier).toBe("social");
    expect(classifyDomain("https://forum.cari.com.my/thread-1").tier).toBe("forum");
    expect(classifyDomain("not a url").tier).toBe("unknown");
  });
});

describe("evidence test", () => {
  it("needs both the identifier and a keyword in the same result", async () => {
    respond({
      phone: [
        hit("https://forum.lowyat.net/t/1", "Selling my car", "Call 012-345 6789, good condition"),
        hit("https://forum.lowyat.net/t/2", "Rental scam in Cheras", "Agent used 019-876 5432"),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(0);
    expect(result.evidence).toEqual([]);
  });

  it("matches keywords on word start, including Malay affixed forms", async () => {
    respond({
      phone: [
        hit("https://forum.lowyat.net/t/3", "Room rental", "012-345 6789 kena scammed RM800"),
        hit("https://www.facebook.com/p/4", "Hati-hati", "saya ditipu oleh 0123456789"),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.breakdown).toEqual({ news: 0, forum: 8, social: 5 });
    expect(result.evidence.find((item) => item.tier === "forum").matched.terms).toEqual(["scammed"]);
    expect(result.evidence.find((item) => item.tier === "social").matched.terms).toEqual(["hati-hati", "ditipu"]);
  });

  it("accepts 'scampi' as known noise (documented in osint.service.js)", () => {
    expect(matchedTerms("garlic scampi recipe")).toEqual(["scampi"]);
  });

  it("attributes a link to the strongest query whose own test it passes", async () => {
    const nameOnly = hit("https://forum.lowyat.net/t/9", "Avoid this agent", "Ahmad Faizal is a scammer");
    respond({ phone: [nameOnly], name: [nameOnly] });
    const result = await searchAgentReputation({ phone: PHONE, agentName: "Ahmad Faizal" });

    // Attributed to name, not phone — and so, on rules alone, not scored.
    expect(result.evidence).toEqual([]);
    expect(result.context).toHaveLength(1);
    expect(result.context[0]).toMatchObject({ query: "name", type: "unverified_mention" });
    expect(result.strongHit).toBe(false);
    expect(result.points).toBe(0);
  });

  it("prefers the phone query when the snippet has both identifiers", async () => {
    const both = hit("https://forum.lowyat.net/t/10", "Avoid", "Ahmad Faizal 012-345 6789 is a scammer");
    respond({ phone: [both], name: [both] });
    const result = await searchAgentReputation({ phone: PHONE, agentName: "Ahmad Faizal" });
    expect(result.evidence).toHaveLength(1);
    expect(result.evidence[0].query).toBe("phone");
    expect(result.strongHit).toBe(true);
  });

  it("never matches a REN inside a phone number", async () => {
    respond({
      ren: [hit("https://forum.lowyat.net/t/11", "Fake agent", "call 0123456789, fake agent scam")],
    });
    const result = await searchAgentReputation({ phone: "019-876 5432", renNumber: "REN 12345" });
    expect(result.queries).toEqual(["phone", "ren"]);
    expect(result.points).toBe(0);
  });
});

describe("query selection", () => {
  it("skips the REN query for a digits-only REN", async () => {
    respond({});
    const result = await searchAgentReputation({ phone: PHONE, renNumber: "12345" });
    expect(mockSearch).toHaveBeenCalledTimes(1);
    expect(result.queries).toEqual(["phone"]);
  });

  it("skips the company query when one word is left after Sdn Bhd", async () => {
    respond({});
    const result = await searchAgentReputation({ phone: PHONE, company: "Maju Sdn Bhd" });
    expect(mockSearch).toHaveBeenCalledTimes(1);
    expect(result.queries).toEqual(["phone"]);
  });

  it("skips a single-word name, runs all four when every field is usable", async () => {
    respond({});
    await searchAgentReputation({ phone: PHONE, agentName: "Ahmad" });
    expect(mockSearch).toHaveBeenCalledTimes(1);

    mockSearch.mockClear();
    const result = await searchAgentReputation({
      phone: PHONE,
      agentName: "Ahmad Faizal",
      renNumber: "REN 12345",
      company: "Maju Jaya Realty Sdn Bhd",
    });
    expect(mockSearch).toHaveBeenCalledTimes(4);
    expect(result.queries).toEqual(["phone", "name", "ren", "company"]);
    const sent = mockSearch.mock.calls.map(([, q]) => q);
    expect(sent).toContain('("012-345 6789" OR "0123456789" OR "+60123456789") scam OR penipu OR penipuan OR tipu');
    expect(sent).toContain('"Ahmad Faizal" scam OR penipu OR "agen palsu" OR fraud property');
    expect(sent).toContain('"REN 12345" scam OR penipu OR "fake agent" OR penipuan');
    expect(sent).toContain('"Maju Jaya Realty Sdn Bhd" scam OR penipu OR fraud OR "syarikat tipu" property Malaysia');
  });
});

describe("cache", () => {
  it("keys by HMAC: no raw phone, and the key changes with the secret", async () => {
    respond({});
    await searchAgentReputation({ phone: PHONE });
    const first = cache.get.mock.calls[0][0];
    expect(first).toMatch(/^osint:v3:v2:rules:[0-9a-f]{64}$/);
    expect(first).not.toContain("123456789");

    config.osintCacheSecret = "another-secret";
    await searchAgentReputation({ phone: PHONE });
    expect(cache.get.mock.calls[1][0]).not.toBe(first);
  });

  it("serves a cached result without searching", async () => {
    cache.get.mockResolvedValue({ status: "ok", provider: "serper", points: 8, riskFraction: 0.32 });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.cached).toBe(true);
    expect(result.points).toBe(8);
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("caches a full success for 24h and a partial failure for 1h", async () => {
    respond({ phone: [LOWYAT] });
    await searchAgentReputation({ phone: PHONE });
    expect(cache.set.mock.calls[0][2]).toBe(24 * 60 * 60);

    respond({ phone: providerError(500), name: [] });
    const partial = await searchAgentReputation({ phone: PHONE, agentName: "Ahmad Faizal" });
    expect(partial.status).toBe("ok");
    expect(partial.failedQueries).toBe(1);
    expect(cache.set.mock.calls[1][2]).toBe(60 * 60);
  });

  it("never caches a complete failure", async () => {
    respond({ phone: providerError(500) });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.status).toBe("search_failed");
    expect(result.riskFraction).toBeNull();
    expect(result.provider).toBe("serper");
    expect(cache.set).not.toHaveBeenCalled();
  });
});

describe("quota", () => {
  it("returns quota_exceeded without searching", async () => {
    config.serperDailyLimit = 0;
    respond({});
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.status).toBe("quota_exceeded");
    expect(result.riskFraction).toBeNull();
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("enforces the limit in memory when Redis is down", async () => {
    cache.incr.mockResolvedValue(null);
    config.serperDailyLimit = 1;
    respond({});

    expect((await searchAgentReputation({ phone: PHONE })).status).toBe("ok");
    const second = await searchAgentReputation({ phone: "019-876 5432" });
    expect(second.status).toBe("quota_exceeded");
    expect(mockSearch).toHaveBeenCalledTimes(1);
  });

  it("gives back a reservation that went over the limit", async () => {
    config.serperDailyLimit = 1;
    respond({});
    await searchAgentReputation({ phone: PHONE, agentName: "Ahmad Faizal" }); // needs 2
    const [[key]] = cache.incr.mock.calls;
    expect(counters.get(key)).toBe(0);
  });
});

describe("provider selection", () => {
  beforeEach(() => {
    config.serpapiApiKey = SERPAPI_KEY;
  });

  it("falls back to SerpApi when every Serper query fails", async () => {
    mockSearch.mockImplementation(async (provider) => {
      if (provider === "serper") throw providerError(429);
      return { provider, results: [LOWYAT] };
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.status).toBe("ok");
    expect(result.provider).toBe("serpapi");
    expect(result.points).toBe(8);
    expect(mockSearch.mock.calls.map(([provider]) => provider)).toEqual(["serper", "serpapi"]);
  });

  it("does not fall back on a partial Serper failure", async () => {
    mockSearch.mockImplementation(async (provider, q) => {
      if (kindOf(q) === "phone") throw providerError(500);
      return { provider, results: [] };
    });
    const result = await searchAgentReputation({ phone: PHONE, agentName: "Ahmad Faizal" });
    expect(result.status).toBe("ok");
    expect(result.provider).toBe("serper");
    expect(mockSearch.mock.calls.every(([provider]) => provider === "serper")).toBe(true);
  });

  it("uses SerpApi directly when Serper is over quota", async () => {
    config.serperDailyLimit = 0;
    respond({ phone: [LOWYAT] });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.provider).toBe("serpapi");
    expect(mockSearch.mock.calls.every(([provider]) => provider === "serpapi")).toBe(true);
  });

  it("uses SerpApi alone when it is the only key", async () => {
    config.serperApiKey = "your_serper_dev_key";
    respond({ phone: [LOWYAT] });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.provider).toBe("serpapi");
  });

  it("reports not_configured when neither key is real", async () => {
    config.serperApiKey = "your_serper_dev_key";
    config.serpapiApiKey = undefined;
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.status).toBe("not_configured");
    expect(result.riskFraction).toBeNull();
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("logs no API key and no raw phone number", async () => {
    mockSearch.mockImplementation(async (provider) => {
      throw providerError(401, `${provider} failed api_key=${SERPAPI_KEY} key ${SERPER_KEY}`);
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.status).toBe("search_failed");
    expect(result.provider).toBe("serpapi");

    const lines = logged();
    expect(lines).toContain("status=401");
    expect(lines).not.toContain(SERPAPI_KEY);
    expect(lines).not.toContain(SERPER_KEY);
    expect(lines).not.toContain("api_key");
    expect(lines).not.toContain("0123456789");
  });
});

describe("exclusion from the score", () => {
  it("excludes the signal when there is nothing to search on", async () => {
    for (const meta of [null, {}, { agentName: "Ahmad" }, { renNumber: "REN 12345" }]) {
      const osint = await searchAgentReputation(meta);
      expect(osint.status).toBe("no_identifier");
      expect(osint.riskFraction).toBeNull();
      expect(aggregateScore({ osint }).excluded).toContain("osint");
    }
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("excludes the signal when no provider is configured", async () => {
    config.serperApiKey = undefined;
    const osint = await searchAgentReputation({ phone: PHONE });
    expect(osint.status).toBe("not_configured");
    expect(aggregateScore({ osint }).excluded).toContain("osint");
  });
});

// ---------------------------------------------------------------------------
// Layer 1 rules (the judge is off in this file).
// ---------------------------------------------------------------------------

describe("layer 1: normalisation and negation", () => {
  it("matches Unicode bold text and digits after NFKC", async () => {
    respond({
      phone: [hit("https://forum.lowyat.net/t/20", "𝐒𝐂𝐀𝐌 𝐀𝐋𝐄𝐑𝐓", "agent 𝟎𝟏𝟐-𝟑𝟒𝟓 𝟔𝟕𝟖𝟗 took my deposit")],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(8);
    expect(result.evidence[0].matched.terms).toEqual(["scam"]);
    expect(result.evidence[0].title).toBe("𝐒𝐂𝐀𝐌 𝐀𝐋𝐄𝐑𝐓"); // shown as the page has it
  });

  it("ignores a keyword with a negation or generic cue in the 3 tokens before it", () => {
    const cueOf = (text) => keywordHits(text).ignored.map((item) => item.cue);
    expect(cueOf("this is not a scam")).toEqual(["not"]);
    expect(cueOf("bukan scam")).toEqual(["bukan"]);
    expect(cueOf("anti-scam tips")).toEqual(["anti"]);
    expect(cueOf("elakkan risiko scam")).toEqual(["elakkan"]);
    expect(cueOf("National Scam Response Centre 997")).toEqual(["national"]);
    expect(cueOf("report it to the scam centre")).toEqual(["scam centre"]);
    expect(cueOf("call 997 scam hotline")).toEqual(["997"]);
    expect(keywordHits("this is not a scam").terms).toEqual([]);
  });

  it("only looks 3 tokens back", () => {
    expect(keywordHits("bukan saya kata dia itu scammer").terms).toEqual(["scammer"]);
  });

  it("does not treat Malay 'no' (number) as a negation", () => {
    expect(keywordHits("no ni scammer").terms).toEqual(["scammer"]);
    expect(keywordHits("no 0123456789 penipu").terms).toEqual(["penipu"]);
    expect(keywordHits("no tel dia tipu").terms).toEqual(["tipu"]);
    expect(keywordHits("no scam here").ignored).toEqual([{ term: "scam", cue: "no" }]);
  });

  it("counts hati-hati, hati hati and awas", () => {
    expect(keywordHits("Hati-hati dengan agent ni").terms).toEqual(["hati-hati"]);
    expect(keywordHits("hati hati semua").terms).toEqual(["hati hati"]);
    expect(keywordHits("Awas! agent palsu").terms).toEqual(["awas"]);
    expect(keywordHits("sila berhati-hati").terms).toEqual(["berhati-hati"]);
  });

  it("puts a result whose every keyword is negated into context", async () => {
    respond({
      phone: [hit("https://forum.lowyat.net/t/21", "Rumah sewa", "Call 012-345 6789, elak risiko scam")],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(0);
    expect(result.context[0]).toMatchObject({ type: "generic_mention" });
    expect(result.context[0].matched.ignored).toEqual([{ term: "scam", cue: "elak" }]);
  });

  it("scores the judge prompt's Lowyat example on rules alone", async () => {
    respond({
      phone: [hit("https://forum.lowyat.net/t/22", "Agent lari", "Agent guna no 012-345 6789 ambil deposit RM2k lepas tu block saya. Hati-hati!")],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(8);
    expect(result.evidence[0].matched.terms).toEqual(["hati-hati"]);
  });
});

describe("layer 1: domains and the URL", () => {
  it("adds Threads to the social tier", () => {
    expect(classifyDomain("https://www.threads.net/@agent/post/1").tier).toBe("social");
    expect(classifyDomain("https://www.threads.com/@agent/post/1").tier).toBe("social");
  });

  it("never uses the URL for identifier or keyword evidence", async () => {
    respond({
      phone: [
        hit("https://forum.lowyat.net/topic/0123456789-scam-alert", "For sale", "Selling my car"),
        hit("https://forum.lowyat.net/topic/scam-alert", "Viewing", "call 012-345 6789 for viewing"),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(0);
    expect(result.evidence).toEqual([]);
    expect(result.context).toEqual([]);
  });
});

describe("layer 1: company hits and impersonation notices", () => {
  const COMPANY = "Maju Jaya Realty Sdn Bhd";

  it("keeps social-media company hits as context; forum ones wait for the judge", async () => {
    respond({
      company: [
        hit("https://www.instagram.com/p/1", "Maju Jaya Realty", "Maju Jaya Realty scam?"),
        hit("https://forum.lowyat.net/t/23", "Avoid", "Maju Jaya Realty Sdn Bhd agent tipu deposit"),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE, company: COMPANY });
    expect(result.points).toBe(0);
    expect(result.evidence).toEqual([]);
    expect(result.context.map((item) => item.type)).toEqual(["social_mention", "unverified_mention"]);
  });

  it("turns a company's impersonation notices into one warning listing every link", async () => {
    respond({
      company: [
        hit("https://www.facebook.com/maju/posts/1", "Notice", "Maju Jaya Realty: beware of scammers impersonating our agents"),
        hit("https://www.facebook.com/maju/posts/2", "Amaran", "Maju Jaya Realty tiada kaitan dengan penipu ini"),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE, company: COMPANY });
    expect(result.points).toBe(0);
    expect(result.context.map((item) => item.type)).toEqual(["impersonation_notice", "impersonation_notice"]);
    expect(result.warnings).toEqual([{
      type: "impersonation_notice",
      scope: "company",
      company: COMPANY,
      links: ["https://www.facebook.com/maju/posts/1", "https://www.facebook.com/maju/posts/2"],
      en: expect.stringMatching(/^This company has publicly warned/),
      ms: expect.stringMatching(/^Syarikat ini telah memberi amaran awam/),
    }]);
  });

  it("warns about this agent personally when the notice is about their REN", async () => {
    respond({
      ren: [hit("https://www.facebook.com/p/9", "Notice", "Someone is impersonating REN 12345, beware of this scam")],
    });
    const result = await searchAgentReputation({ phone: PHONE, renNumber: "REN 12345" });
    expect(result.warnings).toHaveLength(1);
    expect(result.warnings[0]).toMatchObject({ scope: "agent", company: null });
    expect(result.warnings[0].en).toMatch(/^A public notice warns that scammers are pretending to be this agent/);
    expect(result.warnings[0].ms).toMatch(/^Terdapat notis awam bahawa penipu menyamar sebagai ejen ini/);
  });

  it("does not treat impersonation words on a phone or name hit as a notice", async () => {
    // Malay news describes the scammer this way; without a judge it is held
    // back as context, with no points and no warning.
    respond({
      phone: [hit("https://www.hmetro.com.my/mutakhir/1", "Ejen palsu ditahan", "Lelaki menyamar ejen hartanah ditahan selepas tipu 8 penyewa, guna no 012-345 6789")],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.points).toBe(0);
    expect(result.warnings).toEqual([]);
    expect(result.context).toEqual([expect.objectContaining({ type: "impersonation_mention", query: "phone" })]);
  });
});

describe("Vigor Properties regression (rules only)", () => {
  it("scores the four real false positives at 0 with one warning", async () => {
    respond({ company: VIGOR_RESULTS });
    const result = await searchAgentReputation(VIGOR_META);

    expect(result.status).toBe("ok");
    expect(result.verifier).toBe("rules_only");
    expect(result.verifierProvider).toBeNull();
    expect(result.points).toBe(0);
    expect(result.riskFraction).toBe(0);
    expect(result.evidence).toEqual([]);
    expect(result.context.map((item) => item.type)).toEqual([
      "generic_mention", "impersonation_notice", "social_mention", "social_mention",
    ]);
    expect(result.warnings).toEqual([
      expect.objectContaining({
        type: "impersonation_notice",
        company: "Vigor Properties Sdn Bhd",
        links: [VIGOR_RESULTS[1].link],
      }),
    ]);
  });

  it("holds a real complaint about the company back until the judge confirms it", async () => {
    // The judge suite's positive control scores this at forum 8.
    respond({
      company: [hit("https://forum.lowyat.net/topic/vigor-complaint", "Vigor", "Vigor Properties Sdn Bhd agent tipu deposit saya")],
    });
    const result = await searchAgentReputation(VIGOR_META);
    expect(result.points).toBe(0);
    expect(result.context[0]).toMatchObject({ tier: "forum", query: "company", type: "unverified_mention" });
    expect(result.strongHit).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Social corroboration (rules only here; the judge suite covers it with the
// judge on).
// ---------------------------------------------------------------------------

describe("source keys", () => {
  it("collapses the URL forms of one group or account into one key", () => {
    expect(sourceKeyFor("https://www.facebook.com/groups/1107732539961661/posts/2337325683669001/")).toBe("facebook:group:1107732539961661");
    expect(sourceKeyFor("https://m.facebook.com/groups/1107732539961661/permalink/2298526420882261/")).toBe("facebook:group:1107732539961661");
    expect(sourceKeyFor("https://web.facebook.com/officialefcc/posts/1452466210249911/")).toBe("facebook:officialefcc");
    expect(sourceKeyFor("https://www.threads.com/@lizaaajeeelaaa/post/Dca2GDekpHy/media")).toBe("threads:lizaaajeeelaaa");
    expect(sourceKeyFor("https://www.threads.net/@LizaaaJeeelaaa/post/1")).toBe("threads:lizaaajeeelaaa");
    expect(sourceKeyFor("https://www.tiktok.com/@agentscam/video/1")).toBe("tiktok.com:agentscam");
    expect(sourceKeyFor("https://www.instagram.com/agent_ali/")).toBe("instagram.com:agent_ali");
    expect(sourceKeyFor("https://forum.lowyat.net/topic/123")).toBe("forum.lowyat.net");
    expect(sourceKeyFor("not a url")).toBeNull();
  });

  it("treats x.com and twitter.com as one account", () => {
    expect(sourceKeyFor("https://x.com/MA_and_A")).toBe("x:ma_and_a");
    expect(sourceKeyFor("https://mobile.twitter.com/ma_and_a/status/1")).toBe("x:ma_and_a");
  });

  it("gives URLs without an account one shared key per form (never over-counts)", () => {
    expect(sourceKeyFor("https://www.instagram.com/reel/DZsN7foTkQJ/")).toBe("instagram.com:reel");
    expect(sourceKeyFor("https://www.instagram.com/reel/Dbxpyr3PXT2/")).toBe("instagram.com:reel");
    expect(sourceKeyFor("https://m.facebook.com/story.php?id=3")).toBe("facebook:story.php");
  });
});

describe("social corroboration", () => {
  const groupPost = (group, post) => hit(
    `https://www.facebook.com/groups/${group}/posts/${post}/`,
    "Homestay",
    "Memang betul kami kena scam ... 012-345 6789. Semoga dilaknat scammer2 ni",
  );

  it("golden case #2: a scam number in 3 groups and on Threads is a strong hit (rules only)", async () => {
    respond({ phone: ADAM_PHONE_RESULTS, name: ADAM_NAME_RESULTS });
    const result = await searchAgentReputation(ADAM_META);

    expect(result.verifier).toBe("rules_only");
    expect(result.points).toBe(5);
    expect(result.breakdown).toEqual({ news: 0, forum: 0, social: 5 });
    expect(result.strongHit).toBe(true);
    expect(result.strongHitReason).toBe("social_corroboration");
    expect(result.corroboration).toEqual({ sources: 4, threshold: 3, keys: ADAM_SOURCE_KEYS });
    expect(result.evidence).toHaveLength(8);
    expect(result.evidence.every((item) => item.query === "phone")).toBe(true);
    // The four "Muhammad Adam" hits: a namesake's complaint, a law firm, a
    // government group, a fraud trial. Held back, 0 points.
    expect(result.context).toHaveLength(4);
    expect(result.context.every((item) => item.query === "name" && item.type === "unverified_mention")).toBe(true);
  });

  it("counts five posts in one Facebook group as one source", async () => {
    respond({ phone: [1, 2, 3, 4, 5].map((post) => groupPost("1107732539961661", post)) });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.corroboration).toEqual({ sources: 1, threshold: 3, keys: ["facebook:group:1107732539961661"] });
    expect(result.strongHit).toBe(false);
    expect(result.strongHitReason).toBeNull();
    expect(result.points).toBe(5);
  });

  it("needs 3 sources: 2 are not enough", async () => {
    respond({ phone: [groupPost("111", 1), groupPost("222", 1)] });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.corroboration.sources).toBe(2);
    expect(result.strongHit).toBe(false);
  });

  it("counts the same account on x.com and twitter.com once", async () => {
    respond({
      phone: [
        hit("https://x.com/victim_one/status/1", "Scam", "012-345 6789 scammed me"),
        hit("https://twitter.com/victim_one/status/1", "Scam", "012-345 6789 scammed me"),
        groupPost("111", 1),
      ],
    });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.corroboration.keys).toEqual(["x:victim_one", "facebook:group:111"]);
    expect(result.strongHit).toBe(false);
  });

  it("prefers news_or_forum as the reason when both rules apply", async () => {
    respond({ phone: [LOWYAT, groupPost("111", 1), groupPost("222", 1), groupPost("333", 1)] });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.strongHitReason).toBe("news_or_forum");
    expect(result.corroboration.sources).toBe(3);
    expect(result.evidence.find((item) => item.tier === "forum").sourceKey).toBe("forum.lowyat.net");
  });
});

// ---------------------------------------------------------------------------
// Fixes from the first 10-case run (2026-10-10), on its real snippets.
// ---------------------------------------------------------------------------

describe("run 1 fixes", () => {
  it("case 3: files a post by the phone it contains, whichever query found it", async () => {
    respond({ name: FUAD_NAME_RESULTS });
    const result = await searchAgentReputation(FUAD_META);

    expect(result.evidence).toHaveLength(2);
    expect(result.evidence.every((item) => item.query === "phone" && item.foundBy === "name")).toBe(true);
    expect(result.corroboration.keys).toEqual(["facebook:group:1221989615410645", "facebook:pdrmsiaofficial"]);
    expect(result.points).toBe(5);
    expect(result.strongHit).toBe(false); // 2 sources, 3 needed
  });

  it("case 3: the title's last word no longer negates the snippet's first", async () => {
    respond({ name: [FUAD_NAME_RESULTS[1]] });
    const result = await searchAgentReputation(FUAD_META);

    const pdrm = result.evidence.find((item) => item.domain === "facebook.com");
    expect(pdrm.matched).toEqual({ terms: ["penipuan"], ignored: [] });
    expect(result.context).toEqual([]);
  });

  it("does not read a phone number across the title/snippet join", async () => {
    respond({ phone: [hit("https://forum.lowyat.net/t/30", "Call 012", "345 6789 scam")] });
    const result = await searchAgentReputation({ phone: PHONE });
    expect(result.evidence).toEqual([]);
  });

  it("still files a post under the name when the phone is not in it", async () => {
    respond({ phone: [hit("https://forum.lowyat.net/t/31", "Avoid", "Ahmad Faizal is a scammer")] });
    const result = await searchAgentReputation({ phone: PHONE, agentName: "Ahmad Faizal" });
    expect(result.context[0]).toMatchObject({ query: "name", foundBy: "phone", type: "unverified_mention" });
  });

  it("case 7: a name-only match scores nothing without the judge", async () => {
    respond({ name: RAZALI_NAME_RESULTS });
    const result = await searchAgentReputation(RAZALI_META);

    expect(result.points).toBe(0);
    expect(result.evidence).toEqual([]);
    expect(result.context).toEqual([expect.objectContaining({ query: "name", type: "unverified_mention" })]);
  });
});
