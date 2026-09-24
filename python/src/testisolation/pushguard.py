"""Structural push guard: a real ``git push`` to a NON-LOCAL remote is impossible.

The originating forensics: a test mocked a command's ``run``/``run_gh`` helpers
but NOT its push helper, so a full-suite run executed a REAL
``git push origin main`` from the real development repository. This guard
closes that class of bug at the innermost real-execution boundary --
``subprocess.Popen``, which ``subprocess.run`` funnels through. A test that
mocks ``subprocess.run`` in some namespace never reaches Popen, so the guard
composes with existing mock layering instead of fighting it.

Local filesystem paths and ``file://`` URLs are ALLOWED: suites push to local
bare repos constantly.

``pytest.fail`` raises ``Failed`` (a ``BaseException`` subclass), so it slips
past production ``except Exception`` handlers and surfaces loudly even when a
caller would otherwise swallow the push error.
"""

from __future__ import annotations

import os
import re
import subprocess

import pytest


def remote_is_local(url: str | None) -> bool:
    """Classify a git remote URL/path as local (allowed) or non-local (blocked).

    Local: ``file://`` URLs and bare filesystem paths (absolute or relative).
    Non-local: any URL with a non-``file`` scheme (https://, ssh://, git://)
    and SCP-like syntax (``git@host:owner/repo``). ``None``/empty is treated as
    non-local (cannot prove locality -> block loudly).
    """
    if not url:
        return False
    if url.startswith("file://"):
        return True
    # Explicit scheme (scheme://...): only file:// is local.
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        return url.startswith("file://")
    # SCP-like: [user@]host:path -- non-local. A bare Windows drive letter is
    # irrelevant on the Linux CI/dev hosts, so any ``host:`` form is remote.
    if re.match(r"^[^/\\]+@[^/\\]+:", url) or re.match(r"^[A-Za-z0-9.\-]+:", url):
        return False
    # Otherwise a filesystem path (absolute or relative) -- local.
    return True


def extract_push_remote(cmd) -> str | None:
    """Return the remote argument of a ``git push`` command list, or None."""
    tokens = [str(t) for t in cmd]
    try:
        push_idx = tokens.index("push")
    except ValueError:
        return None
    for tok in tokens[push_idx + 1:]:
        if tok.startswith("-"):
            continue
        return tok
    return None


def make_guarded_popen(real_popen):
    """Wrap ``real_popen`` so a non-local ``git push`` fails the test."""

    def _resolve_remote_url(remote: str, cwd) -> str | None:
        try:
            proc = real_popen(
                ["git", "remote", "get-url", remote],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
            )
            out, _ = proc.communicate(timeout=10)
            if proc.returncode == 0:
                return out.strip()
        except Exception:
            return None
        return None

    def guarded_popen(args, *a, **kw):
        cmd = args
        if (
            isinstance(cmd, (list, tuple))
            and len(cmd) >= 2
            and os.path.basename(str(cmd[0])) == "git"
            and "push" in [str(c) for c in cmd]
        ):
            remote = extract_push_remote(cmd)
            cwd = kw.get("cwd")
            if len(a) >= 9:  # positional cwd is the 9th arg of Popen.__init__
                cwd = a[8]
            # A bare remote NAME (no scheme, no ':', no '/') must be resolved
            # to its URL; anything else is used as-is.
            if remote and not re.search(r"[:/\\]", remote):
                url = _resolve_remote_url(remote, cwd)
            else:
                url = remote
            if not remote_is_local(url):
                pytest.fail(
                    "BLOCKED: real 'git push' to a non-local remote from the "
                    f"test suite. cmd={list(cmd)!r} remote={remote!r} "
                    f"resolved_url={url!r} cwd={cwd!r}. A test is exercising a "
                    "push path without mocking it; mock the push helper / the "
                    "push subprocess, or point origin at a local bare repo.",
                    pytrace=False,
                )
        return real_popen(args, *a, **kw)

    return guarded_popen
