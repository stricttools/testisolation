/**
 * The per-test isolation scope: what every helper in this package mutates
 * through, and what undoes itself when the test finishes.
 *
 * This is the Node analogue of the Go module's `testing.TB` plumbing. Go gets
 * `TB.Setenv` (record + restore + a panic under `T.Parallel`) and `TB.Cleanup`
 * for free; Node's test runner offers only `t.after`, so the recording, the
 * restoring, and the interleaving detection are implemented here.
 */

import { rmSync } from "node:fs";

/**
 * The minimum a test runner's per-test context must offer for this package to
 * bind to it: a way to register a callback that runs when the test finishes.
 *
 * Node's built-in runner satisfies this directly -- a `node:test` `TestContext`
 * has `after`, so `isolate(t)` works with no adapter. Other runners need a
 * one-line object literal:
 *
 * ```ts
 * import { onTestFinished } from "vitest";
 * isolate({ after: onTestFinished });
 * ```
 */
export interface CleanupRegistry {
	after(fn: () => void | Promise<void>): void;
}

/** One test's recorded mutations, in the order they were made. */
export interface Scope {
	/** Undo callbacks, run in reverse order when the scope is released. */
	readonly restores: Array<() => void>;
	/** Environment variables already recorded, so a second write to the same
	 * variable does not overwrite the ORIGINAL value with an intermediate one. */
	readonly recorded: Set<string>;
	/** The throwaway home allocated for this test, once one has been. */
	home?: string;
	/** Temporary directories to remove on release. */
	readonly tempDirs: string[];
	released: boolean;
}

const scopes = new WeakMap<CleanupRegistry, Scope>();

/**
 * Scopes whose test has begun but not finished, innermost last.
 *
 * Every mutation this package makes is process-wide (HOME, the working
 * directory, the git identity). Nested tests are fine -- a subtest starts and
 * finishes strictly inside its parent, so the stack unwinds last-in-first-out
 * and each level restores exactly what it changed. CONCURRENT tests in the same
 * process are not fine, and the stack is what proves it: when a scope is
 * released and it is not the innermost one, two tests were isolating at the
 * same time and neither one's environment was ever really its own.
 */
const active: Scope[] = [];

/** Return the scope for `registry`, creating and arming it on first use. */
export function scopeFor(registry: CleanupRegistry): Scope {
	const existing = scopes.get(registry);
	if (existing) {
		if (existing.released) {
			throw new Error(
				"testisolation: this test's isolation scope was already released; a " +
					"testisolation helper was called from an `after` callback, or the same " +
					"test context was reused after its test finished.",
			);
		}
		return existing;
	}
	const scope: Scope = {
		restores: [],
		recorded: new Set(),
		tempDirs: [],
		released: false,
	};
	scopes.set(registry, scope);
	active.push(scope);
	registry.after(() => {
		release(scope);
	});
	return scope;
}

/** Undo every mutation recorded on `scope` and drop it from the active stack. */
function release(scope: Scope): void {
	if (scope.released) {
		return;
	}
	scope.released = true;
	const innermost = active[active.length - 1];
	const index = active.indexOf(scope);
	if (index !== -1) {
		active.splice(index, 1);
	}
	// Every undo runs even when one of them throws: a half-restored environment
	// is what the next test in the file would inherit. The first failure is
	// re-thrown once the rest are done.
	let failure: unknown;
	for (let i = scope.restores.length - 1; i >= 0; i--) {
		try {
			scope.restores[i]?.();
		} catch (error) {
			failure ??= error;
		}
	}
	for (const dir of scope.tempDirs) {
		rmSync(dir, { recursive: true, force: true });
	}
	if (failure !== undefined) {
		throw failure;
	}
	if (innermost !== scope) {
		throw new Error(
			"testisolation: a test finished its isolation while another test's " +
				"isolation was still open. HOME, the working directory and the git " +
				"identity are process-wide, so two tests cannot own them at once -- " +
				"neither test's environment was really its own. Run the tests in this " +
				"file sequentially (node:test's default `concurrency: 1`), or isolate " +
				"in only one of them.",
		);
	}
}

/**
 * Set `name` to `value` for the rest of the test, restoring whatever was there
 * (including its absence) when the test finishes.
 */
export function setEnv(scope: Scope, name: string, value: string): void {
	recordEnv(scope, name);
	process.env[name] = value;
}

/**
 * Remove `name` from the environment for the rest of the test, restoring
 * whatever was there when the test finishes.
 */
export function unsetEnv(scope: Scope, name: string): void {
	recordEnv(scope, name);
	delete process.env[name];
}

function recordEnv(scope: Scope, name: string): void {
	if (scope.recorded.has(name)) {
		return;
	}
	scope.recorded.add(name);
	const previous = Object.hasOwn(process.env, name)
		? process.env[name]
		: undefined;
	scope.restores.push(() => {
		if (previous === undefined) {
			delete process.env[name];
		} else {
			process.env[name] = previous;
		}
	});
}

/** Register an arbitrary undo callback on `scope`. */
export function onRelease(scope: Scope, undo: () => void): void {
	scope.restores.push(undo);
}
