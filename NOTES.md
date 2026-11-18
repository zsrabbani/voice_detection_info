# Notes

## What I built, and what works

Implemented a conservative rule-based enrichment step in `app/enrich.py`. It extracts caller name, summary, sentiment, intent, vehicle make/model, license plate, email, and follow-up need without adding external runtime dependencies.

The extractor favors precision over fill rate: partial plates, third-party names, ambiguous vehicle words, and unsupported facts are left null and added to `unresolved_fields`.

Vehicle extraction uses a broad make alias list plus context checks for ambiguous makes such as `Mini`, `Smart`, `DS`, and `MG`. Models are extracted from the transcript text after a stated make, or from explicit vehicle-context phrases such as "es geht um unseren Golf"; it does not infer a make from a model-only mention.

`run_batch.py --write-db` upserts enriched leads through `app/db.py`; the existing `ON CONFLICT (call_id)` path keeps reruns idempotent.

I also updated the `psycopg[binary]` requirements pin from `3.2.1` to `3.2.13` because `3.2.1` does not provide a compatible binary wheel for the local Python 3.13 environment.

## Fill rates before / after

Before: `enrich_transcript()` was unimplemented.

After on the provided 13 transcripts:
- contact_name: 77%
- summary: 100%
- sentiment: 100%
- intent: 100%
- vehicle_make: 23%
- vehicle_model: 31%
- license_plate: 8%
- email: 8%
- follow_up_required: 100%

Verification: `.venv/bin/python -m pytest -q` passes 12 tests, including the expected self-check examples, no-name and third-party-name cases, incomplete plates, model sentence boundaries, ambiguous make false positives, and DB upsert serialization/conflict behavior. `.venv/bin/python run_batch.py` and `.venv/bin/python run_batch.py --write-db` both run successfully; rerunning the DB batch leaves 12 rows in `leads`, confirming the upsert path does not duplicate calls.

## Measuring accuracy in production

- Field-level accuracy on real traffic: build a labeled sample of anonymized production calls and score each field separately for exact match, acceptable normalized match, false positive, false negative, and correct abstention.
- Catching silent regressions after a prompt or model change: keep a fixed golden set with difficult cases such as no-name calls, third-party names, incomplete plates, multiple speakers, spelled emails, complaints, and unresolved appointment requests. Fail CI or alert when field precision or correct-abstention rate drops.

## Low-confidence extractions

Low confidence becomes `null`, not a best guess. The field is added to `unresolved_fields` so a human knows the CRM value is missing rather than silently wrong.

## Cost and latency at volume

This version is deterministic and local, so cost is zero per call and latency is negligible. If production transcripts need an LLM fallback, I would use it mainly for summary/intent/sentiment and keep factual fields validated by deterministic checks.

## Personal data (customer name)

Customer names are personal data. I would avoid logging raw names unnecessarily, restrict access to transcripts and enriched leads, and use anonymized/evidence-only evaluation sets wherever possible.

## What I deliberately skipped, given the time

I did not add an LLM integration, a full external vehicle database, fuzzy ASR correction, or live Postgres integration tests. Those are useful next steps on the real anonymized branch, but the first priority here is a dependable no-invention baseline with fast local tests.

## AI tools used, and where

Used Codex to inspect the scaffold, implement the extractor, add tests, and prepare these notes.
