"""Typed, versioned cache shared by the billing collector and admin API.

The collector records AWS charges and function-level CloudWatch statistics.
Calendar periods are UTC; money stays decimal until presentation in the browser.
Missing metric samples remain null, independently of legitimate numeric zeroes.
The web application reads this cache without invoking billing or metrics APIs.
A failed collection never replaces the last complete snapshot.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, computed_field

BILLING_BUCKET_ENV = "PLANTTRACER_BILLING_BUCKET"
CACHE_KEY = "summary.json"
STALE_AFTER = timedelta(hours=36)
CACHE_SCHEMA_VERSION = 2


class Charges(BaseModel):
    """A signed reconciliation of charges and credits/refunds, in USD."""
    name: str
    gross: Decimal = Decimal(0)
    credits: Decimal = Decimal(0)

    @computed_field
    @property
    def net(self) -> Decimal:
        """Net charges include negative credits and refunds."""
        return self.gross + self.credits


class MonthCosts(BaseModel):
    """Costs for one UTC calendar period; end is exclusive."""
    start: date
    end: date
    estimated: bool = True
    total: Charges = Field(default_factory=lambda: Charges(name="All AWS services"))
    services: list[Charges] = Field(default_factory=list)
    lambda_usage: list[Charges] = Field(default_factory=list)
    stack_gross: list[Charges] = Field(default_factory=list)


class Activity(BaseModel):
    """CloudWatch samples, with absent series represented as unknown."""
    invocations: float | None = None
    errors: float | None = None
    duration_ms: float | None = None


class StackLifetime(BaseModel):
    """CloudFormation existence, not invocation time or retained-resource lifetime."""
    started_at: AwareDatetime
    stopped_at: AwareDatetime | None = None
    status: str


class FunctionUsage(BaseModel):
    """One physical function, aggregated across its versions without duplication."""
    name: str
    region: str
    stack: str
    component: str
    stack_id: str | None = None
    stack_lifetime: StackLifetime | None = None
    current: Activity = Field(default_factory=Activity)
    previous: Activity = Field(default_factory=Activity)
    snapshots: int = 0
    snapshot_gb: Decimal = Decimal(0)


class BillingSnapshot(BaseModel):
    """Complete collector output; account costs and regional activity have distinct scopes."""
    schema_version: Literal[1, 2] = CACHE_SCHEMA_VERSION
    account_id: str = Field(pattern=r"^\d{12}$")
    collected_at: AwareDatetime
    activity_region: str
    current: MonthCosts
    previous: MonthCosts
    functions: list[FunctionUsage]
    cache_rate_per_gb_second: Decimal | None = None

    @computed_field
    @property
    def snapshot_monthly_estimate(self) -> Decimal | None:
        """Thirty-day run rate using the observed gross cache rate, not a price promise."""
        if self.cache_rate_per_gb_second is None:
            return None
        return sum(f.snapshot_gb for f in self.functions) * 30 * 86400 * self.cache_rate_per_gb_second


def month_boundaries(now: datetime) -> tuple[date, date, date]:
    """Return previous-month start, current-month start, and tomorrow in UTC."""
    today = now.astimezone(timezone.utc).date()
    current = today.replace(day=1)
    previous = (current - timedelta(days=1)).replace(day=1)
    return previous, current, today + timedelta(days=1)
