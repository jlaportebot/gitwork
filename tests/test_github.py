"""Tests for gitwork GitHub integration module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from gitwork.core import Worktree, WorktreeError
from gitwork.github import (
    GitHubError,
    PRInfo,
    checkout_pr,
    clean_merged_prs,
    get_pr_list,
    get_repo_info,
)

PR_NUMBER_1 = 1
PR_NUMBER_2 = 2
PR_NUMBER_123 = 123
PR_NUMBER_999 = 999
PR_NUMBER_456 = 456
EXPECTED_PR_COUNT = 2
EXPECTED_REMOVED_COUNT = 1


class TestPRInfo:
    """Tests for PRInfo dataclass."""

    def test_pr_info_creation(self) -> None:
        """Test creating PRInfo from data."""
        pr = PRInfo(
            number=PR_NUMBER_123,
            title="Test PR",
            head_branch="feature-branch",
            head_repo="owner/repo",
            state="open",
            is_draft=False,
        )
        assert pr.number == PR_NUMBER_123
        assert pr.title == "Test PR"
        assert pr.head_branch == "feature-branch"
        assert pr.head_repo == "owner/repo"
        assert pr.state == "open"
        assert pr.is_draft is False

    def test_pr_info_from_gh_json(self) -> None:
        """Test creating PRInfo from gh API JSON."""
        gh_json = {
            "number": PR_NUMBER_456,
            "title": "Feature PR",
            "headRefName": "feat/new-feature",
            "headRepository": {"nameWithOwner": "owner/repo"},
            "state": "OPEN",
            "isDraft": True,
        }
        pr = PRInfo.from_gh_json(gh_json)
        assert pr.number == PR_NUMBER_456
        assert pr.title == "Feature PR"
        assert pr.head_branch == "feat/new-feature"
        assert pr.head_repo == "owner/repo"
        assert pr.state == "open"
        assert pr.is_draft is True


class TestGetRepoInfo:
    """Tests for get_repo_info function."""

    @patch("gitwork.github.get_repo_root")
    @patch("subprocess.run")
    def test_get_repo_info_success_https(
        self, mock_run: Mock, mock_get_repo_root: Mock, tmp_path: Path
    ) -> None:
        """Test getting repo info from HTTPS GitHub remote."""
        mock_get_repo_root.return_value = tmp_path
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo.git"
        mock_run.return_value = mock_result

        owner, repo = get_repo_info(tmp_path)
        assert owner == "owner"
        assert repo == "repo"

    @patch("gitwork.github.get_repo_root")
    @patch("subprocess.run")
    def test_get_repo_info_success_ssh(
        self, mock_run: Mock, mock_get_repo_root: Mock, tmp_path: Path
    ) -> None:
        """Test getting repo info from SSH GitHub remote."""
        mock_get_repo_root.return_value = tmp_path
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:owner/repo.git"
        mock_run.return_value = mock_result

        owner, repo = get_repo_info(tmp_path)
        assert owner == "owner"
        assert repo == "repo"

    @patch("gitwork.github.get_repo_root")
    @patch("subprocess.run")
    def test_get_repo_info_no_remote(
        self, mock_run: Mock, mock_get_repo_root: Mock, tmp_path: Path
    ) -> None:
        """Test error when no remote exists."""
        mock_get_repo_root.return_value = tmp_path
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "No such remote 'origin'"
        mock_run.return_value = mock_result

        with pytest.raises(GitHubError, match="Failed to get remote URL"):
            get_repo_info(tmp_path)

    @patch("gitwork.github.get_repo_root")
    @patch("subprocess.run")
    def test_get_repo_info_non_github(
        self, mock_run: Mock, mock_get_repo_root: Mock, tmp_path: Path
    ) -> None:
        """Test error when remote is not GitHub."""
        mock_get_repo_root.return_value = tmp_path
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "https://gitlab.com/owner/repo.git"
        mock_run.return_value = mock_result

        with pytest.raises(GitHubError, match="not a GitHub repository"):
            get_repo_info(tmp_path)

    @patch("gitwork.github.get_repo_root")
    def test_get_repo_info_not_git_repo(self, mock_get_repo_root: Mock, tmp_path: Path) -> None:
        """Test error when not in a git repo."""
        mock_get_repo_root.side_effect = WorktreeError("Not a git repository")

        with pytest.raises(WorktreeError):
            get_repo_info(tmp_path)


class TestGetPRList:
    """Tests for get_pr_list function."""

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.get_repo_info")
    def test_get_pr_list_success(
        self,
        mock_get_repo_info: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test successful PR list retrieval."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            [
                {
                    "number": PR_NUMBER_1,
                    "title": "PR 1",
                    "headRefName": "branch-1",
                    "headRepository": {"nameWithOwner": "owner/repo"},
                    "state": "OPEN",
                    "isDraft": False,
                },
                {
                    "number": PR_NUMBER_2,
                    "title": "PR 2",
                    "headRefName": "branch-2",
                    "headRepository": {"nameWithOwner": "owner/repo"},
                    "state": "CLOSED",
                    "isDraft": False,
                },
            ]
        )
        mock_run_gh.return_value = mock_result

        prs = get_pr_list(tmp_path, state="open")

        assert len(prs) == EXPECTED_PR_COUNT
        assert prs[0].number == PR_NUMBER_1
        assert prs[0].title == "PR 1"
        assert prs[1].number == PR_NUMBER_2
        assert prs[1].state == "closed"

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.get_repo_info")
    def test_get_pr_list_gh_failure(
        self,
        mock_get_repo_info: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test handling of gh CLI failure."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "gh auth failed"
        mock_run_gh.return_value = mock_result

        with pytest.raises(GitHubError, match="gh CLI failed"):
            get_pr_list(tmp_path)

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.get_repo_info")
    def test_get_pr_list_invalid_json(
        self,
        mock_get_repo_info: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test handling of invalid JSON from gh."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run_gh.return_value = mock_result

        with pytest.raises(GitHubError, match="Invalid JSON"):
            get_pr_list(tmp_path)


class TestCheckoutPR:
    """Tests for checkout_pr function."""

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.create_worktree")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.get_repo_info")
    def test_checkout_pr_success(
        self,
        mock_get_repo_info: Mock,
        mock_run_gh: Mock,
        mock_create_wt: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test successful PR checkout."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_pr_view = Mock()
        mock_pr_view.returncode = 0
        mock_pr_view.stdout = json.dumps(
            {
                "number": PR_NUMBER_123,
                "title": "Test PR",
                "headRefName": "feature-branch",
                "headRepository": {"nameWithOwner": "owner/repo"},
                "state": "OPEN",
                "isDraft": False,
            }
        )
        mock_run_gh.return_value = mock_pr_view

        mock_create_wt.return_value = Worktree(
            path=tmp_path / "pr-123",
            branch="pr-123-feature-branch",
            commit="abc123",
        )

        wt_path = checkout_pr(PR_NUMBER_123, tmp_path / "pr-123", tmp_path)

        assert wt_path == tmp_path / "pr-123"
        mock_create_wt.assert_called_once()

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.get_repo_info")
    def test_checkout_pr_not_found(
        self,
        mock_get_repo_info: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test PR not found error."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "pull request not found"
        mock_run_gh.return_value = mock_result

        with pytest.raises(GitHubError, match=f"PR #{PR_NUMBER_999} not found"):
            checkout_pr(PR_NUMBER_999, tmp_path / "pr-999", tmp_path)

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.get_repo_info")
    def test_checkout_pr_invalid_json(
        self,
        mock_get_repo_info: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test handling of invalid JSON from gh pr view."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json"
        mock_run_gh.return_value = mock_result

        with pytest.raises(GitHubError, match="Invalid JSON"):
            checkout_pr(PR_NUMBER_123, tmp_path / "pr-123", tmp_path)


class TestCleanMergedPRs:
    """Tests for clean_merged_prs function."""

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.list_worktrees")
    @patch("gitwork.github.get_repo_info")
    def test_clean_merged_prs_no_worktrees(
        self,
        mock_get_repo_info: Mock,
        mock_list_wt: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test clean with no PR worktrees."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")
        mock_list_wt.return_value = []

        removed = clean_merged_prs(tmp_path)
        assert removed == []

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.remove_worktree")
    @patch("gitwork.github.get_repo_info")
    @patch("gitwork.github.list_worktrees")
    @patch("gitwork.github.run_gh_command")
    def test_clean_merged_prs_removes_merged(  # noqa: PLR0913
        self,
        mock_run_gh: Mock,
        mock_list_wt: Mock,
        mock_get_repo_info: Mock,
        mock_remove_wt: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test cleaning removes worktrees for merged PRs."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")

        # Create a worktree that looks like a PR worktree
        pr_wt_path = tmp_path / "pr-123"
        pr_wt_path.mkdir(parents=True)

        mock_list_wt.return_value = [
            Worktree(
                path=pr_wt_path,
                branch="pr-123-feature-branch",
                commit="abc123",
                is_main=False,
            )
        ]

        # Mock gh pr view to return merged state
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "number": PR_NUMBER_123,
                "title": "Merged PR",
                "headRefName": "feature-branch",
                "headRepository": {"nameWithOwner": "owner/repo"},
                "state": "MERGED",
                "isDraft": False,
            }
        )
        mock_run_gh.return_value = mock_result

        removed = clean_merged_prs(tmp_path)

        assert len(removed) == 1
        assert removed[0] == pr_wt_path
        mock_remove_wt.assert_called_once()

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.list_worktrees")
    @patch("gitwork.github.get_repo_info")
    def test_clean_merged_prs_skips_open(
        self,
        mock_get_repo_info: Mock,
        mock_list_wt: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test cleaning skips open PRs."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")

        pr_wt_path = tmp_path / "pr-123"
        pr_wt_path.mkdir(parents=True)

        mock_list_wt.return_value = [
            Worktree(
                path=pr_wt_path,
                branch="pr-123-feature-branch",
                commit="abc123",
                is_main=False,
            )
        ]

        # Mock gh pr view to return open state
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "number": PR_NUMBER_123,
                "title": "Open PR",
                "headRefName": "feature-branch",
                "headRepository": {"nameWithOwner": "owner/repo"},
                "state": "OPEN",
                "isDraft": False,
            }
        )
        mock_run_gh.return_value = mock_result

        removed = clean_merged_prs(tmp_path)

        assert removed == []

    @patch("gitwork.github.get_repo_root")
    @patch("gitwork.github.run_gh_command")
    @patch("gitwork.github.list_worktrees")
    @patch("gitwork.github.get_repo_info")
    def test_clean_merged_prs_skips_non_pr_worktrees(
        self,
        mock_get_repo_info: Mock,
        mock_list_wt: Mock,
        mock_run_gh: Mock,
        mock_get_repo_root: Mock,
        tmp_path: Path,
    ) -> None:
        """Test cleaning skips non-PR worktrees."""
        mock_get_repo_root.return_value = tmp_path
        mock_get_repo_info.return_value = ("owner", "repo")

        mock_list_wt.return_value = [
            Worktree(
                path=tmp_path / "feature-branch",
                branch="feature-branch",
                commit="abc123",
                is_main=False,
            )
        ]

        removed = clean_merged_prs(tmp_path)

        assert removed == []
        mock_run_gh.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
