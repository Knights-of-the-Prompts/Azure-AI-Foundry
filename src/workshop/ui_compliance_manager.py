"""
ui_compliance_manager.py

Terminal user interface for the Compliance Manager.

Features
- Visually appealing (uses rich if available) with a pharma/Bayer themed palette.
- Presents categories, fetches authoritative updates, supports refinement and confirmation.
- Does NOT prompt to create a compliance report until the user explicitly confirms they
  have a sufficient answer. "Create report" is a separate menu action.

Usage
    python -m src.workshop.ui_compliance_manager

This module falls back to a simple CLI if `rich` is not installed.
"""

from typing import Optional, Dict, Any
import sys
import textwrap

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt
    RICH_AVAILABLE = True
except Exception:
    RICH_AVAILABLE = False

from src.workshop.compliance_manager import ComplianceManager


PHARMA_PRIMARY = "#0b5a7c"  # deep teal/blue
PHARMA_ACCENT = "#6fbf73"   # green accent


class UIComplianceManager:
    def __init__(self, cm: Optional[ComplianceManager] = None):
        self.cm = cm or ComplianceManager(require_citations=True)
        self.last_result: Optional[Dict[str, Any]] = None
        self.last_scope: Optional[str] = None
        self.confirmed = False

        # Perform dynamic imports for rich components so toggling RICH_AVAILABLE at runtime
        # works reliably in tests and interactive runs.
        self.rich_available = False
        self.console = None
        self.Panel = None
        self.Table = None
        self.Text = None
        self.Prompt = None
        try:
            if RICH_AVAILABLE:
                from rich.console import Console as _Console
                from rich.table import Table as _Table
                from rich.panel import Panel as _Panel
                from rich.text import Text as _Text
                from rich.prompt import Prompt as _Prompt

                self.console = _Console()
                self.Panel = _Panel
                self.Table = _Table
                self.Text = _Text
                self.Prompt = _Prompt
                self.rich_available = True
        except Exception:
            # fall back to non-rich behavior
            self.rich_available = False

    def _print_header(self):
        title = "Bayer Compliance Manager"
        subtitle = "Authoritative research and compliance reporting — data protection & regulations"
        if self.rich_available:
            header = self.Text("\n  ╔══════════════════════════════════════════════════════════╗\n", style=PHARMA_PRIMARY)
            header.append(self.Text(f"  ║  {title}  ║\n", style=f"bold {PHARMA_PRIMARY}"))
            header.append(self.Text(f"  ║  {subtitle}  ║\n", style=PHARMA_PRIMARY))
            header.append(self.Text("  ╚══════════════════════════════════════════════════════════╝\n", style=PHARMA_PRIMARY))
            self.console.print(self.Panel(header, style=PHARMA_PRIMARY, subtitle="Pharmaceutical Compliance", subtitle_align="right"))
        else:
            print("\n==========================================")
            print(title)
            print(subtitle)
            print("==========================================\n")

    def _show_categories(self):
        categories = list(self.cm.CATEGORY_MAP.keys())
        if self.rich_available:
            table = self.Table(show_header=True, header_style="bold white")
            table.add_column("#", style="bold", width=3)
            table.add_column("Category", style=f"bold {PHARMA_PRIMARY}")
            table.add_column("Description", style="")
            for i, k in enumerate(categories, start=1):
                table.add_row(str(i), k, self.cm.CATEGORY_MAP[k]["description"])
            self.console.print(table)
        else:
            for i, k in enumerate(categories, start=1):
                print(f"{i}. {k} - {self.cm.CATEGORY_MAP[k]['description']}")
        return categories

    def _pretty_print_result(self, result: Dict[str, Any]):
        if not result:
            return
        if self.rich_available:
            panel = self.Panel(result.get('message_text', ''), title="Agent Summary", style=PHARMA_PRIMARY)
            self.console.print(panel)
            if result.get('citations'):
                table = self.Table(show_header=True)
                table.add_column("#", width=3)
                table.add_column("URL", style=PHARMA_ACCENT)
                for i, c in enumerate(result.get('citations'), start=1):
                    table.add_row(str(i), c.get('url'))
                self.console.print(self.Panel(table, title="Citations", style=PHARMA_ACCENT))
        else:
            print('\n--- Agent Summary ---')
            print(textwrap.fill(result.get('message_text', ''), width=100))
            if result.get('citations'):
                print('\nCitations:')
                for c in result.get('citations'):
                    print(f"- {c.get('url')}")

    def run(self):
        self._print_header()
        while True:
            categories = self._show_categories()
            if self.rich_available:
                choice = self.Prompt.ask('\nSelect category number (or 0 to exit)', default="0")
            else:
                choice = input('\nSelect category number (or 0 to exit): ').strip()

            if choice in ("0", "exit", "quit"):
                if RICH_AVAILABLE:
                    self.console.print(Text('Goodbye.', style=PHARMA_PRIMARY))
                else:
                    print('Goodbye.')
                break

            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(categories):
                    raise ValueError()
            except Exception:
                if RICH_AVAILABLE:
                    self.console.print(Text('Invalid selection, try again.', style="red"))
                else:
                    print('Invalid selection, try again.')
                continue

            category = categories[idx]
            meta = self.cm.CATEGORY_MAP[category]
            # Fetch updates
            if self.rich_available:
                self.console.print(self.Panel(self.Text(f"Fetching latest updates for: {category}"), style=PHARMA_PRIMARY))
            else:
                print(f"Fetching latest updates for: {category}...\n")

            updates = self.cm.search_updates(meta['scope'])
            self.last_result = updates
            self.last_scope = meta['scope']
            self.confirmed = False

            # If the agent requested refinement, allow iterative refine-confirm loop
            if updates.get('note') or (not updates.get('citations')):
                # Present what we have and allow refinement
                self._pretty_print_result(updates)
                # Ask the user if they want to refine
                if self.rich_available:
                    refine = self.Prompt.ask('Provide additional context/jurisdiction/timeframe (or leave blank to skip)', default='')
                else:
                    refine = input('Provide additional context/jurisdiction/timeframe (or press Enter to skip): ').strip()
                if refine:
                    refined = self.cm.handle_query(f"Latest official updates on {meta['scope']}. {refine}")
                    self.last_result = refined
                    self._pretty_print_result(refined)
                    # Ask user to confirm sufficiency
                    if self.rich_available:
                        ok = self.Prompt.ask('Is this information sufficient to proceed later? (y/N)', choices=['y','n'], default='n')
                    else:
                        ok = input('Is this information sufficient to proceed later? (y/N): ').strip().lower()
                    if ok and ok.lower().startswith('y'):
                        self.confirmed = True
                        if self.rich_available:
                            self.console.print(self.Text('Result confirmed. You may create a report later via the programmatic API.', style=PHARMA_ACCENT))
                        else:
                            print('Result confirmed. You may create a report later via the programmatic API.')
                    else:
                        if self.rich_available:
                            self.console.print(self.Text('You can refine again by selecting the category again.', style='yellow'))
                        else:
                            print('You can refine again by selecting the category again.')
                else:
                    # No refinement provided, simply show the result and return to menu.
                    self._pretty_print_result(updates)
                    if self.rich_available:
                        self.console.print(self.Text('No refinement provided. Returning to menu.', style='yellow'))
                    else:
                        print('No refinement provided. Returning to menu.')
            else:
                # We received good updates with citations
                self._pretty_print_result(updates)
                if self.rich_available:
                    self.console.print(self.Text('If you want to create a compliance report, use the programmatic API or run the dedicated report flow.', style=PHARMA_ACCENT))
                else:
                    print('\nIf you want to create a compliance report, use the programmatic API or run the dedicated report flow.')


if __name__ == "__main__":
    ui = UIComplianceManager()
    try:
        ui.run()
    except KeyboardInterrupt:
        if RICH_AVAILABLE:
            ui.console.print(Text('\nInterrupted. Exiting.', style='red'))
        else:
            print('\nInterrupted. Exiting.')
        sys.exit(0)
