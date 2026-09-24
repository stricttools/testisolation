"""Ini-file configuration for testisolation's isolation.

Every knob lives in ``[tool.pytest.ini_options]`` (or ``pytest.ini`` /
``tox.ini`` / ``setup.cfg`` -- anything pytest reads as ini).

Installing the plugin IS adoption: the safety keys below are REQUIRED and a
missing one aborts the session at configure time. There are no implicit
defaults for the socket stance, the socket allowlists, or the sandbox stance --
a repo must declare where it stands before its suite is allowed to run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ini key names
# ---------------------------------------------------------------------------

# Safety keys -- REQUIRED. Absence is a hard configure-time error.
KEY_SOCKETS = "testisolation_sockets"
KEY_SOCKET_ALLOWLIST = "testisolation_socket_allowlist"
KEY_UNIX_SOCKET_ALLOWLIST = "testisolation_unix_socket_allowlist"
KEY_LOOPBACK = "testisolation_loopback"
KEY_SANDBOX_REQUIRED = "testisolation_sandbox_required"

REQUIRED_KEYS = (
    KEY_SOCKETS,
    KEY_SOCKET_ALLOWLIST,
    KEY_UNIX_SOCKET_ALLOWLIST,
    KEY_LOOPBACK,
    KEY_SANDBOX_REQUIRED,
)

# Optional keys -- the five parameterized constants plus the preserve enum.
KEY_THRESHOLD = "testisolation_threshold"
KEY_SANDBOX_ENV = "testisolation_sandbox_env"
KEY_RUNNER_COMMAND = "testisolation_runner_command"
KEY_TMP_PREFIX = "testisolation_tmp_prefix"
KEY_GIT_USER_NAME = "testisolation_git_user_name"
KEY_GIT_USER_EMAIL = "testisolation_git_user_email"
KEY_PRESERVE = "testisolation_preserve"

DEFAULT_THRESHOLD = 50
DEFAULT_SANDBOX_ENV = "TESTISOLATION_SANDBOX"
DEFAULT_RUNNER_COMMAND = "scripts/test.sh"
DEFAULT_TMP_PREFIX = "testisolation-env-"
DEFAULT_GIT_USER_NAME = "testisolation"
DEFAULT_GIT_USER_EMAIL = "testisolation@example.invalid"


class _Missing:
    """Sentinel default for every ini key.

    Presence must be distinguishable from an explicitly-empty value: a project
    that writes ``testisolation_socket_allowlist = []`` has declared its stance,
    while one that omits the key has not. Registering this sentinel as each
    key's default makes ``getini`` itself report presence, without reaching for
    the deprecated ``config.inicfg``.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<testisolation: key not declared>"


MISSING = _Missing()

SOCKET_STANCES = ("deny", "allowlist")
LOOPBACK_STANCES = ("deny", "allow")

# Closed enum of toolchain environment variables a repo may opt into
# preserving across the HOME repoint. Values map to
# ``(env var, default path relative to the real HOME)``. Arbitrary strings are
# rejected: a credential vector must never become preservable by typo.
#
# ``{gopath}`` in a default expands to the resolved GOPATH.
PRESERVE_VARS: dict[str, tuple[str, str]] = {
    "go_path": ("GOPATH", "{home}/go"),
    "go_mod_cache": ("GOMODCACHE", "{gopath}/pkg/mod"),
    "go_cache": ("GOCACHE", "{home}/.cache/go-build"),
    "python_user_base": ("PYTHONUSERBASE", "{home}/.local"),
    "cargo_home": ("CARGO_HOME", "{home}/.cargo"),
    "rustup_home": ("RUSTUP_HOME", "{home}/.rustup"),
    "npm_cache": ("npm_config_cache", "{home}/.npm"),
    "uv_cache": ("UV_CACHE_DIR", "{home}/.cache/uv"),
    "pip_cache": ("PIP_CACHE_DIR", "{home}/.cache/pip"),
    "gradle_user_home": ("GRADLE_USER_HOME", "{home}/.gradle"),
}


@dataclass(frozen=True)
class Settings:
    """Resolved, validated testisolation configuration for one pytest session."""

    sockets: str
    socket_allowlist: tuple[tuple[str, str], ...]
    unix_socket_allowlist: tuple[str, ...]
    loopback: str
    sandbox_required: bool
    threshold: int
    sandbox_env: str
    runner_command: str
    tmp_prefix: str
    git_user_name: str
    git_user_email: str
    preserve: tuple[str, ...]


def add_ini_options(parser) -> None:
    """Register every testisolation ini key with pytest's parser."""
    parser.addini(
        KEY_SOCKETS,
        "REQUIRED. Socket stance for non-loopback addresses: 'deny' (no "
        "network at all) or 'allowlist' (only host:port pairs listed in "
        f"{KEY_SOCKET_ALLOWLIST}).",
        default=MISSING,
    )
    parser.addini(
        KEY_SOCKET_ALLOWLIST,
        "REQUIRED (may be empty). One 'host:port' per line; IPv6 hosts are "
        "bracketed, e.g. '[::1]:5432'. Must be empty when "
        f"{KEY_SOCKETS} is 'deny'.",
        type="linelist",
        default=MISSING,
    )
    parser.addini(
        KEY_UNIX_SOCKET_ALLOWLIST,
        "REQUIRED (may be empty). One unix-socket path per line. A trailing "
        "'/' makes the entry a directory prefix; anything else is an exact "
        "path match.",
        type="linelist",
        default=MISSING,
    )
    parser.addini(
        KEY_LOOPBACK,
        "REQUIRED. Loopback stance, declared independently of "
        f"{KEY_SOCKETS}: 'allow' permits connects to 127.0.0.0/8, ::1 and "
        "'localhost'; 'deny' blocks them unless explicitly allowlisted.",
        default=MISSING,
    )
    parser.addini(
        KEY_SANDBOX_REQUIRED,
        "REQUIRED. 'true' enforces the bare-run threshold (a full-ish run "
        "must go through the sandbox runner); 'false' declares that this repo "
        "has no sandbox runner yet and disables the threshold entirely.",
        default=MISSING,
    )
    parser.addini(
        KEY_THRESHOLD,
        "Bare-run refusal threshold: a run collecting MORE than this many "
        f"tests outside the sandbox is refused. Default {DEFAULT_THRESHOLD}.",
        default=MISSING,
    )
    parser.addini(
        KEY_SANDBOX_ENV,
        "Name of the environment variable the sandbox runner sets to '1'. "
        f"Default {DEFAULT_SANDBOX_ENV}.",
        default=MISSING,
    )
    parser.addini(
        KEY_RUNNER_COMMAND,
        "Command shown in the bare-run refusal message. Default "
        f"{DEFAULT_RUNNER_COMMAND!r}.",
        default=MISSING,
    )
    parser.addini(
        KEY_TMP_PREFIX,
        "Prefix for the session's throwaway env directory. Default "
        f"{DEFAULT_TMP_PREFIX!r}.",
        default=MISSING,
    )
    parser.addini(
        KEY_GIT_USER_NAME,
        f"user.name written into the throwaway git config. Default "
        f"{DEFAULT_GIT_USER_NAME!r}.",
        default=MISSING,
    )
    parser.addini(
        KEY_GIT_USER_EMAIL,
        f"user.email written into the throwaway git config. Default "
        f"{DEFAULT_GIT_USER_EMAIL!r}.",
        default=MISSING,
    )
    parser.addini(
        KEY_PRESERVE,
        "Toolchain caches preserved across the HOME repoint, one closed-enum "
        "name per line. Valid names: " + ", ".join(sorted(PRESERVE_VARS)) + ".",
        type="linelist",
        default=MISSING,
    )


def _present(config, key: str) -> bool:
    """True when ``key`` was actually written in the ini file."""
    return config.getini(key) is not MISSING


def _raw(config, key: str):
    return config.getini(key)


def _as_bool(key: str, value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    raise pytest.UsageError(
        f"testisolation: ini key '{key}' must be a boolean "
        f"('true' or 'false'), got {value!r}."
    )


_HOSTPORT_BRACKETED = re.compile(r"^\[(?P<host>[^\]]+)\]:(?P<port>\d+)$")
_HOSTPORT_PLAIN = re.compile(r"^(?P<host>[^:]+):(?P<port>\d+)$")


def parse_host_port(entry: str) -> tuple[str, str]:
    """Parse one allowlist entry into ``(host, port)``.

    Bracketed form ``[::1]:5432`` carries IPv6 literals; the plain form is
    ``host:port``. Anything else is a configuration error.
    """
    text = entry.strip()
    match = _HOSTPORT_BRACKETED.match(text) or _HOSTPORT_PLAIN.match(text)
    if not match:
        raise pytest.UsageError(
            f"testisolation: ini key '{KEY_SOCKET_ALLOWLIST}' entry {entry!r} is "
            "not a 'host:port' pair. Use 'example.com:443' or, for IPv6, "
            "'[::1]:5432'."
        )
    return match.group("host"), match.group("port")


def missing_required_keys(config) -> list[str]:
    """Return the required ini keys absent from this project's config."""
    return [key for key in REQUIRED_KEYS if not _present(config, key)]


# Ini-file section headers, by the file pytest resolved the settings from.
# ``pytest.ini`` and ``tox.ini`` share ``[pytest]``; ``setup.cfg`` needs the
# namespaced form because the file is not pytest's alone.
_INI_SECTION_BY_SUFFIX = {".ini": "[pytest]", ".cfg": "[tool:pytest]"}


def remediation_block(inipath) -> str:
    """The most-restrictive starting stance, in ``inipath``'s own syntax.

    A configuration snippet a project cannot paste is not remediation. TOML
    quotes values and writes lists in brackets; classic ini files take literal
    unquoted text and one list entry per indented line, so a TOML block pasted
    into ``pytest.ini`` produces a second error instead of a fix.

    ``None`` (no ini file at all yet) renders TOML, because the file such a
    project should create is ``pyproject.toml``.
    """
    suffix = Path(str(inipath)).suffix.lower() if inipath else ""
    section = _INI_SECTION_BY_SUFFIX.get(suffix)
    if section is not None:
        return "\n".join(
            [
                section,
                f"{KEY_SOCKETS} = deny",
                f"{KEY_SOCKET_ALLOWLIST} =",
                f"{KEY_UNIX_SOCKET_ALLOWLIST} =",
                f"{KEY_LOOPBACK} = deny",
                f"{KEY_SANDBOX_REQUIRED} = false",
            ]
        )
    return "\n".join(
        [
            "[tool.pytest.ini_options]",
            f'{KEY_SOCKETS} = "deny"',
            f"{KEY_SOCKET_ALLOWLIST} = []",
            f"{KEY_UNIX_SOCKET_ALLOWLIST} = []",
            f'{KEY_LOOPBACK} = "deny"',
            f'{KEY_SANDBOX_REQUIRED} = "false"',
        ]
    )


def required_keys_error(config, missing: list[str]) -> pytest.UsageError:
    """Build the precise configure-time abort for missing safety keys."""
    inipath = getattr(config, "inipath", None)
    inifile = inipath or "your pytest ini file"
    template = remediation_block(inipath)
    return pytest.UsageError(
        "testisolation is installed, and installing it IS adoption -- but this "
        "project has not declared its safety stance. Missing required ini "
        f"key(s): {', '.join(missing)}.\n\n"
        f"Declare every one of them in {inifile}. There are no defaults: the "
        "socket stance, both allowlists, and the sandbox stance are choices a "
        "project must make explicitly. The most restrictive starting point "
        "is:\n\n"
        f"{template}\n\n"
        "Then relax individual keys as the suite genuinely needs them."
    )


def resolve(config) -> Settings:
    """Validate and resolve the full settings object, or raise UsageError."""
    missing = missing_required_keys(config)
    if missing:
        raise required_keys_error(config, missing)

    sockets = str(_raw(config, KEY_SOCKETS)).strip()
    if sockets not in SOCKET_STANCES:
        raise pytest.UsageError(
            f"testisolation: ini key '{KEY_SOCKETS}' must be one of "
            f"{', '.join(SOCKET_STANCES)}; got {sockets!r}."
        )

    loopback = str(_raw(config, KEY_LOOPBACK)).strip()
    if loopback not in LOOPBACK_STANCES:
        raise pytest.UsageError(
            f"testisolation: ini key '{KEY_LOOPBACK}' must be one of "
            f"{', '.join(LOOPBACK_STANCES)}; got {loopback!r}."
        )

    allowlist_entries = [e for e in _raw(config, KEY_SOCKET_ALLOWLIST) if e.strip()]
    socket_allowlist = tuple(parse_host_port(e) for e in allowlist_entries)
    if sockets == "deny" and socket_allowlist:
        raise pytest.UsageError(
            f"testisolation: '{KEY_SOCKETS} = deny' forbids all network access, "
            f"but '{KEY_SOCKET_ALLOWLIST}' lists "
            f"{len(socket_allowlist)} entr{'y' if len(socket_allowlist) == 1 else 'ies'}. "
            "The two contradict each other; entries are never silently "
            f"ignored. Either empty the allowlist or set '{KEY_SOCKETS} = allowlist'."
        )

    unix_allowlist = tuple(
        e.strip() for e in _raw(config, KEY_UNIX_SOCKET_ALLOWLIST) if e.strip()
    )

    sandbox_required = _as_bool(
        KEY_SANDBOX_REQUIRED, _raw(config, KEY_SANDBOX_REQUIRED)
    )

    threshold = DEFAULT_THRESHOLD
    if _present(config, KEY_THRESHOLD):
        raw_threshold = str(_raw(config, KEY_THRESHOLD)).strip()
        try:
            threshold = int(raw_threshold)
        except ValueError:
            raise pytest.UsageError(
                f"testisolation: ini key '{KEY_THRESHOLD}' must be an integer, "
                f"got {raw_threshold!r}."
            ) from None
        if threshold < 1:
            raise pytest.UsageError(
                f"testisolation: ini key '{KEY_THRESHOLD}' must be >= 1, got "
                f"{threshold}. Use '{KEY_SANDBOX_REQUIRED} = false' to turn "
                "the threshold off, not a zero threshold."
            )

    preserve: tuple[str, ...] = ()
    if _present(config, KEY_PRESERVE):
        names = [e.strip() for e in _raw(config, KEY_PRESERVE) if e.strip()]
        unknown = [n for n in names if n not in PRESERVE_VARS]
        if unknown:
            raise pytest.UsageError(
                f"testisolation: ini key '{KEY_PRESERVE}' accepts only the closed "
                f"enum of known-safe toolchain variables. Unknown: "
                f"{', '.join(sorted(unknown))}. Valid names: "
                f"{', '.join(sorted(PRESERVE_VARS))}. Arbitrary environment "
                "variable names are rejected on purpose -- a credential vector "
                "must never become preservable by typo."
            )
        preserve = tuple(dict.fromkeys(names))

    def _opt(key: str, default: str) -> str:
        if not _present(config, key):
            return default
        value = str(_raw(config, key)).strip()
        return value or default

    return Settings(
        sockets=sockets,
        socket_allowlist=socket_allowlist,
        unix_socket_allowlist=unix_allowlist,
        loopback=loopback,
        sandbox_required=sandbox_required,
        threshold=threshold,
        sandbox_env=_opt(KEY_SANDBOX_ENV, DEFAULT_SANDBOX_ENV),
        runner_command=_opt(KEY_RUNNER_COMMAND, DEFAULT_RUNNER_COMMAND),
        tmp_prefix=_opt(KEY_TMP_PREFIX, DEFAULT_TMP_PREFIX),
        git_user_name=_opt(KEY_GIT_USER_NAME, DEFAULT_GIT_USER_NAME),
        git_user_email=_opt(KEY_GIT_USER_EMAIL, DEFAULT_GIT_USER_EMAIL),
        preserve=preserve,
    )
