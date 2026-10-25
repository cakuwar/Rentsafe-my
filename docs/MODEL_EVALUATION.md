# Model evaluation — the deployed scam classifier (XLM-R, retrain run 1)

Evaluation of the layer 2 classifier deployed in the RentSafe-MY NLP service:
`nlp-service/models/xlm-roberta-scam-v3-run1`. Every figure below is produced by
a script in `nlp-service/eval/` and stored in `nlp-service/eval/results/`; the
main file is `run1_evaluation.json` (built by `eval/run1_evaluation.py`).
Positive class = **SCAM** throughout.

---

## 1. Summary

| test | what it measures | result |
|---|---|---|
| Validation set (95 conversations) | accuracy on held-out conversations of the original corpus | accuracy **0.979**, macro-F1 **0.977**, ROC-AUC **0.994**; 0 false alarms, 2 missed scams |
| New-wording minimal pairs (72 pairs, 144 conversations) | whether the model reads the scam behaviour itself, in wording never seen in training | accuracy **0.972**, pair accuracy **0.944**, ROC-AUC **1.000**; 0 false alarms, 4 missed scams |
| English-only conversations (10) | language not well covered by the training data | 10 / 10 correct |
| Benign one-line messages (8) | false alarms on short, harmless messages | 0 / 8 flagged |
| Real conversations (2 chats, 4 versions) | real screenshots through the OCR pipeline | 3 of 4 correct (see §4.6) |
| Acceptance gates (9, fixed before training) | targeted behaviours | 8 of 9 pass today; 7 of 9 when judged after training |
| Calibration | whether a probability means what it says | ECE 0.040 → 0.028 after temperature scaling (validation) |
| Short input | accuracy when few messages are visible | beats the trivial baseline from **6 messages**; below that the service reports "insufficient context" |
| Speed | CPU, one conversation | median 0.18 s; long real chats ≈ 1 s |

**Status.** Run 1 did **not** meet all of its pre-registered acceptance criteria
when trained (two of nine gates failed, §4.7). It is deployed as an **interim**
model because it outperformed the model it replaced on every test both were
given (§5). The evaluation's main limitation is that no independent set of real
conversations exists yet (§6).

---

## 2. The model

| item | value |
|---|---|
| base model | `xlm-roberta-base` (multilingual transformer), 278M parameters |
| task | binary classification of a whole chat: SCAM / LEGITIMATE |
| output | P(SCAM); decision threshold 0.5 |
| input length | up to 512 tokens per window; longer chats are split into windows **cut only between messages**, about 256 tokens apart, and the chat's score is the **highest window** |
| calibration | logits divided by a temperature of **0.731** before softmax (fitted after training); it changes how confident a score is, never which side of 0.5 it falls |
| short-input guard | fewer than 6 messages and a low score → reported as `insufficient_context`, not as low risk (§4.4) |

**Training data** (counts recomputed in `run1_evaluation.json → training_data`):

| part | rows | scam / legitimate |
|---|---|---|
| original corpus, training split | 379 | 253 / 126 |
| + minimal pairs (scam / legitimate twins identical except for the scam behaviour) | 844 | 422 / 422 |
| **= trained on** | **1,223** | **675 / 548** |
| model selection set (early stopping and calibration): validation 95 + held-out pairs 88 | 183 | — |

The minimal pairs exist because the first model learned shortcuts (§6): in the
original corpus, a conversation's length alone predicted its label 77% of the
time, and an itemised price list predicted "scam" 93% of the time. In a minimal
pair, price, length and style are identical in both twins, so only the
behaviour — viewing refused, payment before viewing, keys by courier, pressure,
payment to a third party — can tell them apart.

**Training configuration** (`nlp-service/train_colab_v3.ipynb`): Colab T4 GPU;
cross-entropy with class weights and **label smoothing 0.1**; learning rate
2e-5, warm-up 10%, weight decay 0.01; batch 8 × 2 gradient-accumulation steps;
up to 8 epochs with **early stopping** (patience 2) on macro-F1 of the selection
set; mixed precision; seed 42.

---

## 3. Evaluation design

| set | size | source | used during training? |
|---|---|---|---|
| **Validation** | 95 (63 scam / 32 legit) | original corpus, random split | **yes** — for early stopping and for fitting the temperature, so its scores are optimistic |
| **New-wording minimal pairs** | 72 pairs = 144 | generated; every scam/legit sentence in them uses wording that **never appears in training** (checked: 0 of 88 sentences) | no |
| English-only probes | 5 scam + 5 legit | written by the author | no |
| Benign short messages | 8 | written by the author | no |
| Real conversations | 1 scam (4 screenshots), 1 legitimate (8 screenshots) | real WhatsApp chats | no — but both were used to *diagnose* earlier models (§6) |
| Acceptance gates | 9 | criteria and texts fixed **before** training | no |

The **new-wording minimal pairs are the main test.** Pair accuracy — both twins
of a pair correct — cannot be achieved by any shortcut: a model that reads
anything other than the scam behaviour gives both twins the same answer and
scores 0.

---

## 4. Results

### 4.1 Validation set (95 conversations)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| **actual SCAM** (63) | **61** TP | **2** FN |
| **actual LEGIT** (32) | **0** FP | **32** TN |

| accuracy | precision (scam) | recall (scam) | specificity | F1 (scam) | macro-F1 | MCC | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|---|---|
| 0.9789 | 1.0000 | 0.9683 | 1.0000 | 0.9839 | 0.9768 | 0.9546 | 0.9936 | 0.9971 |

Majority-class baseline (always "scam"): accuracy 0.6632. The Colab run gave
the same accuracy and macro-F1 (0.9789 / 0.9768, `v3_run1_printout.txt`).

### 4.2 New-wording minimal pairs — the main test (144 conversations)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| **actual SCAM** (72) | **68** TP | **4** FN |
| **actual LEGIT** (72) | **0** FP | **72** TN |

| accuracy | precision | recall | specificity | F1 | macro-F1 | MCC | ROC-AUC | **pair accuracy** |
|---|---|---|---|---|---|---|---|---|
| 0.9722 | 1.0000 | 0.9444 | 1.0000 | 0.9714 | 0.9722 | 0.9459 | 1.0000 | **0.9444** (68 / 72) |

Any constant answer scores accuracy 0.5 and pair accuracy 0.0 here.

**By language:**

| language | pairs | pair accuracy | missed scams | false alarms |
|---|---|---|---|---|
| English | 23 | 1.000 | 0 | 0 |
| Manglish (mixed) | 25 | 1.000 | 0 | 0 |
| Malay | 24 | **0.833** | 4 | 0 |

ROC-AUC of 1.000 means every scam was ranked above every legitimate
conversation: the four misses are threshold misses (scores 0.05–0.18), not
inversions. The threshold was **not** adjusted on this set — doing so would make
it no longer a test.

### 4.3 Behavioural tests

| test | result |
|---|---|
| English-only conversations | 5 / 5 scams caught, 5 / 5 legitimate cleared (accuracy 1.000) |
| Benign one-line messages (e.g. "Sure, you can view the unit this Saturday.") | 0 / 8 flagged |
| **Group ablation**: a scam with every scam line removed | full scam 0.9536 → scam lines removed **0.5313** → scam lines only 0.9538 |

The ablation is the weakest result: once every scam line is removed, the
remaining conversation (a renter asking twice to view, no reply) should score
clearly legitimate, but scores 0.53 — "cannot tell". The previous model scored
the same text 0.9995 (§5).

### 4.4 Short input — how many messages are needed

`eval/truncation_sweep.py`: the first *n* messages of the 72 validation
conversations that have at least 8 (51 scam / 21 legit). Always answering
"scam" scores 0.708 on this subset.

| messages visible | 1 | 2 | 3 | 4 | 5 | **6** | 7 | 8 | all |
|---|---|---|---|---|---|---|---|---|---|
| accuracy | 0.292 | 0.319 | 0.375 | 0.542 | 0.667 | **0.792** | 0.889 | 0.903 | 1.000 |
| F1 (scam) | 0.000 | 0.075 | 0.211 | 0.522 | 0.692 | 0.828 | 0.915 | 0.929 | 1.000 |

Below 6 messages the model is worse than the trivial baseline and errs toward
"legitimate" — a false all-clear. The service therefore reports a low score on
fewer than 6 messages as **`insufficient_context`** ("send more of the
conversation"); a *high* score on short input is still reported. Confidence
labels follow the curve: 6 → low, 7 → moderate, 8+ → high.

### 4.5 Calibration

Label smoothing keeps raw scores away from 0 and 1 (no raw score above 0.99 or
below 0.01 on any set). A temperature of 0.731 was then fitted on the selection
set; below 1, it sharpens scores.

| set | ECE raw → served | Brier raw → served | share of scores > 0.99 or < 0.01, served |
|---|---|---|---|
| validation | 0.0395 → **0.0278** | 0.0215 → 0.0209 | 0.34 |
| new-wording pairs | 0.0436 → **0.0373** | 0.0265 → 0.0266 | 0.50 |

Temperature scaling lowers the expected calibration error on both sets; the
Brier score is unchanged. The validation figures are in-sample for the
temperature; the minimal-pair figures are out of sample.

### 4.6 Real conversations

| conversation | expected | P(scam) raw | as served | result |
|---|---|---|---|---|
| real scam chat — 4 screenshots, OCR | SCAM | 0.956 | 0.985 | ✓ |
| real legitimate iBilik chat — 8 screenshots, OCR (current pipeline) | LEGIT | 0.302 | 0.242 | ✓ |
| same chat, OCR before the camera-watermark fix | LEGIT | 0.884 | 0.941 | ✗ |
| same chat, hand-typed transcript | LEGIT | 0.141 | 0.078 | ✓ |

The legitimate chat is the hardest case. Removing one OCR artefact (a camera
date stamp read as a message) moves a window boundary so that the agent's
platform-signing message falls in the same window as the promotion and terms,
and the score drops from 0.88 to 0.30. Its correctness therefore depends on
window composition — it is right, but by a narrow and fragile margin. When the
model scores a chat high but layer 1 finds no scam behaviour in it, the backend
holds the result at MODERATE and tells the user to verify (system design, not
part of this model).

### 4.7 Acceptance gates (fixed before training)

| # | criterion | at acceptance (27 Sep) | now |
|---|---|---|---|
| A1 | validation macro-F1 ≥ 0.90 | 0.9768 ✓ | 0.9768 ✓ |
| A2 | new-wording pair accuracy ≥ 0.85 | 0.9444 ✓ | 0.9444 ✓ |
| A3 | real legitimate chat (OCR) → legitimate | 0.7811 ✗ | 0.3024 ✓ |
| A4 | real scam chat (OCR) → scam | 0.9559 ✓ | 0.9560 ✓ |
| A5 | legitimate chat + itemised prices (+ terms) → legitimate | 0.0272 / 0.0274 ✓ | 0.0273 / 0.0274 ✓ |
| A6 | scam with every scam line removed → legitimate | 0.5219 ✗ | 0.5313 ✗ |
| A7 | under 50% of scores saturated | 0.0000 ✓ | 0.0000 ✓ |

Other gates (not required): the legitimate chat as a transcript 0.1406 ✓, the
complete scam conversation 0.9540 ✓, an English courier-key scam 0.9386 ✓.

"At acceptance" is the Colab result the verdict was based on: **not accepted**.
"Now" is the same model after two input-pipeline fixes (message-aligned
windows; the watermark filter). A3 passes now only because of those fixes, and
the verdict stands. A7 is not evidence of calibration — label smoothing all but
guarantees it.

### 4.8 Errors

All six errors are **missed scams**; there are no false alarms on either set.

| set | P(scam) | what the scam behaviour was |
|---|---|---|
| validation | 0.031 | 5 messages: renter asks twice to view; owner is "outstation", will meet later — no payment demanded yet |
| validation | 0.028 | 4 messages: renter asks to view; owner "outstation, can meet later" — no payment demanded yet |
| pairs (Malay) | 0.069 | owner "in Sabah, no keys"; deposit "today, or I give it to someone else"; deadline before midnight |
| pairs (Malay) | 0.047 | unit locked; booking fee *bank-in* tonight; deadline; pay a friend's account |
| pairs (Malay) | 0.180 | unit locked; booking fee tonight; friend's account; deadline |
| pairs (Malay) | 0.094 | owner "in Sabah, no keys"; deposit "today, or I give it to someone else" |

The two validation misses are short synthetic chats from the same template, in
which the only warning sign is an absent owner. Both are under 6 messages, so
the deployed service would not report them as low risk: it returns
`insufficient_context` (§4.4).

The Malay misses share vocabulary that never occurs in training — *berkunci*
(locked), *yuran tempahan* (booking fee), *bank-in*, *Sabah* — which points to
the model relying partly on familiar words rather than the tactic. Full cases:
`run1_evaluation.json → misclassified`.

### 4.9 Efficiency

CPU only (Intel, 12 logical cores, 8 threads), model loaded, one conversation at
a time: median **0.18 s** per validation conversation (mean 0.31 s); mean
**1.0 s** for the long real chats (two windows). Model file 1.1 GB; inference
needs about 1.1 GB of RAM.

---

## 5. Context: the model it replaced

The same tests on the first fine-tuned model (`xlm-roberta-scam-random`), from
`eval/results/confusion_matrices.json` and `gates_xlm-roberta-scam-random.json`:

| | previous model | run 1 |
|---|---|---|
| validation accuracy / macro-F1 | 0.9895 / 0.9883 | 0.9789 / 0.9768 |
| new-wording pairs: accuracy | 0.444 | **0.972** |
| new-wording pairs: pair accuracy | 0.069 | **0.944** |
| real legitimate chat (OCR, current) | 0.9997 ✗ | **0.3024 ✓** |
| legitimate chat + itemised prices | 0.9492 ✗ | **0.0273 ✓** |
| scam with scam lines removed | 0.9995 | 0.5313 |
| English-only probes | 9 / 10 | **10 / 10** |
| benign messages flagged | 2 / 8 | **0 / 8** |
| acceptance gates passed | 3 / 9 | **8 / 9** |

The previous model scored higher on validation and failed almost everything
else: on the new-wording pairs it was worse than chance (MCC −0.11). It had
learned the training data's shortcuts — prices and length — rather than the
scam behaviour. Validation accuracy alone could not show this.

---

## 6. Limitations and threats to validity

1. **No independent real test set.** The only real conversations are one scam
   and one legitimate chat, and both were used to diagnose earlier models.
   `data/test_real/` exists, sealed and guarded by tests, but is empty. No
   number here measures performance on unseen real conversations.
2. **Validation is optimistic.** It was used for early stopping and for fitting
   the temperature.
3. **The main test is synthetic.** The minimal pairs come from the same
   generator, scaffolding and tactics as the training pairs; only the wording of
   the scam behaviour is new. It tests reading a *known tactic in new words*,
   not recognising a new tactic.
4. **Mostly synthetic training data**, and only 8 real legitimate conversations
   in the whole corpus.
5. **One training run, one seed.** Run-to-run variation is unmeasured; a second
   run with changed data (run 2) scored much lower (pair accuracy 0.736).
6. **Not accepted by its own criteria** (§4.7): it fails the "scam lines
   removed" gate, and passes the real legitimate chat only after input fixes and
   by a narrow margin.
7. **Malay is the weakest language** (§4.2, §4.8).

---

## 7. Reproduction

| script (`nlp-service/eval/`) | produces (`eval/results/`) |
|---|---|
| `run1_evaluation.py` | `run1_evaluation.json` — §1–§4 |
| `confusion_matrices.py` | `confusion_matrices.json`, `.md` — §5 |
| `truncation_sweep.py` | `truncation_sweep.json` — §4.4 |
| `behaviour_checks.py` | `behaviour_checks.json` — §4.3 |
| `../training/score_gates.py` | `gates_xlm-roberta-scam-v3-run1.json` — §4.7 |
| Colab `train_colab_v3.ipynb` | `v3_run1_printout.txt` — §4.7 "at acceptance" |

Data: `data/processed/random/{train,val}.csv`,
`data/processed/augmented/minimal_pairs_test.csv`, `nlp-service/training/gates.json`.
The full development history is in `docs/MODEL_COMPARISON.md`.
