"""Backward-compatible content fetcher exports."""

from src.ingester.polling_fetcher import PollingFetcher


class ContentFetcher(PollingFetcher):
    """Backward-compatible alias for the polling fetcher."""


__all__ = ["ContentFetcher", "PollingFetcher"]
