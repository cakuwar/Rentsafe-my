# API specification

## Backend (Node/Express) — base `http://localhost:4000/api`

Interactive docs (Swagger UI): `http://localhost:4000/api/docs` — spec in
`backend/src/docs/openapi.js`; keep it in step with this file.

### `GET /health`
Liveness check. → `{ status, service, time }`

### `POST /analyze`
Analyse a text listing.

Request:
```json
{
  "text": "Renter: ...\nOwner: ...",
  "language": "auto",
  "agent": { "name": "Ahmad Faizal", "phone": "012-345 6789", "ren": "REN 12345", "company": "Maju Jaya Realty Sdn Bhd" },
  "property": { "price": 1200, "area": "Wangsa Maju", "propertyType": "condo", "bedrooms": 2 }
}
```
`language`: `"auto" | "ms" | "en"`. `text` must be at least 20 characters —
shorter input cannot be judged and is rejected with 400 rather than scored.

`agent` is optional, and so is each field in it (an empty string counts as not
given). A field left blank falls back to what can be parsed from `text` (phone,
REN, a `… Sdn Bhd` company; never a name). The form matters: in a WhatsApp chat
the other party's number is usually in the header, not in any message. `phone`
must be a Malaysian mobile number or the request is rejected with 400. These
details drive the OSINT search — see [OSINT](#osint--evidenceosint) below.

`property` is the **Listing details form** — `price`, `area`, `propertyType`
(`condo | apartment | flat | landed | room | studio`), `bedrooms` and `roomType`.
It is the only source of the rent: nothing is parsed from `text`. Absent or
partial, the price check reports `missing_input` and price is left out of the
score — no error. See [the form contract](#the-listing-details-form).

Response:
```json
{
  "listingId": "uuid",
  "sourceType": "text",
  "riskScore": 60,
  "maxPossibleScore": 60,
  "riskBand": "HIGH",
  "riskColour": "orange",
  "bandCap": null,
  "modelProbability": 0.9853,
  "components": {
    "nlp":   { "points": 60, "max": 60, "included": true },
    "osint": { "points": 0,  "max": 0,  "included": false },
    "price": { "points": 0,  "max": 0,  "included": false }
  },
  "excludedSignals": ["osint", "price"],
  "nlpStatus": "ok",
  "nlpConfidence": "high",
  "message": null,
  "evidenceSupport": "corroborated",
  "narrative": null,
  "metadata": null,
  "evidence": { "redFlags": [], "details": [], "patterns": [],
                "legitSignals": [], "osint": null, "price": null }
}
```

**`riskScore` alone is not enough to render.** Three fields decide what the user
should be told:

| field | meaning |
|---|---|
| `nlpStatus` | `ok`, `insufficient_context` or `model_unavailable` |
| `maxPossibleScore` | the ceiling given which signals were usable; below 100 means a thinner claim |
| `message` | `{ en, ms }` to show the user, or `null` |
| `evidenceSupport` | whether layer 1's evidence agrees with the model — see below |
| `bandCap` | set when a high model score had no red flag behind it and the band was held at MODERATE — see below |

When layer 2 cannot judge, it is **excluded from the score** rather than counted
as 0.5, and `riskBand` is **`UNKNOWN`** (grey), not `LOW`:

```json
{
  "riskScore": null,
  "maxPossibleScore": 0,
  "riskBand": "UNKNOWN",
  "riskColour": "grey",
  "nlpStatus": "insufficient_context",
  "nlpConfidence": "insufficient",
  "excludedSignals": ["nlp", "osint", "price"],
  "message": {
    "en": "Send more of the conversation — there is not enough here to judge.",
    "ms": "Hantar lagi perbualan — tidak cukup maklumat untuk menilai."
  }
}
```

**`riskScore` is `null`, not `0`.** Zero on a 0-100 scale reads as "safe", which
is the opposite of what the service determined. `null` forces the client to
handle the case rather than mis-render it: show `message`, not a number.

Note the guard is one-directional. A conversation short enough to be guarded but
which the model scores *high* comes back with `nlpStatus: "ok"`,
`nlpConfidence: "insufficient"` and a normal `riskScore` — a scam obvious from
four messages is still reported. Only low scores on short input become
`UNKNOWN`.

#### `evidenceSupport` — does the evidence back the number?

The model's probability and layer 1's red flags are computed independently, so
they can disagree. The model is known to be wrong in one direction on real input
(it scored a real legitimate conversation 0.9995), so disagreement is reported
rather than hidden. Critical and high severity count as *strong* flags.

| model says | layer 1 found | `evidenceSupport` | `message` |
|---|---|---|---|
| scam (≥ 0.5) | a strong flag | `corroborated` | `null` |
| scam | only weaker flags | `partial` | `null` |
| scam | nothing | `none` | "The model rated this as risky, but no specific scam tactic was found. Verify the landlord and the unit before paying anything." — and the band is capped, below |
| not scam | a strong flag | `contradicted` | "rated lower risk but contains warning signs — treat with caution" |
| not scam | only weaker flags | `partial` | `null` |
| not scam | nothing | `consistent` | `null` |
| — (`nlpStatus` not `ok`) | — | `not_scored` | the guard's message |

`evidenceSupport` itself only reports. When both apply, the guard's "send more
of the conversation" message takes precedence.

#### `bandCap` — a high score with no red flag is held at MODERATE

Decided 2026-09-28; it reverses the earlier rule that layer 1 never affects the
result (`docs/MODEL_COMPARISON.md` §14.11). The motivating case: a real,
legitimate iBilik agent chat, through OCR, scored 0.94 by the model with no red
flag at all and three legitimacy signals.

| condition | band | `riskScore` | `bandCap` |
|---|---|---|---|
| model ≥ 0.5, `nlpStatus` `ok`, **no red flags**, **no strong OSINT hit**, score above 49 | **MODERATE** | **49** (the top of MODERATE) | `{ applied: true, reason: "no_red_flags", uncappedScore, uncappedBand }` |
| model ≥ 0.5, no red flags, score already ≤ 49 | unchanged (MODERATE) | unchanged | `null` |
| model ≥ 0.5, any red flag | unchanged — HIGH / CRITICAL possible | unchanged | `null` |
| model ≥ 0.5, no red flags, `evidence.osint.strongHit` | unchanged — HIGH / CRITICAL possible | unchanged | `null` |
| model < 0.5 | unchanged | unchanged | `null` |
| `nlpStatus` not `ok` | UNKNOWN, unchanged | `null` | `null` |

**How `riskScore` behaves under the cap.** It is lowered to 49 only when it was
above 49, so the score always lies inside its band's range (MODERATE is
25–49). The score before the cap is `bandCap.uncappedScore`, and the band before
it `bandCap.uncappedBand`. `components` are *not* capped — they are each
signal's own contribution, so under a cap they sum to more than `riskScore`;
that difference is exactly what `bandCap` explains.

**It never lowers a result below MODERATE.** A model score ≥ 0.5 is at least 30
points on its own, and the cap only removes bands above MODERATE.

**Layer 2 is untouched.** `modelProbability` is the model's output as served,
never capped; the NLP service's `scam_probability` and `model_probability` are
unchanged.

**Legitimacy signals play no part.** They can be faked, and every one measured
fires more often on scams than on honest chats. They are returned in
`evidence.legitSignals` as context only; they never lower the band.

**A strong OSINT hit lifts the cap** (decided 2026-10-04). The agent's phone
number or REN in scam reports is evidence independent of the chat text, so
HIGH / CRITICAL is allowed even with no red flag. The rule is deliberately
narrow — it is `evidence.osint.strongHit`, with the reason in
`evidence.osint.strongHitReason`:

| OSINT found | adds points | lifts the cap |
|---|---|---|
| phone / REN complaint on a news or forum source | yes | **yes** (`news_or_forum`) |
| phone / REN complaints from **3+ distinct social sources** | yes | **yes** (`social_corroboration`) |
| phone / REN on 1–2 social sources (any number of posts) | yes | no — unverified posts |
| company, any source | yes (judge only) | no |
| name only (no phone / REN in the same post) | **no** — shown as `name_only_match` | no — names are shared; the hit may be someone else |

**A name-only match never scores** (decided 2026-10-11). The judge is shown just
the name, so it cannot tell the agent from a namesake: in the first 10-case run
it rated "Syed Ahmad Razali bin Wan Yusof … SCAMMER jugak" a complaint at 0.9,
with the agent's phone nowhere in the post. Such hits are listed as
`name_only_match` — for the UI, "same name reported, may be a different
person". A post that also carries the phone or REN is attributed to that, and
scores normally.

Corroboration was added for a real scam number reported in three Facebook
groups and on Threads, but on no news site or forum.

A price anomaly — including the minimum-rent floor (D10) — does not lift the cap (decided 2026-10-15): it adds its points,
but a below-market rent alone cannot carry a no-red-flag result past MODERATE —
see [Price](#price--evidenceprice).

**Cost** (`nlp-service/eval/cap_cost.py`, scored with this code): of 316 corpus
scams, 33 have no red flag; 32 move HIGH → MODERATE (the other was already
LOW), none goes below MODERATE. On scams in wording the model never trained on
(the held-out minimal pairs), 40 of 72 have no red flag and 36 move HIGH →
MODERATE: layer 1's rules miss unfamiliar wording too. No corpus legitimate
conversation was HIGH to begin with.

### `POST /analyze/screenshot`
`multipart/form-data`, field `files` — repeatable, up to 20 screenshots, 5MB
each (`image` accepted as an alias). Pages are OCR'd and stitched in **upload
order**, then analysed as one conversation.

Optional text fields `agentName`, `agentPhone`, `renNumber` and `company` carry
the same agent details as `/analyze`'s `agent` object, and `price`, `area`,
`propertyType`, `bedrooms` and `roomType` its `property` object (the Listing
details form), validated the same way (before any OCR is run). An empty field
counts as not given — an empty `bedrooms` is not a studio.

Response is the `/analyze` body plus:

```json
{
  "ocrText": "Renter: ...\nOwner: ...",
  "ocr": { "pageCount": 3, "messages": 11, "method": "bubbles", "pages": [ ... ] }
}
```

`ocr.messages` is the message count layer 2's guard uses. Below 6 the analysis
returns `insufficient_context`, so a client can ask for more screenshots before
showing anything. Returns 422 if no text could be read from any page.

> ### ⚠️ Pages must be uploaded in chronological order
>
> `/ocr` stitches pages in the order received and does **not** sort them. Out of
> order, the conversation is scrambled: a real four-page scam exported from a
> phone arrived as p3 → p2 → p4 → p1, and classifying the scrambled text gave a
> different result from the correct order.
>
> It also breaks de-duplication. Overlapping messages at a page seam are removed
> by keeping the first occurrence; if the pages are shuffled, the "first" one is
> the wrong one and the reply under a quoted message can be trimmed instead of
> the quote.
>
> **Client responsibility:** order the files by the conversation, not by
> filename — `IMG_10` sorts before `IMG_2` as a string. A file picker returns
> whatever order the OS gives.
>
> **Frontend TODO:** let the user reorder pages before uploading (drag to
> sort, with a thumbnail of each), and show the stitched text back so a bad
> order is visible before the result is trusted.
>
> **Service TODO:** `/ocr` could sort pages by the first timestamp it can read
> on each, falling back to upload order when a page has none. `app/turns.py`
> already recognises the mangled forms OCR produces (`5.95`, `1808`, `17684 W`),
> so the parsing exists; what is missing is reading the *first* timestamp per
> page and ordering on it. Not implemented — upload order is authoritative
> today.

### `POST /search`
Public agent lookup: runs the same OSINT search as `/analyze`, on details typed
in directly. POST, not GET, so the phone number never appears in a URL (and so
never in the request log).

```json
{ "phone": "012-345 6789", "name": "Ahmad Faizal", "ren": "REN 12345", "company": "Maju Jaya Realty Sdn Bhd" }
```
Every field is optional, but a valid Malaysian mobile number **or** a name of 2+
words is required (400 otherwise). Rate-limited to 10 requests per 15 minutes
per IP, on top of the global limit: each request can spend 4 paid searches.

Response: the [`evidence.osint`](#osint--evidenceosint) object plus a fixed
`disclaimer: { en, ms }` — results are public web mentions, not verified
findings, and finding nothing does not mean the agent is safe. There is **no
overall risk score**: without the chat and the price there is nothing to
combine it with.

| `status` | HTTP |
|---|---|
| `ok` | 200 |
| `no_identifier` | 400 |
| `quota_exceeded` | 429 |
| `not_configured`, `search_failed` | 503 |

### OSINT — `evidence.osint`

Research doc §5.3 is the source of truth; the PRD's per-identifier points table
is superseded. Implemented in `backend/src/services/osint.service.js`.

**Queries** — up to 4 per analysis, one per identifier, skipped when that
identifier is unusable:

| query | runs when | sent as |
|---|---|---|
| `phone` | a valid Malaysian mobile | `("012-345 6789" OR "0123456789" OR "+60123456789") scam OR penipu OR penipuan OR tipu` |
| `name` | 2+ words | `"<name>" scam OR penipu OR "agen palsu" OR fraud property` |
| `ren` | prefixed `REN` / `PEA` / `E` (digits alone are skipped) | `"REN 12345" scam OR penipu OR "fake agent" OR penipuan` |
| `company` | 2+ words left after removing Sdn Bhd / Bhd / Berhad | `"<company>" scam OR penipu OR fraud OR "syarikat tipu" property Malaysia` |

A search runs only if there is a valid phone or a 2+ word name.

**Source tiers.** Each result's host (`www.` removed) is matched exactly or as
a subdomain — never as a substring, so `notx.com` is not `x.com`:

| tier | points | domains |
|---|---|---|
| news | 12 | thestar.com.my, nst.com.my, bharian.com.my, hmetro.com.my, malaysiakini.com, freemalaysiatoday.com, malaymail.com, bernama.com, sinarharian.com.my |
| forum | 8 | lowyat.net, reddit.com, forum.cari.com.my, carigold.com |
| social | 5 | facebook.com, twitter.com, x.com, tiktok.com, instagram.com, threads.com, threads.net |
| portal | 0 → `context` | propertyguru.com.my, iproperty.com.my, mudah.my, ibilik.my, edgeprop.my, speedhome.com |
| anything else | 0, ignored | including caller-ID sites |

Listing portals print anti-scam boilerplate on every page, so a portal hit only
shows the number is advertised there; it is listed in `context`, never scored.

**Classifying results — two layers.** Keyword matching alone cannot tell who is
accusing whom. A real agency (Vigor Properties Sdn Bhd) scored 5 points from
four false positives: property reels mentioning "risiko scam", an ad saying it
is *not* a scam, a reel where the company was a tagged sponsor, and the
company's own notice that someone was impersonating its agents. The right
answer is 0 points and one warning.

*Layer 1 — rules (always on, deterministic).* Matching runs on NFKC-normalised
text (titles use Unicode bold such as "𝐓𝐀𝐊𝐔𝐓"); the original text is what is
returned. A result is considered only if it contains **both** one of this
agent's identifiers (phone compared as normalised digits; every name token as a
whole word; REN as an exact word-bounded match, so REN 12345 never matches
inside 0123456789; company core as a whole phrase) **and** a keyword.

The result is attributed (`query`) to the **strongest identifier in its own
text** — phone > ren > name > company — whichever search returned it
(`foundBy`). Google returned a post containing "No tel : 01169340728" for the
name search only; filed under the name, it could not corroborate or survive the
rules-only fallback.

Keywords are checked in the **title and the snippet separately**: a PDRM post
titled "…TAWAR RUMAH TIDAK …" (a house that does not exist) once lost
"PENIPUAN RUMAH SEWA" at the start of its snippet to the title's last word. The
keywords: scam, scammer, penipu, penipuan, tipu,
ditipu, menipu, tertipu, kena tipu, fraud, complaint, aduan, warning, amaran,
berhati-hati, hati-hati, hati hati, awas, beware, victim, mangsa, blacklist,
senarai hitam, agen palsu, fake agent, syarikat tipu. Keywords match on word
start (`scam` → scams, scammed); Malay affixed forms are listed explicitly.
Known noise: `scampi` matches. The URL is never used for identifier or keyword
matching. Then, in order:

| rule | result |
|---|---|
| listing-portal domain | context `listing_portal` |
| impersonation cue (impersonat\*, menyamar, mengaku, 冒充, "not affiliated", "tiada kaitan", "bukan ejen kami") in the text **or the percent-decoded URL path**, on a result attributed to the **company or REN** | context `impersonation_notice` + warning |
| every keyword hit has a cue within the 3 tokens before it: bukan, tak, tidak, not, no, anti, elak, elakkan, avoid, risiko, risk, prevent, national, 997, or "response centre" / "scam centre" around it | context `generic_mention`; the dropped hits are in `matched.ignored` |
| attributed to the company, on a social-media domain | context `social_mention` |
| anything else | **candidate** |

Malay "no" also means "number" ("no ni scammer", "no 012-345 6789 penipu"), so
it only negates when the next token is not a number or ni / ini / tel /
telefon / hp. On a hit attributed to a **phone or name**, impersonation words
usually describe the accused ("Lelaki menyamar ejen hartanah ditahan"), so such
a hit stays a candidate for the judge; with no judge it is held as context
`impersonation_mention` (no points, no warning). A link found by several
queries is kept once: a candidate beats context, then the strongest identifier
wins.

*Layer 2 — LLM judge (when configured).* One batched call per search, only when
there is at least one candidate, within a **15 s** budget. At most **10**
candidates are sent, strongest queries first (phone > ren > name > company,
search-rank order within each); the rest are listed in context as `unjudged`
and score nothing. `judgeCandidates` says how many were sent. The only retry is
one, 1 s later, after a 5xx (the model is overloaded), inside the same 15 s;
`verifierRetried` says whether it happened. Prompt:
`backend/src/prompts/osintVerifier.prompt.js` (`VERIFIER_PROMPT_VERSION`). The
judge receives **only** `{ id, queryType, identifier, domain, title, snippet }`
per candidate — public search text and the one identifier searched for, never
the renter's chat or the other agent details (the Gemini free tier may use
inputs for product improvement). Labels and what they do:

| label | result |
|---|---|
| `complaint`, confidence ≥ 0.6 | **evidence** — scores its tier; except a **name-only** match → context `name_only_match`, 0 points |
| `complaint`, confidence < 0.6 | context `low_confidence_complaint` |
| `impersonation_notice` | context + warning |
| `marketing_or_generic`, `unrelated` | context, typed by label |
| no verdict, or an invalid label | `unrelated`, `judgeMissing: true` |

Judged items carry `label`, `confidence` and `reason`. Provider:
`LLM_VERIFIER_PROVIDER` = `gemini` (default; `GEMINI_API_KEY`, `GEMINI_MODEL` —
no default model, copy it from Google AI Studio) or `anthropic`
(`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`). On by default when that provider's
key is set; `OSINT_LLM_VERIFY=false` turns it off.

| `verifier` | `verifierProvider` | meaning |
|---|---|---|
| `llm` | the provider | the judge ran (or had no candidates to judge) |
| `rules_only` | `null` | the judge is off: no key, empty `GEMINI_MODEL`, or `OSINT_LLM_VERIFY=false` |
| `rules_only` | the provider | the judge call failed — see `verifierError`; the rules decide, conservatively |

| `verifierError` | when | retried |
|---|---|---|
| `timeout` | no answer within 15 s | no |
| `429` | rate or free-tier limit | no |
| `invalid_model` | HTTP 404, or a 400 naming the model (check `GEMINI_MODEL` / `ANTHROPIC_MODEL`) | no |
| `unavailable` | HTTP 5xx — e.g. 503 "This model is currently experiencing high demand" | **once**, 1 s later |
| `bad_json` | output is not JSON, has no tool call, or has no `results` array | no |
| `other` | anything else (e.g. a rejected API key) | no |

The warn log line gives the category, HTTP status and the provider's message
(cut to 300 characters, with every API key redacted).

**Rules-only scoring is conservative.** Whenever `verifier` is `rules_only`,
only the unique identifiers — **phone and REN** — can score. A name or company
candidate goes to context as `unverified_mention` with 0 points: the common
name "Muhammad Adam" matched a Nigerian fraud trial, a law firm's X account and
a government group, and keyword rules cannot tell those from a real complaint.

**Warnings.** An impersonation notice never adds points. It produces at most one
warning, listing every notice link. Its `scope` decides the wording:

| `scope` | when | message |
|---|---|---|
| `agent` | a notice names **this agent** — it is attributed to their phone, REN or name | "A public notice warns that scammers are pretending to be this agent, using fake contact details. Call the agency's official number to confirm this phone number really belongs to the agent before paying." |
| `company` | the notices are about the company only | "This company has publicly warned that people are impersonating its agents. Verify this agent through the company's official phone line before paying." |

Both have a Malay `ms` version. The agent wording came from a legit-agent test:
a Vivahomes notice warned that scammers were posing as its negotiator by name,
with false contact details — the renter's real question is whether the number
they have is the agent's.

```json
{ "type": "impersonation_notice", "scope": "agent", "company": "VIVAHOMES REALTY SDN BHD",
  "links": ["https://www.facebook.com/VivahomesHQ/posts/...", "https://www.facebook.com/VivahomesHQ/posts/..."],
  "en": "A public notice warns that scammers are pretending to be this agent, ...",
  "ms": "Terdapat notis awam bahawa penipu menyamar sebagai ejen ini, ..." }
```

**Judge prompt v2** (2026-10-11): any kind of scam counts as a `complaint` —
rental, online shopping, loans, parcels, investment, jobs. A number used in any
scam is relevant to a renter, and "unrelated" means *not connected*, never *not
about property*. (In v1 the judge's reasons read "unrelated … not rental
fraud": correct there, the hits were namesakes, but the same reasoning would
discard a phone number reported for a shopping scam.)

**Score.** Only `evidence` scores. Each tier scores once across all queries:
`points = news 12 + forum 8 + social 5` (max 25), `riskFraction = points / 25`.
Nothing is scored for something missing — no REN, an unknown company, or a REN
in the wrong format adds 0.

**strongHit and social corroboration.** Only phone and REN evidence counts.
`strongHit` is true when either:

- a news or forum evidence item came from the `phone` or `ren` query
  (`strongHitReason: "news_or_forum"` — reported first when both apply), or
- phone / REN evidence comes from **at least 3 distinct social sources**
  (`strongHitReason: "social_corroboration"`). Points do not change — social
  still scores 5, once.

Each evidence item carries a `sourceKey`, and several posts in one group or
account count as one source:

| URL | `sourceKey` |
|---|---|
| `facebook.com/groups/<id>/…` | `facebook:group:<id>` |
| `facebook.com/<page>/…` | `facebook:<page>` |
| `threads.com/@<user>/…`, `threads.net/@<user>/…` | `threads:<user>` |
| `x.com/<user>`, `twitter.com/<user>` | `x:<user>` (one account, two domains) |
| `instagram.com/<user>`, `tiktok.com/@<user>` | `instagram.com:<user>`, `tiktok.com:<user>` |
| news and forum sites | the hostname |

Keys are lowercase; `www.`, `m.`, `web.` and `mobile.` are ignored. A URL with
no account in it (`instagram.com/reel/<id>`, `facebook.com/story.php?…`) shares
one key per form, which under-counts but never over-counts. Known limit: one
Facebook group linked by both its numeric ID and its vanity name counts twice.

```json
"corroboration": { "sources": 4, "threshold": 3,
  "keys": ["facebook:group:471039784875816", "threads:lizaaajeeelaaa",
           "facebook:group:1107732539961661", "facebook:group:rumahsewaipoh"] }
```
`keys` lists the distinct **social** sources of phone / REN evidence; news and
forum items already qualify on their own.

```json
{
  "status": "ok",
  "provider": "serper",
  "riskFraction": 0.8,
  "points": 20,
  "max": 25,
  "breakdown": { "news": 12, "forum": 8, "social": 0 },
  "strongHit": true,
  "strongHitReason": "news_or_forum",
  "corroboration": { "sources": 0, "threshold": 3, "keys": [] },
  "warnings": [],
  "verifier": "llm",
  "verifierProvider": "gemini",
  "verifierVersion": "v2",
  "verifierError": null,
  "verifierRetried": false,
  "judgeCandidates": 2,
  "identity": { "phone": "0123456789", "name": "Ahmad Faizal", "ren": "REN 12345", "company": null, "source": "form" },
  "queries": ["phone", "name", "ren"],
  "failedQueries": 0,
  "evidence": [
    { "title": "...", "link": "https://www.thestar.com.my/...", "snippet": "...",
      "domain": "thestar.com.my", "tier": "news", "query": "phone",
      "matched": { "terms": ["scam", "victims"], "ignored": [] },
      "label": "complaint", "confidence": 0.93, "reason": "News report of arrest for rental fraud using this number.",
      "sourceKey": "thestar.com.my" }
  ],
  "context": [
    { "title": "...", "link": "https://www.instagram.com/reel/...", "snippet": "...",
      "domain": "instagram.com", "tier": "social", "query": "name",
      "matched": { "terms": ["scam"], "ignored": [] },
      "label": "marketing_or_generic", "confidence": 0.9, "reason": "Property ad mentioning scam risk.",
      "type": "marketing_or_generic" }
  ],
  "cached": false,
  "fetchedAt": "2026-10-04T10:00:00.000Z"
}
```

**Status.** Anything but `ok` has `riskFraction: null` and `points: null`, so
the signal is **excluded** from the score (`excludedSignals` gains `"osint"`),
never counted as a clean 0:

| `status` | when |
|---|---|
| `ok` | at least one query answered (`failedQueries` says how many did not) |
| `no_identifier` | no valid phone and no 2+ word name |
| `not_configured` | neither search key is set |
| `quota_exceeded` | every configured provider is over its daily limit |
| `search_failed` | every query failed, after the fallback |

`ok` with 0 points means *nothing was found* — not that the agent is safe.

**Providers.** Serper.dev is primary, SerpApi the fallback; one result set never
mixes them. Serper is used when `SERPER_API_KEY` is set and within
`SERPER_DAILY_LIMIT`; otherwise SerpApi (`SERPAPI_API_KEY`,
`SERPAPI_DAILY_LIMIT`). If **every** Serper query fails, the whole set is
retried once on SerpApi; a partial failure is not retried. SerpApi's "Google
hasn't returned any results" notice is read as an empty answer, not a failure.
`provider` names the one that produced the results.

**Budget.** Serper's 2,500 free queries are a **one-time** allowance, not
monthly — about 625 uncached analyses at 4 queries each. SerpApi's free plan is
250 a month. Daily limits (defaults: Serper 80, SerpApi 8) are counted per
provider in Redis (`osint:quota:<provider>:<YYYY-MM-DD>`, Malaysia date), in
memory when Redis is down; queries sent count even if they failed.

**Cache and privacy.** Results are cached under
`osint:v3:<prompt version>:<gemini|anthropic|rules>:<HMAC-SHA256(OSINT_CACHE_SECRET, phone|name|ren|company)>`
— independent of the search provider, and not reversible to the phone number
the way a plain hash of a phone number is. The judge's prompt version and mode
are in the key, so changing the prompt or turning the judge on never serves
labels made under the old setup. 24 h after a full success; 1 h after a
partial search failure or a failed judge call; failures and `quota_exceeded`
are never cached. Logs carry masked phones (`012****789`) and query kinds only
— never query text or an API key.

**REN is never "verified".** The LPPEH register is not indexed by Google, so a
REN is only searched for negative evidence; finding nothing about it says
nothing about whether it is valid.

### `GET /price/areas`
Lists **every** canonical area, for the area dropdown. Areas are sorted by state
then name, and included even with no scorable stratum, so a renter can still pick one and be
told `no_baseline` / `thin_baseline`. Returns 503 if the baseline cannot be read.

```json
{
  "areas": [
    { "name": "Cheras (KL)", "state": "KL",
      "strata": [
        { "propertyType": "condo", "bedrooms": 3, "sampleSize": 451, "buildings": 69, "scorable": true },
        { "propertyType": "room", "roomType": "common", "sampleSize": 1, "buildings": 1, "scorable": false }
      ] }
  ],
  "dataNote": { "en": "Based on Mudah asking prices from about 2023, scaled ×1.20 to current prices; iProperty / PropertyGuru asking prices from Aug 2026. Asking prices, not agreed rents. Landed property isn't covered yet.",
                "ms": "…" }
}
```
`state` is `KL` or `Selangor`. A whole-unit stratum carries `bedrooms`; a room
stratum carries `roomType`. `scorable` means 5 or more listings from 3 or more buildings.

### `GET /price/check`
The same price check as `/analyze`, with the same [form contract](#the-listing-details-form):
`?price=1200&area=Wangsa%20Maju&propertyType=condo&bedrooms=2`.
- A field not filled in returns status `missing_input` (200).
- A malformed value (bedrooms `2.5`, price `abc`) is a 400.
- `baseline_unavailable` is a 503.

The response is the [`evidence.price`](#price--evidenceprice) object plus a
fixed `disclaimer: { en, ms }`: it compares asking prices, not agreed rents, and
a normal price is not proof of safety. There is no overall risk score. GET is
fine here because nothing in it identifies anyone; no paid calls are made.

### Price — `evidence.price`

Research doc §5.4 is the spec; the [decisions](#decisions) below record where and
why this differs. Implemented in `backend/src/services/price.service.js`. The
baseline is built by `scripts/baseline` (`data/processed/external_coverage.json`).

#### The Listing details form

**The rent comes only from the form — never from the chat (D8).** `/analyze`
takes it as `property`; `/analyze/screenshot` as multipart fields. Validation is
in `backend/src/validation/property.schema.js`.

| form label | API `propertyType` | compared as | fields shown |
|---|---|---|---|
| Studio | `studio` | condo, 0 bedrooms | rent, area (bedrooms hidden) |
| Condo / Serviced residence | `condo` | condo | rent, area, bedrooms |
| Apartment | `apartment` | apartment | rent, area, bedrooms |
| Flat / PPR | `flat` | flat | rent, area, bedrooms |
| Landed | `landed` | — (always `no_baseline`) | rent, area, bedrooms |
| Room | `room` | room, by `roomType` | rent, area, room type (bedrooms hidden) |

| field | accepts | rules |
|---|---|---|
| `price` | a number, or `"RM1,500"` / `"1,500"` / `"RM 1 500"` | RM, commas and spaces stripped; > 0 and ≤ 100,000 |
| `area` | a canonical name from `GET /price/areas` | trimmed, any case; anything else is `unknown_area`; a plain two-state name ("Cheras") gets "Choose which Cheras: Cheras (KL) or Cheras (Selangor)." |
| `propertyType` | `condo \| apartment \| flat \| landed \| room \| studio` | `studio` → condo with 0 bedrooms; any bedrooms sent is ignored |
| `bedrooms` | integer 0–20, or `"4+"` | required for condo / apartment / flat / landed; 5+ compared as 4; ignored for room and studio |
| `roomType` | `master \| common \| single \| middle` | required for a room; single and middle → common; ignored otherwise |

- **Blank fields.** An empty string means "not given" for every field. A
  multipart `""` stays undefined and never becomes 0.
- **Missing or partial form.** If the whole object is absent or empty, or a
  field the stratum needs is blank, price is `missing_input`, `missing` lists
  the fields, and price is left out of the score. That is not an error.

**Areas.** About 125 KL / Selangor localities, kept apart where a source
distinguishes them (Pudu ≠ KLCC; Damansara Heights ≠ Damansara Perdana; Bangsar
South ≠ Bangsar). A name used in both states carries a suffix (Cheras, Ampang,
Gombak, Puchong, Serdang). The reason is measured: Cheras 3BR condos are RM1,500
in KL and RM1,300 in Selangor. The canonical names and two-state names are
`scripts/scrapers/config.py`, mirrored in `backend/src/config/areas.js` and
checked by a sync test. config.py's aliases (for portal and scraped
spellings) are used by the baseline pipeline only; the form takes no aliases.

#### Scoring

Strata are (area, property type, bedrooms) for whole units and (area, room
type) for rooms. A stratum is scored only with **≥ 5 listings from ≥ 3 distinct
buildings** (D4). Deviation `d = (median − price) / median`, compared by
cross-multiplication:

| d | points | `tier` |
|---|---|---|
| d < 30% (and above market) | 0 | `within_range` |
| 30% ≤ d ≤ 45% | 10 | `suspicious` |
| d > 45% | 15 | `highly_suspicious` |

`anomalyFraction = points / 15`. **p25 guard (D3):** a price at or above the
stratum's 25th percentile scores 0 (`guard: "at_or_above_p25"`).

**Minimum-rent floor (D10)** — a sanity rule, not a market comparison. Before
any baseline lookup, a rent below the floor for its type scores the top tier:
15 points, `tier: "highly_suspicious"`, `guard: "below_floor"`, with
`deviation` and `baseline` null. It applies even where the stratum is thin or
missing (most studios, every room), but only to a canonical area — outside
our KL / Selangor coverage the area is `unknown_area` first — and only to a
complete form (otherwise `missing_input`).

| type | floor (`rule.rentFloor`) | why this number |
|---|---|---|
| whole unit, studio, landed | < RM300 | the baseline cleaning already drops whole units under RM300 as per-day prices; no baseline listing is below it |
| room (master or common) | < RM150 | the cheapest room in the baseline is RM600 |

Like any price signal, it does not lift the no-red-flag cap (D9).

**Status.** Anything but `ok` has `anomalyFraction: null` and `points: null`,
so `excludedSignals` gains `"price"`; it is never counted as a clean 0.

| `status` | when | `message.en` |
|---|---|---|
| `ok`, points > 0 | scored | "RM{price} is {n}% below the median of {sampleSize} comparable listings (RM{median})." + data note |
| `ok`, 0 points | within range, above market or guarded | "RM{price} is within the normal range for {stratum} (median RM{median} across {sampleSize} comparable listings)." + data note |
| `ok`, `guard: "below_floor"` | under the D10 floor; 15 points, no baseline consulted | "RM{price}/month is far below any real rent for this property type in {area}." (no data note) |
| `missing_input` | price, area or type blank | "Fill in rent, area and property type to compare with market prices." (only bedrooms / room type blank: "Add the number of bedrooms…" / "Add the room type (master or common)…") |
| `unknown_area` | not a canonical name | the two-state hint, or "\"{area}\" isn't an area in the price data. Pick one from the list." |
| `no_baseline` | no stratum | "No price data yet for {stratum}." |
| `no_baseline` (landed) | every landed input | "Landed property isn't covered yet: the price data has almost no landed listings." |
| `thin_baseline` | stratum below D4 — comparison shown, unscored | "Only {n} comparable listings from {b} building(s) for {stratum} — too few to score. Their median is RM{median}." + data note |
| `baseline_unavailable` | the database could not be read | "The price check is unavailable right now." |

Every message has a Malay `ms` version. **The data note** names the sources and
their age. When Kaggle rows are in the stratum it reads: "Based on Mudah asking
prices from about 2023, scaled ×1.20 to current prices; iProperty /
PropertyGuru asking prices from Aug 2026. Asking prices, not agreed rents."

```json
{ "status": "ok", "anomalyFraction": 1, "points": 15, "max": 15,
  "tier": "highly_suspicious", "deviation": 0.5098, "guard": null, "listedPrice": 1000,
  "stratum": { "area": "Wangsa Maju", "propertyType": "condo", "bedrooms": 2 },
  "baseline": { "median": 2040, "p25": 1750, "p75": 2820, "sampleSize": 15, "buildings": 9,
                "sources": ["kaggle", "scraped"], "adjustmentFactor": 1.2,
                "vintages": { "kaggle": "2023 (inferred)", "scraped": "2026-08-27" }, "status": "scorable" },
  "missing": [],
  "rule": { "thresholdPct": 30, "highThresholdPct": 45, "p25Guard": true, "minListings": 5, "minBuildings": 3,
            "rentFloor": { "wholeUnit": 300, "room": 150 } },
  "message": { "en": "RM1,000 is 51% below the median of 15 comparable listings (RM2,040). Based on Mudah asking prices from about 2023, scaled ×1.20 to current prices; iProperty / PropertyGuru asking prices from Aug 2026. Asking prices, not agreed rents.",
               "ms": "…" } }
```

#### Baseline data

| source | what | rows in → used |
|---|---|---|
| `kaggle` | Kaggle `ariewijaya/rent-pricing-kuala-lumpur-malaysia`, **scraped from mudah.my**; no date in the file, inferred 2023 (192 rows in buildings completed in 2023, 10 in 2024) | 19,991 → 13,744 |
| `scraped` | our iProperty / PropertyGuru scrape, 2026-08-27 | 558 → 266 |
| `manual` | `data/raw/manual/manual_price_entry.xlsx` (Rooms and Studios sheets): listings recorded by hand from iProperty / PropertyGuru / iBilik, Oct 2026 (two rounds); not time-adjusted | 96 → 96 (84 rooms, 12 studios) |

Cleaning, in this order:
1. Dedupe by listing ID within a source.
2. Kaggle only: keep one row per building + price + size + area + bedrooms
   (5,922 rows removed).
3. Drop any price outside RM100–100,000.
4. Drop as per-day / per-week: a whole unit under RM300, or under RM0.30 per sq ft.
5. Drop as a sale price: over RM12 per sq ft.
6. Blank sizes under 200 or over 10,000 sq ft (the row is kept).
7. Drop 0-bedroom condos with no size that are not confirmed studios.
8. Dedupe across sources one-to-one.

Seeded: **698 whole-unit strata (313 scorable), 19 room strata (14 scorable)**.
The manual workbook is read directly by `scripts/baseline/sources/manual.py`. A
row is rejected with its sheet and row number, never repaired, for: an area
that is not an exact canonical name, a missing building, a price that is not a
whole number from RM150 (rooms) or RM300 (studios) to RM100,000, an unknown
room type, or a date outside 2026 to today. Studios become 0-bedroom condos.

**Time adjustment.** Kaggle prices are multiplied by **1.20**: the median over
**41** (building, bedrooms) pairs listed in both sources of (scrape median ÷
Kaggle median), with an interquartile range of 1.07–1.39.

**The factor mixes time with platform** — Mudah asking prices (~2023) vs
iProperty / PropertyGuru (2026) — and this data cannot separate the two. The
stratum-median estimate (1.84 over 14 strata, ratios 0.95–3.24) was not used:
in KLCC and Mont Kiara the scrape is mostly luxury towers.

**Limitations.**
- **Landed is a gap.** The sources hold 6 landed listings, so every landed
  input returns `no_baseline`.
- **Room prices depend on how many people share the room (pax), which the
  form doesn't capture.** A master room shared by five can rent below a common
  room for two in the same building (Meta City, Nadayu 801), so room strata are
  wider than whole-unit strata. A real cheap shared room can score: Meta City's
  RM600 master room (5 pax) is 37% below the Seri Kembangan master-room median
  (RM955) and gets 10 points. The damage is bounded: price adds at most 15
  points, and D9 stops price alone from lifting a result with no red flag
  above MODERATE.
- **The room and studio data is a small hand-collected sample.** 96 listings
  (84 rooms, 12 studios) recorded in Oct 2026 for 18 cells in 7 areas: common
  and master rooms in Setapak, Cheras (KL), Seri Kembangan, Puchong
  (Selangor), Shah Alam, Petaling Jaya and Subang Jaya, and studios in four
  of them. The four studio cells and Subang Jaya master rooms still have
  exactly the D4 minimum of 5 listings. Rooms in every other area are still
  unscored; only the floor (D10) applies there.
- **Data age and provenance.** Most strata rest on ~2023 Mudah prices scaled by a
  factor that also absorbs platform differences. Mudah's robots.txt forbids
  automated access; this is a third-party published dataset, and its licence is
  not yet verified.
- **Asking prices, not agreed rents.** Bait listings on the portals are inside
  the baseline too.

#### Decisions

| | decision | research doc | why |
|---|---|---|---|
| **D1** | **scored from 30% below the median** (10 points to 45%, 15 beyond) | follows **§5.4.2's decision rule** ("flag below 70% of the stratum"); §5.4.3's 5-point tier from 15% is dropped | leave-one-out over 12,550 legitimate portal listings (`data/processed/price_loo_eval_threshold_choice.json`), see the table below. The 15% start added 12.8 points of false positives at > 0 points and caught nothing at ≥ 10 points that 30% misses |
| D2 | **median**, not mean | deviation from §5.4.1 | heavy outliers; the baseline stores median / p25 / p75 |
| D3 | **p25 guard**, on | addition | a price a quarter of real listings undercut is not anomalous; it cuts 29 of 1,099 false flags at 30% |
| D4 | ≥ 5 listings, ≥ 3 buildings | addition | one development must not set a district's price |
| D5 | not `ok` → excluded, not 0 | — | a check that did not run must not raise `maxPossibleScore` |
| D6 | rooms as `master \| common` strata | not covered | portals label only "Master Room" / "Common Room" |
| D7 | property type required to score | the doc stratifies by type (the PRD form lacks it) | type is a stratum variable |
| **D8** | **form only, no text parsing** | — | a deposit, booking fee or negotiated figure read as the rent would score a listing on a number its landlord never asked for |
| D9 | price does not lift the no-red-flag cap | §5.5.1 "a corroborating signal" | legitimate landlords under-price |
| **D10** | **minimum-rent floor** (2026-10-19): whole unit / studio / landed < RM300, room < RM150 → 15 points, `guard: "below_floor"`, before the baseline lookup, canonical areas only | not in the research doc — a **sanity rule, not a market comparison** | most studio and every room stratum is too thin to score (studios scorable in 6 of 125 areas, rooms in 0), so RM100 for a Subang Jaya studio scored nothing; no listing in the baseline is below either floor |
| types | condo, apartment, **flat**, landed, room | condominium, apartment, terrace, semi-D | flats rent 23% below apartments (median over 31 strata) |
| data | Kaggle (Mudah ~2023, ×1.20) + our scrape + manual | ~500 PropertyGuru listings per area | our scrape alone covered 5 of 98 target cells |

#### False-positive rate (leave-one-out)

`backend/scripts/price_loo_eval.js` uses the production `scoreAgainstBaseline`
and writes `data/processed/price_loo_eval.json`.
- Every pooled listing is an asking price on a portal and is treated as
  **legitimate**.
- Each one is held out and its stratum rebuilt without it. The D4 eligibility
  rule is applied **after** the removal, and the held-out `price_adjusted` is
  scored.

Definitions:
- **flagged**: the held-out listing gets **> 0 points**.
- **flagged ≥ 10**: it gets 10 or 15 points.
- **FP rate**: flagged ÷ listings scored.

Whole units: 13,998 listings, 12,550 scored. Rooms: 102 listings, 89 scored (see
[the hand-filled cells](#rooms-and-studios-the-hand-filled-cells) below).

| start | p25 guard | flagged > 0 | FP rate > 0 | flagged ≥ 10 | FP rate ≥ 10 |
|---|---|---|---|---|---|
| 15% (§5.4.3) | on | 2,673 | 21.3% | 1,070 | 8.5% |
| 15% (§5.4.3) | off | 3,240 | 25.8% | 1,099 | 8.8% |
| **30% (§5.4.2) — implemented** | **on** | **1,070** | **8.5%** | **1,070** | **8.5%** |
| 30% (§5.4.2) | off | 1,099 | 8.8% | 1,099 | 8.8% |

The 15% rows come from the run that chose D1, kept in
`data/processed/price_loo_eval_threshold_choice.json`. The implemented row is
reproduced by the current script.

Two caveats:
- **These are upper bounds.** Some portal listings are bait or scams themselves.
- **By source**, scraped listings flag far less than Kaggle's: 2.3% vs 8.6%.

##### Rooms and studios: the hand-filled cells

`backend/scripts/price_loo_manual_cells.js` runs the same check on the 18
cells filled by hand: 114 listings (96 manual, 18 scraped or Kaggle), after
the second round of entry (2026-10-21). It writes
`data/processed/price_loo_manual_cells.json`. Results, with the p25 guard on:

| view | rooms: flagged ≥ 10 / scored | studios: flagged ≥ 10 / scored |
|---|---|---|
| leave-one-out, D4 after removal (the rule above) | **6 / 89 (6.7%; four at 10, two at 15)** | not measurable under the leave-one-out rule (cells at the 5-listing minimum) |
| leave-one-out against the other 4 listings — **below the D4 minimum**, supporting evidence only | 6 / 94 (6.4%) | 0 / 20 |
| each listing against its whole cell, as served today | 4 / 94 (4.3%; 10 points each) | 0 / 20 |

**Final results** (leave-one-out, D4 applied after removal; target ≤ 15%):

| | listings tested | flagged ≥ 10 | 10 points | 15 points | FP rate | ≤ 15% |
|---|---|---|---|---|---|---|
| whole units | 12,550 | 1,070 | 809 | 261 | 8.5% | met |
| rooms | 89 | 6 | 4 | 2 | 6.7% | met |
| studios | 0 | — | — | — | not measurable under the leave-one-out rule (cells at the 5-listing minimum) | — |

Supporting evidence for studios, below the D4 minimum: each studio listing
scored against the other 4 in its cell — 0 of 20 flagged.

- **What could be tested.** 89 of the 94 room listings can be tested under
  the production rule, up from 17 after the first round. The five Subang Jaya
  master rooms and all 20 studio listings cannot: each of those cells has
  exactly 5 listings, so holding one out leaves it below D4. The second row is
  a sensitivity view only; production never scores a 4-listing cell.
- **Flagged in the leave-one-out run:**
  - Setapak common: Putra Villa RM450 (10 points).
  - Subang Jaya common: Impian Meridian RM450 and USJ 2 RM450 (15 points
    each), and Casa Subang Jaya RM500 (10).
  - Seri Kembangan master: Meta City RM600 (10). This is the worked example of
    the pax limitation above: a master room shared by 5.
  - Puchong (Selangor) master: Aurora Residence RM650 (10).
- **As served today**, Putra Villa, Impian Meridian, USJ 2 and Meta City each
  get 10 points.
- **The p25 guard** saved nothing in the leave-one-out run. As served today it
  zeroes Casa Subang Jaya RM500.
- **Bounded by D9.** Each of these is a price signal only: it adds 10–15
  points, and D9 stops it from lifting a result with no red flag above
  MODERATE.
- **Median sensitivity:** no cell's median moves by more than 15% when one
  listing is removed. The largest shifts are Subang Jaya common 13.3%,
  Setapak common 7.1%, Seri Kembangan master 0.5% and Setapak master 0.0%;
  after the first round Subang Jaya common moved by up to 24%.

#### Scam eval

`data/eval/price_form_cases.csv` has one row per case: what a renter would type
into the form, blank where the source does not say. Columns:
`case_id, label, source_conversation, source_url, price, area, property_type, bedrooms, room_type, notes`.

| `case_id` | case | `label` | source |
|---|---|---|---|
| `PFC-S..` | real labelled chat | `scam` | `source_conversation` (e.g. `REAL-S04`) |
| `PFC-L..` | real labelled chat | `legit` | `source_conversation` |
| `PFC-N..` | news / police-reported scam | `scam` | `source_url` (required) |

The file holds 13 chat rows (6 scam, 7 legit), verified 2026-10-15; no news cases yet.

`backend/scripts/price_scam_eval.js` runs each row through the same validation
and `scorePriceAnomaly`. It reports **chat**, **news** and **combined**, each by
label. Every case gets one outcome, and **coverage is judged before
completeness**: a case in an area or of a type the baseline does not cover
could never be scored, so it is not counted as a failure.

| outcome | when |
|---|---|
| `scored` | status `ok`; `flagged10` = ≥ 10 points, `flagged15` = 15 |
| `outside_coverage` | the area is not one of ours (Seremban, Kedah, Penang …), the type is landed, or there is no stratum |
| `insufficient_data` | the stratum is below D4 eligibility (`thin_baseline`) |
| `input_incomplete` | `missing_input`, a two-state area without its state ("Cheras"), or a value the form would reject |
| `unavailable` | the baseline could not be read |

The script checks the file before scoring and rejects it when:
- a case_id is not `PFC-S` / `PFC-L` / `PFC-N`;
- an S or N case is not `scam`, or an L case is not `legit`;
- a news case has no `source_url`;
- a case_id appears twice.

It refuses to run while any row is still `draft`. Output goes to
`data/processed/price_scam_eval.json`.

Run it as `node backend/scripts/price_scam_eval.js` from the repo root (or
`node scripts/price_scam_eval.js` from `backend/`). It reads `backend/.env`
either way.

**Result (2026-10-15): none of the 13 chat cases could be scored.** That is a
coverage and input finding, not a measure of detection.

| | cases | scored | outside coverage | input incomplete |
|---|---|---|---|---|
| scam | 6 | 0 | 3 (Kota Tinggi, Seremban, Johor) | 3 |
| legit | 7 | 0 | 4 | 3 |

- **Legit, outside coverage:** Serdang (Kedah), Penang, and Kampung Baru (in
  KL, but not in the area list). Subang Jaya common room is the fourth: the
  area is covered but there is no room stratum for it.
- **Input incomplete:** every one is `missing_input`. The chats state a rent
  but no usable area, or no room type for a room.

### Narrative — `narrative`
A plain-language explanation of the finished result, in both languages,
written by an LLM after the score is set (`backend/src/services/llm.service.js`,
prompt in `backend/src/prompts/narrative.prompt.js`):

```json
"narrative": {
  "en": "This listing carries high risk. Money was requested up front. ...",
  "ms": "Iklan ini mempunyai risiko tinggi. Wang diminta terlebih dahulu. ...",
  "provider": "gemini",
  "model": "gemini-3.5-flash-lite",
  "promptVersion": "v2"
}
```

`null` when it is off, the call failed, or the text failed the check below;
the frontend then builds its explanation from the result's own fields.

- **What the model sees:** only system-made facts — band, score, components,
  red-flag labels and advice from the lexicon, price figures, OSINT counts and
  source domains. Never the chat, a snippet, a search result's text, a name or
  a phone number (the OSINT judge's rule).
- **The check:** a text is dropped when it names a band other than
  `riskBand` (or, when capped, `bandCap.uncappedBand`), writes a number that is
  not in the facts, or is empty or over 1,200 characters.
- **Provider:** the OSINT judge's (`LLM_VERIFIER_PROVIDER`, `GEMINI_MODEL` /
  `ANTHROPIC_MODEL`) unless `NARRATIVE_PROVIDER` names another;
  `LLM_NARRATIVE=false` turns it off. 15 s budget, one retry after a 5xx,
  cached 7 days under `narrative:<prompt version>:<provider>:<model>:<SHA-256 of the facts>`.
- **Backfilled:** results saved before the narrative existed can be given one
  with `backend/scripts/narrate_results.js`, which writes only `narrative` and
  adds `backfilled: true`.

### `GET /listings/:id`
Fetch a stored analysis row by `listingId`.

---

## NLP service (FastAPI) — base `http://localhost:8000` (internal)

### `POST /classify`
```json
{ "text": "...", "language": "auto" }
```
→
```json
{
  "scam_probability": 0.9997,
  "normalised_text": "pemilik: bayar deposit dahulu ...",
  "red_flags": ["pay_before_viewing", "upfront_payment"],
  "layer1": {
    "evidence": [ { "id": "pay_before_viewing", "severity": "critical",
                    "label_en": "...", "label_ms": "...", "advice_en": "...",
                    "snippet": "...", "speaker": "owner" } ],
    "patterns": [ { "id": "refundable_hold_lure" } ],
    "legit_signals": [], "legit_signals_withheld": [],
    "suppressed": [], "entities": {},
    "clean_text": "...", "token_count": 88
  },
  "layer2": {
    "scam_probability": 0.9997, "model_probability": 0.9997,
    "turns": 11, "confidence": "high", "status": "ok",
    "model": "xlm-roberta-base"
  }
}
```

The two layers run concurrently and are independent: `layer1` is evidence for
the narrator and contributes **nothing** to `scam_probability`, which comes from
the model alone. `layer2.status` is `ok`, `insufficient_context` (fewer than 6
messages) or `model_unavailable`; in the latter two `scam_probability` is 0.5
meaning *unknown*, and the backend excludes it from the risk score.

**Long conversations are not truncated.** The text is scored in windows of up
to 512 tokens, cut only between messages and about 256 tokens apart, and
`scam_probability` is the highest window. The first
model was served with a 256-token cut, which showed it only 35–39% of a real
legitimate conversation (`nlp-service/eval/results/length_mismatch.json`).

**Calibration.** A checkpoint may carry `calibration_temperature` in its
`config.json`, fitted after training; logits are divided by it before softmax.
It moves scores toward or away from 0.5 but never across it, so no verdict
changes. The deployed checkpoint (retrain run 1) carries 0.731, which sharpens
scores: 0.88 raw becomes 0.94 as served.

**Links are never rewritten by the normaliser.** Tokens shaped like a link
(`go.ibilik.com`, `www…`, `https://…`, an email) and the token right after a
link cue (`go to:`, `goto:`, `link:`, `url:`, `website:`) are left as written:
OCR read "go.ibilik.com" as "cm", which the slang dictionary expanded to
"macam". This affects `normalised_text` and layer 1 only; layer 2 reads the raw
text.

**`legit_signals` are context, not reassurance.** Measured on the corpus
(`eval/results/legit_signal_rates.json`), every legitimacy signal that fires at
all fires more often on scams — scammers imitate a proper letting. So when any
red flag fires, legitimacy language is moved to `legit_signals_withheld` with a
reason, and even then the remaining signals appear on 5.4% of scams and 5.7% of
legitimate conversations. A client must not present them as evidence of safety.

### `POST /ocr`
`multipart/form-data`, field `files` — repeatable, so a chat spanning several
screenshots can be sent in one request. Attach one `files` entry per page,
max 20. This is the only accepted field name.

Pages are OCR'd and stitched **in upload order** (not filename order) into one
conversation. An unreadable page yields `ok: false` for that page rather than
failing the request.

```json
{
  "extracted_text": "Renter: ...
Owner: ...",
  "page_count": 3,
  "turns": 11,
  "method": "bubbles",
  "messages": [ { "speaker": "Renter", "text": "..." } ],
  "pages": [
    { "filename": "p1.png", "extracted_text": "...", "characters": 103, "ok": true }
  ]
}
```

**Text printed inside photos is dropped** — e.g. a camera's date-and-place
stamp on a room photo, which OCR otherwise reads as a message. A line is kept
only if its background is within 15 (mean absolute RGB) of either speaker's
bubble colour, taken across the whole upload; measured on the real screenshots,
typed lines (quote boxes and link previews included) lie within 11.1, the photo
stamp at 18.3–24.7. If a speaker's colour is not clearly established — their
text is not at least twice that of any other colour attributed to them — none of
their lines is dropped: losing a real message is worse than keeping a stamp.

`method` says how the text was assembled:

| `method` | how | `turns` is |
|---|---|---|
| `bubbles` | chat bubbles found in the image by their fill colour; speaker from the bubble's colour (green/tinted = `Renter`, the sender; white/grey = `Owner`); timestamps and page chrome removed; overlapping bubbles at page seams de-duplicated | the number of bubbles |
| `text` | fallback when no bubbles are found: plain OCR text per page, stitched | messages counted by `app/turns.py` |

`turns` over-counts somewhat on real screenshots: 29 against a hand count of 25
on a four-page scam, 42 against 34 on an eight-page legitimate chat
(`nlp-service/eval/results/bubble_segmenter.json`). Both are far above the guard,
so it does not change a verdict there; on a 5–7 message chat it could lift the
confidence band by one step. Layer 2 needs 6 to score at all, so a caller can
use `turns` to ask for more screenshots before classifying.

Speaker labels assume the uploader is the renter — the person whose own
messages are the coloured bubbles.

---

## Scoring formula (deterministic)

```
score = round( scamProbability*60 + osintRiskFraction*25 + priceAnomalyFraction*15 )
band  = LOW 0–24 · MODERATE 25–49 · HIGH 50–74 · CRITICAL 75–100
```
A signal that could not be scored is excluded, not redistributed:
`maxPossibleScore` falls by its weight. With nothing scored, `riskScore` is
`null` and `riskBand` is `UNKNOWN`. `osintRiskFraction` is the source-tier
points / 25 described under [OSINT](#osint--evidenceosint);
`priceAnomalyFraction` is the price tier's points / 15 described under
[Price](#price--evidenceprice).
The LLM narrative is generated **from** this score and can never change it.

### Bands and the boundary rule

| band (API) | shown as | score |
|---|---|---|
| `LOW` | Low | 0–24 |
| `MODERATE` | Medium | 25–49 |
| `HIGH` | High | 50–74 |
| `CRITICAL` | Very High | 75–100 |

Each band starts at its threshold, so a score of exactly 25, 50 or 75 goes to
the **higher** band. Recall comes first: a missed scam costs the renter money,
while a false alarm only costs them a check. Module maximums, from the code:
NLP 60 (`SCORE_WEIGHTS.nlp`), OSINT 25 (news 12 + forum 8 + social 5, each tier
scored once), and price 15 (top tier).

**Design revision (from FYP1).** FYP1 set the bands at 0–25 / 26–50 / 51–75 /
76–100 and said Very High required all three modules. That statement was wrong
even with the cut at 76: NLP and OSINT alone reach 60 + 25 = 85. The Very High
cut was moved to 75 for two reasons:

- **At 76, Very High needs OSINT.** NLP and price together top out at
  60 + 15 = 75. A scammer using a new phone number has no complaints for OSINT
  to find, so Very High was almost unreachable for them. At 75, NLP and price
  can reach it without OSINT, but only when both are at their maximum: a model
  probability of at least 0.9917 (60 points after rounding), the top price tier
  (more than 45% below the area median, or under the rent floor), and at least
  one red flag (without one, the band cap holds the result at `MODERATE`). No
  blind-test case reached that probability; the highest was 0.986.
- **Consistency with the boundary rule.** All three thresholds sit on a quarter
  of the scale (25 / 50 / 75), and each band starts at its threshold.

How the thresholds hold up on data (ROC, with 95% confidence intervals):
[MODEL_EVALUATION.md §4.10](MODEL_EVALUATION.md#410-risk-band-thresholds-roc).
