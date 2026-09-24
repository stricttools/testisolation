/**
 * The environment isolation: a throwaway home, an isolated git configuration and
 * identity, transport lockdown, and credential stripping.
 */

import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
	type CleanupRegistry,
	onRelease,
	type Scope,
	scopeFor,
	setEnv,
	unsetEnv,
} from "./scope.js";

/**
 * The throwaway commit identity. The address is intentionally invalid: a commit
 * made under it can never be mistaken for one of the developer's own, and mail
 * to it goes nowhere.
 */
export const IDENTITY_NAME = "testisolation";
export const IDENTITY_EMAIL = "testisolation@example.invalid";

/**
 * What every helper program git might reach for is pinned to. It exists, it is
 * executable, and it always fails -- so the transport dies at the helper
 * instead of reaching the network or a real credential.
 */
const BLOCKED_COMMAND = "/bin/false";

/** Prefix for the throwaway home directory created under the system temp dir. */
const TEMP_PREFIX = "testisolation-env-";

/**
 * The closed list of ambient credential vectors that {@link stripCredentials}
 * removes from the environment. A test that genuinely needs one sets a FAKE
 * value itself.
 *
 * The list is identical to the Go module's `CredentialVars`, and identical to
 * the Python plugin's `CREDENTIAL_VARS` plus `GIT_ASKPASS`. That one variable
 * is the implementations' single deliberate divergence: the Python implementation pins it to
 * /bin/false, while this package and the Go module remove it. Both close the
 * same door -- git cannot obtain a credential either way -- and a cross-language
 * test in the Python suite holds the three lists in lockstep.
 */
export const CREDENTIAL_VARS: readonly string[] = [
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
];

/**
 * The XDG base directories repointed alongside HOME, with their location
 * relative to it.
 *
 * The relative paths are the XDG defaults on purpose: a tool that ignores the
 * environment variable and hardcodes ~/.config lands in the same throwaway
 * place, so no code path escapes the repoint.
 */
const XDG_DIRS: ReadonlyArray<{ env: string; rel: string }> = [
	{ env: "XDG_CONFIG_HOME", rel: ".config" },
	{ env: "XDG_DATA_HOME", rel: ".local/share" },
	{ env: "XDG_CACHE_HOME", rel: ".cache" },
	{ env: "XDG_STATE_HOME", rel: ".local/state" },
];

/**
 * Repoint HOME, USERPROFILE and the four XDG base directories
 * (XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME, XDG_STATE_HOME) at a fresh
 * temporary directory owned by this test, and return that directory. Every
 * variable is restored and the directory is removed when the test finishes.
 *
 * The XDG directories are repointed as well as HOME because a great many tools
 * read them FIRST: a suite that moved only HOME would still let a tool read the
 * developer's real ~/.config (gh's hosts.yml lives there) and write into their
 * real caches.
 *
 * The call is memoized per test: asking twice within the same test returns the
 * same directory rather than moving HOME again. Each subtest gets its own
 * context and therefore its own home.
 */
export function throwawayHome(registry: CleanupRegistry): string {
	const scope = scopeFor(registry);
	return homeFor(scope);
}

function homeFor(scope: Scope): string {
	if (scope.home !== undefined) {
		return scope.home;
	}
	const home = mkdtempSync(join(tmpdir(), TEMP_PREFIX));
	scope.tempDirs.push(home);
	scope.home = home;
	setEnv(scope, "HOME", home);
	setEnv(scope, "USERPROFILE", home);
	for (const dir of XDG_DIRS) {
		const path = join(home, ...dir.rel.split("/"));
		mkdirSync(path, { recursive: true, mode: 0o700 });
		setEnv(scope, dir.env, path);
	}
	return home;
}

/**
 * Cut git off from the developer's configuration and identity:
 * GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM point at empty files inside the
 * throwaway home (allocated through {@link throwawayHome} if this test has not
 * already), the author and committer identity become a throwaway one, and
 * GIT_TERMINAL_PROMPT is 0 so no git invocation can block a test on a password
 * prompt.
 *
 * The config files are empty rather than carrying the identity, because the
 * GIT_AUTHOR_* / GIT_COMMITTER_* variables below already supply it and outrank
 * any config file -- a git invocation that ignores the config path entirely
 * still cannot commit as the developer.
 *
 * core.hooksPath is deliberately NOT set. It overrides repo-local hooks too,
 * which would silently disable a suite's own pre-push-hook tests; an empty
 * global config already prevents the developer's hooks from firing.
 */
export function isolateGitConfig(registry: CleanupRegistry): void {
	const scope = scopeFor(registry);
	const home = homeFor(scope);
	for (const cfg of [
		{ env: "GIT_CONFIG_GLOBAL", file: "gitconfig-global" },
		{ env: "GIT_CONFIG_SYSTEM", file: "gitconfig-system" },
	]) {
		const path = join(home, cfg.file);
		writeFileSync(path, "", { mode: 0o600 });
		setEnv(scope, cfg.env, path);
	}
	setEnv(scope, "GIT_AUTHOR_NAME", IDENTITY_NAME);
	setEnv(scope, "GIT_AUTHOR_EMAIL", IDENTITY_EMAIL);
	setEnv(scope, "GIT_COMMITTER_NAME", IDENTITY_NAME);
	setEnv(scope, "GIT_COMMITTER_EMAIL", IDENTITY_EMAIL);
	setEnv(scope, "GIT_TERMINAL_PROMPT", "0");
}

/**
 * Restrict git to the local file transport for the duration of this test. Any
 * ssh://, https:// or git:// URL a test reaches for -- a real remote, a real
 * fetch, a real push -- fails at the protocol check instead of touching the
 * network.
 *
 * GIT_SSH_COMMAND and GIT_PROXY_COMMAND are pinned to /bin/false as a second,
 * independent layer. The protocol list is the first line and would be enough on
 * its own, but a test (or a tool under test) that sets GIT_ALLOW_PROTOCOL
 * itself would lift it -- and then the developer's real ssh, with their real
 * key and their real proxy, is what git would run. Pinning both helpers means
 * that path dies at an executable that only ever fails.
 */
export function lockdownTransports(registry: CleanupRegistry): void {
	const scope = scopeFor(registry);
	setEnv(scope, "GIT_ALLOW_PROTOCOL", "file");
	setEnv(scope, "GIT_SSH_COMMAND", BLOCKED_COMMAND);
	setEnv(scope, "GIT_PROXY_COMMAND", BLOCKED_COMMAND);
}

/**
 * Remove every variable in {@link CREDENTIAL_VARS} from the environment for the
 * duration of this test. The original values are restored when it finishes.
 */
export function stripCredentials(registry: CleanupRegistry): void {
	const scope = scopeFor(registry);
	for (const name of CREDENTIAL_VARS) {
		unsetEnv(scope, name);
	}
}

/**
 * Move the process working directory to `dir` for the duration of this test and
 * restore the previous one when it finishes.
 *
 * A failed restore FAILS the test rather than being logged and swallowed: the
 * process is then sitting in the wrong directory, and every later test in the
 * file would run against it. A test that reports the damage is the only honest
 * outcome.
 *
 * PWD is updated alongside the real working directory so that child processes
 * inheriting the environment agree with the parent about where they are.
 */
export function chdir(registry: CleanupRegistry, dir: string): void {
	const scope = scopeFor(registry);
	const previous = process.cwd();
	process.chdir(dir);
	setEnv(scope, "PWD", process.cwd());
	onRelease(scope, () => {
		try {
			process.chdir(previous);
		} catch (cause) {
			throw new Error(
				`testisolation: restoring the working directory to ${previous} after ` +
					`the test chdir'd to ${dir} failed -- every later test in this ` +
					"file now runs from the wrong directory",
				{ cause },
			);
		}
	});
}
