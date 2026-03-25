# Changelog

All notable changes to **analytics-agents** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Planned
- Exploratory / EDA Agent (`run_exploratory_analysis`)
- Model Diagnostics Agent (`run_model_diagnostics`)
- Seasonality Agent (`decompose_seasonality`)
- Scenario Simulation Agent (`run_scenario_simulation`)
- Attribution Agent (`run_attribution`)
- Benchmarking Agent (`benchmark_campaigns`)
- LangGraph orchestration layer in `orchestration/` module (evaluated at second agent build)
- `analytics-agents install-skills` CLI for SKILL.md distribution (requires `platformdirs`)
- Move `skills/` inside `agents/` package and add `[tool.setuptools.package-data]` when CLI is built

---

## [0.1.0] – 2026-03-25

### Added
- `analyse_campaign_saturation` — fits Hill, Exponential, Power, Michaelis-Menten, and
  Logistic saturation curves per campaign; returns saturation status, R², best model,
  saturation point, and optional response curves as JSON
- `optimise_budget` — SLSQP constrained budget optimisation across campaigns; takes JSON
  from `analyse_campaign_saturation` and returns optimal spend allocation and outcome lift
- `generate_report` — self-contained HTML report with all charts embedded as base64 PNG;
  optionally includes budget optimisation section
- Pass-through JSON serialisation layer — tools chain via JSON strings, no intermediate files
- `_NumpyEncoder` and `_safe()` helpers for numpy scalar and NaN serialisation
- `_deserialise_batch_result()` — reconstructs `CampaignBatchResult` from JSON; applies
  `hill_bayesian → hill` substitution and excludes Power model campaigns with no saturation point
- `_deserialise_budget_allocation()` — reconstructs `BudgetAllocation` from JSON
- `skills/campaign-analysis/SKILL.md` — orchestration instructions for Claude-based clients
- 33 tests across three test classes, 90% coverage
- CI workflow: ruff, black, pytest (Python 3.9–3.13 × Ubuntu / Windows / macOS)
- PyPI publish workflow: tag-triggered OIDC trusted publishing
