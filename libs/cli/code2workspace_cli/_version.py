"""Version information and lightweight constants for EpiMindAgent CLI."""

__version__ = "0.0.37"  # x-release-please-version

DOCS_URL = "https://github.com/zhang-pei-feng/code2workspace/blob/main/libs/cli/README.md"
"""URL for EpiMindAgent CLI documentation."""

PYPI_URL = "https://pypi.org/pypi/code2workspace-cli/json"
"""PyPI JSON API endpoint for version checks."""

CHANGELOG_URL = (
    "https://github.com/zhang-pei-feng/code2workspace/releases"
)
"""URL for the full changelog."""

USER_AGENT = f"epimindagent-cli/{__version__} update-check"
"""User-Agent header sent with PyPI requests."""
