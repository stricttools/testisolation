// Live tests for the ephemeral PostgreSQL cluster.
//
// Every test here talks to a real postmaster. When the machine has no
// PostgreSQL server installed, they skip with the discovery error verbatim -- a
// precise reason ("initdb not found on PATH nor in ...") rather than a bare
// "skipped".
//
// The shared cluster is started in TestMain, which is the arrangement the
// package is built for: one cluster per test binary, one database per test.

package pgcluster

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const dsnEnvVar = "TESTISOLATION_TEST_DATABASE_URL"

var (
	// shared is the cluster every live test uses. It is nil when this machine
	// has no usable PostgreSQL, in which case skipReason says why.
	shared         *Cluster
	sharedBinaries Binaries
	skipReason     string
)

func TestMain(m *testing.M) {
	os.Exit(runSuite(m))
}

func runSuite(m *testing.M) int {
	binaries, err := FindBinaries()
	if err != nil {
		// The discovery failure is the skip reason, verbatim.
		skipReason = err.Error()
		return m.Run()
	}
	sharedBinaries = binaries

	started, err := Start(dsnEnvVar, UseBinaries(binaries))
	switch {
	case errors.Is(err, ErrPostgresUnavailable):
		skipReason = err.Error()
	case err != nil:
		fmt.Fprintln(os.Stderr, err)
		return 1
	default:
		shared = started
	}
	code := m.Run()
	if shared != nil {
		shared.Stop()
	}
	return code
}

// cluster returns the shared cluster, skipping the test when the machine cannot
// host one.
func cluster(t *testing.T) *Cluster {
	t.Helper()
	if shared == nil {
		t.Skip(skipReason)
	}
	return shared
}

// binaries returns the resolved PostgreSQL binaries, skipping the test when
// there are none. Tests that boot a cluster of their own pass them back in so
// they do not pay for discovery again.
func binaries(t *testing.T) Binaries {
	t.Helper()
	if sharedBinaries.Initdb == "" {
		t.Skip(skipReason)
	}
	return sharedBinaries
}

func TestTheClusterBootsAndAnswersAQuery(t *testing.T) {
	c := cluster(t)
	if !c.Running() {
		t.Fatal("the shared cluster is not running")
	}
	if got := mustSQL(t, c, "SELECT 1"); got != "1" {
		t.Errorf("SELECT 1 returned %q", got)
	}
	if version := mustSQL(t, c, "SHOW server_version"); version == "" {
		t.Error("SHOW server_version returned nothing")
	} else {
		t.Logf("server_version = %s", version)
	}
	if !fileExists(c.SocketPath()) {
		t.Errorf("no socket at %s", c.SocketPath())
	}
}

func TestTheSocketPathStaysFarBelowTheKernelLimit(t *testing.T) {
	c := cluster(t)
	if length := len(c.SocketPath()); length > SUNPathMax {
		t.Errorf("the socket path is %d bytes, past the %d-byte limit: %s",
			length, SUNPathMax, c.SocketPath())
	}
}

func TestTheClusterListensOnAUnixSocketOnly(t *testing.T) {
	// No TCP port is opened, so the cluster cannot collide with a real server.
	c := cluster(t)
	if got := mustSQL(t, c, "SHOW listen_addresses"); got != "" {
		t.Errorf("listen_addresses = %q, wanted empty", got)
	}
}

func TestTheDataDirectoryIsAThrowawayOne(t *testing.T) {
	c := cluster(t)
	if !isDir(c.DataDir()) {
		t.Fatalf("the data directory %s is not a directory", c.DataDir())
	}
	if !fileExists(filepath.Join(c.DataDir(), "PG_VERSION")) {
		t.Errorf("no PG_VERSION in %s", c.DataDir())
	}
	if got := mustSQL(t, c, "SHOW fsync"); got != "off" {
		t.Errorf("fsync = %q, wanted off", got)
	}
}

func TestTheDSNIsExportedUnderTheDeclaredVariable(t *testing.T) {
	c := cluster(t)
	if got := os.Getenv(dsnEnvVar); got != c.BaseURL() {
		t.Errorf("%s = %q, wanted %q", dsnEnvVar, got, c.BaseURL())
	}
	decoded := strings.ReplaceAll(c.BaseURL(), "%2F", "/")
	if !strings.Contains(decoded, c.SocketDir()) {
		t.Errorf("the base URL does not carry the socket directory: %s", c.BaseURL())
	}
}

func TestTheDSNVariableIsRestoredWhenTheClusterStops(t *testing.T) {
	// A consumer's own value for the variable survives the run.
	own := dsnEnvVar + "_OWN"
	t.Setenv(own, "postgresql://pre-existing/value")

	c, err := Start(own, UseBinaries(binaries(t)))
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	if got := os.Getenv(own); got != c.BaseURL() {
		c.Stop()
		t.Fatalf("%s = %q while running, wanted the cluster's base URL", own, got)
	}
	c.Stop()
	if got := os.Getenv(own); got != "postgresql://pre-existing/value" {
		t.Errorf("%s = %q after Stop, wanted the pre-existing value", own, got)
	}
}

func TestTheDSNVariableIsUnsetAgainWhenItWasNeverSet(t *testing.T) {
	own := dsnEnvVar + "_OWN"
	// TB has no Unsetenv; going through Setenv first is what registers the
	// restore for the real test.
	t.Setenv(own, "")
	if err := os.Unsetenv(own); err != nil {
		t.Fatalf("unsetting %s: %v", own, err)
	}

	c, err := Start(own, UseBinaries(binaries(t)))
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	if _, ok := os.LookupEnv(own); !ok {
		c.Stop()
		t.Fatalf("%s was not exported while the cluster ran", own)
	}
	c.Stop()
	if value, ok := os.LookupEnv(own); ok {
		t.Errorf("%s survived the cluster as %q, wanted it unset", own, value)
	}
}

func TestBootsFastEnoughToBeASharedFixture(t *testing.T) {
	// The whole model rests on a cluster boot being cheap. This is also the
	// live exercise of the TB-bound entry point: the cluster below is stopped
	// and removed by the subtest's cleanup, not by an explicit Stop.
	base := cluster(t)
	bins := binaries(t)
	var (
		elapsed   time.Duration
		dataDir   string
		socketDir string
	)
	t.Run("ephemeral", func(t *testing.T) {
		started := time.Now()
		c := Ephemeral(t, dsnEnvVar, UseBinaries(bins))
		elapsed = time.Since(started)
		dataDir, socketDir = c.DataDir(), c.SocketDir()
		if got := os.Getenv(dsnEnvVar); got != c.BaseURL() {
			t.Errorf("%s = %q, wanted the ephemeral cluster's base URL", dsnEnvVar, got)
		}
		if got := mustSQL(t, c, "SELECT 1"); got != "1" {
			t.Errorf("SELECT 1 returned %q", got)
		}
	})
	t.Logf("cluster boot took %v", elapsed)
	if elapsed > 10*time.Second {
		t.Errorf("cluster boot took %v", elapsed)
	}
	for _, path := range []string{dataDir, socketDir} {
		if fileExists(path) {
			t.Errorf("%s survived the test that owned the cluster", path)
		}
	}
	if got := os.Getenv(dsnEnvVar); got != base.BaseURL() {
		t.Errorf("%s = %q after the subtest, wanted the shared cluster's base URL",
			dsnEnvVar, got)
	}
}

func TestEphemeralDatabasesAreIsolatedFromEachOther(t *testing.T) {
	c := cluster(t)
	first := createDatabase(t, c, "test_isolation_a")
	second := createDatabase(t, c, "test_isolation_b")
	if first == second {
		t.Fatal("two databases got the same URL")
	}
	if _, err := c.SQLIn("test_isolation_a", "CREATE TABLE only_in_a (id int)"); err != nil {
		t.Fatalf("creating the table: %v", err)
	}
	if got := tableCount(t, c, "test_isolation_a", "only_in_a"); got != "1" {
		t.Errorf("only_in_a is not in its own database (count %q)", got)
	}
	if got := tableCount(t, c, "test_isolation_b", "only_in_a"); got != "0" {
		t.Errorf("only_in_a leaked into the other database (count %q)", got)
	}
}

func TestAnEphemeralDatabaseIsDroppedOnTheWayOut(t *testing.T) {
	c := cluster(t)
	var name string
	t.Run("owner", func(t *testing.T) {
		dbURL := c.Database(t)
		name = databaseNameFromURL(t, dbURL)
		if !databaseExists(t, c, name) {
			t.Fatalf("%s was not created", name)
		}
	})
	if databaseExists(t, c, name) {
		t.Errorf("%s survived the test that owned it", name)
	}
}

func TestAnEphemeralDatabaseIsDroppedEvenWhenTheTestFails(t *testing.T) {
	c := cluster(t)
	// The failing test is simulated through the recording TB: a real failing
	// subtest would fail this one too, and the point under test is that the
	// cleanup runs and succeeds regardless of the verdict.
	recorder := &recordingTB{TB: t}
	dbURL := c.Database(recorder)
	name := databaseNameFromURL(t, dbURL)
	if !databaseExists(t, c, name) {
		t.Fatalf("%s was not created", name)
	}

	recorder.Errorf("deliberate")
	recorder.runCleanups()

	if databaseExists(t, c, name) {
		t.Errorf("%s survived a failing test", name)
	}
	if len(recorder.errors) != 1 {
		t.Errorf("the drop reported errors of its own: %v", recorder.errors[1:])
	}
}

func TestExportingAPerTestDatabaseSwapsTheDSNAndPutsItBack(t *testing.T) {
	c := cluster(t)
	base := os.Getenv(dsnEnvVar)
	t.Run("owner", func(t *testing.T) {
		dbURL := c.Database(t)
		if got := os.Getenv(dsnEnvVar); got != dbURL {
			t.Errorf("%s = %q, wanted the per-test database URL %q", dsnEnvVar, got, dbURL)
		}
	})
	if got := os.Getenv(dsnEnvVar); got != base {
		t.Errorf("%s = %q after the test, wanted %q", dsnEnvVar, got, base)
	}
}

func TestAGeneratedDatabaseNameNeedsNoArgument(t *testing.T) {
	c := cluster(t)
	dbURL, err := c.CreateDatabase("")
	if err != nil {
		t.Fatalf("CreateDatabase: %v", err)
	}
	name := databaseNameFromURL(t, dbURL)
	t.Cleanup(func() {
		if err := c.DropDatabase(name); err != nil {
			t.Errorf("DropDatabase: %v", err)
		}
	})
	if !strings.HasPrefix(name, "test_") {
		t.Errorf("the generated name %q does not carry the test_ prefix", name)
	}
	if got := mustSQL(t, c, "SELECT 1"); got != "1" {
		t.Errorf("SELECT 1 returned %q", got)
	}
}

func TestTheInCoreExtensionSetIsAvailable(t *testing.T) {
	// plpgsql is in-core, so its absence would mean a broken installation.
	c := cluster(t)
	name := "test_extensions"
	createDatabase(t, c, name)

	listing, err := c.SQLIn(name, "SELECT name FROM pg_available_extensions ORDER BY name")
	if err != nil {
		t.Fatalf("listing extensions: %v", err)
	}
	available := make(map[string]bool)
	for _, line := range strings.Split(listing, "\n") {
		available[strings.TrimSpace(line)] = true
	}
	if !available["plpgsql"] {
		t.Fatal("plpgsql is not available; this is not a working PostgreSQL installation")
	}
	// Anything else the machine happens to ship must actually load. pgvector is
	// the one this fleet cares about; it is checked only when present, so the
	// test is honest on a machine without it.
	for _, extension := range []string{"pgcrypto", "vector"} {
		if !available[extension] {
			continue
		}
		if _, err := c.SQLIn(name, fmt.Sprintf("CREATE EXTENSION %q", extension)); err != nil {
			t.Errorf("creating the %s extension: %v", extension, err)
			continue
		}
		count, err := c.SQLIn(name, fmt.Sprintf(
			"SELECT count(*) FROM pg_extension WHERE extname = '%s'", extension))
		if err != nil {
			t.Errorf("counting the %s extension: %v", extension, err)
			continue
		}
		if count != "1" {
			t.Errorf("the %s extension did not load (count %q)", extension, count)
		}
	}
}

func TestAmbientPGVariablesCannotRedirectTheCluster(t *testing.T) {
	// A stray PGHOST/PGDATABASE must not point these commands elsewhere.
	c := cluster(t)
	t.Setenv("PGHOST", "/nonexistent-host-dir")
	t.Setenv("PGDATABASE", "nonexistent_db")
	t.Setenv("PGUSER", "nonexistent_user")
	if got := mustSQL(t, c, "SELECT current_database()"); got != c.MaintenanceDB() {
		t.Errorf("current_database() = %q, wanted %q", got, c.MaintenanceDB())
	}
}

func TestStoppingRemovesEveryDirectoryItCreated(t *testing.T) {
	own := dsnEnvVar + "_OWN"
	t.Setenv(own, "")
	if err := os.Unsetenv(own); err != nil {
		t.Fatalf("unsetting %s: %v", own, err)
	}
	c, err := Start(own, UseBinaries(binaries(t)))
	if err != nil {
		t.Fatalf("Start: %v", err)
	}
	dataDir, socketDir := c.DataDir(), c.SocketDir()
	if !isDir(dataDir) || !isDir(socketDir) {
		c.Stop()
		t.Fatalf("the cluster did not create both directories (%s, %s)", dataDir, socketDir)
	}

	c.Stop()

	if fileExists(dataDir) {
		t.Errorf("the data directory %s survived Stop", dataDir)
	}
	if fileExists(socketDir) {
		t.Errorf("the socket directory %s survived Stop", socketDir)
	}
	if fileExists(filepath.Join(filepath.Dir(dataDir), filepath.Base(dataDir)+".log")) {
		t.Errorf("the server log survived Stop")
	}
	if c.Running() {
		t.Error("the cluster still reports itself as running")
	}
	// Idempotent: a second stop (a fixture teardown after an explicit stop) must
	// not panic or resurrect anything.
	c.Stop()
}

// -- helpers ----------------------------------------------------------------

func mustSQL(t *testing.T, c *Cluster, statement string) string {
	t.Helper()
	out, err := c.SQL(statement)
	if err != nil {
		t.Fatalf("%s: %v", statement, err)
	}
	return out
}

// createDatabase creates a named database and drops it when the test ends.
func createDatabase(t *testing.T, c *Cluster, name string) string {
	t.Helper()
	dbURL, err := c.CreateDatabase(name)
	if err != nil {
		t.Fatalf("creating %s: %v", name, err)
	}
	t.Cleanup(func() {
		if err := c.DropDatabase(name); err != nil {
			t.Errorf("dropping %s: %v", name, err)
		}
	})
	return dbURL
}

func databaseExists(t *testing.T, c *Cluster, name string) bool {
	t.Helper()
	count, err := c.SQL(fmt.Sprintf(
		"SELECT count(*) FROM pg_database WHERE datname = '%s'", name))
	if err != nil {
		t.Fatalf("looking for the %s database: %v", name, err)
	}
	return count == "1"
}

func tableCount(t *testing.T, c *Cluster, dbname, table string) string {
	t.Helper()
	count, err := c.SQLIn(dbname, fmt.Sprintf(
		"SELECT count(*) FROM pg_tables WHERE tablename = '%s'", table))
	if err != nil {
		t.Fatalf("counting %s in %s: %v", table, dbname, err)
	}
	return count
}

func databaseNameFromURL(t *testing.T, dbURL string) string {
	t.Helper()
	parsed, err := url.Parse(dbURL)
	if err != nil {
		t.Fatalf("parsing %q: %v", dbURL, err)
	}
	return strings.TrimPrefix(parsed.Path, "/")
}
