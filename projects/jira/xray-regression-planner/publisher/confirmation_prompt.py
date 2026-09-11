"""
confirmation_prompt.py — Interactive CLI confirmation before publishing.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from models.plan import RegressionPlan

console = Console()


def confirm_publish(plan: RegressionPlan) -> bool:
    """Display plan summary and ask for confirmation."""
    console.print("\n[bold blue]═══ Publish Confirmation ═══[/bold blue]\n")

    table = Table(title="Execution Plan Summary")
    table.add_column("Platform", style="cyan")
    table.add_column("Tests", justify="right")
    table.add_column("T1", justify="right", style="red")
    table.add_column("T2", justify="right", style="yellow")
    table.add_column("T3", justify="right", style="green")
    table.add_column("Est. Min", justify="right")

    for e in plan.executions:
        table.add_row(
            e.platform.value.upper(),
            str(len(e.tests)),
            str(e.tier1_count),
            str(e.tier2_count),
            str(e.tier3_count),
            str(e.estimated_minutes),
        )

    console.print(table)
    console.print(f"\n  Total tests: [bold]{plan.total_selected}[/bold]")
    console.print(f"  Confidence:  [bold]{plan.confidence_level.value}[/bold]\n")

    response = console.input("[bold yellow]Create these XRay executions? (yes/no): [/bold yellow]")
    return response.strip().lower() in ("yes", "y")
