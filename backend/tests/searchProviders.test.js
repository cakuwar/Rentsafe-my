// Search adapters: response mapping, error handling, and keeping API keys out
// of every error message.
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost } = vi.hoisted(() => ({ mockGet: vi.fn(), mockPost: vi.fn() }));
vi.mock("axios", () => ({ default: { get: mockGet, post: mockPost } }));

import { config } from "../src/config/index.js";
import { redactSecrets, search, SearchProviderError } from "../src/services/searchProviders.js";

const SERPER_KEY = `serperkey${"1".repeat(31)}`;
const SERPAPI_KEY = `serpapikey${"2".repeat(54)}`;

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  config.serperApiKey = SERPER_KEY;
  config.serpapiApiKey = SERPAPI_KEY;
});

async function caught(promise) {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected a rejection");
}

describe("serpapi adapter", () => {
  it("maps organic_results and fills a missing snippet with an empty string", async () => {
    mockGet.mockResolvedValue({
      status: 200,
      data: {
        search_metadata: { status: "Success" },
        organic_results: [
          { title: "Scam alert", link: "https://forum.lowyat.net/t/1", snippet: "012-345 6789 scam", position: 1 },
          { title: "No snippet", link: "https://example.com/2" },
        ],
      },
    });

    const result = await search("serpapi", "q");

    expect(result).toEqual({
      provider: "serpapi",
      results: [
        { title: "Scam alert", link: "https://forum.lowyat.net/t/1", snippet: "012-345 6789 scam" },
        { title: "No snippet", link: "https://example.com/2", snippet: "" },
      ],
    });
    const [url, options] = mockGet.mock.calls[0];
    expect(url).toBe("https://serpapi.com/search.json");
    expect(options.params).toMatchObject({
      engine: "google", q: "q", gl: "my", hl: "en", google_domain: "google.com.my", num: 10,
    });
    expect(options.timeout).toBe(10_000);
  });

  it("treats SerpApi's 'no results' notice as an empty answer, not a failure", async () => {
    mockGet.mockResolvedValue({
      status: 200,
      data: {
        search_metadata: { status: "Success" },
        error: "Google hasn't returned any results for this query.",
      },
    });
    await expect(search("serpapi", "q")).resolves.toEqual({ provider: "serpapi", results: [] });
  });

  it("throws on a body carrying an error, without the key in the message", async () => {
    mockGet.mockResolvedValue({
      status: 200,
      data: { error: `Invalid API key: api_key=${SERPAPI_KEY}` },
    });
    const error = await caught(search("serpapi", "q"));
    expect(error).toBeInstanceOf(SearchProviderError);
    expect(error.message).not.toContain(SERPAPI_KEY);
  });
});

describe("serper adapter", () => {
  it("maps organic", async () => {
    mockPost.mockResolvedValue({
      status: 200,
      data: { organic: [{ title: "t", link: "https://x.com/a", snippet: "s", position: 1 }] },
    });
    const result = await search("serper", "q");
    expect(result).toEqual({ provider: "serper", results: [{ title: "t", link: "https://x.com/a", snippet: "s" }] });
    const [url, body, options] = mockPost.mock.calls[0];
    expect(url).toBe("https://google.serper.dev/search");
    expect(body).toEqual({ q: "q", gl: "my", hl: "en", num: 10 });
    expect(options.headers["X-API-KEY"]).toBe(SERPER_KEY);
  });
});

describe("errors", () => {
  it("throws SearchProviderError with the HTTP status on a non-2xx response", async () => {
    // What axios rejects with: the request config, key included, rides along.
    mockGet.mockRejectedValue({
      message: `Request failed with status code 401 https://serpapi.com/search.json?api_key=${SERPAPI_KEY}`,
      response: { status: 401 },
      config: { params: { api_key: SERPAPI_KEY } },
    });
    const error = await caught(search("serpapi", "q"));
    expect(error).toBeInstanceOf(SearchProviderError);
    expect(error.status).toBe(401);
    expect(error.provider).toBe("serpapi");
    expect(JSON.stringify({ ...error, message: error.message })).not.toContain(SERPAPI_KEY);
    expect(error.config).toBeUndefined();
  });

  it("reports a network failure with a null status", async () => {
    mockPost.mockRejectedValue({ code: "ECONNABORTED", config: { headers: { "X-API-KEY": SERPER_KEY } } });
    const error = await caught(search("serper", "q"));
    expect(error.status).toBeNull();
    expect(error.message).not.toContain(SERPER_KEY);
  });

  it("redacts api_key parameters and both configured keys", () => {
    const text = `GET ?q=x&api_key=${SERPAPI_KEY}&num=10 header ${SERPER_KEY}`;
    const redacted = redactSecrets(text);
    expect(redacted).not.toContain(SERPAPI_KEY);
    expect(redacted).not.toContain(SERPER_KEY);
    expect(redacted).toContain("api_key=[redacted]");
  });
});
