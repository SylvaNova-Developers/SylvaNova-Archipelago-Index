from __future__ import annotations

from dataclasses import dataclass

from github import Github, GithubException
from github.Repository import Repository


@dataclass(frozen=True)
class OpenedPullRequest:
    number: int
    url: str
    branch: str


class IndexPullRequestClient:
    def __init__(self, *, token: str, repo_full_name: str, base_branch: str, branch_prefix: str):
        self._gh = Github(token)
        self._repo: Repository = self._gh.get_repo(repo_full_name)
        self._base_branch = base_branch
        self._branch_prefix = branch_prefix

    def open_apworld_pr(
        self,
        *,
        apworld: str,
        toml_body: str,
        requested_by: str,
    ) -> OpenedPullRequest:
        path = f"index/{apworld}.toml"
        if self._path_exists_on_base(path):
            raise RuntimeError(f"`{path}` already exists on {self._base_branch}")

        base_ref = self._repo.get_git_ref(f"heads/{self._base_branch}")
        base_sha = base_ref.object.sha
        branch = f"{self._branch_prefix}{apworld}"
        self._ensure_branch(branch, base_sha)

        self._repo.create_file(
            path=path,
            message=f"Add {apworld} apworld via Discord request",
            content=toml_body,
            branch=branch,
        )

        title = f"Add {apworld}"
        body = (
            f"Automated apworld request from Discord user `{requested_by}`.\n\n"
            f"- File: `{path}`\n"
            f"- Opened by SylvaNova-apworld-bot scaffold\n\n"
            "Index `PR CI` will validate, fuzz, and auto-merge when green."
        )
        pr = self._repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=self._base_branch,
        )
        return OpenedPullRequest(number=pr.number, url=pr.html_url, branch=branch)

    def _path_exists_on_base(self, path: str) -> bool:
        try:
            self._repo.get_contents(path, ref=self._base_branch)
            return True
        except GithubException as exc:
            if exc.status == 404:
                return False
            raise

    def _ensure_branch(self, branch: str, base_sha: str) -> None:
        ref_name = f"refs/heads/{branch}"
        try:
            self._repo.create_git_ref(ref=ref_name, sha=base_sha)
        except GithubException as exc:
            if exc.status != 422:
                raise
            # Branch already exists — move it to current base so retries are clean.
            ref = self._repo.get_git_ref(f"heads/{branch}")
            ref.edit(base_sha, force=True)
            try:
                existing = self._repo.get_contents(f"index/{branch.removeprefix(self._branch_prefix)}.toml", ref=branch)
                # If a previous attempt left a file, leave it; create_file would fail.
                # Delete so create_file can succeed on retry.
                if not isinstance(existing, list):
                    self._repo.delete_file(
                        path=existing.path,
                        message=f"Reset {existing.path} before re-opening request PR",
                        sha=existing.sha,
                        branch=branch,
                    )
            except GithubException as inner:
                if inner.status != 404:
                    raise
