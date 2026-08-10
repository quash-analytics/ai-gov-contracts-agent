"""send_message / compose_email — draft messages into a local outbox.

Local-first: nothing is actually sent. Each message becomes a file in
.jarvis/outbox/ that you can read, edit, and send yourself. Wiring a real
channel (email, Telegram, Slack) is a great community contribution — a real
send would still have to be a DRAFT-creation call (e.g. Gmail's drafts.create),
never a send call, to keep this file's one guarantee intact.

compose_email deliberately does NOT let the orchestrating loop model write the
final prose. It hands the recipient/subject/key points to a bare small_model
call — no tools parameter, so that call cannot act either — which drafts the
actual email text. Two reasons: (1) it's the cheap model, so drafting cost
stays a rounding error next to the loop's own tokens, matching the "run email
on the small agent" choice; (2) it's the one call that reads the
email-writing skill directly by path, not by keyword match, so style rules
apply on every draft regardless of how the loop's own prompt was phrased.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jarvis.tools.registry import Tool

# Used only as a fallback if skills/email-writing/SKILL.md hasn't been
# installed yet (see memory/procedural for the real thing) — so compose_email
# works standalone rather than depending on load order between the two.
_FALLBACK_STYLE = """\
Write direct, casual-professional emails: one to two sentences per point, no
em dashes, no hedging ("just", "perhaps", "we feel that"), lead with the
point, end with a real question only if one is needed. Friendly opener,
simple sign-off."""


def _email_writing_skill() -> str:
    """The email-writing skill's instructions, loaded by PATH — this tool
    needs the style rules on every draft, not only when a user's own words
    happen to overlap with the skill's keywords (SkillLoader.match's normal
    trigger). Falls back to a short inline version if the skill file is
    missing so compose_email still behaves reasonably before it's installed."""
    from jarvis.memory import bundled_skill_dirs
    from jarvis.memory.procedural.loader import _parse

    for d in bundled_skill_dirs():
        skill_path = d / "email-writing" / "SKILL.md"
        if skill_path.is_file():
            skill = _parse(skill_path)
            if skill:
                return skill.body
    return _FALLBACK_STYLE


def make_tool(home: Path) -> Tool:
    def send_message(to: str, body: str) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        safe_to = "".join(c if c.isalnum() else "-" for c in to)[:40]
        path = home / "outbox" / f"{stamp}-{safe_to}.txt"
        path.write_text(f"To: {to}\n\n{body}\n", encoding="utf-8")
        return f"Message to {to} placed in outbox ({path.name}). Nothing was sent — review it there."

    return Tool(
        name="send_message",
        description=(
            "Draft a message to someone and place it in the local outbox for the user to "
            "review and send. Use when the user asks you to message, tell, or remind someone."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient name or address"},
                "body": {"type": "string", "description": "The message text"},
            },
            "required": ["to", "body"],
        },
        fn=send_message,
    )


def make_compose_email_tool(home: Path, client, small_model: str) -> Tool:
    """compose_email: to / subject / key_points in, a styled draft in the
    outbox out. `client` and `small_model` are the same client the loop
    already built (client objects are provider-bound, not model-bound — this
    just names a cheaper model in the `model=` argument of its own call)."""

    def compose_email(to: str, subject: str, key_points: str) -> str:
        prompt = (
            f"{_email_writing_skill()}\n\n"
            "Draft an email using the style rules above. Output ONLY the email "
            "body text (no subject line, no \"Subject:\" prefix, no markdown).\n\n"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"Key points to cover: {key_points}"
        )
        # Bare call, no tools parameter — the drafting model cannot act, only
        # produce text. Same discipline as gather.py's synthesize node.
        response = client.messages.create(
            model=small_model, max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        body = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        safe_to = "".join(c if c.isalnum() else "-" for c in to)[:40]
        path = home / "outbox" / f"{stamp}-email-{safe_to}.txt"
        path.write_text(f"To: {to}\nSubject: {subject}\n\n{body}\n", encoding="utf-8")
        return f"Email draft to {to} placed in outbox ({path.name}). Nothing was sent — review it there."

    return Tool(
        name="compose_email",
        description=(
            "Draft an email to someone and place it in the local outbox for the user to review "
            "and send. Use when the user asks you to write, draft, or reply to an email. "
            "Give the recipient, a subject line, and the key points the email needs to make — "
            "the actual prose is drafted for you in the right style."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient name or email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "key_points": {"type": "string",
                              "description": "What the email needs to say — bullet points or a "
                                             "short summary, not final prose"},
            },
            "required": ["to", "subject", "key_points"],
        },
        fn=compose_email,
    )

