### XLM-R original

**validation (random/val)** (n=95)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 62 (TP) | 1 (FN) |
| actual LEGIT | 0 (FP) | 32 (TN) |

accuracy 0.9895 · precision 1.0 · recall 0.9841 · specificity 1.0 · F1 0.992 · macro-F1 0.9883 · MCC 0.9769

**new-wording minimal pairs (test, full)** (n=144)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 36 (TP) | 36 (FN) |
| actual LEGIT | 44 (FP) | 28 (TN) |

accuracy 0.4444 · precision 0.45 · recall 0.5 · specificity 0.3889 · F1 0.4737 · macro-F1 0.4427 · MCC -0.1118 · pair accuracy 0.0694

**English-only probes** (n=10)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 4 (TP) | 1 (FN) |
| actual LEGIT | 0 (FP) | 5 (TN) |

accuracy 0.9 · precision 1.0 · recall 0.8 · specificity 1.0 · F1 0.8889 · macro-F1 0.899 · MCC 0.8165

**benign short messages** (n=8)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 0 (TP) | 0 (FN) |
| actual LEGIT | 2 (FP) | 6 (TN) |

accuracy 0.75 · precision 0.0 · recall 0.0 · specificity 0.75 · F1 0.0 · macro-F1 0.4286 · MCC 0.0

### ELECTRA v2

**validation (random/val)** (n=95)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 63 (TP) | 0 (FN) |
| actual LEGIT | 0 (FP) | 32 (TN) |

accuracy 1.0 · precision 1.0 · recall 1.0 · specificity 1.0 · F1 1.0 · macro-F1 1.0 · MCC 1.0

**new-wording minimal pairs (test, full)** (n=144)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 41 (TP) | 31 (FN) |
| actual LEGIT | 34 (FP) | 38 (TN) |

accuracy 0.5486 · precision 0.5467 · recall 0.5694 · specificity 0.5278 · F1 0.5578 · macro-F1 0.5484 · MCC 0.0973 · pair accuracy 0.0972

**English-only probes** (n=10)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 5 (TP) | 0 (FN) |
| actual LEGIT | 3 (FP) | 2 (TN) |

accuracy 0.7 · precision 0.625 · recall 1.0 · specificity 0.4 · F1 0.7692 · macro-F1 0.6703 · MCC 0.5

**benign short messages** (n=8)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 0 (TP) | 0 (FN) |
| actual LEGIT | 1 (FP) | 7 (TN) |

accuracy 0.875 · precision 0.0 · recall 0.0 · specificity 0.875 · F1 0.0 · macro-F1 0.4667 · MCC 0.0

### XLM-R run 1 (deployed)

**validation (random/val)** (n=95)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 61 (TP) | 2 (FN) |
| actual LEGIT | 0 (FP) | 32 (TN) |

accuracy 0.9789 · precision 1.0 · recall 0.9683 · specificity 1.0 · F1 0.9839 · macro-F1 0.9768 · MCC 0.9546

**new-wording minimal pairs (test, full)** (n=144)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 68 (TP) | 4 (FN) |
| actual LEGIT | 0 (FP) | 72 (TN) |

accuracy 0.9722 · precision 1.0 · recall 0.9444 · specificity 1.0 · F1 0.9714 · macro-F1 0.9722 · MCC 0.9459 · pair accuracy 0.9444

**English-only probes** (n=10)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 5 (TP) | 0 (FN) |
| actual LEGIT | 0 (FP) | 5 (TN) |

accuracy 1.0 · precision 1.0 · recall 1.0 · specificity 1.0 · F1 1.0 · macro-F1 1.0 · MCC 1.0

**benign short messages** (n=8)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 0 (TP) | 0 (FN) |
| actual LEGIT | 0 (FP) | 8 (TN) |

accuracy 1.0 · precision 0.0 · recall 0.0 · specificity 1.0 · F1 0.0 · macro-F1 0.5 · MCC 0.0

### XLM-R run 2 (not kept)

**new-wording minimal pairs (test, full)** (n=144)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 53 (TP) | 19 (FN) |
| actual LEGIT | 0 (FP) | 72 (TN) |

accuracy 0.8681 · precision 1.0 · recall 0.7361 · specificity 1.0 · F1 0.848 · macro-F1 0.8657 · MCC 0.7632 · pair accuracy 0.7361

**validation (random/val)** (n=95)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 63 (TP) | 0 (FN) |
| actual LEGIT | 0 (FP) | 32 (TN) |

accuracy 1.0 · precision 1.0 · recall 1.0 · specificity 1.0 · F1 1.0 · macro-F1 1.0 · MCC 1.0 · _from the Colab printout: accuracy 1.0000 on these 95 rows_

### zero-shot mDeBERTa (rejected)

**validation (random/val)** (n=95)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 63 (TP) | 0 (FN) |
| actual LEGIT | 32 (FP) | 0 (TN) |

accuracy 0.6632 · precision 0.6632 · recall 1.0 · specificity 0.0 · F1 0.7975 · macro-F1 0.3987 · MCC 0.0

**new-wording minimal pairs (test, full)** (n=144)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 72 (TP) | 0 (FN) |
| actual LEGIT | 72 (FP) | 0 (TN) |

accuracy 0.5 · precision 0.5 · recall 1.0 · specificity 0.0 · F1 0.6667 · macro-F1 0.3333 · MCC 0.0 · pair accuracy 0.0

### Layer 1 (regex) as a classifier — any red flag = SCAM

**train (random/train)** (n=379)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 228 (TP) | 25 (FN) |
| actual LEGIT | 13 (FP) | 113 (TN) |

accuracy 0.8997 · precision 0.9461 · recall 0.9012 · specificity 0.8968 · F1 0.9231 · macro-F1 0.8896 · MCC 0.7813

**validation (random/val)** (n=95)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 55 (TP) | 8 (FN) |
| actual LEGIT | 4 (FP) | 28 (TN) |

accuracy 0.8737 · precision 0.9322 · recall 0.873 · specificity 0.875 · F1 0.9016 · macro-F1 0.8626 · MCC 0.7288

**new-wording minimal pairs (test, full)** (n=144)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 32 (TP) | 40 (FN) |
| actual LEGIT | 0 (FP) | 72 (TN) |

accuracy 0.7222 · precision 1.0 · recall 0.4444 · specificity 1.0 · F1 0.6154 · macro-F1 0.699 · MCC 0.5345 · pair accuracy 0.4444

**English-only probes** (n=10)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 5 (TP) | 0 (FN) |
| actual LEGIT | 0 (FP) | 5 (TN) |

accuracy 1.0 · precision 1.0 · recall 1.0 · specificity 1.0 · F1 1.0 · macro-F1 1.0 · MCC 1.0

**benign short messages** (n=8)

| | predicted SCAM | predicted LEGIT |
|---|---|---|
| actual SCAM | 0 (TP) | 0 (FN) |
| actual LEGIT | 0 (FP) | 8 (TN) |

accuracy 1.0 · precision 0.0 · recall 0.0 · specificity 1.0 · F1 0.0 · macro-F1 0.5 · MCC 0.0

### Real conversations

| chat | expect | XLM-R original | ELECTRA v2 | XLM-R run 1 (deployed) |
|---|---|---|---|---|
| real scam chat, OCR | SCAM | 0.9998 ✓ | 0.9432 ✓ | 0.956 ✓ |
| real iBilik legit chat, OCR (current) | LEGITIMATE | 0.9997 ✗ | 0.99 ✗ | 0.3024 ✓ |
| real iBilik legit chat, OCR (before watermark fix) | LEGITIMATE | 0.9997 ✗ | 0.9865 ✗ | 0.8836 ✗ |
| real iBilik legit chat, hand transcript | LEGITIMATE | 0.9996 ✗ | 0.9953 ✗ | 0.1406 ✓ |
| English courier scam (author-written) | SCAM | 0.0282 ✗ | 0.9962 ✓ | 0.9386 ✓ |
