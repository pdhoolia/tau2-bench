"""Common model gateway for in-situ roles (agent / user-sim / judge).

The in-situ harness has three LLM seams that can each run on a *different* provider:

* **agent-under-test** — the live Claude Code session (subscription; configured by the
  ``claude`` CLI / ANTHROPIC_* env, outside this resolver);
* **user simulator** — driven by :class:`tau2.eval_insitu.usersim.UserSimDriver`;
* **NL-assertion judge** — an optional LLM-as-judge.

This resolver gives the user-sim and judge a single, uniform way to point at any
OpenAI- or Anthropic-compatible endpoint via env vars, so a **local MLX server on Apple
Silicon** (Qwen, 8-bit, OpenAI-compatible ``/v1``) is just a provider profile — no code
change. tau2's ``generate()`` forwards ``api_base`` / ``api_key`` straight to LiteLLM,
so all three of these route through the same call path:

    role=USER_SIM
      TAU2_USER_SIM_PROVIDER = mlx | openai | anthropic | litellm   (default: mlx)
      TAU2_USER_SIM_MODEL    = e.g. "qwen2.5-32b-instruct-8bit"
      TAU2_USER_SIM_API_BASE = e.g. "http://localhost:8080/v1"      (mlx/openai)
      TAU2_USER_SIM_API_KEY  = e.g. "mlx" (dummy ok for a local server)

Provider profiles only decide the LiteLLM model prefix and the default api_base/key; if
``TAU2_<ROLE>_MODEL`` already carries a provider prefix (``openai/``, ``anthropic/``,
``litellm_proxy/``, ...) it is used verbatim.

MLX serving: e.g. ``mlx_lm.server --model <hf-id> --port 8080`` (or LM Studio) exposes an
OpenAI-compatible ``/v1``; ``provider=mlx`` targets it via LiteLLM's ``openai/`` route.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Provider -> (litellm model prefix, default api_base, default api_key, backend).
# api_base/api_key None means "let LiteLLM use its standard env (e.g. ANTHROPIC_API_KEY)".
# backend "litellm" routes through tau2's generate(); "claude_cli" shells to `claude -p`.
_PROFILES: dict[str, tuple[str, str | None, str | None, str]] = {
    # Local MLX (Apple Silicon) or any OpenAI-compatible local server.
    "mlx": ("openai/", "http://localhost:8080/v1", "mlx", "litellm"),
    "openai_local": ("openai/", "http://localhost:8080/v1", "local", "litellm"),
    # Cloud OpenAI (uses OPENAI_API_KEY unless overridden).
    "openai": ("openai/", None, None, "litellm"),
    # Anthropic cloud (uses ANTHROPIC_API_KEY unless overridden).
    "anthropic": ("anthropic/", None, None, "litellm"),
    # Corporate LiteLLM proxy (the fork's existing gateway).
    "litellm": ("litellm_proxy/", None, None, "litellm"),
    # Zero-setup fallback: drive the user-sim via `claude -p` on the subscription.
    # No api_base/key; the model string is passed to `claude --model` (blank = default).
    "claude_cli": ("", None, None, "claude_cli"),
}

_DEFAULT_PROVIDER = "mlx"


@dataclass
class ModelSpec:
    """A resolved model and the LiteLLM kwargs needed to reach it."""

    model: str
    llm_args: dict = field(default_factory=dict)
    backend: str = "litellm"


def _env(role: str, key: str) -> str | None:
    return os.environ.get(f"TAU2_{role.upper()}_{key}")


def resolve_model(
    role: str,
    *,
    default_provider: str = _DEFAULT_PROVIDER,
    default_model: str | None = None,
) -> ModelSpec:
    """Resolve the ``ModelSpec`` for ``role`` (e.g. ``"USER_SIM"``) from env.

    Falls back to ``default_model`` when ``TAU2_<ROLE>_MODEL`` is unset. Raises
    ``ValueError`` if no model can be determined or the provider is unknown.
    """
    provider = (_env(role, "PROVIDER") or default_provider).lower()
    if provider not in _PROFILES:
        raise ValueError(
            f"Unknown provider {provider!r} for role {role}. "
            f"Known: {sorted(_PROFILES)}."
        )
    prefix, default_base, default_key, backend = _PROFILES[provider]

    raw_model = _env(role, "MODEL") or default_model

    if backend == "claude_cli":
        # Model is optional: empty means "let the claude CLI use its default model".
        # It is passed to `claude --model`, not to LiteLLM, so no prefix/base/key.
        return ModelSpec(model=raw_model or "", llm_args={}, backend=backend)

    if not raw_model:
        raise ValueError(
            f"No model for role {role}: set TAU2_{role.upper()}_MODEL "
            f"(or pass default_model)."
        )

    # Respect an explicit provider prefix; otherwise apply the profile's.
    known_prefixes = ("openai/", "anthropic/", "litellm_proxy/", "hosted_vllm/")
    model = raw_model if raw_model.startswith(known_prefixes) else prefix + raw_model

    llm_args: dict = {}
    api_base = _env(role, "API_BASE") or default_base
    api_key = _env(role, "API_KEY") or default_key
    if api_base:
        llm_args["api_base"] = api_base
    if api_key:
        llm_args["api_key"] = api_key

    return ModelSpec(model=model, llm_args=llm_args, backend=backend)
