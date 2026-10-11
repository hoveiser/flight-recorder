from pydantic import BaseModel, Field
from typing import Annotated, Optional
from datetime import datetime

from .hash_chain import EVENT_HASH_VERSION_LEGACY

# Bound every piece of caller-supplied text before it reaches a signature check,
# a hash, or the database. These are not cosmetics: the server hashes what it is
# given, and an unbounded field is an unbounded amount of work and storage that any
# caller can hand to it. The deal id limit matches the contract's own
# `assert len(deal_id) <= 100`, so an evidence log and the deal that judges it
# cannot disagree about what fits.
DEAL_ID_MAX_LENGTH = 100
EVENT_TYPE_MAX_LENGTH = 64
PARTY_ADDRESS_MAX_COUNT = 20
CLAIM_MAX_LENGTH = 2000
SIGNATURE_MAX_LENGTH = 200
CLIENT_TIMESTAMP_MAX_LENGTH = 64
NONCE_MAX_LENGTH = 200
# An Ethereum address, and the only thing a party may be identified by: a name is a
# self-report, an address can be proven by a signature.
ADDRESS_PATTERN = r"^0x[0-9a-fA-F]{40}$"

DealId = Annotated[str, Field(min_length=1, max_length=DEAL_ID_MAX_LENGTH)]
Address = Annotated[str, Field(pattern=ADDRESS_PATTERN)]


class EventCreate(BaseModel):
    """Input: agent sends this to record an event

    `signature` and `client_timestamp` are what make a write attributable: the
    server recovers the signer from the EIP-191 signature over the canonical
    event message and refuses the write unless that address is the actor, the
    actor is a party to the deal, and the actor is the authenticated session.
    """
    deal_id: DealId
    actor: Address
    event_type: Annotated[str, Field(min_length=1, max_length=EVENT_TYPE_MAX_LENGTH)]
    payload: dict = {}
    metadata: dict = {}
    signature: Optional[Annotated[str, Field(max_length=SIGNATURE_MAX_LENGTH)]] = None
    client_timestamp: Optional[Annotated[str, Field(max_length=CLIENT_TIMESTAMP_MAX_LENGTH)]] = None


class Event(EventCreate):
    """Stored event with hash chain fields.

    The response fields are deliberately re-declared without the input bounds: a
    row written before an input limit existed must stay readable, and refusing to
    serve history would turn a hardening change into data loss.
    """
    deal_id: str
    actor: str
    event_type: str
    signature: Optional[str] = None
    client_timestamp: Optional[str] = None
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
    deal_id: DealId
    definition_of_done: dict
    parties: Annotated[list[Address], Field(min_length=1, max_length=PARTY_ADDRESS_MAX_COUNT)]


class Deal(DealCreate):
    """Stored deal. As with Event, the response keeps no input bounds so that a
    record written before a limit existed can still be read back."""
    deal_id: str
    parties: list[str]
    agreement_hash: str
    created_at: datetime
    # Once a dispute is filed the evidence log is frozen: no further events may
    # be appended, so the anchored case file can never be extended afterwards.
    sealed: bool = False


class DisputeCreate(BaseModel):
    """Input: a party files a dispute with their claim"""
    deal_id: DealId
    party: Address
    claim: Annotated[str, Field(min_length=1, max_length=CLAIM_MAX_LENGTH)]


class Dispute(DisputeCreate):
    """Stored dispute, same rule as Deal and Event: history stays readable."""
    deal_id: str
    party: str
    claim: str
    id: int
    filed_at: datetime
