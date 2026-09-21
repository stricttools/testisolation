/**
 * The environment isolation: what it repoints, what it strips, and that every one of those
 * mutations is undone when the test that made it finishes.
 *
 * These tests deliberately do NOT call `isolate` on themselves at the top --
 * they are testing the thing, so they invoke it on a synthetic registry whose
 * release they control, and assert on `process.env` around it.
 */

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
	existsSync,
	readdirSync,
	readFileSync,
	realpathSync,
	statSync,
} from "node:fs";
import { test } from "node:test";
import {
	chdir,
	CREDENTIAL_VARS,
	IDENTITY_EMAIL,
	IDENTITY_NAME,
	isolate,
	isolateGitConfig,
	lockdownTransports,
	stripCredentials,
	throwawayHome,
} from "../src/index.js";
import { type Fake, fakeRegistry } from "./support.js";

test("throwawayHome repoints HOME, USERPROFILE and the four XDG dirs", (t) => {
	const before = snapshot();
	let home: string;
	let fake: Fake;
	try {
		fake = fakeRegistry();
		home = throwawayHome(fake.registry);

		assert.equal(process.env["HOME"], home);
		assert.equal(process.env["USERPROFILE"], home);
		for (const [env, rel] of [
			["XDG_CONFIG_HOME", ".config"],
			["XDG_DATA_HOME", ".local/share"],
			["XDG_CACHE_HOME", ".cache"],
			["XDG_STATE_HOME", ".local/state"],
		] as const) {
			const value = process.env[env];
			assert.ok(value, `${env} is set`);
			assert.ok(value.startsWith(home), `${env} lives under the throwaway home`);
			assert.ok(value.endsWith(rel.split("/").join(pathSep())), `${env} = ${rel}`);
			assert.ok(statSync(value).isDirectory(), `${env} exists on disk`);
		}
	} finally {
		fake!.release();
	}
	t.diagnostic(`throwaway home was ${home!}`);
	assert.deepEqual(snapshot(), before, "every variable is restored");
	assert.equal(existsSync(home!), false, "the throwaway directory is removed");
});

test("throwawayHome is memoized within one test", () => {
	const fake = fakeRegistry();
	try {
		assert.equal(throwawayHome(fake.registry), throwawayHome(fake.registry));
	} finally {
		fake.release();
	}
});

test("separate registries get separate homes", () => {
	const outer = fakeRegistry();
	const inner = fakeRegistry();
	try {
		const outerHome = throwawayHome(outer.registry);
		const innerHome = throwawayHome(inner.registry);
		assert.notEqual(outerHome, innerHome);
	} finally {
		// LIFO: the inner one must go first.
		inner.release();
		outer.release();
	}
});

test("isolateGitConfig empties git's config and replaces the identity", () => {
	const before = snapshot();
	const fake = fakeRegistry();
	try {
		isolateGitConfig(fake.registry);
		const home = throwawayHome(fake.registry);

		for (const env of ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"]) {
			const path = process.env[env];
			assert.ok(path, `${env} is set`);
			assert.ok(path.startsWith(home), `${env} lives under the throwaway home`);
			assert.equal(readFileSync(path, "utf8"), "", `${env} is empty`);
		}
		assert.equal(process.env["GIT_AUTHOR_NAME"], IDENTITY_NAME);
		assert.equal(process.env["GIT_AUTHOR_EMAIL"], IDENTITY_EMAIL);
		assert.equal(process.env["GIT_COMMITTER_NAME"], IDENTITY_NAME);
		assert.equal(process.env["GIT_COMMITTER_EMAIL"], IDENTITY_EMAIL);
		assert.equal(process.env["GIT_TERMINAL_PROMPT"], "0");
	} finally {
		fake.release();
	}
	assert.deepEqual(snapshot(), before);
});

test("isolateGitConfig does not set core.hooksPath", () => {
	// core.hooksPath would override REPO-LOCAL hooks too, silently disabling a
	// consumer's own pre-push-hook tests. The empty global config is what keeps
	// the developer's hooks from firing.
	const fake = fakeRegistry();
	try {
		isolateGitConfig(fake.registry);
		const home = throwawayHome(fake.registry);
		for (const env of ["GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"]) {
			const path = process.env[env];
			assert.ok(path);
			assert.ok(path.startsWith(home));
			assert.doesNotMatch(readFileSync(path, "utf8"), /hooksPath/);
		}
	} finally {
		fake.release();
	}
});

test("the isolated git config really is what git reads", () => {
	const fake = fakeRegistry();
	try {
		isolateGitConfig(fake.registry);
		const name = execFileSync("git", ["config", "--global", "--get", "user.name"], {
			encoding: "utf8",
			// A missing key exits 1; the empty config is the point, so tolerate it.
			stdio: ["ignore", "pipe", "ignore"],
		}).trim();
		assert.equal(name, "", "the throwaway global config carries no user.name");
	} catch (error) {
		// git exits 1 when the key is absent, which is the assertion above.
		assert.equal((error as { status?: number }).status, 1);
	} finally {
		fake.release();
	}
});

test("lockdownTransports pins the protocol list and both helpers", () => {
	const before = snapshot();
	const fake = fakeRegistry();
	try {
		lockdownTransports(fake.registry);
		assert.equal(process.env["GIT_ALLOW_PROTOCOL"], "file");
		assert.equal(process.env["GIT_SSH_COMMAND"], "/bin/false");
		assert.equal(process.env["GIT_PROXY_COMMAND"], "/bin/false");
	} finally {
		fake.release();
	}
	assert.deepEqual(snapshot(), before);
});

test("stripCredentials removes every listed variable and restores them", () => {
	const sentinel = "REAL-SECRET-DO-NOT-LEAK";
	const originals = new Map<string, string | undefined>();
	for (const name of CREDENTIAL_VARS) {
		originals.set(
			name,
			Object.hasOwn(process.env, name) ? process.env[name] : undefined,
		);
		process.env[name] = sentinel;
	}
	try {
		const fake = fakeRegistry();
		try {
			stripCredentials(fake.registry);
			for (const name of CREDENTIAL_VARS) {
				assert.equal(
					Object.hasOwn(process.env, name),
					false,
					`${name} is gone from the environment`,
				);
			}
		} finally {
			fake.release();
		}
		for (const name of CREDENTIAL_VARS) {
			assert.equal(process.env[name], sentinel, `${name} is restored`);
		}
	} finally {
		for (const [name, value] of originals) {
			if (value === undefined) {
				delete process.env[name];
			} else {
				process.env[name] = value;
			}
		}
	}
});

test("the credential list is a closed, deduplicated set of plain names", () => {
	assert.equal(
		new Set(CREDENTIAL_VARS).size,
		CREDENTIAL_VARS.length,
		"no duplicates",
	);
	for (const name of CREDENTIAL_VARS) {
		assert.match(name, /^[A-Z][A-Z0-9_]*$/, `${name} is a plain env var name`);
	}
});

test("isolate binds every isolation piece at once", () => {
	const originalToken = Object.hasOwn(process.env, "GH_TOKEN")
		? process.env["GH_TOKEN"]
		: undefined;
	process.env["GH_TOKEN"] = "a-fake-token-that-must-not-survive-isolate";
	const before = snapshot();
	const fake = fakeRegistry();
	try {
		isolate(fake.registry);
		const home = process.env["HOME"];
		assert.ok(home && home !== before["HOME"], "HOME moved");
		assert.ok(process.env["GIT_CONFIG_GLOBAL"]?.startsWith(home));
		assert.equal(process.env["GIT_ALLOW_PROTOCOL"], "file");
		assert.equal(Object.hasOwn(process.env, "GH_TOKEN"), false);
	} finally {
		fake.release();
	}
	assert.deepEqual(snapshot(), before);
	if (originalToken === undefined) {
		delete process.env["GH_TOKEN"];
	} else {
		process.env["GH_TOKEN"] = originalToken;
	}
});

test("a poisoned home hides the developer's real dotfiles", () => {
	// The meta-test: with the isolation bound, a path built from HOME cannot reach
	// anything the developer actually owns.
	const realHome = process.env["HOME"];
	assert.ok(realHome);
	const fake = fakeRegistry();
	try {
		isolate(fake.registry);
		const home = process.env["HOME"];
		assert.ok(home);
		assert.notEqual(home, realHome);
		const planted = new Set([
			".config",
			".local",
			".cache",
			"gitconfig-global",
			"gitconfig-system",
		]);
		assert.deepEqual(
			readdirSync(home).filter((entry) => !planted.has(entry)),
			[],
			"the throwaway home holds nothing but what stricttest put there",
		);
	} finally {
		fake.release();
	}
});

test("chdir moves and restores the working directory and PWD", () => {
	const beforeCwd = process.cwd();
	const beforePwd = process.env["PWD"];
	const fake = fakeRegistry();
	try {
		const home = throwawayHome(fake.registry);
		chdir(fake.registry, home);
		assert.equal(realpath(process.cwd()), realpath(home));
		assert.equal(process.env["PWD"], process.cwd());
	} finally {
		fake.release();
	}
	assert.equal(process.cwd(), beforeCwd);
	assert.equal(process.env["PWD"], beforePwd);
});

const TRACKED = [
	"HOME",
	"USERPROFILE",
	"XDG_CONFIG_HOME",
	"XDG_DATA_HOME",
	"XDG_CACHE_HOME",
	"XDG_STATE_HOME",
	"GIT_CONFIG_GLOBAL",
	"GIT_CONFIG_SYSTEM",
	"GIT_AUTHOR_NAME",
	"GIT_AUTHOR_EMAIL",
	"GIT_COMMITTER_NAME",
	"GIT_COMMITTER_EMAIL",
	"GIT_TERMINAL_PROMPT",
	"GIT_ALLOW_PROTOCOL",
	"GIT_SSH_COMMAND",
	"GIT_PROXY_COMMAND",
	"PWD",
	...CREDENTIAL_VARS,
];

function snapshot(): Record<string, string | undefined> {
	const out: Record<string, string | undefined> = {};
	for (const name of TRACKED) {
		out[name] = Object.hasOwn(process.env, name) ? process.env[name] : undefined;
	}
	return out;
}

function pathSep(): string {
	return process.platform === "win32" ? "\\" : "/";
}

function realpath(p: string): string {
	return realpathSync(p);
}
