from pathlib import Path
from typing import Optional

from tau2.data_model.tasks import Task
from tau2.domains.legal.data_model import LegalDB
from tau2.domains.legal.tools import LegalTools
from tau2.domains.legal.utils import (
    LEGAL_DB_PATH,
    LEGAL_POLICY_PATH,
    LEGAL_TASK_SET_PATH,
)
from tau2.environment.environment import Environment
from tau2.utils import load_file


def get_environment(
    db: Optional[LegalDB] = None,
    solo_mode: bool = False,
) -> Environment:
    if solo_mode:
        raise ValueError("Solo mode not supported for legal")
    if db is None:
        db = LegalDB.load(LEGAL_DB_PATH)
    tools = LegalTools(db)
    with open(LEGAL_POLICY_PATH, "r") as fp:
        policy = fp.read()
    return Environment(
        domain_name="legal",
        policy=policy,
        tools=tools,
    )


def get_tasks(task_split_name: Optional[str] = "base") -> list[Task]:
    tasks = load_file(LEGAL_TASK_SET_PATH)
    tasks = [Task.model_validate(task) for task in tasks]
    if task_split_name is None:
        return tasks
    task_splits = get_tasks_split()
    if task_split_name not in task_splits:
        raise ValueError(
            f"Invalid task split name: {task_split_name}. Valid splits are: {task_splits.keys()}"
        )
    return [task for task in tasks if task.id in task_splits[task_split_name]]


def get_tasks_split() -> dict[str, list[str]]:
    split_file = (
        Path(LEGAL_TASK_SET_PATH).parent
        / f"split_{Path(LEGAL_TASK_SET_PATH).stem}.json"
    )
    return load_file(split_file)
