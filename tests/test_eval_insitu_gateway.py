"""Tests for the in-situ model gateway (local MLX / proxy / cloud resolution)."""

import pytest

from tau2.eval_insitu.model_gateway import resolve_model


def _clear(monkeypatch):
    # MAX_TOKENS/EXTRA_BODY too: a developer .env that tunes the local MLX
    # user-sim would otherwise leak into llm_args and fail the exact-dict
    # assertions below.
    for k in ("PROVIDER", "MODEL", "API_BASE", "API_KEY", "MAX_TOKENS", "EXTRA_BODY"):
        monkeypatch.delenv(f"TAU2_USER_SIM_{k}", raising=False)


def test_mlx_local_default(monkeypatch):
    """Default profile targets a local MLX OpenAI-compatible server."""
    _clear(monkeypatch)
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "qwen2.5-32b-instruct-8bit")
    spec = resolve_model("USER_SIM")
    assert spec.model == "openai/qwen2.5-32b-instruct-8bit"
    assert spec.llm_args["api_base"] == "http://localhost:8080/v1"
    assert spec.llm_args["api_key"] == "mlx"


def test_mlx_custom_api_base(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "mlx")
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "qwen3-30b")
    monkeypatch.setenv("TAU2_USER_SIM_API_BASE", "http://mac-studio.local:1234/v1")
    spec = resolve_model("USER_SIM")
    assert spec.model == "openai/qwen3-30b"
    assert spec.llm_args["api_base"] == "http://mac-studio.local:1234/v1"


def test_litellm_proxy(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "litellm")
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "aws/claude-sonnet-4-5")
    monkeypatch.setenv("TAU2_USER_SIM_API_BASE", "https://gw.example/")
    monkeypatch.setenv("TAU2_USER_SIM_API_KEY", "sk-x")
    spec = resolve_model("USER_SIM")
    assert spec.model == "litellm_proxy/aws/claude-sonnet-4-5"
    assert spec.llm_args == {"api_base": "https://gw.example/", "api_key": "sk-x"}


def test_anthropic_cloud_no_explicit_base(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "anthropic")
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "claude-haiku-4-5")
    spec = resolve_model("USER_SIM")
    assert spec.model == "anthropic/claude-haiku-4-5"
    # No api_base/api_key forced -> LiteLLM uses standard ANTHROPIC_API_KEY.
    assert "api_base" not in spec.llm_args


def test_explicit_prefix_preserved(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "mlx")
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "anthropic/claude-opus-4-8")
    spec = resolve_model("USER_SIM")
    # Already-prefixed model is used verbatim (provider profile only adds api_base/key).
    assert spec.model == "anthropic/claude-opus-4-8"


def test_unknown_provider_raises(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TAU2_USER_SIM_PROVIDER", "nope")
    monkeypatch.setenv("TAU2_USER_SIM_MODEL", "x")
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_model("USER_SIM")


def test_missing_model_raises(monkeypatch):
    _clear(monkeypatch)
    with pytest.raises(ValueError, match="No model for role"):
        resolve_model("USER_SIM")
