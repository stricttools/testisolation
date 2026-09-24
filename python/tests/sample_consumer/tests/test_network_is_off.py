"""The consumer's network-touching code path is refused, loudly."""

from __future__ import annotations

import pytest
from testisolation import NetworkBlocked

import acme


def test_fetching_release_metadata_is_refused():
    with pytest.raises(NetworkBlocked) as excinfo:
        acme.fetch_release_metadata("https://api.github.com/repos/stricttools/testisolation")
    assert "BLOCKED" in str(excinfo.value)


def test_the_refusal_names_the_remediation():
    with pytest.raises(NetworkBlocked) as excinfo:
        acme.fetch_release_metadata("https://pypi.org/pypi/testisolation/json")
    assert "testisolation_socket_allowlist" in str(excinfo.value)
