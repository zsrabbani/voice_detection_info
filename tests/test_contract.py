import json
import os

from app.enrich import enrich_transcript
from app.models import EnrichedLead

HERE = os.path.dirname(__file__)
TRANS = os.path.join(HERE, "..", "transcripts")


def load(call_id):
    with open(os.path.join(TRANS, f"{call_id}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_returns_contract_shape():
    t = load("call_001")
    lead = enrich_transcript(t["call_id"], t["transcript"])
    assert isinstance(lead, EnrichedLead)


def test_does_not_invent_a_name_when_none_is_given():
    # call_002: caller never gives a name. Inventing one is the failure we care about most.
    t = load("call_002")
    lead = enrich_transcript(t["call_id"], t["transcript"])
    assert lead.contact_name is None
    assert "contact_name" in lead.unresolved_fields


def test_expected_selfcheck_examples_match_ground_truth():
    with open(os.path.join(TRANS, "expected_selfcheck.json"), encoding="utf-8") as fh:
        expected = json.load(fh)

    for call_id, fields in expected.items():
        t = load(call_id)
        lead = enrich_transcript(t["call_id"], t["transcript"]).model_dump()
        for field, value in fields.items():
            assert lead[field] == value


def test_uses_caller_name_not_third_party_name():
    # call_005: Herr Bauer is the requested employee, not the caller.
    t = load("call_005")
    lead = enrich_transcript(t["call_id"], t["transcript"])
    assert lead.contact_name == "Petersen"


def test_does_not_guess_incomplete_license_plate():
    # call_008: the caller starts the plate and then says they do not have it.
    t = load("call_008")
    lead = enrich_transcript(t["call_id"], t["transcript"])
    assert lead.license_plate is None
    assert "license_plate" in lead.unresolved_fields


def test_extracts_non_fixture_vehicle_model_after_make():
    lead = enrich_transcript("synthetic", "[Anrufer] Ich fahre einen BMW 320d Touring.")
    assert lead.vehicle_make == "BMW"
    assert lead.vehicle_model == "320d Touring"


def test_model_only_vehicle_does_not_infer_make():
    lead = enrich_transcript("synthetic", "[Anrufer] Es geht um unseren Golf.")
    assert lead.vehicle_make is None
    assert lead.vehicle_model == "Golf"


def test_model_only_vehicle_stops_at_sentence_boundary():
    t = load("call_009")
    lead = enrich_transcript(t["call_id"], t["transcript"])
    assert lead.vehicle_make is None
    assert lead.vehicle_model == "Golf"


def test_ambiguous_make_words_need_vehicle_context():
    examples = [
        "[Anrufer] Das war smart gelöst, danke.",
        "[Anrufer] Ich habe ein mini Problem mit der Rechnung.",
        "[Anrufer] Die Dosis waren 10 mg.",
    ]
    for index, transcript in enumerate(examples):
        lead = enrich_transcript(f"synthetic_{index}", transcript)
        assert lead.vehicle_make is None
        assert lead.vehicle_model is None


def test_does_not_treat_ambiguous_number_as_vehicle_model():
    lead = enrich_transcript("synthetic", "[Anrufer] Ich komme morgen um 3 Uhr.")
    assert lead.vehicle_make is None
    assert lead.vehicle_model is None


def test_angry_readiness_call_is_complaint_without_vehicle_details():
    t = load("call_013")
    lead = enrich_transcript(t["call_id"], t["transcript"])

    assert lead.contact_name is None
    assert lead.intent == "complaint"
    assert lead.sentiment == "negative"
    assert lead.follow_up_required is True
    assert lead.vehicle_make is None
    assert lead.vehicle_model is None
    assert "contact_name" in lead.unresolved_fields
    assert "vehicle_model" in lead.unresolved_fields


def test_upsert_lead_uses_conflict_update_and_serializes_unresolved(monkeypatch):
    from app import db

    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return FakeCursor()

        def commit(self):
            captured["committed"] = True

    def fake_connect(dsn):
        captured["dsn"] = dsn
        return FakeConnection()

    lead = EnrichedLead(call_id="call_test", unresolved_fields=["contact_name", "email"])
    monkeypatch.setattr(db, "_connect", fake_connect)

    db.upsert_lead(lead, "raw transcript")

    assert "ON CONFLICT (call_id) DO UPDATE" in captured["sql"]
    assert captured["params"][0] == "call_test"
    assert json.loads(captured["params"][10]) == ["contact_name", "email"]
    assert captured["params"][11] == "raw transcript"
    assert captured["committed"] is True
