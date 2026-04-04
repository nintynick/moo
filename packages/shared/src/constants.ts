/** Default timeout for eval runs (5 minutes, matching Karpathy's autoresearch). */
export const DEFAULT_EVAL_TIMEOUT_SEC = 300;

/** Default Docker image for eval sandboxes. */
export const DEFAULT_EVAL_IMAGE = "gitspoke-eval-sandbox:latest";

/** The filename where repos declare their eval configuration. */
export const EVAL_CONFIG_FILENAME = "gitspoke.eval.yaml";

/**
 * The JSON file that eval scripts write their results to.
 * The eval runner reads this after the command exits.
 *
 * Format: { "metrics": { "<name>": <number>, ... } }
 */
export const EVAL_RESULTS_FILENAME = "gitspoke-results.json";

/** Maximum branches per repo (soft limit, can be raised). */
export const MAX_BRANCHES_PER_REPO = 10_000;

/** Maximum concurrent eval runs per repo. */
export const MAX_CONCURRENT_EVALS = 4;
