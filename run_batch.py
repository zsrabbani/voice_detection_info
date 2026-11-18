"""Run enrichment over every transcript and report fill rates."""
import argparse
import glob
import json
import os

from app.enrich import enrich_transcript

FIELDS = ["contact_name", "summary", "sentiment", "intent",
          "vehicle_make", "vehicle_model", "license_plate", "email", "follow_up_required"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-db", action="store_true", help="upsert enriched leads into Postgres")
    args = parser.parse_args()
    if args.write_db:
        from app.db import upsert_lead

    paths = sorted(glob.glob(os.path.join("transcripts", "call_*.json")))
    filled = {f: 0 for f in FIELDS}
    results = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            t = json.load(fh)
        lead = enrich_transcript(t["call_id"], t["transcript"])
        results.append(lead)
        if args.write_db:
            upsert_lead(lead, t["transcript"])
        for f in FIELDS:
            if getattr(lead, f) is not None:
                filled[f] += 1
    n = len(paths) or 1
    print(f"{n} transcripts\n")
    for f in FIELDS:
        print(f"  {f:20s} fill rate {filled[f]/n:5.0%}")


if __name__ == "__main__":
    main()
