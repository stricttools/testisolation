"""The structural push guard: a real push to a non-local remote is impossible."""

from __future__ import annotations

import subprocess

import pytest

from testisolation.pushguard import extract_push_remote, make_guarded_popen, remote_is_local


@pytest.mark.parametrize(
    "url",
    [
        "file:///srv/bare/repo.git",
        "/srv/bare/repo.git",
        "../bare/repo.git",
        "./repo.git",
    ],
)
def test_local_remotes_are_allowed(url):
    assert remote_is_local(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/stricttools/testisolation.git",
        "ssh://git@github.com/stricttools/testisolation.git",
        "git://example.com/repo.git",
        "git@github.com:stricttools/testisolation.git",
        "github.com:stricttools/testisolation.git",
        None,
        "",
    ],
)
def test_non_local_remotes_are_blocked(url):
    assert remote_is_local(url) is False


@pytest.mark.parametrize(
    "cmd,expected",
    [
        (["git", "push", "origin", "main"], "origin"),
        (["git", "push", "--force-with-lease", "origin", "main"], "origin"),
        (["git", "push"], None),
        (["git", "status"], None),
        (["git", "push", "--tags"], None),
    ],
)
def test_extract_push_remote(cmd, expected):
    assert extract_push_remote(cmd) == expected


# ---------------------------------------------------------------------------
# Interception. The guard is autouse in this very session, so these tests
# exercise the shipped code path rather than a reconstruction of it.
# ---------------------------------------------------------------------------


def test_real_push_to_a_nonlocal_remote_is_intercepted():
    """A subprocess ``git push`` at an https remote fails the test loudly.

    ``pytest.fail`` raises ``Failed`` -- a ``BaseException`` -- specifically so
    a production ``except Exception`` cannot swallow the refusal, so this test
    catches ``BaseException`` on purpose.
    """
    with pytest.raises(BaseException) as excinfo:
        subprocess.run(
            ["git", "push", "https://example.invalid/nope.git", "main"],
            capture_output=True,
        )
    message = str(excinfo.value)
    assert "BLOCKED: real 'git push' to a non-local remote" in message
    assert "https://example.invalid/nope.git" in message


def test_scp_style_remote_is_intercepted():
    with pytest.raises(BaseException) as excinfo:
        subprocess.run(
            ["git", "push", "git@example.invalid:owner/repo.git", "main"],
            capture_output=True,
        )
    assert "BLOCKED" in str(excinfo.value)


def test_the_guard_is_not_swallowed_by_a_broad_except_handler():
    """The failure class must slip past ``except Exception``."""
    swallowed = False
    try:
        try:
            subprocess.run(
                ["git", "push", "https://example.invalid/nope.git", "main"],
                capture_output=True,
            )
        except Exception:  # noqa: BLE001 - deliberately modelling sloppy production code
            swallowed = True
    except BaseException as exc:
        assert "BLOCKED" in str(exc)
    assert swallowed is False


def test_push_to_a_local_bare_repo_is_allowed(tmp_path):
    """Fixtures push to local bare repos constantly; that must keep working."""
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    (work / "f.txt").write_text("x")
    subprocess.run(["git", "add", "f.txt"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=work, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=work, check=True)

    # No refusal: the guard resolves the remote NAME to a filesystem path.
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=work, check=True)

    out = subprocess.run(
        ["git", "log", "-1", "--format=%s", "main"],
        cwd=bare,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "x"


def test_named_remote_resolving_to_a_nonlocal_url_is_intercepted(tmp_path):
    """The guard resolves a bare remote NAME before deciding."""
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/nope.git"],
        cwd=work,
        check=True,
    )
    with pytest.raises(BaseException) as excinfo:
        subprocess.run(["git", "push", "origin", "main"], cwd=work, capture_output=True)
    message = str(excinfo.value)
    assert "BLOCKED" in message
    assert "https://example.invalid/nope.git" in message


# ---------------------------------------------------------------------------
# Popen's cwd can arrive positionally. ``subprocess.run`` always passes it by
# keyword, but a direct Popen caller need not -- and the guard resolves a bare
# remote NAME by running ``git remote get-url`` in that cwd, so reading it from
# the wrong place turns a local push into a refusal (or a real remote into an
# unresolved None).
# ---------------------------------------------------------------------------

# Popen.__init__(args, bufsize, executable, stdin, stdout, stderr, preexec_fn,
#                close_fds, shell, cwd, ...) -- cwd is the 9th after ``args``.
def _popen_with_positional_cwd(cmd, cwd):
    return subprocess.Popen(
        cmd,
        -1,  # bufsize
        None,  # executable
        None,  # stdin
        subprocess.PIPE,  # stdout
        subprocess.PIPE,  # stderr
        None,  # preexec_fn
        True,  # close_fds
        False,  # shell
        str(cwd),  # cwd
    )


def _work_repo_with_origin(tmp_path, origin: str):
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    (work / "f.txt").write_text("x")
    subprocess.run(["git", "add", "f.txt"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=work, check=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=work, check=True)
    return work


def test_positional_cwd_resolves_a_named_local_remote(tmp_path):
    """A positional cwd must still find the repo whose remote is local."""
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = _work_repo_with_origin(tmp_path, str(bare))

    proc = _popen_with_positional_cwd(["git", "push", "-q", "origin", "main"], work)
    proc.communicate(timeout=30)
    assert proc.returncode == 0

    out = subprocess.run(
        ["git", "log", "-1", "--format=%s", "main"],
        cwd=bare,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "x"


def test_positional_cwd_resolves_a_named_nonlocal_remote(tmp_path):
    """And the refusal names the URL it resolved, not an unresolved None."""
    work = _work_repo_with_origin(tmp_path, "https://example.invalid/nope.git")

    with pytest.raises(BaseException) as excinfo:
        _popen_with_positional_cwd(["git", "push", "origin", "main"], work)
    message = str(excinfo.value)
    assert "resolved_url='https://example.invalid/nope.git'" in message
    assert f"cwd={str(work)!r}" in message


def test_non_git_commands_pass_through():
    out = subprocess.run(["echo", "push"], capture_output=True, text=True)
    assert out.stdout.strip() == "push"


def test_guard_wrapper_is_pure_and_reusable():
    """The wrapper decides before it ever reaches the real Popen."""
    calls = []

    def fake_popen(args, *a, **kw):
        calls.append(args)
        return "process"

    guarded = make_guarded_popen(fake_popen)
    assert guarded(["git", "status"]) == "process"
    assert calls == [["git", "status"]]

    with pytest.raises(BaseException):
        guarded(["git", "push", "https://example.invalid/x.git", "main"])
    assert calls == [["git", "status"]]


def test_push_guard_is_active_in_a_consumer_session(inner):
    inner.write(
        {
            "test_consumer_push.py": (
                "import subprocess\n"
                "\n"
                "def test_push_is_blocked():\n"
                "    subprocess.run(\n"
                "        ['git', 'push', 'https://example.invalid/nope.git', 'main'],\n"
                "        capture_output=True,\n"
                "    )\n"
            )
        }
    )
    result = inner.run("-q")
    assert result.ret != 0
    assert "BLOCKED: real 'git push' to a non-local remote" in "\n".join(result.outlines)
