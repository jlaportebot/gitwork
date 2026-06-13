"""Tests for gitwork core module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from gitwork.core import (
    GitError,
    Worktree,
    WorktreeError,
    WorktreeExistsError,
    WorktreeNotFoundError,
    create_worktree,
    get_current_worktree,
    get_repo_root,
    is_bare_repo,
    list_worktrees,
    lock_worktree,
    prune_worktrees,
    remove_worktree,
    run_git_command,
    unlock_worktree,
)


class TestRunGitCommand:
    """Tests for run_git_command function."""

    def test_run_git_command_success(self, tmp_path: Path) -> None:
        """Test successful git command execution."""
        # Create a git repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        (repo_path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True
        )

        result = run_git_command(["rev-parse", "--show-toplevel"], cwd=repo_path)
        assert result.returncode == 0
        assert repo_path.name in result.stdout

    def test_run_git_command_failure(self, tmp_path: Path) -> None:
        """Test git command failure handling."""
        result = run_git_command(["rev-parse", "--show-toplevel"], cwd=tmp_path)
        assert result.returncode != 0

    def test_run_git_command_git_not_found(self, tmp_path: Path) -> None:
        """Test error when git is not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(WorktreeError, match="Git not found in PATH"):
                run_git_command(["status"], cwd=tmp_path)


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_get_repo_root_success(self, git_repo: Path) -> None:
        """Test getting repo root from inside repo."""
        root = get_repo_root(git_repo)
        assert root == git_repo

    def test_get_repo_root_from_subdir(self, git_repo: Path) -> None:
        """Test getting repo root from subdirectory."""
        subdir = git_repo / "subdir"
        subdir.mkdir()
        root = get_repo_root(subdir)
        assert root == git_repo

    def test_get_repo_root_failure(self, tmp_path: Path) -> None:
        """Test error when not in a git repo."""
        with pytest.raises(WorktreeError, match="Not a git repository"):
            get_repo_root(tmp_path)


class TestIsBareRepo:
    """Tests for is_bare_repo function."""

    def test_is_bare_repo_false(self, git_repo: Path) -> None:
        """Test that normal repo is not bare."""
        assert not is_bare_repo(git_repo)

    def test_is_bare_repo_true(self, tmp_path: Path) -> None:
        """Test that bare repo is detected as bare."""
        bare_path = tmp_path / "bare_repo"
        bare_path.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=bare_path, check=True, capture_output=True)
        assert is_bare_repo(bare_path)


class TestListWorktrees:
    """Tests for list_worktrees function."""

    def test_list_worktrees_basic(self, git_repo: Path) -> None:
        """Test listing worktrees in a simple repo."""
        worktrees = list_worktrees(git_repo)
        assert len(worktrees) == 1
        wt = worktrees[0]
        assert wt.is_main
        assert not wt.is_bare
        assert wt.branch == "master" or wt.branch == "main"

    def test_list_worktrees_with_additional(self, git_repo_with_branch: Path) -> None:
        """Test listing worktrees after creating additional worktree."""
        # Create a worktree for a new branch (feature-branch already exists in fixture)
        wt_path = git_repo_with_branch.parent / "feature_wt"
        create_worktree(wt_path, "another-branch", cwd=git_repo_with_branch)

        worktrees = list_worktrees(git_repo_with_branch)
        assert len(worktrees) == 2

        # Find the new worktree
        new_wt = next(w for w in worktrees if w.path == wt_path.resolve())
        assert new_wt.branch == "another-branch"
        assert not new_wt.is_main

    def test_list_worktrees_bare_repo(self, tmp_path: Path) -> None:
        """Test listing worktrees in bare repo."""
        bare_path = tmp_path / "bare_repo"
        bare_path.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=bare_path, check=True, capture_output=True)

        worktrees = list_worktrees(bare_path)
        assert len(worktrees) == 1
        assert worktrees[0].is_bare
        assert worktrees[0].is_main


class TestCreateWorktree:
    """Tests for create_worktree function."""

    def test_create_worktree_new_branch(self, git_repo: Path, tmp_path: Path) -> None:
        """Test creating worktree with new branch."""
        wt_path = tmp_path / "new_wt"
        wt = create_worktree(wt_path, "new-feature", cwd=git_repo)

        assert wt.path == wt_path.resolve()
        assert wt.branch == "new-feature"
        assert not wt.is_main

        # Verify worktree exists
        worktrees = list_worktrees(git_repo)
        assert len(worktrees) == 2

    def test_create_worktree_from_base(self, git_repo: Path, tmp_path: Path) -> None:
        """Test creating worktree from specific base commit."""
        # Get current commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=git_repo, check=True, capture_output=True, text=True
        )
        commit = result.stdout.strip()

        wt_path = tmp_path / "base_wt"
        wt = create_worktree(wt_path, "from-base", base=commit, cwd=git_repo)

        assert wt.branch == "from-base"

    def test_create_worktree_force(self, git_repo: Path, tmp_path: Path) -> None:
        """Test force creating worktree when branch exists."""
        wt_path1 = tmp_path / "wt1"
        create_worktree(wt_path1, "shared-branch", cwd=git_repo)

        # Try to create another with same branch - should fail without force
        wt_path2 = tmp_path / "wt2"
        with pytest.raises(WorktreeExistsError):
            create_worktree(wt_path2, "shared-branch", cwd=git_repo)

        # With force should succeed
        wt = create_worktree(wt_path2, "shared-branch", force=True, cwd=git_repo)
        assert wt.path == wt_path2.resolve()


class TestRemoveWorktree:
    """Tests for remove_worktree function."""

    def test_remove_worktree(self, git_repo: Path, tmp_path: Path) -> None:
        """Test removing a worktree."""
        wt_path = tmp_path / "wt_to_remove"
        create_worktree(wt_path, "to-remove", cwd=git_repo)

        remove_worktree(wt_path, cwd=git_repo)

        worktrees = list_worktrees(git_repo)
        assert len(worktrees) == 1
        assert not any(wt.path == wt_path.resolve() for wt in worktrees)

    def test_remove_worktree_not_found(self, git_repo: Path, tmp_path: Path) -> None:
        """Test removing non-existent worktree."""
        wt_path = tmp_path / "nonexistent"
        with pytest.raises(WorktreeNotFoundError):
            remove_worktree(wt_path, cwd=git_repo)

    def test_remove_worktree_with_uncommitted_changes(self, git_repo: Path, tmp_path: Path) -> None:
        """Test removing worktree with uncommitted changes requires force."""
        wt_path = tmp_path / "wt_dirty"
        create_worktree(wt_path, "dirty-branch", cwd=git_repo)

        # Make uncommitted change
        (wt_path / "dirty.txt").write_text("uncommitted")
        subprocess.run(["git", "add", "dirty.txt"], cwd=wt_path, check=True, capture_output=True)

        # Should fail without force
        with pytest.raises(WorktreeError):
            remove_worktree(wt_path, cwd=git_repo)

        # Should succeed with force
        remove_worktree(wt_path, force=True, cwd=git_repo)


class TestLockUnlockWorktree:
    """Tests for lock_worktree and unlock_worktree functions."""

    def test_lock_worktree(self, git_repo: Path, tmp_path: Path) -> None:
        """Test locking a worktree."""
        wt_path = tmp_path / "wt_lock"
        create_worktree(wt_path, "lock-branch", cwd=git_repo)

        lock_worktree(wt_path, reason="testing", cwd=git_repo)

        worktrees = list_worktrees(git_repo)
        locked_wt = next(w for w in worktrees if w.path == wt_path.resolve())
        assert locked_wt.is_locked

    def test_lock_worktree_no_reason(self, git_repo: Path, tmp_path: Path) -> None:
        """Test locking a worktree without reason."""
        wt_path = tmp_path / "wt_lock_nr"
        create_worktree(wt_path, "lock-branch-nr", cwd=git_repo)

        lock_worktree(wt_path, cwd=git_repo)

        worktrees = list_worktrees(git_repo)
        locked_wt = next(w for w in worktrees if w.path == wt_path.resolve())
        assert locked_wt.is_locked

    def test_unlock_worktree(self, git_repo: Path, tmp_path: Path) -> None:
        """Test unlocking a worktree."""
        wt_path = tmp_path / "wt_unlock"
        create_worktree(wt_path, "unlock-branch", cwd=git_repo)
        lock_worktree(wt_path, cwd=git_repo)

        unlock_worktree(wt_path, cwd=git_repo)

        worktrees = list_worktrees(git_repo)
        unlocked_wt = next(w for w in worktrees if w.path == wt_path.resolve())
        assert not unlocked_wt.is_locked


class TestPruneWorktrees:
    """Tests for prune_worktrees function."""

    def test_prune_worktrees_dry_run(self, git_repo: Path, tmp_path: Path) -> None:
        """Test prune dry run."""
        wt_path = tmp_path / "wt_prune"
        create_worktree(wt_path, "prune-branch", cwd=git_repo)
        # Remove the worktree directory but not the admin files
        import shutil

        shutil.rmtree(wt_path)

        pruned = prune_worktrees(cwd=git_repo, dry_run=True)
        # Dry run should not actually prune
        assert isinstance(pruned, list)

    def test_prune_worktrees_actual(self, git_repo: Path, tmp_path: Path) -> None:
        """Test actual prune."""
        wt_path = tmp_path / "wt_prune2"
        create_worktree(wt_path, "prune-branch2", cwd=git_repo)
        import shutil

        shutil.rmtree(wt_path)

        pruned = prune_worktrees(cwd=git_repo, dry_run=False)
        assert isinstance(pruned, list)


class TestGetCurrentWorktree:
    """Tests for get_current_worktree function."""

    def test_get_current_worktree_main(self, git_repo: Path) -> None:
        """Test getting current worktree from main repo."""
        wt = get_current_worktree(git_repo)
        assert wt.is_main
        assert wt.path == git_repo

    def test_get_current_worktree_from_worktree(self, git_repo: Path, tmp_path: Path) -> None:
        """Test getting current worktree from within a worktree."""
        wt_path = tmp_path / "wt_current"
        create_worktree(wt_path, "current-branch", cwd=git_repo)

        wt = get_current_worktree(wt_path)
        assert wt.path == wt_path.resolve()
        assert wt.branch == "current-branch"

    def test_get_current_worktree_from_subdir(self, git_repo: Path, tmp_path: Path) -> None:
        """Test getting current worktree from subdirectory of worktree."""
        wt_path = tmp_path / "wt_subdir"
        create_worktree(wt_path, "subdir-branch", cwd=git_repo)
        subdir = wt_path / "sub"
        subdir.mkdir()

        wt = get_current_worktree(subdir)
        assert wt.path == wt_path.resolve()


class TestWorktreeDataclass:
    """Tests for Worktree dataclass."""

    def test_worktree_name_property(self) -> None:
        """Test Worktree.name property returns directory name."""
        wt = Worktree(path=Path("/some/path/my-worktree"), branch="main", commit="abc123")
        assert wt.name == "my-worktree"

    def test_worktree_equality(self) -> None:
        """Test Worktree equality comparison."""
        wt1 = Worktree(path=Path("/path/wt"), branch="main", commit="abc")
        wt2 = Worktree(path=Path("/path/wt"), branch="main", commit="abc")
        wt3 = Worktree(path=Path("/path/other"), branch="main", commit="abc")
        assert wt1 == wt2
        assert wt1 != wt3


class TestExceptions:
    """Tests for exception classes."""

    def test_worktree_error_base(self) -> None:
        """Test base WorktreeError."""
        err = WorktreeError("test error")
        assert str(err) == "test error"

    def test_git_error(self) -> None:
        """Test GitError with command details."""
        err = GitError(["git", "status"], "fatal: not a repo", 128)
        assert "git status" in str(err)
        assert "fatal: not a repo" in str(err)
        assert err.command == ["git", "status"]
        assert err.stderr == "fatal: not a repo"
        assert err.returncode == 128

    def test_worktree_not_found_error(self) -> None:
        """Test WorktreeNotFoundError."""
        err = WorktreeNotFoundError("worktree not found")
        assert str(err) == "worktree not found"

    def test_worktree_exists_error(self) -> None:
        """Test WorktreeExistsError."""
        err = WorktreeExistsError("worktree exists")
        assert str(err) == "worktree exists"
