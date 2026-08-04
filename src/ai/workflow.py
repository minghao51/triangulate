"""Backward-compatible workflow exports.

This module preserves the historical ``src.ai.workflow`` import path while the
implementation now lives in ``src.ai.baseline_workflow``.
"""

from src.ai.baseline_workflow import BaselineWorkflow
from src.ai.agents.collector import collect_claims
from src.ai.agents.clusterer import cluster_claims
from src.ai.agents.narrator import narrate_cluster
from src.ai.agents.classifier import classify_verification, classify_event_verification
from src.ai.agents.party_classifier import classify_parties


class AIWorkflow(BaselineWorkflow):
    """Backward-compatible alias for the baseline workflow."""

    async def _collect_claims(self, *args, **kwargs):
        return await collect_claims(*args, **kwargs)

    async def _classify_parties(self, *args, **kwargs):
        return await classify_parties(*args, **kwargs)

    async def _cluster_claims(self, *args, **kwargs):
        return await cluster_claims(*args, **kwargs)

    async def _narrate_cluster(self, *args, **kwargs):
        return await narrate_cluster(*args, **kwargs)


__all__ = [
    "AIWorkflow",
    "BaselineWorkflow",
    "collect_claims",
    "cluster_claims",
    "narrate_cluster",
    "classify_verification",
    "classify_event_verification",
    "classify_parties",
]
