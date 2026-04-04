"""
GitSpoke eval harness for the optimize-sort challenge.
Measures sorting performance and correctness.

Writes results to the file specified by GITSPOKE_RESULTS_FILE env var,
or falls back to printing JSON to stdout.
"""

import json
import os
import random
import statistics
import time

from sort import sort_array

SEED = 42
ARRAY_SIZE = 10_000
NUM_ITERATIONS = 100


def generate_test_array(seed: int, size: int) -> list[int]:
    rng = random.Random(seed)
    return [rng.randint(-(10**9), 10**9) for _ in range(size)]


def verify_correctness(arr: list[int], result: list[int]) -> bool:
    expected = sorted(arr)
    return result == expected


def main():
    arr = generate_test_array(SEED, ARRAY_SIZE)

    # Verify correctness first
    result = sort_array(arr[:])
    if not verify_correctness(arr, result):
        results = {
            "metrics": {
                "median_ms": 999999,
                "correct": 0,
            }
        }
        output_results(results)
        return

    # Benchmark
    times = []
    for _ in range(NUM_ITERATIONS):
        test_arr = arr[:]
        start = time.perf_counter()
        sort_array(test_arr)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)

    results = {
        "metrics": {
            "median_ms": round(statistics.median(times), 4),
            "p95_ms": round(sorted(times)[int(NUM_ITERATIONS * 0.95)], 4),
            "correct": 1,
        }
    }
    output_results(results)


def output_results(results: dict):
    results_file = os.environ.get("GITSPOKE_RESULTS_FILE")
    json_str = json.dumps(results)

    if results_file:
        os.makedirs(os.path.dirname(results_file), exist_ok=True)
        with open(results_file, "w") as f:
            f.write(json_str)

    # Always print to stdout as fallback
    print(json_str)


if __name__ == "__main__":
    main()
