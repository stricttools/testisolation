"""The pytest plugin entry point (``pytest11``).

Installing testisolation IS adoption. Every hook below binds unconditionally once
the project's safety keys validate; there is no opt-in switch and no runtime
degradation path -- a project either declares its stance and gets the isolation, or
the session aborts.

Ordering matters and is deliberate:

1. ``pytest_load_initial_conftests`` -- the earliest hook that already has a
   parsed ini file. Validation, the TMPDIR refusal, environment overrides and
   the socket guard all bind HERE, before any conftest module is imported. A
   conftest that reads ``HOME`` at import time therefore sees the throwaway one.
2. ``pytest_configure`` -- marker registration and a second TMPDIR check now
   that ``--basetemp`` is fully resolved.
3. ``pytest_collection_modifyitems`` / ``pytest_xdist_node_collection_finished``
   -- the bare-run threshold, once the selected test count is known.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from . import config as _config
from . import env_overrides, sandbox, socketguard
from .config import Settings
from .pushguard import make_guarded_popen

_settings: Settings | None = None


def settings() -> Settings:
    """The resolved settings for this session (raises if not yet configured)."""
    if _settings is None:
        raise RuntimeError("testisolation is not configured yet")
    return _settings


def pytest_addoption(parser):
    _config.add_ini_options(parser)


def _basetemp_of(cfg):
    for holder in ("known_args_namespace", "option"):
        namespace = getattr(cfg, holder, None)
        value = getattr(namespace, "basetemp", None)
        if value:
            return value
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    """Bind every isolation piece before any conftest module is imported."""
    global _settings
    resolved = _config.resolve(early_config)
    _settings = resolved

    repo_root = Path(early_config.rootpath).resolve()
    sandbox.enforce_tmp_outside_repo(repo_root, _basetemp_of(early_config))

    # The isolation allocates its throwaway directory with ``tempfile``, so it only
    # runs once TMPDIR has been proven to live outside the repository.
    env_overrides.install(resolved)
    socketguard.install(resolved)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "repo_cwd: opt a test OUT of the autouse tmp-cwd isolation. Reserved "
        "for tests that must resolve the real project from the process cwd.",
    )
    global _settings
    if _settings is None:  # pragma: no cover - defensive, ordering is fixed
        _settings = _config.resolve(config)
        env_overrides.install(_settings)
        socketguard.install(_settings)
    sandbox.enforce_tmp_outside_repo(
        Path(config.rootpath).resolve(), _basetemp_of(config)
    )


def pytest_unconfigure(config):
    """Tear down the throwaway env directory for this process."""
    env_overrides.uninstall()


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    """Refuse a bare full-ish run outside the sandbox.

    ``trylast`` so this runs AFTER pytest's own ``-k`` / ``-m`` deselection,
    which mutates ``items`` in place -- the count then reflects the SELECTED
    tests, so a ``-k`` slice of a big file stays under the threshold and runs
    bare instead of being refused on the pre-deselection total.

    Enforcement is split by execution topology:

    * Single process (no xdist): ``items`` is the full set here -- enforce.
    * xdist worker (``PYTEST_XDIST_WORKER`` set): a shard; defer to the
      controller so the error surfaces once, not once per worker.
    * xdist controller (``numprocesses`` set): ``items`` is empty here because
      workers do the collecting -- defer to
      ``pytest_xdist_node_collection_finished`` which sees the real count.
    """
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    if getattr(config.option, "numprocesses", None):
        return
    sandbox.enforce_threshold(settings(), len(items))


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    """xdist controller: enforce the threshold once collection lands.

    The controller does not collect items itself; each worker reports its
    collected ``ids`` here. All workers collect the same full set, so the first
    report carries the true test count -- enforce on it.

    ``optionalhook`` so the plugin loads cleanly in projects without xdist.
    """
    sandbox.enforce_threshold(settings(), len(ids))


@pytest.fixture(autouse=True)
def _testisolation_chdir_into_tmp(request, tmp_path, monkeypatch):
    """Autouse: never let a test run with the process cwd at the real repo.

    A test whose process cwd is the real repo can make every unanchored git
    command (status/commit/push, file generation, scaffolding) operate on the
    development repo. Chdir-ing each test into its own ``tmp_path`` makes
    implicit repo-cwd reliance a visible failure instead of silent real-repo
    pollution. Fixtures that chdir into their own ``tmp_path`` (the same
    ``tmp_path`` object) compose cleanly -- they land in the same directory.
    Tests that genuinely need the repo cwd must anchor explicitly, or opt out
    with ``@pytest.mark.repo_cwd``.
    """
    if request.node.get_closest_marker("repo_cwd") is not None:
        yield
        return
    monkeypatch.chdir(tmp_path)
    yield


@pytest.fixture(autouse=True)
def _testisolation_guard_nonlocal_push():
    """Autouse guard: block any real ``git push`` to a non-local remote."""
    guarded = make_guarded_popen(subprocess.Popen)
    with patch("subprocess.Popen", side_effect=guarded):
        yield
