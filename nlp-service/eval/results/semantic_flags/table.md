| new-wording pairs, 72 each | layer 1 alone | + semantic, e5-base | + semantic, mesolitica 64M |
|---|---|---|---|
| scam twins caught | 32 | 47 | 40 |
| of the 40 layer 1 misses, caught (need 20) | — | 15 | 8 |
| legitimate twins flagged | 0 | 6 | 35 |
| real scam chat (development chat): flags | 8 red flags | 9 semantic | 7 semantic |
| real iBilik chat (current OCR): flags | 0 red flags | 0 semantic | 0 semantic |
| real iBilik chat (pre-fix OCR): flags | 0 red flags | 0 semantic | 0 semantic |
| real iBilik chat (hand transcript): flags | 0 red flags | 0 semantic | 1 semantic |
| CPU seconds per chat (median / mean) | — | 0.221 / 0.338 | 0.143 / 0.176 |

| baseline | run 1 (deployed) | e5-base + LR | mesolitica 64M + LR |
|---|---|---|---|
| validation accuracy | 0.9789 | 0.8421 | 0.8316 |
| validation macro-F1 | 0.9768 | 0.8037 | 0.793 |
| new-wording pairs: row accuracy | 0.9722 | 0.7639 | 0.6319 |
| new-wording pairs: pair accuracy | 0.9444 | 0.5278 | 0.2917 |

Chosen model (plan's rule): e5-base.
Checks: e5-base: a_catches_half_of_layer1_misses=False, b_no_extra_legit_twins=False, c_no_flag_on_real_ibilik=True; mesolitica 64M: a_catches_half_of_layer1_misses=False, b_no_extra_legit_twins=False, c_no_flag_on_real_ibilik=False
Outcome: **DROP**.
