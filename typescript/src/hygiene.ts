/**
 * The composite entry point and the closed preserve enum.
 *
 * ## No socket guard
 *
 * Unlike the Python plugin, this package ships no network guard, for the same
 * reason the Go module ships none: there is no honest in-process interception
 * point. Python has `sys.addaudithook`, a hook the interpreter itself calls on
 * every socket operation and which cannot be removed once installed. Node has
 * no equivalent. The nearest thing is monkey-patching `net.Socket.prototype
 * .connect`, which misses `dgram`, misses anything reaching the syscall through
 * a native addon, and is undone by any code that re-imports `node:net` through
 * a fresh module loader. A partial guard reads as a guarantee and is worse than
 * none, so this package does not ship one.
 *
 * Network isolation for Node suites is owned by the sandbox runner -- the
 * bubblewrap wrapper that runs the suite with no network namespace -- and
 * {@link requireSandbox} is what makes sure the suite actually goes through it.
 *
 * ## No push guard
 *
 * The Python plugin intercepts `subprocess.Popen` to refuse a real `git push`
 * to a non-local remote. The equivalent here would be patching
 * `node:child_process`, and it fails the same honesty test: `spawn`, `exec`,
 * `execFile`, `fork` and their sync twins all reach the same binding, native
 * addons bypass the module entirely, and a fresh loader restores the original.
 * {@link lockdownTransports} already closes the outcome that guard exists to
 * prevent -- a push over ssh:// or https:// dies at the protocol check with the
 * ssh and proxy helpers pinned to a command that only fails.
 */

import {
	isolateGitConfig,
	lockdownTransports,
	stripCredentials,
	throwawayHome,
} from "./env.js";
import { type CleanupRegistry, scopeFor, setEnv } from "./scope.js";

/**
 * One toolchain cache variable a suite may opt into preserving across the HOME
 * repoint. The type is a closed union of the names below, so a credential
 * vector can never become preservable by typo.
 */
export type KnownVar = keyof typeof KNOWN_VARS;

/**
 * The closed preserve enum. Every entry names a cache or package location that
 * holds build artifacts, not secrets, and that would otherwise send a toolchain
 * into a cold rebuild (or hide an already-installed module) once HOME moves.
 *
 * The table mirrors the Go module's `knownVars` and the Python plugin's
 * `PRESERVE_VARS` one-for-one, so a polyglot repo declares the same set on all
 * three sides. `{home}` in a default stands for the real home directory and
 * `{gopath}` for the resolved GOPATH.
 */
export const KNOWN_VARS = {
	goPath: { env: "GOPATH", default: "{home}/go" },
	goModCache: { env: "GOMODCACHE", default: "{gopath}/pkg/mod" },
	goCache: { env: "GOCACHE", default: "{home}/.cache/go-build" },
	pythonUserBase: { env: "PYTHONUSERBASE", default: "{home}/.local" },
	cargoHome: { env: "CARGO_HOME", default: "{home}/.cargo" },
	rustupHome: { env: "RUSTUP_HOME", default: "{home}/.rustup" },
	npmCache: { env: "npm_config_cache", default: "{home}/.npm" },
	uvCache: { env: "UV_CACHE_DIR", default: "{home}/.cache/uv" },
	pipCache: { env: "PIP_CACHE_DIR", default: "{home}/.cache/pip" },
	gradleUserHome: { env: "GRADLE_USER_HOME", default: "{home}/.gradle" },
} as const satisfies Record<string, { env: string; default: string }>;

/** Options for {@link isolate}. There is deliberately no option that turns an
 * isolation piece off. */
export interface IsolateOptions {
	/** Toolchain caches that survive the HOME repoint. */
	preserve?: readonly KnownVar[];
}

/**
 * Bind the full environment isolation for the duration of this test: the preserved
 * toolchain caches (if any) are pinned first, then HOME and the four XDG base
 * directories are repointed at a throwaway directory, git's global and system
 * config are emptied, the git identity is replaced, transports are locked down
 * to file:// with git's ssh and proxy helpers pinned to a command that always
 * fails, and every ambient credential variable is removed.
 *
 * ```ts
 * import { test } from "node:test";
 * import { isolate } from "testisolation";
 *
 * test("something", (t) => {
 *   isolate(t);
 *   // HOME is a throwaway dir, git reads an empty global config with a
 *   // throwaway identity, only the file:// transport is allowed, and every
 *   // ambient credential variable is gone.
 * });
 * ```
 *
 * The throwaway home is not returned; call {@link throwawayHome} (which is
 * memoized per test and returns the same directory `isolate` created) when the
 * path is needed.
 */
export function isolate(
	registry: CleanupRegistry,
	options: IsolateOptions = {},
): void {
	// Before HOME moves: the preserved caches all default to a location under
	// the real home, so their values must be pinned while it is still readable.
	preserveVars(registry, options.preserve ?? []);
	throwawayHome(registry);
	isolateGitConfig(registry);
	lockdownTransports(registry);
	stripCredentials(registry);
}

/**
 * Pin the named toolchain caches so they survive the HOME repoint. Each one is
 * pinned to its current value, or to its default location under the real home
 * when it is unset. Call it BEFORE anything moves HOME; {@link isolate} does.
 *
 * Unknown names are rejected at runtime as well as at compile time, so plain
 * JavaScript callers get the same closed enum TypeScript callers do.
 */
export function preserveVars(
	registry: CleanupRegistry,
	vars: readonly KnownVar[],
): void {
	if (vars.length === 0) {
		return;
	}
	const scope = scopeFor(registry);
	const realHome = process.env["HOME"] ?? "";
	if (realHome === "") {
		// Nothing to anchor the defaults to; an already-unset HOME means the
		// caches cannot be derived, and pinning them to a guess would be worse
		// than leaving them alone.
		return;
	}
	let gopath = process.env["GOPATH"] ?? `${realHome}/go`;
	const seen = new Set<KnownVar>();
	for (const name of vars) {
		const known = Object.hasOwn(KNOWN_VARS, name)
			? KNOWN_VARS[name]
			: undefined;
		if (known === undefined) {
			throw new Error(
				`testisolation: preserve got an unknown name (${JSON.stringify(name)}); ` +
					"only the closed enum declared in this package is accepted: " +
					`${Object.keys(KNOWN_VARS).join(", ")}. Arbitrary environment ` +
					"variable names are rejected on purpose -- a credential vector must " +
					"never become preservable by typo.",
			);
		}
		if (seen.has(name)) {
			continue;
		}
		seen.add(name);
		const current = process.env[known.env];
		const value =
			current !== undefined && current !== ""
				? current
				: known.default
						.replaceAll("{home}", realHome)
						.replaceAll("{gopath}", gopath);
		if (value === "") {
			continue;
		}
		setEnv(scope, known.env, value);
		if (known.env === "GOPATH") {
			gopath = value;
		}
	}
}
