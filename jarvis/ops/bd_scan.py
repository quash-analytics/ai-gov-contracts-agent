"""`make bd-scan` — the BD hit-list scan, run as a graph.

This is the one place real callables meet the pure workflow in
jarvis/graph/workflows/bd_scan.py, mirroring jarvis/ops/gather.py exactly:
both the CLI and the dashboard's /api/graph/stream come through
build_bound_graph, so there is one definition of what a bd_scan may touch.

Nothing here can act. The scans are reads, synthesis is one model call with
no tools, and the only write is a markdown digest in the outbox plus a
history row per opportunity (jarvis/db.py's bd_opportunities table — never a
submission, never contact with an agency).

SAM.gov and USAspending are real, documented public federal APIs and are
wired against their actual endpoints below. Tango is NOT wired: its request/
response shape isn't something to guess at, so scan_tango honestly reports
"not yet wired" rather than shipping a fabricated integration against an
unverified URL. Wire it once JARVIS_TANGO_API_KEY holders have Tango's real
API docs in hand.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from rich.console import Console

from jarvis.app import Jarvis
from jarvis.graph import run_graph
from jarvis.graph.workflows.bd_scan import HITLIST_PROMPT, build_bd_scan_graph

SAM_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


def _get_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Jarvis)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _sam_gov(settings, conn: sqlite3.Connection) -> dict:
    """SAM.gov's live Get Opportunities API, filtered to registered NAICS
    codes and the last 24h of postings. Needs JARVIS_SAM_API_KEY (free,
    Account Details > Public API Key) — without one, this reports honestly
    rather than guessing at the bulk CSV's (much larger, harder to verify
    offline) format."""
    if not settings.sam_api_key:
        return {"sam_text": "(SAM.gov unavailable: JARVIS_SAM_API_KEY not set)", "sam_new_count": 0}

    today = date.today()
    params = {
        "api_key": settings.sam_api_key,
        "ncode": ",".join(settings.naics_codes),
        "postedFrom": (today - timedelta(days=1)).strftime("%m/%d/%Y"),
        "postedTo": today.strftime("%m/%d/%Y"),
        "limit": "25",
    }
    data = _get_json(f"{SAM_SEARCH_URL}?{urllib.parse.urlencode(params)}")
    rows = data.get("opportunitiesData") or []

    lines, new_count = [], 0
    for row in rows:
        notice_id = row.get("noticeId", "")
        title = row.get("title", "")
        agency = row.get("fullParentPathName", "")
        naics = row.get("naicsCode", "")
        deadline = row.get("responseDeadLine", "")
        link = row.get("uiLink", "")
        if not notice_id:
            continue
        existing = conn.execute(
            "SELECT 1 FROM bd_opportunities WHERE notice_id = ?", (notice_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO bd_opportunities (notice_id, title, agency, naics, response_deadline, link) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(notice_id) DO UPDATE SET last_seen_at = datetime('now')",
            (notice_id, title, agency, naics, deadline, link),
        )
        if existing is None:
            new_count += 1
        lines.append(f"- {title} ({agency}, NAICS {naics}, due {deadline}) {link}")
    conn.commit()
    return {"sam_text": "\n".join(lines) or "(no new postings)", "sam_new_count": new_count}


def _tango() -> str:
    """Deliberately NOT wired to a real endpoint — see module docstring."""
    return "(Tango cross-check not yet wired — needs Tango's actual API docs before this can call it honestly)"


def _usaspending(settings) -> str:
    """Award history for the registered NAICS codes, from USAspending.gov's
    public API (no key needed) — context for the capability statement, not
    for ranking."""
    body = {
        "filters": {"naics_codes": list(settings.naics_codes),
                    "time_period": [{"start_date": "2025-01-01", "end_date": date.today().isoformat()}]},
        "fields": ["Recipient Name", "Award Amount", "Awarding Agency", "NAICS Code"],
        "sort": "Award Amount", "order": "desc", "limit": 10,
    }
    req = urllib.request.Request(
        USASPENDING_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (compatible; Jarvis)"},
    )
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        data = json.loads(resp.read())
    results = data.get("results") or []
    lines = [f"- {r.get('Recipient Name', '?')} — ${r.get('Award Amount', 0):,.0f} "
             f"({r.get('Awarding Agency', '?')}, NAICS {r.get('NAICS Code', '?')})" for r in results]
    return "\n".join(lines) or "(no recent awards found for these NAICS codes)"


def _synthesize(jarvis, state: dict) -> str:
    """One model call, NO tools parameter — see rule 1 in the workflow docstring."""
    prompt = HITLIST_PROMPT.format(
        naics=", ".join(jarvis.settings.naics_codes),
        sam_text=state.get("sam_text", ""), tango_text=state.get("tango_text", ""),
        usa_text=state.get("usa_text", ""),
    )
    resp = jarvis.client.messages.create(
        model=jarvis.settings.model, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _draft(home: Path, state: dict) -> str:
    """Same outbox-escape guard as gather.py's _draft."""
    outbox = (home / "outbox").resolve()
    outbox.mkdir(parents=True, exist_ok=True)
    dest = (outbox / f"bd-hitlist-{date.today().isoformat()}.md").resolve()
    if outbox not in dest.parents:
        return "refused: draft path escaped the outbox"
    dest.write_text(state.get("digest", "") + "\n", encoding="utf-8")
    return str(dest)


def build_bound_graph(jarvis: Jarvis):
    s = jarvis.settings
    return build_bd_scan_graph(
        sam_gov_fn=lambda: _sam_gov(s, jarvis.conn),
        tango_fn=_tango,
        usaspending_fn=lambda: _usaspending(s),
        synth_fn=lambda state: _synthesize(jarvis, state),
        draft_fn=lambda state: _draft(s.home, state),
    )


def run_bd_scan(jarvis: Jarvis | None = None, observer=None) -> dict:
    """Run one bd_scan to completion. Returns the final state; never raises.
    Mirrors run_gather exactly, including composing the observer with the
    tracer so a run lands in traces/*.jsonl and animates the Graph tab."""
    own = jarvis is None
    jarvis = jarvis or Jarvis()
    try:
        def notify(kind: str, ev: dict) -> None:
            jarvis.tracer.event(kind, ev)
            if observer:
                observer(kind, ev)

        return run_graph(build_bound_graph(jarvis), {}, observer=notify)
    finally:
        if own:
            jarvis.close()


def main() -> None:
    console = Console()
    jarvis = Jarvis()
    try:
        console.print("[dim]scanning — SAM.gov, Tango, and USAspending, together…[/dim]")
        state = run_bd_scan(jarvis)
        console.print(state.get("digest") or "(no digest — every source was empty)")
        if state.get("draft_path"):
            console.print(f"[dim]saved to {state['draft_path']}[/dim]")
        for node, err in (state.get("errors") or {}).items():
            console.print(f"[dim]{node}: {err}[/dim]")
    finally:
        jarvis.close()


if __name__ == "__main__":
    main()
