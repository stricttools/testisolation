"""An ordinary git-using suite runs green under the isolation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import acme


def test_commit_uses_the_throwaway_identity(repo: Path):
    acme.init_repo(repo)
    (repo / "file.txt").write_text("hello")
    sha = acme.commit_all(repo, "add file")
    assert len(sha) == 40

    author = subprocess.run(
        ["git", "log", "-1", "--format=%ae"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert author.endswith(".invalid")


def test_publishing_to_a_local_bare_remote_works(repo: Path, tmp_path: Path):
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    acme.init_repo(repo)
    (repo / "file.txt").write_text("hello")
    acme.commit_all(repo, "add file")
    acme.publish(repo, str(bare))

    log = subprocess.run(
        ["git", "log", "-1", "--format=%s", "main"],
        cwd=bare,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "add file"


def test_the_suite_never_runs_inside_the_project_checkout():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    assert out.returncode != 0
