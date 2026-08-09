"""The wake-word matcher is a pure function — so it gets deterministic evals.
Whisper mangles phrases in predictable ways; these cases pin the fuzziness."""

import pytest

from jarvis.gateway.voice import matches_wake

SHOULD_WAKE = [
    ("jarvis jarvis", "jarvis jarvis"),
    ("Jarvis, jarvis!", "jarvis jarvis"),            # punctuation
    ("jarvisjarvis", "jarvis jarvis"),         # generic: matcher tolerates a dropped space
    ("so anyway jarvis jarvis schedule it", "jarvis jarvis"),  # embedded in speech
    ("jarviz jarvis", "jarvis jarvis"),          # generic: matcher tolerates a one-letter mangle
    ("Hey Jarvis", "hey jarvis"),
    ("hey computer, what's up", "hey computer"),
    # regression from the first live session: whisper wrote the wake word in
    # kana — variants after a comma cover other scripts
    ("わくわく", "jarvis jarvis,わくわく"),
    ("わくわくわく", "jarvis jarvis,わくわく"),
    ("小助手你好", "jarvis jarvis,小助手"),
]

SHOULD_NOT_WAKE = [
    ("what a nice day", "jarvis jarvis"),
    ("wake up call at nine", "jarvis jarvis"),
    ("", "jarvis jarvis"),
    ("jarvis jarvis", ""),                        # no wake word configured
    ("walk to work", "jarvis jarvis"),
]


@pytest.mark.parametrize("heard,wake", SHOULD_WAKE, ids=[h for h, _ in SHOULD_WAKE])
def test_wakes(heard, wake):
    assert matches_wake(heard, wake)


@pytest.mark.parametrize("heard,wake", SHOULD_NOT_WAKE, ids=[h or "empty" for h, _ in SHOULD_NOT_WAKE])
def test_stays_asleep(heard, wake):
    assert not matches_wake(heard, wake)
