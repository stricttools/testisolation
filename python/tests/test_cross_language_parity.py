"""The three implementations must strip and preserve the same variables.

The pytest plugin, the Go ``hygiene`` package and the npm package ship in one
repository and are adopted side by side in polyglot repos. If their lists drift,
a repo gets one guarantee in Python, a different one in Go, and a third in Node
-- silently. These tests read the Go and TypeScript sources directly, so drift
is a failure here rather than a discovery in production.

They skip when the other languages' sources are not on disk (an installed wheel
carries only the Python package).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from stricttest.config import PRESERVE_VARS
from stricttest.envpoison import CREDENTIAL_VARS

REPO_ROOT = Path(__file__).resolve().parents[2]
GO_ROOT = REPO_ROOT / "go" / "hygiene"
TS_ROOT = REPO_ROOT / "typescript" / "src"

# GIT_ASKPASS is stripped by the Go and Node implementations and pinned to /bin/false by
# the Python one. All three otherwise lock transports down identically
# (GIT_ALLOW_PROTOCOL plus a pinned GIT_SSH_COMMAND and GIT_PROXY_COMMAND), and
# either treatment leaves git unable to obtain a credential, so this is the one
# deliberate difference between the lists.
NON_PYTHON_CREDENTIAL_VARS = {"GIT_ASKPASS"}


def _source(root: Path, name: str) -> str:
    path = root / name
    if not path.exists():
        pytest.skip(f"the source is not present at {path}")
    return path.read_text()


def _block(source: str, pattern: str, what: str) -> str:
    match = re.search(pattern, source, re.DOTALL)
    assert match, f"{what} no longer has the literal shape this test reads"
    return match.group(1)


def _go_credential_vars() -> set[str]:
    block = _block(
        _source(GO_ROOT, "env.go"),
        r"var CredentialVars = \[\]string\{(.*?)\n\}",
        "CredentialVars in go/hygiene/env.go",
    )
    return set(re.findall(r'"([A-Za-z0-9_]+)"', block))


def _go_preserve_vars() -> set[str]:
    block = _block(
        _source(GO_ROOT, "hygiene.go"),
        r"var knownVars = map\[KnownVar\]knownVar\{(.*?)\n\}",
        "knownVars in go/hygiene/hygiene.go",
    )
    # Each entry is {"Name", "ENV_VAR", "{home}/default"}.
    return set(re.findall(r'\{"[A-Za-z]+",\s*"([A-Za-z0-9_]+)"', block))


def _ts_credential_vars() -> set[str]:
    block = _block(
        _source(TS_ROOT, "env.ts"),
        r"export const CREDENTIAL_VARS[^=]*= \[(.*?)\n\];",
        "CREDENTIAL_VARS in typescript/src/env.ts",
    )
    return set(re.findall(r'"([A-Za-z0-9_]+)"', block))


def _ts_preserve_vars() -> set[str]:
    block = _block(
        _source(TS_ROOT, "hygiene.ts"),
        r"export const KNOWN_VARS = \{(.*?)\n\} as const",
        "KNOWN_VARS in typescript/src/hygiene.ts",
    )
    # Each entry is `name: { env: "ENV_VAR", default: "{home}/..." },`.
    return set(re.findall(r'env:\s*"([A-Za-z0-9_]+)"', block))


def test_the_go_credential_list_matches_python():
    assert _go_credential_vars() == set(CREDENTIAL_VARS) | NON_PYTHON_CREDENTIAL_VARS


def test_the_node_credential_list_matches_python():
    assert _ts_credential_vars() == set(CREDENTIAL_VARS) | NON_PYTHON_CREDENTIAL_VARS


def test_the_go_and_node_credential_lists_match_each_other():
    # Asserted directly as well as transitively: if the Python list and one of
    # the other two changed together, the pairwise checks above would both pass
    # while the two non-Python implementations had drifted apart.
    assert _go_credential_vars() == _ts_credential_vars()


def test_the_preserve_enums_cover_the_same_variables():
    python_vars = {env for env, _ in PRESERVE_VARS.values()}
    assert _go_preserve_vars() == python_vars
    assert _ts_preserve_vars() == python_vars
