"""gitwork - CLI tool for managing git worktrees with ease."""

__version__ = "0.1.0"

from gitwork.core import (
    Worktree,
    WorktreeError,
    GitError,
    WorktreeNotFoundError,
    WorktreeExistsError,
    list_worktrees,
    create_worktree,
    remove_worktree,
    lock_worktree,
    unlock_worktree,
    prune_worktrees,
    get_current_worktree,
    get_repo_root,
)

__all__ = [
    "Worktree",
    "WorktreeError",
    "GitError",
    "WorktreeNotFoundError",
    "WorktreeExistsError",
    "list_worktrees",
    "create_worktree",
    "remove_worktree",
    "lock_worktree",
    "unlock_worktree",
    "prune_worktrees",
    "get_current_worktree",
    "get_repo_root",
]