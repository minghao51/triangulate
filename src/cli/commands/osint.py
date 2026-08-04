"""OSINT artifact ingestion commands."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from src.runtime import build_case_service

console = Console()


def cmd_osint_ingest(
    *,
    tool: str,
    file: Path,
    case_id: str,
    output: Path = Path("./output"),
) -> None:
    """Import a single OSINT artifact into a case."""
    service = build_case_service(output)
    result = service.ingest_osint_artifact(
        tool=tool,
        file_path=file,
        case_id=case_id,
    )
    console.print(
        f"[green]Imported OSINT artifact[/green] {result['artifact_id']} "
        f"and linked evidence {result['evidence_id']}"
    )


def cmd_osint_stream(
    *,
    tool: str,
    watch: Path,
    case_id: str,
    once: bool = False,
    output: Path = Path("./output"),
) -> None:
    """Import all OSINT artifacts currently present in a watch directory."""
    service = build_case_service(output)
    result = service.stream_osint_artifacts(
        tool=tool,
        watch_dir=watch,
        case_id=case_id,
        once=once,
    )
    console.print(
        f"[green]Imported {result['imported_count']} artifact(s)[/green] "
        f"from {result['watch_dir']}"
    )
