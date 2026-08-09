"""jarvis-agent — a minimal, transparent, local-first Jarvis.

Four pillars, one module each:
  harness  → jarvis/runtime + jarvis/gateway  (scaffolding around the raw LLM)
  loop     → jarvis/loop                      (observe → reason → act → repeat)
             jarvis/graph                     (opt-in structure around the loop — extends this pillar)
  memory   → jarvis/memory                    (procedural / semantic / episodic)
  ops      → jarvis/ops + evals/              (trace → eval → gate → release)
"""

__version__ = "0.1.0"
