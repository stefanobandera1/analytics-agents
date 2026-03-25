# Analytics Agents — Shared Context

This file applies to everything under `analytics-agents/` and must be read at the start
of every session before writing any code, creating any file, or making any structural change.

---

## What this project is

`analytics-agents` is the orchestration layer that sits **above** individual analytics
packages (starting with `adsat`). Its purpose is to expose Python analytics functions
as **MCP (Model Context Protocol) tools** so that any MCP-compatible client — Claude
Desktop, Cowork, Claude Code — can invoke them conversationally.

A user should be able to say: _"Here is a dataset. Analyse this campaign and give me
results split by region."_ — and an agent will know which functions to call, in what
order, and how to present the results.

This folder does **not** own any analytical logic. All computation lives in the
underlying packages (`adsat`, and future packages). This folder owns:
- The MCP server that wraps those packages as tools
- The SKILL.md files that define how agents orchestrate those tools
- The evaluation suite that monitors agent accuracy and reliability over time

---

## Folder structure

```
analytics-agents/
├── CLAUDE.md              ← this file; read before every session
├── server.py              ← MCP server entry point; exposes tools to MCP clients
├── agents/                ← one Python module per agent
│   ├── campaign_analyst.py
│   ├── exploratory_agent.py
│   ├── diagnostics_agent.py
│   ├── seasonality_agent.py
│   ├── simulation_agent.py
│   ├── attribution_agent.py
│   ├── benchmarking_agent.py
│   └── sql_agent.py
├── skills/                ← one SKILL.md per agent (orchestration instructions)
│   ├── campaign-analysis/
│   │   └── SKILL.md
│   ├── exploratory/
│   │   └── SKILL.md
│   ├── diagnostics/
│   │   └── SKILL.md
│   ├── seasonality/
│   │   └── SKILL.md
│   ├── simulation/
│   │   └── SKILL.md
│   ├── attribution/
│   │   └── SKILL.md
│   └── benchmarking/
│       └── SKILL.md
└── tests/
    ├── golden/            ← golden datasets with known correct outputs
    └── test_agents.py     ← eval suite: tool correctness + accuracy thresholds
```

---

## Relationship to adsat and future packages

- `analytics-agents` **imports** from `adsat` (and future packages) as pip dependencies
- Never modify `adsat` source from within this folder — raise the change in `adsat_package/`
- When a new analytics package is created, add it as a dependency in `pyproject.toml` here
  and expose its functions as new MCP tools in `server.py`
- Version pins go in `pyproject.toml` — never hardcode version strings in agent code

### Packages in scope (current and planned)

This table must be kept up to date. Every time a new package is created under
`Analytics_projects/`, it must be added here and its modules fully mapped to agents
before any agent work on that package begins.

| Package | Status | Domain | Agent coverage |
|---|---|---|---|
| `adsat` | v0.5.0, production-ready | Advertising saturation, attribution, benchmarking, budget optimisation | 15/15 modules covered |
| _(future CLV package)_ | planned | Customer analytics / CLV | not yet mapped |
| _(future pricing package)_ | planned | Pricing analytics | not yet mapped |
| _(future web analytics package)_ | planned | Web / product analytics | not yet mapped |

---

## Coverage rule — no module must be left without an agent

**Every Python module in every analytics package must be covered by at least one agent.**

This is a hard rule that applies permanently and grows with the project. The 7 agents
currently listed are a starting point, not a ceiling. As `adsat` adds new modules, and as
new packages are introduced (CLV, pricing, web analytics, and anything beyond), the agent
layer must grow in lockstep. There is no version of this project where a Python module
exists but has no agent that can reach it.

Specifically:
- When a **new module** is added to an existing package → propose and add a new agent or
  extend an existing one in the same session, before any other work continues
- When a **new analytics package** is introduced → map every one of its modules to an agent
  before writing any agent code for that package
- When an existing module is **split or renamed** → update the coverage map immediately
- When a module is **deprecated or removed** → remove or update the corresponding agent entry

An uncovered module is a critical gap: a capability exists in code but cannot be reached
conversationally. This must never be allowed to persist across sessions.

When starting a new session, cross-check the agent inventory against the current module list
in each package. If any module is uncovered, flag it immediately and propose a new agent or
an extension to an existing one before doing anything else.

---

## Runtime model

The MCP server runs as a **local process** on the user's machine. It is installed via pip
and started locally — there is no cloud hosting or REST API. MCP handles the communication
layer between the server and any MCP-compatible client (Claude Desktop, Cowork, Claude Code).

This applies to all agents, whether they wrap Python package functions or external tools.
The local runtime model is the starting point; if a specific agent requires remote execution
in the future, that decision must be flagged and confirmed before any implementation.

---

## Agent scope — Python packages and external tools

Agents are **not limited to wrapping Python analytics packages**. As the project grows,
agents will increasingly integrate external tools and services alongside or instead of
Python functions. This is expected and must be planned for from the start.

Examples of external integrations already anticipated:
- **SQL Agent** — connects to data warehouses or databases via a database connector MCP;
  translates natural language to SQL, executes queries, and feeds results to other agents
- **Future agents** — may call external APIs, read from dashboards, write to reporting
  platforms, or chain multiple external services

When building an agent that uses external tools:
- Document the external dependency clearly in the agent description in this file
- Add the connector or SDK to `pyproject.toml` and flag the addition for confirmation
- Ensure the tool contract in `server.py` handles both the Python and external layers cleanly
- Write tests that mock external calls so the eval suite remains deterministic

---

## LLM framework strategy

**Current approach: MCP SDK only — no additional LLM framework.**

For the Campaign Saturation Agent (the first agent), the MCP Python SDK is sufficient.
The tools are deterministic, the workflow is sequential, and Claude reading the SKILL.md
is a reliable orchestration layer for a single-agent run.

**Multi-agent orchestration (current approach):** All MCP tools from all agents are
registered on the same `server.py`. Claude can see all tools at once and chains them across
agents by reading the relevant SKILL.md files and calling tools in the right order. Simple
sequential hand-offs (e.g. SQL Agent → Campaign Saturation Agent → Budget Optimiser) are
handled this way without any framework. The SKILL.md "Handoff conditions" section in each
skill file is the inter-agent orchestration layer for these cases.

**LangGraph decision — introduce at the second agent, not deferred.**

Multi-agent workflows are not always linear in practice. Even a workflow that looks
sequential on paper (EDA → Saturation → Diagnostics → Budget) may require conditional
branching in real use: run diagnostics only if R² is below threshold; re-run saturation
on deseasonalised data if seasonality is detected; skip budget optimisation if no campaign
converged. Expressing that logic reliably in SKILL.md across multiple agents is fragile —
Claude can lose track of state, misread a condition, or skip a branch. That logic belongs
in code.

**Decision: LangGraph (or equivalent) will be evaluated and introduced when building the
second agent.** This does not mean every agent needs LangGraph — single-agent tools that
wrap deterministic functions remain MCP-only. It means the multi-agent orchestration layer
is built in code from the start, rather than retrofitted later when complexity has already
accumulated.

When LangGraph is introduced:
- It slots into the orchestration layer only — `server.py` and the MCP tool contracts
  remain unchanged for all agents
- Individual agent modules that wrap single deterministic tools do not change
- The graph definition lives in a dedicated `orchestration/` module, not inside any
  individual agent file
- Document the graph structure here and update this section before implementation

Rules:
- Do not add a framework without proposing the graph structure and getting explicit confirmation
- Do not add a framework just because it is familiar — justify it against the specific
  workflow being built
- When a framework is introduced, document it here and update the relevant agent descriptions
- If LangGraph proves unnecessary for the second agent's workflow, defer again but
  re-evaluate at each subsequent agent — do not drift back to assuming SKILL.md is sufficient

---

## Client-agnostic design goal

**The orchestration and quality layer must eventually be client-agnostic.** This is a
first-class design requirement, not a nice-to-have.

### What this means in practice

The MCP tools themselves are already client-agnostic — any MCP client can call them and get
correct results. The problem is everything around the tool calls: the question flow before a
run, the model quality gate (R², convergence, n) before presenting results, the guardrail
against using non-converged models for budget decisions, the conditional handoffs to other
agents. Today all of that logic lives in SKILL.md and is only executed when Claude is the
client. A Cursor, Continue, or Zed user calling the tools directly gets correct JSON back
but none of the workflow intelligence or safety checks.

### Why this matters

The quality gates are not cosmetic. A user who calls `optimise_budget` on a batch that
includes non-converged models gets a numerically plausible but unreliable allocation. The
SKILL.md guard against this is only active for Claude users. That is a correctness gap, not
just a UX gap.

### The fix — orchestration in code

When the `orchestration/` module is introduced (targeted at the second agent), the workflow
graph — quality gates, conditional branching, guardrails — moves from SKILL.md into Python.
The server then exposes composite tools (e.g. `run_saturation_pipeline`) that any client can
call and receive the same safeguards. SKILL.md is retained for Claude-specific presentation
(question flow, plain-language interpretation, narrative output) but stops being the only
place where correctness is enforced.

**Rule:** any logic that enforces a correctness guarantee (not just a UX preference) must
live in the `orchestration/` module, not solely in SKILL.md. When writing or reviewing a
SKILL.md, ask: "if a non-Claude client bypassed this instruction, would the output be wrong
or misleading?" If yes, that logic belongs in code.

---

## MCP server design (`server.py`)

`server.py` is the single entry point. It starts a local MCP server and registers tools.
Each tool wraps one or more adsat (or future package) functions, or connects to an
external tool or service where required.

**Tools — current status:**

| Tool name | Status | Wraps | Inputs | Output |
|---|---|---|---|---|
| `analyse_campaign_saturation` | ✓ built | `CampaignSaturationAnalyzer`, `ResponseCurveAnalyzer` | CSV path, x_col, y_col, campaign_col, include_response_curves, exclude_campaigns | JSON string — saturation status + optional response curves per campaign |
| `optimise_budget` | ✓ built | `BudgetOptimizer` | batch_json (from above), total_budget, current_spend | JSON string — optimal spend allocation + outcome lift + excluded_campaigns |
| `generate_report` | ✓ built | `ReportBuilder` | batch_json, output_path, budget_json (optional), title, subtitle, author | JSON string — `{"output_path": "<abs path>"}` |
| `run_exploratory_analysis` | planned | `CampaignExplorer` | CSV path, x_col, y_col, group_col | EDA plots + descriptive summary |
| `run_model_diagnostics` | planned | `ModelDiagnostics` | pipeline result or campaign result | 6-panel residual diagnostic report |
| `decompose_seasonality` | planned | `SeasonalDecomposer` | CSV path, y_col, period, model | Trend + seasonal + residual decomposition |
| `run_scenario_simulation` | planned | `ScenarioSimulator` | batch result + scenario spend dicts | Outcome comparison across scenarios |
| `run_attribution` | planned | `JourneyBuilder`, `AttributionAnalyzer` | CSV path, model(s), lookback_days | Channel credits DataFrame |
| `benchmark_campaigns` | planned | `CampaignBenchmarker` | CSV path, metric_col, metric_type, segment_cols | Benchmark scores + change-point flags |

### Serialisation approach (pass-through JSON)

Tools pass results to each other as JSON strings — no intermediate files or temp storage.
`analyse_campaign_saturation` → `optimise_budget` → `generate_report` chain via JSON strings.

Private helpers in `agents/campaign_analyst.py`:
- `_deserialise_batch_result(json_str)` — rebuilds `CampaignBatchResult` from JSON; applies
  `hill_bayesian → hill` substitution and marks Power model / no-saturation-point campaigns
  as `succeeded=False` (excluded from budget optimisation with reason in `excluded_campaigns`)
- `_deserialise_budget_allocation(json_str)` — rebuilds `BudgetAllocation` from JSON

Known serialisation edge case: `numpy.bool_` from SLSQP feasibility check is not natively
JSON-serialisable. Handled by `_NumpyEncoder` and `_safe()` helpers.

Before adding a new tool, propose the name, inputs, and output contract and wait for
confirmation before writing any code.

---

## SKILL.md philosophy — when to use SKILL.md vs Python code

This distinction is critical. Getting it wrong means either brittle natural-language logic
where code should be, or over-engineered code where plain instructions would do.

### Use SKILL.md for:
- **Orchestration logic** — which tools to call, in what order, under what conditions
- **User-facing instructions** — what questions to ask before running, how to interpret results
- **Boundaries and guardrails** — what the agent should and shouldn't do
- **Reference data** — thresholds, business rules, naming conventions

### Write Python code for:
- **Any computation** — statistics, curve fitting, optimisation, attribution
- **Anything that must be numerically correct and reproducible every time**
- **Anything that needs versioning, testing, and a pip-installable interface**
- **Any logic that would be too long or ambiguous to express reliably in plain language**

**The rule of thumb:** if you could be wrong by expressing it in words, it belongs in code.
If it's purely "do X then Y then Z based on what the user said", it belongs in SKILL.md.

### Reference repos for SKILL.md best practices

When writing or refining any SKILL.md file, always study these two repos first:

- **https://github.com/ericporres/email-triage-plugin** — a full plugin with structured
  `commands/` and `skills/` folders; the gold standard for multi-step orchestration with
  clear agent boundaries, decision logic, and user-facing instructions
- **https://github.com/ericporres/family-assistant-skill** — a pure SKILL.md with reference
  data and policy rules; the gold standard for context-rich instruction files with no custom code

Before writing any new SKILL.md:
1. Read both repos
2. Identify which patterns apply to the skill being built
3. Document in the SKILL.md which patterns were borrowed and why

---

## Agent inventory — full coverage map (all packages)

This list will grow. Every new package added to `Analytics_projects/` must be fully mapped
here before any agent work on that package begins. Every new module added to an existing
package must be assigned to an agent in the same session it is created. This inventory
is the single source of truth for what the agent layer can and cannot do.

### adsat module coverage (v0.5.0 — 15/15 modules covered)

| adsat module | Primary class(es) | Covered by agent | Agent status |
|---|---|---|---|
| `distribution.py` | `DistributionAnalyzer` | Campaign Saturation Agent (via pipeline) | planned |
| `transformation.py` | `DataTransformer` | Campaign Saturation Agent (via pipeline) | planned |
| `modeling.py` | `SaturationModeler` | Campaign Saturation Agent (via pipeline) | planned |
| `evaluation.py` | `ModelEvaluator` | Campaign Saturation Agent (via pipeline) | planned |
| `pipeline.py` | `SaturationPipeline` | Campaign Saturation Agent | planned |
| `campaign.py` | `CampaignSaturationAnalyzer` | Campaign Saturation Agent | planned |
| `exploratory.py` | `CampaignExplorer` | Exploratory / EDA Agent | planned |
| `budget.py` | `BudgetOptimizer` | Campaign Saturation Agent | planned |
| `response_curves.py` | `ResponseCurveAnalyzer` | Campaign Saturation Agent | planned |
| `diagnostics.py` | `ModelDiagnostics` | Model Diagnostics Agent | planned |
| `seasonality.py` | `SeasonalDecomposer` | Seasonality Agent | planned |
| `simulation.py` | `ScenarioSimulator` | Scenario Simulation Agent | planned |
| `report.py` | `ReportBuilder` | Campaign Saturation Agent | planned |
| `attribution.py` | `JourneyBuilder`, `AttributionAnalyzer` | Attribution Agent | planned |
| `benchmark.py` | `CampaignBenchmarker` | Benchmarking Agent | planned |

### Future package coverage sections

When a new package is introduced, add a new subsection here following the same format:
`### <package_name> module coverage (vX.Y.Z — N/N modules covered)`
with a full table mapping every module to an agent before writing any code.

---

### Agent descriptions

#### 1. Campaign Saturation Agent
- **File**: `agents/campaign_analyst.py`
- **Skill**: `skills/campaign-analysis/SKILL.md`
- **Purpose**: End-to-end saturation analysis per campaign — from raw data to budget recommendation
- **adsat modules**: `pipeline.py`, `campaign.py`, `modeling.py`, `evaluation.py`,
  `distribution.py`, `transformation.py`, `budget.py`, `response_curves.py`, `report.py`
- **Typical invocation**: _"Analyse this campaign CSV and tell me which campaigns are
  approaching saturation and how to reallocate budget"_

#### 2. Exploratory / EDA Agent
- **File**: `agents/exploratory_agent.py`
- **Skill**: `skills/exploratory/SKILL.md`
- **Purpose**: Full EDA suite on a dataset before any modelling — distributions, correlations,
  outliers, scatter plots, time series
- **adsat modules**: `exploratory.py`
- **Typical invocation**: _"Run an exploratory analysis on this dataset before I start modelling"_

#### 3. Model Diagnostics Agent
- **File**: `agents/diagnostics_agent.py`
- **Skill**: `skills/diagnostics/SKILL.md`
- **Purpose**: Post-modelling residual diagnostics — checks model health, normality, Cook's D,
  autocorrelation, heteroscedasticity
- **adsat modules**: `diagnostics.py`
- **Typical invocation**: _"Run diagnostics on the model I just fitted for campaign X"_

#### 4. Seasonality Agent
- **File**: `agents/seasonality_agent.py`
- **Skill**: `skills/seasonality/SKILL.md`
- **Purpose**: CMA decomposition of time-series data; separates trend, seasonal, and residual
  components before saturation modelling
- **adsat modules**: `seasonality.py`
- **Typical invocation**: _"Decompose this weekly impressions series and tell me if there's
  a strong seasonal pattern I need to account for"_

#### 5. Scenario Simulation Agent
- **File**: `agents/simulation_agent.py`
- **Skill**: `skills/simulation/SKILL.md`
- **Purpose**: What-if scenario planning; compares hypothetical budget allocations against
  baseline and against each other
- **adsat modules**: `simulation.py`
- **Typical invocation**: _"What happens to total conversions if I move 20% of Campaign A's
  budget to Campaign B?"_

#### 6. Attribution Agent
- **File**: `agents/attribution_agent.py`
- **Skill**: `skills/attribution/SKILL.md`
- **Purpose**: Multi-touch attribution across 9 models (last-click, Shapley, Markov, etc.);
  takes journey-level event data
- **adsat modules**: `attribution.py`
- **Typical invocation**: _"Run attribution on this touchpoint data and compare last-click
  vs Shapley vs Markov results"_

#### 7. Benchmarking Agent
- **File**: `agents/benchmarking_agent.py`
- **Skill**: `skills/benchmarking/SKILL.md`
- **Purpose**: Statistical benchmarking of campaign metrics against historical peers;
  detects change points and flags anomalies
- **adsat modules**: `benchmark.py`
- **Typical invocation**: _"Is Campaign X's CTR performing above or below benchmark
  for its impression volume tier?"_

#### 8. SQL Agent _(future)_
- **File**: `agents/sql_agent.py`
- **Skill**: _(to be defined)_
- **Purpose**: Translate natural language questions about campaign data into SQL queries;
  feeds results into other agents
- **Dependencies**: TBD (database connector MCP)
- **adsat modules**: none directly — feeds data into other agents
- **Typical invocation**: _"Pull last 90 days of impression and conversion data for all
  UK campaigns from the warehouse"_

---

## Testing and performance monitoring

### Tool-level tests
- Location: `tests/test_agents.py`
- What they check: does calling each MCP tool return the same result as calling the
  underlying adsat function directly? These are deterministic and must always pass.

### Agent-level evals (golden datasets)
- Location: `tests/golden/`
- Each golden dataset has a known correct output (saturation points, attribution credits,
  benchmark scores, etc.)
- After every change to `server.py` or any agent module, run the eval suite and verify
  outputs are within acceptable tolerance
- If any agent's accuracy drops below threshold, open a GitHub issue before merging

### Accuracy thresholds
- To be defined per agent when each agent is built
- Numerical outputs (saturation points, attribution credits): within ±1% of golden value
- Classification outputs (saturation status, benchmark flag): 100% match required

### CI schedule
- GitHub Actions workflow runs the eval suite weekly
- Opens an issue automatically if any metric drops below threshold

---

## Publishing roadmap

### GitHub / PyPI (as of 2026-03-25)

- **GitHub repo**: `https://github.com/stefanobandera1/analytics-agents`
- **PyPI**: `analytics-agents` v0.1.2 — published via OIDC trusted publishing
- **CI**: Python 3.10–3.13 × Ubuntu / Windows / macOS — passing
- **requires-python**: `>=3.10` — `mcp>=1.26.0` has no release for Python 3.9

### Steps

1. ✓ Build and test the MCP server locally (`run_end_to_end.py` passing)
2. ✓ `pyproject.toml` with proper metadata, deps, and `[project.urls]`
3. ✓ README with install, Claude Desktop config, tools table, orchestration design
4. ✓ Published to PyPI — tag-triggered OIDC (same flow as adsat)
5. ☐ Submit to MCP community registry: https://github.com/modelcontextprotocol/servers

### MCP server portability

The MCP server is **not Claude-exclusive**. MCP is an open protocol — any MCP-compatible
client (Cursor, Continue, Zed, Claude Desktop, Cowork, Claude Code) can connect and call
the tools. The SKILL.md files are Claude-specific (they are Claude's orchestration layer);
other clients must implement their own equivalent instruction layer. The README must make
this distinction explicit.

### SKILL.md distribution — decided

SKILL.md files ship **bundled inside the pip package**, not as a separate download.
Rationale: SKILL.md files are tightly coupled to tool contracts in `server.py`. A version
mismatch between a separately distributed SKILL.md and the installed server would produce
broken behaviour with no clear error. Bundling enforces version alignment automatically.

**Implementation (not yet built — deferred to a future session):**
- `skills/` must be moved **inside** the `agents/` package directory before adding
  package-data — setuptools package-data paths cannot use `../` to reference files
  outside the package. Proposed layout: `agents/skills/campaign-analysis/SKILL.md`
- Then add to `pyproject.toml`:
  ```toml
  [tool.setuptools.package-data]
  "agents" = ["skills/**/*.md"]
  ```
- Ship a CLI command `analytics-agents install-skills` that copies bundled SKILL.md files
  to the correct Cowork skills directory using `importlib.resources` + `shutil.copy`
- Path resolution uses `platformdirs` (user_data_dir) — works across macOS, Windows, Linux
- **`platformdirs` is a new dependency — flag it and wait for confirmation before adding
  to `pyproject.toml`**
- Wire in `pyproject.toml`:
  ```toml
  [project.scripts]
  analytics-agents = "agents.cli:main"
  ```
- README already caveats this as "coming in a future release" — update when implemented

---

## How to work with Claude on this project

**Before writing any code or creating any file:**
1. Propose exactly what will be created, where, and why
2. Wait for explicit confirmation from Stefano before proceeding
3. Never act silently — describe first, act only after approval

**Never do without flagging and confirming:**
- Add or change dependencies in `pyproject.toml`
- Rename or restructure the folder layout
- Change tool names or input/output contracts in `server.py`
- Modify the agent inventory or coverage map above
- Create new SKILL.md files without reviewing the reference repos first
- Leave any new package module uncovered by an agent
- Build or modify an agent without first reading the CLAUDE.md of every package it uses

**Before working on any agent, always read:**
- This file
- `../CLAUDE.md` (parent shared context)
- The `CLAUDE.md` of every package the agent touches (e.g. `../adsat_package/CLAUDE.md`)
- As new packages are added, their CLAUDE.md files become mandatory reading for any agent
  that wraps their functions — no exceptions

**Coding standards:**
- Follow the same conventions as `adsat`: Python 3.9+, Black (100 chars), Ruff, NumPy
  docstrings, full type hints on public functions
- All new tools must have a corresponding test in `tests/test_agents.py`

---

## Session startup checklist

At the start of every new session on this project:
1. Read this file (`analytics-agents/CLAUDE.md`)
2. Read `../CLAUDE.md` (parent shared context)
3. Read the `CLAUDE.md` of **every package currently in scope** — starting with
   `../adsat_package/CLAUDE.md`, and extending to any new packages added since the last
   session. Each package CLAUDE.md contains the full API, module map, known bugs, and
   design decisions needed to build or improve agents that wrap that package. Never build
   or modify an agent without having read the CLAUDE.md of every package it touches.
4. Run `ls ../` to check whether any new packages have been added to `Analytics_projects/`
   since the last session. If yes, read their CLAUDE.md before doing anything else.
5. Cross-check the agent coverage map against current module lists in **all** packages
6. Flag any uncovered modules or unmapped packages before doing anything else
7. Ask Stefano what we are working on today before touching anything
