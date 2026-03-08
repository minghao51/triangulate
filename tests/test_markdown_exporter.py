"""Unit tests for Markdown exporter."""

from pathlib import Path
import pytest

from src.exporter.markdown_exporter import MarkdownExporter


@pytest.fixture
def exporter():
    """MarkdownExporter instance."""
    return MarkdownExporter()


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
                        "claim": "Test claim confirmed",
                        "verification_status": "CONFIRMED"
                    },
                    {
                        "claim": "Test claim alleged",
                        "verification_status": "ALLEGED"
                    }
                ]
            }
        ],
        "narratives": [
            {
                "cluster_id": "0",
                "stance_summary": "Test narrative about Gaza ceasefire",
                "claim_count": 1
            }
        ],
        "parties": [
            {
                "canonical_name": "Hamas",
                "stance": "Supports ceasefire conditions"
            },
            {
                "canonical_name": "Israel",
                "stance": "Demands security guarantees"
            }
        ],
        "timeline": [],
        "executive_summary": "This analysis covers recent ceasefire negotiations."
    }


@pytest.fixture
def sample_metadata():
    """Sample metadata."""
    return {
        "topic": "Gaza ceasefire negotiations",
        "conflict": "gaza_war",
        "queried_at": "2024-01-01T10:00:00Z",
        "sources_used": ["Reuters", "Al Jazeera"],
        "articles_fetched": 10,
        "articles_processed": 5,
        "queries_generated": ["Gaza ceasefire", "Hamas truce"]
    }


class TestMarkdownExporter:
    """Test MarkdownExporter class."""

    def test_export_creates_file(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that export creates a file."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        assert output_path.exists()

    def test_export_creates_directory(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that export creates output directory if it doesn't exist."""
        output_dir = tmp_path / "subdir" / "output"
        output_path = output_dir / "results.md"

        exporter.export(sample_results, sample_metadata, output_path)

        assert output_dir.exists()
        assert output_path.exists()

    def test_export_contains_header(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file contains header."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "# Topic Analysis: Gaza ceasefire negotiations" in content
        assert "**Conflict Context:** Gaza War" in content
        assert "**Analyzed:**" in content

    def test_export_contains_summary(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file contains summary section."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "## Summary" in content
        assert "processed **1 articles**" in content
        assert "identified **1 distinct narratives**" in content
        assert "across **2 parties/entities**" in content
        assert "This analysis covers recent ceasefire negotiations" in content

    def test_export_contains_key_findings(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file contains key findings section."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "## Key Findings" in content
        assert "### Confirmed Facts" in content
        assert "### Contested Claims" in content
        assert "Test claim confirmed" in content

    def test_export_contains_party_perspectives(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file contains party perspectives section."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "## Party Perspectives" in content
        assert "### Hamas" in content
        assert "### Israel" in content
        assert "Supports ceasefire conditions" in content

    def test_export_contains_timeline(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file contains timeline section."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "## Timeline" in content

    def test_export_contains_sources(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file contains sources section."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "## Sources Analyzed" in content
        assert "**Articles fetched:** 10" in content
        assert "**Articles processed:** 5" in content  # Fixed: uses metadata value
        assert "**Sources analyzed:** 2" in content
        assert "Reuters" in content
        assert "Al Jazeera" in content

    def test_export_empty_timeline(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test exporting with empty timeline."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        assert "## Timeline" in content
        assert "No timeline events available" in content

    def test_export_with_timeline_events(self, exporter, tmp_path):
        """Test exporting with timeline events."""
        output_path = tmp_path / "output.md"

        results_with_timeline = {
            "articles": [],
            "narratives": [],
            "parties": [],
            "timeline": [
                {
                    "date": "2024-01-01",
                    "title": "Ceasefire announced",
                    "description": "Parties agree to ceasefire"
                }
            ]
        }

        exporter.export(results_with_timeline, {}, output_path)

        content = output_path.read_text()

        assert "### 2024-01-01" in content
        assert "**Ceasefire announced**" in content

    def test_export_markdown_formatting(self, exporter, sample_results, sample_metadata, tmp_path):
        """Test that exported file has proper markdown formatting."""
        output_path = tmp_path / "output.md"

        exporter.export(sample_results, sample_metadata, output_path)

        content = output_path.read_text()

        # Check for markdown headers
        assert "# " in content  # H1
        assert "## " in content  # H2
        assert "### " in content  # H3

        # Check for bold text
        assert "**" in content
