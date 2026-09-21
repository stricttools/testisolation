// Package pgcluster boots an ephemeral PostgreSQL cluster for a test binary.
//
// This is a cluster *launcher*, one layer below the per-test database managers
// consumers already have: it boots a real postmaster on a private tmpfs
// directory with fsync off, hands back a base libpq URL, and shuts the cluster
// down again. Creating and dropping a database per test is then an ordinary
// CREATE DATABASE against that URL.
//
// The model is one shared cluster per test binary, many ephemeral databases
// inside it. Booting a cluster costs roughly a second; creating a database
// inside a running one costs milliseconds. A per-test cluster would be neither.
//
// # Usage
//
// The shared cluster belongs in TestMain, where it can be started once and
// stopped once. [Start] is TB-free for exactly this reason, and its errors wrap
// sentinels so a machine without PostgreSQL skips instead of failing:
//
//	var cluster *pgcluster.Cluster
//
//	func TestMain(m *testing.M) {
//		started, err := pgcluster.Start("MYAPP_DATABASE_URL")
//		switch {
//		case errors.Is(err, pgcluster.ErrPostgresUnavailable):
//			// Leave cluster nil; each test skips with err.Error().
//		case err != nil:
//			fmt.Fprintln(os.Stderr, err)
//			os.Exit(1)
//		default:
//			cluster = started
//		}
//		code := m.Run()
//		if cluster != nil {
//			cluster.Stop()
//		}
//		os.Exit(code)
//	}
//
// A test then takes a database of its own, which is created, exported under the
// DSN variable, and dropped again when the test ends:
//
//	func TestSomething(t *testing.T) {
//		url := cluster.Database(t)
//		// MYAPP_DATABASE_URL now names a fresh empty database.
//	}
//
// [Ephemeral] is the TB-bound alternative for a suite that wants a whole cluster
// scoped to one test (or to one subtest) rather than to the binary. It fails the
// test rather than returning an error, and registers its own shutdown through
// TB.Cleanup.
//
// # The DSN variable is mandatory
//
// There is no default for dsnEnv: the variable an application reads its
// connection string from is the application's decision, and guessing it would
// either do nothing or silently point production configuration at a test
// cluster.
//
// # Zero dependencies
//
// The package depends only on the standard library and the PostgreSQL binaries
// it launches -- initdb, pg_ctl and psql. It drives them as subprocesses and
// never links a driver, so adopting the test isolation cannot drag a database
// driver into a consumer's module graph.
//
// # A killed test binary leaks its postmaster
//
// Read this before adopting the package. [Cluster.Stop] runs from TB.Cleanup or
// from TestMain, and both are ordinary Go code: neither runs when the test
// binary dies without unwinding -- SIGKILL, an editor or CI job cancelling the
// run, an OOM kill. When that happens the postmaster stays alive with its data
// directory deleted underneath it, and its socket directory survives as a stray.
//
// This is accepted, not solved. The Python implementation of the same launcher
// registers an atexit hook, which covers the interpreter's ordinary exit paths.
// Go has no equivalent: there is no runtime hook that fires on process exit, and
// the substitutes are worse than the leak. A signal handler cannot catch SIGKILL
// (the case that actually happens), and installing one would fight the consuming
// suite for the same signals; a watchdog goroutine dies with the process it is
// watching.
//
// The recorded alternative, not built: a PID-file reaper. Each cluster would
// record its postmaster PID and directories in a well-known registry file, and
// every later start would sweep the registry, killing any recorded postmaster
// whose data directory no longer exists and removing its leftovers. That turns
// an unbounded leak into one cleaned up at the next test run. It is a real
// design with real hazards (a stale PID can be reused by an unrelated process,
// and the registry becomes shared mutable state between concurrent test
// binaries), so it is written down here rather than shipped by default.
//
// Until then: the strays are visible and cheap to clear. Every directory this
// package creates is named stpg-*, so `pkill -f stpg-` ends any orphaned
// postmaster and `rm -rf /dev/shm/stpg-*` removes what it left behind. They live
// on a tmpfs, so a reboot clears them too.
//
// # No in-process network guard can see a C driver
//
// The cluster listens on a unix socket and nothing else, so it cannot collide
// with a real local server and cannot be reached from off the machine. That is
// the whole of the isolation this package provides, and it is worth being exact
// about what it is not.
//
// Go suites have no in-process network guard at all -- see the hygiene package's
// documentation for why one is not shipped -- so nothing intercepts a Go
// driver's dial in either direction. It is worth stating that even where such a
// guard exists it would not help: the Python plugin's socket guard is built on
// sys.addaudithook and sees only connects made through Python's socket module,
// so a libpq-backed driver (psycopg) opens its connection in C, entirely outside
// the guard's view. Adding the socket directory to an allowlist changes nothing
// for such a driver, because there is no event to allow.
//
// The protection that does work is the same one in every language: point the
// application's DSN at this cluster. A driver that connects to the URL under
// dsnEnv reaches a throwaway database on a private socket, whatever it is
// implemented in.
package pgcluster

import (
	"bytes"
	"errors"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

// fastSettings are server settings that make a throwaway cluster fast. Every
// one of them trades crash safety for speed, which is the correct trade for a
// cluster whose data directory is deleted at the end of the run and lives on a
// tmpfs anyway.
var fastSettings = []string{
	"fsync=off",
	"full_page_writes=off",
	"synchronous_commit=off",
	"wal_level=minimal",
	"max_wal_senders=0",
	"autovacuum=off",
}

const (
	defaultPort          = 5432
	defaultSuperuser     = "postgres"
	defaultMaintenanceDB = "postgres"
	defaultStartTimeout  = 60 * time.Second
)

// Cluster is a throwaway PostgreSQL cluster on a private tmpfs directory.
//
// A Cluster is created already started, by [Start] or [Ephemeral]. It is not
// safe for concurrent use by multiple goroutines: every test that touches one
// mutates process-wide environment state through TB.Setenv, which is itself
// incompatible with T.Parallel.
type Cluster struct {
	dsnEnv        string
	port          int
	superuser     string
	maintenanceDB string
	startTimeout  time.Duration
	dataParent    string
	socketParent  string
	binaries      Binaries
	haveBinaries  bool

	dataDir   string
	socketDir string
	logFile   string

	running bool

	// ownsEnv records who is responsible for putting dsnEnv back. Start sets the
	// variable itself and restores it in Stop; Ephemeral goes through TB.Setenv
	// and lets the testing package restore it.
	ownsEnv     bool
	previousDSN string
	dsnWasSet   bool
}

// Option customizes a cluster before it starts. Options are applied in the
// order they are given.
type Option func(*Cluster)

// Port sets the port the postmaster listens on. It is part of the socket file
// name (there is no TCP listener), so it counts toward the sun_path limit.
func Port(port int) Option { return func(c *Cluster) { c.port = port } }

// Superuser sets the name of the superuser initdb creates. It becomes the user
// in every URL this cluster hands out.
func Superuser(name string) Option { return func(c *Cluster) { c.superuser = name } }

// MaintenanceDB sets the database [Cluster.BaseURL] points at and that
// CREATE/DROP DATABASE statements are issued from.
func MaintenanceDB(name string) Option { return func(c *Cluster) { c.maintenanceDB = name } }

// DataParent pins the directory the cluster's data directory is created under,
// instead of trying the built-in candidates. An explicit choice is never
// second-guessed: if it is unusable, starting fails.
func DataParent(dir string) Option { return func(c *Cluster) { c.dataParent = dir } }

// SocketParent pins the directory the cluster's socket directory is created
// under, instead of trying the built-in candidates (/dev/shm, then /tmp). This
// is the escape route when the default parents produce a path past
// [SUNPathMax]. An explicit choice is never second-guessed.
func SocketParent(dir string) Option { return func(c *Cluster) { c.socketParent = dir } }

// UseBinaries supplies already-resolved PostgreSQL binaries, skipping
// discovery. A suite that calls [FindBinaries] once (to decide whether to skip)
// passes the result back through this option rather than paying for the search
// again.
func UseBinaries(b Binaries) Option {
	return func(c *Cluster) {
		c.binaries = b
		c.haveBinaries = true
	}
}

// StartTimeout sets how long pg_ctl is given to start and to stop the
// postmaster. It is passed through as whole seconds.
func StartTimeout(d time.Duration) Option { return func(c *Cluster) { c.startTimeout = d } }

// Start initdbs into tmpfs, starts a postmaster, exports its base URL under
// dsnEnv, and returns the running cluster. [Cluster.Stop] shuts it down again
// and restores dsnEnv to whatever it held before.
//
// Start takes no testing.TB so it can be called from TestMain, where there is
// none. Every error it returns wraps one of this package's sentinels; in
// particular [ErrPostgresUnavailable] is the "skip this suite" answer.
func Start(dsnEnv string, opts ...Option) (*Cluster, error) {
	c, err := newCluster(dsnEnv, opts...)
	if err != nil {
		return nil, err
	}
	if err := c.start(); err != nil {
		return nil, err
	}
	c.ownsEnv = true
	c.exportDSN()
	return c, nil
}

// Ephemeral starts a cluster bound to t: it is stopped, and everything it wrote
// is removed, when t finishes. The base URL is exported under dsnEnv through
// TB.Setenv, so the testing package restores the caller's own value.
//
// Failures fail t rather than being returned; a test that asks for a cluster
// outright has already decided it needs one. A suite that wants to SKIP when
// PostgreSQL is missing should start the cluster in TestMain with [Start] and
// check for [ErrPostgresUnavailable], or call [FindBinaries] first.
//
// TB.Setenv panics under T.Parallel. That is intended: a parallel test cannot
// own a process-wide variable like the DSN one.
func Ephemeral(t testing.TB, dsnEnv string, opts ...Option) *Cluster {
	t.Helper()
	c, err := newCluster(dsnEnv, opts...)
	if err != nil {
		t.Fatalf("pgcluster: %v", err)
		return nil
	}
	if err := c.start(); err != nil {
		t.Fatalf("pgcluster: %v", err)
		return nil
	}
	t.Cleanup(c.Stop)
	t.Setenv(dsnEnv, c.BaseURL())
	return c
}

func newCluster(dsnEnv string, opts ...Option) (*Cluster, error) {
	if dsnEnv == "" {
		return nil, fmt.Errorf(
			"%w: dsnEnv is required: the cluster's DSN is exported under the "+
				"environment variable the consuming application reads its "+
				"connection string from. There is no default name",
			ErrInvalidArgument)
	}
	c := &Cluster{
		dsnEnv:        dsnEnv,
		port:          defaultPort,
		superuser:     defaultSuperuser,
		maintenanceDB: defaultMaintenanceDB,
		startTimeout:  defaultStartTimeout,
	}
	for _, opt := range opts {
		opt(c)
	}
	return c, nil
}

// -- state ------------------------------------------------------------------

// Running reports whether the postmaster is up.
func (c *Cluster) Running() bool { return c.running }

// SocketDir is the directory holding the cluster's unix socket.
func (c *Cluster) SocketDir() string { return c.socketDir }

// DataDir is the cluster's data directory.
func (c *Cluster) DataDir() string { return c.dataDir }

// SocketPath is the full path of the cluster's unix socket file.
func (c *Cluster) SocketPath() string { return SocketPathFor(c.socketDir, c.port) }

// MaintenanceDB is the database [Cluster.BaseURL] points at.
func (c *Cluster) MaintenanceDB() string { return c.maintenanceDB }

// BaseURL is the libpq URL of the maintenance database. This is what gets
// exported under dsnEnv, and what a per-test database manager connects to in
// order to CREATE DATABASE.
func (c *Cluster) BaseURL() string { return c.URLFor(c.maintenanceDB) }

// URLFor is the libpq URL of dbname in this cluster.
func (c *Cluster) URLFor(dbname string) string {
	return fmt.Sprintf("postgresql://%s@/%s?host=%s&port=%d",
		url.PathEscape(c.superuser),
		url.PathEscape(dbname),
		url.PathEscape(c.socketDir),
		c.port)
}

// -- lifecycle --------------------------------------------------------------

func (c *Cluster) start() error {
	if c.running {
		return nil
	}
	if os.Geteuid() == 0 {
		return fmt.Errorf(
			"%w: PostgreSQL refuses to run as root, so an ephemeral cluster "+
				"cannot be started by a root process. Run the suite as an "+
				"unprivileged user", ErrPostgresUnavailable)
	}
	if !c.haveBinaries {
		binaries, err := FindBinaries()
		if err != nil {
			return err
		}
		c.binaries = binaries
		c.haveBinaries = true
	}

	dataParent, err := pickParent(c.dataParent, defaultDataParents, c.port, false, "data")
	if err != nil {
		return err
	}
	socketParent, err := pickParent(c.socketParent, defaultSocketParents, c.port, true, "socket")
	if err != nil {
		return err
	}

	if c.dataDir, err = makeTempDir(dataParent, "stpg-data-"); err != nil {
		return fmt.Errorf("%w: creating the data directory under %s: %v", ErrCluster, dataParent, err)
	}
	if c.socketDir, err = makeTempDir(socketParent, tempDirPrefixProbe); err != nil {
		c.Stop()
		return fmt.Errorf("%w: creating the socket directory under %s: %v", ErrCluster, socketParent, err)
	}
	// The real directory exists now; re-check the real path rather than the
	// probe used to choose the parent.
	if _, err := CheckSocketDir(c.socketDir, c.port); err != nil {
		c.Stop()
		return err
	}
	c.logFile = filepath.Join(filepath.Dir(c.dataDir), filepath.Base(c.dataDir)+".log")

	if err := c.initdb(); err != nil {
		c.Stop()
		return err
	}
	if err := c.pgCtlStart(); err != nil {
		c.Stop()
		return err
	}
	c.running = true
	return nil
}

// Stop stops the postmaster and deletes everything it wrote. It is idempotent,
// and it is safe to call on a cluster whose start failed part-way.
//
// Nothing calls it automatically on process death: see the package
// documentation on the killed-binary leak.
func (c *Cluster) Stop() {
	if c.running {
		c.running = false
		if c.ownsEnv {
			c.restoreDSN()
		}
	}
	if c.dataDir != "" && fileExists(filepath.Join(c.dataDir, "postmaster.pid")) {
		// -m immediate: no checkpoint, no clean shutdown bookkeeping. The data
		// directory is about to be deleted, so durability is pointless and the
		// shutdown should be as fast as the boot was.
		_, _, _ = c.run([]string{
			c.binaries.PgCtl,
			"-D", c.dataDir,
			"-m", "immediate",
			"-w",
			"-t", c.timeoutSeconds(),
			"stop",
		}, false)
	}
	for _, path := range []string{c.dataDir, c.socketDir, c.logFile} {
		if path == "" {
			continue
		}
		if isDir(path) {
			_ = os.RemoveAll(path)
			continue
		}
		_ = os.Remove(path)
	}
	c.dataDir = ""
	c.socketDir = ""
	c.logFile = ""
}

// -- databases --------------------------------------------------------------

// CreateDatabase creates a database in this cluster and returns its libpq URL.
// An empty name gets a fresh generated one -- the ordinary per-test case.
func (c *Cluster) CreateDatabase(name string) (string, error) {
	if name == "" {
		name = GenerateName()
	}
	if err := checkName(name); err != nil {
		return "", err
	}
	if _, err := c.SQL(fmt.Sprintf("CREATE DATABASE %q", name)); err != nil {
		return "", err
	}
	return c.URLFor(name), nil
}

// DropDatabase drops a database, disconnecting anything still attached to it.
func (c *Cluster) DropDatabase(name string) error {
	if err := checkName(name); err != nil {
		return err
	}
	// WITH (FORCE) terminates leftover connections instead of failing on them: a
	// test that leaked a connection should not break teardown.
	_, err := c.SQL(fmt.Sprintf("DROP DATABASE IF EXISTS %q WITH (FORCE)", name))
	return err
}

// Database creates a fresh database for the duration of t, exports its URL
// under the cluster's DSN variable through TB.Setenv, and drops it when t
// finishes. It returns the database's URL.
//
// This is the per-test half of the model: one cluster for the binary, one
// database per test. An application that reads its connection string from the
// environment lands in this test's own database without knowing the difference.
func (c *Cluster) Database(t testing.TB) string {
	t.Helper()
	name := GenerateName()
	dbURL, err := c.CreateDatabase(name)
	if err != nil {
		t.Fatalf("pgcluster: %v", err)
		return ""
	}
	t.Cleanup(func() {
		if err := c.DropDatabase(name); err != nil {
			t.Errorf("pgcluster: dropping the per-test database: %v", err)
		}
	})
	t.Setenv(c.dsnEnv, dbURL)
	return dbURL
}

// -- queries ----------------------------------------------------------------

// SQL runs one statement against the maintenance database through psql and
// returns its trimmed output.
//
// A subprocess rather than a driver on purpose: this module depends on the
// standard library only, and a database driver would be a dependency every
// consumer inherits.
func (c *Cluster) SQL(statement string) (string, error) {
	return c.sqlAgainst(c.BaseURL(), statement)
}

// SQLIn runs one statement against a named database in this cluster.
func (c *Cluster) SQLIn(dbname, statement string) (string, error) {
	return c.sqlAgainst(c.URLFor(dbname), statement)
}

func (c *Cluster) sqlAgainst(dbURL, statement string) (string, error) {
	stdout, _, err := c.run([]string{
		c.binaries.Psql,
		"--no-psqlrc",
		"--quiet",
		"--no-align",
		"--tuples-only",
		"--set=ON_ERROR_STOP=1",
		"--dbname", dbURL,
		"--command", statement,
	}, true)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(stdout), nil
}

// -- internals --------------------------------------------------------------

func (c *Cluster) timeoutSeconds() string {
	seconds := int(c.startTimeout / time.Second)
	if seconds < 1 {
		seconds = 1
	}
	return strconv.Itoa(seconds)
}

// cleanEnv is the environment the PostgreSQL programs run with.
//
// Every PG* variable is dropped: an ambient PGHOST, PGDATABASE, PGSERVICE or
// PGPASSFILE would silently redirect these commands at the developer's real
// cluster. The locale is pinned so error messages are the ones this package's
// callers expect to match on.
func cleanEnv() []string {
	entries := os.Environ()
	env := make([]string, 0, len(entries)+2)
	for _, entry := range entries {
		name, _, _ := strings.Cut(entry, "=")
		if strings.HasPrefix(name, "PG") || name == "LC_ALL" || name == "LANG" {
			continue
		}
		env = append(env, entry)
	}
	return append(env, "LC_ALL=C", "LANG=C")
}

func (c *Cluster) run(argv []string, check bool) (string, string, error) {
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Env = cleanEnv()
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	runErr := cmd.Run()
	if check && runErr != nil {
		return stdout.String(), stderr.String(),
			fmt.Errorf("%w: %s", ErrCluster,
				c.failureMessage(argv, stdout.String(), stderr.String(), runErr))
	}
	return stdout.String(), stderr.String(), nil
}

func (c *Cluster) failureMessage(argv []string, stdout, stderr string, runErr error) string {
	status := runErr.Error()
	var exitErr *exec.ExitError
	if errors.As(runErr, &exitErr) {
		status = "exit status " + strconv.Itoa(exitErr.ExitCode())
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%s failed with %s.\ncommand: %s\n",
		filepath.Base(argv[0]), status, strings.Join(argv, " "))
	if trimmed := strings.TrimSpace(stdout); trimmed != "" {
		fmt.Fprintf(&b, "stdout:\n%s\n", trimmed)
	}
	if trimmed := strings.TrimSpace(stderr); trimmed != "" {
		fmt.Fprintf(&b, "stderr:\n%s\n", trimmed)
	}
	if c.logFile != "" {
		if log, err := os.ReadFile(c.logFile); err == nil {
			if trimmed := strings.TrimSpace(string(log)); trimmed != "" {
				fmt.Fprintf(&b, "server log:\n%s\n", trimmed)
			}
		}
	}
	return b.String()
}

func (c *Cluster) initdb() error {
	_, _, err := c.run([]string{
		c.binaries.Initdb,
		"--pgdata", c.dataDir,
		// The cluster is deleted at the end of the run, so paying for durable
		// initialization would be pure waste.
		"--no-sync",
		"--username", c.superuser,
		"--auth-local=trust",
		"--auth-host=reject",
		"--encoding=UTF8",
		"--locale=C",
	}, true)
	return err
}

func (c *Cluster) pgCtlStart() error {
	options := []string{
		// No TCP at all: the cluster is reachable through its unix socket and
		// nothing else, so it cannot collide with a real local server and cannot
		// be reached from off the machine.
		"-c listen_addresses=",
		"-c unix_socket_directories=" + c.socketDir,
		"-p " + strconv.Itoa(c.port),
	}
	for _, setting := range fastSettings {
		options = append(options, "-c "+setting)
	}
	_, _, err := c.run([]string{
		c.binaries.PgCtl,
		"-D", c.dataDir,
		"-l", c.logFile,
		"-o", strings.Join(options, " "),
		"-w",
		"-t", c.timeoutSeconds(),
		"start",
	}, true)
	return err
}

func (c *Cluster) exportDSN() {
	c.previousDSN, c.dsnWasSet = os.LookupEnv(c.dsnEnv)
	_ = os.Setenv(c.dsnEnv, c.BaseURL())
}

func (c *Cluster) restoreDSN() {
	if c.dsnWasSet {
		_ = os.Setenv(c.dsnEnv, c.previousDSN)
	} else {
		_ = os.Unsetenv(c.dsnEnv)
	}
	c.previousDSN = ""
	c.dsnWasSet = false
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
