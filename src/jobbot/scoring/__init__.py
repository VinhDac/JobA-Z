"""M5 — Scoring the CV against a JD.

The requirement: produce a score AND be able to EXPLAIN it.
A score that cannot be explained is not used to decide whether to apply.

The algorithm was deliberately left open (keyword/BM25 | embedding | LLM) —
to be decided once there is real data from M2/M3. Choosing before there is
data is guessing.

A reminder: a high score can still be a false positive. Analysing that is
the most substantial material for the personal project (strategy.md §7-8).
"""
