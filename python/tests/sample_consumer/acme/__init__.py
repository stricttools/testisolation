"""A miniature library that touches everything the isolation governs."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path


def config_path() -> Path:
    """Where the tool keeps its user configuration."""
    return Path.home() / ".config" / "acme" / "config.toml"


def save_config(text: str) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def init_repo(directory: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=directory, check=True)


def commit_all(directory: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=directory, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=directory, check=True)
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def publish(directory: Path, remote: str) -> None:
    """Push the current branch. Deliberately unmocked in one of the tests."""
    subprocess.run(["git", "push", remote, "main"], cwd=directory, check=True)


def fetch_release_metadata(url: str) -> dict:
    """Fetch JSON over the network -- the thing tests must never really do."""
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode())
