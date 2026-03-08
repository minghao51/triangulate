"""Run the configured topic pipeline once."""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from rich.console import Console

from src.cli.commands.cases import build_case_service

console = Console()


def cmd_run_pipeline() -> None:
    """Run the topic case pipeline for configured topics once."""
    topics_path = Path("./topics.yaml")
    if not topics_path.exists():
        console.print("[yellow]topics.yaml not found; nothing to run[/yellow]")
        return

    with open(topics_path) as handle:
        config = yaml.safe_load(handle) or {}

    topics = config.get("topics", [])
    if not topics:
        console.print("[yellow]No topics configured in topics.yaml[/yellow]")
        return

    service = build_case_service()
    cases = asyncio.run(service.run_monitor_cycle(topics, output_root=Path("./output")))
    console.print(f"[green]Pipeline complete for {len(cases)} case(s)[/green]")
