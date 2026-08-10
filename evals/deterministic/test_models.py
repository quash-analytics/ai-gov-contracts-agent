from types import SimpleNamespace

from jarvis.config import Settings
from jarvis.loop import models


def test_xai_grok_provider_uses_expected_key_endpoint_and_models(monkeypatch, tmp_path):
    captured = {}

    class StubOpenAICompatClient:
        def __init__(self, *, api_key, base_url, timeout):
            captured.update(api_key=api_key, base_url=base_url, timeout=timeout)

    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setattr(models, "OpenAICompatClient", StubOpenAICompatClient)
    settings = Settings(provider="xai", api_key="", base_url=None, model="",
                        small_model="", home=tmp_path)

    client = models.get_client(settings)

    assert isinstance(client, StubOpenAICompatClient)
    assert captured["api_key"] == "test-xai-key"
    assert captured["base_url"] == "https://api.x.ai/v1"
    assert settings.model == "grok-4"


def test_openai_default_is_tool_capable(tmp_path):
    """Regression: bare 'gpt-5.6' isn't callable, and the gpt-5.6 REASONING
    variants (luna/sol/terra) can't use function tools on /v1/chat/completions
    (they 400). The default must be a NON-reasoning, tool-capable chat model."""
    from jarvis.loop.models import PROVIDERS
    assert PROVIDERS["openai"].model == "gpt-5.3-chat-latest"
    assert PROVIDERS["openai"].default_pair() == ["gpt-5.3-chat-latest", "gpt-4.1-mini"]


def test_large_model_falls_back_to_model_when_unset(monkeypatch, tmp_path):
    """large_model is an upgrade slot for background agents (email, BD scan),
    not a provider concept — unset, it must silently mirror the main model
    rather than leave the two callers of settings.large_model with an empty
    string (which would send model="" straight to the client)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    settings = Settings(provider="anthropic", api_key="", base_url=None, model="",
                        small_model="", home=tmp_path)
    assert settings.large_model == ""
    models.get_client(settings)
    assert settings.large_model == settings.model == "claude-sonnet-5"


def test_large_model_explicit_value_is_kept(monkeypatch, tmp_path):
    """An explicit JARVIS_LARGE_MODEL is a deliberate choice and must survive
    get_client — mirrors the model/small_model contract right above it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    settings = Settings(provider="anthropic", api_key="", base_url=None, model="",
                        small_model="", large_model="claude-opus-4-8", home=tmp_path)
    models.get_client(settings)
    assert settings.large_model == "claude-opus-4-8"
    assert settings.model == "claude-sonnet-5"


def test_ollama_provider_uses_local_endpoint_and_placeholder_key(monkeypatch, tmp_path):
    """Ollama runs locally with no real credential; the openai-compatible
    client still requires a non-empty key string, so JARVIS_HOME users are
    told to set any placeholder (see .env.example's default="ollama")."""
    from jarvis.loop.models import PROVIDERS

    captured = {}

    class StubOpenAICompatClient:
        def __init__(self, *, api_key, base_url, timeout):
            captured.update(api_key=api_key, base_url=base_url, timeout=timeout)

    monkeypatch.setenv("OLLAMA_API_KEY", "ollama")
    monkeypatch.setattr(models, "OpenAICompatClient", StubOpenAICompatClient)
    settings = Settings(provider="ollama", api_key="", base_url=None, model="",
                        small_model="", home=tmp_path)

    client = models.get_client(settings)

    assert isinstance(client, StubOpenAICompatClient)
    assert captured["base_url"] == "http://localhost:11434/v1"
    assert settings.model == PROVIDERS["ollama"].model == "gemma4:e4b"
    assert settings.small_model == PROVIDERS["ollama"].small_model == "gemma4:e2b"


def test_gemini_thought_signature_round_trips():
    """Gemini thinking models attach a thought_signature to each tool call and
    REQUIRE it echoed back next turn, or the follow-up 400s. The OpenAI-compat
    adapter must capture it on parse (_create) and put it back on serialize
    (_to_openai). Verified end-to-end without a network call."""
    from jarvis.loop.models import OpenAICompatClient

    client = OpenAICompatClient.__new__(OpenAICompatClient)   # skip __init__ (no network)
    sig = {"google": {"thought_signature": "ABC123"}}
    toolcall = SimpleNamespace(id="t1", extra_content=sig,
                               function=SimpleNamespace(name="create_event", arguments='{"title":"x"}'))
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[toolcall]))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    client._call = lambda kwargs, **extra: resp

    parsed = client._create(model="gemini-3.5-flash", messages=[{"role": "user", "content": "hi"}], max_tokens=10)
    block = next(b for b in parsed.content if b.type == "tool_use")
    assert block.extra == sig                                  # captured on parse

    kwargs = client._to_openai(model="gemini-3.5-flash", max_tokens=10,
                               messages=[{"role": "assistant", "content": parsed.content}])
    assert kwargs["messages"][0]["tool_calls"][0]["extra_content"] == sig   # echoed back


def test_deepseek_provider_uses_expected_key_endpoint_and_models(monkeypatch, tmp_path):
    captured = {}

    class StubOpenAICompatClient:
        def __init__(self, *, api_key, base_url, timeout):
            captured.update(api_key=api_key, base_url=base_url, timeout=timeout)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setattr(models, "OpenAICompatClient", StubOpenAICompatClient)
    settings = Settings(
        provider="deepseek",
        api_key="",
        base_url=None,
        model="",
        small_model="",
        home=tmp_path,
    )

    client = models.get_client(settings)

    assert isinstance(client, StubOpenAICompatClient)
    assert captured["api_key"] == "test-deepseek-key"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert settings.model == "deepseek-v4-pro"
    assert settings.small_model == "deepseek-v4-pro"


def test_minimax_provider_uses_expected_key_endpoint_and_models(monkeypatch, tmp_path):
    captured = {}

    class StubAnthropicClient:
        def __init__(self, *, api_key, base_url, timeout):
            captured.update(api_key=api_key, base_url=base_url, timeout=timeout)
            self.messages = None

    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    monkeypatch.delenv("JARVIS_BASE_URL", raising=False)
    monkeypatch.setitem(
        __import__("sys").modules,
        "anthropic",
        SimpleNamespace(Anthropic=StubAnthropicClient),
    )
    settings = Settings(
        provider="minimax",
        api_key="",
        base_url=None,
        model="",
        small_model="",
        home=tmp_path,
    )

    client = models.get_client(settings)

    assert isinstance(client, StubAnthropicClient)
    assert captured["api_key"] == "test-minimax-key"
    assert captured["base_url"] == "https://api.minimaxi.com/anthropic"
    assert captured["timeout"] == 120.0
    assert settings.model == "MiniMax-M3"
    assert settings.small_model == "MiniMax-M2"
