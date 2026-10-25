# Datasets

The RentSafe MY labelled dataset (research contribution — Gap 3). **Raw scraped
content is git-ignored**; only structure and the schema of processed files are
tracked.

```
data/
├── raw/
│   ├── scam/         Real scam examples (Lowyat.net, Facebook victim groups) — target ~60
│   └── legitimate/   Real legit listings (PropertyGuru, iProperty, Mudah.my) — target 100–150
├── synthetic/        Reviewed synthetic Manglish examples (≤ 50% of final train set)
└── processed/        Cleaned + split CSVs used for training/eval
```

## Labels & splits

Each processed CSV has columns:

| column | values |
| --- | --- |
| `text`   | the listing / message text |
| `label`  | `SCAM` or `LEGITIMATE` |
| `origin` | `real` or `synthetic` |
| `source` | provenance note |
| `split`  | `train`, `val`, or `test` |

- Keep **20 real scam examples** in a held-out `test` split — never train on them.
- Target ratio: **50/50 real-to-synthetic** in the train set (Risk Register mitigation).

## Building the splits

Run `scripts/build_dataset.py` to merge `raw/` + `synthetic/` into
`processed/{train,val,test}.csv`, then `nlp-service/scripts_train.py` to
fine-tune.
