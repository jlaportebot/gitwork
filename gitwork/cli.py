"""CLI entry point for gitwork."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from gitwork import (
    Worktree,
    WorktreeError,
    WorktreeExistsError,
    WorktreeNotFoundError,
    create_worktree,
    get_current_worktree,
    get_repo_root,
    list_worktrees,
    lock_worktree,
    prune_worktrees,
    remove_worktree,
    unlock_worktree,
)

console = Console()


def handle_error(e: Exception) -> int:
    """Handle and display errors consistently."""
    if (
        isinstance(e, WorktreeNotFoundError)
        or isinstance(e, WorktreeExistsError)
        or isinstance(e, WorktreeError)
    ):
        console.print(f"[red]Error:[/red] {e}")
    else:
        console.print(f"[red]Unexpected error:[/red] {e}")
    return 1


def format_worktree(wt: Worktree) -> dict:
    """Format a worktree for display."""
    status_parts = []
    if wt.is_main:
        status_parts.append("[bold green]main[/bold green]")
    if wt.is_bare:
        status_parts.append("[yellow]bare[/yellow]")
    if wt.is_locked:
        status_parts.append("[red]locked[/red]")
    if wt.prunable:
        status_parts.append("[dim]prunable[/dim]")
    status = " ".join(status_parts) if status_parts else ""

    return {
        "name": wt.name,
        "branch": wt.branch,
        "commit": wt.commit[:8] if wt.commit else "",
        "path": str(wt.path),
        "status": status,
    }


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="gitwork")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Git worktree manager - manage multiple working trees with ease."""
    if ctx.invoked_subcommand is None:
        # Default to list when no subcommand given
        ctx.invoke(list_cmd)


@main.command(name="list")
@click.option("--all", "show_all", is_flag=True, help="Show all worktrees including bare")
@click.option("--porcelain", is_flag=True, help="Machine-readable output")
@click.pass_context
def list_cmd(ctx: click.Context, show_all: bool, porcelain: bool) -> None:
    """List all worktrees in the repository."""
    try:
        worktrees = list_worktrees()
    except WorktreeError as e:
        ctx.exit(handle_error(e))

    if porcelain:
        for wt in worktrees:
            parts = [str(wt.path), wt.branch, wt.commit[:8]]
            if wt.is_main:
                parts.append("main")
            if wt.is_bare:
                parts.append("bare")
            if wt.is_locked:
                parts.append("locked")
            if wt.prunable:
                parts.append("prunable")
            click.echo(" ".join(parts))
        return

    table = Table(title="Git Worktrees", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Branch", style="green")
    table.add_column("Commit", style="dim")
    table.add_column("Path", style="blue")
    table.add_column("Status")

    for wt in worktrees:
        if not show_all and wt.is_bare:
            continue
        fmt = format_worktree(wt)
        table.add_row(fmt["name"], fmt["branch"], fmt["commit"], fmt["path"], fmt["status"])

    console.print(table)


@main.command()
@click.argument("branch")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("-b", "--base", help="Base commit/branch to create from")
@click.option("-f", "--force", is_flag=True, help="Force creation even if branch exists")
@click.pass_context
def create(ctx: click.Context, branch: str, path: Path, base: str | None, force: bool) -> None:
    """Create a new worktree at PATH for BRANCH."""
    # Validate path doesn't exist as a file
    if path.exists() and path.is_file():
        console.print(f"[red]Error:[/red] Path '{path}' exists as a file")
        ctx.exit(1)

    try:
        wt = create_worktree(path=path, branch=branch, base=base, force=force)
        console.print(f"[green]Created worktree:[/green] {wt.name} at {wt.path}")
        console.print(f"  Branch: {wt.branch}")
        console.print(f"  Commit: {wt.commit[:8]}")
    except WorktreeError as e:
        ctx.exit(handle_error(e))


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("-f", "--force", is_flag=True, help="Force removal even with uncommitted changes")
@click.pass_context
def remove(ctx: click.Context, path: Path, force: bool) -> None:
    """Remove a worktree at PATH."""
    try:
        remove_worktree(path=path, force=force)
        console.print(f"[green]Removed worktree:[/green] {path}")
    except WorktreeError as e:
        ctx.exit(handle_error(e))


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("-r", "--reason", help="Reason for locking")
@click.pass_context
def lock(ctx: click.Context, path: Path, reason: str | None) -> None:
    """Lock a worktree to prevent pruning."""
    try:
        lock_worktree(path=path, reason=reason)
        msg = f"[green]Locked worktree:[/green] {path}"
        if reason:
            msg += f" (reason: {reason})"
        console.print(msg)
    except WorktreeError as e:
        ctx.exit(handle_error(e))


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def unlock(ctx: click.Context, path: Path) -> None:
    """Unlock a worktree."""
    try:
        unlock_worktree(path=path)
        console.print(f"[green]Unlocked worktree:[/green] {path}")
    except WorktreeError as e:
        ctx.exit(handle_error(e))


@main.command()
@click.option("--dry-run", is_flag=True, help="Show what would be pruned without doing it")
@click.pass_context
def prune(ctx: click.Context, dry_run: bool) -> None:
    """Prune worktree administrative files."""
    try:
        pruned = prune_worktrees(dry_run=dry_run)
        if dry_run:
            console.print("[yellow]Dry run - would prune:[/yellow]")
        else:
            console.print("[green]Pruned:[/green]")
        for p in pruned:
            console.print(f"  {p}")
        if not pruned:
            console.print("  (none)")
    except WorktreeError as e:
        ctx.exit(handle_error(e))


@main.command()
@click.pass_context
def current(ctx: click.Context) -> None:
    """Show the current worktree."""
    try:
        wt = get_current_worktree()
        fmt = format_worktree(wt)
        console.print(f"Current worktree: [bold]{fmt['name']}[/bold]")
        console.print(f"  Branch: {fmt['branch']}")
        console.print(f"  Commit: {fmt['commit']}")
        console.print(f"  Path: {fmt['path']}")
        if fmt["status"]:
            console.print(f"  Status: {fmt['status']}")
    except WorktreeError as e:
        ctx.exit(handle_error(e))


@main.command()
@click.pass_context
def root(ctx: click.Context) -> None:
    """Show the repository root."""
    try:
        root_path = get_repo_root()
        console.print(f"Repository root: {root_path}")
    except WorktreeError as e:
        ctx.exit(handle_error(e))


if __name__ == "__main__":
    sys.exit(main())
