"""The BD hit-list scan — a bd_scan modeled directly on gather.py's shape.

Same argument as gather: every scan run asks the same three questions (what's
newly posted in our NAICS codes, what's the live/real-time picture, who's
already winning similar work), and none of those three depend on each other.
So the engine runs them in one wave, exactly like gather's four scans.

    START ─┬─ scan_sam_gov     ─┐
           ├─ scan_tango        ├─► synthesize_hitlist ──router──► draft_hitlist → END
           └─ scan_usaspending ─┘                          └──── quiet ────────► END

TWO RULES, carried over unchanged from gather.py, both load-bearing here too:

1. IT PROPOSES, IT NEVER ACTS. synthesize_hitlist is one bare messages.create
   call with NO tools parameter — it can score and rank opportunities in text,
   it cannot submit a proposal, contact an agency, or write anywhere. The one
   write in the whole graph is a markdown digest in the outbox.

2. EVERY BRANCH CATCHES ITS OWN FAILURE. A dead SAM.gov endpoint or an
   unset Tango key must not take out the synthesize step — see _safe.
"""

from __future__ import annotations

from collections.abc import Callable

from jarvis.graph.engine import END, START, Graph, Node

SCAN_KEYS = {
    "scan_sam_gov": ("sam_text", "sam_new_count"),
    "scan_tango": ("tango_text",),
    "scan_usaspending": ("usa_text",),
}

HITLIST_PROMPT = """You are scoring government contract opportunities for a
business-development hit list. The registered NAICS codes are: {naics}.

NEW/OPEN OPPORTUNITIES (SAM.gov):
{sam_text}

REAL-TIME CROSS-CHECK (Tango):
{tango_text}

WHO IS ALREADY WINNING SIMILAR WORK (USAspending award history):
{usa_text}

For each opportunity, output one row in this exact markdown table format:

| Title | Agency | NAICS | Response Deadline | Link | Rationale |
|---|---|---|---|---|---|

Rank rows with the strongest fit (NAICS match + realistic past-performance
angle) first. The Rationale column is ONE line explaining the ranking — cite
what makes it a fit or a stretch. If USAspending shows an incumbent, name them
in the rationale so the capability statement can address it.

You are DRAFTING A LIST for a human to review. You have not contacted anyone,
submitted anything, or committed to bid — never write as if you have. If a
section gathered nothing, say so briefly and move on."""


def _safe(fn: Callable[[], dict], fallback: dict) -> dict:
    """Same wrapper as gather.py's _safe: a scan that raises must not silently
    drop the whole run — it returns honest text saying why instead."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — the whole point is to not propagate
        return {**fallback, **{k: f"unavailable ({type(exc).__name__}: {exc})"
                               for k in fallback if isinstance(fallback[k], str)}}


def needs_action(state: dict) -> str:
    """CODE routes on the count scan_sam_gov wrote, never on the digest's
    prose — same rule as gather.py's needs_action."""
    return "propose" if state.get("sam_new_count") else "quiet"


def build_bd_scan_graph(*, sam_gov_fn: Callable[[], dict],
                        tango_fn: Callable[[], str],
                        usaspending_fn: Callable[[], str],
                        synth_fn: Callable[[dict], str],
                        draft_fn: Callable[[dict], str]) -> Graph:
    """Callables injected exactly as gather.py does it: evals script them,
    bd_scan_topology() passes stubs to describe the shape without running it,
    jarvis/ops/bd_scan.py binds the real ones."""
    g = Graph("bd_scan")

    g.add_node(Node("scan_sam_gov", lambda s: _safe(
        sam_gov_fn, {"sam_text": "", "sam_new_count": 0}), kind="tool"))
    g.add_node(Node("scan_tango", lambda s: _safe(
        lambda: {"tango_text": tango_fn()}, {"tango_text": ""}), kind="tool"))
    g.add_node(Node("scan_usaspending", lambda s: _safe(
        lambda: {"usa_text": usaspending_fn()}, {"usa_text": ""}), kind="tool"))

    g.add_node(Node("synthesize_hitlist", lambda s: {"digest": synth_fn(s)}, kind="llm"))
    g.add_node(Node("draft_hitlist", lambda s: {"draft_path": draft_fn(s)}, kind="tool"))

    for scan in SCAN_KEYS:
        g.add_edge(START, scan)
        g.add_edge(scan, "synthesize_hitlist")

    g.add_router("synthesize_hitlist", needs_action,
                 {"propose": "draft_hitlist", "quiet": END})
    g.add_edge("draft_hitlist", END)
    return g


def bd_scan_topology() -> dict:
    """The topology as data, for the dashboard — built with stubs, never run."""
    return build_bd_scan_graph(
        sam_gov_fn=lambda: {"sam_text": "", "sam_new_count": 0},
        tango_fn=lambda: "",
        usaspending_fn=lambda: "",
        synth_fn=lambda s: "",
        draft_fn=lambda s: "",
    ).describe()
