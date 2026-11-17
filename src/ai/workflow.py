"""Backward-compatible workflow exports.

The implementation now lives in :mod:`src.ai.baseline_workflow` (shared with the
case service); this module preserves the historical ``src.ai.workflow`` import
path, the ``AIWorkflow`` name and the collector-outcome helpers introduced for
honest extraction reporting.
"""

from src.ai.baseline_workflow import (
    BaselineWorkflow,
    _AGENT_METADATA_KEYS,
    _collector_metadata,
    _collector_outcome,
    _extract_location,
    _normalize_agent_result,
)

# Historical name for the baseline pipeline.
AIWorkflow = BaselineWorkflow

__all__ = [
    "AIWorkflow",
    "BaselineWorkflow",
    "_AGENT_METADATA_KEYS",
    "_collector_metadata",
    "_collector_outcome",
    "_extract_location",
    "_normalize_agent_result",
]
