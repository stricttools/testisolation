package hygiene

import (
	"os"
	"path/filepath"
	"sync"
	"testing"
)

// The throwaway commit identity. It is intentionally an invalid address: a
// commit made under it can never be mistaken for one of the developer's own,
// and mail to it goes nowhere.
const (
	identityName  = "testisolation"
	identityEmail = "testisolation@example.invalid"
)

// blockedCommand is what every helper program git might reach for is pinned to.
// It exists, it is executable, and it always fails -- so the transport dies at
// the helper instead of reaching the network or a real credential.
const blockedCommand = "/bin/false"

// CredentialVars is the closed list of ambient credential vectors that
// [StripCredentials] removes from the environment. A test that genuinely needs
// one sets a FAKE value itself with TB.Setenv.
//
// The list mirrors the Python plugin's CREDENTIAL_VARS, plus GIT_ASKPASS. That
// one variable is the two implementations' single deliberate divergence: the Python implementation
// pins it to /bin/false, while this package removes it here. Both close the same
// door -- git cannot obtain a credential either way -- and a cross-language test
// holds the rest of the two lists identical.
var CredentialVars = []string{
	"SSH_AUTH_SOCK",
	"GIT_ASKPASS",
	"GITHUB_TOKEN",
	"GH_TOKEN",
	"GITHUB_API_TOKEN",
	"NPM_TOKEN",
	"NODE_AUTH_TOKEN",
	"PYPI_TOKEN",
	"TWINE_PASSWORD",
	"TWINE_USERNAME",
	"CARGO_REGISTRY_TOKEN",
	"AWS_ACCESS_KEY_ID",
	"AWS_SECRET_ACCESS_KEY",
	"AWS_SESSION_TOKEN",
	"CLOUDFLARE_API_TOKEN",
	"CF_PAGES_API_TOKEN",
	"ANTHROPIC_API_KEY",
	"OPENAI_API_KEY",
}

var (
	homesMu sync.Mutex
	// homes memoizes the throwaway home per TB so that Isolate and a later
	// direct ThrowawayHome call (or IsolateGitConfig, which needs the home to
	// write into) all agree on one directory per test.
	homes = map[testing.TB]string{}
)

// xdgDirs are the XDG base directories repointed alongside HOME, mapped to
// their location relative to it.
//
// The relative paths are the XDG defaults on purpose: a tool that ignores the
// environment variable and hardcodes ~/.config lands in the same throwaway
// place, so no code path escapes the repoint.
var xdgDirs = []struct{ env, rel string }{
	{"XDG_CONFIG_HOME", ".config"},
	{"XDG_DATA_HOME", ".local/share"},
	{"XDG_CACHE_HOME", ".cache"},
	{"XDG_STATE_HOME", ".local/state"},
}

// ThrowawayHome repoints HOME, USERPROFILE and the four XDG base directories
// (XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME, XDG_STATE_HOME) at a fresh
// temporary directory owned by t, and returns that directory. Every variable is
// restored when t finishes, and the directory is removed with the rest of t's
// TempDir tree.
//
// The XDG directories are repointed as well as HOME because a great many tools
// read them FIRST: a suite that moved only HOME would still let a tool read the
// developer's real ~/.config (gh's hosts.yml lives there) and write into their
// real caches.
//
// The call is memoized per TB: asking twice within the same test returns the
// same directory rather than moving HOME again. Each subtest gets its own TB
// and therefore its own home.
func ThrowawayHome(t testing.TB) string {
	t.Helper()
	homesMu.Lock()
	existing, ok := homes[t]
	homesMu.Unlock()
	if ok {
		return existing
	}

	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)

	for _, dir := range xdgDirs {
		path := filepath.Join(home, filepath.FromSlash(dir.rel))
		if err := os.MkdirAll(path, 0o700); err != nil {
			t.Fatalf("hygiene: creating the throwaway %s directory: %v", dir.env, err)
			return home
		}
		t.Setenv(dir.env, path)
	}

	homesMu.Lock()
	homes[t] = home
	homesMu.Unlock()
	t.Cleanup(func() {
		homesMu.Lock()
		delete(homes, t)
		homesMu.Unlock()
	})
	return home
}

// IsolateGitConfig cuts git off from the developer's configuration and
// identity: GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM point at empty files inside
// the throwaway home (which it allocates through [ThrowawayHome] if the test
// has not already), the author and committer identity become a throwaway one,
// and GIT_TERMINAL_PROMPT is 0 so no git invocation can ever block a test on a
// password prompt.
//
// The config files are empty rather than carrying the identity, because the
// GIT_AUTHOR_* / GIT_COMMITTER_* variables below already supply it and outrank
// any config file -- a git invocation that ignores the config path entirely
// still cannot commit as the developer.
//
// core.hooksPath is deliberately NOT set. It overrides repo-local hooks too,
// which would silently disable a suite's own pre-push-hook tests; an empty
// global config already prevents the developer's hooks from firing.
func IsolateGitConfig(t testing.TB) {
	t.Helper()
	home := ThrowawayHome(t)

	for _, cfg := range []struct{ env, file string }{
		{"GIT_CONFIG_GLOBAL", "gitconfig-global"},
		{"GIT_CONFIG_SYSTEM", "gitconfig-system"},
	} {
		path := filepath.Join(home, cfg.file)
		if err := os.WriteFile(path, nil, 0o600); err != nil {
			t.Fatalf("hygiene: writing the throwaway %s file: %v", cfg.env, err)
			return
		}
		t.Setenv(cfg.env, path)
	}

	t.Setenv("GIT_AUTHOR_NAME", identityName)
	t.Setenv("GIT_AUTHOR_EMAIL", identityEmail)
	t.Setenv("GIT_COMMITTER_NAME", identityName)
	t.Setenv("GIT_COMMITTER_EMAIL", identityEmail)
	t.Setenv("GIT_TERMINAL_PROMPT", "0")
}

// LockdownTransports restricts git to the local file transport for the
// duration of t. Any ssh://, https:// or git:// URL a test reaches for -- a
// real remote, a real fetch, a real push -- fails at the protocol check instead
// of touching the network.
//
// GIT_SSH_COMMAND and GIT_PROXY_COMMAND are pinned to /bin/false as a second,
// independent layer. The protocol list is the first line and would be enough on
// its own, but a test (or a tool under test) that sets GIT_ALLOW_PROTOCOL
// itself would lift it -- and then the developer's real ssh, with their real
// key and their real proxy, is what git would run. Pinning both helpers means
// that path dies at an executable that only ever fails.
func LockdownTransports(t testing.TB) {
	t.Helper()
	t.Setenv("GIT_ALLOW_PROTOCOL", "file")
	t.Setenv("GIT_SSH_COMMAND", blockedCommand)
	t.Setenv("GIT_PROXY_COMMAND", blockedCommand)
}

// StripCredentials removes every variable in [CredentialVars] from the
// environment for the duration of t. The original values are restored when t
// finishes.
func StripCredentials(t testing.TB) {
	t.Helper()
	for _, name := range CredentialVars {
		unsetEnv(t, name)
	}
}

// unsetEnv removes name from the environment until t finishes.
//
// TB has no Unsetenv, so this goes through TB.Setenv first and then unsets the
// (now empty) variable directly. Routing through TB.Setenv is what registers
// the restore -- and what keeps the T.Parallel panic intact, which a bare
// os.Unsetenv would silently skip.
func unsetEnv(t testing.TB, name string) {
	t.Helper()
	t.Setenv(name, "")
	if err := os.Unsetenv(name); err != nil {
		t.Fatalf("hygiene: unsetting %s: %v", name, err)
	}
}
