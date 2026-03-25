"""Pytest configuration for analytics-agents tests.

Sets the matplotlib backend to non-interactive Agg before any import of
matplotlib occurs, preventing display errors in headless and CI environments.
"""

import matplotlib

matplotlib.use("Agg")
