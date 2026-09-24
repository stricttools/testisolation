"""Test harness for the testisolation plugin's own suite.

Most isolation pieces can only be proved end-to-end, from a real pytest session
that adopts the plugin. Those tests run an INNER pytest session in a
subprocess (``pytester.runpytest_subprocess``) against a generated consumer
project. A subprocess is mandatory, not a stylistic choice: the socket guard's
audit hook is permanent for the life of a process, so a differing stance can
only be exercised in a fresh interpreter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

pytest_plugins = ["pytester"]

# The sample consumer is a complete project of its own -- it must run as its own
# pytest session with its own rootdir and stance, never as part of this suite.
collect_ignore = ["sample_consumer"]

# The most restrictive stance -- what a new consumer starts from. Individual
# tests override single keys.
SAFE_DEFAULTS: dict[str, object] = {
    "testisolation_sockets": "deny",
    "testisolation_socket_allowlist": [],
    "testisolation_unix_socket_allowlist": [],
    "testisolation_loopback": "deny",
    "testisolation_sandbox_required": "false",
}


def _toml_value(value: object) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(v)) for v in value) + "]"
    return json.dumps(str(value))


def render_pyproject(ini: dict[str, object]) -> str:
    lines = ["[tool.pytest.ini_options]"]
    for key, value in ini.items():
        lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


# The ini-file names pytest reads, mapped to the section header each one uses.
# ``pytest.ini`` outranks ``pyproject.toml`` in pytest's own discovery order, so
# writing one is enough to make it the session's inipath.
INI_SECTIONS: dict[str, str] = {
    "pytest.ini": "[pytest]",
    "tox.ini": "[pytest]",
    "setup.cfg": "[tool:pytest]",
}


def render_ini(filename: str, ini: dict[str, object]) -> str:
    """Render settings in classic ini syntax: unquoted values, one per line."""
    lines = [INI_SECTIONS[filename]]
    for key, value in ini.items():
        if isinstance(value, list):
            joined = "".join(f"\n    {v}" for v in value)
            lines.append(f"{key} ={joined}")
        else:
            lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


@dataclass
class InnerProject:
    """A generated consumer project plus the ability to run pytest inside it."""

    pytester: pytest.Pytester
    _runs: int = field(default=0, init=False)

    def write(
        self,
        files: dict[str, str],
        ini: dict[str, object] | None = None,
        omit: tuple[str, ...] = (),
        ini_filename: str = "pyproject.toml",
        raw_ini: str | None = None,
    ) -> None:
        """Generate the consumer project.

        ``ini_filename`` selects which of pytest's ini files carries the
        settings, because the remediation the plugin prints has to match the
        syntax of the file the project actually uses. ``raw_ini`` writes that
        file verbatim instead of rendering ``ini`` -- what a consumer pasting
        the plugin's own snippet does.
        """
        merged = dict(SAFE_DEFAULTS)
        merged.update(ini or {})
        for key in omit:
            merged.pop(key, None)
        if ini_filename == "pyproject.toml":
            self.pytester.makepyprojecttoml(
                raw_ini if raw_ini is not None else render_pyproject(merged)
            )
        else:
            (self.pytester.path / ini_filename).write_text(
                raw_ini if raw_ini is not None else render_ini(ini_filename, merged)
            )
        for name, source in files.items():
            path = self.pytester.path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)

    def run(self, *args: str) -> pytest.RunResult:
        """Run pytest inside the generated project.

        ``pytester`` puts its own ``--basetemp`` INSIDE the inner project root,
        which testisolation's own TMPDIR refusal correctly rejects. A basetemp
        outside the project root is appended so it wins the last-flag-wins
        argument race -- which is exactly the remediation the refusal message
        asks a consumer for.
        """
        self._runs += 1
        basetemp = self.pytester.path.parent / f"inner-basetemp-{self._runs}"
        return self.pytester.runpytest_subprocess(f"--basetemp={basetemp}", *args)


@pytest.fixture
def inner(pytester: pytest.Pytester) -> InnerProject:
    return InnerProject(pytester)
