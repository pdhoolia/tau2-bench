"""Seed an isolated per-task retail DB for the claude_harness MCP server.

The retail MCP server loads its database from a JSON path (`RetailDB.load`). To
give Claude a private, correctly-initialized world per task — mirroring exactly
the starting state tau2 evaluates against — we materialize the task's initial DB
to a temp JSON file and point the server at it.

All 114 stock retail tasks have ``initial_state is None`` (they use the default
db.json unchanged), so the common path is a straight copy. Tasks that DO carry an
``initial_state`` are handled via the same ``Environment.set_state`` machinery the
orchestrator/evaluator use, so the seeded DB matches the evaluated baseline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from loguru import logger

from tau2.data_model.tasks import Task


def seed_retail_db_for_task(task: Optional[Task], out_path: str | Path) -> Path:
    """Write the initial retail DB for ``task`` to ``out_path`` (JSON).

    Returns the path, ready to pass to ``retail_server --db-path``.
    """
    from tau2.domains.retail.data_model import RetailDB
    from tau2.domains.retail.environment import get_environment
    from tau2.domains.retail.utils import RETAIL_DB_PATH

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    initial_state = getattr(task, "initial_state", None) if task else None

    if initial_state is None:
        # Fast path: pristine default DB, round-tripped through RetailDB so the
        # serialized form is exactly what the server will load back.
        db = RetailDB.load(str(RETAIL_DB_PATH))
        db.dump(str(out_path))
        return out_path

    # Initialized task: apply initial_state via the same env machinery tau2 uses.
    env = get_environment()
    env.set_state(
        initialization_data=initial_state.initialization_data,
        initialization_actions=initial_state.initialization_actions,
        message_history=initial_state.message_history or [],
    )
    db = env.tools.db
    db.dump(str(out_path))
    logger.debug(f"Seeded initialized retail DB for task {getattr(task, 'id', '?')}")
    return out_path
