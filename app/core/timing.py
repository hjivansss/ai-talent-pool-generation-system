# Lightweight stage-timing helper.

import time
from contextlib import contextmanager


@contextmanager
def timed(label: str):
    """
    Usage:
        with timed("Step 4 — GitHub fetch"):
            ... do work ...
    Prints elapsed wall-clock time for the block, even if it raises.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"[TIMING] {label}: {elapsed:.2f}s")


class Timer:
    """
    Usage for cases where you can't use a `with` block cleanly (e.g. timing
    something inside a loop and wanting a running total):
        t = Timer("Stage 2 — Ollama evaluation (total)")
        ... work ...
        t.stop()
    """
    def __init__(self, label: str):
        self.label = label
        self.start = time.perf_counter()

    def stop(self):
        elapsed = time.perf_counter() - self.start
        print(f"[TIMING] {self.label}: {elapsed:.2f}s")
        return elapsed
