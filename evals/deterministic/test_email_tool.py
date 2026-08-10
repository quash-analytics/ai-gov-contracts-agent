"""compose_email — offline coverage for the outbox-only email drafting tool.

Two things to pin: (1) it drafts through the SCRIPTED small_model client
directly, not through a real network call, so this is deterministic; (2) the
call it makes carries no `tools` parameter — the drafting model can act on
nothing, same discipline as gather.py's synthesize node.
"""

from __future__ import annotations

from evals.helpers import ScriptedClient, response, text_block
from jarvis.tools.email import make_compose_email_tool, make_tool


def test_compose_email_drafts_into_outbox_and_never_sends(tmp_path):
    (tmp_path / "outbox").mkdir()
    client = ScriptedClient([response([text_block("Hey Alex,\n\nFollowing up on the proposal.\n\nBest,\nSean")])])

    tool = make_compose_email_tool(tmp_path, client, "small-model")
    result = tool.fn(to="alex@example.com", subject="Follow-up", key_points="check in on the proposal")

    assert "Nothing was sent" in result
    drafts = list((tmp_path / "outbox").glob("*-email-*.txt"))
    assert len(drafts) == 1
    text = drafts[0].read_text(encoding="utf-8")
    assert "To: alex@example.com" in text
    assert "Subject: Follow-up" in text
    assert "Following up on the proposal" in text


def test_compose_email_calls_the_small_model_with_no_tools(tmp_path):
    """The whole point of routing through small_model is that it's a bare,
    tool-less call — pin both: the model id passed, and the absence of a
    `tools` kwarg."""
    (tmp_path / "outbox").mkdir()
    captured = {}

    class CapturingClient:
        def __init__(self):
            from types import SimpleNamespace
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            captured.update(kwargs)
            return response([text_block("draft body")])

    tool = make_compose_email_tool(tmp_path, CapturingClient(), "small-model")
    tool.fn(to="a@b.com", subject="Hi", key_points="say hi")

    assert captured["model"] == "small-model"
    assert "tools" not in captured


def test_send_message_still_works_after_the_rename(tmp_path):
    """messages.py -> email.py kept send_message's contract identical."""
    (tmp_path / "outbox").mkdir()
    tool = make_tool(tmp_path)
    result = tool.fn(to="Alex", body="running late")
    assert "Nothing was sent" in result
    assert list((tmp_path / "outbox").glob("*-Alex.txt"))
