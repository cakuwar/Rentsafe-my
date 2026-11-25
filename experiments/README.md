# experiments/

These are extra experiments for the dissertation (E1–E5). They are for the report only and change nothing in the system.

**Results:** `RESULTS.md`. **Draft wording for the dissertation:** `DRAFT_TEXT.md`.

| Path | What it is |
|---|---|
| `scripts/` | the experiment scripts (run with `nlp-service/.venv/Scripts/python.exe -I -B -X utf8 …`) |
| `prompts/` | the frozen E4 prompt and its SHA-256 |
| `results/` | metrics and tables only, with no chat text |
| `proof/` | pre-flight and post-flight snapshots: git state and hashes of the model and price-baseline files |

**Kept outside the repo, because it holds chat text or personal data:** `~/rentsafe_experiments_data/`. It contains:
- run 1's data copy
- the blind-test transcripts
- anonymised texts and raw API outputs
- overlap snippets
- the price working copies

**Before committing:** `experiments/` is not covered by `.gitignore`. It holds nothing private, but decide whether you want it in the repo.
