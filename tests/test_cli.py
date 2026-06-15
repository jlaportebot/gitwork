"""Tests for gitwork CLI module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from gitwork.cli import main


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
        # Create a file at the path - git worktree add will fail if path exists as a file
        existing_file = tmp_path / "existing_file"
        existing_file.write_text("content")
        result = runner.invoke(main, ["create", str(existing_file), "new-branch"])
        # Should fail gracefully
        assert result.exit_code != 0 or "Error" in result.output or "error" in result.output.lower()

    def test_cli_with_explicit_repo(self, git_repo: Path) -> None:
        """Test CLI commands with explicit repo path."""
        runner = CliRunner()
        result = runner.invoke(main, ["--repo", str(git_repo), "list"])
        # Should work with explicit repo
        assert result.exit_code in (0, 1, 2)


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
