# Draft text for the dissertation

Plain, passive, British spelling. The numbers come from `RESULTS.md`; please reword in your own voice. Each item says where it would go.

---

## E1 → Section 4.6.3 (blind test), after the description of the 15 cases

> To check that the blind test did not reward memorisation, each case was compared with the 1,406 training items (the 474 corpus conversations and run 1's 932 minimal-pair rows). Three measures were used: character 3–5-gram TF-IDF cosine similarity, the share of the case's word 8-grams found in an item, and the longest run of shared consecutive words. The thresholds were fixed in advance at 0.80, 0.20 and 15 words. No case reached any of them. The highest values were a cosine of 0.215, a containment of 0.026 and a run of 11 words, and the longest runs were stock phrases such as an itemised price list and a tenant-details form. For comparison, two pairs of blind cases known to come from the same script shared runs of 17 and 18 words.

**Optional, for Section 4.9.3 (internal validity):** "Cases 2, 6 and 10 were treated as sharing a script, but case 2 shares no text with the other two; their link is the tactic rather than the wording."

## E2 → Section 4.6.1, after the paragraph on run 2 and the zero-shot model

> To check whether the improvement came from the transformer or from the training data, a TF-IDF and logistic regression baseline was trained on the same data, using word 1–2-grams and character 3–5-grams, balanced class weights and C chosen on the model-selection set. Trained on the 379 corpus conversations only, it reached a pair accuracy of 0.111 on the new-wording pairs, in the same range as the first XLM-R model (0.069) and ELECTRA (0.097). Trained on run 1's 1,223 rows, it reached a pair accuracy of 0.944, the same as run 1, and passed the same 8 of 9 acceptance gates. The gain on the new-wording pairs is therefore explained by the minimal-pair data rather than by the transformer. On the 15 blind-test cases, run 1 caught 10 of 10 scams and the linear model 8 of 10, each with one false alarm (ROC-AUC 0.94 and 0.88). The two scams it missed were an English tenancy takeover, a tactic absent from the training pairs, and a 153-message Malay chat in which the scam messages formed a small part of the whole text. With ten scams, the difference between the two models is not conclusive.

## E2 → Section 4.9.3, Internal validity (one clause)

> …and a linear TF-IDF model trained on the same data matched run 1 on the new-wording pairs, so these pairs measure the effect of the training data more than the choice of model.

## E3 → Section 4.5.3, after the paragraph on the 8.5% false-positive rate

> The 266 scraped portal listings were collected without first checking the sites' terms of use (Section 3.5.6), so the baseline was rebuilt without them as a check. The time factor of 1.20 was kept, because it is estimated from buildings that appear in both the scraped and the Kaggle data and cannot be recomputed without the scrape. In the rebuilt baseline, 12,324 of 13,764 legitimate whole-unit listings were scored in the leave-one-out test, and 1,036 (8.41%) received points, against 8.53% before. Six whole-unit strata were no longer eligible (307 instead of 313), the 14 eligible room strata were unchanged, and none of the five blind-test cases with a usable price form (cases 3, 4, 5, 12 and 14) received different points.

## E3 → Section 3.5.6, last sentence of the paragraph on the scraped listings

Current: "…and the baseline can be rebuilt without them."

Proposed: "…and the baseline can be rebuilt without them; doing so changes the false-positive rate from 8.53% to 8.41% (Section 4.5.3)."

## E3 → Section 5.5, Price bullet (one clause)

> …and the scraped portal listings were collected without first checking the sites' terms of use, although removing them changed the false-positive rate by only 0.1 percentage points; the 1.20 time factor, however, depends on them.

---

## E4 → Section 4.6.1, after the E2 paragraph

> GPT-4o-mini was also tested as a zero-shot classifier, with a fixed prompt, temperature 0 and anonymised input. Without any training data, it classified all 72 new-wording pairs correctly, which shows that the tactics in the pairs are recognisable from general knowledge, so the pair test checks whether a trained model has learnt them rather than serving as a hard benchmark. On the validation set it reached an accuracy of 0.947, below run 1's 0.979, with three false alarms. On the blind test it caught 9 of 10 scams with one false alarm. It missed case 10 while catching case 6, which used the same script word for word. The 254 calls cost US$0.013, but the median response time was 1.2 seconds and the 95th percentile 23 seconds, the conversation must be sent to an external service, and the scores took only seven distinct values.

## E2 + E4 → Section 4.6.1 or 4.9.3, one summary sentence

> Run 1, a TF-IDF baseline trained on the same data and a zero-shot GPT-4o-mini made 1, 3 and 2 errors respectively on the 15 blind cases, sharing only one error (case 9, made by run 1 and GPT-4o-mini). With ten scams and five role-played legitimate chats, the blind test cannot rank the three; the practical case for run 1 is that it runs locally in under a second and keeps the conversation on the user's device.

## E4 → Section 5.5 or 5.6 (optional)

> A large language model used as a zero-shot classifier was perfect on the new-wording pairs but less accurate than the trained models on the validation set, and its response time, reliance on an external service and unreproducible scores make it better suited to the explanation step, where it is already used, than to scoring.

## E5 → already added to the dissertation (v4, tracked changes F-1 to F-5)

`RentSafe_MY_Dissertation_v4.docx` holds the final wording.
- **Source of the numbers:** Test A comes from the rerun with the corrected Serper key, in which all 15 scores match Table 4.11. Test B comes from the first full run.
- **Where the wording is kept:** `~/dissertation_fixes/NEW_TEXT_FOR_REWRITE.md` (entries F-1 to F-5), so you can reword it in your own voice.

### Section 4.2, new last paragraph (F-2)

> Timing and load were measured on 10 November 2026 on a separate copy of the system running on the development laptop, with an empty cache. Each of the 15 blind cases was submitted once, with the same screenshots and form details as in the blind test, and all 15 scores and bands matched Table 4.11, including the complaint points, which depend on live search results. A case took a median of 7.6 s from upload to result (range 4.4 to 26.0 s); OCR took a median of 2.1 s and the classifier 0.26 s. The six cases without agent details took 4.4 to 6.6 s, most of it for the explanation, whereas the complaint search and its judge raised the median of the other nine to 15.3 s, and three of them exceeded the 20 s target (20.1, 22.1 and 26.0 s). In a load test, 10 simulated users submitted pasted conversations without agent details continuously for three minutes. All 368 requests succeeded, with a median of 4.5 s, a 95th percentile of 8.4 s and 120 analyses per minute; the processor was busy 89% of the time on average, and free memory stayed above 0.5 GB. Ten simultaneous screenshot requests took at most 11.4 s. When the 10 users shared one network address, the 101st request within 15 minutes was refused, as the rate limit is designed to do, so users behind a shared address would share one allowance. These figures come from one laptop and one run of each test, and the load test did not include the complaint search.

### Table 3.10, System tests (F-1)

> Graceful handling of failed signals was implemented and tested; on the development laptop, a blind case took 4.4 to 26.0 s (at most 6.6 s without the complaint search), and 10 simultaneous users were served without errors; three cases with the complaint search exceeded the 20 s target (Section 4.2)

### Section 4.5.5 (F-3), Section 5.5 (F-4), Section 5.6 (F-5)

See NEW_TEXT_FOR_REWRITE.md.
