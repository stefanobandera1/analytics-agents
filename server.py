"""MCP server for analytics-agents.

Exposes adsat analytics functions as MCP tools so that any MCP-compatible
client (Claude Desktop, Claude Code) can invoke them conversationally.

This module is the single entry point for the server. All tools are registered
here. Analytical logic lives entirely in the underlying adsat package — this
file owns only the tool wrappers and server lifecycle.

Usage
-----
Run directly::

    python server.py

Or, once a ``[project.scripts]`` entry point is added to ``pyproject.toml``::

    analytics-agents
"""

from mcp.server.fastmcp import FastMCP

from adsat_agents.campaign_analyst import (
    analyse_campaign_saturation,
    generate_report,
    optimise_budget,
)

# ---------------------------------------------------------------------------
# Server instantiation
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="analytics-agents",
    instructions=(
        "Analytics agent server wrapping the adsat advertising saturation toolkit. "
        "Available tools cover campaign saturation analysis, budget optimisation, "
        "and HTML report generation."
    ),
)

# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

mcp.add_tool(analyse_campaign_saturation)
mcp.add_tool(optimise_budget)
mcp.add_tool(generate_report)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
