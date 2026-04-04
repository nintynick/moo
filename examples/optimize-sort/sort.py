"""
The file to optimize. Implement your sorting algorithm here.
The eval harness calls sort_array() and measures wall-clock time.

Rules:
  - Must sort in ascending order
  - Must handle arrays of 10,000 random integers
  - No external dependencies (stdlib only)
  - Must return a new sorted list (don't modify in place)
"""


def sort_array(arr: list[int]) -> list[int]:
    """Sort an array of integers. This is the baseline — beat it."""
    return sorted(arr)
