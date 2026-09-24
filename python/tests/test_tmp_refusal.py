"""TMPDIR / basetemp inside the project root is refused at startup."""

from __future__ import annotations

from pathlib import Path

import pytest

from testisolation.sandbox import enforce_tmp_outside_repo

OK_TEST = "def test_ok():\n    assert True\n"


def test_basetemp_inside_the_project_root_is_refused(inner):
    """``pytester``'s default basetemp lands inside the inner project root.

    Running WITHOUT the harness's outside-basetemp override therefore exercises
    the real refusal, using pytest's own default rather than a contrived path.
    """
    inner.write({"test_ok.py": OK_TEST})
    result = inner.pytester.runpytest_subprocess("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "is inside the repository" in combined
    assert "commit junk" in combined


def test_tmpdir_env_inside_the_project_root_is_refused(inner, monkeypatch):
    inner.write({"test_ok.py": OK_TEST})
    inside = inner.pytester.path / "tmp"
    inside.mkdir()
    monkeypatch.setenv("TMPDIR", str(inside))
    result = inner.run("-q")
    assert result.ret != 0
    combined = "\n".join(result.outlines + result.errlines)
    assert "is inside the repository" in combined
    assert str(inside) in combined


def test_tmpdir_outside_the_project_root_is_fine(inner, monkeypatch, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    inner.write({"test_ok.py": OK_TEST})
    monkeypatch.setenv("TMPDIR", str(outside))
    inner.run("-q").assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Unit-level: the containment rule itself.
# ---------------------------------------------------------------------------


def test_basetemp_equal_to_the_root_is_refused(tmp_path):
    with pytest.raises(pytest.UsageError):
        enforce_tmp_outside_repo(tmp_path.resolve(), tmp_path)


def test_nested_basetemp_is_refused(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    with pytest.raises(pytest.UsageError):
        enforce_tmp_outside_repo(tmp_path.resolve(), nested)


def test_sibling_basetemp_is_allowed(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    sibling = tmp_path / "tmp"
    sibling.mkdir()
    enforce_tmp_outside_repo(root.resolve(), sibling)


def test_parent_basetemp_is_allowed(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    enforce_tmp_outside_repo(root.resolve(), tmp_path)


def test_unresolvable_candidate_is_skipped_not_crashed(tmp_path):
    enforce_tmp_outside_repo(tmp_path.resolve(), Path("/nonexistent/deep/path"))
