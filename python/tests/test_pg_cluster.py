"""Live tests for the ephemeral PostgreSQL cluster.

Every test here boots a real postmaster. When the machine has no PostgreSQL
server installed, they skip with the discovery error verbatim -- a precise
reason ("initdb not found on PATH nor in ...") rather than a bare "skipped".
"""

from __future__ import annotations

import os
import time

import pytest

from testisolation.pgcluster import (
    SUN_PATH_MAX,
    EphemeralCluster,
    PostgresUnavailable,
    ephemeral_cluster,
    find_binaries,
)

DSN_ENV = "TESTISOLATION_TEST_DATABASE_URL"


@pytest.fixture(scope="module")
def binaries():
    try:
        return find_binaries()
    except PostgresUnavailable as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def cluster(binaries):
    """One cluster shared by this module -- the model the helper is built for."""
    with ephemeral_cluster(DSN_ENV, binaries=binaries) as running:
        yield running


def test_the_cluster_boots_and_answers_a_query(cluster):
    assert cluster.running
    assert cluster.sql("SELECT 1") == "1"
    version = cluster.sql("SHOW server_version")
    assert version
    assert os.path.exists(cluster.socket_path)


def test_the_socket_path_stays_far_below_the_kernel_limit(cluster):
    assert len(cluster.socket_path.encode()) <= SUN_PATH_MAX


def test_the_cluster_listens_on_a_unix_socket_only(cluster):
    """No TCP port is opened, so the cluster cannot collide with a real server."""
    assert cluster.sql("SHOW listen_addresses") == ""


def test_the_data_directory_is_a_throwaway_one(cluster):
    assert cluster.data_dir.is_dir()
    assert (cluster.data_dir / "PG_VERSION").exists()
    assert cluster.sql("SHOW fsync") == "off"


def test_the_dsn_is_exported_under_the_declared_variable(cluster):
    assert os.environ[DSN_ENV] == cluster.base_url
    assert str(cluster.socket_dir) in cluster.base_url.replace("%2F", "/")


def test_the_dsn_variable_is_restored_when_the_cluster_stops(binaries, monkeypatch):
    """A consumer's own value for the variable survives the session."""
    monkeypatch.setenv(DSN_ENV, "postgresql://pre-existing/value")
    with ephemeral_cluster(DSN_ENV, binaries=binaries) as own:
        assert os.environ[DSN_ENV] == own.base_url
    assert os.environ[DSN_ENV] == "postgresql://pre-existing/value"


def test_the_dsn_variable_is_unset_again_when_it_was_never_set(binaries, monkeypatch):
    monkeypatch.delenv(DSN_ENV, raising=False)
    with ephemeral_cluster(DSN_ENV, binaries=binaries):
        assert DSN_ENV in os.environ
    assert DSN_ENV not in os.environ


def test_boots_fast_enough_to_be_a_session_fixture(binaries):
    """The whole model rests on a cluster boot being cheap."""
    started = time.perf_counter()
    with ephemeral_cluster(DSN_ENV, binaries=binaries):
        elapsed = time.perf_counter() - started
    assert elapsed < 10, f"cluster boot took {elapsed:.2f}s"


def test_ephemeral_databases_are_isolated_from_each_other(cluster):
    with (
        cluster.database("test_isolation_a") as url_a,
        cluster.database("test_isolation_b") as url_b,
    ):
        assert url_a != url_b
        cluster.sql("CREATE TABLE only_in_a (id int)", dbname="test_isolation_a")
        assert _table_count(cluster, "test_isolation_a", "only_in_a") == "1"
        assert _table_count(cluster, "test_isolation_b", "only_in_a") == "0"


def test_an_ephemeral_database_is_dropped_on_the_way_out(cluster):
    with cluster.database("test_dropped_after") as url:
        assert "test_dropped_after" in url
        assert _database_exists(cluster, "test_dropped_after")
    assert not _database_exists(cluster, "test_dropped_after")


def test_an_ephemeral_database_is_dropped_even_when_the_block_raises(cluster):
    with (
        pytest.raises(RuntimeError, match="deliberate"),
        cluster.database("test_dropped_on_error"),
    ):
        raise RuntimeError("deliberate")
    assert not _database_exists(cluster, "test_dropped_on_error")


def test_exporting_a_per_test_database_swaps_the_dsn_and_puts_it_back(cluster):
    base = os.environ[DSN_ENV]
    with cluster.database("test_exported", export=True) as url:
        assert os.environ[DSN_ENV] == url
        assert "test_exported" in os.environ[DSN_ENV]
    assert os.environ[DSN_ENV] == base


def test_a_generated_database_name_needs_no_argument(cluster):
    with cluster.database() as url:
        assert cluster.sql("SELECT 1") == "1"
        assert "/test_" in url


def test_the_in_core_extension_set_is_available(cluster):
    """plpgsql is in-core, so its absence would mean a broken installation."""
    with cluster.database("test_extensions"):
        available = cluster.sql(
            "SELECT name FROM pg_available_extensions ORDER BY name",
            dbname="test_extensions",
        ).splitlines()
        assert "plpgsql" in available
        # Anything else the machine happens to ship must actually load. pgvector
        # is the one this fleet cares about; it is checked only when present, so
        # the test is honest on a machine without it.
        for extension in ("pgcrypto", "vector"):
            if extension in available:
                cluster.sql(
                    f'CREATE EXTENSION "{extension}"', dbname="test_extensions"
                )
                assert (
                    cluster.sql(
                        "SELECT count(*) FROM pg_extension WHERE extname = "
                        f"'{extension}'",
                        dbname="test_extensions",
                    )
                    == "1"
                )


def test_ambient_pg_variables_cannot_redirect_the_cluster(cluster, monkeypatch):
    """A stray PGHOST/PGDATABASE must not point these commands elsewhere."""
    monkeypatch.setenv("PGHOST", "/nonexistent-host-dir")
    monkeypatch.setenv("PGDATABASE", "nonexistent_db")
    monkeypatch.setenv("PGUSER", "nonexistent_user")
    assert cluster.sql("SELECT current_database()") == cluster.maintenance_db


def test_stopping_removes_every_directory_it_created(binaries):
    own = EphemeralCluster(DSN_ENV, binaries=binaries)
    own.start()
    data_dir = own.data_dir
    socket_dir = own.socket_dir
    assert data_dir.exists() and socket_dir.exists()
    own.stop()
    assert not data_dir.exists()
    assert not socket_dir.exists()
    assert not own.running
    # Idempotent: a second stop (the atexit path, or a fixture teardown after an
    # explicit stop) must not raise.
    own.stop()


def _database_exists(cluster: EphemeralCluster, name: str) -> bool:
    return (
        cluster.sql(f"SELECT count(*) FROM pg_database WHERE datname = '{name}'") == "1"
    )


def _table_count(cluster: EphemeralCluster, dbname: str, table: str) -> str:
    return cluster.sql(
        f"SELECT count(*) FROM pg_tables WHERE tablename = '{table}'", dbname=dbname
    )
