"""Shared test fixtures for gitwork."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def git_repo(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository with initial commit."""
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
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

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path


@pytest.fixture
def git_repo_with_branch(git_repo: Path) -> Generator[Path, None, None]:
    """Create a git repo with an additional branch."""
    # Create a feature branch
    subprocess.run(
        ["git", "branch", "feature-branch"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    yield git_repo


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch: pytest.MonkeyPatch, temp_dir: Path) -> None:
    """Isolate environment variables for tests."""
    monkeypatch.setenv("HOME", str(temp_dir))
    monkeypatch.setenv("USERPROFILE", str(temp_dir))
