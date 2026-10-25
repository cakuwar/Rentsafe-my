| | run 1 (deployed) | zero-shot mDeBERTa |
|---|---|---|
| threshold | 0.5 | -0.0519 (chosen on validation) |
| validation accuracy | 0.9789 | 0.6632 |
| new-wording pairs: row accuracy | 0.9722 | 0.5 |
| new-wording pairs: pair accuracy | 0.9444 | 0.0 |
| real scam chat (current OCR) (expect SCAM) | 0.956 SCAM ✓ | -0.0012 SCAM ✓ |
| real iBilik chat (current OCR) (expect LEGITIMATE) | 0.3024 LEGITIMATE ✓ | -0.0022 SCAM ✗ |
| real iBilik chat (pre-fix OCR) (expect LEGITIMATE) | 0.8836 SCAM ✗ | -0.0018 SCAM ✗ |
| real iBilik chat (hand transcript) (expect LEGITIMATE) | 0.1406 LEGITIMATE ✓ | -0.0016 SCAM ✗ |
| English courier scam (gate) (expect SCAM) | 0.9386 SCAM ✓ | 0.0016 SCAM ✓ |
| CPU seconds per chat (median / mean) | 0.27 / 0.3 | 4.06 / 5.96 |
| CPU seconds per real chat (mean) | 0.61 | 40.53 |

Pairs criterion (>= run 1 + 0.05): False. iBilik criterion (right on current AND pre-fix OCR): False. Outcome: **DROP - does not clearly beat run 1**.
