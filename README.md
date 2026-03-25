# analytics-agents

MCP server that exposes [adsat](https://github.com/stefanobandera1/adsat) advertising analytics
functions as conversational tools for Claude Desktop, Cowork, and any other MCP-compatible client.

Ask questions like _"which of my campaigns are past saturation?"_ or _"how should I reallocate
my £2M budget across these campaigns?"_ — the server handles the tool calls; you get the results.

---

## Requirements

- Python 3.9 or higher
- `adsat >= 0.5.0` (installed automatically as a dependency)

---

## Installation

```bash
pip install analytics-agents
```

If you are using **Claude Desktop or Cowork**, run one additional command to copy the bundled
skill files to your skills directory:

```bash
analytics-agents install-skills
```

This copies the SKILL.md orchestration files from the package into the directory where Claude
reads them. It is only needed for Claude-based clients — other MCP clients do not use SKILL.md
files and can skip this step.

> **Why bundled?** The SKILL.md files are tightly coupled to the tool contracts in `server.py`.
> Shipping them inside the pip package ensures the skill instructions and the server are always
> on the same version. A mismatch between a separately distributed skill file and an installed
> server would produce broken behaviour with no clear error message.

---

## Connecting to Claude Desktop

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "analytics-agents": {
      "command": "python",
      "args": ["/path/to/analytics-agents/server.py"]
    }
  }
}
```

Replace `/path/to/analytics-agents/` with the absolute path to the directory where you cloned or installed this repo.

The server runs as a local process on your machine — no cloud hosting, no API keys required.

---

## Available tools

### Currently available

| Tool | What it does |
|---|---|
| `analyse_campaign_saturation` | Fits saturation curves per campaign; returns saturation status, R², best model, and optional response curves |
| `optimise_budget` | Allocates a total budget across campaigns to maximise total outcome using SLSQP optimisation |
| `generate_report` | Produces a self-contained HTML report with all charts embedded as base64 PNG |

### Planned

| Tool | What it does |
|---|---|
| `run_exploratory_analysis` | Full EDA suite — distributions, correlations, outliers, time-series plots |
| `run_model_diagnostics` | Six-panel residual diagnostics (normality, autocorrelation, Cook's D, heteroscedasticity) |
| `decompose_seasonality` | CMA-based seasonal decomposition; separates trend, seasonal, and residual components |
| `run_scenario_simulation` | Named what-if scenario comparison and sensitivity tables |
| `run_attribution` | Multi-touch attribution across 9 models (last-click, Shapley, Markov, and more) |
| `benchmark_campaigns` | Statistical benchmarking of campaign metrics against historical baselines with change-point detection |

---

## Multi-agent orchestration

All tools — across all agents — are registered on the same `server.py`. A client like Claude
can see every tool at once and chain them across agents by reading the SKILL.md files and
calling tools in the right order.

Simple sequential workflows are handled this way without any additional framework:

```
SQL Agent (pulls data) → Campaign Saturation Agent → Budget Optimiser → Report
```

Each SKILL.md file contains a "Handoff conditions" section that tells Claude when to invoke
another agent's tools — for example, handing off to the Seasonality Agent when a date column
is present, or to the Diagnostics Agent when R² is below threshold.

**LangGraph is not used in the current release** (Campaign Saturation Agent only). It will be
evaluated and introduced when building the second agent. Multi-agent workflows are not always
linear — conditional branching across agents (e.g. re-run saturation on deseasonalised data
only if seasonality is detected) is too fragile to express reliably in SKILL.md. When
introduced, LangGraph slots into a dedicated `orchestration/` layer only; `server.py` and
all tool contracts remain unchanged.

---

## MCP client compatibility

The MCP server is **not Claude-exclusive**. MCP is an open protocol — any MCP-compatible client
(Cursor, Continue, Zed, Claude Desktop, Cowork, Claude Code) can connect and call the tools.

**What all clients get:** the full tool set — `analyse_campaign_saturation`, `optimise_budget`,
`generate_report`, and all future tools. The tools are deterministic and return structured JSON
regardless of which client calls them.

**What is currently Claude-only:** the orchestration and quality layer — the two-round question
flow before a run, the model quality gate (R², convergence status) before presenting results,
the guardrail against using non-converged models for budget decisions, and the handoff
suggestions to other agents. These behaviours live in the SKILL.md files, which are read by
Claude only. A non-Claude client calling the tools directly gets correct results but none of
this workflow intelligence.

**The path to full client parity:** once orchestration logic moves into the planned
`orchestration/` module (targeted for the second agent), the workflow graph — including
quality gates, conditional branching, and guardrails — will live in code rather than in
SKILL.md. At that point, any client calling a composite tool (e.g. `run_saturation_pipeline`)
gets the same safeguards as a Claude user. The SKILL.md layer remains for Claude-specific
presentation and user-facing narrative; the correctness guarantees become client-agnostic.

---

## Development

See [CLAUDE.md](CLAUDE.md) for the full architectural context, agent inventory, tool contract
specifications, and conventions for adding new tools or agents.

Quick start for local development:

```bash
git clone https://github.com/stefanobandera1/analytics-agents
cd analytics-agents
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## Links

- **adsat package**: [github.com/stefanobandera1/adsat](https://github.com/stefanobandera1/adsat) · [pypi.org/project/adsat](https://pypi.org/project/adsat/)
- **MCP protocol**: [modelcontextprotocol.io](https://modelcontextprotocol.io)
- **MCP community servers**: [github.com/modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers)
