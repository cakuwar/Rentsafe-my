# Datasets

The RentSafe MY labelled dataset (research contribution: Gap 3). Real
conversations and anything derived from them are git-ignored (personal data);
only the synthetic set, the price data and the folder structure are tracked.

```
data/
├── raw/            Real conversations (scam, legitimate) and baseline sources  [ignored]
├── synthetic/      RentSafe_MY_Synthetic_Dataset.csv: 450 synthetic conversations
├── processed/      random/{train,val}.csv, augmented/minimal_pairs_{train,test}.csv,
│                   price baseline builds                                       [ignored]
├── price/          Mudah KL/Selangor apartment listings (price baseline source)
├── eval/           price_form_cases.csv (labelled cases for the price check)
├── samples/        Real screenshots used in tests and diagnosis                [ignored]
└── test_real/      The blind test: 15 cases never used in training           [ignored]
```

## What the classifier was trained on

| | conversations | synthetic | real |
|---|---|---|---|
| Corpus (`processed/random`) | 474 | 450 (94.9%) | 24 (5.1%): 16 scam, 8 legitimate |
| Split | train 379, validation 95 | | |
| Minimal pairs, training | 844 (422 scam / 422 legitimate twins) | all | |
| Minimal pairs, test (new wording) | 144 (72 pairs) | all | |

Conversations are WhatsApp-style transcripts written `Renter: ... / Owner: ...`.
A minimal pair is a scam and a legitimate conversation that are identical
except for the scam behaviour, so price, length and style cannot decide the
label (`nlp-service/training/make_minimal_pairs.py`).

**The FYP1 plan was not met.** It aimed for a 50/50 real-to-synthetic training
set and 20 real scams held out for testing. Only 24 real conversations could
be collected, and all of them are in the training or validation split, so the
corpus is about 95% synthetic and has no held-out real test set
(`docs/MODEL_COMPARISON.md` §3, `docs/MODEL_EVALUATION.md` §6). The closest
thing is the blind test in `test_real/cases/`: 15 cases collected after
training (10 scam, 5 legitimate; 9 of the scams real, the other 6 cases
role-played), reported in `docs/MODEL_EVALUATION.md` §4.10.

## How the deployed model was built

1. `data/processed/random/{train,val}.csv`: the corpus split at random.
2. `nlp-service/training/make_minimal_pairs.py`: the minimal pairs.
3. `nlp-service/training/pack_for_colab.py`, then
   `nlp-service/train_colab_v3.ipynb` on a Colab T4: fine-tunes XLM-RoBERTa.
4. `nlp-service/eval/run1_evaluation.py`: the evaluation.

`scripts/build_dataset.py` and `nlp-service/scripts_train.py` are the FYP1
versions of steps 1 and 3, kept for the record; the deployed model does not
come from them.
