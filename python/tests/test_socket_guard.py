"""The audit-hook socket guard.

Every stance test runs in a SUBPROCESS. ``sys.addaudithook`` cannot be removed
once installed, so a differing stance is only observable in a fresh
interpreter -- and that constraint is itself the guard's main strength.
"""

from __future__ import annotations

import socket

import pytest

from testisolation.socketguard import Policy, is_loopback


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


TCP_SERVER_HELPERS = """
import socket
import contextlib


@contextlib.contextmanager
def listening(port):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    try:
        yield srv
    finally:
        srv.close()
"""


# ---------------------------------------------------------------------------
# Default stance: network off.
# ---------------------------------------------------------------------------


def test_loopback_connect_is_denied_by_default(inner):
    port = _free_port()
    inner.write(
        {
            "helpers.py": TCP_SERVER_HELPERS,
            "test_denied.py": (
                "import socket\n"
                "import pytest\n"
                "from helpers import listening\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                f"PORT = {port}\n"
                "\n"
                "def test_loopback_denied():\n"
                "    with listening(PORT):\n"
                "        with pytest.raises(NetworkBlocked) as exc:\n"
                "            socket.create_connection(('127.0.0.1', PORT), timeout=5)\n"
                "        assert 'BLOCKED' in str(exc.value)\n"
            ),
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_public_name_resolution_is_denied_by_default(inner):
    inner.write(
        {
            "test_dns.py": (
                "import socket\n"
                "import pytest\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                "def test_resolution_denied():\n"
                "    with pytest.raises(NetworkBlocked) as exc:\n"
                "        socket.getaddrinfo('example.com', 443)\n"
                "    assert 'name resolution' in str(exc.value)\n"
            )
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_gethostbyname_is_denied_by_default(inner):
    """``gethostbyname`` is a real DNS query on its own audit event.

    It does NOT go through ``getaddrinfo``, so a guard that only watches
    ``socket.getaddrinfo`` lets a resolver packet leave the machine.
    """
    inner.write(
        {
            "test_dns.py": (
                "import socket\n"
                "import pytest\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                "def test_gethostbyname_denied():\n"
                "    with pytest.raises(NetworkBlocked) as exc:\n"
                "        socket.gethostbyname('example.com')\n"
                "    assert 'name resolution' in str(exc.value)\n"
                "\n"
                "def test_gethostbyname_ex_denied():\n"
                "    with pytest.raises(NetworkBlocked):\n"
                "        socket.gethostbyname_ex('example.com')\n"
            )
        }
    )
    inner.run("-q").assert_outcomes(passed=2)


def test_gethostbyaddr_is_denied_by_default(inner):
    """Reverse resolution is a DNS query too, on its own audit event."""
    inner.write(
        {
            "test_dns.py": (
                "import socket\n"
                "import pytest\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                "def test_gethostbyaddr_denied():\n"
                "    with pytest.raises(NetworkBlocked) as exc:\n"
                "        socket.gethostbyaddr('93.184.216.34')\n"
                "    assert 'name resolution' in str(exc.value)\n"
            )
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_udp_sendmsg_is_denied_by_default(inner):
    """``sendmsg`` sends a datagram without ever calling ``connect``.

    ``sendto`` was guarded from the start; ``sendmsg`` is its sibling with the
    same ``(sock, address)`` audit payload, and an unguarded one is a UDP
    packet leaving the machine.
    """
    inner.write(
        {
            "test_udp.py": (
                "import socket\n"
                "import pytest\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                "def test_sendmsg_denied():\n"
                "    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
                "    try:\n"
                "        with pytest.raises(NetworkBlocked) as exc:\n"
                "            sock.sendmsg([b'testisolation'], [], 0, ('8.8.8.8', 53))\n"
                "    finally:\n"
                "        sock.close()\n"
                "    assert '8.8.8.8:53' in str(exc.value)\n"
            )
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_refusal_is_not_swallowed_by_a_broad_except(inner):
    """``NetworkBlocked`` is a ``BaseException`` so sloppy code cannot hide it."""
    inner.write(
        {
            "test_swallow.py": (
                "import socket\n"
                "import pytest\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                "def test_not_swallowed():\n"
                "    with pytest.raises(NetworkBlocked):\n"
                "        try:\n"
                "            socket.getaddrinfo('example.com', 443)\n"
                "        except Exception:\n"
                "            raise AssertionError('refusal was swallowed')\n"
            )
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Loopback stance, declared explicitly.
# ---------------------------------------------------------------------------


def test_loopback_allow_permits_local_connects(inner):
    port = _free_port()
    inner.write(
        {
            "helpers.py": TCP_SERVER_HELPERS,
            "test_loopback.py": (
                "import socket\n"
                "import pytest\n"
                "from helpers import listening\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                f"PORT = {port}\n"
                "\n"
                "def test_loopback_allowed():\n"
                "    with listening(PORT):\n"
                "        conn = socket.create_connection(('127.0.0.1', PORT), timeout=5)\n"
                "        conn.close()\n"
                "\n"
                "def test_public_still_denied():\n"
                "    with pytest.raises(NetworkBlocked):\n"
                "        socket.getaddrinfo('example.com', 443)\n"
            ),
        },
        ini={"testisolation_loopback": "allow"},
    )
    inner.run("-q").assert_outcomes(passed=2)


def test_loopback_allow_permits_every_guarded_event(inner):
    """Every event the guard watches honors the loopback carve-out.

    Resolution may still fail on an offline machine, so the assertion is
    "not refused by the guard", never "resolution succeeded".
    """
    port = _free_port()
    inner.write(
        {
            "test_loopback_events.py": (
                "import socket\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                f"PORT = {port}\n"
                "\n"
                "def not_blocked(fn, *args):\n"
                "    try:\n"
                "        fn(*args)\n"
                "    except NetworkBlocked as exc:\n"
                "        raise AssertionError(f'the guard refused loopback: {exc}')\n"
                "    except OSError:\n"
                "        pass  # resolution/delivery may fail offline; the guard let it through\n"
                "\n"
                "def test_gethostbyname_localhost():\n"
                "    not_blocked(socket.gethostbyname, 'localhost')\n"
                "\n"
                "def test_gethostbyaddr_loopback():\n"
                "    not_blocked(socket.gethostbyaddr, '127.0.0.1')\n"
                "\n"
                "def test_getaddrinfo_localhost():\n"
                "    not_blocked(socket.getaddrinfo, 'localhost', PORT)\n"
                "\n"
                "def test_sendto_loopback():\n"
                "    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
                "    try:\n"
                "        not_blocked(sock.sendto, b'x', ('127.0.0.1', PORT))\n"
                "    finally:\n"
                "        sock.close()\n"
                "\n"
                "def test_sendmsg_loopback():\n"
                "    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
                "    try:\n"
                "        not_blocked(sock.sendmsg, [b'x'], [], 0, ('127.0.0.1', PORT))\n"
                "    finally:\n"
                "        sock.close()\n"
                "\n"
                "def test_sendmsg_on_a_connected_socket_carries_no_address():\n"
                "    # The audit payload's address is None here; the destination was\n"
                "    # already authorized at connect time, so this must not be refused.\n"
                "    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
                "    try:\n"
                "        not_blocked(sock.connect, ('127.0.0.1', PORT))\n"
                "        not_blocked(sock.sendmsg, [b'x'])\n"
                "    finally:\n"
                "        sock.close()\n"
            ),
        },
        ini={"testisolation_loopback": "allow"},
    )
    inner.run("-q").assert_outcomes(passed=6)


def test_allowlisted_host_permits_its_name_resolution(inner):
    """An allowlisted host resolves through every resolution event."""
    port = _free_port()
    inner.write(
        {
            "test_allowlisted_dns.py": (
                "import socket\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                "def not_blocked(fn, *args):\n"
                "    try:\n"
                "        fn(*args)\n"
                "    except NetworkBlocked as exc:\n"
                "        raise AssertionError(f'the guard refused an allowlisted host: {exc}')\n"
                "    except OSError:\n"
                "        pass\n"
                "\n"
                "def test_gethostbyname_allowlisted():\n"
                "    not_blocked(socket.gethostbyname, 'localhost')\n"
            ),
        },
        ini={
            "testisolation_sockets": "allowlist",
            "testisolation_loopback": "deny",
            "testisolation_socket_allowlist": [f"localhost:{port}"],
        },
    )
    inner.run("-q").assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# host:port granularity -- the reason pytest-socket was rejected.
# ---------------------------------------------------------------------------


def test_allowlist_is_port_specific(inner):
    allowed = _free_port()
    denied = _free_port()
    inner.write(
        {
            "helpers.py": TCP_SERVER_HELPERS,
            "test_ports.py": (
                "import socket\n"
                "import pytest\n"
                "from helpers import listening\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                f"ALLOWED = {allowed}\n"
                f"DENIED = {denied}\n"
                "\n"
                "def test_allowlisted_port_connects():\n"
                "    with listening(ALLOWED):\n"
                "        conn = socket.create_connection(('127.0.0.1', ALLOWED), timeout=5)\n"
                "        conn.close()\n"
                "\n"
                "def test_other_port_on_the_same_host_is_denied():\n"
                "    with listening(DENIED):\n"
                "        with pytest.raises(NetworkBlocked) as exc:\n"
                "            socket.create_connection(('127.0.0.1', DENIED), timeout=5)\n"
                "        assert str(DENIED) in str(exc.value)\n"
            ),
        },
        ini={
            "testisolation_sockets": "allowlist",
            "testisolation_loopback": "deny",
            "testisolation_socket_allowlist": [f"127.0.0.1:{allowed}"],
        },
    )
    inner.run("-q").assert_outcomes(passed=2)


# ---------------------------------------------------------------------------
# Unix sockets -- the DB-test case.
# ---------------------------------------------------------------------------


UNIX_HELPERS = """
import contextlib
import socket


@contextlib.contextmanager
def unix_listening(path):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(path))
    srv.listen(1)
    try:
        yield srv
    finally:
        srv.close()
"""


def test_unix_socket_denied_by_default(inner, tmp_path):
    sock_path = tmp_path / "denied.sock"
    inner.write(
        {
            "helpers.py": UNIX_HELPERS,
            "test_unix.py": (
                "import socket\n"
                "import pytest\n"
                "from helpers import unix_listening\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                f"PATH = {str(sock_path)!r}\n"
                "\n"
                "def test_unix_denied():\n"
                "    with unix_listening(PATH):\n"
                "        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "        with pytest.raises(NetworkBlocked) as exc:\n"
                "            client.connect(PATH)\n"
                "        assert 'unix-socket connect' in str(exc.value)\n"
            ),
        }
    )
    inner.run("-q").assert_outcomes(passed=1)


def test_unix_socket_exact_path_allowlist(inner, tmp_path):
    allowed = tmp_path / "allowed.sock"
    other = tmp_path / "other.sock"
    inner.write(
        {
            "helpers.py": UNIX_HELPERS,
            "test_unix.py": (
                "import socket\n"
                "import pytest\n"
                "from helpers import unix_listening\n"
                "from testisolation import NetworkBlocked\n"
                "\n"
                f"ALLOWED = {str(allowed)!r}\n"
                f"OTHER = {str(other)!r}\n"
                "\n"
                "def test_allowlisted_path_connects():\n"
                "    with unix_listening(ALLOWED):\n"
                "        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "        client.connect(ALLOWED)\n"
                "        client.close()\n"
                "\n"
                "def test_sibling_path_is_denied():\n"
                "    with unix_listening(OTHER):\n"
                "        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "        with pytest.raises(NetworkBlocked):\n"
                "            client.connect(OTHER)\n"
            ),
        },
        ini={"testisolation_unix_socket_allowlist": [str(allowed)]},
    )
    inner.run("-q").assert_outcomes(passed=2)


def test_unix_socket_directory_prefix_allowlist(inner, tmp_path):
    """A trailing '/' allowlists a directory -- what an ephemeral cluster needs."""
    sock_dir = tmp_path / "cluster"
    sock_dir.mkdir()
    inner.write(
        {
            "helpers.py": UNIX_HELPERS,
            "test_unix.py": (
                "import os\n"
                "import socket\n"
                "from helpers import unix_listening\n"
                "\n"
                f"SOCK_DIR = {str(sock_dir)!r}\n"
                "\n"
                "def test_any_socket_in_the_directory_connects():\n"
                "    path = os.path.join(SOCK_DIR, '.s.PGSQL.5432')\n"
                "    with unix_listening(path):\n"
                "        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
                "        client.connect(path)\n"
                "        client.close()\n"
            ),
        },
        ini={"testisolation_unix_socket_allowlist": [f"{sock_dir}/"]},
    )
    inner.run("-q").assert_outcomes(passed=1)


# ---------------------------------------------------------------------------
# Unit-level: loopback classification and policy decisions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "127.0.0.53", "::1", "[::1]", "localhost", "LOCALHOST", "::1%lo"],
)
def test_is_loopback_true(host):
    assert is_loopback(host) is True


@pytest.mark.parametrize(
    "host", ["example.com", "8.8.8.8", "192.168.1.5", "2606:4700::1111", "", "0.0.0.0"]
)
def test_is_loopback_false(host):
    assert is_loopback(host) is False


def test_policy_describe_names_every_axis():
    policy = Policy(
        sockets="allowlist",
        loopback="deny",
        allowlist=frozenset({("127.0.0.1", "5432")}),
        unix_allowlist=("/run/pg/",),
    )
    described = policy.describe()
    for fragment in (
        "testisolation_sockets=allowlist",
        "testisolation_loopback=deny",
        "127.0.0.1:5432",
        "/run/pg/",
    ):
        assert fragment in described


def test_guard_is_armed_in_this_very_session():
    from testisolation import socketguard

    policy = socketguard.current_policy()
    assert policy is not None
    assert policy.sockets == "deny"
    assert policy.loopback == "deny"


def test_this_suite_cannot_reach_the_network():
    """A meta-test on the suite you are reading: egress is off, right now."""
    from testisolation import NetworkBlocked

    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("pypi.org", 443)
