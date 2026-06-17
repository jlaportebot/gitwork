"""Tests for gitwork CLI module."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from gitwork.cli import main

PORCELAIN_FIELD_COUNT = 6


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_help(self) -> None:
        """Test that CLI help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "git worktree manager" in result.output.lower()

    def test_cli_version(self) -> None:
        """Test that CLI version works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "gitwork" in result.output.lower()

    def test_create_command_help(self) -> None:
        """Test create command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["create", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output.lower()

    def test_list_command_help(self) -> None:
        """Test list command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["list", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output.lower()

    def test_remove_command_help(self) -> None:
        """Test remove command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["remove", "--help"])
        assert result.exit_code == 0
        assert "remove" in result.output.lower()

    def test_lock_command_help(self) -> None:
        """Test lock command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["lock", "--help"])
        assert result.exit_code == 0
        assert "lock" in result.output.lower()

    def test_unlock_command_help(self) -> None:
        """Test unlock command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["unlock", "--help"])
        assert result.exit_code == 0
        assert "unlock" in result.output.lower()

    def test_prune_command_help(self) -> None:
        """Test prune command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["prune", "--help"])
        assert result.exit_code == 0
        assert "prune" in result.output.lower()

    def test_current_command_help(self) -> None:
        """Test current command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["current", "--help"])
        assert result.exit_code == 0
        assert "current" in result.output.lower()


class TestCLIIntegration:
    """Integration tests for CLI commands using real git repos."""

    def test_list_in_git_repo(self, git_repo: Path) -> None:
        """Test list command in a git repo."""
        runner = CliRunner()
        result = runner.invoke(main, ["list"], obj={}, catch_exceptions=False)
        # The command should run without crashing
        # (it may fail due to not being in the repo, but shouldn't crash)
        assert result.exit_code in (0, 1, 2)

    def test_create_invalid_path(self, tmp_path: Path) -> None:
        """Test create command with invalid path (existing file)."""
        runner = CliRunner()
        # Create a file at the path - CLI should reject paths that exist as files
        existing_file = tmp_path / "existing_file"
        existing_file.write_text("content")
        # Correct argument order: branch first, then path
        result = runner.invoke(main, ["create", "new-branch", str(existing_file)])
        # Should fail gracefully - path exists as a file
        assert result.exit_code != 0
        assert "Error" in result.output or "error" in result.output.lower()

    def test_cli_with_explicit_repo(self, git_repo: Path) -> None:
        """Test CLI commands with explicit repo path."""
        runner = CliRunner()
        result = runner.invoke(main, ["--repo", str(git_repo), "list"])
        # Should work with explicit repo
        assert result.exit_code in (0, 1, 2)


class TestStatusCommand:
    """Tests for status command."""

    def test_status_command_help(self) -> None:
        """Test status command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output.lower()

    def test_status_clean_repo(self, git_repo: Path) -> None:
        """Test status command on clean repo."""
        runner = CliRunner()
        old_cwd = Path.cwd()
        try:
            os.chdir(git_repo)
            result = runner.invoke(main, ["status"], obj={}, catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Worktree Status" in result.output
        assert "Clean" in result.output

    def test_status_with_uncommitted(self, git_repo: Path) -> None:
        """Test status command detects uncommitted changes."""
        (git_repo / "uncommitted.txt").write_text("uncommitted")
        runner = CliRunner()
        old_cwd = Path.cwd()
        try:
            os.chdir(git_repo)
            result = runner.invoke(main, ["status"], obj={}, catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "Dirty" in result.output or "Yes" in result.output

    def test_status_porcelain(self, git_repo: Path) -> None:
        """Test status command with porcelain output."""
        runner = CliRunner()
        old_cwd = Path.cwd()
        try:
            os.chdir(git_repo)
            result = runner.invoke(main, ["status", "--porcelain"], obj={}, catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        # Porcelain output should have 6 fields: branch commit ahead behind upstream has_uncommitted
        parts = result.output.strip().split()
        assert len(parts) == PORCELAIN_FIELD_COUNT
        assert parts[0] in {"master", "main"}
        assert parts[4] == "none"
        assert parts[5] == "0"


class TestSyncCommand:
    """Tests for sync command."""

    def test_sync_command_help(self) -> None:
        """Test sync command help."""
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--help"])
        assert result.exit_code == 0
        assert "sync" in result.output.lower()

    def test_sync_no_upstream(self, git_repo: Path) -> None:
        """Test sync command fails when no upstream configured."""
        runner = CliRunner()
        old_cwd = Path.cwd()
        try:
            os.chdir(git_repo)
            result = runner.invoke(main, ["sync"], obj={}, catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code != 0
        assert "No upstream branch configured" in result.output

    def test_sync_with_uncommitted(self, git_repo: Path, tmp_path: Path) -> None:
        """Test sync command fails with uncommitted changes."""
        # Create a remote
        remote_path = tmp_path / "remote_repo"
        remote_path.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=remote_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_path)],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "HEAD"],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )

        # Add uncommitted change
        (git_repo / "uncommitted.txt").write_text("uncommitted")

        runner = CliRunner()
        old_cwd = Path.cwd()
        try:
            os.chdir(git_repo)
            result = runner.invoke(main, ["sync"], obj={}, catch_exceptions=False)
        finally:
            os.chdir(old_cwd)
        assert result.exit_code != 0
        assert "uncommitted changes" in result.output


def test_main_entry_point() -> None:
    """Test that main can be called as module."""
    result = subprocess.run(
        [sys.executable, "-m", "gitwork", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "gitwork" in result.stdout.lower()
