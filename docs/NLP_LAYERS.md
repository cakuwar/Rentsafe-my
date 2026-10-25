# How the NLP service works — Layer 1 and Layer 2

How RentSafe-MY's NLP service turns a rental chat into evidence and a scam
probability: what each layer does, how it was built, and why it was built that
way. Layer 2 is described for the **deployed model only**, XLM-R retrain run 1
(`nlp-service/models/xlm-roberta-scam-v3-run1`). Its full evaluation is in
`docs/MODEL_EVALUATION.md`; the development history is in
`docs/MODEL_COMPARISON.md`.

---

## 0. The one-minute version

A chat (typed, or screenshots read by OCR) goes through **two independent
layers at the same time**:

- **Layer 1 — rules.** 26 hand-written detectors find known scam tactics
  ("payment before viewing", "keys by courier", "owner is overseas"…) and
  return them as **evidence** with a bilingual explanation and the exact
  snippet. It gives **no score**. Its job is to say *why*.
- **Layer 2 — a fine-tuned transformer.** XLM-RoBERTa reads the whole chat and
  returns **P(scam)** between 0 and 1. Its job is to say *how likely*.

The backend turns P(scam) into a 0–100 risk score, then checks it against layer
1's evidence. A high score with no scam tactic behind it is held at MODERATE
and the user is told to verify. A chat too short to judge is reported as
UNKNOWN, not as safe.

```
 screenshots ──► OCR (bubbles, speakers, cleanup) ──┐
 typed text ────────────────────────────────────────┤
                                                    ▼
                                         POST /classify (NLP service)
                                 ┌──────────────────┴──────────────────┐
                    normalise (slang → standard)                 raw text, unchanged
                                 ▼                                      ▼
                  LAYER 1: rules → red flags,             LAYER 2: XLM-R run 1 →
                  evidence, tactic patterns,              P(scam), message count,
                  legitimacy context (no score)           confidence, status
                                 └──────────────────┬──────────────────┘
                                                    ▼
                         backend: score = P(scam) × 60 (+ other signals),
                         evidence check, MODERATE cap, UNKNOWN for short chats
```

---

## 1. Before the layers: getting clean text

### 1.1 Screenshots → text (`POST /ocr`, `app/ocr/`)

WhatsApp screenshots are read with Tesseract (English + Malay). Raw OCR text is
messy: timestamps, the phone's status bar, and long messages wrapped over
several lines. So the service rebuilds the chat from the image itself
(`app/ocr/bubbles.py`):

| step | what it does | why |
|---|---|---|
| find bubbles | text lines are grouped into chat bubbles by their background fill colour | one bubble = one message |
| speaker | coloured bubbles = the uploader (**Renter**); white/grey = the other party (**Owner**) | the models need to know who said what |
| remove furniture | the status bar, the contact header and the input bar are cut by position; timestamps are detected by their smaller font size | they are not conversation |
| drop text inside photos | a line whose background matches neither bubble colour is dropped (cut-off 15 RGB units; typed lines measured ≤ 11.1, a camera date stamp on a room photo 18.3–24.7) | a camera stamp was being read as a renter message |
| stitch pages | pages are joined **in upload order**; messages repeated at page seams and quoted replies are removed by fuzzy matching | one conversation from many screenshots |

Output: `Renter: …` / `Owner: …` lines. **Pages must be uploaded in
chronological order**: the service does not reorder them.

### 1.2 Counting messages (`app/turns.py`)

Layer 2 needs to know how much of the conversation it can see (§3.5). The unit
is a **message** (one bubble), not a line, because OCR wraps one message over
several lines. Message boundaries come from speaker labels if present, else
from trailing timestamps, else from line breaks.

### 1.3 Normalising Manglish for layer 1 (`app/normaliser/`)

Malaysian chat is full of shortforms ("byr dlu baru blh tgk"). Layer 1's rules
are written in standard words, so its input is normalised first:

1. lower-case and tidy whitespace;
2. expand ditto reduplication (`tiba""tiba` → `tiba-tiba`);
3. word by word: the **shortform dictionary** (`byr` → `bayar`, `xleh` → `tak
   boleh`); leetspeak (`b4` → `before`, `2day` → `today`); the `x` prefix
   (`xnak` → `tak nak`); the `2` reduplication suffix (`kawan2` →
   `kawan-kawan`, but never `rm2`).

The dictionary (`rentsafe_manglish_shortform_dictionary_v2.csv`) has 610
entries. **26 are marked ambiguous and never applied**: for example `no` (in
English, "no") and `come` (English, not `comel`), which had been destroying
English sentences. Links are never rewritten (`go.ibilik.com`, `www…`, and the
word after "go to:" / "link:").

**Layer 1 reads the normalised text; layer 2 reads the raw text.** The model was
fine-tuned on raw chats. Normalising changes words, case and line breaks, which
would move its input away from what it learned, and once cut the score of an
eight-message scam from 0.9952 to 0.0815.

---

## 2. Layer 1 — rule-based red flags (`app/layer1/red_flags.py`)

### 2.1 Purpose and principles

- **Explainable.** Layer 2 is a black box, so layer 1 is the only part of the
  verdict that can be shown to a renter as a reason. Every rule carries a label
  and advice in **Malay and English**.
- **Evidence, not a score.** Layer 1 produces no number and adds nothing to
  P(scam). Severity only orders what is shown first; it is never summed.
- **Mechanics, not phrases.** Rules describe *what the scammer does* (asks for
  money before a viewing), not the words that happen to be common in the
  dataset. The synthetic corpus comes from about 20 templates; matching its
  frequent phrases would recognise the template, not the scam.
- **Sources.** Rules were written from the labelled corpus and from real
  WhatsApp scam screenshots.

### 2.2 Anatomy of a rule

Each rule is one object (`Rule`):

| field | example (`pay_before_viewing`) |
|---|---|
| `id`, `category`, `severity` | `pay_before_viewing`, payment, **critical** |
| `patterns` (regular expressions) | money word … then/before … viewing word: `\b(?:bayar\|transfer\|deposit\|booking\|tempah\|lock)\b … \b(?:baru\|sebelum\|then\|before)\b … \b(?:view\|tengok\|lihat\|masuk\|kunci\|key…)\b`, plus 3 more patterns |
| `label_en` / `label_ms` | "Payment demanded before you can view" / "Bayaran diminta sebelum anda boleh melihat unit" |
| `advice_en` / `advice_ms` | "Never pay before seeing the unit in person…" |
| `exceptions` | `negation` |

A rule **fires** if any of its patterns matches and no exception cancels that
match.

### 2.3 The 26 rules

| category | rule | severity | exceptions |
|---|---|---|---|
| payment | `pay_before_viewing` — payment before viewing | critical | negation |
| payment | `viewing_fee` — a fee just to view | critical | negation |
| identity | `otp_tac_request` — OTP / TAC requested | critical | negation |
| channel | `third_party_account` — money to someone else's account | high | — |
| channel | `crypto_or_remittance` — crypto or overseas transfer | high | — |
| verification | `key_courier` — keys posted or couriered | high | — |
| verification | `viewing_denial` — viewing refused | high | timing, question |
| verification | `verification_refusal` — refuses to prove ownership | high | — |
| payment | `upfront_payment` — money requested up front (booking / holding fee) | medium | negation |
| channel | `personal_account` — payment to a personal account | medium | — |
| channel | `non_bank_channel` — e-wallet instead of a bank | medium | — |
| pressure | `deadline_pressure` — deadline on the payment | medium | negation, question |
| pressure | `competition_pressure` — "many people are asking" | medium | — |
| verification | `video_only_viewing` — only a video-call viewing | medium | question |
| verification | `remote_owner` — owner away or overseas | medium | — |
| verification | `meeting_avoidance` — avoids meeting in person | medium | timing, question |
| verification | `proxy_collector` — a third party collects the money | medium | — |
| identity | `selfie_with_ic` — photo holding your IC | medium | negation |
| identity | `personal_details_request` — personal details before meeting | medium | negation |
| tenancy | `agreement_irregularity` — irregular tenancy terms | medium | — |
| payment | `proof_of_payment_request` — proof of transfer demanded | medium | — |
| payment | `refund_promise` — full refund promised | low | — |
| pressure | `rush_language` — rushing language | low | question |
| pressure | `social_proof_payment` — "others already paid" | low | — |
| pricing | `too_good_text` — priced suspiciously low | low | — |
| channel | `off_platform` — moves the chat off-platform | low | — |

3 critical, 5 high, 13 medium, 5 low.

### 2.4 Exceptions — avoiding false alarms

A word list would flag good advice. Three checks cancel a match:

| exception | rule | example it cancels |
|---|---|---|
| **negation** | a negating word (*jangan, jgn, tak payah, tidak perlu, don't, never, no need to, avoid, without…*) in the **60 characters before** the match | "**Jangan** bayar sebelum tengok rumah ya" — advice, not a demand |
| **question** | the sentence ends with "?" | "urgent ke?" — the renter asking |
| **timing** | the sentence names a day or date (*hari ini, esok, hujung minggu, Sabtu, this week…*) | "tak boleh tengok hujung minggu" — a busy landlord, not a refusal |

Cancelled matches are not thrown away: they are returned in `suppressed` with
the reason, so it is always possible to see why something did not fire.

### 2.5 Tactic patterns — combinations that name the scam

A single flag is weak; the combination is the scam. Four pattern rules name the
tactic when flags from two groups fire together:

| pattern | fires when | meaning |
|---|---|---|
| `refundable_hold_lure` | refund promise **+** a payment demand | the reassurance makes paying feel reversible |
| `pressure_to_pay` | deadline / competition / rush **+** a payment demand | urgency stops the renter checking |
| `absent_owner_payment` | owner away / keys by courier / no meeting / no viewing **+** a payment demand or another person's account | nobody will meet you, yet money is asked |
| `irregular_channel_payment` | third-party account / e-wallet / crypto **+** a payment demand | the money cannot be traced or reversed |

("A payment demand" = `upfront_payment`, `pay_before_viewing` or `viewing_fee`.)

### 2.6 Legitimacy signals — context, never reassurance

Ten signals recognise signs of a proper letting: a REN number, a registered
agency, a viewing offered first, documents, stamping, a company account, a
viewing arranged, keys handed over in person, payment at signing or handover,
and an agreement through a platform.

**They never lower anything.** Measured on the corpus
(`eval/results/legit_signal_rates.json`), every signal that fires at all fires
**more often on scams** than on honest chats. Scammers imitate a proper
letting: "transfer to the company account" appears in 23.1% of scams and 0% of
legitimate chats. So:

- if **any red flag fires**, legitimacy language is moved to
  `legit_signals_withheld` and is not shown as reassurance;
- otherwise it is listed as context, with a note telling the user what to
  verify (e.g. "verify the REN at lppeh.gov.my").

After this rule, any signal appears on 5.4% of scams and 5.7% of legitimate
chats: a prompt to verify, not evidence of safety.

### 2.7 What layer 1 returns — a real example

Input:

```
Renter: Boleh saya tengok rumah dulu?
Owner: Maaf saya outstation sekarang.
Owner: Kena byr booking RM300 dulu baru boleh tengok, ramai org tgh tanya.
Owner: Lepas transfer saya pos kunci.
```

Output (from the running code):

| field | value |
|---|---|
| `red_flags` (most severe first) | `pay_before_viewing` (critical), `key_courier` (high), `upfront_payment`, `competition_pressure`, `remote_owner` (medium) |
| `evidence` | one entry per flag: label and advice in BM + EN, the matched snippet with phone / IC / account numbers / links redacted (amounts kept as evidence), severity, speaker |
| `patterns` | `pressure_to_pay`, `absent_owner_payment` |
| `entities` | amount `rm300` |
| `legit_signals` | none |

And "Owner: Jangan bayar sebelum tengok rumah ya, datang Sabtu ni pukul 11."
gives **no** red flag: `pay_before_viewing` matched, but was suppressed by the
**negation** exception (listed in `suppressed`).

### 2.8 How well layer 1 works

As a stand-alone classifier ("any red flag = scam"; `eval/results/confusion_matrices.json`):

| set | scams caught | legitimate chats flagged |
|---|---|---|
| training + validation corpus | 283 of 316 (89.6%) | 17 of 158 (10.8%) |
| validation | 55 of 63 | 4 of 32 |
| new-wording minimal pairs | **32 of 72** | **0 of 72** |

Layer 1 is precise, but tied to the wording it was written for: on scams
phrased in new words it catches fewer than half. A sentence-embedding
extension was tested to close that gap and was rejected (§5).

**Tests:** `tests/test_red_flags.py` (60) — every rule fires on its examples,
ordinary rental language stays quiet, the exceptions work, corpus precision
floors, legitimacy signals and their withholding.

### 2.9 Known issues in layer 1

1. **The `speaker` field is unreliable.** The normaliser collapses line breaks,
   so layer 1 sees the whole chat as one line and attributes every flag to the
   first speaker (in the example above, all five flags say "renter" although
   the owner wrote them). The flags themselves are correct; only the
   attribution is wrong. Not yet fixed.
2. **Two dead patterns.** The normaliser rewrites "owner" to "pemilik", so
   `remote_owner`'s pattern "owner is away/busy" can never match; and
   `deadline_pressure` knows only Malay verbs, so "please **pay** before 6pm" is
   missed. Found while building the semantic-flag experiment; not yet fixed.
3. **Wording-bound** (§2.8): new phrasings of a known tactic are often missed.

---

## 3. Layer 2 — the transformer model (`app/layer2/classifier.py`)

### 3.1 What it is

| item | value |
|---|---|
| model | `xlm-roberta-base`, fine-tuned — "retrain run 1" |
| size | 278M parameters, 1.1 GB |
| task | is the whole chat a scam? → P(scam) |
| languages | multilingual (Malay, English and code-switched Manglish in one model) |

**Why XLM-R.** It was compared with a Malay-specific ELECTRA model. ELECTRA
scored higher on validation (F1 1.000 against 0.992), but on the real
screenshot path it called a real scam safe (0.0179). XLM-R separated the real
chats correctly, so it was chosen; validation alone would have picked the wrong
model.

### 3.2 Training data

**Original corpus** (`data/processed/random/`): 474 WhatsApp-style
conversations, 450 synthetic (from about 20 templates) and 24 real (8
legitimate, 16 scam), split into 379 for training and 95 for validation.

**The problem with it.** The first model fine-tuned on this corpus scored 0.99
on validation but called a real legitimate chat a scam (0.9995). It had
learned shortcuts: in the training data, a chat's length alone predicts the
label 77% of the time, and a chat with four or more prices is a scam 93% of the
time — but real agents send itemised prices too.

**The fix: minimal pairs** (`training/make_minimal_pairs.py`). Each legitimate
conversation has a **scam twin that is identical except for the scam
behaviour**: the same greeting, prices, terms and small talk, but where the
legitimate owner says *"Of course, Saturday at 11am works, I'll meet you
there"*, the scam owner says *"Sorry, I'm overseas right now so I can't open
the unit"*. Price, length and style are then useless for telling them apart, so
the model has to learn the behaviour.

| training data for run 1 | rows | scam / legit |
|---|---|---|
| original corpus, training split | 379 | 253 / 126 |
| minimal pairs (408 pairs + 58 mid-conversation fragments, minus 10% kept for model selection) | 844 | 422 / 422 |
| **total** | **1,223** | 675 / 548 |

An audit (`training/audit_training_data.py`) confirmed that no surface feature
— length, number of messages or prices, question marks, English share — still
predicts the label much better than the majority baseline.

A separate **test family** uses different sentences for the same tactics and
never appears in training: this is the main test (§3.6).

### 3.3 Training procedure (`nlp-service/train_colab_v3.ipynb`, Colab T4 GPU)

| setting | value | why |
|---|---|---|
| max input | 512 tokens | real chats are long; the first model only saw 256 |
| loss | cross-entropy with **class weights** | more scam than legitimate rows |
| **label smoothing** | 0.1 | the first model answered only 0.9997 or 0.0021 — no gradation of risk |
| optimiser | learning rate 2e-5, warm-up 10%, weight decay 0.01 | standard fine-tuning settings |
| batch | 8 × 2 accumulation steps (effective 16) | fits the T4 GPU |
| epochs | up to 8, **early stopping** (patience 2) on macro-F1 | stops before overfitting |
| model selection set | validation (95) + held-out training pairs (88) | |
| seed | 42 | reproducibility |

**Acceptance criteria were fixed before training** — so that the result could
not be judged by rules chosen to fit it:

| | criterion | run 1 |
|---|---|---|
| A1 | validation macro-F1 ≥ 0.90 | 0.9768 ✓ |
| A2 | new-wording pair accuracy ≥ 0.85 | 0.9444 ✓ |
| A3 | real legitimate chat (OCR) → legitimate | 0.7811 ✗ |
| A4 | real scam chat (OCR) → scam | 0.9559 ✓ |
| A5 | legitimate chat + itemised prices → legitimate | ✓ |
| A6 | scam with every scam line removed → legitimate | 0.5219 ✗ |
| A7 | under 50% of scores saturated | ✓ |

Two criteria failed, so run 1 was **not accepted**. It was deployed anyway, as
an **interim** model, because it beat the model it replaced on every test both
were given (3 of 9 gates → 7 of 9 at the time, 8 of 9 today). A second retrain
(run 2) changed the training data and did worse, and was discarded.

**Calibration.** After training, one number — the **temperature** (0.731) — was
fitted on the selection set and saved in the model's `config.json`. The service
divides the model's raw outputs by it, so that a probability of 0.8 means
"about 80% likely". It never changes which side of 0.5 a score falls on.

### 3.4 How a score is produced (inference)

1. **Raw text in** (not normalised, §1.3).
2. **Tokenise** with XLM-R's tokenizer.
3. **Windows.** XLM-R reads at most 512 tokens. A longer chat is split into
   windows of up to 510 tokens, **cut only between messages** (never in the
   middle of one), each starting about 256 tokens after the last, the final one
   packed back from the end. *Why between messages:* a window that ended
   mid-sentence ("…please take a screenshot and send it to") made a legitimate
   chat look like a scam (0.78); no training example ends mid-sentence.
4. **Score each window**, divide by the temperature, softmax → P(scam) per
   window.
5. **The chat's score is the highest window** — a scam is a scam if the
   evidence is anywhere in it.

Example: the real 8-screenshot legitimate chat is 731 tokens → 2 windows → the
higher of the two is its score (0.30 raw, 0.24 served).

### 3.5 Short chats: the guard and confidence levels

The model needs enough conversation. Measured on the deployed model
(`eval/truncation_sweep.py`; first *n* messages of 72 validation chats; always
answering "scam" scores 0.708):

| messages visible | 1 | 2 | 3 | 4 | 5 | **6** | 7 | 8 | all |
|---|---|---|---|---|---|---|---|---|---|
| accuracy | 0.29 | 0.32 | 0.38 | 0.54 | 0.67 | **0.79** | 0.89 | 0.90 | 1.00 |

Below 6 messages the model is worse than guessing, and it errs toward
"legitimate" — a dangerous false all-clear. So:

| messages | confidence | if the score is low | if the score is high |
|---|---|---|---|
| ≤ 5 | insufficient | replaced by 0.5, `status: insufficient_context`, "send more of the conversation" | still reported — a warning is never suppressed |
| 6 | low | reported | reported |
| 7 | moderate | reported | reported |
| ≥ 8 | high | reported | reported |

If the model files are missing, the service still answers: `status:
model_unavailable` with a neutral 0.5, which the backend leaves out of the
score.

### 3.6 How well layer 2 works (summary of `docs/MODEL_EVALUATION.md`)

| test | result |
|---|---|
| validation (95) | accuracy 0.979, macro-F1 0.977, 0 false alarms, 2 missed scams |
| **new-wording minimal pairs** (72 pairs) | accuracy 0.972, **pair accuracy 0.944**, 0 false alarms, 4 missed scams (all Malay) |
| English-only chats / benign one-liners | 10 / 10 correct / 0 of 8 flagged |
| real chats | real scam 0.956 ✓; real legitimate 0.30 ✓ (current OCR), 0.14 ✓ (transcript) |
| speed | about 0.2 s per chat on a CPU |

---

## 4. How the two layers come together (backend)

The layers run **in parallel and never feed each other**. The backend
(`backend/src/services/scoring.service.js`) combines them:

1. **Score.** `risk = P(scam) × 60` + OSINT × 25 + price × 15 (bands: LOW 0–24,
   MODERATE 25–49, HIGH 50–74, CRITICAL 75–100). A signal that cannot be scored
   is left out, not filled in.
2. **Too short to judge.** If layer 2 says `insufficient_context`, the result
   is **UNKNOWN** (grey) with "send more of the conversation" — never LOW.
3. **Does the evidence back the number?** (`evidenceSupport`)

   | model | layer 1 | result |
   |---|---|---|
   | scam | strong red flag (critical / high) | `corroborated` |
   | scam or not scam | only weaker red flags | `partial` |
   | scam | no red flag | `none` — "no specific scam tactic was found; verify the landlord and the unit before paying" |
   | not scam | strong red flag | `contradicted` — "contains warning signs, treat with caution" |
   | not scam | nothing | `consistent` |
   | — | layer 2 could not judge | `not_scored` |

4. **The MODERATE cap.** If the model says scam (≥ 0.5) but layer 1 found **no
   red flag at all**, the band is held at **MODERATE** (score at most 49). It
   is never lowered below MODERATE. With any red flag, HIGH is allowed. (An
   independent strong OSINT hit also lifts the cap — outside the NLP service.)
   Legitimacy signals never lower the band.

**Why the cap (a deliberate design change).** Originally layer 1 never touched
the result. Then the real legitimate iBilik chat scored HIGH (0.94) with zero
red flags and three legitimacy signals. The cap stops a number with nothing
behind it from being shown as a high-risk finding. The cost was measured: on
the corpus, 32 of 316 scams have no red flag and show as MODERATE instead of
HIGH (none drops lower); on scams in new wording the cost is higher (36 of 72),
because layer 1 misses new wording too.

---

## 5. Design decisions a supervisor may ask about

| question | answer |
|---|---|
| Why two layers? | The model gives a probability but cannot explain itself; rules can explain but miss new wording. Each covers the other's weakness. |
| Why doesn't layer 1 add to the score? | The model was trained on chats containing the same phrases the rules match; adding rule points would count the same evidence twice, and every new rule would silently change the model's measured accuracy. |
| Then why does it cap the band? | To stop a high score with no evidence behind it from being presented as a finding (§4). It only ever lowers to MODERATE, and only when there is no red flag at all. |
| Why raw text for the model, normalised for the rules? | The model was trained on raw chats; the rules are written in standard words (§1.3). |
| Why minimal pairs? | The first model learned the dataset's shortcuts (prices, length) instead of the scam; identical twins remove the shortcuts (§3.2). |
| Why the highest window? | A scam needs to show its tactic only once; averaging would dilute it. |
| Why a 6-message minimum? | Measured: below 6 the model is worse than guessing and errs toward "safe" (§3.5). |
| Was a second (zero-shot) model tried? | Yes, as a planned "calibration" model. With rules fixed beforehand, it could not tell scam from legitimate (pair accuracy 0.0) and was 20× slower; dropped. Calibration is done by the temperature instead. |
| Was meaning-based matching tried for layer 1? | Yes: sentence embeddings (e5-base and a Malaysian model). They match sentence *form*, not meaning ("tak boleh bela haiwan" — no pets — matched "viewing refused"); dropped. |
| Is the model accepted? | Not by its own pre-set criteria (2 of 9 failed). It is deployed as an interim model because it beats the previous model everywhere. |

---

## 6. Limitations

1. **No independent real test set.** Only two real chats exist outside
   training, and both were used during development. `data/test_real/` is
   reserved for this but empty.
2. **Mostly synthetic data** (95%); only 8 real legitimate conversations.
3. **Malay is the weakest language** for the model, and the rules are tied to
   the wording they were written for.
4. **The real legitimate chat is right by a narrow margin** — it depends on
   which messages share a window.
5. **Layer 1 known issues** (§2.9): speaker attribution, two dead patterns.

---

## 7. Where everything lives

| part | file |
|---|---|
| API (`/classify`, `/ocr`) | `nlp-service/app/main.py` |
| OCR and bubble segmentation | `nlp-service/app/ocr/ocr.py`, `nlp-service/app/ocr/bubbles.py` |
| message counting | `nlp-service/app/turns.py` |
| normaliser and dictionary | `nlp-service/app/normaliser/` |
| layer 1 rules | `nlp-service/app/layer1/red_flags.py` |
| layer 2 inference | `nlp-service/app/layer2/classifier.py` |
| layer 2 training | `nlp-service/train_colab_v3.ipynb`, `nlp-service/training/` |
| deployed model | `nlp-service/models/xlm-roberta-scam-v3-run1/` (not in git) |
| evaluation scripts / results | `nlp-service/eval/`, `nlp-service/eval/results/` |
| scoring, evidence check, cap | `backend/src/services/scoring.service.js` |

Tests: 335 in the NLP service (`cd nlp-service && pytest`), including the layer
1 rules (60), layer 2 (53), the normaliser (124), message counting (21) and OCR
(21).
