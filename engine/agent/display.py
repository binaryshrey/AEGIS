from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


class Display:
    def header(self, player_id: str, timeout: float, num_opponents: int):
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="bold cyan")
        grid.add_column()
        grid.add_row("Player", player_id)
        grid.add_row("Timeout", f"{timeout}s / move")
        grid.add_row("Opponents", str(num_opponents))
        console.print()
        console.print(Panel(grid, title="[bold white]STARSLING AGENT[/]",
                            border_style="cyan", box=box.HEAVY))

    def attempt_start(self, attempt_num: int, prior_attempts: int, memory_opponents: int):
        parts = [f"[bold]ATTEMPT {attempt_num}[/]"]
        if prior_attempts > 0:
            parts.append(f"  prior: {prior_attempts}  |  memory: {memory_opponents} opponents")
        console.print()
        console.rule(Text.from_markup(" ".join(parts)), style="blue")

    def attempt_end(self, attempt_num: int, wins: int, losses: int):
        total = wins + losses
        wr = wins / total if total else 0
        color = "green" if wr >= 0.9 else "yellow" if wr >= 0.7 else "red"
        console.print(
            f"\n  [{color} bold]Attempt {attempt_num}:[/] "
            f"{wins}W / {losses}L ({wr:.0%})"
        )

    def game_start(self, n: int, opp: str, known_place: bool, known_fire: bool,
                   games_played: int = 0, win_rate: float = 0.0,
                   strategy: str = "", strategy_reason: str = ""):
        if games_played == 0:
            ctx = "[dim]first encounter[/]"
        elif games_played == 1:
            ctx = f"1 game · {win_rate:.0%} W"
        else:
            ctx = f"{games_played} games · {win_rate:.0%} W"

        tags = []
        if known_place:
            tags.append("[magenta]KNOWN-PLACE[/]")
        if known_fire:
            tags.append("[magenta]KNOWN-FIRE[/]")
        tag_str = f"  {'  '.join(tags)}" if tags else ""

        strat_str = ""
        if strategy:
            strat_color = {"exploit": "red bold", "hunt": "yellow", "probability": "cyan"}.get(strategy, "white")
            strat_str = f"  [{strat_color}]{strategy}[/]"
            if strategy_reason:
                strat_str += f"  [dim]({strategy_reason})[/]"

        console.print(
            f"\n[bold white]GAME {n:02}[/] vs [bold]{opp}[/]  |  "
            f"{ctx}{tag_str}{strat_str}"
        )

    def move(self, turn: int, x: int, y: int, result: str, ms: float,
             strategy: str = "", move_reason: dict = None):
        if result == "miss":
            return
        if result == "sunk":
            icon = "[red bold]SUNK[/]"
        else:
            icon = "[yellow]HIT [/]"
        strat_tag = f"  [dim][{strategy}][/]" if strategy else ""
        console.print(f"  T{turn:02}  ({x},{y}) {icon}  [dim]{ms:.0f}ms[/]{strat_tag}")

        # Explainability: show WHY this cell was chosen
        if move_reason:
            parts = []
            mode = move_reason.get("mode", "")
            if mode == "exploit":
                remaining = move_reason.get("remaining_targets", 0)
                parts.append(f"known position, {remaining} targets left")
            elif mode == "hunt":
                active = move_reason.get("active_hits", 0)
                ships = move_reason.get("remaining_ships", [])
                parts.append(f"hunting {active} active hit{'s' if active != 1 else ''}")
                if ships:
                    parts.append(f"ships left: {ships}")
            else:
                prob = move_reason.get("prob", 0)
                conc = move_reason.get("concentration", 0)
                candidates = move_reason.get("total_candidates", 0)
                ships = move_reason.get("remaining_ships", [])
                parts.append(f"prob={prob:.0f}")
                if conc > 0:
                    parts.append(f"{conc:.1f}x avg")
                parts.append(f"1/{candidates} cells")
                if ships:
                    parts.append(f"ships left: {ships}")
            console.print(f"        [dim italic]  {' | '.join(parts)}[/]")

    def game_end(self, won: bool, moves: int, avg_ms: float, delta: int | None = None,
                 ships_lost: int = 0, hits_received: int = 0):
        status = "[green bold]WON [/]" if won else "[red bold]LOST[/]"
        delta_str = ""
        if delta is not None and delta != 0:
            arrow = "↓" if delta > 0 else "↑"
            color = "green" if delta > 0 else "red"
            delta_str = f" [{color}]{arrow}{abs(delta)}[/]"
        defense_str = ""
        if ships_lost > 0:
            defense_str = f"  |  [dim]lost {ships_lost} ships ({hits_received} hits)[/]"
        console.print(f"  {status}  {moves} moves{delta_str}  |  [dim]{avg_ms:.0f}ms avg[/]{defense_str}")

    def lesson(self, msg: str):
        console.print(f"  [blue]LEARN[/] {msg}")

    def pattern(self, msg: str):
        console.print(f"  [magenta]DETECT[/] {msg}")

    def memory(self, opp: str, fixed_place: bool, fixed_fire: bool):
        pass

    def board(self, board_str: str):
        for line in board_str.split("\n"):
            console.print(f"    {line}")

    def leaderboard(self, entries: list, my_id: str):
        table = Table(title="LEADERBOARD", box=box.ROUNDED, border_style="cyan",
                      title_style="bold white")
        table.add_column("#", style="dim", width=4)
        table.add_column("Player", min_width=16)
        table.add_column("Score", justify="right")

        for i, e in enumerate(entries[:15], 1):
            pid = e.get("playerId", "?")
            score = str(e.get("score", 0))
            style = "bold green" if pid == my_id else ""
            marker = " ◀" if pid == my_id else ""
            table.add_row(str(i), f"{pid}{marker}", score, style=style)

        console.print()
        console.print(table)

    def info(self, msg: str):
        console.print(f"  [dim cyan]→[/] {msg}")

    def error(self, msg: str):
        console.print(f"  [red bold]✗[/] {msg}")

    def summary(self, wins: int, total: int):
        rate = f"{wins/total:.0%}" if total else "—"
        color = "green" if total and wins / total >= 0.9 else "yellow"
        console.print(
            f"\n  [{color} bold]Final: {wins}W / {total - wins}L  ({rate})[/]  "
            f"out of {total} games\n"
        )
