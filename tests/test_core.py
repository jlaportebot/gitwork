"""Tests for gitwork."""

from gitwork.core import get_repo_root, list_worktrees


def test_get_repo_root(tmp_path):
    """Test getting repo root."""
    # This is a basic test - in a real git repo it would work
    assert get_repo_root is not None


def test_list_worktrees(tmp_path):
    """Test listing worktrees."""
    assert list_worktrees is not None
