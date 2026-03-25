"""Campaign Saturation Agent — tool implementations.

Wraps adsat's campaign saturation, budget optimisation, and report generation
functions as MCP-callable tool functions. All analytical logic lives in adsat;
this module owns only the tool interface and result serialisation.

Tools defined here
------------------
- ``analyse_campaign_saturation`` : fit saturation curves per campaign
- ``optimise_budget``             : allocate budget across campaigns
- ``generate_report``             : produce a self-contained HTML report (Phase 3)
"""

from __future__ import annotations

import json
from typing import Any, Optional

import numpy as np
import pandas as pd
from adsat.budget import BudgetAllocation, BudgetOptimizer
from adsat.campaign import (
    CampaignBatchResult,
    CampaignResult,
    CampaignSaturationAnalyzer,
)
from adsat.report import ReportBuilder
from adsat.response_curves import ResponseCurveAnalyzer

# Synthetic campaign identifier used when the user provides no campaign column.
_SINGLE_CAMPAIGN_LABEL = "__single_campaign__"


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------


class _NumpyEncoder(json.JSONEncoder):
    """Extend the default JSON encoder to handle numpy scalars and NaN values.

    Parameters
    ----------
    *args, **kwargs
        Passed through to ``json.JSONEncoder``.
    """

    def default(self, obj: Any) -> Any:  # noqa: ANN401
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return None if np.isnan(obj) else float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _safe(val: Any) -> Any:
    """Convert a value to a JSON-safe Python type.

    Replaces ``float('nan')`` / ``np.nan`` with ``None`` and coerces numpy
    scalar types to their plain Python equivalents.

    Parameters
    ----------
    val : any
        Raw value from an adsat result dict.

    Returns
    -------
    any
        JSON-serialisable value.
    """
    if isinstance(val, np.bool_):
        return bool(val)
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, np.integer):
        return int(val)
    if isinstance(val, np.floating):
        return None if np.isnan(val) else float(val)
    return val


def _sanitise_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Apply ``_safe`` to every value in a flat dictionary.

    Parameters
    ----------
    d : dict
        Flat dictionary whose values may contain numpy scalars or NaN.

    Returns
    -------
    dict
        New dictionary with all values converted to JSON-safe types.
    """
    return {k: _safe(v) for k, v in d.items()}


# ---------------------------------------------------------------------------
# Tool: analyse_campaign_saturation
# ---------------------------------------------------------------------------


def analyse_campaign_saturation(
    csv_path: str,
    x_col: str,
    y_col: str,
    campaign_col: Optional[str] = None,
    include_response_curves: bool = False,
    exclude_campaigns: Optional[list[str]] = None,
) -> str:
    """Fit saturation curves across one or more campaigns and return results.

    Loads the CSV at *csv_path*, runs ``CampaignSaturationAnalyzer`` across
    every unique campaign in *campaign_col* (or treats the whole dataset as a
    single campaign when *campaign_col* is ``None``), and returns a JSON string
    containing the serialised results.

    Optionally wraps ``ResponseCurveAnalyzer`` when *include_response_curves*
    is ``True``.

    Parameters
    ----------
    csv_path : str
        Absolute or relative path to the CSV file containing campaign data.
    x_col : str
        Column name for the input variable (spend or impressions).
    y_col : str
        Column name for the outcome variable (conversions, revenue, clicks).
    campaign_col : str, optional
        Column name that identifies each campaign. When ``None`` the entire
        dataset is analysed as a single campaign labelled ``"all"``.
    include_response_curves : bool, optional
        Whether to run ``ResponseCurveAnalyzer`` for each campaign. Default
        ``False``.
    exclude_campaigns : list[str], optional
        Campaign IDs to exclude before fitting. Default ``None`` (no
        exclusions).

    Returns
    -------
    str
        JSON string with the following structure::

            {
              "metadata": {
                "campaign_col": str | null,
                "x_col": str,
                "y_col": str,
                "n_total": int,
                "n_succeeded": int,
                "n_failed": int,
                "include_response_curves": bool
              },
              "campaigns": [
                {
                  "campaign_id": any,
                  "n_observations": int,
                  "best_model": str | null,
                  "saturation_point": float | null,
                  "saturation_y": float | null,
                  "current_x_median": float | null,
                  "pct_of_saturation": float | null,
                  "saturation_status": str,
                  "r2": float | null,
                  "rmse": float | null,
                  "aic": float | null,
                  "converged": bool | null,
                  "succeeded": bool,
                  "error": str | null,
                  "best_model_params": dict | null,
                  "response_curve": dict | null
                }
              ]
            }

    Raises
    ------
    FileNotFoundError
        If *csv_path* does not point to an existing file.
    ValueError
        If required columns (*x_col*, *y_col*, or *campaign_col* when
        provided) are absent from the CSV, or if no rows remain after
        applying *exclude_campaigns*.
    """
    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"CSV file not found: {csv_path!r}. Please check the path and try again."
        )

    # ------------------------------------------------------------------
    # 2. Handle single-campaign mode
    # ------------------------------------------------------------------
    single_mode = campaign_col is None
    if single_mode:
        df = df.copy()
        df[_SINGLE_CAMPAIGN_LABEL] = _SINGLE_CAMPAIGN_LABEL
        effective_campaign_col = _SINGLE_CAMPAIGN_LABEL
    else:
        effective_campaign_col = campaign_col

    # ------------------------------------------------------------------
    # 3. Validate required columns
    # ------------------------------------------------------------------
    required = [effective_campaign_col, x_col, y_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"The following columns were not found in the CSV: {missing}.\n"
            f"Available columns: {list(df.columns)}"
        )

    # ------------------------------------------------------------------
    # 4. Apply campaign exclusions
    # ------------------------------------------------------------------
    if exclude_campaigns:
        df = df[~df[effective_campaign_col].isin(exclude_campaigns)].copy()
        if df.empty:
            raise ValueError(f"No rows remain after excluding campaigns: {exclude_campaigns}.")

    # ------------------------------------------------------------------
    # 5. Run saturation analysis
    # ------------------------------------------------------------------
    analyzer = CampaignSaturationAnalyzer(
        campaign_col=effective_campaign_col,
        x_col=x_col,
        y_col=y_col,
        verbose=False,
    )
    batch = analyzer.run(df)

    # ------------------------------------------------------------------
    # 6. Optionally run response curve analysis
    # ------------------------------------------------------------------
    rc_results: dict[Any, Any] = {}
    if include_response_curves:
        rc_analyzer = ResponseCurveAnalyzer(verbose=False)
        rc_results = rc_analyzer.analyse(batch)

    # ------------------------------------------------------------------
    # 7. Build output
    # ------------------------------------------------------------------
    campaigns_out = []
    for cid, cr in batch.campaign_results.items():
        row = _sanitise_dict(cr.as_dict())

        # Surface converged flag from the underlying ModelFitResult.
        converged: Optional[bool] = None
        if cr.succeeded and cr.pipeline_result is not None and cr.best_model is not None:
            model_fit = cr.pipeline_result.model_results.get(cr.best_model)
            if model_fit is not None:
                converged = bool(model_fit.converged)
        row["converged"] = converged

        # Include best_model_params so the serialisation layer (Step 9) can
        # reconstruct a CampaignBatchResult for budget optimisation.
        if cr.best_model_params is not None:
            row["best_model_params"] = _sanitise_dict(cr.best_model_params)
        else:
            row["best_model_params"] = None

        # Include response curve summary when requested.
        if include_response_curves:
            if cid in rc_results:
                rc_summary = _sanitise_dict(rc_results[cid].summary_row())
                # Remove keys already present in the parent row.
                for key in ("campaign_id", "saturation_point"):
                    rc_summary.pop(key, None)
                row["response_curve"] = rc_summary
            else:
                row["response_curve"] = None

        # In single-campaign mode replace the synthetic ID with "all".
        if single_mode:
            row["campaign_id"] = "all"

        campaigns_out.append(row)

    result: dict[str, Any] = {
        "metadata": {
            "campaign_col": campaign_col,
            "x_col": x_col,
            "y_col": y_col,
            "n_total": batch.n_total,
            "n_succeeded": batch.n_succeeded,
            "n_failed": batch.n_failed,
            "include_response_curves": include_response_curves,
        },
        "campaigns": campaigns_out,
    }

    return json.dumps(result, cls=_NumpyEncoder)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _deserialise_batch_result(
    json_str: str,
) -> tuple[CampaignBatchResult, list[dict[str, str]]]:
    """Reconstruct a ``CampaignBatchResult`` from the JSON returned by
    ``analyse_campaign_saturation``.

    Also returns a list of campaigns excluded before optimisation, each as a
    dict with ``campaign_id`` and ``reason`` keys.

    Parameters
    ----------
    json_str : str
        JSON string produced by ``analyse_campaign_saturation``.

    Returns
    -------
    tuple[CampaignBatchResult, list[dict[str, str]]]
        Reconstructed batch result and list of excluded campaign dicts.

    Notes
    -----
    - ``hill_bayesian`` is substituted with ``hill`` in ``best_model`` to
      avoid a ``KeyError`` in ``MODEL_REGISTRY`` (documented adsat fix).
    - Campaigns where ``best_model == "power"`` and ``saturation_point`` is
      ``None`` are marked ``succeeded=False`` and added to the exclusions
      list, preventing ``BudgetOptimizer`` from using an uncapped upper bound.
    """
    data = json.loads(json_str)
    meta = data["metadata"]
    x_col: str = meta["x_col"]
    y_col: str = meta["y_col"]
    campaign_col: str = meta["campaign_col"] or _SINGLE_CAMPAIGN_LABEL

    excluded: list[dict[str, str]] = []
    campaign_results: dict[Any, CampaignResult] = {}

    for c in data["campaigns"]:
        cid: Any = c["campaign_id"]

        # Defensive fix: hill_bayesian is not in MODEL_REGISTRY — use hill.
        best_model: Optional[str] = c.get("best_model")
        if best_model == "hill_bayesian":
            best_model = "hill"

        # Exclude Power model campaigns with no saturation point — the
        # optimiser would otherwise use total_budget as the upper bound,
        # producing an unconstrained and meaningless allocation.
        power_no_sat = best_model == "power" and c.get("saturation_point") is None
        if power_no_sat:
            excluded.append(
                {
                    "campaign_id": str(cid),
                    "reason": "Power model — no saturation point defined",
                }
            )

        cr = CampaignResult(
            campaign_id=cid,
            n_observations=c.get("n_observations", 0),
            x_col=x_col,
            y_col=y_col,
            best_model=best_model,
            saturation_point=c.get("saturation_point"),
            saturation_y=c.get("saturation_y"),
            saturation_threshold=0.90,
            r2=c.get("r2"),
            rmse=c.get("rmse"),
            aic=c.get("aic"),
            best_model_params=c.get("best_model_params"),
            current_x_median=c.get("current_x_median"),
            pct_of_saturation=None,  # recomputed by CampaignResult.__post_init__
            succeeded=False if power_no_sat else c.get("succeeded", False),
            error=("Power model — no saturation point defined" if power_no_sat else c.get("error")),
        )
        campaign_results[cid] = cr

    summary_table = pd.DataFrame([cr.as_dict() for cr in campaign_results.values()])
    n_succeeded = sum(1 for cr in campaign_results.values() if cr.succeeded)

    batch = CampaignBatchResult(
        campaign_col=campaign_col,
        x_col=x_col,
        y_col=y_col,
        campaign_results=campaign_results,
        summary_table=summary_table,
        n_total=meta["n_total"],
        n_succeeded=n_succeeded,
        n_failed=meta["n_total"] - n_succeeded,
    )
    return batch, excluded


# ---------------------------------------------------------------------------
# Tool: optimise_budget
# ---------------------------------------------------------------------------


def optimise_budget(
    batch_json: str,
    total_budget: float,
    current_spend: Optional[dict[str, float]] = None,
) -> str:
    """Allocate a fixed budget across campaigns to maximise total outcome.

    Deserialises the ``CampaignBatchResult`` from *batch_json* (the JSON
    string returned by ``analyse_campaign_saturation``), then runs
    ``BudgetOptimizer`` using SLSQP constrained optimisation.

    Parameters
    ----------
    batch_json : str
        JSON string returned by a prior call to ``analyse_campaign_saturation``.
    total_budget : float
        Total spend budget to distribute across all eligible campaigns.
    current_spend : dict[str, float], optional
        Current spend per campaign used as the comparison baseline.
        Keys must match the campaign IDs in *batch_json*.
        When ``None``, each campaign's ``current_x_median`` is used.

    Returns
    -------
    str
        JSON string with the following structure::

            {
              "total_budget": float,
              "total_current_outcome": float,
              "total_optimal_outcome": float,
              "total_outcome_lift": float,
              "total_outcome_lift_pct": float,
              "converged": bool,
              "notes": str,
              "campaigns": [
                {
                  "campaign_id": any,
                  "current_spend": float,
                  "optimal_spend": float,
                  "spend_change": float,
                  "spend_change_pct": float,
                  "current_outcome": float,
                  "optimal_outcome": float,
                  "outcome_lift": float,
                  "outcome_lift_pct": float,
                  "pct_of_saturation_before": float | null,
                  "pct_of_saturation_after": float | null,
                  "marginal_return_at_optimum": float
                }
              ],
              "excluded_campaigns": [
                {"campaign_id": str, "reason": str}
              ]
            }

    Raises
    ------
    ValueError
        If *batch_json* contains fewer than 2 eligible campaigns after
        exclusions, or if *total_budget* is not positive.
    """
    batch, excluded = _deserialise_batch_result(batch_json)

    usable = batch.succeeded_campaigns()
    if len(usable) < 2:
        excluded_ids = [e["campaign_id"] for e in excluded]
        raise ValueError(
            f"Budget optimisation requires at least 2 campaigns with fitted models. "
            f"Got {len(usable)} usable campaign(s) after exclusions. "
            f"Excluded campaigns: {excluded_ids}"
        )

    optimizer = BudgetOptimizer(total_budget=float(total_budget), verbose=False)
    allocation = optimizer.optimise(batch, current_spend=current_spend)

    campaigns_out = [_sanitise_dict(row.to_dict()) for _, row in allocation.allocations.iterrows()]

    result: dict[str, Any] = {
        "total_budget": allocation.total_budget,
        "total_current_outcome": allocation.total_current_outcome,
        "total_optimal_outcome": allocation.total_optimal_outcome,
        "total_outcome_lift": allocation.total_outcome_lift,
        "total_outcome_lift_pct": allocation.total_outcome_lift_pct,
        "converged": allocation.converged,
        "notes": allocation.notes,
        "campaigns": campaigns_out,
        "excluded_campaigns": excluded,
    }

    return json.dumps(result, cls=_NumpyEncoder)


# ---------------------------------------------------------------------------
# Budget allocation deserialisation helper
# ---------------------------------------------------------------------------


def _deserialise_budget_allocation(json_str: str) -> BudgetAllocation:
    """Reconstruct a ``BudgetAllocation`` from the JSON returned by
    ``optimise_budget``.

    Parameters
    ----------
    json_str : str
        JSON string produced by ``optimise_budget``.

    Returns
    -------
    BudgetAllocation
        Reconstructed result with ``allocations`` as a DataFrame, ready to
        pass to ``ReportBuilder.add_budget_allocation()``.
    """
    data = json.loads(json_str)
    allocations = pd.DataFrame(data["campaigns"])
    return BudgetAllocation(
        total_budget=float(data["total_budget"]),
        allocations=allocations,
        total_current_outcome=float(data["total_current_outcome"]),
        total_optimal_outcome=float(data["total_optimal_outcome"]),
        total_outcome_lift=float(data["total_outcome_lift"]),
        total_outcome_lift_pct=float(data["total_outcome_lift_pct"]),
        converged=bool(data["converged"]),
        notes=data.get("notes", ""),
    )


# ---------------------------------------------------------------------------
# Tool: generate_report
# ---------------------------------------------------------------------------


def generate_report(
    batch_json: str,
    output_path: str,
    budget_json: Optional[str] = None,
    title: str = "Advertising Saturation Report",
    subtitle: str = "",
    author: str = "",
) -> str:
    """Generate a self-contained HTML report from saturation and budget results.

    Deserialises the results from *batch_json* (and optionally *budget_json*),
    builds a ``ReportBuilder`` with all available sections, and saves the
    report to *output_path*.

    Parameters
    ----------
    batch_json : str
        JSON string returned by ``analyse_campaign_saturation``. Required.
    output_path : str
        File path where the HTML report will be saved (e.g.
        ``"reports/q3_analysis.html"``). Relative paths are resolved against
        the current working directory.
    budget_json : str, optional
        JSON string returned by ``optimise_budget``. When provided, a budget
        optimisation section is appended to the report.
    title : str, optional
        Report title shown in the HTML header. Default
        ``"Advertising Saturation Report"``.
    subtitle : str, optional
        Optional subtitle line below the main title.
    author : str, optional
        Author name shown in the report header and footer.

    Returns
    -------
    str
        JSON string ``{"output_path": "<absolute path to saved HTML file>"}``.

    Raises
    ------
    ValueError
        If *batch_json* cannot be deserialised or contains no campaigns.
    OSError
        If the directory containing *output_path* does not exist or is not
        writable.
    """
    batch, _ = _deserialise_batch_result(batch_json)

    builder = ReportBuilder(title=title, subtitle=subtitle, author=author)
    builder.add_campaign_batch(batch)

    if budget_json is not None:
        budget_allocation = _deserialise_budget_allocation(budget_json)
        builder.add_budget_allocation(budget_allocation)

    abs_path = builder.save(output_path, open_browser=False)

    return json.dumps({"output_path": abs_path})
