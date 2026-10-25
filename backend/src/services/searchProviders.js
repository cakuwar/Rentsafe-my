// Web-search adapters for the OSINT module. Each runs one query and returns
// { provider, results: [{ title, link, snippet }] }, so osint.service never
// sees a provider's own response format.
//
// Errors are rebuilt from scratch, never rethrown: SerpApi takes its key as a
// URL parameter, and an axios error carries the whole request (URL, headers)
// in error.config — logging one would publish the key.
import axios from "axios";
import { config } from "../config/index.js";
import { redactSecrets } from "../utils/keys.js";

export { redactSecrets };

const TIMEOUT_MS = 10_000;

export class SearchProviderError extends Error {
  constructor(provider, status, detail) {
    const code = status ? ` (HTTP ${status})` : "";
    super(redactSecrets(`${provider} search failed${code}${detail ? `: ${detail}` : ""}`));
    this.name = "SearchProviderError";
    this.provider = provider;
    this.status = status ?? null;
  }
}

const ADAPTERS = {
  serper: {
    request: (q) =>
      axios.post(
        "https://google.serper.dev/search",
        { q, gl: "my", hl: "en", num: 10 },
        {
          headers: { "X-API-KEY": config.serperApiKey, "Content-Type": "application/json" },
          timeout: TIMEOUT_MS,
        },
      ),
    results: (data) => data.organic,
    isEmptyNotice: () => false,
  },
  serpapi: {
    request: (q) =>
      axios.get("https://serpapi.com/search.json", {
        params: {
          engine: "google",
          q,
          gl: "my",
          hl: "en",
          google_domain: "google.com.my",
          num: 10,
          api_key: config.serpapiApiKey,
        },
        timeout: TIMEOUT_MS,
      }),
    results: (data) => data.organic_results,
    // SerpApi reports a search with no results through the `error` field
    // ("Google hasn't returned any results for this query.") on a successful
    // search. That is an answer — nothing was found — not a failure; treating
    // it as one would turn every clean phone number into search_failed.
    isEmptyNotice: (data) =>
      data.search_metadata?.status === "Success" &&
      /hasn'?t returned any results/i.test(String(data.error)),
  },
};

export const PROVIDER_NAMES = Object.keys(ADAPTERS);

const toResult = (item) => ({
  title: typeof item?.title === "string" ? item.title : "",
  link: typeof item?.link === "string" ? item.link : "",
  snippet: typeof item?.snippet === "string" ? item.snippet : "",
});

/**
 * search(provider, q) -> { provider, results: [{ title, link, snippet }] }
 * Throws SearchProviderError on a network error (status null), a non-2xx
 * response, or a body carrying an `error` field.
 */
export async function search(provider, q) {
  const adapter = ADAPTERS[provider];
  if (!adapter) throw new SearchProviderError(provider, null, "unknown provider");

  let response;
  try {
    response = await adapter.request(q);
  } catch (error) {
    // Only the status and the error code survive; error.message is not
    // trusted to be free of the request URL.
    const status = error?.response?.status ?? null;
    throw new SearchProviderError(provider, status, status ? null : error?.code ?? "network error");
  }

  if (response.status < 200 || response.status >= 300) {
    throw new SearchProviderError(provider, response.status);
  }
  const data = response.data ?? {};
  if (data.error) {
    if (adapter.isEmptyNotice(data)) return { provider, results: [] };
    throw new SearchProviderError(provider, response.status, String(data.error));
  }
  const items = adapter.results(data);
  return { provider, results: Array.isArray(items) ? items.map(toResult) : [] };
}
