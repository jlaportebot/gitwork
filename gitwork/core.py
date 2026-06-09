"""Core worktree management logic."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Worktree:
    """Represents a git worktree."""

    path: Path
    branch: str
    commit: str
    is_main: bool = False
    is_bare: bool = False
    is_locked: bool = False
    prunable: bool = False

    @property
    def name(self) -> str:
        """Get the worktree directory name."""
        return self.path.name


class WorktreeError(Exception):
    """Base exception for worktree operations."""

    pass


class GitError(WorktreeError):
    """Git command failed."""

    def __init__(self, command: list[str], stderr: str, returncode: int):
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(f"Git command failed: {' '.join(command)}\n{stderr}")


class WorktreeNotFoundError(WorktreeError):
    """Worktree not found."""

    pass


class WorktreeExistsError(WorktreeError):
    """Worktree already exists."""

    pass


def run_git_command(
    args: list[str],
    cwd: Optional[Path] = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            check=False,
        )
        return result
    except FileNotFoundError as e:
        raise WorktreeError("Git not found in PATH") from e


def get_repo_root(cwd: Optional[Path] = None) -> Path:
    """Get the git repository root directory."""
    result = run_git_command(["rev-parse", "--show-toplevel"], cwd=cwd)
    if result.returncode != 0:
        raise WorktreeError(f"Not a git repository: {result.stderr.strip()}")
    return Path(result.stdout.strip())


def is_bare_repo(cwd: Optional[Path] = None) -> bool:
    """Check if the repository is bare."""
    result = run_git_command(["rev-parse", "--is-bare-repository"], cwd=cwd)
    return result.stdout.strip() == "true"


def list_worktrees(cwd: Optional[Path] = None) -> list[Worktree]:
    """List all worktrees in the repository."""
    repo_root = get_repo_root(cwd)
    bare = is_bare_repo(cwd)

    # Use porcelain format for consistent parsing
    result = run_git_command(["worktree", "list", "--porcelain"], cwd=repo_root)
    if result.returncode != 0:
        raise WorktreeError(f"Failed to list worktrees: {result.stderr.strip()}")

    worktrees = []
    current = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            if current:
                worktrees.append(_parse_worktree(current, repo_root, bare))
                current = {}
            continue

        if line.startswith("worktree "):
            current["path"] = Path(line[9:])
        elif line.startswith("HEAD "):
            current["commit"] = line[5:]
        elif line.startswith("branch "):
            current["branch"] = line[7:]
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["detached"] = True
        elif line.startswith("locked"):
            current["locked"] = True
            if len(line) > 6:
                current["lock_reason"] = line[8:]
        elif line == "prunable":
            current["prunable"] = True

    if current:
        worktrees.append(_parse_worktree(current, repo_root, bare))

    return worktrees


def _parse_worktree(data: dict, repo_root: Path, bare: bool) -> Worktree:
    """Parse worktree data from git worktree list output."""
    path = data.get("path", repo_root)
    commit = data.get("commit", "")
    branch = data.get("branch", "")
    is_bare = data.get("bare", False)
    is_locked = data.get("locked", False)
    is_prunable = data.get("prunable", False)

    # Determine if this is the main worktree
    is_main = path == repo_root and not is_bare

    # Clean up branch name (remove refs/heads/ prefix)
    if branch.startswith("refs/heads/"):
        branch = branch[11:]
    elif branch == "(none)" or data.get("detached"):
        branch = f"detached@{commit[:8]}"

    return Worktree(
        path=path,
        branch=branch,
        commit=commit,
        is_main=is_main,
        is_bare=is_bare,
        is_locked=is_locked,
        prunable=is_prunable,
    )


def create_worktree(
    path: Path,
    branch: str,
    base: Optional[str] = None,
    force: bool = False,
    cwd: Optional[Path] = None,
) -> Worktree:
    """Create a new worktree."""
    repo_root = get_repo_root(cwd)

    args = ["worktree", "add"]
    if force:
        args.append("--force")
    if base:
        args.extend(["-b", branch, base])
    else:
        args.extend([str(path), branch])

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "already exists" in stderr:
            raise WorktreeExistsError(f"Worktree or branch '{branch}' already exists")
        raise WorktreeError(f"Failed to create worktree: {stderr}")

    # Get the created worktree info
    worktrees = list_worktrees(repo_root)
    for wt in worktrees:
        if wt.path == path.resolve() or wt.branch == branch:
            return wt

    # Fallback
    return Worktree(
        path=path.resolve(),
        branch=branch,
        commit="",
        is_main=False,
    )


def remove_worktree(
    path: Path,
    force: bool = False,
    cwd: Optional[Path] = None,
) -> None:
    """Remove a worktree."""
    repo_root = get_repo_root(cwd)

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(path))

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not found" in stderr or "no such worktree" in stderr:
            raise WorktreeNotFoundError(f"Worktree not found: {path}")
        raise WorktreeError(f"Failed to remove worktree: {stderr}")


def lock_worktree(path: Path, reason: Optional[str] = None, cwd: Optional[Path] = None) -> None:
    """Lock a worktree to prevent pruning."""
    repo_root = get_repo_root(cwd)

    args = ["worktree", "lock"]
    if reason:
        args.extend(["--reason", reason])
    args.append(str(path))

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        raise WorktreeError(f"Failed to lock worktree: {result.stderr.strip()}")


def unlock_worktree(path: Path, cwd: Optional[Path] = None) -> None:
    """Unlock a worktree."""
    repo_root = get_repo_root(cwd)

    result = run_git_command(["worktree", "unlock", str(path)], cwd=repo_root)
    if result.returncode != 0:
        raise WorktreeError(f"Failed to unlock worktree: {result.stderr.strip()}")


def prune_worktrees(cwd: Optional[Path] = None, dry_run: bool = False) -> list[Path]:
    """Prune worktree administrative files."""
    repo_root = get_repo_root(cwd)

    args = ["worktree", "prune"]
    if dry_run:
        args.append("--dry-run")
    else:
        args.append("--verbose")

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        raise WorktreeError(f"Failed to prune worktrees: {result.stderr.strip()}")

    # Parse output for pruned paths
    pruned = []
    for line in result.stdout.strip().split("\n"):
        if "Removing worktree" in line:
            # Extract path from "Removing worktree <path>"
            parts = line.split("Removing worktree")
            if len(parts) > 1:
                pruned.append(Path(parts[1].strip()))

    return pruned


def get_current_worktree(cwd: Optional[Path] = None) -> Worktree:
    """Get the worktree for the current directory."""
    repo_root = get_repo_root(cwd)
    worktrees = list_worktrees(repo_root)

    current_dir = Path(cwd or ".").resolve()
    for wt in worktrees:
        try:
            current_dir.relative_to(wt.path)
            return wt
        except ValueError:
            continue

    # Fallback to main worktree
    for wt in worktrees:
        if wt.is_main:
            return wt

    raise WorktreeNotFoundError("Could not determine current worktree")