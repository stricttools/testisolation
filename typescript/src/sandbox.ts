/**
 * Bare-run refusal: a suite that is supposed to run inside the sandbox refuses
 * to run outside it.
 *
 * ## Why this is a helper the consumer calls, and not a hook
 *
 * The Python plugin refuses at `pytest_collection_modifyitems`: pytest hands it
 * the whole selected test list before a single test body runs, so the plugin
 * can count the run and abort it before anything happens.
 *
 * Node's built-in runner offers no equivalent, and the gap is structural rather
 * than a missing API. `node --test` runs each test FILE in its own child
 * process; a module loaded with `--import` is loaded in those children, never
 * in the parent that owns the run (`NODE_TEST_CONTEXT=child-v8` is set in every
 * one of them). A setup module therefore sees exactly one file and can never
 * learn how many tests the whole run selected. Custom reporters do run in the
 * parent, but they are fed events as tests complete -- far too late to refuse a
 * run, and with no way to abort one.
 *
 * So the count has to come from wherever the consumer genuinely knows it, and
 * this module is a plain function the consumer calls there. The two honest call
 * sites:
 *
 * - **A programmatic runner entry.** `node:test`'s `run({ files })` is called
 *   with the file list, so the entry point knows the size of the run before it
 *   starts. Use `policy: "threshold"` there:
 *
 *   ```ts
 *   import { run } from "node:test";
 *   import { glob } from "node:fs/promises";
 *   import { requireSandbox } from "testisolation";
 *
 *   const files = await Array.fromAsync(glob("dist-test/tests/ **\/*.test.js"));
 *   requireSandbox({ policy: "threshold", threshold: 10, count: files.length });
 *   run({ files }).pipe(process.stdout);
 *   ```
 *
 * - **A `--import`ed setup module**, for suites that run through plain
 *   `node --test`. A child cannot count the run, so the only honest stance
 *   there is `policy: "always"` -- every bare run is refused, including the
 *   small targeted one. That is strictly stronger than the threshold and costs
 *   the fast bare inner loop; a suite that wants that loop back needs the
 *   runner entry above.
 *
 * There is deliberately no third shape that guesses. A cross-process counter
 * that refused halfway through a run would have already executed tests bare,
 * which is the thing being prevented.
 */

/** The environment variable the sandbox runner sets to `"1"`. */
export const DEFAULT_SANDBOX_ENV = "TESTISOLATION_SANDBOX";

/** The command shown in the refusal message. */
export const DEFAULT_RUNNER_COMMAND = "scripts/test.sh";

/** Thrown by {@link requireSandbox} when a run is refused. */
export class SandboxRequiredError extends Error {
	override name = "SandboxRequiredError";
}

/**
 * How much of a bare run to refuse. The choice is required: a suite declares
 * where it stands rather than inheriting a default.
 *
 * - `"always"`: refuse every run outside the sandbox.
 * - `"threshold"`: refuse a run of more than `threshold` items outside the
 *   sandbox, where `count` is how many this run has. Smaller runs stay bare for
 *   iteration speed.
 */
export type SandboxPolicy =
	| { policy: "always" }
	| { policy: "threshold"; threshold: number; count: number };

export type RequireSandboxOptions = SandboxPolicy & {
	/** Defaults to {@link DEFAULT_SANDBOX_ENV}. */
	sandboxEnv?: string;
	/** Defaults to {@link DEFAULT_RUNNER_COMMAND}. */
	runnerCommand?: string;
};

/** Whether this process is running inside the sandbox runner. */
export function insideSandbox(sandboxEnv = DEFAULT_SANDBOX_ENV): boolean {
	return process.env[sandboxEnv] === "1";
}

const WHY_THE_SANDBOX =
	"The sandbox binds the real repo read-only, runs in a writable throwaway " +
	"copy on a private tmpfs, and has no network -- so a stray real git push, " +
	"an unanchored commit into the dev repo, or a live API call is physically " +
	"impossible.";

/**
 * Refuse this run if it is happening outside the sandbox, per the declared
 * policy. Throws {@link SandboxRequiredError}; returns silently otherwise.
 */
export function requireSandbox(options: RequireSandboxOptions): void {
	const sandboxEnv = options.sandboxEnv ?? DEFAULT_SANDBOX_ENV;
	const runnerCommand = options.runnerCommand ?? DEFAULT_RUNNER_COMMAND;

	if (options.policy === "threshold") {
		if (!Number.isInteger(options.threshold) || options.threshold < 1) {
			throw new TypeError(
				"testisolation: requireSandbox threshold must be an integer >= 1, got " +
					`${options.threshold}. Use { policy: "always" } to refuse every ` +
					"bare run, not a zero threshold.",
			);
		}
		if (!Number.isInteger(options.count) || options.count < 0) {
			throw new TypeError(
				"testisolation: requireSandbox count must be a non-negative integer, " +
					`got ${options.count}.`,
			);
		}
	} else if (options.policy !== "always") {
		throw new TypeError(
			"testisolation: requireSandbox needs an explicit policy, either " +
				`{ policy: "always" } or { policy: "threshold", threshold, count }; ` +
				`got ${JSON.stringify((options as { policy: unknown }).policy)}.`,
		);
	}

	if (insideSandbox(sandboxEnv)) {
		return;
	}

	if (options.policy === "always") {
		throw new SandboxRequiredError(
			"Refusing to run this suite outside the sandbox. Every run must go " +
				`through the sandbox runner:\n\n    ${runnerCommand}\n\n` +
				`${WHY_THE_SANDBOX} This suite declared policy "always", so no run ` +
				`is exempt. ${runnerCommand} must export ${sandboxEnv}=1.`,
		);
	}

	if (options.count <= options.threshold) {
		return;
	}
	throw new SandboxRequiredError(
		`Refusing to run ${options.count} tests bare (> ${options.threshold}). ` +
			"A full-ish suite run must go through the sandbox runner:\n\n" +
			`    ${runnerCommand}\n\n` +
			`${WHY_THE_SANDBOX} Small targeted runs stay allowed bare for ` +
			`iteration speed (<= ${options.threshold} tests). To run the full ` +
			`suite, use ${runnerCommand} (which must export ${sandboxEnv}=1).`,
	);
}
