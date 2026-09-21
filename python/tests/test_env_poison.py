"""Env poisoning, proved from inside a session it governs."""

from __future__ import annotations

import os
import pwd
import subprocess
from pathlib import Path

import pytest

from stricttest import envpoison
from stricttest.config import PRESERVE_VARS

OK_TEST = "def test_ok():\n    assert True\n"


def _real_home() -> str:
    """The OS-level home, read from the passwd database rather than $HOME.

    This is the whole point of the meta-test: the isolation rewrote $HOME, so the
    only way to know what it rewrote is to ask the kernel's user database.
    """
    return pwd.getpwuid(os.getuid()).pw_dir


# ---------------------------------------------------------------------------
# Poisoned-home meta-tests: a test that reaches for "the home directory" must
# land in the throwaway one, never the developer's.
# ---------------------------------------------------------------------------


def test_home_is_not_the_real_home():
    assert os.environ["HOME"] != _real_home()


def test_home_lives_inside_this_session_throwaway_dir():
    session_dir = envpoison.session_env_dir()
    assert session_dir is not None
    assert session_dir in Path(os.environ["HOME"]).resolve().parents


def test_tilde_expansion_lands_in_the_throwaway_home():
    """The idiomatic way a test reaches for a dotfile is redirected."""
    assert Path("~").expanduser() == Path(os.environ["HOME"])
    assert Path.home() == Path(os.environ["HOME"])
    assert str(Path("~/.gitconfig").expanduser()).startswith(os.environ["HOME"])


def test_real_dotfiles_are_unreachable_through_the_home_directory():
    home = Path(os.environ["HOME"])
    for dotfile in (".gitconfig", ".ssh", ".netrc", ".config/gh/hosts.yml", ".npmrc"):
        assert not (home / dotfile).exists()


def test_userprofile_is_repointed_too():
    assert os.environ["USERPROFILE"] == os.environ["HOME"]


@pytest.mark.parametrize(
    "var", ["XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"]
)
def test_xdg_dirs_are_throwaway(var):
    session_dir = envpoison.session_env_dir()
    assert session_dir is not None
    assert Path(os.environ[var]).resolve().parent == session_dir.resolve()


# ---------------------------------------------------------------------------
# Git identity, config and transport lockdown
# ---------------------------------------------------------------------------


def test_git_config_points_at_the_throwaway_file():
    session_dir = envpoison.session_env_dir()
    for var in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"):
        path = Path(os.environ[var]).resolve()
        assert path.parent == session_dir.resolve()
        assert path.exists()


def test_git_reports_the_throwaway_identity(tmp_path):
    out = subprocess.run(
        ["git", "config", "--get", "user.email"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert out.stdout.strip() == "stricttest@example.invalid"


def test_git_commits_are_attributed_to_the_throwaway_identity(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    out = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae> | %cn <%ce>"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == (
        "stricttest <stricttest@example.invalid> | "
        "stricttest <stricttest@example.invalid>"
    )


def test_ssh_protocol_is_refused_by_the_throwaway_config(tmp_path):
    config_path = Path(os.environ["GIT_CONFIG_GLOBAL"]).read_text()
    assert "allow = never" in config_path


@pytest.mark.parametrize(
    "var,value",
    [
        ("GIT_ALLOW_PROTOCOL", "file"),
        ("GIT_SSH_COMMAND", "/bin/false"),
        ("GIT_PROXY_COMMAND", "/bin/false"),
        ("GIT_TERMINAL_PROMPT", "0"),
        ("GIT_ASKPASS", "/bin/false"),
    ],
)
def test_transport_lockdown(var, value):
    assert os.environ[var] == value


def test_https_clone_is_refused_by_the_transport_lockdown(tmp_path):
    """A live network clone cannot even start: the protocol is not permitted."""
    out = subprocess.run(
        ["git", "clone", "https://github.com/smm-h/stricttest.git", str(tmp_path / "c")],
        capture_output=True,
        text=True,
    )
    assert out.returncode != 0
    assert "transport 'https' not allowed" in (out.stderr + out.stdout).lower()


# ---------------------------------------------------------------------------
# Credential stripping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("var", envpoison.CREDENTIAL_VARS)
def test_credential_vars_are_stripped(var):
    assert var not in os.environ


def test_credential_list_covers_the_forge_and_registry_vectors():
    for expected in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "NPM_TOKEN"):
        assert expected in envpoison.CREDENTIAL_VARS


# ---------------------------------------------------------------------------
# The isolation binds before conftest import, not merely before the first test.
# ---------------------------------------------------------------------------


def test_isolation_binds_before_the_consumer_conftest_is_imported(inner):
    inner.write(
        {
            "conftest.py": (
                "import os\n"
                "# Captured at conftest IMPORT time -- the earliest a consumer\n"
                "# can observe the environment.\n"
                "HOME_AT_IMPORT = os.environ['HOME']\n"
            ),
            "test_import_time.py": (
                "import os, pwd\n"
                "from conftest import HOME_AT_IMPORT\n"
                "\n"
                "def test_home_was_already_poisoned_at_import():\n"
                "    real = pwd.getpwuid(os.getuid()).pw_dir\n"
                "    assert HOME_AT_IMPORT != real\n"
                "    assert 'stricttest-env-' in HOME_AT_IMPORT\n"
            ),
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_throwaway_dir_uses_the_configured_prefix(inner):
    inner.write(
        {
            "test_prefix.py": (
                "import os\n"
                "def test_prefix():\n"
                "    assert 'consumer-env-' in os.environ['HOME']\n"
            )
        },
        ini={"stricttest_tmp_prefix": "consumer-env-"},
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_configured_commit_identity_is_used(inner):
    inner.write(
        {
            "test_identity.py": (
                "import os, subprocess\n"
                "def test_identity(tmp_path):\n"
                "    out = subprocess.run(['git', 'config', '--get', 'user.name'],\n"
                "                         capture_output=True, text=True, cwd=tmp_path)\n"
                "    assert out.stdout.strip() == 'acme-tests'\n"
                "    assert os.environ['GIT_AUTHOR_NAME'] == 'acme-tests'\n"
            )
        },
        ini={"stricttest_git_user_name": "acme-tests"},
    )
    inner.run("-q").assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Preservation carve-outs: a CLOSED enum, opt-in per repo.
# ---------------------------------------------------------------------------


def test_preserve_rejects_arbitrary_env_var_names(inner):
    inner.write({"test_ok.py": OK_TEST}, ini={"stricttest_preserve": ["GITHUB_TOKEN"]})
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "closed enum" in combined
    assert "Unknown: GITHUB_TOKEN" in combined
    # The error names the whole valid set so the fix is mechanical.
    for name in PRESERVE_VARS:
        assert name in combined


def test_preserve_rejects_a_near_miss_name(inner):
    inner.write({"test_ok.py": OK_TEST}, ini={"stricttest_preserve": ["gocache"]})
    result = inner.run("-q")
    assert result.ret != 0
    assert "Unknown: gocache" in "\n".join(result.outlines + result.errlines)


def test_preserved_caches_survive_the_home_repoint(inner):
    inner.write(
        {
            "test_preserve.py": (
                "import os\n"
                "def test_go_caches_point_outside_the_throwaway_home():\n"
                "    home = os.environ['HOME']\n"
                "    for var in ('GOPATH', 'GOMODCACHE', 'GOCACHE'):\n"
                "        assert var in os.environ, var\n"
                "        assert not os.environ[var].startswith(home), var\n"
                "    assert os.environ['GOMODCACHE'].startswith(os.environ['GOPATH'])\n"
            )
        },
        ini={"stricttest_preserve": ["go_path", "go_mod_cache", "go_cache"]},
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_unpreserved_caches_are_not_pinned(inner):
    """Opt-in means opt-in: an unlisted cache is left to follow the new HOME."""
    inner.write(
        {
            "test_no_preserve.py": (
                "import os\n"
                "def test_cargo_home_not_pinned():\n"
                "    assert 'CARGO_HOME' not in os.environ\n"
            )
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_preserve_enum_maps_only_to_toolchain_vars():
    """A credential-bearing variable must never be representable here."""
    env_vars = {var for var, _ in PRESERVE_VARS.values()}
    assert not (env_vars & set(envpoison.CREDENTIAL_VARS))
