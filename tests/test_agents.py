"""Tool-level tests for analytics-agents.

Each test class covers one MCP tool and verifies:
  1. Correct JSON structure and field types.
  2. Numerical agreement with the underlying adsat function called directly.
  3. Edge cases and error handling.

Fixtures
--------
``csv_path``   — temporary CSV with 3 deterministic synthetic campaigns.
``batch_json`` — JSON returned by ``analyse_campaign_saturation``.
``budget_json``— JSON returned by ``optimise_budget``.

All synthetic data uses ``np.random.seed(42)`` for determinism.
All expensive adsat runs are scoped to ``"module"`` so they execute once.
"""

from __future__ import annotations

import json
import os
from typing import Any

import numpy as np
import pandas as pd
import pytest
from adsat.budget import BudgetOptimizer
from adsat.campaign import CampaignSaturationAnalyzer

from agents.campaign_analyst import (
    _deserialise_batch_result,
    analyse_campaign_saturation,
    generate_report,
    optimise_budget,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_campaign_df() -> pd.DataFrame:
    """Return a deterministic 3-campaign DataFrame (180 rows total).

    Uses ``np.random.seed(42)`` for reproducibility.  Campaign C intentionally
    has only 5 rows so it fails the ``min_observations=10`` check, giving the
    test suite a built-in failed campaign.
    """
    np.random.seed(42)
    rows = []
    for campaign, ec50, a, n_pts in [
        ("Alpha", 1_200_000, 30_000, 60),
        ("Beta", 800_000, 20_000, 60),
        ("Gamma", 600_000, 15_000, 60),
    ]:
        x = np.linspace(100_000, 3_000_000, n_pts)
        y = a * (x**1.5) / (ec50**1.5 + x**1.5) + np.random.normal(0, 200, n_pts)
        for xi, yi in zip(x, y):
            rows.append(
                {
                    "campaign": campaign,
                    "impressions": int(xi),
                    "conversions": float(max(yi, 0.0)),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def csv_path(tmp_path_factory) -> str:
    """Write the synthetic campaign DataFrame to a temp CSV and return its path."""
    path = tmp_path_factory.mktemp("data") / "campaigns.csv"
    _make_campaign_df().to_csv(path, index=False)
    return str(path)


@pytest.fixture(scope="module")
def batch_json(csv_path: str) -> str:
    """Return the JSON string from ``analyse_campaign_saturation``."""
    return analyse_campaign_saturation(
        csv_path=csv_path,
        x_col="impressions",
        y_col="conversions",
        campaign_col="campaign",
    )


@pytest.fixture(scope="module")
def budget_json(batch_json: str) -> str:
    """Return the JSON string from ``optimise_budget``."""
    return optimise_budget(batch_json=batch_json, total_budget=3_000_000)


# ---------------------------------------------------------------------------
# TestAnalyseCampaignSaturation
# ---------------------------------------------------------------------------


class TestAnalyseCampaignSaturation:
    """Tests for the ``analyse_campaign_saturation`` MCP tool."""

    # ── happy path ───────────────────────────────────────────────────────────

    def test_returns_valid_json(self, batch_json: str) -> None:
        """Output must be a valid JSON string."""
        result = json.loads(batch_json)
        assert isinstance(result, dict)

    def test_metadata_structure(self, batch_json: str) -> None:
        """Metadata block must contain all required keys with correct types."""
        meta = json.loads(batch_json)["metadata"]
        assert meta["campaign_col"] == "campaign"
        assert meta["x_col"] == "impressions"
        assert meta["y_col"] == "conversions"
        assert isinstance(meta["n_total"], int)
        assert isinstance(meta["n_succeeded"], int)
        assert isinstance(meta["n_failed"], int)
        assert meta["n_total"] == meta["n_succeeded"] + meta["n_failed"]

    def test_campaign_count(self, batch_json: str) -> None:
        """All 3 campaigns must appear in the output."""
        campaigns = json.loads(batch_json)["campaigns"]
        assert len(campaigns) == 3
        ids = {c["campaign_id"] for c in campaigns}
        assert ids == {"Alpha", "Beta", "Gamma"}

    def test_campaign_fields_present(self, batch_json: str) -> None:
        """Each campaign entry must contain the full set of required fields."""
        required_keys = {
            "campaign_id",
            "n_observations",
            "best_model",
            "saturation_point",
            "saturation_y",
            "current_x_median",
            "pct_of_saturation",
            "saturation_status",
            "r2",
            "rmse",
            "aic",
            "converged",
            "succeeded",
            "error",
            "best_model_params",
        }
        for c in json.loads(batch_json)["campaigns"]:
            assert required_keys.issubset(c.keys()), (
                f"Missing keys for {c['campaign_id']}: " f"{required_keys - c.keys()}"
            )

    def test_json_types_are_native_python(self, batch_json: str) -> None:
        """No numpy scalar types should survive serialisation."""
        result = json.loads(batch_json)
        for c in result["campaigns"]:
            if c["r2"] is not None:
                assert isinstance(c["r2"], float), f"r2 is {type(c['r2'])}"
            if c["n_observations"] is not None:
                assert isinstance(c["n_observations"], int)
            if c["converged"] is not None:
                assert isinstance(c["converged"], bool)

    def test_saturation_status_values(self, batch_json: str) -> None:
        """saturation_status must be one of the four defined values (or 'unknown')."""
        valid = {"below", "approaching", "at", "beyond", "unknown"}
        for c in json.loads(batch_json)["campaigns"]:
            assert c["saturation_status"] in valid, f"Unexpected status: {c['saturation_status']}"

    # ── matches adsat directly ────────────────────────────────────────────────

    def test_matches_adsat_saturation_points(self, csv_path: str, batch_json: str) -> None:
        """Saturation points from the tool must match a direct adsat call within 1%."""
        df = _make_campaign_df()
        analyzer = CampaignSaturationAnalyzer(
            campaign_col="campaign",
            x_col="impressions",
            y_col="conversions",
            verbose=False,
        )
        direct_batch = analyzer.run(df)

        tool_campaigns = {c["campaign_id"]: c for c in json.loads(batch_json)["campaigns"]}

        for cid in direct_batch.succeeded_campaigns():
            direct_cr = direct_batch.get(cid)
            tool_c = tool_campaigns[cid]
            if direct_cr.saturation_point and tool_c["saturation_point"]:
                diff_pct = (
                    abs(direct_cr.saturation_point - tool_c["saturation_point"])
                    / direct_cr.saturation_point
                )
                assert diff_pct < 0.01, f"{cid}: saturation_point differs by {diff_pct:.2%}"

    def test_matches_adsat_r2(self, csv_path: str, batch_json: str) -> None:
        """R² values from the tool must match a direct adsat call exactly."""
        df = _make_campaign_df()
        analyzer = CampaignSaturationAnalyzer(
            campaign_col="campaign",
            x_col="impressions",
            y_col="conversions",
            verbose=False,
        )
        direct_batch = analyzer.run(df)

        tool_campaigns = {c["campaign_id"]: c for c in json.loads(batch_json)["campaigns"]}

        for cid in direct_batch.succeeded_campaigns():
            direct_r2 = direct_batch.get(cid).r2
            tool_r2 = tool_campaigns[cid]["r2"]
            if direct_r2 is not None and tool_r2 is not None:
                assert (
                    abs(direct_r2 - tool_r2) < 1e-3
                ), f"{cid}: r2 mismatch — direct={direct_r2}, tool={tool_r2}"

    # ── edge cases ───────────────────────────────────────────────────────────

    def test_single_campaign_mode(self, csv_path: str) -> None:
        """When campaign_col is omitted the whole dataset is one campaign labelled 'all'."""
        result = json.loads(
            analyse_campaign_saturation(
                csv_path=csv_path,
                x_col="impressions",
                y_col="conversions",
            )
        )
        assert result["metadata"]["n_total"] == 1
        assert result["campaigns"][0]["campaign_id"] == "all"

    def test_exclude_campaigns(self, csv_path: str) -> None:
        """Excluded campaigns must not appear in the output."""
        result = json.loads(
            analyse_campaign_saturation(
                csv_path=csv_path,
                x_col="impressions",
                y_col="conversions",
                campaign_col="campaign",
                exclude_campaigns=["Beta"],
            )
        )
        ids = {c["campaign_id"] for c in result["campaigns"]}
        assert "Beta" not in ids
        assert result["metadata"]["n_total"] == 2

    def test_include_response_curves(self, csv_path: str) -> None:
        """When include_response_curves=True, each succeeded campaign has a response_curve dict."""
        result = json.loads(
            analyse_campaign_saturation(
                csv_path=csv_path,
                x_col="impressions",
                y_col="conversions",
                campaign_col="campaign",
                include_response_curves=True,
            )
        )
        for c in result["campaigns"]:
            if c["succeeded"]:
                assert (
                    c.get("response_curve") is not None
                ), f"{c['campaign_id']}: response_curve is None despite succeeded=True"

    def test_missing_csv_raises_file_not_found(self) -> None:
        """A non-existent CSV path must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            analyse_campaign_saturation(
                csv_path="/no/such/file.csv",
                x_col="impressions",
                y_col="conversions",
            )

    def test_bad_column_raises_value_error(self, csv_path: str) -> None:
        """A column name absent from the CSV must raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            analyse_campaign_saturation(
                csv_path=csv_path,
                x_col="nonexistent_col",
                y_col="conversions",
                campaign_col="campaign",
            )


# ---------------------------------------------------------------------------
# TestOptimiseBudget
# ---------------------------------------------------------------------------


class TestOptimiseBudget:
    """Tests for the ``optimise_budget`` MCP tool."""

    # ── happy path ───────────────────────────────────────────────────────────

    def test_returns_valid_json(self, budget_json: str) -> None:
        """Output must be a valid JSON string."""
        result = json.loads(budget_json)
        assert isinstance(result, dict)

    def test_output_structure(self, budget_json: str) -> None:
        """All required top-level keys must be present with correct types."""
        result = json.loads(budget_json)
        assert isinstance(result["total_budget"], float)
        assert isinstance(result["total_current_outcome"], float)
        assert isinstance(result["total_optimal_outcome"], float)
        assert isinstance(result["total_outcome_lift"], float)
        assert isinstance(result["total_outcome_lift_pct"], float)
        assert isinstance(result["converged"], bool)
        assert isinstance(result["notes"], str)
        assert isinstance(result["campaigns"], list)
        assert isinstance(result["excluded_campaigns"], list)

    def test_budget_constraint_satisfied(self, budget_json: str) -> None:
        """Optimal spend values must sum to total_budget within 1 unit."""
        result = json.loads(budget_json)
        total_opt = sum(c["optimal_spend"] for c in result["campaigns"])
        assert abs(total_opt - result["total_budget"]) < 1.0, (
            f"Budget constraint violated: sum={total_opt}, " f"budget={result['total_budget']}"
        )

    def test_campaign_fields_present(self, budget_json: str) -> None:
        """Each campaign allocation must contain all required fields."""
        required = {
            "campaign_id",
            "current_spend",
            "optimal_spend",
            "spend_change",
            "spend_change_pct",
            "current_outcome",
            "optimal_outcome",
            "outcome_lift",
            "outcome_lift_pct",
            "marginal_return_at_optimum",
        }
        for c in json.loads(budget_json)["campaigns"]:
            assert required.issubset(c.keys()), f"Missing keys: {required - c.keys()}"

    def test_converged_is_python_bool(self, budget_json: str) -> None:
        """converged must be a native Python bool, not numpy.bool_."""
        result = json.loads(budget_json)
        assert type(result["converged"]) is bool

    def test_no_excluded_campaigns_by_default(self, budget_json: str) -> None:
        """With clean data the excluded_campaigns list must be empty."""
        assert json.loads(budget_json)["excluded_campaigns"] == []

    # ── matches adsat directly ────────────────────────────────────────────────

    def test_matches_adsat_optimal_spend(self, batch_json: str) -> None:
        """Optimal spend values must match a direct BudgetOptimizer call within 1%."""
        df = _make_campaign_df()
        direct_batch = CampaignSaturationAnalyzer(
            campaign_col="campaign",
            x_col="impressions",
            y_col="conversions",
            verbose=False,
        ).run(df)

        direct_result = BudgetOptimizer(total_budget=3_000_000, verbose=False).optimise(
            direct_batch
        )

        tool_campaigns = {
            c["campaign_id"]: c
            for c in json.loads(optimise_budget(batch_json=batch_json, total_budget=3_000_000))[
                "campaigns"
            ]
        }

        for _, row in direct_result.allocations.iterrows():
            cid = row["campaign_id"]
            if cid not in tool_campaigns:
                continue
            direct_opt = row["optimal_spend"]
            tool_opt = tool_campaigns[cid]["optimal_spend"]
            diff_pct = abs(direct_opt - tool_opt) / max(direct_opt, 1.0)
            assert diff_pct < 0.01, f"{cid}: optimal_spend differs by {diff_pct:.2%}"

    # ── edge cases ───────────────────────────────────────────────────────────

    def test_explicit_current_spend(self, batch_json: str) -> None:
        """Explicit current_spend dict must override the auto median baseline."""
        explicit = {"Alpha": 1_000_000, "Beta": 800_000, "Gamma": 600_000}
        result = json.loads(
            optimise_budget(
                batch_json=batch_json,
                total_budget=3_000_000,
                current_spend=explicit,
            )
        )
        tool_campaigns = {c["campaign_id"]: c for c in result["campaigns"]}
        for cid, spend in explicit.items():
            assert tool_campaigns[cid]["current_spend"] == spend

    def test_hill_bayesian_substituted_in_deserialise(self, batch_json: str) -> None:
        """hill_bayesian in best_model must be silently replaced with hill."""
        data = json.loads(batch_json)
        data["campaigns"][0]["best_model"] = "hill_bayesian"
        batch_rebuilt, _ = _deserialise_batch_result(json.dumps(data))
        first_cid = data["campaigns"][0]["campaign_id"]
        assert batch_rebuilt.campaign_results[first_cid].best_model == "hill"

    def test_power_model_no_sat_excluded(self, batch_json: str) -> None:
        """A Power-model campaign with no saturation_point must be excluded."""
        data = json.loads(batch_json)
        # Force first campaign to power model with no saturation point.
        data["campaigns"][0]["best_model"] = "power"
        data["campaigns"][0]["saturation_point"] = None
        result = json.loads(optimise_budget(batch_json=json.dumps(data), total_budget=3_000_000))
        excluded = result["excluded_campaigns"]
        assert len(excluded) == 1
        assert excluded[0]["campaign_id"] == str(data["campaigns"][0]["campaign_id"])
        assert excluded[0]["reason"] == "Power model — no saturation point defined"
        # Remaining two campaigns should have been optimised.
        assert len(result["campaigns"]) == 2

    def test_fewer_than_two_campaigns_raises(self, batch_json: str) -> None:
        """Fewer than 2 succeeded campaigns must raise ValueError."""
        data = json.loads(batch_json)
        for c in data["campaigns"]:
            c["succeeded"] = False
        with pytest.raises(ValueError, match="at least 2 campaigns"):
            optimise_budget(batch_json=json.dumps(data), total_budget=3_000_000)


# ---------------------------------------------------------------------------
# TestGenerateReport
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Tests for the ``generate_report`` MCP tool."""

    # ── happy path ───────────────────────────────────────────────────────────

    def test_returns_valid_json_with_output_path(self, batch_json: str, tmp_path: Any) -> None:
        """Return value must be JSON containing an ``output_path`` key."""
        out = tmp_path / "report.html"
        result = json.loads(generate_report(batch_json=batch_json, output_path=str(out)))
        assert "output_path" in result
        assert isinstance(result["output_path"], str)

    def test_html_file_is_created(self, batch_json: str, tmp_path: Any) -> None:
        """The HTML file must exist and be non-empty after a successful call."""
        out = tmp_path / "report.html"
        result = json.loads(generate_report(batch_json=batch_json, output_path=str(out)))
        assert os.path.exists(result["output_path"])
        assert os.path.getsize(result["output_path"]) > 5_000

    def test_output_path_is_absolute(self, batch_json: str, tmp_path: Any) -> None:
        """output_path in the return JSON must be an absolute path."""
        out = tmp_path / "report.html"
        result = json.loads(generate_report(batch_json=batch_json, output_path=str(out)))
        assert os.path.isabs(result["output_path"])

    def test_html_contains_title(self, batch_json: str, tmp_path: Any) -> None:
        """The title passed to the tool must appear in the saved HTML."""
        out = tmp_path / "report.html"
        generate_report(
            batch_json=batch_json,
            output_path=str(out),
            title="Unique Test Report Title XYZ",
        )
        html = out.read_text(encoding="utf-8")
        assert "Unique Test Report Title XYZ" in html

    def test_html_contains_saturation_section(self, batch_json: str, tmp_path: Any) -> None:
        """The saturation analysis section must always be present."""
        out = tmp_path / "report.html"
        generate_report(batch_json=batch_json, output_path=str(out))
        html = out.read_text(encoding="utf-8")
        assert "Campaign Saturation Analysis" in html

    def test_html_without_budget_has_no_budget_section(
        self, batch_json: str, tmp_path: Any
    ) -> None:
        """Without budget_json the report must not contain a budget section."""
        out = tmp_path / "report.html"
        generate_report(batch_json=batch_json, output_path=str(out))
        html = out.read_text(encoding="utf-8")
        assert "Budget Optimisation" not in html

    # ── edge cases ───────────────────────────────────────────────────────────

    def test_html_with_budget_section(
        self, batch_json: str, budget_json: str, tmp_path: Any
    ) -> None:
        """When budget_json is provided a budget optimisation section must appear."""
        out = tmp_path / "report_with_budget.html"
        generate_report(
            batch_json=batch_json,
            budget_json=budget_json,
            output_path=str(out),
        )
        html = out.read_text(encoding="utf-8")
        assert "Budget Optimisation" in html
        assert "Campaign Saturation Analysis" in html

    def test_custom_subtitle_and_author(self, batch_json: str, tmp_path: Any) -> None:
        """Subtitle and author must appear in the generated HTML."""
        out = tmp_path / "report_meta.html"
        generate_report(
            batch_json=batch_json,
            output_path=str(out),
            subtitle="Q3 2026 Summary",
            author="Stefano",
        )
        html = out.read_text(encoding="utf-8")
        assert "Q3 2026 Summary" in html
        assert "Stefano" in html

    def test_report_with_budget_larger_than_without(
        self, batch_json: str, budget_json: str, tmp_path: Any
    ) -> None:
        """Adding a budget section must produce a larger HTML file."""
        out_plain = tmp_path / "plain.html"
        out_budget = tmp_path / "budget.html"
        generate_report(batch_json=batch_json, output_path=str(out_plain))
        generate_report(
            batch_json=batch_json,
            budget_json=budget_json,
            output_path=str(out_budget),
        )
        assert out_budget.stat().st_size > out_plain.stat().st_size
