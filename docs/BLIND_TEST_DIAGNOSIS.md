# Blind test diagnosis — legitimate iBilik conversation

True label **LEGITIMATE**. Hand count **34** text messages
(p1 3, p2 3, p3 3, p4 6, p5 9, p6 5, p7 3, p8 2). Pages not contiguous; gaps
between p1–p2 and p4–p5.

System output: **7 messages stitched, 76 per page, p(scam) 0.9995, HIGH, zero
red flags, no message to the renter.**

No code was changed to produce this document.

> **Where this copy comes from.** Written in
> `nlp-service/eval/results/blind_legit/diagnosis/`, which is gitignored because
> the raw outputs beside it contain personal data from the screenshots. This
> copy contains none. The scripts and files it mentions live in that folder.
> The numbers here describe the system **as it was at the blind test**; what was
> changed in response is in `MODEL_COMPARISON.md` §14.

---

## 1. The counter

### Root cause: a threshold flips the whole strategy

`split_messages()` picks one of three branches:

```
speaker labels present        -> by_speaker_label
>= 2 lines ending in a clock  -> by_timestamp
otherwise                     -> by_line
```

This conversation has **no speaker labels**, so the choice comes down to how
many lines end in something the code recognises as a clock. That count is tiny
here, and it sits either side of the threshold depending on how much text is
being looked at:

| input | lines | lines ending in a clock | branch | result |
|---|---|---|---|---|
| each page alone | 12–34 | 0–4 | `by_line` on 6 of 8 pages | **76** |
| all 8 stitched | 170 | 7 | `by_timestamp` | **7** |

The same text, the same code, a 10× difference — decided by whether a count
crosses 2. That is the root cause, and both failure directions follow from it:

- **`by_line` overcounts.** One message per surviving line, so every wrapped
  line of a long bubble becomes its own message.
- **`by_timestamp` undercounts.** Lines accumulate in a buffer and are only
  flushed when one ends in a clock. With 7 flush points across 170 lines, the
  output is 7 messages, one of them 865 characters long.

### Why so few clocks are detected

The fixtures this was built against are Android, 24-hour, and OCR read them as
digits (`1808`, `17684 W`). This is iOS, 12-hour, and OCR read the timestamps as
**words**: `pate`, `nasi`, `samy`, `sores`, `gion yy`, `eyes`, `ary,`,
`yaya, w`, `ceonen`, `oiras`, `ye`. A pattern looking for digits cannot see any
of those, so nearly every bubble boundary is invisible.

### Page by page

| page | hand | mine | diff | branch | what did it |
|---|---|---|---|---|---|
| p1 | 3 | 19 | **+16** | `by_line` (0 clocks) | Listing card, encryption notice, URL and every wrapped line counted separately |
| p2 | 3 | 6 | **+3** | `by_line` (1 clock) | Album caption and camera watermark lines counted separately |
| p3 | 3 | 3 | 0 | `by_timestamp` (4 clocks) | Correct by luck — enough clocks survived |
| p4 | 6 | 2 | **−4** | `by_timestamp` (2 clocks) | Only 2 flush points for 6 bubbles; four messages absorbed |
| p5 | 9 | 25 | **+16** | `by_line` (1 clock) | The promo bubble alone is ~20 lines, each counted |
| p6 | 5 | 8 | **+3** | `by_line` (1 clock) | Quote headers and PDF card lines counted |
| p7 | 3 | 6 | **+3** | `by_line` (0 clocks) | PDF preview and sticker text counted |
| p8 | 2 | 7 | **+5** | `by_line` (0 clocks) | Sticker text, date separator, PDF card counted |

### Which stage lost what, stitched

| stage | lines / messages | effect |
|---|---|---|
| raw across 8 pages | 174 lines | — |
| chrome removal by repetition | 170 lines | **−4 only.** iOS headers differ per page (`8:36 a 72>` vs `837% Poe` vs `8:39 a ow)`), so the repetition test almost never fires. On the Android scam set the header was identical on every page and this worked. |
| grouped by timestamp | 7 | **the collapse.** 7 flush points. |
| de-duplication | 7 | **−0.** The clumps are all unique, so there is nothing to match. |
| prefix trimming | 7 | **−0.** Same reason. |
| wrap merging | n/a | Not reached — it lives in `by_line`, which the stitched text does not use. |

So of the five mechanisms, **only timestamp grouping did anything**, and it did
the damage. Chrome removal, de-duplication and prefix trimming were all inert
because each was built against the Android fixture's shape.

### What this says about the earlier 25/25 result

The scam set matched the hand count exactly. That was not a general counter
working — it was a counter fitted to one Android screenshot's characteristics:
identical page headers, digit-readable 24-hour clocks, `Anda` quote markers. On
an iOS conversation with 12-hour clocks and per-page headers, every one of those
assumptions fails at once.

---

## 2. Model failure vs OCR failure — **the model is wrong, not the OCR**

The 34 messages were transcribed by hand from the images (`transcript_a`,
`transcript_b`; names, phone number and room address redacted) and scored.

| input | model_probability | messages |
|---|---|---|
| OCR stitched text | 0.9995 | 7 |
| Clean transcript, no speaker labels | **0.9997** | 33 |
| Clean transcript, `Renter:`/`Owner:` labels | **0.9997** | 34 |

**The clean transcript scores higher than the OCR mess.** Perfect input, correct
message boundaries, correct speaker attribution — and the model is *more*
confident this legitimate conversation is a scam.

OCR quality is not the cause and fixing OCR cannot fix this. The model is wrong
on real legitimate English rental chat.

Worth noting alongside §7.4 of `MODEL_COMPARISON.md`: that showed the model
scoring a scam conversation at 0.9995 with every scam mechanic removed. This
shows it scoring a legitimate conversation at 0.9997. Taken together the model
appears to be responding to something common to both — long multi-turn rental
chat containing prices — rather than to scam content.

Side note: the labelled transcript counts **34/34** messages, because speaker
labels take the `by_speaker_label` branch, which is the only reliable one.

---

## 3. Layer 1 on the clean transcript: still **zero**

Zero red flags, zero legit signals, zero patterns, zero suppressed. On text with
no OCR damage at all.

**Normalisation is not the cause.** None of the eight evidence lines is altered
by it — the text is English and the slang map leaves it alone.

### The legitimacy rules, and why each missed

| rule | why it missed |
|---|---|
| `ren_number` | No REN quoted. Correctly absent — the agent works through a platform. |
| `registered_firm` | Wants `Sdn Bhd` or a firm number. The text says `iBilik`, a platform brand. |
| `viewing_first` | Wants *"view … dulu/first/before pay"*. The chat schedules a viewing instead: *"i plan to visit on 20/8"*, *"I'm available at either 11am or 2pm"*. The rule matches a phrasing; the conversation expresses the idea as an appointment. |
| `formal_documents` | Wants `geran`, `cukai taksiran`, `tenancy agreement`, `surat perjanjian`. The chat says *"agreement"* and *"E-Agreement"* alone. |
| `stamping_mentioned` | The PDF card does read *"Stamping Status: N/A"* — but that is inside an image, and never reaches the rules. |
| `company_account` | No account details appear in text. |

### Evidence present that no rule models at all

- **A viewing happened before any money changed hands.** The strongest signal in
  the conversation. `viewing_first` matches a phrase, not a sequence.
- **A platform-mediated e-agreement** (`go.ibilik.com`, *"E-Agreement"*,
  *"Login using your registered mobile number"*). No rule mentions platforms.
- **In-person key handover**: *"meet on 28/8 to settle balance payment and
  handover the keys"* — the exact inverse of the `key_courier` red flag, with no
  positive counterpart.
- **Payment at handover**, the inverse of `pay_before_viewing`. Not rewarded.
- **Itemised written costs** with no pressure to pay. Weak alone — scammers
  quote totals too — but it is evidence.

The underlying shape: **all six legitimacy rules were written for Malay,
owner-direct, document-based letting.** This is English, platform-mediated,
agent-brokered. The rules are not wrong, they are aimed elsewhere — the same
narrowness the red-flag rules showed when 14 of 26 never fired on the synthetic
corpus.

---

## 4. High model score, no evidence — options

The backend returned **HIGH (60/60), zero red flags, `message: null`**. The
renter is told a legitimate agent is high risk, with nothing to justify it.

### Option A — cap the band when layer 1 is silent

Above a threshold, a model score with no supporting red flag caps at MODERATE,
with a message saying the assessment is automated and unexplained.

*For:* directly addresses this case; keeps the number visible; cheap; reversible
per-conversation once layer 1 improves.
*Against:* caps genuine scams that layer 1 misses — and layer 1 misses 10.4% of
corpus scams. A real scam phrased unusually gets quieted exactly when the model
was right.

### Option B — require corroboration for the top bands

HIGH and CRITICAL need the model **and** at least one other signal (a red flag,
OSINT, or price). Model-only maxes at MODERATE regardless of probability.

*For:* the same principle already used for `maxPossible`; symmetric with "no
signal means UNKNOWN"; explainable as a policy rather than a patch.
*Against:* stricter than A, so more missed scams; and with OSINT and price still
stubs, *every* result would be capped today, which makes the product look
uniformly uncertain.

### Option C — report the disagreement instead of resolving it

Keep the score, add `evidenceSupport: "none" | "partial" | "corroborated"` and
show the renter: *"Our automated check flagged this, but we could not identify a
specific reason. Look for these yourself: …"*.

*For:* hides nothing and suppresses nothing; honest about a known weakness;
useful even when the model is right; no scoring change so it cannot mask a scam.
*Against:* pushes the judgement onto the renter, which is what the product is
meant to spare them; needs UI work; does not stop a wrong HIGH from frightening
someone.

### Recommendation: **C, then B when OSINT and price exist**

C is right now because the demonstrated failure is *unexplained confidence*, and
C is the only option that makes the confidence honest rather than quieter. This
conversation would still show HIGH — which is wrong — but the renter would be
told no specific reason was found, which is true and is actionable.

A and B both suppress, and suppression is the wrong instrument while the model's
failure mode is still this poorly understood: §7.4 shows it scoring a
mechanic-free scam at 0.9995 and this shows 0.9997 on a legitimate chat, so
neither a cap nor a corroboration rule is grounded in a model we can predict.

Once OSINT and price are implemented, B becomes the stronger policy: requiring
two independent signals for the top band is defensible on its own terms rather
than as a workaround.

**None of these fixes the real problem.** The model assigns 0.9997 to a
legitimate conversation on clean input. Scoring policy decides how loudly that
error is announced, not whether it is made.
