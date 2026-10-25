# Layer 2 backbone comparison — XLM-R vs ELECTRA Bahasa

Record of the model selection for the `nlp-service` layer 2 scam classifier:
what was trained, what was measured, what the numbers mean, and what they
cannot support.

Last updated 2026-10-12.

---

## 1. Verdict

> **Deployed model: XLM-R retrain run 1** —
> `nlp-service/models/xlm-roberta-scam-v3-run1`. It is an **interim** model:
> it did not meet two of its nine acceptance criteria, fixed before training
> (§14.7), and is deployed because it beats the original model on every test
> both were given (§14.10). Its full evaluation — confusion matrices, metrics,
> acceptance gates, calibration, short-input behaviour, errors and limitations
> — is in **`docs/MODEL_EVALUATION.md`**. Headline figures: validation
> accuracy 0.979 (macro-F1 0.977); new-wording minimal pairs accuracy 0.972,
> pair accuracy 0.944; acceptance gates 8 of 9 today.
>
> **The rest of this section is history:** the original model selection
> (September 2026), XLM-R against ELECTRA Bahasa, before retraining. §14
> explains why the first XLM-R was replaced — it scored a real legitimate
> conversation 0.9995, having learned that itemised prices and length mean
> "scam".

**`xlm-roberta-base` was chosen as the backbone.** Its first fine-tune
(`xlm-roberta-scam-random`) was deployed until 2026-09-28 and then replaced by
retrain run 1 on the same backbone. The Malay ELECTRA weights are kept on disk
for the report but must not be deployed.

XLM-R was chosen **despite scoring lower on validation** — F1 0.9920 against
ELECTRA v2's 1.0000. Tested on the path the product actually uses, OCR of
screenshots followed by `/classify`, the two models behave completely
differently:

| conversation, 3 screenshots | ELECTRA v2 | XLM-R |
|---|---|---|
| Scam | **0.0179 — wrong** | 0.9997 ✓ |
| Legitimate | 0.0080 ✓ | 0.0021 ✓ |

ELECTRA v2 answers LEGITIMATE to both: on this input it does not discriminate at
all. XLM-R separates them cleanly. See §7 for why, and §8 for the failure that
preceded it.

### Five findings that matter more than the choice

1. **Neither model learned scam semantics.** ELECTRA v2's line-by-line
   ablation (§7.2) shows it treats *"after you transfer I'll post the key"* as
   evidence of **legitimacy**. XLM-R survives that test only because its output
   is saturated: strip every scam mechanic at once (§7.4) and it still scores
   0.9995. Both match the shape of a conversation rather than its content, which
   is what a near-perfect validation score was actually measuring.
2. **XLM-R template-matches as well, and its headline scores hide it.** Strip
   every scam mechanic from a scam conversation — the deposit demand, the
   outstation excuse, the courier promise, the manufactured urgency — and it
   still scores **0.9995** (§7.4). The conversation is not memorised text: its
   highest 5-gram overlap with training is 1.6%. So it is keying on register and
   structure, which no test that varies wording can see. XLM-R remains the
   deployed model because it discriminates where ELECTRA v2 does not, not
   because it reads scams correctly.
3. **Validation F1 failed to detect two different unusable models.** ELECTRA v1
   scored 0.9764 while answering SCAM to nearly everything (§8); ELECTRA v2
   scored 1.0000 while answering LEGITIMATE to a scam conversation. Probability
   calibration caught the first, an end-to-end behavioural test caught the
   second. Neither was visible in any aggregate metric.
4. **Both models collapse on short input**, defaulting to LEGITIMATE below
   **six messages** (§6.4, measured by `eval/truncation_sweep.py`). A false
   all-clear is worse than a false alarm here, so layer 2 reports these as
   `insufficient_context` rather than as a low score (§10), and the backend
   excludes them from the risk score entirely.
5. **There is no held-out real test set.** All 24 real conversations in the
   project are inside the train/validation splits (§3). No number in this
   document speaks to real-world performance, XLM-R's included.
   `data/test_real/` now exists, sealed and guarded, waiting to be filled.

### A caveat on the winner

XLM-R is the better of the two artifacts, not a validated scam detector. It was
trained on the same ~95% synthetic data and will carry some of the same
template-matching. It has not been subjected to the ablation in §7.2 in the same
depth, and it has no honest test set to be measured against. "Better" here means
"gets these cases right where the other does not".

---

## 2. Models

| | XLM-R | ELECTRA Bahasa |
|---|---|---|
| Base checkpoint | `xlm-roberta-base` | `mesolitica/electra-base-discriminator-bahasa-cased` |
| Pretraining corpus | 100 languages, CommonCrawl | Malay corpora (Mesolitica / Malaya) |
| Vocabulary | 250k SentencePiece | 32k WordPiece, cased |
| Parameters (fine-tuned) | 278M | 111M |
| On-disk size | ~1.1 GB | ~440 MB |
| Published head | `XLMRobertaForSequenceClassification` | `ElectraForPreTraining` |
| Local folder | `nlp-service/models/xlm-roberta-scam-random` | `nlp-service/models/electra-malay-scam-random-v2` |

The ELECTRA checkpoint ships as a pretraining discriminator with no
classification head, so `AutoModelForSequenceClassification` initialises
`classifier.*` from scratch and logs a warning. This is expected, and it is the
reason the model is sensitive to learning rate — see §8.

The repository also ships `vocab.txt` without `tokenizer.json`, so the fast
tokenizer is built from the vocabulary at load time, and weights are distributed
as `pytorch_model.bin` with no safetensors variant.

---

## 3. Dataset

This section is the most important context for every number that follows.

### Composition

| | conversations | synthetic | real |
|---|---|---|---|
| Processed total | 474 | 450 (94.9%) | 24 (5.1%) |
| Real source files | 24 | — | 8 legitimate, 16 scam |

Conversations are multi-turn WhatsApp-style transcripts in the form
`Renter: ... / Owner: ...`, median ~480 characters.

### Splits

| split | train | val | val SCAM / LEGIT | template overlap |
|---|---|---|---|---|
| `random` | 379 | 95 | 63 / 32 | 19 of 20 groups shared with train |
| `grouped` | 381 | 93 | 63 / 30 | none — 5 groups held out |

`grouped/val.csv` draws its 93 rows from only **five** template families, each
single-label:

| group | rows | label |
|---|---|---|
| L02 | 17 | LEGITIMATE |
| L07 | 13 | LEGITIMATE |
| S04 | 19 | SCAM |
| S08 | 27 | SCAM |
| S10 | 17 | SCAM |

Rows within a family are variations on one script and stand or fall together, so
the effective sample size of the grouped validation set is closer to **5 items
than 93**. A single family going wrong moves 13–27 rows at once.

### Majority-class baselines

A classifier that answers SCAM unconditionally scores:

| split | accuracy | precision | recall | F1 |
|---|---|---|---|---|
| `random` | 0.6632 | 0.6632 | 1.0000 | **0.7975** |
| `grouped` | 0.6774 | 0.6774 | 1.0000 | **0.8077** |

The project's stated target of F1 ≥ 0.80 is therefore almost reached by a model
that has learned nothing. Any F1 in the high 0.70s or low 0.80s should be read
against this line, not against zero.

### No sealed test set

Earlier working notes referred to a held-out set of real conversations reserved
for final evaluation. **It does not exist.** All 24 real conversations appear in
the train or validation splits. Consequences:

- Every score in this document is measured on data that is ~95% synthetic and
  generated from templates the model saw variants of.
- The model has been trained on essentially every real example of a *legitimate*
  landlord conversation the project possesses — eight of them.
- No number here predicts behaviour on a scam that was not written by the
  dataset's own generator.

---

## 4. Training configurations

All runs used AdamW with a linear schedule, warmup ratio 0.1, fp16, seed 42,
`load_best_model_at_end=True` selecting on validation F1, on a Colab T4.

| | XLM-R | ELECTRA v1 | ELECTRA v2 |
|---|---|---|---|
| Split trained on | `random` | `random`, then `grouped` | `random` |
| Learning rate | 2e-5 | 2e-5 | **5e-5** |
| Epochs | 8 | 8 | **20**, early stopping patience 5 |
| Train batch / eval batch | 16 / 32 | 16 / 32 | 16 / 32 |
| Weight decay | 0.0 | 0.0 | **0.01** |
| Loss | unweighted CE | unweighted CE | **class-weighted CE** (LEGIT 1.504, SCAM 0.749) |
| Max sequence length | 192 | 192 | **256** |
| Optimiser steps | 192 | 192 | up to 480 |

ELECTRA v1 deliberately mirrored XLM-R's recipe so the comparison would isolate
the backbone. That design turned out to be the flaw — see §8.

Class weights are computed as `len(train) / (2 * class_count)`.

The `max_length` increase from 192 to 256 removed the 9.5% of `random`
validation conversations that were previously truncated. Scam tells (the demand
for payment before viewing) typically appear late in a conversation, so
truncation removes exactly the decisive evidence.

Notebooks: `nlp-service/train_colab.ipynb` (XLM-R),
`train_colab_electra.ipynb` (v1), `train_colab_electra_v2.ipynb` (v2).

---

## 5. Results as reported by the training runs

Numbers printed by the Colab notebooks at the end of each run.

| model | split | accuracy | precision | recall | F1 |
|---|---|---|---|---|---|
| XLM-R | random | — | — | — | 0.9920 |
| XLM-R | grouped | — | — | — | 0.9672 |
| ELECTRA v1 | random | 0.9684 | 0.9688 | 0.9841 | 0.9764 |
| ELECTRA v1 | grouped | 0.9677 | 0.9688 | 0.9841 | 0.9764 |
| ELECTRA v2 | random | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Confusion matrices for ELECTRA v1:

| split | LEGIT correct | false alarms | missed scams | SCAM correct |
|---|---|---|---|---|
| random | 30 | 2 | 1 | 62 |
| grouped | 28 | 2 | 1 | 62 |

XLM-R's confusion matrices were not captured at training time; reconstructed
from F1, the `random` run made 1 missed scam and 0 false alarms, and the
`grouped` run 4 missed scams and 0 false alarms. Both reproduce the reported F1
exactly, but they are inferred rather than recorded.

**Two caveats on this table.** These validation scores select the checkpoint and
then report it, so they are optimistically biased — particularly for ELECTRA v1
on `grouped`, where F1 peaked at epoch 5 (0.9764) and then fell to 0.9167,
0.9167 and 0.9344. The reported figure is the peak of a bouncing curve. And a
perfect 1.0000 indicates a saturated dataset rather than a perfect model.

---

## 6. Independent measurements

Measured locally against the saved weights under identical conditions
(`max_length` 256, threshold 0.5, CPU). These are the authoritative comparison
numbers; ELECTRA v1 was deleted from disk before the final sweep, so it appears
only where it was measured earlier.

### 6.1 Validation sets

| split | model | accuracy | precision | recall | F1 | missed scams | false alarms |
|---|---|---|---|---|---|---|---|
| random | ELECTRA v2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |
| random | XLM-R | 0.9895 | 1.0000 | 0.9841 | 0.9920 | 1 | 0 |
| random | ELECTRA v1 | 0.9684 | 0.9688 | 0.9841 | 0.9764 | 1 | 2 |

For XLM-R, `eval/behaviour_checks.py` also reports **macro-F1 0.9883** and **MCC 0.9769**. Both are more informative than binary F1 on a set that is two-thirds SCAM: MCC in particular would collapse toward 0 for a majority-class guesser, where binary F1 sits at 0.7975.

**`grouped` scores are omitted deliberately.** Both saved models were trained on
the `random` split, whose training data contains the template families that
`grouped/val.csv` holds out. Evaluating either on `grouped` scores data they
have already seen. Any grouped number for these weights is contaminated and must
not be quoted as a generalisation result. The 0.9672 in §5 came from a
separately trained grouped model that is not on disk.

### 6.2 Probability calibration — `random` validation set

Share of predictions outside the 0.1–0.9 band, i.e. where the model commits.

| model | confident | < 0.1 | 0.1–0.9 | > 0.9 | rows |
|---|---|---|---|---|---|
| ELECTRA v2 | **100.0%** | 32 | 0 | 63 | 95 (all) |
| XLM-R | 98.9% | 32 | 1 | 62 | 95 (all) |
| ELECTRA v1 | **0.0%** | 0 | 91 | 0 | 91 (synthetic only) |

The v1 row was measured before those weights were deleted, over the 91 synthetic
validation rows rather than all 95; the four real conversations were scored
separately and are reported in §8.

This is the measurement that exposed v1. A model whose probabilities never leave
0.1–0.9 has not learned a decision boundary; it hovers either side of 0.5, which
happens to sort the synthetic data and nothing else.

### 6.3 Held-out hand-written probes

Written by hand, never present in any split. Two sets were used.

**Probe set A** — 6 short fragments plus 2 full transcripts. All three models
measured:

| model | correct |
|---|---|
| XLM-R | 7 / 8 |
| ELECTRA v2 | 5 / 8 |
| ELECTRA v1 | 3 / 8 |

**Probe set B** — 8 short fragments only, no transcripts:

| input | truth | ELECTRA v2 | XLM-R |
|---|---|---|---|
| "Sure, you can view the unit this Saturday." | LEGIT | 0.102 ✓ | 0.998 ✗ |
| "The rent is RM1200 a month, deposit is two months as usual." | LEGIT | 0.051 ✓ | 0.001 ✓ |
| "Boleh datang tengok rumah hujung minggu ni, saya ada." | LEGIT | 0.061 ✓ | 0.019 ✓ |
| "Sewa rm900 sebulan, deposit 2 bulan. Agreement kita buat kat office." | LEGIT | 0.888 ✗ | 0.001 ✓ |
| "Transfer the deposit first, then I will post you the keys." | SCAM | 0.035 ✗ | 0.999 ✓ |
| "Bayar deposit dulu baru boleh viewing, saya outstation sekarang." | SCAM | 0.385 ✗ | 1.000 ✓ |
| "Kalau nak lock unit ni kena bayar booking RM500 dulu, ramai tengah tanya." | SCAM | 0.596 ✓ | 1.000 ✓ |
| "I cannot do viewing, I'm overseas. Pay one month rent and I courier the key." | SCAM | 0.010 ✗ | 0.001 ✗ |
| **total** | | **4 / 8** | **6 / 8** |

Both sets are small and author-written; the ratios should not be over-read. Two
qualitative observations do survive that caveat:

- ELECTRA v2 assigns p(scam) 0.385 and 0.035 to two textbook Malaysian rental
  scam lines when they appear in isolation.
- **Both models confidently miss the English-only scam** in the last row
  (0.010 and 0.001). Training scams are almost entirely code-switched Malay, so
  a purely English scam is out of distribution for both.

### 6.4 Truncation sensitivity — the deployment finding

Re-measured in **messages**, not lines: `eval/truncation_sweep.py`, results in
`eval/results/truncation_sweep.json`. An earlier version of this section cut on
line breaks, which is not what a reader assumes and not what the guard counts.
Messages are counted by `app/turns.py`, which strips phone furniture and rejoins
wrapped bubbles.

72 validation conversations with at least
8 messages (51 scam /
21 legitimate), truncated to their first N:

| messages visible | accuracy | F1 | beats baseline? |
|---|---|---|---|
| 1 | 0.306 | 0.138 | **no** |
| 2 | 0.361 | 0.179 | **no** |
| 3 | 0.417 | 0.300 | **no** |
| 4 | 0.597 | 0.603 | **no** |
| 5 | 0.694 | 0.725 | **no** |
| 6 | 0.833 | 0.867 | yes |
| 7 | 0.931 | 0.949 | yes |
| 8 | 0.972 | 0.980 | yes |
| all | 1.000 | 1.000 | yes |

Answering SCAM unconditionally scores **0.708**
on this subset. So **up to and including 5 messages the model is worse than a
trivial classifier**, and 6 is the first count
that beats it.

The low F1 alongside the low accuracy shows the direction of the failure: with
little context the model does not hesitate, it answers **LEGITIMATE**. For
RentSafe that is the dangerous direction — a renter uploading the opening of a
conversation would receive a false all-clear.

This is what sets the guard (§10). A previous revision guarded below 4, a number
picked by eye: at 4 messages accuracy is 0.597 against a 0.708 baseline, so that
guard passed through exactly the band it existed to catch.

---

## 7. The OCR path — what decided the choice

Everything in §6 scores the models on conversation text taken straight from the
CSVs. The product does not receive that. It receives OCR output from WhatsApp
screenshots. Testing that path reversed the decision.

### 7.1 End to end, through the running service

Three screenshots of one conversation were rendered, uploaded to `POST /ocr`, and
the stitched text posted to `POST /classify`.

| conversation | pages | turns | ELECTRA v2 | XLM-R |
|---|---|---|---|---|
| Scam | 3 | 11 | **0.0179 — wrong** | 0.9997 ✓ |
| Legitimate | 3 | 11 | 0.0080 ✓ | 0.0021 ✓ |
| Scam, one page only | 1 | 5 | — | 0.9997 ✓ |

ELECTRA v2 returns "legitimate" for both conversations. A model that answers the
same way regardless of input is not classifying, and its 1.0000 validation score
gave no hint of it.

Two explanations were ruled out before concluding this:

- **Not formatting.** The same scam conversation was re-shaped six ways — one
  message per line, messages wrapped across lines as a narrow screenshot would,
  all on one line, speaker labels stripped, lowercased, blank lines between page
  groups. Every variant still scored SCAM (0.7953 – 0.9964). Line structure is
  not the cause.
- **Not truncation.** Every variant tokenised to 75–107 tokens against a 256
  limit.

### 7.2 Ablation: what ELECTRA v2 is actually reading

Removing one line at a time from the OCR'd scam conversation (baseline 0.0179).
A positive delta means that line was pulling the verdict *toward* LEGITIMATE.

| line removed | p(scam) after | delta |
|---|---|---|
| `Renter: Can I see it first?` | 0.2431 | **+0.2252** |
| `Renter: Early next month.` | 0.1702 | **+0.1523** |
| `Owner: Lepas transfer saya pos kunci.` | 0.0922 | **+0.0743** |
| `Owner: Ramai orang tengah tanya.` | 0.0338 | +0.0159 |
| `Owner: Cannot open the unit sorry.` | 0.0306 | +0.0127 |
| `Renter: Hi, is the room still available?` | 0.0188 | +0.0009 |
| `Owner: Kalau nak lock the room,` | 0.0112 | −0.0067 |
| `Renter: Boleh pergi viewing dulu tak?` | 0.0106 | −0.0073 |
| `Owner: Yes it is. Nak masuk bila ya?` | 0.0083 | −0.0096 |
| `Owner: I'm outstation in Sabah now.` | 0.0082 | −0.0097 |
| `Owner: transfer deposit RM800 dulu.` | 0.0076 | −0.0104 |

Three things are wrong here, and they are the substance of the finding:

1. **Deleting a scam line makes the conversation look more like a scam.**
   Removing *"Lepas transfer saya pos kunci"* — after you transfer, I'll post the
   key — raises p(scam) by 0.074.
2. **The scam mechanics contribute almost nothing.** The upfront-payment demand
   (`transfer deposit RM800 dulu`) and the refusal to allow viewing
   (`I'm outstation in Sabah now`) each move the score by about 0.01 — and in the
   direction that says they are *evidence of legitimacy*.
3. **Removing the three highest-impact lines flips the verdict**: 0.0179 → 0.2431
   → 0.6019 → 0.9821. A scam is correctly identified only after deleting part of
   the scam.

Scored in isolation, the ordering is inverted from what the task requires:

| line | p(scam) alone |
|---|---|
| `Renter: Boleh pergi viewing dulu tak?` (renter asks to view — neutral) | **0.4599** |
| `Owner: transfer deposit RM800 dulu.` (the demand) | 0.3913 |
| `Owner: Ramai orang tengah tanya.` (false urgency) | 0.1939 |
| `Owner: Lepas transfer saya pos kunci.` (the classic tell) | **0.0107** |

The single most diagnostic sentence in Malaysian rental scams scores lowest.

### 7.3 The same ablation on XLM-R — SUPERSEDED by §7.4

> **This section's conclusion does not hold.** It is kept because the
> measurement is real and because the mistake is instructive: single-line
> ablation cannot say anything about a model whose output is saturated. §7.4
> removes every scam mechanic at once and shows XLM-R is template-matching too.

| baseline | effect of removing any single line |
|---|---|
| 0.9997 | no change beyond 0.0003 |

XLM-R holds the correct verdict and does not depend on any one line. This was
originally read as stability. It is not: a model that returns 0.9997 for
everything it considers a scam will not move for any single deletion, so the
test had no power to detect what §7.4 found.

### 7.4 Group ablation — XLM-R is also template-matching

§7.2 removed lines from the scam conversation one at a time and XLM-R did not
move, which §7.3 read as stability. `eval/behaviour_checks.py` removes **every
scam mechanic at once** — the deposit demand, the outstation excuse, the courier
promise and the manufactured urgency — and the reading does not survive.

| version of the conversation | p(scam) |
|---|---|
| full | 0.9997 |
| **every scam mechanic removed** | **0.9995** |
| scam mechanics only | 0.9997 |

A conversation with no scam content left in it still scores
0.9995. XLM-R is not reading the mechanics either; it is
matching the shape of the conversation. Single-line ablation could not show this
because the output is saturated — removing any one line moved it by less than
0.001, which §9 now records as a limitation rather than a strength.

The conversation is not a copied template: its highest 5-gram overlap with any
training conversation is 1.6% (closest source group
L08). So the model is not recognising memorised text —
it is keying on something more general about register and structure, which is
worse, because it is invisible to any test that varies the wording.

**This does not reverse the §1 verdict.** XLM-R still separates scam from
legitimate on the OCR path where ELECTRA v2 does not, and still clears the
legitimate conversations. But both models reach their answers by a route that has
little to do with scam semantics, and neither has been shown to generalise.

### 7.5 English-only conversations

`eval/behaviour_checks.py`, ten **author-written** conversations of 8 messages —
written for this test, not collected, so they show whether the model generalises
to English phrasing and nothing about field performance.

| | caught / cleared | scores |
|---|---|---|
| English scams | **4/5** | 1.000, 1.000, 1.000, 0.999, 0.028 |
| English legitimate | **5/5** | 0.001, 0.001, 0.001, 0.006, 0.001 |

Better than the earlier single-probe result suggested. The one miss scores
0.0282 — an overseas owner offering to post the access card
and asking for payment before 9pm. It is the courier-key pattern both models have
failed before, and it remains the clearest known gap.

### 7.6 Benign short messages

Eight ordinary one-line landlord replies, scored as-is:

**2 of 8 were flagged as scam.** *"Sure, you can view the
unit this Saturday."* scores 0.9984, and *"Yes it is still
available, when would you like to see it?"* scores 0.6604. Both are
exactly what an honest landlord writes.

This is the false-alarm cost of the saturated output, and it is why the guard
(§10) reports short input as unknown rather than passing the probability through.

---

## 8. Case study: the ELECTRA v1 failure

Worth documenting because the failure was invisible to the project's chosen
metric.

**Symptom.** v1 scored F1 0.9764 on both splits — above the 0.80 target,
competitive with XLM-R — while answering SCAM to nearly every input outside its
training distribution:

| input | v1 p(scam) | correct? |
|---|---|---|
| 4 hand-written legitimate messages | 0.75 – 0.82 | all wrong |
| Legitimate full transcript | 0.864 | wrong |
| The real legitimate conversation in validation | 0.871 | wrong |

**Diagnosis.** Three signals, none of them F1:

1. Probabilities never left the 0.1–0.9 band (§6.2).
2. Validation F1 for epochs 1 and 2 was exactly 0.7975 — the always-SCAM
   baseline to four decimal places. The classification head had not begun to
   learn.
3. Training loss was 0.1948 and still falling when the run ended.

**Cause.** Not the backbone: the optimisation. ELECTRA's discriminator arrives
without a classification head, and v1 gave the freshly initialised head XLM-R's
learning rate of 2e-5 for 8 epochs. At 379 training rows and batch 16 that is 24
steps per epoch, 192 steps in total. XLM-R converged within that budget; ELECTRA
did not.

**Fix.** The v2 recipe (§4) — 5e-5, up to 20 epochs with early stopping, class
weighting, longer sequences. Calibration went from 0% confident to 100%, the
real conversations from 3/4 to 4/4, and probe set A from 3/8 to 5/8.

**Lesson for the write-up.** The matched-hyperparameter design that made the
comparison "fair" was the thing that broke it. Holding the recipe constant across
two architectures with different optimisation requirements does not compare the
architectures; it compares one architecture against another one that has been
mistuned. And an evaluation metric certified a model that answered SCAM to
everything, because the validation set was 66% SCAM and drawn from the same
generator as the training data.

---

## 9. Limitations

> Items 2–14 describe the **original model and its selection**. Several no
> longer hold for the deployed run-1 model — it is not saturated (item 9), it
> catches the English courier scam and all five English probes (item 13), and
> its retrain has been run (item 14). The deployed model's own limitations are
> in `docs/MODEL_EVALUATION.md` §6. Item 1 holds for both.

1. **No held-out real test set** (§3). No number in this document predicts
   real-world performance.
2. **Validation scores select the checkpoint they report.** `load_best_model_at_end`
   with `metric_for_best_model="f1"` picks the best epoch by validation F1, then
   that same F1 is reported. All figures in §5 and §6.1 are optimistically biased.
3. **ELECTRA v2's 1.0000 indicates dataset saturation**, not a perfect
   classifier — as §7 demonstrates, it was compatible with a model that cannot
   tell a scam from a legitimate conversation on real input. The dataset can no
   longer distinguish between candidate models.
4. **Single seed per configuration.** With 95 validation rows, one row is worth
   1.05 accuracy points; gaps of a few points are not separable from seed noise.
5. **`grouped` evaluations of the saved weights are contaminated** (§6.1).
6. **Eight real legitimate conversations exist in total**, all used in training.
   The models have minimal basis for recognising an unfamiliar honest landlord.
7. **Validation scores were measured on CSV text, not on OCR output.** §6 calls
   the model on conversation text taken from the splits. The product receives OCR
   output from screenshots, and §7 shows the two can disagree completely — the
   model that wins §6 loses §7. Any future model must be judged on the OCR path
   before it is trusted.
8. **XLM-R has not been ablated as thoroughly as ELECTRA v2.** §7.3 establishes
   that it holds its verdict when lines are removed, which is the opposite of
   ELECTRA's inversion, but the deeper question — whether it reasons about scam
   mechanics or matches templates more robustly — is unanswered. It trained on the
   same ~95% synthetic data, so template matching is likely present.
9. **XLM-R's probabilities are saturated.** It returns 0.9997 and 0.0021 with
   little in between, so it offers no usable gradation of risk. A UI that wants
   to show "somewhat suspicious" has nothing to work with.
10. **The §7.1 OCR verdict rests on one scam and one legitimate conversation.**
    Two conversations decided which model was deployed. Enough to show ELECTRA v2
    failed to discriminate at all; nowhere near enough to characterise XLM-R.
11. **Single-line ablation is uninformative for XLM-R** (§7.3). Because the
    output is saturated, removing any one line moves it by less than 0.001, so
    the "stability" that section reported carries no information. Only the group
    ablation in §7.4 could say anything, and it says the model scores a
    conversation with every scam mechanic removed at 0.9995.
12. **The guard deliberately lets short-input false alarms through.** Below six
    messages a *low* score becomes 0.5, but a *high* score is still reported, so
    the 2 benign one-line messages XLM-R flags (§7.6) reach the user as
    warnings. Suppressing them would also suppress genuine short-message scam
    warnings, and a false alarm is the cheaper error.
13. **English-only scams remain a known gap** (§7.5). Four of five author-written
    English scams were caught; the fifth — overseas owner, access card by
    courier, pay before 9pm — scored 0.0282. Training scams are almost
    entirely code-switched Malay, and no real English scam has ever been tested.
14. **The deployed model fails a real legitimate conversation** (§14): 0.9995 on
    a blind iBilik letting, from learned shortcuts — itemised prices, length —
    and a 256-token cut that showed it a third of the chat. It passes 3 of the 9
    acceptance gates. The fix is a retrain, prepared but not yet run.

---

## 10. Deployment state

Configured, wired into the request path, and verified end to end.

`nlp-service/.env` (since 2026-09-28 — see §14.10; before that the folder was
`./models/xlm-roberta-scam-random`, now the commented rollback line):

```
PRIMARY_MODEL=xlm-roberta-base
FINETUNED_MODEL_DIR=./models/xlm-roberta-scam-v3-run1
```

The ELECTRA v2 weights stay on disk as the comparison artifact for the report and
are the commented-out block in the same file, marked do-not-deploy:

```
#   PRIMARY_MODEL=mesolitica/electra-base-discriminator-bahasa-cased
#   FINETUNED_MODEL_DIR=./models/electra-malay-scam-random-v2
```

The `.env` comment records *why* the lower-validation-F1 model is the deployed
one, so the choice is not silently reverted by someone comparing F1 alone.

Supporting changes in `nlp-service/app/config.py`:

- `.env` is now read at import. Previously nothing called `load_dotenv`, so a
  local `uvicorn app.main:app` ignored the file entirely and silently used the
  defaults; only Docker saw it, through compose's `env_file`.
- Relative paths such as `./models/...` resolve against the service root, so the
  service works regardless of the directory it is started from.
- Defaults updated to match, replacing a default that pointed at an empty
  `models/scam-classifier` directory.

### Layer architecture

The two layers are **independent and run concurrently** (`asyncio.gather` in
`classify_endpoint`). Neither feeds the other:

| | produces | feeds |
|---|---|---|
| Layer 1 — regex | evidence: labels, BM+EN advice, redacted snippets, pattern rules | the LLM narrator, and the renter |
| Layer 2 — transformer | `scam_probability` from the model alone | the backend's `aggregateScore` (× 60) |

> **Changed 2026-09-28 (§14.11):** red flags still contribute nothing to
> `scam_probability`, but the backend now holds the *band* at MODERATE when the
> model scores ≥ 0.5 and layer 1 found no red flag at all.

**Red flags contribute nothing to `scam_probability`.** An earlier revision added
up to 0.15 on top of the model's output; that was removed. The model was
fine-tuned on conversations containing the very phrases layer 1 matches, so a
rule bonus counted the same evidence twice — and it meant adding one regex
silently changed every score the service reported, leaving the model's measured
F1 unreproducible from its own API. Four tests now pin the boundary, including
one asserting `classify()`'s signature is exactly `(text, language)`.

They read different text deliberately: layer 1 takes the normalised form its
patterns depend on, layer 2 takes the raw text it was fine-tuned on.

### Layer 2 implementation

`app/layer2/classifier.py` loads the weights lazily on first request and returns
a probability. Behaviour:

- **Short input is reported as unknown.** Messages are counted by
  `app/turns.py` — chat bubbles, not lines, since OCR wraps one bubble across
  several and inflated two real screenshot sets to 146 and 103. Validated
  against a real four-page WhatsApp scam (`data/samples/`): **25 messages
  counted against a hand count of 25**, per page 9 / 11 / 3 / 3 where the hand
  count is 9 / 11 / 3 / 3 including one image bubble. That is the text
  counter on OCR text; `/ocr` now segments chat bubbles first and counts
  those, which over-counts the same conversation at 29 (§14.6). Below
  **6 messages**, where measured accuracy of the deployed run-1 model
  (`eval/results/truncation_sweep.json`; the original model's in §6.4) falls
  under the always-SCAM baseline of 0.708 and errs toward LEGITIMATE, a
  low score is replaced by 0.5 with `status: "insufficient_context"` and an
  explanatory `note`. A *high* score on short input is still reported, so the
  guard cannot suppress a warning. The raw value is always available as
  `model_probability`. A test fails the build if these constants drift from
  `eval/results/truncation_sweep.json`.
- **Confidence bands** map to the deployed model's measured curve, in messages:
  `high` ≥ 8 (0.903), `moderate` 7 (0.889), `low` 6 (0.792),
  `insufficient` ≤ 5 (0.667 and below, under the baseline). The original
  model's curve gave the same thresholds (0.972 / 0.931 / 0.833 / 0.694).
- **Missing weights report `status: "model_unavailable"`** with a neutral 0.5
  and a note, rather than failing the request or fabricating a number from rules.
- **Long input is read in windows of up to 512 tokens cut only between
  messages**, about 256 tokens apart, scoring the highest (§14.8), rather than
  cut at 256 tokens (§14.2).
- **A checkpoint's `calibration_temperature`** divides the logits when present
  (§14.3); the deployed run-1 checkpoint carries 0.731.

Two fixes in `app/main.py` were needed to make it work:

1. **Layer 2 receives the raw request text, not the normalised text.** The
   endpoint originally passed `normalised_text`. Normalisation lowercases,
   rewrites words (`Owner:` → `pemilik:`, `come` → `comel`) and collapses
   newlines. That shifted input away from the cased, multi-line conversations
   the model was fine-tuned on, and flattened every request to one "turn" so
   everything landed in the short-input guard. End to end, an eight-turn scam
   conversation scored 0.0815 before the fix and 0.9952 after. Layer 1 still
   reads the normalised text, which its patterns depend on.
2. **Inference runs in a worker thread** via `run_in_threadpool`, so a blocking
   forward pass does not stall the event loop.

### Verified end to end

> **History — the original model.** This check was run on the first XLM-R
> (`xlm-roberta-scam-random`), on the earlier OCR path. The deployed run-1
> model's results on real screenshots are in `docs/MODEL_EVALUATION.md` §4.6.

Screenshots uploaded to `POST /ocr`, the stitched text posted to `POST /classify`,
with the original XLM-R deployed:

| input | pages | turns | scam_probability | confidence | status |
|---|---|---|---|---|---|
| Scam conversation | 3 | 11 | 0.9997 | high | ok |
| Legitimate conversation | 3 | 11 | 0.0021 | high | ok |
| Scam, one screenshot | 1 | 5 | 0.9997 | low | ok |

All three correct. The third case is the useful one: a single screenshot gave 5
turns, which lands in the `low` confidence band rather than the guard, and XLM-R
still caught it. ELECTRA v2 returned 0.0179 on that same conversation.

The guard was separately confirmed against a 1-turn fragment, where the model
returned 0.0348 for *"Transfer the deposit first, then I will post you the keys"*
and the service reported 0.5 with `status: "insufficient_context"` instead of a
3%-risk all-clear.

`POST /ocr` accepts a repeatable `files` field (max 20 pages) so a chat spanning
several screenshots arrives as one conversation. Pages
are stitched in **upload order**, not filename order — `IMG_10` sorts before
`IMG_2` as a string. The response carries `turns`, letting a caller ask for more
screenshots before classifying. Full contract in `docs/API_SPEC.md`.

### Layer 1 implementation

`app/layer1/red_flags.py` holds 26 rules, 4 pattern rules and 10 legitimacy
signals. `analyse()` returns red_flags, evidence, patterns, legit_signals,
legit_signals_withheld, suppressed, entities, clean_text and token_count — no
score of any kind.

- Every rule carries a category, a severity (display priority only, never
  summed) and a BM + EN label and advice, because these are shown to the renter.
- **Exceptions** suppress a match when the sentence negates it ("jangan bayar
  sebelum tengok"), asks it as a question ("urgent ke?"), or scopes it to a time
  ("tak boleh tengok hujung minggu"). Suppressed matches are returned, not
  dropped.
- **Pattern rules** name the tactic when flags co-occur: `refundable_hold_lure`,
  `pressure_to_pay`, `absent_owner_payment`, `irregular_channel_payment`.
- **Legitimacy signals** are context only and never cancel a flag — a REN number
  can be copied from a real agent, so the narrator says "verify at lppeh.gov.my".
  Measured, they fire more often on scams than on honest chats, so any that
  appear alongside a red flag are moved to `legit_signals_withheld` (§14.5).
- Phone, IC, account numbers and URLs are redacted from snippets; amounts are
  kept as evidence.

Measured on 316 scam / 158 legitimate conversations: **89.6% of scams raise at
least one flag, 10.8% of legitimate ones do.** `eval/normaliser_impact.py`
re-measures with and without the English-homograph fix in one run: the rates are
**identical before and after (89.6% / 10.8%, no per-rule movement)**, because the
corpus is Malay-heavy synthetic text where "come" and "no" barely occur in their
English senses. The fix is demonstrable on real input — `no viewing allowed` was
being rewritten to `nombor viewing allowed`, destroying the `viewing_denial`
flag — and invisible on this corpus, which is itself a measure of how little the
corpus resembles real code-switched chat. Median flags per conversation is 2
for scams and 0 for legitimate. Two rules needed tightening after measurement —
`urgency_pressure` first scored 4.3% precision because real landlords also chase
tenants, and `refund_promise` fired on "deposit akan dipulangkan bila keluar",
which is a normal tenancy term.

14 of the 26 rules never fire on this corpus — `viewing_fee`, `otp_tac_request`,
`crypto_or_remittance`, `key_courier`, `verification_refusal`,
`deadline_pressure`, `video_only_viewing`, `meeting_avoidance`,
`proxy_collector`, `selfie_with_ic`, `agreement_irregularity`, `rush_language`,
`social_proof_payment`, `off_platform`. That measures how narrow the 20 templates
are, not a defect in the rules: `deadline_pressure`, `rush_language` and
`agreement_irregularity` all fire on a real scam screenshot and on nothing in the
synthetic data.

Tests: **335 passed, 3 skipped** (the skips are the sealed `data/test_real/`,
which is still empty).

| file | count | covers |
|---|---|---|
| `tests/test_normaliser.py` + `app/normaliser/test_normaliser.py` | 83 + 41 | normalisation, including the English-homograph fix and links never being rewritten |
| `tests/test_red_flags.py` | 60 | each rule fires; normal rental language stays quiet; exceptions; corpus precision floors; legitimacy signals and their withholding; the real scam screenshot |
| `tests/test_layer2.py` | 53 | message counting, confidence bands, the guard in both directions, independence from layer 1, windowing, calibration temperature, the missing-weights path, and three against the real weights |
| `tests/test_turns.py` | 21 | the message counter's strategies and de-duplication |
| `tests/test_ocr_endpoint.py` | 21 | multi-file upload, page order, partial failure, page limits, the bubble path, text inside photos dropped |
| `tests/test_real_screenshot.py` | 13 | the counter against the redacted OCR text of a real four-page scam |
| `tests/test_redaction.py` | 13 | names, addresses and numbers redacted; dates and money left alone; no listed name in any tracked file |
| `tests/test_classify_endpoint.py` | 10 | wiring — raw-text routing, layer independence, and that layer 1's evidence reaches the response |
| `tests/test_held_out.py` | 7 | the sealed test set is never read by training code |
| `tests/test_notebook_parity.py` | 8 | the service scores exactly as `train_colab_v3.ipynb` evaluates — windows, max, calibration temperature |
| `tests/test_minimal_pairs.py` | 8 | one legit + one scam twin per `pair_id`; test pairs from the held-out family, no mechanic sentence shared with training |

---

## 11. How the backend uses the score

`POST /api/analyze` and `/api/analyze/screenshot` run the full chain:
screenshots → NLP `/ocr` → NLP `/classify` → `aggregateScore` → response.
`nlp.service.js`, `pipeline.service.js`, `scoring.service.js` and
`analyze.controller.js` were empty stubs before this round.

### Layer 2 counts only when it can judge

`scam_probability` is 0.5 on both `insufficient_context` and
`model_unavailable`, and in both cases it means *cannot judge* — not *medium
risk*. Scoring it anyway would put 0.5 × 60 = 30 points on the board and present
a conversation nobody could assess as MODERATE, the opposite of what the service
said. So `aggregateScore` **excludes** the signal:

| layer 2 status | scored? | effect |
|---|---|---|
| `ok` | yes | `scam_probability × 60` |
| `insufficient_context` | no | excluded, `maxPossible` drops by 60 |
| `model_unavailable` | no | excluded, `maxPossible` drops by 60 |

`status`, `confidence` and a bilingual `message` are carried through unchanged so
the UI can explain itself.

### Weights are not redistributed

A score built from fewer signals is a weaker claim, and `maxPossible` says so
rather than scaling the remainder up to 100 and hiding it. The consequence is
deliberate: with only the NLP signal available the ceiling is 60, so a certain
scam reaches HIGH but not CRITICAL. Corroboration earns the top band.

### UNKNOWN is not LOW

When nothing could be scored the band is **`UNKNOWN`** (grey), not `LOW`. A
guarded scam scoring 0 out of a possible 0 is an absence of evidence, and showing
LOW beside "send more of the conversation" would tell the renter the opposite of
the truth.

### Verified end to end

Against both services running, screenshots posted to the backend:

| request | riskScore | band | nlpStatus | messages |
|---|---|---|---|---|
| 3 screenshots of the scam chat | 60 / 60 | HIGH (orange) | `ok` | 11 |
| 1 screenshot of the same chat | 0 / 0 | **UNKNOWN** (grey) | `insufficient_context` | 3 |
| `{"text": "hi"}` | — | — | 400 Validation failed | — |

The middle row is the point of the whole mechanism: the same conversation, seen
through one screenshot instead of three, returns "not enough to judge" rather
than a number.

One defect was found by wiring this up: `errorHandler` was a stub that returned
without sending a response, so any validation error left the connection open
until the client gave up. `POST /api/analyze` appeared to hang rather than
returning 400.

### The score is checked against the evidence

`assessEvidenceSupport` compares the model's verdict with layer 1's red flags
and returns `evidenceSupport` (`corroborated`, `partial`, `none`, `consistent`,
`contradicted` or `not_scored`), with a bilingual message when the two disagree
outright. It exists because of §14: the model scored a real legitimate
conversation 0.9995 with no red flag in it, and a number with nothing behind it
should say so. Contract in `docs/API_SPEC.md`.

### A high score with no red flag is held at MODERATE

Since 2026-09-28 `capUnsupportedScore` follows the score: model ≥ 0.5 and no red
flag → band at most MODERATE, `riskScore` at most 49, recorded in `bandCap`.
Decision, rule and measured cost: §14.11.

Tests: `backend/tests/scoring.test.js` (26) and `backend/tests/band_cap.test.js`
(13) — 39 cases covering the weighting, all three layer-2 statuses, missing
signals, the UNKNOWN band, clamping, every `evidenceSupport` outcome, every cap
rule, and the pipeline response with the services mocked.

---

## 12. Reproduction

Training (Colab, T4):

| notebook | produces |
|---|---|
| `nlp-service/train_colab.ipynb` | XLM-R, 8 epochs, lr 2e-5 |
| `nlp-service/train_colab_electra.ipynb` | ELECTRA v1, matched to XLM-R |
| `nlp-service/train_colab_electra_v2.ipynb` | ELECTRA v2, lr 5e-5, class-weighted |
| `nlp-service/train_colab_v3.ipynb` | XLM-R retrain on minimal pairs, 512 tokens, label smoothing, acceptance gates, calibration (§14.4) — generated by `training/make_retrain_notebook.py` |

Inputs for v3, all produced locally: `training/make_minimal_pairs.py --pairs 480
--seed 7`, checked by `training/audit_training_data.py`; `training/gates.json`
from `training/build_gates.py` (needs the private screenshots and redaction
list); scored locally with `training/score_gates.py [model_dir]`. All five are
bundled for Colab by `training/pack_for_colab.py` into `colab_upload_v3.zip`
with a SHA-256 manifest the notebook checks — Colab's picker selects from one
folder at a time, so uploading the files individually sent only some of them.

`train_colab_compare.ipynb` trains both backbones in one session across multiple
seeds. It was not used for the results above — each model here was trained in its
own run — and re-running it would produce a *different* XLM-R from the one on
disk.

The v2 notebook's section 7 runs the checks that caught the v1 failure:
confidence spread, hand-written probes scored separately for transcripts and
fragments, and the real validation conversations.

Local evaluation of the saved weights requires no GPU; inference needs roughly
0.6 GB of RAM for ELECTRA and 1.1 GB for XLM-R.

---

## 13. Recommended next work

Ordered by expected value:

0. ~~Run `train_colab_v3.ipynb`~~ — done twice: run 1 (not accepted, deployed
   as interim, §14.7–14.10) and run 2 (worse, discarded, §14.9). What the
   deployed model needs next, in order:
   - **Fill `data/test_real/`** (item 3) with real conversations never used for
     anything else — the only evidence that would count, and the gap an
     examiner will ask about first.
   - **Real-style training pairs:** real legitimate chats, each with a scam twin
     written by changing only the scam/legit lines, so real agents' promotions,
     terms and OCR noise appear in both classes (§14.11's motivating case).
   - **More Malay wording per tactic:** all four of run 1's misses on the
     new-wording pairs are Malay, with words never seen in training
     (`docs/MODEL_EVALUATION.md` §4.8).
1. **Collect English-language scam conversations.** First among the data gaps
   because it has a measured failure attached: §7.5 shows a courier-key English
   scam scoring 0.0282, and every scam in training is code-switched Malay.
2. **Collect more real legitimate conversations.** Eight exist in the whole
   project and all eight are in training, so the model has almost no basis for
   recognising an honest landlord it has not seen. This is also what makes the
   §7.6 false alarms hard to reason about.
3. **Fill the sealed test set.** `data/test_real/` exists with its rule and its
   guard tests (`tests/test_held_out.py`), and `eval/test_real.py` refuses to
   report a number until there is something in it.
4. ~~Add an OCR-path behavioural check~~ — done: `eval/behaviour_checks.py`.
   Any future candidate should pass it before its F1 is quoted.
5. ~~Implement layer 2 with the short-input guard~~ — done (§10), and the backend
   now excludes a guarded result from the score (§11). Remaining: the frontend
   must render `riskBand: "UNKNOWN"` and `message` rather than the number, or a
   guarded scam still reads as harmless.
6. ~~Implement the backend chain~~ — done (§11).
7. ~~Retrain on matched minimal pairs~~ — done: run 1 (§14.7) is this retrain,
   and it is the deployed model. The reasoning, kept for the record: the
   same conversation in the same style and register, differing *only* in the
   scam mechanics. §7.4 shows both models score a conversation stripped of every
   scam mechanic at 0.9995, which means nothing in the current data forces them
   to attend to those mechanics — scam and legitimate conversations differ in
   register, length and phrasing all at once, so matching any of those is enough
   to fit the training set. Minimal pairs remove that shortcut. They also make a
   sharper test than an accuracy number: a model that cannot separate a matched
   pair has not learned the task, whatever its F1 says.
8. Re-run the comparison across several seeds only once the dataset can
   distinguish the candidates. At present it cannot.

---

## 14. The blind test, and what was changed because of it

### 14.1 What happened

A real legitimate conversation — an iBilik agent letting a room, eight
screenshots, never seen by the project — was run blind through the full
pipeline. It came back **0.9995, HIGH, with zero red flags**. The diagnosis is
in `docs/BLIND_TEST_DIAGNOSIS.md`. The hand-transcribed text, with OCR removed
from the question entirely, scores **0.9997**; the production OCR text scores
**0.9998** (`eval/results/gates_xlm-roberta-scam-random.json`). OCR was not the
cause. The model was.

### 14.2 Why the model is wrong — three measured causes

**1. It learned that itemised prices mean scam.** `eval/shortcut_probe.py`
starts from a plain legitimate conversation and adds one kind of content at a
time (`eval/results/shortcut_probe.json`):

| variant | p(scam) |
|---|---|
| plain legitimate conversation, 8 messages | 0.0006 |
| + one line of itemised prices | **0.9492** |
| + terms and penalties | 0.0050 |
| + promotion / "limited units" | 0.0009 |
| + neutral chatter (length only) | 0.0008 |
| + prices + terms | **0.9992** |
| promo + prices + terms, alone, 3 messages | **0.9996** |

One line of prices flips it. Length does nothing on its own.

**2. Every surface feature in the training data predicts the label.**
`training/audit_training_data.py` asks how well a single threshold on one
feature separates the classes (`eval/results/training_data_audit.json`). On
`random/train.csv`, against a 66.8% majority baseline:

| feature | scam mean | legit mean | one-feature accuracy |
|---|---|---|---|
| characters | 533 | 388 | **77.3%** |
| messages | 13.4 | 8.9 | 73.1% |
| RM amounts | 3.4 | 1.7 | 72.8% |
| question marks | 2.7 | 2.2 | 69.1% |

**P(SCAM | ≥ 4 RM amounts) = 93.2%.** The synthetic scam templates itemise costs
and the legitimate ones quote one price, so "cost sheet → scam" is right 93% of
the time in training and wrong for nearly every real agent, who sends one.

**3. It never saw a conversation as long as a real one.** Measured with the
deployed tokenizer (`eval/length_mismatch.py`,
`eval/results/length_mismatch.json`):

| text | tokens | seen by a 256-token cut |
|---|---|---|
| training split, longest | 241 | all |
| validation split, longest | 227 | all |
| real legitimate, production OCR | 733 | **34.9%** |
| real legitimate, clean transcript | 655 | **39.1%** |
| real scam, production OCR | 411 | 62.3% |

The model was served with a 256-token cut, so it read the listing and the price
breakdown and never reached the part where the viewing was arranged and the
keys handed over in person.

### 14.3 What was changed — in code, now

| change | where | effect |
|---|---|---|
| **Sliding windows** instead of truncation: 512 tokens, stride 256, score = highest window | `app/layer2/classifier.py` | the whole conversation is read. On the current model it changes nothing — both real conversations still score > 0.999 — because the weights are the problem, but a retrained model is no longer blinded |
| **Calibration temperature** read from the checkpoint (`calibration_temperature` in `config.json`), clamped to 0.05–20, default 1.0 | `app/layer2/classifier.py`, 8 tests | a retrained model's probabilities can mean what they say. Never changes a verdict. The deployed model has none, so its output is unchanged |
| **Bubble segmentation** for `/ocr`: bubbles found by fill colour, speaker by colour, timestamps and page chrome removed, seam overlaps de-duplicated | `app/ocr/bubbles.py`, `app/ocr/ocr.py` | in the blind test the flat-text path counted 7 messages for the whole chat (76 summed page by page) against a hand count of 34, with no speakers; it now yields 43 labelled `Renter:`/`Owner:` messages. Still high — see 14.6 |
| **Legitimacy signals withheld** when any red flag fires, 4 new signals (`viewing_arranged`, `in_person_handover`, `payment_at_handover`, `platform_agreement`) | `app/layer1/red_flags.py` | see 14.5 — they were never evidence of legitimacy |
| **`evidenceSupport`** in the backend response: `corroborated` / `partial` / `none` / `consistent` / `contradicted` / `not_scored`, with a bilingual message for `none` and `contradicted` | `backend/src/services/scoring.service.js` | a high score with nothing to point at now tells the renter to verify, instead of presenting 0.9995 as a finding. Does not change `riskScore` |
| **Personal data** out of tracked files: names and addresses read from a gitignored list, phone/IC/account numbers by pattern | `training/redaction.py`, `tests/test_redaction.py` | fixtures, gates and eval outputs are redacted before they reach disk; a test fails if a listed name appears in any tracked file |

### 14.4 What was prepared — the retrain, which you run

The weights cannot be fixed by code. `nlp-service/train_colab_v3.ipynb` retrains
`xlm-roberta-base` in Colab (T4) on data built to remove each cause.

**Minimal pairs** (`training/make_minimal_pairs.py --pairs 480 --seed 7`). Every
legitimate conversation has a scam twin that is identical — greeting, property
details, price breakdown, terms, small talk — except for the mechanics: whether
viewing comes before payment, how keys are handed over, whether there is
pressure, where the money goes. Price, length and style then carry no
information and cannot be learned. The generator also covers length:

- an **extended** profile with the long boilerplate real agents send (terms,
  promotions, penalties, house rules) — exactly the content 14.2 showed flipping
  a legitimate chat — in both twins;
- mechanics at a **random position**, the same in both twins, not always at
  the end, where position would become a cue;
- **fragment pairs**: both twins cut at the same line mid-conversation, keeping
  the mechanics — the shape of the second window on a long chat.

**Test pairs come from a held-out family of phrasings.** Holding out whole pairs
was not enough: every pair was assembled from the same sentence banks, and in
the first version 92 of the 93 distinct mechanic sentences in the test split
also appeared word for word in training, so pair accuracy rewarded recognising
a memorised sentence. Test pairs now use different sentences for the same
tactics — viewing refused, pay first, keys by courier, urgency, a third party's
account, and their legitimate counterparts. The shared scaffolding stays common:
it is identical in both twins and carries no label. The generator refuses to
write if any test mechanic sentence occurs in training, the notebook re-checks
before training, and `tests/test_minimal_pairs.py` guards it. Twins now also ask
the same questions; the first version drew the renter's question separately for
each twin, so 54 test line-pairs differed outside the mechanics.

Each row carries `pair_id` (one twin pair; a fragment pair gets `MPnnnn-F`),
`source_group` (the parent pair, so a split never separates a pair from its
fragment) and `family`. A2 is scored per `pair_id`.

Output: 932 training rows (408 pairs + 58 fragment pairs, family `train`) and
166 test rows (72 pairs + 11 fragment pairs, family `heldout`); 79 distinct
mechanic sentences in the test split, none in training. The longest example is
429 tokens and none exceeds 512, so none is truncated
(`eval/results/length_mismatch.json`).

**Audit, before training** (`eval/results/training_data_audit.json`). On the
combined set the notebook trains on, against a 54.8% majority baseline, the
best single feature reaches 58.0% (characters); RM amounts 56.6%; messages
56.7%. P(SCAM | ≥ 4 RM amounts) falls from 93.2% to **57.8%**. Zero rows overlap
the validation split, the sealed test set, the pair test split or the real
legitimate transcript.

**Acceptance criteria, fixed before any training.** All must hold:

| # | criterion |
|---|---|
| A1 | validation macro-F1 ≥ 0.90 |
| A2 | held-out-family minimal pairs: pair accuracy ≥ 0.85 (both twins of a `pair_id` right) |
| A3 | gate `real_legit_production` → LEGITIMATE |
| A4 | gate `real_scam_production` → SCAM |
| A5 | gates `shortcut_plus_prices`, `shortcut_plus_prices_terms` → LEGITIMATE |
| A6 | gate `ablation_mechanics_removed` → LEGITIMATE |
| A7 | under 50% of validation predictions saturated (> 0.99 or < 0.01), on the raw output — a sanity check only |

Training: 512 tokens, class-weighted cross-entropy with label smoothing 0.1,
lr 2e-5, effective batch 16, up to 8 epochs, early stopping on dev macro-F1 (the
original validation split plus 10% of training pairs held out). After training,
one temperature is fitted on dev and saved into the checkpoint; calibration
error is reported on the pair test split, which it never saw. Fragment-pair
accuracy is reported but not gated.

**A7 is not evidence of calibration.** Label smoothing 0.1 sets the training
target to 0.95 / 0.05, so the loss is minimised by predicting about 0.95 —
under A7's 0.99 line. A7 all but passes by construction and only confirms the
smoothing took effect. Calibration is shown, if at all, by the out-of-sample
ECE and Brier score on the held-out pair test after temperature scaling, which
are reported and not gated.

**The service scores exactly as the notebook evaluates.**
`tests/test_notebook_parity.py` takes `windowed_margin` and `probability` out
of the notebook file itself and compares them with `app/layer2/classifier.py`
on a small random XLM-R saved with a `calibration_temperature`, one-window and
seven-window input: equal to 1e-5. Deliberately breaking the service — ignoring
the temperature, stride 200, mean instead of max over windows — makes each
comparison fail.

**The current model against the same gates** (`training/score_gates.py`,
`eval/results/gates_xlm-roberta-scam-random.json`): **3 of 9**.

| gate | expect | p(scam) | |
|---|---|---|---|
| real_legit_production | LEGITIMATE | 0.9998 | fail |
| real_legit_clean | LEGITIMATE | 0.9997 | fail |
| real_scam_production | SCAM | 0.9998 | pass |
| shortcut_base | LEGITIMATE | 0.0006 | pass |
| shortcut_plus_prices | LEGITIMATE | 0.9492 | fail |
| shortcut_plus_prices_terms | LEGITIMATE | 0.9991 | fail |
| ablation_full_scam | SCAM | 0.9997 | pass |
| ablation_mechanics_removed | LEGITIMATE | 0.9995 | fail |
| english_courier_scam | SCAM | 0.0282 | fail |

The notebook was executed end to end locally with a 2-layer model in place of
XLM-R: every cell ran, the temperature was written to `config.json` and read
back by the service, and the untrained model was rejected. That checks the
notebook, not the recipe — only the Colab run can say whether the recipe works.

**To deploy an accepted model:** unzip to `models/xlm-roberta-scam-v3/`, set
`FINETUNED_MODEL_DIR=./models/xlm-roberta-scam-v3` in `.env` (keep the old
folder for rollback), then re-run `eval/truncation_sweep.py` — the six-message
guard was measured on the old model, and `tests/test_layer2.py` fails until the
constants match the new sweep — and `training/score_gates.py`,
`eval/behaviour_checks.py` against the new folder.

### 14.5 Legitimacy signals were never evidence of legitimacy

`eval/legit_signal_rates.py` measures each signal on the 474 corpus
conversations (`eval/results/legit_signal_rates.json`):

| signal | scams | legitimate |
|---|---|---|
| `company_account` | 23.1% | 0.0% |
| `viewing_arranged` | 17.7% | 4.4% |
| `viewing_first` | 12.0% | 1.9% |
| `stamping_mentioned` | 8.5% | 0.0% |
| `formal_documents` | 6.0% | 0.0% |
| **any signal** | **42.7%** | **5.7%** |

All five signals that fire at all fire more often on scams: scammers imitate the
language of a proper letting. Withholding them when a red flag fires brings
"any signal" to 5.4% of scams against 5.7% of legitimate conversations — no
longer misleading, and still not evidence. The four new signals never fire on
this corpus, whose legitimate conversations are too short to reach a handover;
they exist for real ones like the blind test's. The narrator is told to treat
them as context only (`backend/src/services/llm.service.js`).

### 14.6 What is still not fixed

1. **The deployed model is still wrong** on the real legitimate conversation,
   and will be until an accepted retrain replaces it. Until then
   `evidenceSupport: "none"` is the only thing standing between a renter and a
   false alarm with nothing behind it.
2. **Passing the gates would not prove generalisation.** The real legitimate
   conversation was used to diagnose the failure, and the training data was
   designed knowing how it failed. The real scam's text was used to write layer
   1's rules. The pair test comes from the same generator as the training pairs.
   Only conversations placed in `data/test_real/`, used for nothing else, can
   measure real-world accuracy; it is still empty.
3. **The message count over-counts** through bubble segmentation: 29 against a
   hand count of 25 on the four-page scam, 43 against 34 on the eight-page
   legitimate chat (`eval/results/bubble_segmenter.json`). Tuning stopped
   deliberately — two conversations are not enough to tune against without
   fitting them. Both are far above the guard, so no verdict changes; a 5–7
   message chat could land one confidence band too high.
4. **The window score is the maximum**, so one scam-looking stretch makes the
   whole conversation score high. Right for scams, which only need to appear
   once; it also means a long legitimate chat gets more chances to trip a
   residual shortcut than a short one.
5. **English-only scams** remain untrained: `english_courier_scam` scores
   0.0282, and the minimal pairs add English conversations but no real English
   scam exists in the project.

### 14.7 Retrain run 1 — not accepted

`train_colab_v3.ipynb`, run once on Colab, data packed 2026-09-27T22:48:44.
Verbatim printout: `nlp-service/eval/results/v3_run1_printout.txt`. **Verdict:
NOT ACCEPTED.** The model is not deployed; `.env` is unchanged.

| criterion | result | |
|---|---|---|
| A1 validation macro-F1 ≥ 0.90 | 0.9768 | pass |
| A2 held-out-family pair accuracy ≥ 0.85 | 0.9444 (72 pairs); fragment pairs 11/11 | pass |
| A3 `real_legit_production` → LEGITIMATE | **0.7811** | **fail** |
| A4 `real_scam_production` → SCAM | 0.9559 | pass |
| A5 `shortcut_plus_prices`, `…_terms` → LEGITIMATE | 0.0272, 0.0274 | pass |
| A6 `ablation_mechanics_removed` → LEGITIMATE | **0.5219** | **fail** |
| A7 saturated share < 0.50 | 0.0000 — expected by construction (§14.4) | pass |

Against the deployed model, gates went from **3 of 9 to 7 of 9**. The price
shortcut is gone (0.9492 → 0.0272), and a conversation with every scam mechanic
removed dropped from 0.9995 to 0.5219. `english_courier_scam` now passes
(0.0282 → 0.9385), but the courier-key tactic is in the training pairs, so that
is not evidence about unseen English scams.

Calibration: temperature 0.731. Below 1 means label smoothing left the model
*under*-confident and the temperature sharpens it. On the held-out pair test ECE
fell from 0.0655 to 0.0319; Brier did not move (0.0187 → 0.0190).

**Failure 1 — the same conversation passes clean and fails through OCR.** The
hand transcript scores 0.1418; the production OCR text of the same eight
screenshots scores 0.7811. The model now reads the real legitimate conversation
correctly; what fails is the text the OCR path gives it. A word-level comparison
of the two texts (no model needed) finds only 4 of 43 OCR lines with no
counterpart in the transcript. The rest differ structurally: a quoted owner
message reappears as a *renter* line, two owner messages are merged into one,
and "go.ibilik.com" became "Goto: cm", leaving "Login using your registered
mobile number and password" without the platform it refers to. Which of these
moves the score was then measured — §14.8. It was none of them directly: the
window boundary was.

**Failure 2 — a design flaw in the gate itself, noticed only because it
failed.** `ablation_mechanics_removed` is five messages; the service's own
guard says fewer than six cannot be judged. It also keeps the renter asking
twice to view first with no answer, which is residue of the scam rather than a
neutral conversation. 0.52 on that input is close to "cannot tell". This does
**not** change the verdict: the criterion was fixed before training, and
revising a gate after seeing it fail is exactly what pre-registration exists to
prevent. If the gate is revised for a second run, the change and its reason go
into the notebook's criteria before that run, and the report says it was made
after run 1.

**The cost of iterating.** Each run that is diagnosed against the real
legitimate conversation makes that conversation weaker evidence. A second run
tuned on what the diagnosis finds will pass A3 more easily than an honest test
would. `data/test_real/` remains the only measurement that would count.

### 14.8 Run 1 diagnosed, and what changed for run 2

`training/colab_diagnose_gates.py` was run on the run-1 model in Colab;
per-line results in `nlp-service/eval/results/v3_run1_diagnosis.json`.

**The first window ended mid-sentence.** The OCR text is 731 tokens, so the
first 510-token window ended inside the owner's platform-signing message, at
"…Login using your registered mobile number and password … Please take a
screenshot and **send it to**" — "me after signing ya" fell in the next window.
Leave-one-line-out shows it exactly: removing *any one* of lines 0–22, even
"can i take look?", pulls the rest of that sentence into the window and drops
the score from 0.78 to between 0.09 and 0.33; removing any of lines 24–42, which
are not in that window, changes nothing (0.0000). The clean transcript is 78
tokens shorter, so its first window holds the whole message, and it scores
0.14. OCR noise mattered only by adding those tokens.

**Underneath, the clean pass hangs on one line.** In the clean transcript,
removing the platform-signing message alone raises the score from 0.14 to 0.81;
in the OCR text, removing it raises the score to 0.90. A window holding the
listing, promotion, terms, prices and viewing chat — with nothing wrong in it —
scores around 0.8–0.9, because no training example ever said what such text
is. With the highest window taken as the conversation's score, that undefined
value became the verdict. `ablation_mechanics_removed` (0.52) is the same gap:
the renter's questions, with the scam removed.

**Changes for run 2** — general rather than fitted to that chat, but chosen
after seeing it fail, which the notebook states:

| change | where | check |
|---|---|---|
| Windows cut only **between messages**, never inside one; up to 510 tokens of whole messages, next window about 256 tokens on, last window packed back from the end; only a single over-long message is ever split | `app/layer2/classifier.py` `_message_windows`, the notebook's `message_windows` | tokenizing message by message equals the whole text on 416 of 416 texts, so windows are exact slices; 4 window-shape tests; parity test compares the two token for token, and catches the old fixed-offset windows as a mismatch |
| **Prefix** rows: text before the twins diverge, identical in both, labelled LEGITIMATE — a window's label now means "scam behaviour is in this text" | `training/make_minimal_pairs.py` | verified to contain only lines both twins share |
| **Core** rows: as many messages from the scam twin, including its first scam line, labelled SCAM | same | without them prefixes made length a shortcut — characters predicted the label at 60.5% against a 52.0% baseline; with them, 54.9% against 53.0% |
| **Truncated** pairs: both twins cut after the mechanics, before the goodbye, so an abrupt ending belongs to both classes | same | twin checks as for full pairs |

The data now: 1,772 training rows (408 pairs, 68 fragment pairs, 210 truncated
pairs, 200 prefixes, 200 cores) and 312 held-out-family test rows; 88 test
mechanic sentences, none in training; audit verdict OK, zero leakage
(`eval/results/training_data_audit.json`). The first window of the real OCR text
now ends on a whole message (line 22) and the platform-signing message sits
whole in the second (`eval/results/length_mismatch.json`: still 2 windows).

**What is not expected.** Message-aligned windows alone would probably not have
saved run 1: its first window would then be lines 0–22 without the signing
message, the kind of window it scored 0.8–0.9. The two changes are meant to
work together. The criteria are unchanged, including the flawed
`ablation_mechanics_removed` gate (§14.7). Run 2's report must say that A3 and
A6 are being retested on the conversation whose failure shaped the changes.

### 14.9 Retrain run 2 — not accepted, and worse than run 1

Printout: `nlp-service/eval/results/v3_run2_printout.txt`. Diagnosis (run on the
run-2 model in the same Colab session): `v3_run2_diagnosis.json`. Data
comparison with run 1: `eval/run2_data_comparison.py` →
`run2_data_comparison.json`. Run 1's data was rebuilt exactly for this (the
run-1 model scores 0.9444 pair accuracy on the rebuilt test split, as in Colab).

| | run 1 | run 2 |
|---|---|---|
| held-out-wording pair accuracy (A2) | 0.9444 | **0.7361** |
| real legit chat, clean / OCR | 0.14 / 0.78 | **0.94 / 0.95** |
| English courier scam | 0.94 | **0.27** |
| scam with mechanics removed (A6) | 0.52 | 0.05 |
| gates passed | 7 of 9 | 6 of 9 |

**Every error is a missed scam.** Legitimate rows: 100% right in every kind.
Scam rows: 74% of full conversations, 44% of cores. Missed scam twins by
language: Malay 12 of 24, mixed 5 of 25, English 2 of 23.

**It recognises words, not tactics.** Same generator, same scaffolding: pairs
worded as in training score **1.000**, pairs in held-out wording **0.736**. The
missed scam lines are full of words that never occur in training — *berkunci*,
*tempahan*, *Poslaju*, *DuitNow*, *holding fee*, *midnight*. Run 2 repeated
each training mechanic sentence 43 times on average (run 1: 27.7), which
rewards memorising them.

**The core rows were mislabelled** (my error). 166 of 200 (83%) held nothing but
the owner saying they cannot show the unit — not a scam without a payment
demand. On the held-out split run 2 called these 38% SCAM, against 63% for
cores that included a payment demand (8 rows; small).

**Why the real legit chat flipped.** Its first window is fine (0.045). The
second scores 0.94 almost entirely because of one agent message: "This
promotion is valid for the August move in only, and our rooms can **reserve**
for up to 30 days only" — removing it lowers the score by 0.887. In run 1 that
line had no effect (−0.0001). "Reserve" appears only in scam rows in all the
training data — 132 times in run 1, 251 in run 2, 58 of them in short core
rows where it is nearly the whole scam content. The English scam is missed the
same way in reverse: "Pay one month rent and I'll mail the keys" alone pulls it
to LEGITIMATE (removing it raises the score by 0.668).

**Calibration made it worse.** The temperature was fitted on dev, which the
model got 100% right (275 rows), so it came out at 0.176 and sharpened every
score, including the mistakes: out-of-sample ECE 0.151 → 0.157.

**Lessons for any further retrain.** (1) Remove core rows. (2) The limit is
wording: about 115 mechanic sentences, repeated dozens of times, are learned as
keywords; what is needed is many more phrasings per tactic — in Malay above all
— ideally from real chats. (3) Fit the temperature on held-out wording, not on
a dev set the model has memorised, keeping a separate part for testing it.

### 14.10 Run 1 deployed as an interim model

Decided by the author on 2026-09-28, after run 2's diagnosis. **Run 1 did not
meet its pre-registered acceptance criteria** (A3, A6) and is not described
anywhere as accepted. It replaces the original model because it is better on
every measurement both were given, and the original model was never held to
those criteria at all.

`.env`: `FINETUNED_MODEL_DIR=./models/xlm-roberta-scam-v3-run1`; the original
model is one commented line below it for rollback. The weights are
byte-identical to the run-1 download (SHA-256 `dc4244d2…5851a9f`) and carry
`calibration_temperature` 0.731, which the service applies.

**Gates**, scored by `training/score_gates.py` with the service's own
message-aligned windows (`eval/results/gates_*.json`):

| gate | expect | original | run 1 (raw) | run 1 as served |
|---|---|---|---|---|
| real_legit_production | LEGIT | 0.9997 ✗ | 0.8836 ✗ | 0.9411 |
| real_legit_clean | LEGIT | 0.9996 ✗ | 0.1406 ✓ | 0.0776 |
| real_scam_production | SCAM | 0.9998 ✓ | 0.9560 ✓ | 0.9853 |
| shortcut_base | LEGIT | 0.0006 ✓ | 0.0258 ✓ | 0.0069 |
| shortcut_plus_prices | LEGIT | 0.9492 ✗ | 0.0273 ✓ | 0.0075 |
| shortcut_plus_prices_terms | LEGIT | 0.9991 ✗ | 0.0274 ✓ | 0.0075 |
| ablation_full_scam | SCAM | 0.9997 ✓ | 0.9540 ✓ | 0.9844 |
| ablation_mechanics_removed | LEGIT | 0.9995 ✗ | 0.5313 ✗ | 0.5428 |
| english_courier_scam | SCAM | 0.0282 ✗ | 0.9386 ✓ | 0.9765 |
| **passed** | | **3 / 9** | **7 / 9** | |

"As served" applies the temperature, which sharpens scores; pass/fail is
judged on the raw score, and the two never disagree about which side of 0.5.

**Behaviour checks** (`eval/behaviour_checks.py`; the original model's run kept
as `behaviour_checks_xlmr_random.json`): mechanics-removed scam 0.9995 → 0.5313;
English scams caught 4/5 → 5/5; benign short messages flagged 2/8 → 0/8;
validation macro-F1 0.9883 → 0.9768 (recall 0.984 → 0.968).

**Short-input guard re-measured** (`eval/truncation_sweep.py`; the original's
sweep kept as `truncation_sweep_xlmr_random.json`): run 1 first beats the
always-SCAM baseline (0.708) at **6 messages**, the same threshold as before,
so the constants are unchanged; the accuracies quoted in
`app/layer2/classifier.py` were updated (6: 0.792, 7: 0.889, 8: 0.903).

**End to end** through `/classify`: the real scam 0.9853 with 8 red flags; the
clean real legitimate chat 0.0776; the same chat through OCR **0.9411 with no
red flags**. That last case is the known remaining failure. The backend's
`evidenceSupport: "none"` is what stands between it and the renter: a high
score with nothing behind it is reported with "verify before paying" rather
than as a finding.

All tests pass with run 1 live: Python 320 passed, 3 skipped (the empty
`data/test_real/`), including the three that call the real weights; backend 26.

### 14.11 Decision reversed: a high score with no red flag is capped at MODERATE

**Decided by the author, 2026-09-28.** This reverses the rule in §10 that layer
1 never affects the result. It still contributes nothing to `scam_probability`;
it now caps the *band*.

**Why.** The motivating case is the real, legitimate iBilik conversation. Through
OCR, the deployed model scored it 0.9292–0.9411 — HIGH — while layer 1 found no
red flag at all and three legitimacy signals (keys handed over in person,
payment at handover, an agreement through the platform). A renter would have
been told a genuine letting was high risk with nothing in the text to point to.
Retraining on real-style data is the real fix (§14.9); this is the guard until
then.

**The rule** (`backend/src/services/scoring.service.js`,
`capUnsupportedScore`; contract in `docs/API_SPEC.md`):

| condition | result |
|---|---|
| model ≥ 0.5, status ok, **no red flags**, score > 49 | band **MODERATE**, `riskScore` 49, `bandCap` records the score and band before the cap; `evidenceSupport` "none" with "no specific scam tactic was found; verify the landlord and the unit before paying" |
| any red flag | unchanged — HIGH / CRITICAL possible |
| model < 0.5 | unchanged |
| layer 2 could not judge | UNKNOWN, unchanged |

It never lowers a result below MODERATE (a model score ≥ 0.5 is at least 30
points by itself). Legitimacy signals play no part in it — they are listed as
context. `modelProbability` and the NLP service's probabilities are untouched.

**Cost**, measured by `nlp-service/eval/cap_cost.py` with the backend's own code
(`backend/scripts/apply_band_cap.js`), deployed model, NLP signal alone as in
production (`eval/results/cap_cost.json`):

| set | scams | scams with no red flag | → band after the cap | legitimate moved HIGH → MODERATE |
|---|---|---|---|---|
| random/train (model trained on it) | 253 | 25 | 24 HIGH→MODERATE, 1 already LOW | 0 of 126 |
| random/val | 63 | 8 | 8 HIGH→MODERATE | 0 of 32 |
| minimal-pair test (wording never trained on) | 72 | **40** | 36 HIGH→MODERATE, 2 stay MODERATE, 2 already LOW | 0 of 72 |
| real conversations | 1 | 0 | stays HIGH | — (see below) |

No scam falls below MODERATE because of the cap, in any set. On the corpus the
cost is 32 of 316 scams (10%) shown as MODERATE instead of HIGH. On unfamiliar
wording it is far larger — 36 of 72 — because layer 1's rules are written in
the same wording as the training data and miss new phrasings just as the model
does. No corpus legitimate conversation scored HIGH in the first place, so the
benefit is visible only on real text.

**Two input fixes found in the same iBilik output.**

1. *Camera watermarks inside photos.* The camera's "2:28 PM | Aug 05, 2026 /
   Subang Jaya Selangor" stamp on a room photo was read as a renter message. It
   sits on a flat patch of the photo (the floor), so the existing flatness test
   passes it. A new test compares each line's background with the two bubble
   colours of the whole upload (`app/ocr/bubbles.py`, `drop_media_text`):
   measured on both real chats, typed lines — quote boxes and link previews
   included — lie within 11.1 (mean absolute RGB), the stamp at 18.3–24.7; the
   cut is 15. A speaker's colour must carry twice the text of any other colour
   attributed to them before anything of theirs is dropped, so a sparse chat
   never loses a real message (found by a unit test that dropped one). Result:
   the legitimate chat 43 → 42 messages (renter 20 → 19), the scam chat
   unchanged at 29; the hand counts are still 34 and 25.
2. *Links.* OCR read "go.ibilik.com" as "cm", and the normaliser expanded "cm"
   to "macam". Link-shaped tokens were already left alone, by accident of the
   tokenizer; that is now an explicit rule, and the token after a link cue
   ("go to:", "goto:", "link:") is also left alone. `normalised_text` now
   reads "goto: cm".

**End to end** (fresh NLP service and backend on the final code; both real
screenshot sets posted to `POST /api/analyze/screenshot` in page order):

| chat | `riskScore` | band | `bandCap` | `modelProbability` | `evidenceSupport` | red flags | legitimacy signals |
|---|---|---|---|---|---|---|---|
| real scam, 4 pages | 59 / 60 | **HIGH** | null | 0.9854 | corroborated | 8 | — |
| real iBilik legit, 8 pages | 10 / 60 | **LOW** | null | 0.1648 | consistent | 0 | in-person handover, payment at handover, platform agreement |
| iBilik, pre-fix OCR text, `POST /api/analyze` | 49 / 60 | **MODERATE** | applied: 56 / HIGH before | 0.9411 | none (+ message) | 0 | the same three |

The iBilik chat did **not** land in MODERATE as expected: after the watermark
fix the model itself scores it LOW. That is a boundary effect, not a better
model — with the watermark's ~20 tokens gone, the platform-signing message fits
in the same 510-token window as the promotion and terms, and the window scores
0.1648; put the watermark line back and it scores 0.9292. A slightly longer
chat would flip it back, and then the cap holds it at MODERATE — the third row
is that case, through the live API.

**Gates rebuilt.** `training/gates.json` is defined as the production pipeline's
output, so it was rebuilt after the watermark fix; only
`real_legit_production` changed, and the previous file is kept as
`training/gates_2026-09-27.json` (runs 1 and 2 were judged on it). Scored
again, the deployed model passes it (0.3024 raw) — **8 of 9** — for the same
boundary reason. Run 1's verdict, made at the time, stays NOT ACCEPTED; the
remaining failure is `ablation_mechanics_removed` (0.5313).

**Open.** With OSINT and price not yet implemented, the cap's interaction with
them is untested; as written, it would also hold a result at MODERATE that
independent OSINT evidence pushed higher. Decide when those signals go live.

### 14.12 The zero-shot second model: tested and dropped

The original design had a second, zero-shot model for "calibration". It was
never built. Before deciding, it was tested once, with the decision rule set by
the author before any result existed: **unless it clearly beats run 1 on the
new-wording pairs AND the real iBilik chat, drop it; if it does, it may be added
later as an extra evidence signal — never as calibration.**

A zero-shot model cannot calibrate another model in any case: calibration needs
labelled data the model has not seen, and the deployed checkpoint already
carries its own temperature (§14.4). The only open question was whether it adds
information.

**Set-up** (`nlp-service/eval/zero_shot_test.py`; everything below fixed in
`eval/results/zero_shot_test/plan.json` before scoring, and the script refuses
to run if that file changes):

- Model: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, local, no
  training.
- Hypotheses in English and Malay — scam: payment before viewing, keys by
  courier, owner unavailable, paying into someone else's account, urgency;
  legitimacy: viewing arranged, agreement signed via a platform, keys handed
  over in person.
- P(entailment) = softmax over the entailment and contradiction logits (the
  standard multi-label zero-shot recipe). Chat score = the strongest scam
  hypothesis minus the strongest legitimacy hypothesis, over message-aligned
  windows (run 1's `_message_windows`, sized to leave room for the hypothesis).
- Threshold chosen on the validation split only.
- "Clearly beats": pair accuracy at least run 1's + 0.05, **and** the real
  iBilik chat called legitimate on both its current and its pre-fix OCR text.
- Disclosed in the plan: one load-check sentence pair was scored before the
  hypotheses were written.

**Result** (`eval/results/zero_shot_test/table.md`; CPU: Intel, 12 logical
cores, 8 torch threads):

| | run 1 (deployed) | zero-shot mDeBERTa |
|---|---|---|
| threshold | 0.5 | −0.0519 (chosen on validation) |
| validation accuracy | 0.9789 | 0.6632 |
| new-wording pairs: row accuracy | 0.9722 | 0.5000 |
| new-wording pairs: pair accuracy | 0.9444 | **0.0000** |
| real scam chat (current OCR) | 0.9560 SCAM ✓ | SCAM ✓ |
| real iBilik chat (current OCR) | 0.3024 LEGIT ✓ | SCAM ✗ |
| real iBilik chat (pre-fix OCR) | 0.8836 SCAM ✗ | SCAM ✗ |
| real iBilik chat (hand transcript) | 0.1406 LEGIT ✓ | SCAM ✗ |
| English courier scam | 0.9386 SCAM ✓ | SCAM ✓ |
| CPU seconds per chat, median / mean | 0.27 / 0.30 | 4.06 / 5.96 |
| CPU seconds per real chat, mean | 0.61 | 40.53 |

Both criteria fail. **Decision: dropped.**

What the numbers show: the zero-shot model does not discriminate at all. Every
hypothesis, scam and legitimacy alike, comes out at 0.99–1.00 entailment on
nearly every chat (validation medians: strongest scam 0.9966, strongest
legitimacy 0.9954), so the score moves only in the third decimal. No threshold
beats answering SCAM for everything — the one chosen on validation sits just
below the lowest validation score and does exactly that: 0.6632 is the
always-SCAM baseline (63 of 95), both twins of every pair get the same answer
(pair accuracy 0.0), and its "correct" scam verdicts come from answering SCAM
to everything. It is also about 20 times slower per chat, 65 times on the long
real ones.

One limitation, stated rather than explored: the recipe drops the "neutral"
class, which is what saturates the scores, and the plan did not include an
alternative. Trying other recipes after seeing this result is the kind of
search the fixed rule exists to prevent, and the one pair scored before the
plan was written came out 98% neutral, so there is little sign another recipe
would change the outcome.

What remains of the idea: `SECONDARY_MODEL` and `ZERO_SHOT_LABELS` in
`app/config.py` and `.env` are marked unused. The stale reason in
`app/layer2/classifier.py` ("the fine-tuned classifier separates the validation
set cleanly") is replaced by this result.

### 14.13 Semantic red flags (sentence embeddings): tested and dropped

**Question.** Layer 1's regex misses scams worded differently from its patterns:
on the new-wording minimal-pair test set it flags 32 of 72 scam twins and misses
40 (§14.11). Could sentence embeddings match the same tactics by meaning?

**Rule, set by the author before any result:** adopt only if, on the
new-wording pairs, the semantic flags catch at least half of the scam twins
layer 1 misses (20 of 40), AND flag no legitimate twin beyond what layer 1
already flags (it flags 0), AND raise no new red flag on the real iBilik chat.
Otherwise report and drop. Not wired into the band rules either way.

**Everything fixed before scoring** (`eval/results/semantic_flags/plan.json`,
which hashes the example bank; the script refuses to run if either changes):

- *Candidates.* `intfloat/multilingual-e5-base` (278M parameters) and the
  smallest mesolitica Malaysian model, `mesolitica/embedding-malaysian-mistral-64M-32k`
  (48M parameters counted). The mesolitica leaderboard needs a login and could
  not be read, so "best small one" could not be confirmed; the 64M model is the
  smallest they publish. It needs `trust_remote_code`: its code file was read
  before use (a Mistral model plus one linear layer, no file or network access)
  and the revision is pinned (`ca29fada…`).
- *Example bank* (`app/layer1/semantic_tactics.json`, built by
  `eval/build_semantic_bank.py`): 8 tactics, 8–12 examples each, 78 in all —
  71 written from layer 1's own rules in BM, English and Manglish, each one
  verified to be flagged by its tactic's rule, plus 7 owner messages of the
  development scam chat, assigned by which rule fires on them. Nothing from the
  test split or `data/test_real/`. Because the same author wrote the held-out
  test sentences, every example was compared with every test line; none is a
  near duplicate (closest difflib ratio 0.696, cut 0.8).
- *Matching.* Owner messages only; a message's score for a tactic is its
  highest cosine similarity to that tactic's examples.
- *Thresholds*, one per tactic, from the original training and validation data
  only: just above (+0.01) the highest score that tactic reaches on any owner
  message of a legitimate conversation — no false alarm there by construction.
- *Model choice* on the minimal-pair results, as the author asked: fewer
  legitimate twins flagged, then more layer-1 misses caught, then CPU time.

**Sanity check** (`eval/results/semantic_flags/sanity.md`):

| pair | expected | e5-base | mesolitica 64M |
|---|---|---|---|
| "byr dlu baru blh tgk" / "pay first before viewing" | match | 0.759 | 0.796 |
| "rumah berkunci, tak boleh masuk tengok" / "the unit is locked, no viewing" | match | 0.857 | 0.614 |
| "I hantar keys by Poslaju" / "kunci saya pos" | match | 0.878 | 0.684 |
| "jangan bayar sebelum tengok" / "bayar dulu sebelum tengok" | **no match** | **0.969** | **0.891** |
| "boleh viewing dulu?" (renter) / "bayar dulu baru viewing" | no match | 0.899 | 0.538 |

Both models rate "**don't** pay before viewing" as closer to "pay before
viewing" than any true paraphrase in the table.

**Result** (`eval/results/semantic_flags/table.md`, `summary.json`):

| new-wording pairs, 72 each | layer 1 alone | + semantic, e5-base | + semantic, mesolitica 64M |
|---|---|---|---|
| scam twins caught | 32 | 47 | 40 |
| of the 40 layer 1 misses, caught (need 20) | — | **15** | **8** |
| legitimate twins flagged | 0 | **6** | **35** |
| real scam chat (development chat; the bank came from it) | 8 red flags | 9 semantic | 7 semantic |
| real iBilik chat — current OCR / pre-fix OCR / transcript | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / **1** |
| CPU seconds per chat, median / mean (owner messages only, cache emptied; 4 real-chat versions + 20 test chats) | — | 0.221 / 0.338 | 0.143 / 0.176 |

e5-base is the model the plan's rule picks. It fails criteria (a) and (b);
mesolitica fails all three. **Decision: dropped.**

**Why.** The embeddings match the *form* of a sentence, not the scam behaviour
in it:

- All 6 of e5's false alarms come from one ordinary landlord line, "maaf, tak
  boleh bela haiwan" ("sorry, no pets"), matching the viewing-refused example
  "Tidak boleh lawat unit tu, maaf" at 0.906 (threshold 0.900) — a refusal, but
  of pets, not of a viewing.
- mesolitica matches on register: "should be ok, nanti saya confirm" against a
  competition-pressure example; on the iBilik transcript, "Can move in
  earlier" against "It's first come first serve" (0.922).
- The classes barely separate even on the data the thresholds were set on: at
  a threshold with no false alarm on the legitimate training and validation
  chats, e5 flags 4 of 316 training/validation scams (mesolitica 11). What e5
  does catch among the layer 1 misses is deadline/urgency (9), keys by courier
  (6) and booking fee (1).

**Baseline for the report:** embeddings + logistic regression (conversation =
mean of its message embeddings; trained on exactly the data run 1 was trained
on), next to run 1:

| | run 1 (deployed) | e5-base + LR | mesolitica 64M + LR |
|---|---|---|---|
| validation accuracy | 0.9789 | 0.8421 | 0.8316 |
| validation macro-F1 | 0.9768 | 0.8037 | 0.7930 |
| new-wording pairs: row accuracy | 0.9722 | 0.7639 | 0.6319 |
| new-wording pairs: pair accuracy | 0.9444 | 0.5278 | 0.2917 |

The fine-tuned model is far ahead of a frozen-embedding classifier; on the two
real chats the baselines return 0.49–0.60, i.e. no opinion.

**Side findings about layer 1, not fixed here.** Building the bank checked
every hand-written example against its own rule, and 5 failed. Two are rule
defects worth fixing separately: the normaliser rewrites "owner" to "pemilik",
so `remote_owner`'s pattern "owner (is) busy/away/not around" can never fire in
production; and `deadline_pressure`'s verbs are Malay only, so "please **pay**
before 6pm" is not flagged. The others were suppressed by layer 1's time-scope
exception ("this week", "buat masa ini"), which is working as designed.

**Caveat.** Choosing the model on the test results, as asked, makes the chosen
model's numbers slightly optimistic; with both models failing, it does not
affect the outcome.
