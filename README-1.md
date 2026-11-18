# CallSift

**Turns German phone-call transcripts into structured CRM leads, filling a field only when the transcript actually states it.**

CallSift reads a transcript of a customer calling a car dealership and extracts the caller's name, intent, sentiment, vehicle, license plate, email, whether a follow-up is needed, and a short summary. It returns a typed lead object and can upsert it into Postgres.

The design rule is **precision over fill rate**. A wrong customer name in a dealer's CRM does more damage than an empty field, so when the transcript doesn't clearly state something, CallSift leaves it `null` and lists it in `unresolved_fields`. That way a service advisor can tell "missing" apart from "known".

---

## Example

**Input** (`transcripts/call_001.json`)

```text
[Anrufer] Guten Tag, Schröder mein Name. Ich habe einen VW Passat, Kennzeichen M-AB 4721.
[Agent]   Guten Tag Frau Schröder, was kann ich für Sie tun?
[Anrufer] Die Bremsen quietschen seit einer Woche und die Inspektion ist auch fällig.
[Agent]   Verstehe. Nächste Woche Dienstag um 9 Uhr hätte ich einen Termin frei.
[Anrufer] Ja, das passt gut, danke.
[Agent]   Sehr gern, ich habe den Termin eingetragen.
```

**Output**

```json
{
  "call_id": "call_001",
  "contact_name": "Schröder",
  "summary": "Die anrufende Person möchte einen Service- oder Werkstatttermin für einen VW Passat klären. Das Kennzeichen lautet M-AB 4721.",
  "sentiment": "neutral",
  "intent": "service",
  "vehicle_make": "VW",
  "vehicle_model": "Passat",
  "license_plate": "M-AB 4721",
  "email": null,
  "follow_up_required": false,
  "unresolved_fields": ["email"]
}
```

## How it handles the tricky cases

The sample transcripts include cases where guessing would be easy and wrong. CallSift handles them like this:

| Situation | Example | Behaviour |
|---|---|---|
| Caller never gives a name | *"bis wann Sie heute geöffnet haben?"* | `contact_name = null` and marked unresolved |
| A third party is named | *"verbinden Sie mich mit Herrn Bauer"* … *"Frau Petersen"* | Returns **Petersen** (the caller), never Bauer |
| Plate is started but not finished | *"Das ist S-K… ähm, ich habe den Schein nicht zur Hand"* | `license_plate = null` |
| Email is spelled out | *"m-a-r-k-u-s punkt klein at example punkt com"* | Normalised to `markus.klein@example.com` |
| Model mentioned without make | *"es geht um unseren Golf"* | `vehicle_model = "Golf"`, make **not** inferred |
| Make name used as an ordinary word | *"smart gelöst"*, *"ein mini Problem"*, *"10 mg"* | No vehicle extracted |
| Name appears in an answer to the agent | Agent: *"auf welchen Namen?"* → *"Hoffmann."* | Returns **Hoffmann** |
| Several speakers (`[Anrufer 2]`) | Spouse speaking in the background | Name is taken only from the primary caller's turns |

## How it works

CallSift is deterministic and rule-based (regex plus keyword rules). It has no LLM or network calls and no dependencies beyond Pydantic.

```
transcript ──► parse speaker turns ──► per-field extractors ──► EnrichedLead (Pydantic)
                 [Anrufer] / [Agent]     name · vehicle · plate          │
                                         email · intent · sentiment      ├──► unresolved_fields
                                         follow-up · summary             └──► Postgres upsert (optional)
```

| Field | Approach |
|---|---|
| `contact_name` | Self-introduction patterns in the caller's turns only (*"mein Name ist…"*, *"… hier"*, *"hier spricht…"*) plus answers to *"wer anruft?"* / *"welchen Namen?"*. Names that appear after *mit Herrn/Frau…* or *erreiche Herrn/Frau…* are blocked as third parties. |
| `vehicle_make` / `vehicle_model` | Alias table of about 90 makes (e.g. `vw → VW`, `range rover → Land Rover`). Ambiguous makes (Mini, Smart, DS, MG) also need nearby vehicle context. The model is read from the words after the make, or from phrases such as *"es geht um unseren …"*. |
| `license_plate` | German plate pattern (`M-AB 4721`). It must be complete, so partial plates are ignored. |
| `email` | Written addresses, plus spoken ones (*punkt*, *at* / *ät*, letter-by-letter spelling). |
| `intent` | Ordered keyword rules: `other` → `complaint` → `transfer_request` → `callback_request` → `sales` → `information` → `appointment` → `service`. |
| `sentiment` | Negative and positive keyword lists. Defaults to `neutral`. |
| `follow_up_required` | Callback or confirmation promises, open appointment requests that weren't booked during the call, and requests to send something by email. |
| `summary` | A German template sentence for each intent, filled in with the extracted vehicle, plate or email. |

## Project structure

```
.
├── app/
│   ├── models.py        # EnrichedLead output contract (Pydantic)
│   ├── enrich.py        # enrich_transcript(): all extraction logic
│   └── db.py            # idempotent Postgres upsert (ON CONFLICT (call_id))
├── tests/
│   └── test_contract.py # 12 tests: ground truth, no-invention cases, DB upsert
├── transcripts/         # 13 sample transcripts + expected_selfcheck.json
├── run_batch.py         # runs every transcript and prints per-field fill rates
├── schema.sql           # leads table
├── docker-compose.yml   # local Postgres 16
├── requirements.txt
└── NOTES.md             # design notes: evaluation, regressions, PII, trade-offs
```

## Quick start

**Requirements:** Python 3.11+ (developed on 3.13). Docker is only needed for the database step.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                # run the tests
python run_batch.py      # enrich all sample transcripts and print fill rates
```

**Use it in code**

```python
from app.enrich import enrich_transcript

lead = enrich_transcript("call_42", "[Anrufer] Guten Tag, mein Name ist Weber. ...")
print(lead.model_dump_json(indent=2))
```

**Write leads to Postgres**

```bash
docker compose up -d
cat schema.sql | docker compose exec -T db psql -U cara8 -d cara8
export DATABASE_URL=postgresql://cara8:cara8@localhost:5432/cara8

python run_batch.py --write-db   # rerunning updates rows in place; it never duplicates them
```

## Results

Fill rates from `python run_batch.py` on the 13 bundled transcripts. Before this work, `enrich_transcript()` was a stub and every field was empty.

| Field | Fill rate |
|---|---|
| summary, sentiment, intent, follow_up_required | 100% |
| contact_name | 77% |
| vehicle_model | 31% |
| vehicle_make | 23% |
| license_plate | 8% |
| email | 8% |

Most of the lower numbers are correct abstentions: many of these calls don't mention a vehicle, plate or email. The test suite (12 tests, all passing) checks the ground-truth examples and each no-invention case listed above.

## Limitations

- **Tuned on a small sample.** The rules were built against 13 clean transcripts. Real call audio brings interruptions, dialect and ASR errors, so expect lower recall there. The no-invention behaviour should hold up better, because the rules fail toward `null`.
- **Summaries are templates.** They don't paraphrase the specific call.
- **Intent and sentiment use keywords.** Sarcasm, mixed feelings and unusual phrasing won't be caught.
- **No per-field confidence scores.** A field is either filled or unresolved.

## Roadmap

- Labelled evaluation set scored per field (precision, recall, correct-abstention rate) and run in CI to catch regressions.
- Optional LLM pass for summary, intent and sentiment. Factual fields (name, plate, email) would still go through the deterministic validators.
- Fuzzy matching for ASR errors in makes and models, plus a proper vehicle-model database.
- Live Postgres integration tests.

See [`NOTES.md`](NOTES.md) for more on evaluation, regression detection, cost and latency, and handling customer names as personal data.
