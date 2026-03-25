"""Analytics Agents — End-to-End Smoke Test
============================================
Exercises the full Campaign Saturation Agent tool chain:

    analyse_campaign_saturation → optimise_budget → generate_report

Calls tool functions directly (Python import, no MCP transport). Produces a
real HTML report at ``reports/smoke_test_report.html`` relative to this script.

Usage
-----
::

    python run_end_to_end.py

Exit codes
----------
- 0  all steps completed successfully
- 1  any step raised an exception

Claude Desktop configuration
-----------------------------
To connect this server to Claude Desktop, add the following entry to
``~/Library/Application Support/Claude/claude_desktop_config.json``::

    {
      "mcpServers": {
        "analytics-agents": {
          "command": "/Users/stefano/adsat_environment/bin/python3",
          "args": ["/Users/stefano/Analytics_projects/analytics-agents/server.py"]
        }
      }
    }

Restart Claude Desktop after editing the config. The three tools
(analyse_campaign_saturation, optimise_budget, generate_report) will appear
in the tool list.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup — allow running from the repo root without installing the package
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from agents.campaign_analyst import (
    analyse_campaign_saturation,
    generate_report,
    optimise_budget,
)

DIVIDER = "=" * 70
SECTION = "-" * 70
TOTAL_BUDGET = 500_000.0
REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
REPORT_PATH = os.path.join(REPORT_DIR, "smoke_test_report.html")


# ---------------------------------------------------------------------------
# Synthetic dataset (deterministic, same seed as test suite)
# ---------------------------------------------------------------------------


def _build_dataset() -> pd.DataFrame:
    """Generate a 3-campaign × 60-row synthetic dataset.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: campaign_id, impressions, conversions.
    """
    np.random.seed(42)
    records = []
    campaigns = {
        "Alpha": (50_000, 1_500_000, 2.0, 600, 400_000, 2_800_000),
        "Beta": (18_000, 2_800_000, 1.8, 200, 150_000, 900_000),
        "Gamma": (6_000, 200_000, 1.5, 100, 80_000, 600_000),
    }
    for name, (a, k, n_hill, noise, imp_start, imp_end) in campaigns.items():
        x = np.linspace(imp_start, imp_end, 60)
        x += np.random.normal(0, imp_start * 0.04, 60)
        x = np.maximum(x, 1_000)
        y_true = a * (x**n_hill) / (k**n_hill + x**n_hill)
        y = np.maximum(y_true + np.random.normal(0, noise, 60), 0).round(0)
        for xi, yi in zip(x, y):
            records.append(
                {"campaign_id": name, "impressions": float(xi), "conversions": float(yi)}
            )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def _ok(msg: str) -> None:
    print(f"  [OK]  {msg}")


def _info(label: str, value: object) -> None:
    print(f"  {label:<35s} {value}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the end-to-end smoke test."""
    csv_path: str | None = None

    try:
        # ------------------------------------------------------------------
        # STEP 1 — Write synthetic CSV to a temp file
        # ------------------------------------------------------------------
        _section("STEP 1 — Build synthetic dataset and write CSV")
        df = _build_dataset()
        _info("Campaigns:", df["campaign_id"].unique().tolist())
        _info("Rows:", len(df))
        _info("Columns:", list(df.columns))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, prefix="smoke_test_"
        ) as fh:
            df.to_csv(fh, index=False)
            csv_path = fh.name

        _ok(f"CSV written to {csv_path}")

        # ------------------------------------------------------------------
        # STEP 2 — analyse_campaign_saturation
        # ------------------------------------------------------------------
        _section("STEP 2 — analyse_campaign_saturation")
        batch_json = analyse_campaign_saturation(
            csv_path=csv_path,
            x_col="impressions",
            y_col="conversions",
            campaign_col="campaign_id",
            include_response_curves=False,
        )

        batch_data = json.loads(batch_json)
        meta = batch_data["metadata"]
        _info("n_total:", meta["n_total"])
        _info("n_succeeded:", meta["n_succeeded"])
        _info("n_failed:", meta["n_failed"])

        print()
        print(
            f"  {'Campaign':<12} {'Model':<22} {'Saturation point':>18}"
            f" {'% reached':>10} {'Status':<14} {'R²':>6}"
        )
        print(f"  {SECTION}")
        for c in batch_data["campaigns"]:
            sat_pt = c["saturation_point"]
            pct = c["pct_of_saturation"]
            r2 = c["r2"]
            sat_str = f"{sat_pt:>18,.0f}" if sat_pt is not None else f"{'N/A':>18}"
            pct_str = f"{pct:.1f}%" if pct is not None else "N/A"
            r2_str = f"{r2:.3f}" if r2 is not None else "N/A"
            print(
                f"  {str(c['campaign_id']):<12} "
                f"{str(c['best_model']):<22} "
                f"{sat_str} "
                f"{pct_str:>10} "
                f"{str(c['saturation_status']):<14} "
                f"{r2_str:>6}"
            )

        _ok("analyse_campaign_saturation returned valid JSON")

        # ------------------------------------------------------------------
        # STEP 3 — optimise_budget
        # ------------------------------------------------------------------
        _section(f"STEP 3 — optimise_budget  (total_budget={TOTAL_BUDGET:,.0f})")
        budget_json = optimise_budget(
            batch_json=batch_json,
            total_budget=TOTAL_BUDGET,
        )

        budget_data = json.loads(budget_json)
        _info("Total budget:", f"{budget_data['total_budget']:>12,.0f}")
        _info("Current outcome:", f"{budget_data['total_current_outcome']:>12,.1f}")
        _info("Optimal outcome:", f"{budget_data['total_optimal_outcome']:>12,.1f}")
        _info(
            "Outcome lift:",
            f"{budget_data['total_outcome_lift']:>12,.1f}"
            f"  ({budget_data['total_outcome_lift_pct']:.1f}%)",
        )
        _info("Converged:", budget_data["converged"])

        if budget_data["excluded_campaigns"]:
            print("\n  Excluded campaigns:")
            for exc in budget_data["excluded_campaigns"]:
                print(f"    - {exc['campaign_id']}: {exc['reason']}")

        print()
        print(
            f"  {'Campaign':<12} {'Current spend':>14} {'Optimal spend':>14}"
            f" {'Change':>10} {'Outcome lift':>14}"
        )
        print(f"  {SECTION}")
        for row in budget_data["campaigns"]:
            print(
                f"  {str(row['campaign_id']):<12} "
                f"{row['current_spend']:>14,.0f} "
                f"{row['optimal_spend']:>14,.0f} "
                f"{row['spend_change_pct']:>+9.1f}% "
                f"{row['outcome_lift_pct']:>+13.1f}%"
            )

        _ok("optimise_budget returned valid JSON")

        # ------------------------------------------------------------------
        # STEP 4 — generate_report
        # ------------------------------------------------------------------
        _section("STEP 4 — generate_report")
        os.makedirs(REPORT_DIR, exist_ok=True)
        report_json = generate_report(
            batch_json=batch_json,
            output_path=REPORT_PATH,
            budget_json=budget_json,
            title="Smoke Test — Campaign Saturation Report",
            subtitle="Analytics Agents v0.1.0",
            author="Smoke Test",
        )

        report_data = json.loads(report_json)
        abs_report_path = report_data["output_path"]
        file_size_kb = os.path.getsize(abs_report_path) / 1024

        _info("Report saved to:", abs_report_path)
        _info("File size:", f"{file_size_kb:.1f} KB")
        assert os.path.isfile(abs_report_path), "Report file not found after save"
        assert file_size_kb > 10, f"Report suspiciously small: {file_size_kb:.1f} KB"
        _ok("generate_report produced a valid HTML file")

        # ------------------------------------------------------------------
        # Done
        # ------------------------------------------------------------------
        _section("SMOKE TEST PASSED — all steps completed successfully")
        print()
        sys.exit(0)

    except Exception as exc:  # noqa: BLE001
        print(f"\n  [FAIL]  {type(exc).__name__}: {exc}")
        sys.exit(1)

    finally:
        if csv_path and os.path.exists(csv_path):
            os.unlink(csv_path)


if __name__ == "__main__":
    main()
