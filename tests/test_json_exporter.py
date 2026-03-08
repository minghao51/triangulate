"""Unit tests for JSON exporter."""

import json
from pathlib import Path
import pytest

from src.exporter.json_exporter import JSONExporter


@pytest.fixture
def exporter():
    """JSONExporter instance."""
    return JSONExporter()


@pytest.fixture
def sample_results():
    """Sample analysis results."""
    return {
        "articles": [
            {
                "url": "http://test.com/article1",
                "title": "Test Article 1",
                "source": "Reuters",
                "published_at": "2024-01-01T10:00:00Z",
                "relevance_score": 0.9,
                "claims": [
                    {
                        "claim": "Test claim",
                        "verification_status": "CONFIRMED"
                    }
                ]
            }
        ],
        "narratives": [
            {
                "cluster_id": "0",
                "stance_summary": "Test narrative",
                "claim_count": 1
            }
        ],
        "parties": [
            {
                "canonical_name": "Test Party",
                "stance": "Supports"
            }
        ],
        "timeline": []
    }


@pytest.fixture
def sample_metadata():
    """Sample metadata."""
    return {
        "topic": "Gaza ceasefire",
        "conflict": "gaza_war",
        "queried_at": "2024-01-01T10:00:00Z",
        "sources_used": ["Reuters", "Al Jazeera"],
        "articles_fetched": 10,
        "articles_processed": 5,
        "queries_generated": ["Gaza ceasefire", "Hamas truce"]
    }


class TestJSONExporter:
    """Test JSONExporter class."""

    def test_export_creates_file(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that export creates a file."""
        output_path = tmp_path / "output.json"

        exporter.export(sample_results, sample_metadata, output_path)

        assert output_path.exists()

    def test_export_creates_directory(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that export creates output directory if it doesn't exist."""
        output_dir = tmp_path / "subdir" / "output"
        output_path = output_dir / "results.json"

        exporter.export(sample_results, sample_metadata, output_path)

        assert output_dir.exists()
        assert output_path.exists()

    def test_export_valid_json(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file is valid JSON."""
        output_path = tmp_path / "output.json"

        exporter.export(sample_results, sample_metadata, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert isinstance(data, dict)

    def test_export_metadata(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that metadata is exported correctly."""
        output_path = tmp_path / "output.json"

        exporter.export(sample_results, sample_metadata, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "metadata" in data
        assert data["metadata"]["topic"] == "Gaza ceasefire"
        assert data["metadata"]["conflict"] == "gaza_war"
        assert data["metadata"]["articles_fetched"] == 10
        assert data["metadata"]["articles_processed"] == 5

    def test_export_articles(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that articles are exported correctly."""
        output_path = tmp_path / "output.json"

        exporter.export(sample_results, sample_metadata, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "articles" in data
        assert len(data["articles"]) == 1
        assert data["articles"][0]["title"] == "Test Article 1"
        assert data["articles"][0]["relevance_score"] == 0.9

    def test_export_narratives(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that narratives are exported correctly."""
        output_path = tmp_path / "output.json"

        exporter.export(sample_results, sample_metadata, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "narratives" in data
        assert len(data["narratives"]) == 1
        assert data["narratives"][0]["cluster_id"] == "0"

    def test_export_parties(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that parties are exported correctly."""
        output_path = tmp_path / "output.json"

        exporter.export(sample_results, sample_metadata, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "parties" in data
        assert len(data["parties"]) == 1
        assert data["parties"][0]["canonical_name"] == "Test Party"

    def test_export_empty_results(self, exporter, tmp_path):
        """Test exporting empty results."""
        output_path = tmp_path / "output.json"

        exporter.export({}, {}, output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "metadata" in data
        assert "articles" in data
        assert "narratives" in data
        assert "parties" in data
        assert "timeline" in data
