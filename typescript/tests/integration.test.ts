/**
 * The package against the real `node:test` runner.
 */

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import { isolate, throwawayHome } from "../src/index.js";

/** HOME as it is outside any isolation, captured before anything runs. */
const REAL_HOME = process.env["HOME"];

test("a node:test TestContext is a cleanup registry with no adapter", (t) => {
	isolate(t);
	const home = throwawayHome(t);
	assert.equal(process.env["HOME"], home);
	assert.notEqual(home, REAL_HOME);
	assert.equal(process.env["GIT_ALLOW_PROTOCOL"], "file");
});

test("the previous test's isolation is gone by the time this one runs", () => {
	// Top-level tests in one file run sequentially, so this is the observation
	// that the TestContext cleanup really fired.
	assert.equal(process.env["HOME"], REAL_HOME);
	assert.equal(Object.hasOwn(process.env, "GIT_ALLOW_PROTOCOL"), false);
});

test("a subtest isolates inside its parent and unwinds first", async (t) => {
	isolate(t);
	const parentHome = process.env["HOME"];
	await t.test("subtest", (st) => {
		isolate(st);
		assert.notEqual(process.env["HOME"], parentHome);
	});
	assert.equal(process.env["HOME"], parentHome, "the parent's home is back");
});

test("--import setup modules load per test FILE, never in the runner parent", () => {
	// This is the reason requireSandbox is a function the consumer calls rather
	// than an automatic hook, and it is the kind of claim that rots silently.
	// The fixture below proves it against the installed node.
	const dir = mkdtempSync(join(tmpdir(), "testisolation-runner-probe-"));
	fixtureDirs.push(dir);
	// The setup module records each load in a file rather than on a stream: the
	// runner rewrites child output into TAP, and this observation must not
	// depend on how it does that.
	writeFileSync(
		join(dir, "setup.mjs"),
		'import {appendFileSync} from "node:fs";\n' +
			'import {join} from "node:path";\n' +
			'appendFileSync(join(import.meta.dirname, "loads.txt"),\n' +
			'  `${process.env.NODE_TEST_CONTEXT ?? "parent"}\\n`);\n',
	);
	writeFileSync(
		join(dir, "a.test.mjs"),
		"import {test} from 'node:test';test('a',()=>{});\n",
	);
	writeFileSync(
		join(dir, "b.test.mjs"),
		"import {test} from 'node:test';test('b',()=>{});\n",
	);

	// This test is itself running inside a node:test child, and NODE_TEST_CONTEXT
	// is inherited. A nested `node --test` that sees it reports into the outer
	// runner's protocol instead of owning its own run, so the probe would be
	// watching the wrong topology. Clear it.
	const env = { ...process.env };
	delete env["NODE_TEST_CONTEXT"];
	execFileSync(process.execPath, ["--import", "./setup.mjs", "--test"], {
		cwd: dir,
		encoding: "utf8",
		stdio: "ignore",
		env,
	});
	const loads = readFileSync(join(dir, "loads.txt"), "utf8")
		.split("\n")
		.filter((line) => line !== "");
	assert.equal(loads.length, 2, "the setup module loaded once per test file");
	for (const line of loads) {
		assert.match(
			line,
			/^child-/,
			"every load was in a per-file child, none in the runner parent",
		);
	}
});

const fixtureDirs: string[] = [];
after(() => {
	for (const dir of fixtureDirs) {
		rmSync(dir, { recursive: true, force: true });
	}
});
