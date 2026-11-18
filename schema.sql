-- Simplified lead table. Today the enrichment columns are mostly NULL.
DROP TABLE IF EXISTS leads;

CREATE TABLE leads (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id            text UNIQUE NOT NULL,
    intent             text,
    contact_name       text,
    summary            text,
    sentiment          text,
    vehicle_make       text,
    vehicle_model      text,
    license_plate      text,
    email              text,
    follow_up_required boolean,
    unresolved_fields  jsonb NOT NULL DEFAULT '[]',
    transcript         text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT leads_sentiment_check CHECK (sentiment IN ('positive','neutral','negative'))
);
