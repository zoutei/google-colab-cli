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

"""Tests mirroring colab-vscode status-bar.unit.test.ts consumption display."""

import pytest

from colab_cli.consumption import (
    ConsumptionDataSource,
    ConsumptionFetchResult,
    ConsumptionUserInfo,
    FreeCcuQuotaInfo,
    SubscriptionTier,
    approximate_free_minutes_remaining,
    format_consumption_status,
    format_consumption_tooltip,
    format_gapi_consumption_tooltip,
    format_tunnel_consumption_tooltip,
)


def _info(**kwargs) -> ConsumptionUserInfo:
    defaults = {
        "subscription_tier": SubscriptionTier.NONE,
        "paid_compute_units_balance": 0.0,
        "consumption_rate_hourly": 0.07,
        "assignments_count": 0,
        "free_ccu_quota_info": None,
    }
    defaults.update(kwargs)
    return ConsumptionUserInfo(**defaults)


def _gapi_result(**kwargs) -> ConsumptionFetchResult:
    return ConsumptionFetchResult(info=_info(**kwargs), source=ConsumptionDataSource.GAPI)


def _tunnel_result(**kwargs) -> ConsumptionFetchResult:
    return ConsumptionFetchResult(info=_info(**kwargs), source=ConsumptionDataSource.TUNNEL)


class TestApproximateFreeMinutesRemaining:
    def test_quantizes_to_ten_minute_buckets(self):
        # 5960 milli-CCU at 0.07/hr -> 85h0m in vscode fixture
        assert approximate_free_minutes_remaining(5960, 0.07) == 85 * 60


class TestFormatConsumptionTooltip:
  tier_tests = [
      (
          SubscriptionTier.NONE,
          "You are not subscribed.",
      ),
      (
          SubscriptionTier.PRO,
          "You are subscribed to Colab Pro.",
      ),
      (
          SubscriptionTier.PRO_PLUS,
          "You are subscribed to Colab Pro+.",
      ),
  ]

  paid_balance_tests = [
      (
          "zero paid balance and undefined free quota",
          {
              "paid_compute_units_balance": 0,
              "free_ccu_quota_info": None,
              "consumption_rate_hourly": 0.07,
              "assignments_count": 0,
          },
          (
              "You currently have zero compute units available. "
              "Resources offered free of charge are not guaranteed."
          ),
      ),
      (
          "zero paid balance and negative free quota",
          {
              "paid_compute_units_balance": 0,
              "free_ccu_quota_info": FreeCcuQuotaInfo(
                  remaining_tokens=-1, next_refill_timestamp_sec=0
              ),
              "consumption_rate_hourly": 0.07,
              "assignments_count": 1,
          },
          (
              "You currently have zero compute units available. "
              "Resources offered free of charge are not guaranteed."
          ),
      ),
      (
          "zero paid balance and zero free quota",
          {
              "paid_compute_units_balance": 0,
              "free_ccu_quota_info": FreeCcuQuotaInfo(
                  remaining_tokens=0, next_refill_timestamp_sec=0
              ),
              "consumption_rate_hourly": 0.07,
              "assignments_count": 1,
          },
          (
              "You currently have zero compute units available. "
              "Resources offered free of charge are not guaranteed."
          ),
      ),
      (
          "zero paid balance but positive free quota and consumption rate",
          {
              "paid_compute_units_balance": 0,
              "free_ccu_quota_info": FreeCcuQuotaInfo(
                  remaining_tokens=5960, next_refill_timestamp_sec=0
              ),
              "consumption_rate_hourly": 0.07,
              "assignments_count": 1,
          },
          (
              "You currently have zero compute units available. "
              "Resources offered free of charge are not guaranteed.\n\n"
              "At your current usage level, your server(s) may last up to "
              "85h0m."
          ),
      ),
      (
          "positive paid balance",
          {
              "paid_compute_units_balance": 123.45,
              "free_ccu_quota_info": None,
              "consumption_rate_hourly": 0.07,
              "assignments_count": 4,
          },
          (
              "Available: 123.45 compute units\n"
              "Usage rate: approximately 0.07 per hour\n"
              "You have 4 active session(s)."
          ),
      ),
  ]

  @pytest.mark.parametrize("tier, tier_line", tier_tests)
  @pytest.mark.parametrize("case_name, fields, balance_part", paid_balance_tests)
  def test_matches_vscode_status_bar_tooltip(
      self, tier, tier_line, case_name, fields, balance_part
  ):
      info = _info(subscription_tier=tier, **fields)
      expected = f"{tier_line}\n\n{balance_part}"
      assert format_gapi_consumption_tooltip(info) == expected


class TestFormatConsumptionStatus:
    def test_paid_pro_user(self):
        expected = (
            "0.07/hr\n"
            "You are subscribed to Colab Pro.\n"
            "\n"
            "Available: 123.45 compute units\n"
            "Usage rate: approximately 0.07 per hour\n"
            "You have 4 active session(s)."
        )
        assert format_consumption_status(_gapi_result(
            subscription_tier=SubscriptionTier.PRO,
            paid_compute_units_balance=123.45,
            consumption_rate_hourly=0.07,
            assignments_count=4,
        )) == expected


class TestTunnelConsumptionDisplay:
    def test_uses_current_balance_wording_not_paid_path(self):
        info = _info(
            paid_compute_units_balance=298.53,
            consumption_rate_hourly=0.0,
            assignments_count=0,
            subscription_tier=None,
        )
        tooltip = format_tunnel_consumption_tooltip(info)
        assert "Current balance: 298.53 compute units" in tooltip
        assert "Active assignments: 0" in tooltip
        assert "Available:" not in tooltip
        assert "zero compute units available" not in tooltip
        assert "subscribed" not in tooltip.lower()

    def test_includes_subscription_only_when_known(self):
        info = _info(
            subscription_tier=SubscriptionTier.PRO,
            paid_compute_units_balance=10.0,
            consumption_rate_hourly=0.07,
            assignments_count=1,
        )
        tooltip = format_tunnel_consumption_tooltip(info)
        assert tooltip.startswith("You are subscribed to Colab Pro.")
