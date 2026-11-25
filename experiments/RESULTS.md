# RentSafe MY: extra experiments for the dissertation

Status on 2026-11-10:
- **E1–E4 are complete.** You ran E4 yourself on 2026-11-09, 23:47–00:13.
- **E5 is complete.** You ran it on 2026-11-10, 10:59–11:09.

This folder holds scripts, the frozen prompt and result tables only. Nothing in it contains chat text. Transcripts, anonymised texts, overlap snippets and the price working copies are in `~/rentsafe_experiments_data/`, outside the repo.

## Setup and safety

- **Proof that nothing changed:**
  - `proof/preflight.txt` holds git status, HEAD and the SHA-256 of all 46 model and price-baseline files.
  - `proof/postflight.txt` repeats the check.
  - The only git change is the untracked `experiments/` folder.
- **Python:** the existing `nlp-service/.venv` (scikit-learn 1.5.2, numpy 1.26.4, pandas 2.2.3), run with `-I -B`, so no bytecode is written into the repo. Nothing was installed into it. No `experiments/.venv` was needed: E4 uses Python's own HTTP client, not the `openai` package.
- **Git and Docker:**
  - **`experiments/` is not ignored by `.gitignore`**; it shows as untracked. `experiments/.venv/` would be ignored by the existing `.venv/` rule.
  - There is no root `.dockerignore`. The compose builds use `./backend`, `./nlp-service` and `./frontend` as contexts, and `nlp-service/.dockerignore` is an allowlist, so `experiments/` cannot enter an image.
  - `.gitignore` and `.dockerignore` were not edited.
- **What was not touched:** no container, service or database was started, stopped or contacted. The only API calls were E4's 254, run by you after the cost gate.
- **Data:**
  - Run 1's rebuilt data (`~/rentsafe_experiments_data/run1_data/`, copied from `~/electra_colab/data/` and verified by SHA-256): train 1,223 rows (675 scam / 548 legit) and dev 183 (95 validation + 88 pair rows).
  - Run 1's own pair test split: 166 rows (72 full + 11 fragment pairs).
  - "New wording, 144": the 72 full pairs of the split behind Figure 4.3.
  - The 9 gates.

### Blind-test transcripts

The blind test sent screenshots only, and its saved results keep no chat text. The 15 transcripts were therefore **regenerated from the case screenshots with the project's own OCR code**, called exactly as `POST /ocr` does (`scripts/e1_make_transcripts.py`).
- That code has not changed since the blind test: the only later commit on `app/ocr`, `app/turns.py` and `app/main.py` touched `main.py` only.
- **All 15 message counts match those recorded in the blind test** (50, 33, 17, 14, 17, 34, 45, 18, 11, 28, 12, 14, 153, 62, 34): `results/e1/transcripts_check.json`.
- No model was loaded.

## E1. Near-duplicate check

### Method

Fixed in `scripts/e1_near_duplicates.py` before any result was seen:
- **Compared against:** 1,406 training items, which are the 474 corpus conversations plus run 1's 932 pair rows.
- **Preprocessing:** speaker labels are removed before comparing, because "Renter:" and "Owner:" occur in every text.
- **Measures:** character 3–5-gram TF-IDF cosine; share of the case's word 8-grams found in the item; longest run of consecutive shared words.
- **Flag:** cosine ≥ 0.80, containment ≥ 0.20, or a run of ≥ 15 words.

### Results

| Case | Truth | Origin | Words | Max cosine | Max 8-gram containment | Longest run (words) | Flagged | Most similar item (cosine) |
|---|---|---|---|---|---|---|---|---|
| 1 | Scam | real | 371 | 0.132 | 0.000 | 3 | no | corpus:val:64 (synthetic) |
| 2 | Scam | real | 229 | 0.150 | 0.000 | 2 | no | pairs:MP0092-F:SCAM (minimal pair) |
| 3 | Legit | role-play | 119 | 0.135 | 0.000 | 3 | no | pairs:MP0006:SCAM (minimal pair) |
| 4 | Legit | role-play | 98 | 0.133 | 0.000 | 3 | no | corpus:train:97 (synthetic) |
| 5 | Scam | real | 133 | 0.173 | 0.000 | 4 | no | pairs:MP0263:LEGIT (minimal pair) |
| 6 | Scam | real | 161 | 0.132 | 0.026 | 11 | no | corpus:val:88 (synthetic) |
| 7 | Scam | real | 305 | 0.122 | 0.000 | 3 | no | pairs:MP0084:LEGIT (minimal pair) |
| 8 | Scam | role-play | 117 | 0.148 | 0.000 | 3 | no | pairs:MP0232:SCAM (minimal pair) |
| 9 | Legit | role-play | 148 | 0.215 | 0.000 | 5 | no | pairs:MP0186:LEGIT (minimal pair) |
| 10 | Scam | real | 136 | 0.106 | 0.000 | 3 | no | corpus:train:228 (synthetic) |
| 11 | Legit | role-play | 111 | 0.141 | 0.000 | 3 | no | pairs:MP0002:LEGIT (minimal pair) |
| 12 | Scam | real | 160 | 0.213 | 0.000 | 5 | no | corpus:train:200 (real) |
| 13 | Scam | real | 760 | 0.158 | 0.003 | 9 | no | corpus:train:200 (real) |
| 14 | Scam | real | 451 | 0.147 | 0.000 | 3 | no | pairs:MP0229:LEGIT (minimal pair) |
| 15 | Legit | role-play | 178 | 0.170 | 0.000 | 3 | no | pairs:MP0006:LEGIT (minimal pair) |

Reference pairs (cases known to share a script):

| Pair | Cosine | Containment (a in b / b in a) | Longest run (words) |
|---|---|---|---|
| 2 and 6 | 0.095 | 0.000 / 0.000 | 2 |
| 2 and 10 | 0.051 | 0.000 / 0.000 | 1 |
| 6 and 10 | 0.193 | 0.065 / 0.077 | 17 |
| 12 and 13 | 0.275 | 0.144 / 0.029 | 18 |

Across all 105 pairs of blind cases, only 12–13 and 6–10 share more than 4 consecutive words.

**Reading:**
- **No blind case is a near-duplicate of any training item.** The highest figures are 0.215 cosine (case 9), 0.026 containment and an 11-word run (case 6), all well below the flags.
- They are also below what the shared-script pairs 6–10 and 12–13 reach on containment and run length (up to 0.144 and 18 words).
- The longest runs with training are stock phrases, not copied conversations: an itemised price list (case 6) and a tenant-details request form (cases 12 and 13).
- **Case 2 shares no text with cases 6 or 10** (runs of 1–2 words). Their link is the tactic, not the wording.
- **The 0.80 cosine flag is far above anything observed,** even for pairs that do share text. At this level, cosine reflects topic and register more than copying.
- The redacted overlapping text is in `~/rentsafe_experiments_data/e1/overlaps.md`.

## E2. TF-IDF + logistic regression baseline

### Settings

Fixed in `scripts/e2_tfidf_lr.py` before any result was seen:
- **Features:** word 1–2-gram plus character 3–5-gram TF-IDF on the raw text (scikit-learn defaults, including lowercasing).
- **Model:** logistic regression with `class_weight="balanced"`, liblinear, seed 42.
- **Choice of C:** C in {0.1, 1, 10} chosen on dev macro-F1, with ties going to the smaller C. Threshold 0.5.
- **Variants:** A trains on the 379 corpus rows; B trains on run 1's 1,223 rows.
- **Scoring:** the classifier scores each whole transcript. Run 1 takes the highest score over its message windows.

**Cautions:**
- The 95 validation rows are part of dev, so validation scores are in-sample for the choice of C, as they are for run 1's early stopping.
- Both variants chose C = 10, the edge of the fixed grid. Dev macro-F1 for C = 0.1 / 1 / 10 was 0.791 / 0.828 / 0.863 for A and 0.994 / 0.994 / 1.000 for B.
- Re-run with scikit-learn 1.5.2, the results are identical to a first run with 1.9.1, apart from the order of features with equal weights.

### Results

| | A: TF-IDF+LR, corpus only | B: TF-IDF+LR, run 1 data | XLM-R run 1 (deployed) |
|---|---|---|---|
| Validation accuracy / macro-F1 (95) | 1.000 / 1.000 | 1.000 / 1.000 | 0.979 / 0.977 |
| New wording (144): accuracy | 0.556 | **0.972** | 0.972 |
| New wording: **pair accuracy** (72) | 0.111 (8) | **0.944 (68)** | 0.944 (68) |
| New wording: MCC / ROC-AUC | 0.134 / 0.676 | 0.946 / 1.000 | 0.946 / 1.000 |
| New wording pair accuracy, en / mix / ms | 0.130 / 0.160 / 0.042 | 0.957 / 1.000 / 0.875 | 1.000 / 1.000 / 0.833 |
| Errors on new wording | 52 missed scams, 12 false alarms | 4 missed (3 Malay, 1 English), 0 false alarms | 4 missed (all Malay), 0 false alarms |
| Run 1's split (166): row accuracy | 0.602 | 0.982 | – |
| Run 1's split: full-pair accuracy (72) | 0.236 (17) | 0.958 (69) | 0.944 (68) |
| Run 1's split: fragment pairs (11) | 0 / 11 | 11 / 11 | 11 / 11 |
| Gates passed (of 9) | 7 | 8 | 8 |
| Gates failed (raw P(scam)) | real_legit_production 0.54, real_legit_clean 0.56 | ablation_mechanics_removed 0.76 | ablation_mechanics_removed 0.53 |
| **Blind: scams caught** (10) | 9 (90%; 95% CI 60–98%) | 8 (80%; 49–94%) | 10 (100%; 72–100%) |
| **Blind: false alarms** (5) | 4 (80%; 38–96%) | 1 (20%; 4–62%) | 1 (20%; 4–62%) |
| Blind ROC-AUC (extra, not in the plan) | 0.50 | 0.88 | 0.94 |

Context: on the same 144 rows, the original XLM-R (379 rows) scored 0.444 accuracy and 0.069 pair accuracy, and ELECTRA v2 scored 0.549 and 0.097.

Run 1's sources:
- **Validation and run 1's split:** `v3_run1_printout.txt`.
- **New wording:** `confusion_matrices.md` and `docs/MODEL_EVALUATION.md` §4.2.
- **Gates:** `gates_xlm-roberta-scam-v3-run1.json`.
- **Blind:** `data/test_real/cases/results.csv`, as recorded.

### Blind test per case (P(scam); "wrong" means the wrong side of 0.5)

| Case | Truth | Origin | TF-IDF A | TF-IDF B | XLM-R run 1 |
|---|---|---|---|---|---|
| 1 | Scam | real | 0.73 | 0.69 | 0.98 |
| 2 | Scam | real | 0.56 | 0.67 | 0.98 |
| 3 | Legit | role-play | 0.32 | 0.35 | 0.02 |
| 4 | Legit | role-play | 0.57 **wrong** | 0.28 | 0.01 |
| 5 | Scam | real | 0.51 | 0.49 **wrong** | 0.91 |
| 6 | Scam | real | 0.66 | 0.73 | 0.89 |
| 7 | Scam | real | 0.44 **wrong** | 0.61 | 0.96 |
| 8 | Scam | role-play | 0.84 | 0.89 | 0.98 |
| 9 | Legit | role-play | 0.77 **wrong** | 0.21 | 0.95 **wrong** |
| 10 | Scam | real | 0.55 | 0.91 | 0.99 |
| 11 | Legit | role-play | 0.81 **wrong** | 0.73 **wrong** | 0.43 |
| 12 | Scam | real | 0.91 | 0.81 | 0.98 |
| 13 | Scam | real | 0.55 | 0.48 **wrong** | 0.98 |
| 14 | Scam | real | 0.71 | 0.60 | 0.91 |
| 15 | Legit | role-play | 0.56 **wrong** | 0.24 | 0.01 |

**Reading:**
- **The pair test and the gates show no gap between models trained on the same data.** On the synthetic new-wording pairs, the deployed transformer and a linear n-gram model trained on the same data are indistinguishable (pair accuracy 0.944 for both; 8 of 9 gates, failing the same gate). So the gain from about 0.07 to 0.94 is explained by the minimal-pair data rather than by the transformer, and the pair test cannot separate the two architectures.
- **The blind test shows a gap.** On the 15 blind cases, which are mostly real conversations, run 1 is ahead: it catches 10 of 10 scams against 8 of 10, with one false alarm each, and its ROC-AUC is 0.94 against 0.88. The linear model's scores for real scams cluster near 0.5–0.7, and its two misses (cases 5 and 13) sit just under the threshold.
- **The gap is small and uncertain.** It is two scams out of ten, and the Wilson intervals overlap almost entirely, so it is a sign rather than evidence.
- **Variant A's scores hover around 0.5** on real chats (AUC 0.50). A model trained on the original corpus alone does not discriminate on real conversations.
- **Variant B's strongest features are tactic words** (towards scam "dulu", "transfer", "booking dulu", "refund", "reserve"; towards legitimate "sign", "meet", "jumpa", "no booking"): `results/e2/top_features.md`.

### The two blind scams that variant B missed

This diagnosis was made after the result (`scripts/e2_blind_misses.py`, `results/e2/blind_misses.json`). It changes nothing in E2.

| Case | Language | Scam type | B's P(scam) | Best 15-message window |
|---|---|---|---|---|
| 5 | English | Tenancy takeover. A "current tenant" leaving early asks the renter to take over her deposit and pay the rent to her, and keeps the landlord out of it | 0.49 | 0.63 |
| 13 | Casual northern Malay (Penang) | Deposit-first. The forwarded 7-step script also seen in case 12, inside a 14-page, 153-message chat spread over several days | 0.48 | 0.90 |

- **Case 5: the tactic is not in the training data.** The minimal pairs cover viewing refused, pay first, keys by courier, urgency and a third party's account, but not a tenancy takeover. The weights that pushed the case towards scam came from common function words. Its takeover wording ("moving", "over", "this weekend") pushed it towards legitimate. No layer 1 rule fired on this case either.
- **Case 13: dilution.** The windows that contain the forwarded script score 0.88–0.90. The whole chat scores 0.48, because the scam messages are a small share of a long, ordinary house-hunting conversation. A TF-IDF vector of the whole text averages over all of it, whereas run 1 scores message-aligned windows and takes the highest.
- **Diagnostic only:** if variant B also took its highest window, it would get 14 of 15 cases right, with only the case 11 false alarm left. This was not part of the plan and is not a result to report as one.

## E3. Price baseline without the 266 scraped listings

### Method

- **Working copies:** the raw files and the project's build and leave-one-out scripts were copied to `~/rentsafe_experiments_data/e3_price/{full,no_scraped}/`, outside the repo. The leave-one-out code ran with a stub database module that refuses any query (`scripts/e3/pool_stub.js`). Setup: `scripts/e3/README.md`.
- **Reproduction first:** the copy's `baseline_listings.csv` and both seed SQL files are **byte-identical** to the repo's. The figures match exactly:

| Figure | Reproduced |
|---|---|
| Whole-unit listings scored | 12,550 of 13,998 |
| Flagged | 1,070 (8.53%): 809 at 10 points, 261 at 15 |
| Scorable whole-unit strata | 313 |
| Scorable room strata | 14 |

- **Variant (`scripts/e3/run_no_scraped.py`):** the project's build ran unchanged, except that the scraped source returns no rows. **The time factor is held at 1.20,** because it is estimated from buildings listed in both the scrape and Kaggle and cannot be recomputed without the scrape.

### Results

| | Current baseline | Without the scrape |
|---|---|---|
| Pooled listings (Kaggle / scraped / manual) | 14,106 (13,744 / 266 / 96) | 13,848 (13,752 / 0 / 96) |
| Whole-unit listings in the leave-one-out | 13,998 | 13,764 |
| Scored | 12,550 | 12,324 |
| Flagged (false positives) | 1,070 (8.53%) | 1,036 (8.41%) |
| at 10 / 15 points | 809 / 261 | 788 / 248 |
| Saved by the p25 guard | 29 | 18 |
| Scorable whole-unit strata | 313 of 698 | 307 of 690 |
| Room listings / scored / flagged | 102 / 89 / 6 (6.74%) | 84 / 64 / 5 (7.81%) |
| Scorable room strata | 14 of 19 | 14 of 14 (the same 14) |

- **Kaggle rows:** 8 Kaggle rows return, because they had been dropped as duplicates of scraped listings.
- **Whole-unit strata:** six lose eligibility and none gain it. The six are Cheras (KL) studio, Damansara Perdana 2-bedroom, Kelana Jaya 3-bedroom, Pantai 2-bedroom, Segambut 1-bedroom and Setapak studio, all condos. Of the strata that stay eligible, 40 change median. Most move by under 10%, but Damansara Heights 2-bedroom condo falls from RM5,290 to RM2,369 (`results/e3/strata_changes.json`).
- **Room strata:** four room medians change: Cheras common RM720 → 690, Puchong common 600 → 550, Seri Kembangan master 955 → 950 and Setapak common 700 → 600.

### Blind cases re-scored with the production scorer (`results/e3/rescore_blind.json`)

| Case | Stratum | Price | Current: median, n (buildings), deviation, points | Without scrape |
|---|---|---|---|---|
| 3 | Shah Alam, common room | RM400 | 715, 6 (6), 0.44, **10** | 715, 6 (6), 0.44, **10** |
| 4 | Petaling Jaya, studio condo | RM1,100 | 1,320, 20 (7), 0.17, **0** | 1,320, 20 (7), 0.17, **0** |
| 5 | Subang Jaya, common room | RM500 | 750, 8 (8), 0.33, **0** (p25 guard) | 750, 8 (8), 0.33, **0** (p25 guard) |
| 12 | Shah Alam, common room | RM450 | 715, 6 (6), 0.37, **10** | 715, 6 (6), 0.37, **10** |
| 14 | Setapak, master room | RM700 | 1,000, 8 (7), 0.30, **10** | 1,000, 6 (6), 0.30, **10** |

The "current" column matches the blind test's recorded values for all five cases.

**Reading:**
- Removing the scraped listings changes little. The false-positive rate moves from 8.53% to 8.41%, six whole-unit strata drop out, and no blind-test result changes.
- What the scrape does provide is the 1.20 time factor. Without it, there is no current-market reference for adjusting the older Kaggle prices.

## E4. GPT-4o-mini zero-shot baseline

### Set-up

- **Prompt and settings:** frozen in `prompts/e4_prompt.json`, SHA-256 `485edc00…8d46d2`, recorded before any call. The run used exactly this file, because the runner checks the hash.
  - Settings: gpt-4o-mini (served as `gpt-4o-mini-2024-07-18`), temperature 0, JSON mode, seed 42, max 60 output tokens.
  - Decision rule: P(scam) ≥ 0.5 is scam. The label and P(scam) never disagreed.
- **Anonymisation:** `scripts/anonymise.py` was applied to every text.
  - Names come from three places: the project's `redact.txt`, the blind-test agent forms, and a private extra list built by reviewing the blind transcripts (outside the repo).
  - Other patterns: names after honorifics, street addresses, emails, URLs, REN, IC, phone and account numbers.
  - Before the run, the review found three names and four street addresses (in cases 6, 7, 13 and 14) that the patterns missed, and one over-match ("puan" inside "perempuan"). All were fixed.
  - 46 texts had replacements (8 of the 15 blind cases).
- **Where outputs are:** the texts sent and the raw replies are in `~/rentsafe_experiments_data/e4/`; the metrics are in `results/e4/e4_results.json`.

### Run

You ran it on 2026-11-09, 23:47–00:13.

| | |
|---|---|
| Calls | 254 (95 validation + 144 new wording + 15 blind), all answered on the first attempt |
| Errors | **0**, and every reply was valid JSON |
| Tokens | 72,010 input, 4,294 output |
| **Cost** | **US$0.0134** (dry-run estimate US$0.022). Computed from the token usage the API returned, at the list price of US$0.15 / 0.60 per million tokens. The billed amount is on the OpenAI usage page |
| **Latency per call** | median 1.22 s, p95 22.96 s, max 43.8 s, mean 6.1 s. 50 of the 254 calls took over 20 s, and the whole run took about 26 minutes |
| Score levels | only 7 distinct P(scam) values (0, 0.1, 0.7, 0.8, 0.85, 0.9, 0.95) |
| Reproducibility | replies came from 43 different `system_fingerprint` values, so a rerun at temperature 0 with a fixed seed is not guaranteed to give the same answers |

### Results (same metrics as E2)

| | GPT-4o-mini, zero-shot |
|---|---|
| Validation (95): accuracy / macro-F1 / MCC / ROC-AUC | 0.947 / 0.941 / 0.882 / 0.981 |
| Validation errors | 2 missed scams, 3 false alarms; all 5 are synthetic rows, and all 4 real validation chats are right |
| New wording (144): accuracy | **1.000** |
| New wording: pair accuracy (72) | **1.000 (72)** |
| Pair accuracy, en / mix / ms | 1.000 / 1.000 / 1.000 |
| **Blind: scams caught** (10) | 9 (90%; 95% CI 60–98%). Missed case 10 with P(scam) 0.0 |
| **Blind: false alarms** (5) | 1 (20%; 4–62%), case 9 at 0.8 |
| Blind ROC-AUC | 0.88 (on 7 distinct score levels) |
| Run 1's 166-row split and the 9 gates | not run: not in the E4 plan |

**Reading:**
- **With no training data at all, GPT-4o-mini gets every new-wording pair right.** The tactics in the minimal pairs are textbook scam behaviour that a general model already knows. The pair test therefore shows whether a trained classifier has learnt those tactics; it is not a hard benchmark in itself.
- **On the corpus validation set,** its only out-of-sample corpus test, it does worse than the trained models: 0.947 against 0.979, with 3 false alarms against none.
- **On the blind test it sits between run 1 and TF-IDF** (9 of 10 scams, 1 false alarm). It missed case 10 at 0.0 while catching case 6, a word-for-word copy of the same script, at 0.8.
- **Practical drawbacks:**
  - The chats, although anonymised, leave the device.
  - The slow calls run to 23–44 s.
  - The scores are coarse and not calibrated.
  - The serving is not reproducible.
- The cost is negligible: about US$0.05 per 1,000 conversations.

## Comparison of the three classifiers

(`results/comparison_three_models.json`)

| | XLM-R run 1 (deployed) | TF-IDF + LR (B) | GPT-4o-mini zero-shot |
|---|---|---|---|
| Training data | run 1's 1,223 rows | the same 1,223 rows | none |
| Validation accuracy / macro-F1 (95) | 0.979 / 0.977 (in-sample: early stopping) | 1.000 / 1.000 (in-sample: choice of C) | 0.947 / 0.941 (out of sample) |
| New wording: accuracy / **pair accuracy** | 0.972 / **0.944** | 0.972 / **0.944** | 1.000 / **1.000** |
| Pair accuracy, en / mix / ms | 1.000 / 1.000 / 0.833 | 0.957 / 1.000 / 0.875 | 1.000 / 1.000 / 1.000 |
| Gates passed (of 9) | 8 | 8 | not run |
| **Blind: scams caught** (10; 9 real + 1 role-played) | **10** (95% CI 72–100%) | 8 (49–94%) | 9 (60–98%) |
| **Blind: false alarms** (5, all role-played) | 1, case 9 (4–62%) | 1, case 11 (4–62%) | 1, case 9 (4–62%) |
| Blind ROC-AUC | 0.94 | 0.88 | 0.88 |
| Blind errors | case 9 | cases 5, 11, 13 | cases 9, 10 |
| Latency per conversation | median 0.18 s on the laptop CPU (about 1 s for long chats) | about 2 ms | median 1.2 s, p95 23 s (network) |
| Cost | none (local) | none (local) | US$0.0134 for 254 calls |
| Chat leaves the device | no | no | yes (anonymised) |

### Blind test per case (P(scam); "wrong" means the wrong side of 0.5)

| Case | Truth | Origin | XLM-R run 1 | TF-IDF B | GPT-4o-mini |
|---|---|---|---|---|---|
| 1 | Scam | real | 0.98 | 0.69 | 0.90 |
| 2 | Scam | real | 0.98 | 0.67 | 0.90 |
| 3 | Legit | role-play | 0.02 | 0.35 | 0.00 |
| 4 | Legit | role-play | 0.01 | 0.28 | 0.00 |
| 5 | Scam | real | 0.91 | 0.49 **wrong** | 0.80 |
| 6 | Scam | real | 0.89 | 0.73 | 0.80 |
| 7 | Scam | real | 0.96 | 0.61 | 0.80 |
| 8 | Scam | role-play | 0.98 | 0.89 | 0.90 |
| 9 | Legit | role-play | 0.95 **wrong** | 0.21 | 0.80 **wrong** |
| 10 | Scam | real | 0.99 | 0.91 | 0.00 **wrong** |
| 11 | Legit | role-play | 0.43 | 0.73 **wrong** | 0.00 |
| 12 | Scam | real | 0.98 | 0.81 | 0.80 |
| 13 | Scam | real | 0.98 | 0.48 **wrong** | 0.80 |
| 14 | Scam | real | 0.91 | 0.60 | 0.80 |
| 15 | Legit | role-play | 0.01 | 0.24 | 0.00 |

Sources: run 1's blind scores are the probabilities recorded in the blind test (`data/test_real/cases/results.csv`). TF-IDF and GPT-4o-mini scored the regenerated transcripts, whose message counts match the recorded ones.

**Reading:**
- **No model is best everywhere.**
  - On the synthetic new-wording pairs, the zero-shot model is perfect, and the two trained models tie at 0.944.
  - On the 15 blind cases, run 1 makes 1 error, GPT-4o-mini 2 and TF-IDF 3. The only error they share is case 9, a false alarm by both run 1 and GPT-4o-mini.
- **The blind differences are small.** With 10 scams and 5 role-played legitimate chats, they lie well inside each other's confidence intervals, so the blind test cannot rank the three.
- **The clearer differences are operational.** Run 1 runs locally in under a second and keeps the conversation on the device. TF-IDF is about 90 times faster but scores long chats as one document. GPT-4o-mini needs a network connection and a third-party API, has a slow tail, and gives coarse, unreproducible scores.

## E5. Timing and 10 concurrent users

**Runs (all by you, with `scripts/e5/RUN_E5.ps1`, on 2026-11-10):**

| Time | What | Folder |
|---|---|---|
| 10:55 | free smoke run, no keys | `results/e5/20261110T105459_smoke/` |
| 10:59–11:09 | Tests A and B | `results/e5/20261110T105950/` |
| 11:22–11:28 | Test A again, with the corrected Serper key (`-OnlyA`) | `results/e5/20261110T112255_testA/` |

In the 10:59 run, a wrong Serper key was entered, so every search got HTTP 403. **The Test A results below are therefore from the 11:22 rerun.** Test B uses no search by design, so its results come from the 10:59 run.

**Setup:**
- **Laptop:** the development laptop: Intel Core i5-12450H (12 logical processors), 7.7 GB RAM, Windows 11. Only Docker Desktop and VS Code were open; about 0.8 GB was free before the run.
- **Separate copy:** Docker project `rentsafe_exp` with its own PostgreSQL (port 5433) and Redis (port 6380) on a new volume.
  - The backend (port 4100) and model service (port 8100) ran from a copy of the code with no `.env` files.
  - The weights were a copy with the same SHA-256 as the deployed run 1, and the model loaded with temperature 0.731.
  - The price baseline came from the committed seed files: 698 whole-unit strata and 19 room strata.
- **Models:** the explanation used gpt-4o-mini. The OSINT judge was set to gemini-3.5-flash-lite but was never reached (see Test A).
- **Start-up:** the model service was ready after 8.2 s (40.5 s on the smoke run's cold disk). One untimed warm-up OCR and classify call (3.3 s) came before Test A, because the first OCR call after start-up is slower.

### Test A: the 15 blind cases, one at a time, empty cache (rerun, 11:22)

| Case | Pages | OCR (s) | Classifier (s) | End to end (s) | Score (Table 4.11) | Band | Complaint search |
|---|---|---|---|---|---|---|---|
| 1 | 6 | 3.8 | 0.89 | 22.1 | 59 (59) | HIGH | yes |
| 2 | 4 | 2.7 | 0.38 | 7.6 | 59 (59) | HIGH | yes |
| 3 | 2 | 1.3 | 0.20 | 20.1 | 11 (11) | LOW | yes |
| 4 | 2 | 1.2 | 0.17 | 5.3 | 0 (0) | LOW | no agent details |
| 5 | 2 | 1.2 | 0.23 | 5.8 | 49 (49) | MODERATE | yes |
| 6 | 3 | 1.9 | 0.30 | 6.6 | 53 (53) | HIGH | no agent details |
| 7 | 4 | 2.9 | 0.78 | 8.2 | 58 (58) | HIGH | yes |
| 8 | 3 | 1.6 | 0.17 | 6.6 | 59 (59) | HIGH | no agent details |
| 9 | 2 | 1.3 | 0.20 | 4.4 | 57 (57) | HIGH | no agent details |
| 10 | 3 | 2.1 | 0.23 | 11.5 | 64 (64) | HIGH | yes |
| 11 | 3 | 2.4 | 0.19 | 5.6 | 26 (26) | MODERATE | no agent details |
| 12 | 3 | 2.0 | 0.29 | 15.3 | 74 (74) | HIGH | yes |
| 13 | 14 | 10.5 | 1.69 | 26.0 | 64 (64) | HIGH | yes |
| 14 | 9 | 5.8 | 1.20 | 17.1 | 64 (64) | HIGH | yes |
| 15 | 4 | 2.3 | 0.26 | 5.6 | 0 (0) | LOW | no agent details |

- **Results:** all 15 requests succeeded. **All 15 scores and all 15 bands match Table 4.11 exactly.**
  - The complaint search ran in the 9 cases with agent details: 14 searches, 29 results judged by Gemini.
  - It again gave 5 points to cases 10, 12 and 13, and none to the other six.
  - OCR found the same number of messages as in the blind test in every case.
- **Time:**
  - End to end, the median was 7.6 s (range 4.4–26.0 s), and all 15 cases together took 168 s.
  - OCR took a median of 2.1 s and the classifier 0.26 s.
  - **The six cases without agent details** took a median of 5.6 s (4.4–6.6 s). Most of the time after OCR is the explanation call.
  - **The nine cases with the complaint search** took a median of 15.3 s (5.8–26.0 s), because the search and the Gemini judge add up to about 18 s.
  - **Three cases took over 20 s:** case 1 (22.1 s), case 3 (20.1 s) and case 13 (26.0 s; 14 pages, OCR 10.5 s).
- **Resources:** free memory fell to 302 MB at the lowest; the model service used at most 730 MB.
- **First attempt (10:59), with the wrong key:** every search failed at once. Cases 10, 12 and 13 scored 5 points lower (59, 69 and 59). Every other component was identical, and the median time was 6.5 s.

### Test B: concurrent users

Conditions for all three runs:
- The explanation was on, and the cache was off (no Redis), so every request was new, as with different real chats.
- No agent details were sent, and the search and judge keys were withheld. The backend reads phone numbers from the chat text itself, so this guaranteed no search spend.

| Run | Requests | Succeeded | 429 | Errors | Median | 95th pct | Max | Throughput |
|---|---|---|---|---|---|---|---|---|
| B1: 10 users, own addresses, 3 min, text | 368 | 368 | 0 | 0 | 4.5 s | 8.4 s | 12.4 s | 120 per minute |
| B2: 10 users, one shared address, text | 150 | 100 | 50 | 0 | 4.5 s | 7.1 s | 9.3 s | – |
| B3: 10 screenshot requests at once (2–6 pages each) | 10 | 10 | 0 | 0 | 9.2 s | 11.2 s | 11.4 s | – |

- **B1:**
  - The latency stayed steady across the 3 minutes (median 4.6, 4.4 and 4.5 s per minute), and each user completed 36–38 analyses.
  - The CPU averaged 89%. Free memory never fell below 543 MB; the model service used at most 816 MB and the backend 110 MB.
- **B2:** requests 1–100 succeeded. From request 101 (after 46.5 s) every request got HTTP 429, exactly as the limit is set: 100 requests per address per 15 minutes.
  - This affects only users who share one address, such as a campus network.
  - During UAT the tunnel passed on each tester's own address.
- **B3:** all 10 succeeded. Free memory fell to 339 MB at the lowest, and the model service peaked at 1.2 GB.
- **Explanations:** 451 of the 478 successful requests had one.
  - **All 27 missing explanations were for case 5** (27 of its 35 requests). The reassurance check rejected gpt-4o-mini's text because it contained "sign of a genuine", so the result went out without the AI explanation, and the page then builds the explanation from the result.
  - The check lets negated forms through ("not a sign of a genuine…"). Rejected texts are not stored, though, so it could not be confirmed that each one was a real reassurance.
  - In Test A, where case 5 had its listing and agent details, the explanation passed.

**Cost (both runs):**
- **OpenAI:** about 508 explanation calls (15 + 368 + 100 + 10, plus 15 in the rerun). That is roughly US$0.25 at list price; this is an estimate, and the exact amount is on your OpenAI usage page.
- **Serper:** 14 searches in the rerun. The 14 in the first run were refused.
- **Gemini:** at most 9 judge calls in the rerun (one per case with results).

**Safety:**
- Pre-flight equals post-flight in both runs (`proof/e5_preflight_20261110T105950.txt` and `proof/e5_postflight_20261110T105950.txt`; the same files with the `_112255_testA` tag). Git status is `?? experiments/`, HEAD is da24abb, and all 46 hashes match.
- The demo containers kept the same IDs and start times with 0 restarts, and the demo volumes are unchanged.
- The `rentsafe_exp` containers and volume were removed.
- The code copy, which holds no personal data, is still in `~/rentsafe_experiments_data/e5_stack` (about 1.3 GB) and can be deleted.

**Reading:**
- **On this laptop a chat takes about 4–7 s without the complaint search,** and **6–26 s with it** (median 15 s). OCR, the explanation call and the search with its judge take most of the time; the classifier takes a fraction of a second.
- **Ten simultaneous users were served without errors** (pasted text, no agent details). The median was 4.5 s and the 95th percentile 8.4 s, and 10 screenshot uploads at once took at most 11.4 s. **The CPU was the limit, not memory.**
- **Against the Table 3.10 targets:**
  - 10 s for text with 10 users: met.
  - 20 s for images: met for 12 of the 15 single cases. **Not met for three cases**, where the complaint search ran: 20.1, 22.1 and 26.0 s.
- **Limits:**
  - one laptop and one run of each test;
  - load made from the same 15 chats;
  - the load test without the complaint search.
