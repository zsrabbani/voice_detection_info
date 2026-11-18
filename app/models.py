"""Output contract. Keep these shapes so results are comparable.

You may add fields (e.g. per-field confidence), but do not remove these.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class EnrichedLead(BaseModel):
    call_id: str
    contact_name: Optional[str] = None       # the CALLER's name, not a third party
    summary: Optional[str] = None            # 1-2 sentences, German or English
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = None
    intent: Optional[str] = None             # service | sales | complaint | appointment |
                                             # information | callback_request | transfer_request | other | unknown
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    license_plate: Optional[str] = None
    email: Optional[str] = None
    follow_up_required: Optional[bool] = None

    # every field you could NOT determine from the transcript
    unresolved_fields: list[str] = Field(default_factory=list)
