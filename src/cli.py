import argparse
import json
import sys

from rich.console import Console
from rich.table import Table

from src.engine import CampaignAnalyzerEngine
from src.streamer import get_campaign_metadata

console = Console()


def build_table() -> Table:
    table = Table(
        title="Faction Inactivity & Sleep Pattern Analysis",
        show_lines=True,
    )
    table.add_column("ID", justify="right", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold white")
    table.add_column("Sleep Window (UTC)", style="yellow")
    table.add_column("Avg Duration", justify="center")
    table.add_column("Inferred TZ", style="magenta", justify="center")
    table.add_column("Sleep Cycles", justify="center")
    table.add_column("AFK Blocks", justify="center")
    return table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Torn City Inactivity & Sleep Pattern Analysis Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python src/cli.py -f campaign_21.json\n"
            "  python src/cli.py -f campaign_21.json -j report.json --min-sleep 4.5\n"
        ),
    )
    parser.add_argument("--file", "-f", required=True, help="Path to campaign JSON file")
    parser.add_argument(
        "--min-sleep",
        type=float,
        default=4.0,
        metavar="HOURS",
        help="Minimum inactivity gap to consider (default: 4.0 hours)",
    )
    parser.add_argument("--json-out", "-j", metavar="PATH", help="Write full JSON report to this path")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress table output (useful with --json-out)")

    args = parser.parse_args()

    # ── Campaign metadata header ─────────────────────────────────────
    try:
        meta = get_campaign_metadata(args.file)
        faction = meta.get("faction_name", "Unknown Faction")
        camp_id = meta.get("id", "N/A")
        console.print(
            f"\n[bold green]▶ Campaign {camp_id}[/bold green] · "
            f"[bold white]{faction}[/bold white]\n"
        )
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] File not found: {args.file}")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Failed to read campaign file:[/bold red] {e}")
        sys.exit(1)

    # ── Analysis ─────────────────────────────────────────────────────
    engine = CampaignAnalyzerEngine(args.file, min_sleep_gap=args.min_sleep)
    profiles = []
    table = build_table()

    with console.status("[bold cyan]Analysing members…[/bold cyan]", spinner="dots"):
        for profile in engine.run():
            profiles.append(profile)
            table.add_row(
                str(profile.player_id),
                profile.name,
                profile.estimated_sleep_window_utc,
                f"{profile.avg_sleep_duration_hours:.1f}h",
                profile.inferred_timezone,
                str(len(profile.primary_sleep_cycles)),
                str(len(profile.secondary_afk_blocks)),
            )

    # ── Output ───────────────────────────────────────────────────────
    if not args.quiet:
        console.print(table)
        console.print(f"\n[dim]Processed {len(profiles)} member(s).[/dim]")

    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump([p.model_dump() for p in profiles], f, indent=2, default=str)
            console.print(f"\n[bold green]✔[/bold green] JSON report saved to [cyan]{args.json_out}[/cyan]")
        except OSError as e:
            console.print(f"[bold red]Failed to write JSON output:[/bold red] {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
