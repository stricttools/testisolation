"""Always-on environment overrides.

Installed once per process before any conftest module is imported, so it binds
before a test body, a fixture, or even a module-level constant can read the
real environment. ``os.environ`` is mutated directly rather than through
``monkeypatch`` because the isolation is session-wide and must outlive every
individual test.

Extracted verbatim-in-behavior from rlsbl's test suite, with the
repo-specific constants moved into :mod:`testisolation.config`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .config import PRESERVE_VARS, Settings

# Ambient credential vectors stripped from the environment outright. Tests that
# need one re-set a FAKE value per-test via monkeypatch.
CREDENTIAL_VARS = (
    "SSH_AUTH_SOCK",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_API_TOKEN",
    "NPM_TOKEN",
    "NODE_AUTH_TOKEN",
    "PYPI_TOKEN",
    "TWINE_PASSWORD",
    "TWINE_USERNAME",
    "CARGO_REGISTRY_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "CLOUDFLARE_API_TOKEN",
    "CF_PAGES_API_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)

# Session temp dir holding the throwaway HOME / git config. Created by
# ``install``, removed by ``uninstall``. One per process -- each xdist worker
# installs its own, fully isolated.
_SESSION_ENV_DIR: Path | None = None


def session_env_dir() -> Path | None:
    """The throwaway env directory for this process, or None if not installed."""
    return _SESSION_ENV_DIR


def _preserve_toolchain_vars(settings: Settings, real_home: str) -> None:
    """Pin the opted-in toolchain caches BEFORE HOME is repointed.

    Every one of these defaults to a location under the real HOME; a throwaway
    HOME would send the toolchain into a cold rebuild (Go), or hide an
    importable module that a spawned system-python needs (PYTHONUSERBASE).
    They hold packages and build artifacts, not secrets -- which is why the
    enum is closed and why membership is opt-in per repo.
    """
    if not real_home:
        return
    gopath = os.environ.get("GOPATH") or f"{real_home}/go"
    for name in settings.preserve:
        env_var, default = PRESERVE_VARS[name]
        value = os.environ.get(env_var) or default.format(home=real_home, gopath=gopath)
        if value:
            os.environ[env_var] = value
            if env_var == "GOPATH":
                gopath = value


def install(settings: Settings) -> None:
    """Install the environment overrides for this process (idempotent)."""
    global _SESSION_ENV_DIR
    if _SESSION_ENV_DIR is not None:
        return

    real_home = os.environ.get("HOME", "")
    _preserve_toolchain_vars(settings, real_home)

    session_dir = Path(tempfile.mkdtemp(prefix=settings.tmp_prefix))
    _SESSION_ENV_DIR = session_dir

    # Throwaway HOME + XDG dirs so nothing reads (or writes) real dotfiles.
    home = session_dir / "home"
    home.mkdir()
    (session_dir / "xdg-config").mkdir()
    (session_dir / "xdg-data").mkdir()
    (session_dir / "xdg-cache").mkdir()
    (session_dir / "xdg-state").mkdir()
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["XDG_CONFIG_HOME"] = str(session_dir / "xdg-config")
    os.environ["XDG_DATA_HOME"] = str(session_dir / "xdg-data")
    os.environ["XDG_CACHE_HOME"] = str(session_dir / "xdg-cache")
    os.environ["XDG_STATE_HOME"] = str(session_dir / "xdg-state")

    # Throwaway git global + system config. Carries protocol.ssh.allow=never
    # and a session commit identity so real-git fixtures that skip per-repo
    # identity still commit.
    #
    # maintenance.auto=false: without it a git commit may start
    # `git maintenance run --auto --detach` in the background, which keeps
    # writing into .git after the commit returns and races the removal of the
    # test's temporary directory ("unlinkat .git: directory not empty").
    #
    # We deliberately do NOT set core.hooksPath here. core.hooksPath overrides
    # REPO-LOCAL hooks too, which would silently disable a suite's real
    # pre-push-hook tests. A global config cannot inject hooks on its own, so
    # simply having no hooks entry in the throwaway global config is enough to
    # keep real user/global hooks from firing -- and omitting hooksPath is
    # required to keep repo-local hook tests working.
    gitconfig = session_dir / "gitconfig"
    gitconfig.write_text(
        "[user]\n"
        f"\tname = {settings.git_user_name}\n"
        f"\temail = {settings.git_user_email}\n"
        '[protocol "ssh"]\n'
        "\tallow = never\n"
        "[init]\n"
        "\tdefaultBranch = main\n"
        "[maintenance]\n"
        "\tauto = false\n"
    )
    os.environ["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    os.environ["GIT_CONFIG_SYSTEM"] = str(gitconfig)

    # An explicit throwaway identity in the environment as well, so a git
    # invocation that ignores the global config file still cannot commit as the
    # real developer.
    os.environ["GIT_AUTHOR_NAME"] = settings.git_user_name
    os.environ["GIT_AUTHOR_EMAIL"] = settings.git_user_email
    os.environ["GIT_COMMITTER_NAME"] = settings.git_user_name
    os.environ["GIT_COMMITTER_EMAIL"] = settings.git_user_email

    # Transport lockdown: only the local ``file`` protocol may be used by git;
    # ssh / proxy invocations hard-fail; no interactive or credential prompt
    # can ever block a test or leak a real credential.
    os.environ["GIT_ALLOW_PROTOCOL"] = "file"
    os.environ["GIT_SSH_COMMAND"] = "/bin/false"
    os.environ["GIT_PROXY_COMMAND"] = "/bin/false"
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    os.environ["GIT_ASKPASS"] = "/bin/false"

    # Kill ambient credentials outright. Per-test fixtures re-set FAKE values
    # via monkeypatch for the tests that need one.
    # ``GIT_ASKPASS`` is deliberately NOT in this list: the transport lockdown
    # above pins it to /bin/false, which is strictly stronger than unsetting it.
    for var in CREDENTIAL_VARS:
        os.environ.pop(var, None)


def uninstall() -> None:
    """Tear down the throwaway env directory for this process."""
    global _SESSION_ENV_DIR
    if _SESSION_ENV_DIR is not None:
        shutil.rmtree(_SESSION_ENV_DIR, ignore_errors=True)
        _SESSION_ENV_DIR = None
