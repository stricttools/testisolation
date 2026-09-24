"""Audit-hook socket guard.

Net-new to testisolation (rlsbl's isolation layer had no in-process network guard). Built on
``sys.addaudithook`` rather than by monkeypatching ``socket``, so it cannot be
un-patched by a test, a library, or a ``reload``. Audit hooks are permanent for
the life of the process by design: the hook is installed at most once and reads
a module-level policy, and raising from it propagates the refusal to whoever
attempted the connect.

Granularity is host:port and unix-socket path -- pytest-socket only offers
host-level blocking, which is unusable for database tests that need exactly one
port or exactly one unix socket.

Scope, stated plainly: this guard sees the connects, datagram sends and name
resolutions made through Python's ``socket`` module -- resolution included,
because a DNS query for a forbidden host has already left the machine by the
time a connect could be refused. Network performed by a spawned subprocess
(git, gh, psql) is invisible to it. Whole-process network isolation is the
sandbox runner's job (``--unshare-net``); this guard is the in-process guard
beneath it.

A C extension that calls ``connect()`` itself is equally invisible, and this is
worth being blunt about because it is easy to assume otherwise. The audit
events this guard listens for are raised by Python's ``socket`` module, so a
libpq-backed driver (``psycopg``) or any other native client opens its
connection at a level the hook never runs at. That is not a gap an allowlist
can close: there is no event to allow, so allowlisting changes nothing in
either direction, and no stance offered here protects such a consumer. Clients
implemented in Python (``asyncpg``, ``httpx``, ``requests``, ``urllib``) go
through ``socket`` and are covered. For the ones that are not, the protection
has to be structural -- an ephemeral database at the end of the socket
(:mod:`testisolation.pgcluster`), or the sandbox runner's network namespace.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
from dataclasses import dataclass

from .config import Settings

LOOPBACK_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})


class NetworkBlocked(BaseException):
    """Raised inside the audit hook when a connection is refused.

    Subclasses ``BaseException`` on purpose: a bare ``except Exception`` in
    production code under test must not be able to swallow the refusal and turn
    a real egress attempt into a silent pass. Same reasoning as the push
    guard's use of ``pytest.fail``.
    """


@dataclass(frozen=True)
class Policy:
    """The resolved network stance for one process."""

    sockets: str
    loopback: str
    allowlist: frozenset[tuple[str, str]]
    unix_allowlist: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: Settings) -> Policy:
        return cls(
            sockets=settings.sockets,
            loopback=settings.loopback,
            allowlist=frozenset(settings.socket_allowlist),
            unix_allowlist=tuple(settings.unix_socket_allowlist),
        )

    def allowlist_hosts(self) -> frozenset[str]:
        return frozenset(host for host, _ in self.allowlist)

    def describe(self) -> str:
        parts = [
            f"testisolation_sockets={self.sockets}",
            f"testisolation_loopback={self.loopback}",
            f"allowlist={sorted(f'{h}:{p}' for h, p in self.allowlist) or '[]'}",
            f"unix_allowlist={list(self.unix_allowlist) or '[]'}",
        ]
        return "; ".join(parts)


_policy: Policy | None = None
_hook_installed = False


def is_loopback(host: str) -> bool:
    """True when ``host`` names the loopback interface."""
    text = str(host).strip()
    if not text:
        return False
    if text.lower() in LOOPBACK_HOSTNAMES:
        return True
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.split("%", 1)[0]  # strip an IPv6 zone id
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _blocked(policy: Policy, what: str, detail: str) -> NetworkBlocked:
    return NetworkBlocked(
        f"BLOCKED: {what} {detail} refused by the testisolation socket guard. "
        f"Current stance: {policy.describe()}. Tests do not reach the network: "
        "mock the call, point it at a fixture, or -- if this connection is "
        "genuinely required -- declare it in testisolation_socket_allowlist / "
        "testisolation_unix_socket_allowlist."
    )


def _check_unix(policy: Policy, address) -> None:
    try:
        path = os.fsdecode(address)
    except Exception:
        path = str(address)
    for entry in policy.unix_allowlist:
        if entry.endswith("/"):
            if path.startswith(entry):
                return
        elif path == entry:
            return
    raise _blocked(policy, "unix-socket connect to", repr(path))


def _check_inet(policy: Policy, address) -> None:
    if not isinstance(address, (tuple, list)) or len(address) < 2:
        return
    host, port = str(address[0]), str(address[1])
    if (host, port) in policy.allowlist:
        return
    if is_loopback(host):
        if policy.loopback == "allow":
            return
        raise _blocked(policy, "loopback connect to", f"{host}:{port}")
    if policy.sockets == "deny":
        raise _blocked(policy, "network connect to", f"{host}:{port}")
    raise _blocked(policy, "non-allowlisted connect to", f"{host}:{port}")


def _check_address(policy: Policy, sock, address) -> None:
    if address is None:
        # ``socket.sendmsg`` on a CONNECTED socket audits a None address. The
        # destination was already checked at connect time, so there is nothing
        # left to decide -- and refusing here would block an authorized peer.
        return
    family = getattr(sock, "family", None)
    if family == getattr(socket, "AF_UNIX", None):
        _check_unix(policy, address)
        return
    if family in (socket.AF_INET, socket.AF_INET6):
        _check_inet(policy, address)
        return
    # Other families (AF_NETLINK, AF_PACKET, AF_BLUETOOTH, ...) are not
    # credential-bearing network egress and are left alone deliberately;
    # blocking them would break unrelated OS plumbing without buying safety.


def _check_resolution(policy: Policy, host, port=None) -> None:
    """Refuse name resolution that could only serve a forbidden connect.

    Resolution is blocked before the connect so the failure names the host
    instead of surfacing later as an opaque timeout -- and, more importantly,
    because a resolution IS egress: a DNS query for a forbidden host has
    already left the machine by the time the connect would be refused.

    ``port`` is present for ``getaddrinfo`` and absent for the
    ``gethostbyname`` / ``gethostbyaddr`` family, which resolve a bare name.
    """
    if host in (None, "", b""):
        return
    text = os.fsdecode(host) if isinstance(host, bytes) else str(host)
    if is_loopback(text):
        if policy.loopback == "allow":
            return
        if any(h == text for h, _ in policy.allowlist):
            return
        raise _blocked(policy, "loopback name resolution of", repr(text))
    if text in policy.allowlist_hosts():
        return
    where = f"{text!r}" if port is None else f"{text!r} (port {port!r})"
    raise _blocked(policy, "name resolution of", where)


def _hook(event: str, args) -> None:
    policy = _policy
    if policy is None:
        return
    if event == "socket.connect":
        _check_address(policy, args[0], args[1])
    elif event == "socket.sendto":
        _check_address(policy, args[0], args[1])
    elif event == "socket.sendmsg":
        # Same ``(sock, address)`` payload as sendto: a datagram that never
        # calls connect. Without this, UDP egress bypasses the guard entirely.
        _check_address(policy, args[0], args[1])
    elif event == "socket.getaddrinfo":
        _check_resolution(policy, args[0], args[1])
    elif event == "socket.gethostbyname":
        # ``gethostbyname`` / ``gethostbyname_ex`` do NOT route through
        # getaddrinfo; they raise this event and then query the resolver.
        _check_resolution(policy, args[0])
    elif event == "socket.gethostbyaddr":
        # Reverse resolution -- also raised by ``socket.getfqdn``.
        _check_resolution(policy, args[0])


def install(settings: Settings) -> None:
    """Arm the guard for this process. The audit hook is added at most once."""
    global _policy, _hook_installed
    _policy = Policy.from_settings(settings)
    if not _hook_installed:
        sys.addaudithook(_hook)
        _hook_installed = True


def current_policy() -> Policy | None:
    """The active policy, or None when the guard has not been armed."""
    return _policy
