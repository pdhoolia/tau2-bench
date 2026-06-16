"""Seed an isolated per-task domain DB for the claude_harness MCP server.

A domain MCP server loads its database from a JSON path (`<Domain>DB.load`). To
give Claude a private, correctly-initialized world per task — mirroring exactly
the starting state tau2 evaluates against — we materialize the task's initial DB
to a temp JSON file and point the server at it.

Most stock tasks have ``initial_state is None`` (they use the default db.json
unchanged), so the common path is a straight copy. Tasks that DO carry an
``initial_state`` are handled via the same ``Environment.set_state`` machinery the
orchestrator/evaluator use, so the seeded DB matches the evaluated baseline.

Each domain plugs in by providing its default ``DB`` loader and ``get_environment``
factory; :func:`seed_db_for_task` dispatches on the domain name.
``seed_retail_db_for_task`` / ``seed_legal_db_for_task`` are the concrete seeders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from tau2.data_model.tasks import Task


def _seed_with(
    task: Optional[Task],
    out_path: str | Path,
    *,
    domain: str,
    load_default_db: Callable,
    get_environment: Callable,
) -> Path:
    """Write the initial DB for ``task`` to ``out_path`` (JSON).

    :param load_default_db: callable returning a fresh default DB instance.
    :param get_environment: the domain's ``get_environment`` factory, used only
        when the task carries an ``initial_state`` that must be applied.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    initial_state = getattr(task, "initial_state", None) if task else None

    if initial_state is None:
        # Fast path: pristine default DB, round-tripped through the DB model so
        # the serialized form is exactly what the server will load back.
        db = load_default_db()
        db.dump(str(out_path))
        return out_path

    # Initialized task: apply initial_state via the same env machinery tau2 uses.
    env = get_environment()
    env.set_state(
        initialization_data=initial_state.initialization_data,
        initialization_actions=initial_state.initialization_actions,
        message_history=initial_state.message_history or [],
    )
    env.tools.db.dump(str(out_path))
    logger.debug(f"Seeded initialized {domain} DB for task {getattr(task, 'id', '?')}")
    return out_path


def seed_retail_db_for_task(task: Optional[Task], out_path: str | Path) -> Path:
    """Write the initial retail DB for ``task`` to ``out_path`` (JSON).

    Returns the path, ready to pass to ``retail_server --db-path``.
    """
    from tau2.domains.retail.data_model import RetailDB
    from tau2.domains.retail.environment import get_environment
    from tau2.domains.retail.utils import RETAIL_DB_PATH

    return _seed_with(
        task,
        out_path,
        domain="retail",
        load_default_db=lambda: RetailDB.load(str(RETAIL_DB_PATH)),
        get_environment=get_environment,
    )


def seed_legal_db_for_task(task: Optional[Task], out_path: str | Path) -> Path:
    """Write the initial legal DB for ``task`` to ``out_path`` (JSON).

    Returns the path, ready to pass to ``legal_server --db-path``.
    """
    from tau2.domains.legal.data_model import LegalDB
    from tau2.domains.legal.environment import get_environment
    from tau2.domains.legal.utils import LEGAL_DB_PATH

    return _seed_with(
        task,
        out_path,
        domain="legal",
        load_default_db=lambda: LegalDB.load(str(LEGAL_DB_PATH)),
        get_environment=get_environment,
    )


# Domain name -> per-task DB seeder.
_SEEDERS: dict[str, Callable[[Optional[Task], "str | Path"], Path]] = {
    "retail": seed_retail_db_for_task,
    "legal": seed_legal_db_for_task,
}


def seed_db_for_task(
    domain_name: str, task: Optional[Task], out_path: str | Path
) -> Path:
    """Seed the per-task DB for ``domain_name``; dispatches to the domain seeder."""
    try:
        seeder = _SEEDERS[domain_name]
    except KeyError:
        raise ValueError(
            f"claude_harness has no DB seeder for domain {domain_name!r}. "
            f"Supported domains: {sorted(_SEEDERS)}."
        )
    return seeder(task, out_path)
