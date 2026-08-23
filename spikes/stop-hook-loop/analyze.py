#!/usr/bin/env python3
"""Parse the stream-json run log and report the verdict for the Stop-hook spike.

Reads .runtime/run.log (newline-delimited JSON from `claude -p --output-format
stream-json`) and prints, in order, every assistant text block. Then checks whether
the injected tokens (TURN-B, TURN-C, TURN-D) appear — i.e. whether the Stop hook
successfully fed each follow-up "user" turn back to the model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent / ".runtime"
EXPECTED_TOKENS = ["TURN-A", "TURN-B", "TURN-C", "TURN-D"]


def assistant_texts(log_path: Path) -> list[str]:
    texts: list[str] = []
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        if evt.get("type") != "assistant":
            continue
        content = evt.get("message", {}).get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "").strip()
                if t:
                    texts.append(t)
    return texts


def main() -> int:
    log_path = RUNTIME / "run.log"
    if not log_path.exists():
        print(f"no run log at {log_path} — run ./run.sh first")
        return 1

    texts = assistant_texts(log_path)
    print("=== assistant text blocks (in order) ===")
    for i, t in enumerate(texts):
        print(f"  [{i}] {t!r}")

    joined = "\n".join(texts)
    print("\n=== token check ===")
    found = []
    for tok in EXPECTED_TOKENS:
        present = re.search(rf"\b{re.escape(tok)}\b", joined) is not None
        print(f"  {tok}: {'FOUND' if present else 'missing'}")
        if present:
            found.append(tok)

    print("\n=== verdict ===")
    injected = [t for t in found if t != "TURN-A"]
    if len(found) == len(EXPECTED_TOKENS):
        print("PASS: all injected turns reached the model. Stop-hook injection works.")
        return 0
    if injected:
        print(
            f"PARTIAL: {len(injected)} injected turn(s) reached the model "
            f"({injected}); expected {EXPECTED_TOKENS[1:]}."
        )
        return 2
    print("FAIL: no injected turn reached the model — `reason` is not fed back.")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
