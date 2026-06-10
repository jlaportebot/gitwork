"""gitwork - CLI tool for managing git worktrees with ease."""

__version__ = "0.1.0"

from gitwork.core import (
    GitError,
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

__all__ = [
    "GitError",
    "Worktree",
    "WorktreeError",
    "WorktreeExistsError",
    "WorktreeNotFoundError",
    "create_worktree",
    "get_current_worktree",
    "get_repo_root",
    "list_worktrees",
    "lock_worktree",
    "prune_worktrees",
    "remove_worktree",
    "unlock_worktree",
]
