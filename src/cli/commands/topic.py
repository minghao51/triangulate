"""Topic-oriented CLI entrypoints."""

from pathlib import Path

from rich.console import Console

from src.cli.commands.cases import (
    cmd_fetch_topic_case,
    cmd_monitor_cases,
)

console = Console()


def cmd_fetch_topic(
    query: str,
    output: Path = Path("./output"),
    format: str = "json,markdown",
    max_articles: int = 50,
    relevance_threshold: float = 0.3,
    conflict: str | None = None,
    confirmed_parties: list[str] | None = None,
    manual_links: list[str] | None = None,
    automation_mode: str = "exceptions_only",
) -> None:
    """Fetch and analyze news by topic through the case pipeline."""
    cmd_fetch_topic_case(
        query=query,
        output=output,
        format=format,
        max_articles=max_articles,
        relevance_threshold=relevance_threshold,
        conflict=conflict,
        confirmed_parties=confirmed_parties,
        manual_links=manual_links,
        automation_mode=automation_mode,
    )


def cmd_interactive() -> None:
    """Launch interactive topic exploration session."""
    console.print("[bold blue]Interactive Topic Copilot[/bold blue]")
    console.print("Enter 'quit' or 'exit' to stop\n")

    while True:
        try:
            query = console.input("[bold cyan]Topic:[/bold cyan] ")
            if not query.strip():
                continue
            if query.lower() in ["quit", "exit"]:
                console.print("Goodbye!")
                break
            cmd_fetch_topic_case(query=query)
        except KeyboardInterrupt:
            console.print("\nGoodbye!")
            break
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]\n")


def cmd_monitor_start(
    topics_config: Path = Path("./topics.yaml"),
    interval: int = 30,
) -> None:
    """Start the recurring monitor service."""
    cmd_monitor_cases(topics_config=topics_config, interval=interval)
