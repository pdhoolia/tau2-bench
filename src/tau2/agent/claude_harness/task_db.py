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


def _build_db(
    task: Optional[Task],
    *,
    domain: str,
    load_default_db: Callable,
    get_environment: Callable,
):
    """Return the initial DB *object* for ``task`` (no file I/O).

    This is the shared core used by both the file seeders (which dump the result)
    and the in-memory reseed path (which assigns it onto a live toolkit). Tasks
    with no ``initial_state`` get the pristine default DB; tasks that carry one are
    materialized via the same ``Environment.set_state`` machinery tau2 evaluates
    against, so the resulting state matches the scored baseline.

    :param load_default_db: callable returning a fresh default DB instance.
    :param get_environment: the domain's ``get_environment`` factory, used only
        when the task carries an ``initial_state`` that must be applied.
    """
    initial_state = getattr(task, "initial_state", None) if task else None

    if initial_state is None:
        return load_default_db()

    env = get_environment()
    env.set_state(
        initialization_data=initial_state.initialization_data,
        initialization_actions=initial_state.initialization_actions,
        message_history=initial_state.message_history or [],
    )
    logger.debug(f"Built initialized {domain} DB for task {getattr(task, 'id', '?')}")
    return env.tools.db


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

    # Round-trip through the DB model so the serialized form is exactly what the
    # server will load back.
    db = _build_db(
        task,
        domain=domain,
        load_default_db=load_default_db,
        get_environment=get_environment,
    )
    db.dump(str(out_path))
    return out_path


def _retail_spec() -> tuple[Callable, Callable]:
    from tau2.domains.retail.data_model import RetailDB
    from tau2.domains.retail.environment import get_environment
    from tau2.domains.retail.utils import RETAIL_DB_PATH

    return (lambda: RetailDB.load(str(RETAIL_DB_PATH))), get_environment


def _legal_spec() -> tuple[Callable, Callable]:
    from tau2.domains.legal.data_model import LegalDB
    from tau2.domains.legal.environment import get_environment
    from tau2.domains.legal.utils import LEGAL_DB_PATH

    return (lambda: LegalDB.load(str(LEGAL_DB_PATH))), get_environment


# Domain name -> callable returning (load_default_db, get_environment).
_DOMAIN_SPECS: dict[str, Callable[[], tuple[Callable, Callable]]] = {
    "retail": _retail_spec,
    "legal": _legal_spec,
}


def _resolve_spec(domain_name: str) -> tuple[Callable, Callable]:
    try:
        spec = _DOMAIN_SPECS[domain_name]
    except KeyError:
        raise ValueError(
            f"claude_harness has no DB support for domain {domain_name!r}. "
            f"Supported domains: {sorted(_DOMAIN_SPECS)}."
        )
    return spec()


def seed_retail_db_for_task(task: Optional[Task], out_path: str | Path) -> Path:
    """Write the initial retail DB for ``task`` to ``out_path`` (JSON).

    Returns the path, ready to pass to ``retail_server --db-path``.
    """
    return seed_db_for_task("retail", task, out_path)


def seed_legal_db_for_task(task: Optional[Task], out_path: str | Path) -> Path:
    """Write the initial legal DB for ``task`` to ``out_path`` (JSON).

    Returns the path, ready to pass to ``legal_server --db-path``.
    """
    return seed_db_for_task("legal", task, out_path)


def seed_db_for_task(
    domain_name: str, task: Optional[Task], out_path: str | Path
) -> Path:
    """Seed the per-task DB for ``domain_name`` to a JSON file at ``out_path``."""
    load_default_db, get_environment = _resolve_spec(domain_name)
    return _seed_with(
        task,
        out_path,
        domain=domain_name,
        load_default_db=load_default_db,
        get_environment=get_environment,
    )


def build_task_db(domain_name: str, task: Optional[Task]):
    """Return the initial DB *object* for ``domain_name``/``task`` (no file I/O).

    Used by the persistent eval-control server to reseed a live toolkit between
    tasks without spawning a new process. The state matches what tau2 evaluates
    against (same machinery as :func:`seed_db_for_task`).
    """
    load_default_db, get_environment = _resolve_spec(domain_name)
    return _build_db(
        task,
        domain=domain_name,
        load_default_db=load_default_db,
        get_environment=get_environment,
    )
