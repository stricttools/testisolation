"""The sample consumer project runs green under the isolation.

Blocking things is only half of the contract; the other half is that an
ordinary suite -- one that writes user config, drives git, and has a
network-touching code path -- keeps working.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent / "sample_consumer"


def _copy_sample(pytester) -> None:
    shutil.copytree(SAMPLE, pytester.path, dirs_exist_ok=True)


def test_sample_consumer_suite_is_green(inner):
    _copy_sample(inner.pytester)
    result = inner.run("-q")
    result.assert_outcomes(passed=9)


def test_sample_consumer_is_green_under_xdist(inner):
    _copy_sample(inner.pytester)
    result = inner.run("-q", "-n", "2")
    result.assert_outcomes(passed=9)


def test_sample_consumer_declares_every_required_key():
    """The checked-in fixture must stay a valid adoption example."""
    from testisolation.config import REQUIRED_KEYS

    ini = (SAMPLE / "pytest.ini").read_text()
    for key in REQUIRED_KEYS:
        assert f"\n{key} " in ini or f"\n{key}=" in ini


def test_sample_consumer_unmocked_push_would_be_caught(inner):
    """Adding a careless push test to the sample makes the suite fail."""
    _copy_sample(inner.pytester)
    (inner.pytester.path / "tests" / "test_careless.py").write_text(
        "import acme\n"
        "\n"
        "def test_publish_to_github(repo):\n"
        "    acme.init_repo(repo)\n"
        "    (repo / 'f.txt').write_text('x')\n"
        "    acme.commit_all(repo, 'x')\n"
        "    acme.publish(repo, 'https://github.com/stricttools/testisolation.git')\n"
    )
    result = inner.run("-q")
    assert result.ret != 0
    assert "BLOCKED: real 'git push' to a non-local remote" in "\n".join(result.outlines)
