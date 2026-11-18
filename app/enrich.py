"""Conservative German transcript enrichment.

This module favors precision over fill rate: facts are written only when the
transcript clearly supports them; otherwise fields stay null and unresolved.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .models import EnrichedLead


LEAD_FIELDS = tuple(
    name for name in EnrichedLead.model_fields if name not in {"call_id", "unresolved_fields"}
)

TURN_RE = re.compile(r"\[(?P<speaker>[^\]]+)\]\s*(?P<text>.*)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PLATE_RE = re.compile(r"\b([A-ZÄÖÜ]{1,3})\s*-\s*([A-ZÄÖÜ]{1,2})\s+(\d{1,4})\b")
NAME_TOKEN_RE = re.compile(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+$")

NAME_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in [
        r"\bmein name ist\s+([^.,;!?]+)",
        r"\b([^.,;!?]+?)\s+mein name\b",
        r"\bhier ist\s+([^.,;!?]+)",
        r"\bhier spricht\s+([^.,;!?]+)",
        r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+)?)\s+hier\b",
        r"^(?:ja\s+)?(?:guten\s+tag|hallo|guten\s+morgen),\s+([^.,;!?]+)",
    ]
)
THIRD_PARTY_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in [
        r"\bmit\s+(?:herrn|herr|frau)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+)",
        r"\berreiche\s+(?:herrn|herr|frau)\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+)",
    ]
)

STOPWORDS_IN_NAMES = set("bitte danke guten hallo herrn ich kann koennen können meine meinen mich morgen sie tag wollte".split())


def _alias_regex(alias: str) -> str:
    return r"\b" + re.escape(alias).replace(r"\ ", r"[\s-]+").replace(r"\-", r"[\s-]+") + r"\b"


MAKE_ALIAS_DATA = """
Abarth:abarth; Acura:acura; Aiways:aiways; Alfa Romeo:alfa romeo|alfa; Alpine:alpine; Aston Martin:aston martin; Audi:audi;
BAIC:baic; Bentley:bentley; BMW:bmw; BYD:byd; Cadillac:cadillac; Changan:changan; Chery:chery; Chevrolet:chevrolet|chevy;
Chrysler:chrysler; Citroen:citroen|citroën; Cupra:cupra; Dacia:dacia; Daewoo:daewoo; Daihatsu:daihatsu; Dodge:dodge;
Dongfeng:dongfeng; DS:ds; Ferrari:ferrari; Fiat:fiat; Fisker:fisker; Ford:ford; Genesis:genesis; Geely:geely; GMC:gmc;
Great Wall:great wall; Haval:haval; Honda:honda; Hongqi:hongqi; Hyundai:hyundai; Infiniti:infiniti; Isuzu:isuzu; Jaguar:jaguar;
Jeep:jeep; KGM:kgm|ssangyong|ssang yong; Kia:kia; Lada:lada; Lamborghini:lamborghini; Lancia:lancia; Land Rover:land rover|range rover;
Leapmotor:leapmotor|leap motor; Lexus:lexus; Lincoln:lincoln; Lotus:lotus; Lucid:lucid; Maserati:maserati; Mazda:mazda;
McLaren:mclaren; Mercedes-Benz:mercedes benz|mercedes-benz|mercedes; MG:mg; Mini:mini; Mitsubishi:mitsubishi; NIO:nio;
Nissan:nissan; Opel:opel; Peugeot:peugeot; Polestar:polestar; Porsche:porsche; Proton:proton; Renault:renault; Rivian:rivian;
Rolls-Royce:rolls royce|rolls-royce; Rover:rover; Saab:saab; Seat:seat; Seres:seres; Skoda:skoda|škoda; Smart:smart;
Subaru:subaru; Suzuki:suzuki; Tata:tata; Tesla:tesla; Toyota:toyota; Vauxhall:vauxhall; VinFast:vinfast|vin fast;
VW:volkswagen|vw; Volvo:volvo; XPeng:xpeng|x peng; Zeekr:zeekr
"""
MAKE_ALIASES = {
    alias.strip(): make.strip()
    for row in MAKE_ALIAS_DATA.replace("\n", " ").split(";")
    if row.strip()
    for make, aliases in [row.split(":", 1)]
    for alias in aliases.split("|")
}
MAKE_MATCHERS = tuple(
    (re.compile(_alias_regex(alias), re.I), make)
    for alias, make in sorted(MAKE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True)
)
AMBIGUOUS_MAKES = {"DS", "MG", "Mini", "Smart"}

MODEL_STOPWORDS = set(
    "aber aus bei braucht das dem den der die ein eine einen einer für in ist kennzeichen "
    "macht mein meine meinem mit muss problem service steht und von".split()
)
OWNER = r"(?:mein(?:e[rmn]?|en|em)?|unser(?:e[rmn]?|en|em)?)"
MODEL = r"(?P<model>[A-ZÄÖÜ0-9][A-Za-zÄÖÜäöüß0-9.+-]*(?:\s+[A-ZÄÖÜ0-9][A-Za-zÄÖÜäöüß0-9.+-]*){0,2})"
MODEL_CONTEXT_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in [
        rf"\b(?:es\s+geht\s+um|geht\s+um|wegen|für)\s+(?:mein(?:en|em)?|unser(?:en|em)?|den|die|das)\s+{MODEL}",
        rf"\b{OWNER}\s+(?:auto|wagen|fahrzeug|pkw)\s+(?:ist|heißt|heisst)?\s*(?:ein(?:e[rmn]?)?)?\s*{MODEL}",
        rf"\b{OWNER}\s+{MODEL}\s+(?:macht|braucht|steht|springt|klappert|zieht|ruckelt)",
    ]
)

NEGATIVE_WORDS = ("frechheit", "ärger", "beschwer", "niemand gemeldet", "niemand kümmert sich")
POSITIVE_WORDS = ("perfekt", "sehr gut", "super")
FOLLOW_UP_WORDS = (
    "zurückrufen",
    "rückruf",
    "ich melde mich",
    "melde mich zurück",
    "bestätigung",
    "gebe das weiter",
)
BOOKING_WORDS = ("bräuchte einen termin", "wann passt", "diese woche noch")
BOOKING_DONE_WORDS = ("eingetragen", "der steht", "nächsten donnerstag")

INTENT_RULES = (
    ("other", ("verwählt",)),
    ("complaint", NEGATIVE_WORDS),
    ("transfer_request", ("verbinden",)),
    ("callback_request", ("zurückrufen", "rückruf")),
    ("sales", ("anzeige", "probefahren", "probe fahren", "interessiere mich")),
    ("information", ("geöffnet", "öffnungszeit", "bis wann")),
    ("appointment", ("termin bestätigen",)),
    (
        "service",
        (
            "inspektion",
            "brems",
            "klimaanlage",
            "kühlt nicht",
            "ölwechsel",
            "reifenwechsel",
            "werkstatt",
            "kostenvoranschlag",
        ),
    ),
)


def enrich_transcript(call_id: str, transcript: str) -> EnrichedLead:
    turns = _parse_turns(transcript)
    text = " ".join(line for _, line in turns)
    lower = text.lower()
    vehicle_make, vehicle_model = _vehicle(text)
    email = _email(turns)
    license_plate = _plate(text)
    intent = _intent(lower)

    values = {
        "contact_name": _contact_name(turns),
        "summary": _summary(lower, intent, vehicle_make, vehicle_model, license_plate, email),
        "sentiment": _sentiment(lower),
        "intent": intent,
        "vehicle_make": vehicle_make,
        "vehicle_model": vehicle_model,
        "license_plate": license_plate,
        "email": email,
        "follow_up_required": _follow_up_required(lower, intent),
    }
    values["unresolved_fields"] = [field for field in LEAD_FIELDS if values[field] is None]
    return EnrichedLead(call_id=call_id, **values)


def _parse_turns(transcript: str) -> list[tuple[str, str]]:
    turns = [
        (match["speaker"].strip(), match["text"].strip())
        for raw in transcript.splitlines()
        if (match := TURN_RE.match(raw.strip()))
    ]
    return turns or [("", transcript)]


def _caller(speaker: str) -> bool:
    return speaker.lower() == "anrufer"


def _has(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _contact_name(turns: list[tuple[str, str]]) -> str | None:
    blocked = {
        match.group(1).lower()
        for speaker, text in turns
        if _caller(speaker)
        for pattern in THIRD_PARTY_PATTERNS
        for match in pattern.finditer(text)
    }

    for index, (speaker, text) in enumerate(turns):
        if not _caller(speaker):
            continue
        previous = turns[index - 1][1].lower() if index else ""
        candidates = [match.group(1) for pattern in NAME_PATTERNS for match in pattern.finditer(text)]
        if "wer anruft" in previous or "welchen namen" in previous:
            candidates.append(text)

        for candidate in candidates:
            name = _clean_name(candidate)
            if name and name.lower() not in blocked:
                return name
    return None


def _clean_name(candidate: str) -> str | None:
    name = re.sub(r"^(?:ja|guten tag|hallo|guten morgen)\b,?\s*", "", candidate, flags=re.I)
    name = re.sub(r"^(?:herr|herrn|frau)\s+", "", name.strip(), flags=re.I)
    words = re.sub(r"\s+", " ", name.strip(" .,!?:;")).split()

    if not 1 <= len(words) <= 3:
        return None
    if any(word.lower() in STOPWORDS_IN_NAMES for word in words):
        return None
    if not all(NAME_TOKEN_RE.match(word) for word in words):
        return None
    return " ".join(words)


def _email(turns: list[tuple[str, str]]) -> str | None:
    text = " ".join(line for _, line in turns)
    if match := EMAIL_RE.search(text):
        return match.group(0).lower()

    for _, line in turns:
        spoken = line.lower()
        if not _has(spoken, (" at ", " ät ", "punkt")):
            continue
        spoken = re.sub(r"\b(?:punkt|dot)\b", ".", spoken)
        spoken = re.sub(r"\b(?:at|ät)\b", "@", spoken).replace("-", "")
        spoken = re.sub(r"\s*([.@])\s*", r"\1", spoken)
        if match := re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", spoken):
            return match.group(0).strip(".").lower()
    return None


def _plate(text: str) -> str | None:
    if match := PLATE_RE.search(text):
        return f"{match.group(1)}-{match.group(2)} {match.group(3)}"
    return None


def _vehicle(text: str) -> tuple[str | None, str | None]:
    for matcher, make in MAKE_MATCHERS:
        if match := matcher.search(text):
            if make in AMBIGUOUS_MAKES and not _ambiguous_make_supported(text, match):
                continue
            return make, _model_after_make(text[match.end() :])

    return None, _model_from_context(text)


def _ambiguous_make_supported(text: str, match: re.Match[str]) -> bool:
    before = text[max(0, match.start() - 70) : match.start()].lower()
    after = text[match.end() : match.end() + 70].lower()

    if re.match(r"\s+(?:antwort|aufwand|gelöst|geloest|home|lösung|loesung|problem|repair)\b", after):
        return False
    vehicle_words = r"\b(?:auto|fahrzeug|inspektion|kennzeichen|modell|nummernschild|pkw|service|termin|wagen|werkstatt)\b"
    if re.search(vehicle_words, before + after):
        return True
    return bool(
        re.search(
            r"\b(?:fahre|fährt|faehrt|gefahren|habe|haben|besitze)\s+"
            r"(?:einen|meinen|meinem|unseren|unserem)?\s*$",
            before,
        )
        or re.search(r"\b(?:mein(?:e[rmn]?|en|em)?|unser(?:e[rmn]?|en|em)?)\s+$", before)
    )


def _model_after_make(tail: str) -> str | None:
    chunk = re.split(r"[.,;!?\n]", tail.lstrip(), maxsplit=1)[0]
    return _clean_model(chunk)


def _model_from_context(text: str) -> str | None:
    for pattern in MODEL_CONTEXT_PATTERNS:
        if match := pattern.search(text):
            return _clean_model(match.group("model"))
    return None


def _clean_model(candidate: str) -> str | None:
    candidate = re.split(r"(?<=[.;!?])\s+", candidate.strip(), maxsplit=1)[0]
    parts = []
    for token in re.findall(r"[A-Za-zÄÖÜäöüß0-9][A-Za-zÄÖÜäöüß0-9.+-]*", candidate):
        token = token.strip(".,;:!?")
        if token.lower() in MODEL_STOPWORDS:
            break
        parts.append(token)
        if len(parts) == 3:
            break
    return " ".join(parts) or None


def _intent(lower: str) -> str:
    for intent, keywords in INTENT_RULES:
        if _has(lower, keywords):
            return intent
    return "appointment" if "termin" in lower else "unknown"


def _sentiment(lower: str) -> str:
    if _has(lower, NEGATIVE_WORDS):
        return "negative"
    return "positive" if _has(lower, POSITIVE_WORDS) else "neutral"


def _follow_up_required(lower: str, intent: str) -> bool:
    if intent in {"information", "other", "transfer_request"}:
        return False
    if _has(lower, FOLLOW_UP_WORDS) or _has(lower, ("schicken sie mir", "per mail")):
        return True
    return _has(lower, BOOKING_WORDS) and not _has(lower, BOOKING_DONE_WORDS)


def _summary(
    lower: str,
    intent: str,
    vehicle_make: str | None,
    vehicle_model: str | None,
    plate: str | None,
    email: str | None,
) -> str:
    vehicle = " ".join(part for part in (vehicle_make, vehicle_model) if part)
    vehicle_part = f" für einen {vehicle}" if vehicle else ""
    plate_part = f" Das Kennzeichen lautet {plate}." if plate else ""
    email_part = f" Die E-Mail-Adresse wurde als {email} genannt." if email else ""

    if intent == "complaint":
        return "Die anrufende Person beschwert sich über fehlende Rückmeldung zur Werkstatt und bittet um Auskunft oder Rückruf."
    if intent == "sales":
        return f"Die anrufende Person interessiert sich{vehicle_part} und möchte eine Probefahrt oder Bestätigung vereinbaren."
    if intent == "information":
        return "Die anrufende Person fragt nach den heutigen Öffnungszeiten der Serviceannahme."
    if intent == "transfer_request":
        return "Die anrufende Person möchte mit einer Person im Service verbunden werden."
    if intent == "callback_request":
        return "Die anrufende Person bittet um einen Rückruf."
    if "verwählt" in lower:
        return "Die anrufende Person hat sich verwählt."
    if "kostenvoranschlag" in lower:
        return f"Die anrufende Person bittet darum, einen Kostenvoranschlag per E-Mail zu erhalten.{email_part}"
    if "klimaanlage" in lower:
        return f"Die anrufende Person meldet ein Problem mit der Klimaanlage{vehicle_part}."
    if "termin" in lower and "bestätigen" in lower:
        return "Die anrufende Person bestätigt einen bestehenden Termin."
    if intent in {"service", "appointment"}:
        return f"Die anrufende Person möchte einen Service- oder Werkstatttermin{vehicle_part} klären.{plate_part}"
    return "Die anrufende Person hat ein Anliegen beim Autohaus geschildert."
