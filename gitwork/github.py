"""GitHub integration for gitwork - PR worktree management."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gitwork.core import (
    WorktreeError,
    create_worktree,
    get_repo_root,
    list_worktrees,
    remove_worktree,
)


class GitHubError(WorktreeError):
    """GitHub integration error."""

    pass


class GitHubCLINotFoundError(GitHubError):
    """gh CLI not found in PATH."""

    def __init__(self) -> None:
        super().__init__("gh CLI not found in PATH")


class GitHubRemoteURLError(GitHubError):
    """Failed to get remote URL."""

    def __init__(self) -> None:
        super().__init__("Failed to get remote URL")


class GitHubNonGitHubRemoteError(GitHubError):
    """Remote is not a GitHub repository."""

    def __init__(self) -> None:
        super().__init__("Remote is not a GitHub repository")


class GitHubInvalidRepoPathError(GitHubError):
    """Invalid GitHub repository path."""

    def __init__(self) -> None:
        super().__init__("Invalid GitHub repository path")


class GitHubCLIError(GitHubError):
    """gh CLI command failed."""

    def __init__(self) -> None:
        super().__init__("gh CLI failed")


class GitHubInvalidJSONError(GitHubError):
    """Invalid JSON response from gh."""

    def __init__(self, original_error: json.JSONDecodeError) -> None:
        super().__init__("Invalid JSON from gh")
        self.original_error = original_error


class GitHubPRNotFoundError(GitHubError):
    """Pull request not found."""

    def __init__(self, pr_number: int) -> None:
        super().__init__(f"PR #{pr_number} not found")
        self.pr_number = pr_number


class GitHubPRDetailsError(GitHubError):
    """Failed to get PR details."""

    def __init__(self) -> None:
        super().__init__("Failed to get PR details")


# Constants for magic values
GITHUB_REPO_PATH_PARTS = 2
PR_BRANCH_PARTS_MIN = 3


def run_gh_command(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a gh command and return the result."""
    cmd = ["gh", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitHubCLINotFoundError() from e
    else:
        return result


@dataclass(frozen=True)
class PRInfo:
    """Information about a GitHub pull request."""

    number: int
    title: str
    head_branch: str
    head_repo: str
    state: str
    is_draft: bool = False

    @classmethod
    def from_gh_json(cls, data: dict[str, Any]) -> PRInfo:
        """Create PRInfo from gh API JSON response."""
        return cls(
            number=data["number"],
            title=data["title"],
            head_branch=data["headRefName"],
            head_repo=data["headRepository"]["nameWithOwner"],
            state=data["state"].lower(),
            is_draft=data.get("isDraft", False),
        )


def get_repo_info(cwd: Path | None = None) -> tuple[str, str]:
    """Get GitHub owner and repo name from git remote."""
    repo_root = get_repo_root(cwd)

    # Get remote URL
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitHubRemoteURLError() from None

    remote_url = result.stdout.strip()

    # Parse GitHub URL (HTTPS or SSH)
    # HTTPS: https://github.com/owner/repo.git
    # SSH: git@github.com:owner/repo.git
    if remote_url.startswith("https://github.com/"):
        path = remote_url[len("https://github.com/") :]
    elif remote_url.startswith("git@github.com:"):
        path = remote_url[len("git@github.com:") :]
    else:
        raise GitHubNonGitHubRemoteError()

    # Remove .git suffix
    if path.endswith(".git"):
        path = path[:-4]

    parts = path.split("/")
    if len(parts) != GITHUB_REPO_PATH_PARTS:
        raise GitHubInvalidRepoPathError()

    return parts[0], parts[1]


def get_pr_list(
    cwd: Path | None = None,
    state: str = "open",
    limit: int = 30,
) -> list[PRInfo]:
    """List pull requests for the repository."""
    repo_root = get_repo_root(cwd)
    owner, repo = get_repo_info(repo_root)

    args = [
        "pr",
        "list",
        "--repo",
        f"{owner}/{repo}",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,headRefName,headRepository,state,isDraft",
    ]

    result = run_gh_command(args, cwd=repo_root)
    if result.returncode != 0:
        raise GitHubCLIError()

    try:
        prs_data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GitHubInvalidJSONError(e) from e

    return [PRInfo.from_gh_json(pr) for pr in prs_data]


def checkout_pr(
    pr_number: int,
    path: Path,
    cwd: Path | None = None,
    base: str | None = None,
) -> Path:
    """Create a worktree for a GitHub pull request."""
    repo_root = get_repo_root(cwd)
    owner, repo = get_repo_info(repo_root)

    # Get PR details from gh
    args = [
        "pr",
        "view",
        str(pr_number),
        "--repo",
        f"{owner}/{repo}",
        "--json",
        "number,title,headRefName,headRepository,state,isDraft",
    ]

    result = run_gh_command(args, cwd=repo_root)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not found" in stderr.lower():
            raise GitHubPRNotFoundError(pr_number)
        raise GitHubPRDetailsError()

    try:
        pr_data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GitHubInvalidJSONError(e) from e

    pr = PRInfo.from_gh_json(pr_data)

    # Create worktree for the PR branch
    # Use the PR head branch name, prefixed with pr-{number}-
    branch_name = f"pr-{pr.number}-{pr.head_branch}"
    wt = create_worktree(path=path, branch=branch_name, base=base, cwd=repo_root)

    return wt.path


def clean_merged_prs(cwd: Path | None = None) -> list[Path]:
    """Remove worktrees for merged/closed pull requests."""
    repo_root = get_repo_root(cwd)
    owner, repo = get_repo_info(repo_root)

    worktrees = list_worktrees(repo_root)
    removed = []

    for wt in worktrees:
        # Skip main worktree
        if wt.is_main:
            continue

        # Check if this looks like a PR worktree (branch starts with pr-{number}-)
        if not wt.branch.startswith("pr-"):
            continue

        # Extract PR number from branch name
        # Format: pr-{number}-{branch-name}
        parts = wt.branch.split("-", 2)
        if len(parts) < PR_BRANCH_PARTS_MIN:
            continue

        try:
            pr_number = int(parts[1])
        except ValueError:
            continue

        # Check PR state via gh
        args = [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "state",
        ]

        result = run_gh_command(args, cwd=repo_root)
        if result.returncode != 0:
            # If we can't check, skip this worktree
            continue

        try:
            pr_data = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue

        pr_state = pr_data.get("state", "").lower()

        # Remove if merged or closed
        if pr_state in ("merged", "closed"):
            try:
                remove_worktree(wt.path, cwd=repo_root)
                removed.append(wt.path)
            except WorktreeError:
                # If removal fails, continue with others
                pass

    return removed


if __name__ == "__main__":
    # Quick manual test
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        try:
            owner, repo = get_repo_info()
            print(f"Repo: {owner}/{repo}")  # noqa: T201
            prs = get_pr_list(state="open", limit=5)
            for pr in prs:
                print(f"  #{pr.number}: {pr.title} ({pr.head_branch})")  # noqa: T201
        except GitHubError as e:
            print(f"Error: {e}", file=sys.stderr)  # noqa: T201
            sys.exit(1)
