import json
import os

from .models import EnrichedLead

DSN = os.environ.get("DATABASE_URL", "postgresql://cara8:cara8@localhost:5432/cara8")


def _connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn)


def upsert_lead(lead: EnrichedLead, transcript: str) -> None:
    """Write the enriched lead. Re-running the same call must not duplicate."""
    with _connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leads (call_id, intent, contact_name, summary, sentiment,
                                   vehicle_make, vehicle_model, license_plate, email,
                                   follow_up_required, unresolved_fields, transcript)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (call_id) DO UPDATE SET
                    intent = EXCLUDED.intent,
                    contact_name = EXCLUDED.contact_name,
                    summary = EXCLUDED.summary,
                    sentiment = EXCLUDED.sentiment,
                    vehicle_make = EXCLUDED.vehicle_make,
                    vehicle_model = EXCLUDED.vehicle_model,
                    license_plate = EXCLUDED.license_plate,
                    email = EXCLUDED.email,
                    follow_up_required = EXCLUDED.follow_up_required,
                    unresolved_fields = EXCLUDED.unresolved_fields,
                    transcript = EXCLUDED.transcript
                """,
                (lead.call_id, lead.intent, lead.contact_name, lead.summary, lead.sentiment,
                 lead.vehicle_make, lead.vehicle_model, lead.license_plate, lead.email,
                 lead.follow_up_required, json.dumps(lead.unresolved_fields), transcript),
            )
        conn.commit()
