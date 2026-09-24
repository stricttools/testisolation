"""The bare-run threshold, including the xdist controller/worker topology."""

from __future__ import annotations

import pytest

from testisolation.config import Settings
from testisolation.sandbox import enforce_threshold


def _tests(count: int, prefix: str = "a") -> str:
    return "\n".join(f"def test_{prefix}{i}():\n    assert True\n" for i in range(count))


STRICT = {"testisolation_sandbox_required": "true", "testisolation_threshold": "3"}


def test_bare_full_run_is_refused(inner):
    inner.write({"test_many.py": _tests(5)}, ini=STRICT)
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "Refusing to run 5 tests bare (> 3)" in combined
    assert "scripts/test.sh" in combined


def test_run_inside_the_sandbox_is_allowed(inner, monkeypatch):
    inner.write({"test_many.py": _tests(5)}, ini=STRICT)
    monkeypatch.setenv("TESTISOLATION_SANDBOX", "1")
    inner.run("-q").assert_outcomes(passed=5)


def test_run_at_the_threshold_is_allowed(inner):
    """The refusal is for runs strictly ABOVE the threshold."""
    inner.write({"test_many.py": _tests(3)}, ini=STRICT)
    inner.run("-q").assert_outcomes(passed=3)


def test_deselection_is_counted_after_k_filtering(inner):
    """A ``-k`` slice of a big file stays bare-runnable.

    The hook runs ``trylast`` precisely so the count reflects SELECTED tests,
    not the pre-deselection total.
    """
    inner.write({"test_many.py": _tests(5, "a") + _tests(2, "b")}, ini=STRICT)
    result = inner.run("-q", "-k", "b")
    result.assert_outcomes(passed=2)


def test_sandbox_not_required_disables_the_threshold(inner):
    inner.write({"test_many.py": _tests(20)}, ini={"testisolation_sandbox_required": "false"})
    inner.run("-q").assert_outcomes(passed=20)


def test_configured_sandbox_env_var_is_honoured(inner, monkeypatch):
    ini = dict(STRICT, testisolation_sandbox_env="ACME_TEST_SANDBOX")
    inner.write({"test_many.py": _tests(5)}, ini=ini)

    # The default name must NOT satisfy a project that renamed the handshake.
    monkeypatch.setenv("TESTISOLATION_SANDBOX", "1")
    result = inner.run("-q")
    assert result.ret != 0
    assert "ACME_TEST_SANDBOX" in "\n".join(result.outlines + result.errlines)

    monkeypatch.setenv("ACME_TEST_SANDBOX", "1")
    inner.run("-q").assert_outcomes(passed=5)


def test_configured_runner_command_appears_in_the_refusal(inner):
    ini = dict(STRICT, testisolation_runner_command="make sandboxed-test")
    inner.write({"test_many.py": _tests(5)}, ini=ini)
    result = inner.run("-q")
    assert result.ret != 0
    assert "make sandboxed-test" in "\n".join(result.outlines + result.errlines)


# ---------------------------------------------------------------------------
# xdist topology: workers defer, the controller enforces exactly once.
# ---------------------------------------------------------------------------


def test_xdist_controller_refuses_once(inner):
    inner.write({"test_many.py": _tests(5)}, ini=STRICT)
    result = inner.run("-q", "-n", "2")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "Refusing to run 5 tests bare (> 3)" in combined
    # One report, not one per worker: the workers defer to the controller.
    assert combined.count("Refusing to run 5 tests bare") == 1


def test_xdist_inside_the_sandbox_is_allowed(inner, monkeypatch):
    inner.write({"test_many.py": _tests(5)}, ini=STRICT)
    monkeypatch.setenv("TESTISOLATION_SANDBOX", "1")
    result = inner.run("-q", "-n", "2")
    result.assert_outcomes(passed=5)


def test_xdist_small_run_is_allowed_bare(inner):
    inner.write({"test_many.py": _tests(3)}, ini=STRICT)
    inner.run("-q", "-n", "2").assert_outcomes(passed=3)


# ---------------------------------------------------------------------------
# Unit-level: the rule itself.
# ---------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    base = dict(
        sockets="deny",
        socket_allowlist=(),
        unix_socket_allowlist=(),
        loopback="deny",
        sandbox_required=True,
        threshold=50,
        sandbox_env="TESTISOLATION_SANDBOX",
        runner_command="scripts/test.sh",
        tmp_prefix="testisolation-env-",
        git_user_name="testisolation",
        git_user_email="testisolation@example.invalid",
        preserve=(),
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.parametrize("count", [0, 1, 49, 50])
def test_counts_up_to_the_threshold_pass(count, monkeypatch):
    monkeypatch.delenv("TESTISOLATION_SANDBOX", raising=False)
    enforce_threshold(_settings(), count)


def test_count_above_the_threshold_raises(monkeypatch):
    monkeypatch.delenv("TESTISOLATION_SANDBOX", raising=False)
    with pytest.raises(pytest.UsageError, match="Refusing to run 51 tests bare"):
        enforce_threshold(_settings(), 51)


def test_sandbox_env_short_circuits(monkeypatch):
    monkeypatch.setenv("TESTISOLATION_SANDBOX", "1")
    enforce_threshold(_settings(), 10_000)


def test_sandbox_env_must_be_exactly_one(monkeypatch):
    """A truthy-looking value that is not '1' does not satisfy the handshake."""
    monkeypatch.setenv("TESTISOLATION_SANDBOX", "yes")
    with pytest.raises(pytest.UsageError):
        enforce_threshold(_settings(), 51)


def test_not_required_short_circuits(monkeypatch):
    monkeypatch.delenv("TESTISOLATION_SANDBOX", raising=False)
    enforce_threshold(_settings(sandbox_required=False), 10_000)
