"""Bare-run refusal and the TMPDIR-inside-repo refusal.

Two independent startup guards:

* **Bare-run threshold.** A run collecting MORE than the threshold is treated
  as a full-ish run and must go through the sandbox runner (which exports the
  sandbox env var). Small targeted runs stay bare-runnable so the inner
  development loop is fast -- the always-on environment isolation plus the push/chdir/socket
  guards still protect those.
* **TMPDIR-inside-repo refusal.** Fixture temp directories inside the repo let
  unanchored git commands walk UP into the real repo and commit junk. Both the
  pytest ``--basetemp`` and the ``TMPDIR`` environment variable are checked
  against the repository root, which is derived from pytest's ``rootpath``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from .config import Settings


def enforce_threshold(settings: Settings, count: int) -> None:
    """Raise ``UsageError`` if a bare run of ``count`` tests is too large.

    No-op when the project declared ``stricttest_sandbox_required = false``,
    when the run is already inside the sandbox, or when the run is a small
    targeted slice.
    """
    if not settings.sandbox_required:
        return
    if os.environ.get(settings.sandbox_env) == "1":
        return
    if count <= settings.threshold:
        return
    raise pytest.UsageError(
        f"Refusing to run {count} tests bare (> {settings.threshold}). "
        "A full-ish suite run must go through the sandbox runner:\n\n"
        f"    {settings.runner_command}\n\n"
        "The sandbox binds the real repo read-only, runs in a writable "
        "throwaway copy on a private tmpfs, and has no network -- so a stray "
        "real git push, an unanchored commit into the dev repo, or a live API "
        "call is physically impossible. Small targeted runs stay allowed bare "
        f"for iteration speed (<= {settings.threshold} tests: a single file or "
        f"a -k slice). To run the full suite, use {settings.runner_command} "
        f"(which must export {settings.sandbox_env}=1)."
    )


def enforce_tmp_outside_repo(repo_root: Path, basetemp) -> None:
    """Refuse to run if the temp root is inside the repository.

    Junk-commit incidents happen because a TMPDIR (or pytest basetemp) points
    inside the repo: fixtures create non-git directories there, and unanchored
    git commands walk UP into the real repo and commit junk. Fail loudly at
    startup rather than let that recur.
    """
    candidates = []
    if basetemp:
        candidates.append(Path(basetemp))
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        candidates.append(Path(tmpdir))
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved == repo_root or repo_root in resolved.parents:
            raise pytest.UsageError(
                f"TMPDIR/basetemp {resolved} is inside the repository "
                f"{repo_root} -- refusing. Fixture temp dirs inside the repo "
                f"let unanchored git commands walk up into the real repo and "
                f"commit junk. Point TMPDIR at a location OUTSIDE the "
                f"repository and re-run."
            )
