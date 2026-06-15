"""Core worktree management logic."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

    def __init__(self, command: list[str], stderr: str, returncode: int) -> None:
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(f"Git command failed: {' '.join(command)}\n{stderr}")


class WorktreeNotFoundError(WorktreeError):
    """Worktree not found."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Worktree not found: {path}")
        self.path = path


class WorktreeExistsError(WorktreeError):
    """Worktree already exists."""

    def __init__(self, branch: str) -> None:
        super().__init__(f"Worktree or branch '{branch}' already exists")
        self.branch = branch


class GitNotFoundError(WorktreeError):
    """Git executable not found in PATH."""

    def __init__(self) -> None:
        super().__init__("Git not found in PATH")


class NotAGitRepositoryError(WorktreeError):
    """Not a git repository."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Not a git repository: {stderr}")


class ListWorktreesError(WorktreeError):
    """Failed to list worktrees."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Failed to list worktrees: {stderr}")


class CreateWorktreeError(WorktreeError):
    """Failed to create worktree."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Failed to create worktree: {stderr}")


class RemoveWorktreeError(WorktreeError):
    """Failed to remove worktree."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Failed to remove worktree: {stderr}")


class LockWorktreeError(WorktreeError):
    """Failed to lock worktree."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Failed to lock worktree: {stderr}")


class UnlockWorktreeError(WorktreeError):
    """Failed to unlock worktree."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Failed to unlock worktree: {stderr}")


class PruneWorktreesError(WorktreeError):
    """Failed to prune worktrees."""

    def __init__(self, stderr: str) -> None:
        super().__init__(f"Failed to prune worktrees: {stderr}")


class CurrentWorktreeError(WorktreeError):
    """Could not determine current worktree."""

    def __init__(self) -> None:
        super().__init__("Could not determine current worktree")


def run_git_command(
    args: list[str],
    cwd: Path | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    cmd = ["git", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitNotFoundError() from e
    else:
        return result


def get_repo_root(cwd: Path | None = None) -> Path:
    """Get the git repository root directory."""
    # For bare repos, use --git-dir
    result = run_git_command(["rev-parse", "--show-toplevel"], cwd=cwd)
    if result.returncode != 0:
        # Try bare repo approach
        result = run_git_command(["rev-parse", "--git-dir"], cwd=cwd)
        if result.returncode != 0:
            raise NotAGitRepositoryError(result.stderr.strip())
        # For bare repo, the git dir is the repo root
        git_dir = Path(result.stdout.strip())
        if not git_dir.is_absolute():
            git_dir = (cwd or Path()).resolve() / git_dir
        return git_dir
    return Path(result.stdout.strip())


def is_bare_repo(cwd: Path | None = None) -> bool:
    """Check if the repository is bare."""
    result = run_git_command(["rev-parse", "--is-bare-repository"], cwd=cwd)
    return result.stdout.strip() == "true"


def _parse_worktree_line(line: str, current: dict[str, Any]) -> None:
    """Parse a single line from git worktree list --porcelain output."""
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
        if len(line) > len("locked "):
            current["lock_reason"] = line[len("locked ") :]
    elif line == "prunable":
        current["prunable"] = True


def list_worktrees(cwd: Path | None = None) -> list[Worktree]:
    """List all worktrees in the repository."""
    repo_root = get_repo_root(cwd)
    bare = is_bare_repo(cwd)

    # Use porcelain format for consistent parsing
    result = run_git_command(["worktree", "list", "--porcelain"], cwd=repo_root)
    if result.returncode != 0:
        raise ListWorktreesError(result.stderr.strip())

    worktrees = []
    current: dict[str, Any] = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            if current:
                worktrees.append(_parse_worktree(current, repo_root, bare))
                current = {}
            continue

        _parse_worktree_line(line, current)

    if current:
        worktrees.append(_parse_worktree(current, repo_root, bare))

    return worktrees


def _parse_worktree(data: dict[str, Any], repo_root: Path, bare: bool) -> Worktree:
    """Parse worktree data from git worktree list output."""
    path = data.get("path", repo_root)
    commit = data.get("commit", "")
    branch = data.get("branch", "")
    is_bare = data.get("bare", False)
    is_locked = data.get("locked", False)
    is_prunable = data.get("prunable", False)

    # Determine if this is the main worktree
    # For bare repos, the first (and only) worktree is the main one
    is_main = (path == repo_root and not is_bare) or (bare and path == repo_root)

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


def _build_create_worktree_args(
    path: Path, branch: str, base: str | None, force: bool
) -> list[str]:
    """Build git worktree add command arguments."""
    args = ["worktree", "add"]
    if force:
        args.append("--force")
    # Use -b to create a new branch, unless force is used with existing branch
    if not force:
        args.extend(["-b", branch])
    if base:
        args.extend([str(path), base])
    else:
        args.append(str(path))
        if force:
            # When forcing without base, attach to existing branch
            args.append(branch)
    return args


def _find_created_worktree(repo_root: Path, path: Path, branch: str) -> Worktree:
    """Find the newly created worktree in the worktree list."""
    worktrees = list_worktrees(repo_root)
    # First try to find by path (most reliable)
    for wt in worktrees:
        if wt.path == path.resolve():
            return wt
    # Fallback to branch match
    for wt in worktrees:
        if wt.branch == branch:
            return wt
    # Fallback
    return Worktree(
        path=path.resolve(),
        branch=branch,
        commit="",
        is_main=False,
    )


def create_worktree(
    path: Path,
    branch: str,
    base: str | None = None,
    force: bool = False,
    cwd: Path | None = None,
) -> Worktree:
    """Create a new worktree."""
    repo_root = get_repo_root(cwd)

    args = _build_create_worktree_args(path, branch, base, force)

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "already exists" in stderr:
            raise WorktreeExistsError(branch)
        raise CreateWorktreeError(stderr)

    # Get the created worktree info
    return _find_created_worktree(repo_root, path, branch)


def remove_worktree(
    path: Path,
    force: bool = False,
    cwd: Path | None = None,
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
        if (
            "not found" in stderr
            or "no such worktree" in stderr
            or "not a working tree" in stderr
        ):
            raise WorktreeNotFoundError(path)
        raise RemoveWorktreeError(stderr)


def lock_worktree(path: Path, reason: str | None = None, cwd: Path | None = None) -> None:
    """Lock a worktree to prevent pruning."""
    repo_root = get_repo_root(cwd)

    args = ["worktree", "lock"]
    if reason:
        args.extend(["--reason", reason])
    args.append(str(path))

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        raise LockWorktreeError(result.stderr.strip())


def unlock_worktree(path: Path, cwd: Path | None = None) -> None:
    """Unlock a worktree."""
    repo_root = get_repo_root(cwd)

    result = run_git_command(["worktree", "unlock", str(path)], cwd=repo_root)
    if result.returncode != 0:
        raise UnlockWorktreeError(result.stderr.strip())


def prune_worktrees(cwd: Path | None = None, dry_run: bool = False) -> list[Path]:
    """Prune worktree administrative files."""
    repo_root = get_repo_root(cwd)

    args = ["worktree", "prune"]
    if dry_run:
        args.append("--dry-run")
    else:
        args.append("--verbose")

    result = run_git_command(args, cwd=repo_root)
    if result.returncode != 0:
        raise PruneWorktreesError(result.stderr.strip())

    # Parse output for pruned paths
    pruned = []
    for line in result.stdout.strip().split("\n"):
        if "Removing worktree" in line:
            # Extract path from "Removing worktree <path>"
            parts = line.split("Removing worktree")
            if len(parts) > 1:
                pruned.append(Path(parts[1].strip()))

    return pruned


def get_current_worktree(cwd: Path | None = None) -> Worktree:
    """Get the worktree for the current directory."""
    repo_root = get_repo_root(cwd)
    worktrees = list_worktrees(repo_root)

    current_dir = Path(cwd or ".").resolve()
    for wt in worktrees:
        try:
            current_dir.relative_to(wt.path)
        except ValueError:
            continue
        else:
            return wt

    # Fallback to main worktree
    for wt in worktrees:
        if wt.is_main:
            return wt

    raise CurrentWorktreeError()
