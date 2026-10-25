# Held-out real conversations — SEALED

This folder is the honest test set. It is **empty on purpose** until real
conversations are put here, and nothing in it may ever be used for training.

## Why it exists

Every number currently reported for layer 2 — including a validation F1 of
1.0000 — is measured on data that is ~95% synthetic, generated from about 20
templates, with the model's checkpoint selected on that same validation set. All
24 real conversations the project holds are inside `data/processed/random/` and
`data/processed/grouped/`, so they are in training.

That means **no existing number predicts real-world performance.** This folder
is where that gets fixed.

## The rule

A conversation placed here must never have been used to train or select a model.
Concretely:

1. It must not appear in `data/processed/*/train.csv` or `val.csv`.
2. It must not be added to them later.
3. No training notebook or script may read this folder.
4. It is scored only after a model is finished, and the number is reported
   whatever it says.

If a conversation here turns out to overlap the training splits, it is not a
test case any more. `tests/test_held_out.py` fails the build if that happens.

## Format

Same columns as the processed splits, so the same loaders work:

```csv
text,label,origin,source_group
"Renter: ...\nOwner: ...",SCAM,real,R01
```

| column | meaning |
|---|---|
| `text` | the whole conversation, one message per line |
| `label` | `SCAM` or `LEGITIMATE` |
| `origin` | `real` — synthetic rows do not belong here |
| `source_group` | an id per source conversation, so variants of one chat cannot be split across a comparison |

Put files in as `test_real_<nn>.csv`, or one `test_real.csv`.

## What to collect first

Ranked by what the current evaluation cannot see:

1. **Legitimate conversations.** Only 8 exist in the whole project, and all 8 are
   in training. The model has almost no basis for recognising an honest landlord
   it has not already seen.
2. **English-only scams.** Training scams are nearly all code-switched Malay.
   Both candidate models scored *"I cannot do viewing, I'm overseas. Pay one
   month rent and I courier the key"* below 0.01 — a textbook scam, called safe.
3. **Scam tactics absent from the templates.** 14 of layer 1's 26 rules never
   fire on the synthetic corpus, including OTP/TAC requests, crypto payment and
   viewing fees. If those happen in reality, nothing here can measure them.
4. **Short conversations**, 1–5 messages, where the guard currently refuses to
   score. Whether that refusal is right is untested.

## How to score it

```
python eval/test_real.py
```

Refuses to run if the folder is empty, and writes
`eval/results/test_real.json`.
