# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Colab compute-unit display helpers (parity with colab-vscode status-bar.ts)."""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SubscriptionTier(str, Enum):
    NONE = "NONE"
    PRO = "PRO"
    PRO_PLUS = "PRO_PLUS"


class ConsumptionDataSource(str, Enum):
    """Where consumption fields were loaded from."""

    GAPI = "gapi"
    TUNNEL = "tunnel"


_GAPI_SUBSCRIPTION_TIER_MAP = {
    "SUBSCRIPTION_TIER_PRO": SubscriptionTier.PRO,
    "SUBSCRIPTION_TIER_PRO_PLUS": SubscriptionTier.PRO_PLUS,
    "SUBSCRIPTION_TIER_FREE": SubscriptionTier.NONE,
    "SUBSCRIPTION_TIER_NONE": SubscriptionTier.NONE,
}


def normalize_subscription_tier(value: object) -> SubscriptionTier:
    if isinstance(value, SubscriptionTier):
        return value
    if isinstance(value, str):
        return _GAPI_SUBSCRIPTION_TIER_MAP.get(value, SubscriptionTier.NONE)
    return SubscriptionTier.NONE


def _normalize_subscription_tier(value: object) -> SubscriptionTier:
    return normalize_subscription_tier(value)


class FreeCcuQuotaInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    remaining_tokens: Optional[int] = Field(None, alias="remainingTokens")
    next_refill_timestamp_sec: Optional[int] = Field(
        None, alias="nextRefillTimestampSec"
    )

    @field_validator("remaining_tokens", mode="before")
    @classmethod
    def _parse_remaining_tokens(cls, value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str):
            return int(value)
        return int(value)


class CcuInfo(BaseModel):
    """Response from ``GET /tun/m/ccu-info`` (session backend)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    current_balance: float = Field(..., alias="currentBalance")
    consumption_rate_hourly: float = Field(..., alias="consumptionRateHourly")
    assignments_count: int = Field(..., alias="assignmentsCount")


class ConsumptionUserInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    subscription_tier: Optional[SubscriptionTier] = Field(
        None, alias="subscriptionTier"
    )
    paid_compute_units_balance: float = Field(..., alias="paidComputeUnitsBalance")
    consumption_rate_hourly: float = Field(..., alias="consumptionRateHourly")
    assignments_count: int = Field(..., alias="assignmentsCount")
    free_ccu_quota_info: Optional[FreeCcuQuotaInfo] = Field(
        None, alias="freeCcuQuotaInfo"
    )

    @field_validator("subscription_tier", mode="before")
    @classmethod
    def _normalize_tier(cls, value: object) -> Optional[SubscriptionTier]:
        if value is None:
            return None
        return normalize_subscription_tier(value)


@dataclass(frozen=True)
class ConsumptionFetchResult:
    """Consumption data plus provenance for honest display."""

    info: ConsumptionUserInfo
    source: ConsumptionDataSource


def consumption_user_info_from_tunnel(
    ccu: CcuInfo,
    *,
    subscription_tier: Optional[SubscriptionTier] = None,
) -> ConsumptionUserInfo:
    """Map tunnel ccu-info into the shared ConsumptionUserInfo container."""
    return ConsumptionUserInfo(
        subscription_tier=subscription_tier,
        paid_compute_units_balance=ccu.current_balance,
        consumption_rate_hourly=ccu.consumption_rate_hourly,
        assignments_count=ccu.assignments_count,
        free_ccu_quota_info=None,
    )


def approximate_free_minutes_remaining(
    remaining_free_tokens: int,
    consumption_rate_hourly: float,
) -> int:
    """Port of colab-vscode approximateFreeMinutesRemaining (10-minute buckets)."""
    free_minutes_remaining = (
        remaining_free_tokens / 1000 / consumption_rate_hourly
    ) * 60
    return math.floor(free_minutes_remaining / 10) * 10


def _subscription_line(tier: SubscriptionTier) -> str:
    if tier == SubscriptionTier.PRO:
        return "You are subscribed to Colab Pro."
    if tier == SubscriptionTier.PRO_PLUS:
        return "You are subscribed to Colab Pro+."
    return "You are not subscribed."


def format_consumption_rate_line(info: ConsumptionUserInfo) -> str:
    rate = f"{info.consumption_rate_hourly:.2f}"
    return f"{rate}/hr"


def format_gapi_consumption_tooltip(info: ConsumptionUserInfo) -> str:
    """Verbatim tooltip text from colab-vscode consumption status bar (GAPI only)."""
    rate = f"{info.consumption_rate_hourly:.2f}"
    sections: list[str] = []

    if info.subscription_tier is not None:
        sections.append(_subscription_line(info.subscription_tier))

    if info.paid_compute_units_balance <= 0:
        body = (
            "You currently have zero compute units available. "
            "Resources offered free of charge are not guaranteed."
        )
        remaining_free_tokens = 0
        if info.free_ccu_quota_info and info.free_ccu_quota_info.remaining_tokens:
            remaining_free_tokens = info.free_ccu_quota_info.remaining_tokens
        if remaining_free_tokens > 0 and info.consumption_rate_hourly > 0:
            approx_free_minutes = approximate_free_minutes_remaining(
                remaining_free_tokens, info.consumption_rate_hourly
            )
            hours = approx_free_minutes // 60
            minutes = approx_free_minutes % 60
            body += (
                "\n\nAt your current usage level, your server(s) may last up to "
                f"{hours:.0f}h{minutes:.0f}m."
            )
        sections.append(body)
    else:
        balance = f"{info.paid_compute_units_balance:.2f}"
        session_count = f"{info.assignments_count:.0f}"
        sections.append(
            f"Available: {balance} compute units\n"
            f"Usage rate: approximately {rate} per hour\n"
            f"You have {session_count} active session(s)."
        )

    return "\n\n".join(sections)


def format_tunnel_consumption_tooltip(info: ConsumptionUserInfo) -> str:
    """Partial display for session-backend ccu-info — only assert fetched fields."""
    rate = f"{info.consumption_rate_hourly:.2f}"
    sections: list[str] = []

    if info.subscription_tier is not None:
        sections.append(_subscription_line(info.subscription_tier))

    balance = f"{info.paid_compute_units_balance:.2f}"
    count = f"{info.assignments_count:.0f}"
    sections.append(
        f"Current balance: {balance} compute units\n"
        f"Usage rate: approximately {rate} per hour\n"
        f"Active assignments: {count}"
    )
    return "\n\n".join(sections)


def format_consumption_tooltip(result: ConsumptionFetchResult) -> str:
    if result.source == ConsumptionDataSource.GAPI:
        return format_gapi_consumption_tooltip(result.info)
    return format_tunnel_consumption_tooltip(result.info)


def format_consumption_status(result: ConsumptionFetchResult) -> str:
    """Rate line plus detail block, labeled according to data source."""
    return (
        f"{format_consumption_rate_line(result.info)}\n"
        f"{format_consumption_tooltip(result)}"
    )
