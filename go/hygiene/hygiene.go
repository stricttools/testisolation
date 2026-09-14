// Package hygiene is an always-on test-isolation floor that makes a test suite
// structurally unable to reach the real HOME, an ambient credential, the
// developer's git identity, or a remote git transport.
//
// The pieces of the floor are a throwaway HOME, an isolated git config and
// identity, transport lockdown, credential stripping, and cleanup-restoring
// chdir.
//
// # Usage
//
// The composite entry point is [Isolate]. One call at the top of a test (or of
// a helper every test in the package funnels through) binds the whole floor:
//
//	func TestSomething(t *testing.T) {
//		hygiene.Isolate(t)
//		// HOME is a throwaway dir, git reads an empty global config with a
//		// throwaway identity, only the file:// transport is allowed, and every
//		// ambient credential variable is gone.
//	}
//
// Each piece is also exported on its own -- [ThrowawayHome],
// [IsolateGitConfig], [LockdownTransports], [StripCredentials] -- for suites
// that need one guarantee without the others. [Chdir] is separate on purpose:
// it is a per-test tool, not part of the floor.
//
// # Contract
//
// Every helper takes a [testing.TB], calls TB.Helper so failures point at the
// caller, and undoes itself through TB.Cleanup. Nothing here is global or
// process-wide: the isolation lives exactly as long as the test (or subtest)
// whose TB was passed in.
//
// # Parallelism
//
// Every environment mutation goes through TB.Setenv, which panics when the test
// has called T.Parallel. That is intended and is not worked around: a parallel
// test cannot own a process-wide variable like HOME, so a suite that wants this
// floor cannot run its tests in parallel with each other. The panic makes the
// conflict immediate and obvious instead of letting one test's HOME leak into
// another's.
//
// # No socket guard
//
// Unlike the Python plugin, this package ships no network guard. Go has no
// equivalent of sys.addaudithook, so there is no in-process interception point
// that could refuse a dial without patching the runtime. Network isolation for
// Go suites is owned by the sandbox runner (the bubblewrap wrapper that runs
// the suite with no network namespace), not by this package. Do not add a
// half-guard here that only covers net.Dial: a partial guard reads as a
// guarantee and is worse than none.
package hygiene

import (
	"fmt"
	"os"
	"strings"
	"testing"
)

// Option customizes [Isolate]. The only option is [Preserve]; there is
// deliberately no option that turns a floor piece off.
type Option func(*options)

type options struct {
	preserve []KnownVar
}

// Isolate binds the full environment floor for the duration of t: the
// preserved toolchain caches (if any) are pinned first, then HOME and the four
// XDG base directories are repointed at a throwaway directory, git's global and
// system config are emptied, the git identity is replaced, transports are
// locked down to file:// with git's ssh and proxy helpers pinned to a command
// that always fails, and every ambient credential variable is removed.
//
// The throwaway home is not returned; call [ThrowawayHome] (which is memoized
// per TB and returns the same directory Isolate created) when the path is
// needed.
func Isolate(t testing.TB, opts ...Option) {
	t.Helper()
	var cfg options
	for _, opt := range opts {
		opt(&cfg)
	}
	// Before HOME moves: the preserved caches all default to a location under
	// the real home, so their values must be pinned while it is still readable.
	preserveVars(t, cfg.preserve)
	ThrowawayHome(t)
	IsolateGitConfig(t)
	LockdownTransports(t)
	StripCredentials(t)
}

// KnownVar names one toolchain cache variable that a suite may opt into
// preserving across the HOME repoint. The enum is closed: a caller cannot ask
// for an arbitrary variable name, so a credential vector can never become
// preservable by typo.
type KnownVar int

// The closed preserve enum. Every entry names a cache or package location that
// holds build artifacts, not secrets, and that would otherwise send a toolchain
// into a cold rebuild (or hide an already-installed module) once HOME moves.
const (
	GoPath KnownVar = iota
	GoModCache
	GoCache
	PythonUserBase
	CargoHome
	RustupHome
	NpmCache
	UvCache
	PipCache
	GradleUserHome
)

type knownVar struct {
	name string
	env  string
	// def is the variable's default location, with {home} standing for the real
	// home directory and {gopath} for the resolved GOPATH.
	def string
}

// knownVars mirrors the Python plugin's PRESERVE_VARS table one-for-one so a
// polyglot repo declares the same set on both sides.
var knownVars = map[KnownVar]knownVar{
	GoPath:         {"GoPath", "GOPATH", "{home}/go"},
	GoModCache:     {"GoModCache", "GOMODCACHE", "{gopath}/pkg/mod"},
	GoCache:        {"GoCache", "GOCACHE", "{home}/.cache/go-build"},
	PythonUserBase: {"PythonUserBase", "PYTHONUSERBASE", "{home}/.local"},
	CargoHome:      {"CargoHome", "CARGO_HOME", "{home}/.cargo"},
	RustupHome:     {"RustupHome", "RUSTUP_HOME", "{home}/.rustup"},
	NpmCache:       {"NpmCache", "npm_config_cache", "{home}/.npm"},
	UvCache:        {"UvCache", "UV_CACHE_DIR", "{home}/.cache/uv"},
	PipCache:       {"PipCache", "PIP_CACHE_DIR", "{home}/.cache/pip"},
	GradleUserHome: {"GradleUserHome", "GRADLE_USER_HOME", "{home}/.gradle"},
}

// String returns the enum member's Go name, or a marker for an out-of-range
// value.
func (v KnownVar) String() string {
	if known, ok := knownVars[v]; ok {
		return known.name
	}
	return fmt.Sprintf("KnownVar(%d)", int(v))
}

// Env returns the environment variable this enum member pins.
func (v KnownVar) Env() string {
	if known, ok := knownVars[v]; ok {
		return known.env
	}
	return ""
}

// Preserve opts the named toolchain caches into surviving the HOME repoint.
// Each one is pinned to its current value, or to its default location under the
// real home when it is unset, before HOME changes.
func Preserve(v ...KnownVar) Option {
	return func(o *options) {
		o.preserve = append(o.preserve, v...)
	}
}

// preserveVars pins the opted-in toolchain variables. It must run BEFORE HOME
// is repointed.
func preserveVars(t testing.TB, vars []KnownVar) {
	t.Helper()
	if len(vars) == 0 {
		return
	}
	realHome := os.Getenv("HOME")
	if realHome == "" {
		// Nothing to anchor the defaults to; an already-unset HOME means the
		// caches cannot be derived, and pinning them to a guess would be worse
		// than leaving them alone.
		return
	}
	gopath := os.Getenv("GOPATH")
	if gopath == "" {
		gopath = realHome + "/go"
	}
	seen := make(map[KnownVar]bool, len(vars))
	for _, v := range vars {
		known, ok := knownVars[v]
		if !ok {
			t.Fatalf("hygiene: Preserve got an unknown KnownVar (%d); only the "+
				"closed enum declared in this package is accepted", int(v))
			return
		}
		if seen[v] {
			continue
		}
		seen[v] = true
		value := os.Getenv(known.env)
		if value == "" {
			value = expandDefault(known.def, realHome, gopath)
		}
		if value == "" {
			continue
		}
		t.Setenv(known.env, value)
		if known.env == "GOPATH" {
			gopath = value
		}
	}
}

func expandDefault(def, home, gopath string) string {
	return strings.NewReplacer("{home}", home, "{gopath}", gopath).Replace(def)
}
