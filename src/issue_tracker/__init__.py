"""Agent Issue Tracker.

A small, local-first issue tracker and human-gated knowledge base
designed to be driven by coding agents via a CLI, and observed by
humans via a web interface.
"""

__version__ = "0.4.0"

# Capability flags so an agent can check whether the build it is talking to has
# a given feature, e.g. `issue version --json` -> features contains "kb-supersede".
# Add a flag here (and bump __version__) whenever a user-observable capability
# lands, so "am I running the fixed build?" is a one-liner.
FEATURES = [
    "issues",
    "hierarchy",
    "dependencies",
    "knowledge-base",
    "kb-approval",
    "kb-supersede",
    "kb-withdraw",
    "comments",
    "markdown",
    "sse",
    "changes-sentinel",
    "version",
    "hierarchical-list",
    "mobile-view",
    "activity-feed",
    "actor-attribution",
    "notifications",
]
