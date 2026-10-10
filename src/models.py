from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from .hash_chain import EVENT_HASH_VERSION_LEGACY


class EventCreate(BaseModel):
    """Input: agent sends this to record an event

    `signature` and `client_timestamp` are what make a write attributable: the
    server recovers the signer from the EIP-191 signature over the canonical
    event message and refuses the write unless that address is the actor, the
    actor is a party to the deal, and the actor is the authenticated session.
    """
    deal_id: str
    actor: str
    event_type: str  # REQUEST, RESPONSE, DELIVERY, VALIDATION, WARNING, ERROR, PAYMENT_INTENT, STATE_CHANGE, CUSTOM
    payload: dict = {}
    metadata: dict = {}
    signature: Optional[str] = None
    client_timestamp: Optional[str] = None


class Event(EventCreate):
    """Stored event with hash chain fields"""
    id: int
    payload_hash: str
    previous_event_hash: str
    event_hash: str
    timestamp: datetime
    # 1 = written before event signing existed (no signature), 2 = signed.
    # Verification picks the hash formula from this field instead of guessing,
    # and it is never rewritten in place for old rows.
    sig_version: int = EVENT_HASH_VERSION_LEGACY


class DealCreate(BaseModel):
    """Input: create a deal with definition of done"""
    deal_id: str
    definition_of_done: dict
    parties: list[str]


class Deal(DealCreate):
    """Stored deal"""
    agreement_hash: str
    created_at: datetime
    # Once a dispute is filed the evidence log is frozen: no further events may
    # be appended, so the anchored case file can never be extended afterwards.
    sealed: bool = False


class DisputeCreate(BaseModel):
    """Input: a party files a dispute with their claim"""
    deal_id: str
    party: str
    claim: str


class Dispute(DisputeCreate):
    """Stored dispute"""
    id: int
    filed_at: datetime