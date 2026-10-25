# Real scam screenshots — reference samples, NOT test data

Four pages of one real WhatsApp rental scam, used to develop and check the
message counter (`app/turns.py`) and layer 1's rules.

**These are not held-out data and must never be treated as such.** Their text was
already read while writing layer 1's patterns, so scoring a model on them proves
nothing. `data/test_real/` is the sealed set; this is not it. Do not train on
these either.

Files are in **chronological order**, which is not the order they were exported
in. The original `scam_p1..p4` were `17:35 → 18:13` in the order p3, p2, p4, p1;
they have been renamed so that page order matches conversation order.

| file | covers |
|---|---|
| `scam_p1.jpg` | 17:35 – 17:49 |
| `scam_p2.jpg` | 17:49 – 18:03 |
| `scam_p3.jpg` | 18:03 – 18:08 |
| `scam_p4.jpg` | 18:08 – 18:13 |

Hand count: **26 bubbles** = 25 text messages + 1 image (a QR code). Per page
after de-duplicating quoted replies and page-seam repeats: 9, 11, 3, 3.

Counting rules used: one bubble is one message; a quoted reply is one message and
the quoted text inside it does not count again; messages repeated at a page seam
count once; a multi-line bubble is one message.

The OCR text extracted from these (redacted) lives in
`nlp-service/tests/fixtures/` so tests can use it without the images.

## Also here

`legit_p1..p8.jpg` — the real legitimate iBilik conversation from the blind test
(`docs/BLIND_TEST_DIAGNOSIS.md`). Hand count 34 messages. It was used to
diagnose the model's failure, so it is not held-out data either.

## Privacy — `redact.txt`

Everything in this folder except this README is gitignored: the screenshots
carry real names, a phone number and an address. `redact.txt` lists the names
and addresses to strip from anything derived from them, one per line; a line may
start with a tag such as `[address]` to use that as the replacement (default
`[name]`). Phone, IC and account numbers are caught by pattern and need no entry.

`nlp-service/training/redaction.py` reads the list, so no name is ever written
into source code in order to remove it. `training/build_gates.py` and the
segmenter evaluations redact before writing, and refuse to write if anything
survives; `tests/test_redaction.py` fails if a listed name appears in any
tracked file. Add a name here the moment a new screenshot introduces one.
