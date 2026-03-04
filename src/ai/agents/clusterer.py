"""Clusterer agent: Group claims by narrative stance."""

import logging
from typing import Any

try:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not available, narrative clustering will be limited")


logger = logging.getLogger(__name__)


async def cluster_claims(
    claims: list[dict[str, Any]], n_clusters: int = 3
) -> dict[str, Any]:
    """Group claims by narrative stance.

    Args:
        claims: List of claim dictionaries
        n_clusters: Number of narrative clusters to identify

    Returns:
        Dictionary with cluster assignments and summaries
    """
    if len(claims) < 2:
        logger.info("Not enough claims to cluster")
        return {
            "clusters": {str(i): [claim] for i, claim in enumerate(claims)},
            "n_clusters": len(claims),
        }

    if not SKLEARN_AVAILABLE:
        # Fallback: simple grouping by confidence
        logger.warning("Using fallback clustering by confidence")
        return _cluster_by_confidence(claims)

    try:
        # Extract claim texts
        texts = [claim.get("claim", "") for claim in claims]

        # Create TF-IDF vectors
        vectorizer = TfidfVectorizer(stop_words="english", max_features=100)
        tfidf_matrix = vectorizer.fit_transform(texts)

        # Perform clustering
        n_clusters = min(n_clusters, len(claims))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(tfidf_matrix)

        # Group claims by cluster
        clusters = {}
        for idx, label in enumerate(cluster_labels):
            cluster_id = str(label)
            if cluster_id not in clusters:
                clusters[cluster_id] = []
            clusters[cluster_id].append(claims[idx])

        logger.info(
            f"Clustered {len(claims)} claims into {len(clusters)} narrative groups"
        )

        return {
            "clusters": clusters,
            "n_clusters": len(clusters),
        }

    except Exception as e:
        logger.error(f"Error clustering claims: {e}")
        return _cluster_by_confidence(claims)


def _cluster_by_confidence(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Fallback: group claims by confidence level.

    Args:
        claims: List of claim dictionaries

    Returns:
        Dictionary with cluster assignments
    """
    clusters = {}
    for claim in claims:
        confidence = claim.get("confidence", "MEDIUM")
        if confidence not in clusters:
            clusters[confidence] = []
        clusters[confidence].append(claim)

    return {
        "clusters": clusters,
        "n_clusters": len(clusters),
    }
