/**
 * testisolation -- always-on test isolation for Node suites.
 *
 * The composite entry point is {@link isolate}: one call at the top of a test
 * (or of a helper every test in the file funnels through) binds every
 * isolation piece. Each piece is exported on its own too -- {@link throwawayHome},
 * {@link isolateGitConfig}, {@link lockdownTransports},
 * {@link stripCredentials} -- for suites that need one guarantee without the
 * others. {@link chdir} is separate on purpose: it is a per-test tool, not part
 * of the isolation.
 *
 * ## Contract
 *
 * Every helper takes a per-test cleanup registry -- `node:test`'s `TestContext`
 * satisfies it directly -- and undoes itself when that test finishes. Nothing
 * here is process-wide or permanent: the isolation lives exactly as long as the
 * test (or subtest) whose context was passed in.
 *
 * ## Concurrency
 *
 * HOME, the working directory and the git identity belong to the process, not
 * to a test. Nested tests are fine (a subtest starts and finishes inside its
 * parent), but two tests isolating at the same time is not, and this package
 * detects it rather than letting one test's HOME leak into another's: a test
 * that finishes its isolation while another's is still open fails with an
 * explanatory error. Run the tests in an isolating file sequentially.
 *
 * @packageDocumentation
 */

export {
	chdir,
	CREDENTIAL_VARS,
	IDENTITY_EMAIL,
	IDENTITY_NAME,
	isolateGitConfig,
	lockdownTransports,
	stripCredentials,
	throwawayHome,
} from "./env.js";
export {
	isolate,
	type IsolateOptions,
	KNOWN_VARS,
	type KnownVar,
	preserveVars,
} from "./hygiene.js";
export {
	DEFAULT_RUNNER_COMMAND,
	DEFAULT_SANDBOX_ENV,
	insideSandbox,
	requireSandbox,
	type RequireSandboxOptions,
	SandboxRequiredError,
	type SandboxPolicy,
} from "./sandbox.js";
export type { CleanupRegistry } from "./scope.js";
