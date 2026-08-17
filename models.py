from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PilotQAPlan(str, Enum):
    trial = "trial"
    pro = "pro"
    enterprise = "enterprise"
    canceled = "canceled"


class PilotQASubscriber(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True)
    plan: str = Field(default=PilotQAPlan.trial)
    trial_ends_at: Optional[datetime] = Field(default=None)
    asaas_customer_id: Optional[str] = Field(default=None)
    asaas_subscription_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
