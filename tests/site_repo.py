"""Dataset D13 (test strategy v3 §3): a temp landing-page repository.

`paths.site_repo()` reads `JURA_SITE_REPO`, which `tests/conftest.py` points at `tmp_path/site`.
`make()` builds a git repository there with one commit on `main`; `branch()` adds a task branch
based on `main` with a commit of its own; `merge()` merges one commit into `main`, as Ting Yu does
by hand. Git runs with no global or system config, so nothing on this Mac changes what it does.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from jura_growth import paths

ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env={**os.environ, **ENV}
    )
    return done.stdout.strip()


def make(repo: Path | None = None) -> Path:
    """A repository at `paths.site_repo()` with one commit on `main`."""
    repo = Path(repo or paths.site_repo())
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("landing page\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "First commit")
    return repo


def branch(name: str, *, repo: Path | None = None, file: str = "app.txt", text: str = "built\n") -> str:
    """Commit `file` on a new branch `name` from `main`; returns the commit's full SHA."""
    repo = Path(repo or paths.site_repo())
    git(repo, "switch", "-q", "-c", name, "main")
    (repo / file).write_text(text)
    git(repo, "add", file)
    git(repo, "commit", "-q", "-m", f"Build on {name}")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-q", "main")
    return sha


def commit_on(name: str, *, repo: Path | None = None, file: str = "later.txt") -> str:
    """One more commit on an existing branch; returns its SHA."""
    repo = Path(repo or paths.site_repo())
    git(repo, "switch", "-q", name)
    (repo / file).write_text("pushed after the approval\n")
    git(repo, "add", file)
    git(repo, "commit", "-q", "-m", f"Later work on {name}")
    sha = git(repo, "rev-parse", "HEAD")
    git(repo, "switch", "-q", "main")
    return sha


def merge(sha: str, *, repo: Path | None = None) -> None:
    """Merge exactly `sha` into `main`, as the printed release plan says."""
    repo = Path(repo or paths.site_repo())
    git(repo, "merge", "-q", "--no-ff", "-m", "Release", sha)


def main_head(repo: Path | None = None) -> str:
    return git(Path(repo or paths.site_repo()), "rev-parse", "main")
