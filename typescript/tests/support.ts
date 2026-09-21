/**
 * A synthetic cleanup registry.
 *
 * The isolation helpers are tested by binding them and then asserting on
 * `process.env` both while they are bound and after they are released. A real
 * `node:test` `TestContext` releases when the test itself finishes, which is
 * after the assertions -- so these tests drive a registry whose release they
 * call explicitly.
 */

import type { CleanupRegistry } from "../src/index.js";

export interface Fake {
	registry: CleanupRegistry;
	/** Run every registered cleanup, innermost first. */
	release(): void;
}

export function fakeRegistry(): Fake {
	const callbacks: Array<() => void | Promise<void>> = [];
	let released = false;
	return {
		registry: {
			after(fn) {
				callbacks.push(fn);
			},
		},
		release() {
			if (released) {
				return;
			}
			released = true;
			for (let i = callbacks.length - 1; i >= 0; i--) {
				const result = callbacks[i]?.();
				if (result instanceof Promise) {
					throw new Error("the isolation's cleanups are synchronous by design");
				}
			}
		},
	};
}
