"""Autofill profile data models for cards, addresses, and identities."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class CardProfile:
    """Payment card profile."""

    label: str  # e.g. "Chase Sapphire", "Amex Gold"
    cardholder_name: str
    card_number: str
    exp_month: str  # MM
    exp_year: str  # YYYY
    cvv: str
    billing_address: str = ""
    billing_zip: str = ""
    profile_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> CardProfile:
        return cls(**json.loads(data))

    @property
    def masked_number(self) -> str:
        if len(self.card_number) >= 4:
            return f"****{self.card_number[-4:]}"
        return "****"

    @property
    def exp_combined(self) -> str:
        """MM/YYYY format for forms that use a single expiry field."""
        return f"{self.exp_month}/{self.exp_year}"


@dataclass
class AddressProfile:
    """Mailing/billing address profile."""

    label: str
    full_name: str
    street: str
    city: str
    state: str
    zip_code: str
    country: str = "US"
    phone: str = ""
    profile_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> AddressProfile:
        return cls(**json.loads(data))


@dataclass
class IdentityProfile:
    """Personal identity profile for general form filling."""

    label: str
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    date_of_birth: str = ""  # YYYY-MM-DD
    profile_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> IdentityProfile:
        return cls(**json.loads(data))


# Vault key prefixes
CARD_PREFIX = "autofill_card_"
ADDRESS_PREFIX = "autofill_addr_"
IDENTITY_PREFIX = "autofill_id_"

PROFILE_TYPES = {
    "card": (CARD_PREFIX, CardProfile),
    "address": (ADDRESS_PREFIX, AddressProfile),
    "identity": (IDENTITY_PREFIX, IdentityProfile),
}
