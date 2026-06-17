"""Run an in-situ benchmark *suite* (many tasks, optional trials/concurrency).

Wraps :func:`tau2.eval_insitu.run_insitu.run` to evaluate a whole task set in-situ and
aggregate the rewards — the multi-task layer behind the MLX benchmark playbook
(``harnesses/docs/insitu-playbook.md``).

Concurrency is safe by construction: each task run gets its own eval-control lane on its
own port + private world (Phase 1), so ``--concurrency N`` runs N tasks in parallel
without them resetting a shared DB. A single MLX user-sim server can back all lanes
(watch its throughput).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from loguru import logger

from tau2.eval_insitu.run_insitu import _DOMAINS, InsituRunConfig, run


def _resolve_task_ids(domain: str, task_ids: Optional[list[str]]) -> list[str]:
    task_set, _ = _DOMAINS[domain]
    from tau2.runner.helpers import get_tasks

    all_ids = [t.id for t in get_tasks(task_set_name=task_set)]
    if not task_ids:
        return all_ids
    unknown = [t for t in task_ids if t not in all_ids]
    if unknown:
        raise ValueError(f"unknown task ids for {domain}: {unknown}")
    return task_ids


def summarize(results: list[dict]) -> dict:
    """Aggregate per-run results into a suite summary.

    ``results`` items are ``{"task_id","trial","reward",...}``. Per task we take the mean
    reward over trials; the suite reward is the mean over tasks; pass@1 counts runs with
    reward == 1.0.
    """
    by_task: dict[str, list[float]] = {}
    for r in results:
        by_task.setdefault(r["task_id"], []).append(float(r.get("reward") or 0.0))
    per_task = {tid: sum(v) / len(v) for tid, v in by_task.items()}
    n_runs = len(results)
    return {
        "num_tasks": len(per_task),
        "num_runs": n_runs,
        "suite_reward": (sum(per_task.values()) / len(per_task)) if per_task else 0.0,
        "pass@1": (sum(1 for r in results if (r.get("reward") or 0) == 1.0) / n_runs)
        if n_runs
        else 0.0,
        "per_task_reward": per_task,
    }


def run_suite(
    *,
    domain: str,
    harness_plugin_dir: str,
    tau2_eval_plugin_dir: str,
    out_dir: str | Path,
    task_ids: Optional[list[str]] = None,
    trials: int = 1,
    concurrency: int = 1,
    model: Optional[str] = None,
    user_sim_default_model: Optional[str] = None,
    max_turns: int = 60,
    runner=run,
) -> dict:
    """Run ``trials`` of each task in-situ and return the aggregated summary.

    ``runner`` is injectable for testing. Writes ``<out_dir>/suite_result.json``.
    """
    if domain not in _DOMAINS:
        raise ValueError(f"unsupported domain {domain!r}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = _resolve_task_ids(domain, task_ids)

    jobs = [(tid, trial) for tid in ids for trial in range(trials)]

    def _one(job) -> dict:
        tid, trial = job
        cfg = InsituRunConfig(
            domain=domain,
            task_id=tid,
            harness_plugin_dir=harness_plugin_dir,
            tau2_eval_plugin_dir=tau2_eval_plugin_dir,
            run_dir=out_dir / tid / f"trial-{trial}",
            user_sim_default_model=user_sim_default_model,
            model=model,
            max_turns=max_turns,
        )
        try:
            res = runner(cfg)
        except Exception as e:  # noqa: BLE001 — one task must not sink the suite
            logger.error(f"task {tid} trial {trial} failed: {e}")
            res = {"task_id": tid, "reward": 0.0, "error": str(e)}
        res.setdefault("task_id", tid)
        res["trial"] = trial
        return res

    results: list[dict] = []
    if concurrency <= 1:
        for job in jobs:
            results.append(_one(job))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(_one, job) for job in jobs]
            for fut in as_completed(futures):
                results.append(fut.result())

    summary = summarize(results)
    summary["results"] = sorted(results, key=lambda r: (r["task_id"], r["trial"]))
    (out_dir / "suite_result.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run an in-situ benchmark suite")
    parser.add_argument("--domain", required=True, choices=sorted(_DOMAINS))
    parser.add_argument("--harness-plugin-dir", required=True)
    parser.add_argument("--tau2-eval-plugin-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--task-ids", default=None, help="comma-separated; omit for ALL tasks"
    )
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--model", default=None, help="agent-under-test model")
    parser.add_argument("--user-sim-default-model", default=None)
    parser.add_argument("--max-turns", type=int, default=60)
    args = parser.parse_args(argv)

    summary = run_suite(
        domain=args.domain,
        harness_plugin_dir=args.harness_plugin_dir,
        tau2_eval_plugin_dir=args.tau2_eval_plugin_dir,
        out_dir=args.out_dir,
        task_ids=args.task_ids.split(",") if args.task_ids else None,
        trials=args.trials,
        concurrency=args.concurrency,
        model=args.model,
        user_sim_default_model=args.user_sim_default_model,
        max_turns=args.max_turns,
    )
    print(
        f"suite reward {summary['suite_reward']:.3f} | pass@1 {summary['pass@1']:.3f} "
        f"| {summary['num_tasks']} tasks, {summary['num_runs']} runs"
    )
    for tid, r in sorted(summary["per_task_reward"].items()):
        print(f"  {r:.3f}  {tid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
