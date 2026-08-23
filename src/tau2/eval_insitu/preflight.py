"""Preflight check for an in-situ role's model gateway (esp. local MLX).

Resolves the gateway config for a role (default ``USER_SIM``) and verifies the endpoint
is actually reachable and answering, so you can confirm a local MLX server works with our
stack *before* a full run:

    python -m tau2.eval_insitu.preflight                 # checks USER_SIM
    python -m tau2.eval_insitu.preflight --role JUDGE

For LiteLLM-backed providers (mlx / openai / anthropic / litellm) it sends a tiny chat
completion to the resolved model + api_base. For the ``claude_cli`` provider it runs a
one-shot ``claude -p``. Exit code 0 = OK, non-zero = misconfigured/unreachable.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

from tau2.eval_insitu.model_gateway import resolve_model


def check_role(role: str, default_model: Optional[str] = None) -> tuple[bool, str]:
    """Return (ok, message) after pinging the resolved model for ``role``."""
    try:
        spec = resolve_model(role, default_model=default_model)
    except ValueError as e:
        return False, f"config error: {e}"

    if spec.backend == "claude_cli":
        cmd = ["claude", "-p", "Reply with exactly: OK", "--max-turns", "1"]
        if spec.model:
            cmd += ["--model", spec.model]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return False, f"claude_cli failed: {e}"
        if res.returncode != 0:
            return False, f"claude_cli rc={res.returncode}: {res.stderr.strip()[:200]}"
        return (
            True,
            f"claude_cli OK (model={spec.model or 'default'}): {res.stdout.strip()[:60]!r}",
        )

    # LiteLLM-backed providers: a tiny completion to the resolved endpoint.
    try:
        from litellm import completion

        resp = completion(
            model=spec.model,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=5,
            **spec.llm_args,
        )
        text = resp.choices[0].message.content
    except Exception as e:  # noqa: BLE001
        base = spec.llm_args.get("api_base", "<provider default>")
        return False, f"completion failed (model={spec.model}, api_base={base}): {e}"
    return (
        True,
        f"OK (model={spec.model}, api_base={spec.llm_args.get('api_base', 'default')}): {str(text).strip()[:60]!r}",
    )


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Preflight an in-situ model gateway role"
    )
    parser.add_argument(
        "--role", default="USER_SIM", help="role env prefix (default USER_SIM)"
    )
    parser.add_argument("--default-model", default=None)
    args = parser.parse_args(argv)

    ok, msg = check_role(args.role, default_model=args.default_model)
    print(f"[{'PASS' if ok else 'FAIL'}] {args.role}: {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
