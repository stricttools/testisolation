"""Configuration surface: required safety keys, closed enums, contradictions."""

from __future__ import annotations

import pytest

from testisolation import config

OK_TEST = "def test_ok():\n    assert True\n"


def test_missing_every_safety_key_aborts(inner):
    """Plugin presence IS adoption: an undeclared stance aborts the session."""
    inner.write({"test_ok.py": OK_TEST}, omit=tuple(config.REQUIRED_KEYS))
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "installing it IS adoption" in combined
    for key in config.REQUIRED_KEYS:
        assert key in combined
    # No test ran: the abort happens before collection.
    assert "1 passed" not in combined


@pytest.mark.parametrize("key", config.REQUIRED_KEYS)
def test_each_safety_key_is_individually_required(inner, key):
    inner.write({"test_ok.py": OK_TEST}, omit=(key,))
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert f"Missing required ini key(s): {key}" in combined


def test_empty_allowlists_count_as_declared(inner):
    """An explicitly-empty list is a stance; only absence is undeclared."""
    inner.write({"test_ok.py": OK_TEST})
    inner.run("-q").assert_outcomes(passed=1)


def test_unknown_socket_stance_rejected(inner):
    inner.write({"test_ok.py": OK_TEST}, ini={"testisolation_sockets": "sometimes"})
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "testisolation_sockets' must be one of deny, allowlist" in combined


def test_unknown_loopback_stance_rejected(inner):
    inner.write({"test_ok.py": OK_TEST}, ini={"testisolation_loopback": "maybe"})
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "testisolation_loopback' must be one of deny, allow" in combined


def test_deny_plus_allowlist_is_a_contradiction(inner):
    """Allowlist entries are never silently ignored."""
    inner.write(
        {"test_ok.py": OK_TEST},
        ini={
            "testisolation_sockets": "deny",
            "testisolation_socket_allowlist": ["example.com:443"],
        },
    )
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "contradict each other" in combined


def test_malformed_allowlist_entry_rejected(inner):
    inner.write(
        {"test_ok.py": OK_TEST},
        ini={
            "testisolation_sockets": "allowlist",
            "testisolation_socket_allowlist": ["example.com"],
        },
    )
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "is not a 'host:port' pair" in combined


def test_zero_threshold_rejected_in_favour_of_the_sandbox_stance(inner):
    inner.write(
        {"test_ok.py": OK_TEST},
        ini={"testisolation_threshold": "0", "testisolation_sandbox_required": "true"},
    )
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "testisolation_threshold' must be >= 1" in combined


def test_non_integer_threshold_rejected(inner):
    inner.write({"test_ok.py": OK_TEST}, ini={"testisolation_threshold": "many"})
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "testisolation_threshold' must be an integer" in combined


def test_non_boolean_sandbox_stance_rejected(inner):
    inner.write({"test_ok.py": OK_TEST}, ini={"testisolation_sandbox_required": "sorta"})
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "must be a boolean" in combined


# ---------------------------------------------------------------------------
# The remediation snippet must be pasteable into the project's OWN ini file.
# ---------------------------------------------------------------------------


def test_remediation_snippet_is_toml_for_a_pyproject(inner):
    inner.write({"test_ok.py": OK_TEST}, omit=tuple(config.REQUIRED_KEYS))
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "[tool.pytest.ini_options]" in combined
    assert 'testisolation_sockets = "deny"' in combined


@pytest.mark.parametrize(
    "filename,header",
    [("pytest.ini", "[pytest]"), ("setup.cfg", "[tool:pytest]")],
)
def test_remediation_snippet_is_ini_syntax_for_an_ini_file(inner, filename, header):
    """A TOML block pasted into pytest.ini is a second error, not a fix."""
    inner.write(
        {"test_ok.py": OK_TEST},
        omit=tuple(config.REQUIRED_KEYS),
        ini_filename=filename,
    )
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert header in combined
    assert "[tool.pytest.ini_options]" not in combined
    # Unquoted: ini values are literal text, and the quotes would end up in
    # the value.
    assert "testisolation_sockets = deny" in combined
    assert 'testisolation_sockets = "deny"' not in combined


@pytest.mark.parametrize(
    "filename", ["pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg"]
)
def test_pasting_the_remediation_snippet_verbatim_makes_the_session_run(
    inner, filename
):
    """The end-to-end contract: paste what the abort printed, and it works."""
    from pathlib import Path

    snippet = config.remediation_block(Path(filename))
    inner.write({"test_ok.py": OK_TEST}, ini_filename=filename, raw_ini=snippet)
    inner.run("-q").assert_outcomes(passed=1)


def test_remediation_block_falls_back_to_toml_without_an_ini_file():
    """No ini file yet: pyproject.toml is what a new project should create."""
    assert "[tool.pytest.ini_options]" in config.remediation_block(None)


# ---------------------------------------------------------------------------
# host:port parsing (pure)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry,expected",
    [
        ("example.com:443", ("example.com", "443")),
        ("127.0.0.1:5432", ("127.0.0.1", "5432")),
        ("[::1]:5432", ("::1", "5432")),
        ("  example.com:80  ", ("example.com", "80")),
    ],
)
def test_parse_host_port(entry, expected):
    assert config.parse_host_port(entry) == expected


@pytest.mark.parametrize("entry", ["example.com", "example.com:", ":443", "::1:5432"])
def test_parse_host_port_rejects_garbage(entry):
    with pytest.raises(pytest.UsageError):
        config.parse_host_port(entry)


def test_default_threshold_is_fifty():
    """rlsbl's threshold is the shipped default."""
    assert config.DEFAULT_THRESHOLD == 50


def test_default_sandbox_env_var_name():
    assert config.DEFAULT_SANDBOX_ENV == "TESTISOLATION_SANDBOX"
