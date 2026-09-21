package hygiene

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestIsolateBindsEveryIsolationPieceAndRestoresEverything(t *testing.T) {
	poisoned := map[string]string{
		"HOME":               "/poisoned/home",
		"USERPROFILE":        "/poisoned/home",
		"GIT_CONFIG_GLOBAL":  "/poisoned/gitconfig",
		"GIT_CONFIG_SYSTEM":  "/poisoned/gitconfig",
		"GIT_AUTHOR_NAME":    "Real Developer",
		"GIT_ALLOW_PROTOCOL": "",
		"GH_TOKEN":           "ghp_realtoken",
		"OPENAI_API_KEY":     "sk-realkey",
	}
	for name, value := range poisoned {
		t.Setenv(name, value)
	}

	t.Run("during", func(t *testing.T) {
		Isolate(t)

		home := os.Getenv("HOME")
		if home == "/poisoned/home" {
			t.Fatal("HOME still points at the poisoned value")
		}
		if got := ThrowawayHome(t); got != home {
			t.Errorf("ThrowawayHome() = %q but HOME = %q; Isolate did not reuse the same home", got, home)
		}
		if path := os.Getenv("GIT_CONFIG_GLOBAL"); !strings.HasPrefix(path, home+string(filepath.Separator)) {
			t.Errorf("GIT_CONFIG_GLOBAL = %q, want a file inside the throwaway home", path)
		}
		if got := os.Getenv("GIT_AUTHOR_EMAIL"); got != identityEmail {
			t.Errorf("GIT_AUTHOR_EMAIL = %q, want %q", got, identityEmail)
		}
		if got := os.Getenv("GIT_ALLOW_PROTOCOL"); got != "file" {
			t.Errorf("GIT_ALLOW_PROTOCOL = %q, want %q", got, "file")
		}
		for _, name := range []string{"GH_TOKEN", "OPENAI_API_KEY"} {
			if value, ok := os.LookupEnv(name); ok {
				t.Errorf("%s survived Isolate with value %q", name, value)
			}
		}
	})

	for name, value := range poisoned {
		if got := os.Getenv(name); got != value {
			t.Errorf("%s = %q after the subtest, want the poisoned value %q back", name, got, value)
		}
	}
}

func TestIsolatePreserveKeepsOnlyTheRequestedEnumVariables(t *testing.T) {
	realHome := t.TempDir()
	t.Setenv("HOME", realHome)
	t.Setenv("GOCACHE", "/an/explicit/build/cache")
	unsetEnv(t, "GOPATH")
	unsetEnv(t, "GOMODCACHE")
	unsetEnv(t, "CARGO_HOME")

	t.Run("during", func(t *testing.T) {
		Isolate(t, Preserve(GoCache, GoModCache))

		if got := os.Getenv("HOME"); got == realHome {
			t.Fatal("HOME was not repointed")
		}
		// An explicitly-set variable keeps its value.
		if got := os.Getenv("GOCACHE"); got != "/an/explicit/build/cache" {
			t.Errorf("GOCACHE = %q, want the value it had before the repoint", got)
		}
		// An unset one is pinned to its default under the REAL home, which is
		// the whole point: the module cache must not move when HOME does.
		want := filepath.Join(realHome, "go", "pkg", "mod")
		if got := os.Getenv("GOMODCACHE"); got != want {
			t.Errorf("GOMODCACHE = %q, want %q", got, want)
		}
		// Anything not asked for stays untouched -- Preserve is opt-in per
		// variable, not per toolchain.
		for _, name := range []string{"GOPATH", "CARGO_HOME"} {
			if value, ok := os.LookupEnv(name); ok {
				t.Errorf("%s = %q, but it was never passed to Preserve", name, value)
			}
		}
	})

	for _, name := range []string{"GOPATH", "GOMODCACHE", "CARGO_HOME"} {
		if value, ok := os.LookupEnv(name); ok {
			t.Errorf("%s = %q after the subtest, want it unset again", name, value)
		}
	}
}

func TestPreserveResolvesTheModuleCacheAgainstAnExplicitGopath(t *testing.T) {
	realHome := t.TempDir()
	t.Setenv("HOME", realHome)
	t.Setenv("GOPATH", "/explicit/gopath")
	unsetEnv(t, "GOMODCACHE")

	t.Run("during", func(t *testing.T) {
		Isolate(t, Preserve(GoPath, GoModCache))
		if got := os.Getenv("GOPATH"); got != "/explicit/gopath" {
			t.Errorf("GOPATH = %q, want it preserved", got)
		}
		if got, want := os.Getenv("GOMODCACHE"), "/explicit/gopath/pkg/mod"; got != want {
			t.Errorf("GOMODCACHE = %q, want %q", got, want)
		}
	})
}

func TestPreserveRejectsAValueOutsideTheClosedEnum(t *testing.T) {
	rec := &recordingTB{TB: t}
	preserveVars(rec, []KnownVar{KnownVar(9999)})
	if len(rec.fatals) != 1 {
		t.Fatalf("expected exactly one failure, got %v", rec.fatals)
	}
	if !strings.Contains(rec.fatals[0], "unknown KnownVar") {
		t.Errorf("failure message does not name the problem: %q", rec.fatals[0])
	}
}

func TestPreserveIgnoresADuplicateRequest(t *testing.T) {
	realHome := t.TempDir()
	t.Setenv("HOME", realHome)
	unsetEnv(t, "GOCACHE")

	t.Run("during", func(t *testing.T) {
		Isolate(t, Preserve(GoCache), Preserve(GoCache))
		want := filepath.Join(realHome, ".cache", "go-build")
		if got := os.Getenv("GOCACHE"); got != want {
			t.Errorf("GOCACHE = %q, want %q", got, want)
		}
	})
}

func TestKnownVarNamesItself(t *testing.T) {
	for value, known := range knownVars {
		if value.String() != known.name {
			t.Errorf("KnownVar(%d).String() = %q, want %q", int(value), value.String(), known.name)
		}
		if value.Env() != known.env {
			t.Errorf("%s.Env() = %q, want %q", known.name, value.Env(), known.env)
		}
	}
	if got := KnownVar(9999).String(); got != "KnownVar(9999)" {
		t.Errorf("an out-of-range KnownVar stringified as %q", got)
	}
	if got := KnownVar(9999).Env(); got != "" {
		t.Errorf("an out-of-range KnownVar named the environment variable %q", got)
	}
}

func TestKnownVarsAreDistinct(t *testing.T) {
	seen := map[string]KnownVar{}
	for value, known := range knownVars {
		if other, ok := seen[known.env]; ok {
			t.Errorf("%s and %s both pin %s", value, other, known.env)
		}
		seen[known.env] = value
	}
	if len(knownVars) != 10 {
		t.Errorf("the preserve enum has %d members; update this test (and the "+
			"Python plugin's PRESERVE_VARS) deliberately, never by accident", len(knownVars))
	}
}
