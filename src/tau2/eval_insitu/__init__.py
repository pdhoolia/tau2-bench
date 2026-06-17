"""In-situ evaluation harness (higher-order harness).

Phase 2 building blocks for running tau2 evaluation *inside* a Claude Code session:
assemble a tau2 ``SimulationRun`` trajectory and score it with the canonical
``tau2.evaluator.evaluate_simulation`` (no reimplementation — parity by reuse).
"""

from tau2.eval_insitu.score import build_action_trajectory, score_trajectory

__all__ = ["build_action_trajectory", "score_trajectory"]
