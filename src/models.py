from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EventCreate(BaseModel):
    """Input: agent sends this to record an event"""
    deal_id: str
    actor: str
    event_type: str  # REQUEST, RESPONSE, DELIVERY, VALIDATION, WARNING, ERROR, PAYMENT_INTENT, STATE_CHANGE, CUSTOM
    payload: dict = {}
    metadata: dict = {}


class Event(EventCreate):
    """Stored event with hash chain fields"""
    id: int
    payload_hash: str
    previous_event_hash: str
    event_hash: str
    timestamp: datetime


class DealCreate(BaseModel):
    """Input: create a deal with definition of done"""
    deal_id: str
    definition_of_done: dict
    parties: list[str]


class Deal(DealCreate):
    """Stored deal"""
    agreement_hash: str
    created_at: datetime