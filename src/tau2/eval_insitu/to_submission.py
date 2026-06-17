"""Convert an in-situ suite run into a tau2-bench leaderboard submission.

The in-situ runner (``run_insitu`` / ``suite``) records, per task, the agent's full
``claude -p`` transcript. This module rebuilds the canonical tau2 artifacts from those
transcripts — a proper ``Results`` object (tasks + ``SimulationRun``s with messages and
the rich ``RewardInfo`` from ``evaluate_simulation``) — and writes a leaderboard
submission (``submission.json`` + ``trajectories/<domain>_results.json``) plus a
``manifest.json`` entry, so the run can be browsed in the leaderboard web app exactly
like a ``tau2 run`` result.

Mirrors the fork's existing local legal submissions (minimal ``submission.json`` with a
local ``trajectories/`` dir), not the official S3 schema.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from tau2.data_model.simulation import (
    AgentInfo,
    Info,
    Results,
    SimulationIndexEntry,
    SimulationRun,
    TerminationReason,
    UserInfo,
)
from tau2.environment.environment import EnvironmentInfo
from tau2.eval_insitu.hook_logic import load_task
from tau2.eval_insitu.transcript import stream_json_to_trajectory
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.registry import registry


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            or "unknown"
        )
    except Exception:
        return "unknown"


def _git_ignored(path: str | Path) -> bool:
    """True if ``path`` is excluded by a .gitignore rule (so a plain `git add` skips it)."""
    try:
        return (
            subprocess.run(
                ["git", "check-ignore", "-q", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
    except Exception:
        return False


def _mcp_prefix(domain: str) -> str:
    return f"mcp__tau2-{domain}__"


def build_results(suite_dir: str | Path, domain: str) -> Results:
    """Rebuild a tau2 ``Results`` from an in-situ suite out-dir.

    Walks ``<suite_dir>/<task>/trial-*/`` dirs, reconstructs each trajectory from the
    saved ``claude_stdout.jsonl``, scores it with the canonical evaluator, and assembles
    a ``Results`` object.
    """
    suite_dir = Path(suite_dir)
    prefix = _mcp_prefix(domain)

    simulations: list[SimulationRun] = []
    tasks = []
    seen_tasks: set[str] = set()
    last_cfg: dict = {}

    for task_dir in sorted(p for p in suite_dir.iterdir() if p.is_dir()):
        for trial_dir in sorted(task_dir.glob("trial-*")):
            stdout_f = trial_dir / "claude_stdout.jsonl"
            cfg_f = trial_dir / "config.json"
            if not stdout_f.exists() or not cfg_f.exists():
                continue
            cfg = json.loads(cfg_f.read_text())
            last_cfg = cfg
            task = load_task(cfg["task_set"], cfg["task_id"])
            if task.id not in seen_tasks:
                tasks.append(task)
                seen_tasks.add(task.id)

            trial_no = int(trial_dir.name.split("-")[-1] or 0)
            messages = stream_json_to_trajectory(stdout_f.read_text(), prefix)

            mtime = datetime.fromtimestamp(stdout_f.stat().st_mtime).isoformat()
            sim = SimulationRun(
                id=f"insitu_{task.id}_t{trial_no}",
                task_id=task.id,
                start_time=mtime,
                end_time=mtime,
                duration=0.0,
                termination_reason=TerminationReason.USER_STOP,
                messages=messages,
                trial=trial_no,
            )
            sim.reward_info = evaluate_simulation(
                simulation=sim,
                task=task,
                evaluation_type=EvaluationType.ALL,
                solo_mode=False,
                domain=domain,
            )
            simulations.append(sim)

    if not simulations:
        raise ValueError(f"No in-situ trial transcripts found under {suite_dir}")

    env = registry.get_env_constructor(domain)()
    env_info = EnvironmentInfo(domain_name=domain, policy=env.policy, tool_defs=None)

    backend = last_cfg.get("user_sim_backend", "litellm")
    user_sim_model = last_cfg.get("user_sim_model") or ""
    user_sim_label = (
        f"claude_cli ({user_sim_model or 'claude -p subscription default'})"
        if backend == "claude_cli"
        else user_sim_model
    )

    info = Info(
        git_commit=_git_commit(),
        num_trials=1 + max((s.trial or 0) for s in simulations),
        max_steps=0,
        max_errors=0,
        user_info=UserInfo(
            implementation=f"user_simulator (in-situ / {backend})",
            llm=user_sim_label,
            llm_args=last_cfg.get("user_sim_llm_args") or None,
        ),
        agent_info=AgentInfo(
            implementation="tau2-eval in-situ (Claude Code session + domain harness plugin)",
            llm="claude -p (subscription default model, unpinned)",
        ),
        environment_info=env_info,
        seed=None,
    )

    sim_index = [
        SimulationIndexEntry(
            id=s.id,
            task_id=s.task_id,
            trial=s.trial or 0,
            reward=(s.reward_info.reward if s.reward_info else None),
            termination_reason=s.termination_reason.value,
            agent_cost=s.agent_cost,
            duration=s.duration,
        )
        for s in simulations
    ]

    return Results(
        info=info, tasks=tasks, simulations=simulations, simulation_index=sim_index
    )


def write_submission(
    results: Results,
    domain: str,
    submissions_root: str | Path,
    name: str,
    *,
    model_name: str,
    model_organization: str = "local",
    submitting_organization: str = "local",
    submission_date: Optional[str] = None,
    notes: str = "",
    update_manifest: bool = True,
) -> Path:
    """Write ``<submissions_root>/<name>/`` (submission.json + trajectories) + manifest."""
    submissions_root = Path(submissions_root)
    sub_dir = submissions_root / name
    (sub_dir / "trajectories").mkdir(parents=True, exist_ok=True)

    results_file = f"{domain}_results.json"
    (sub_dir / "trajectories" / results_file).write_text(
        results.model_dump_json(indent=2)
    )

    n = len(results.simulations)
    n_pass = sum(
        1 for s in results.simulations if s.reward_info and s.reward_info.reward == 1.0
    )
    ui = results.info.user_info
    submission = {
        "model_name": model_name,
        "model_organization": model_organization,
        "submitting_organization": submitting_organization,
        "submission_date": submission_date or date.today().isoformat(),
        "submission_type": "custom",
        "is_new": True,
        "trajectories_available": True,
        "trajectory_files": {domain: results_file},
        "methodology": {
            "tau2_bench_version": "fork",
            "user_simulator": ui.llm,
            "notes": notes
            or (
                f"In-situ higher-order harness: the tau2-eval plugin runs the eval loop "
                f"inside a live Claude Code session (agent-under-test = the session + the "
                f"{domain}-harness plugin). User simulator: {ui.llm}. "
                f"Scored by the canonical evaluator. {n_pass}/{n} passing."
            ),
        },
    }
    (sub_dir / "submission.json").write_text(json.dumps(submission, indent=2) + "\n")

    if update_manifest:
        manifest_f = submissions_root / "manifest.json"
        manifest = json.loads(manifest_f.read_text())
        if name not in manifest.get("submissions", []):
            manifest.setdefault("submissions", []).append(name)
        manifest_f.write_text(json.dumps(manifest, indent=2) + "\n")

    return sub_dir


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert an in-situ suite run into a leaderboard submission"
    )
    parser.add_argument("--suite-dir", required=True, help="in-situ suite out-dir")
    parser.add_argument("--domain", required=True)
    parser.add_argument(
        "--submissions-root",
        default="web/leaderboard/public/submissions",
    )
    parser.add_argument(
        "--name", required=True, help="submission dir name (include 'insitu')"
    )
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--submission-date", default=None)
    parser.add_argument("--notes", default="")
    parser.add_argument("--no-manifest", action="store_true")
    args = parser.parse_args(argv)

    results = build_results(args.suite_dir, args.domain)
    sub_dir = write_submission(
        results,
        args.domain,
        args.submissions_root,
        args.name,
        model_name=args.model_name,
        submission_date=args.submission_date,
        notes=args.notes,
        update_manifest=not args.no_manifest,
    )
    n = len(results.simulations)
    n_pass = sum(
        1 for s in results.simulations if s.reward_info and s.reward_info.reward == 1.0
    )
    print(f"Wrote submission {sub_dir} ({n_pass}/{n} passing)")

    # Reminder: submissions/.gitignore excludes */trajectories/*.json, so the
    # trajectory file needs `git add -f` or it is silently left untracked.
    traj = sub_dir / "trajectories" / f"{args.domain}_results.json"
    if _git_ignored(traj):
        print(
            "\nNOTE: the trajectory file is git-ignored "
            "(submissions/.gitignore: */trajectories/*.json).\n"
            "Force-add it (and the rest of the submission) so it is versioned:\n"
            f"  git add -f {traj}\n"
            f"  git add {sub_dir / 'submission.json'} "
            f"{Path(args.submissions_root) / 'manifest.json'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
