"""Tests for the in-situ benchmark suite runner (offline; runner injected)."""

from tau2.eval_insitu.suite import run_suite, summarize


def test_summarize_means_and_pass_at_1():
    results = [
        {"task_id": "a", "trial": 0, "reward": 1.0},
        {"task_id": "a", "trial": 1, "reward": 0.0},
        {"task_id": "b", "trial": 0, "reward": 1.0},
    ]
    s = summarize(results)
    assert s["num_tasks"] == 2
    assert s["num_runs"] == 3
    assert s["per_task_reward"]["a"] == 0.5
    assert s["per_task_reward"]["b"] == 1.0
    assert s["suite_reward"] == 0.75  # mean over tasks: (0.5 + 1.0)/2
    assert abs(s["pass@1"] - (2 / 3)) < 1e-9


def test_run_suite_with_injected_runner(tmp_path):
    seen = []

    def fake_runner(cfg):
        seen.append((cfg.task_id, cfg.run_dir))
        # happy_path "passes", a conflict task "passes" too; pretend one fails.
        reward = 0.0 if cfg.task_id.endswith("fail") else 1.0
        return {"task_id": cfg.task_id, "reward": reward}

    summary = run_suite(
        domain="legal",
        harness_plugin_dir="/p/legal-harness",
        tau2_eval_plugin_dir="/p/tau2-eval",
        out_dir=tmp_path,
        task_ids=["intake_happy_path"],
        trials=2,
        runner=fake_runner,
    )
    assert summary["num_runs"] == 2
    assert summary["per_task_reward"]["intake_happy_path"] == 1.0
    # Per-task/per-trial run dirs are distinct.
    assert len({rd for _, rd in seen}) == 2
    assert (tmp_path / "suite_result.json").exists()


def test_run_suite_isolates_task_failures(tmp_path):
    def flaky_runner(cfg):
        if cfg.task_id == "boom":
            raise RuntimeError("kaboom")
        return {"task_id": cfg.task_id, "reward": 1.0}

    # Patch task-id resolution to a synthetic set including a failing one.
    import tau2.eval_insitu.suite as suite_mod

    orig = suite_mod._resolve_task_ids
    suite_mod._resolve_task_ids = lambda domain, ids: ids
    try:
        summary = run_suite(
            domain="legal",
            harness_plugin_dir="/p/legal-harness",
            tau2_eval_plugin_dir="/p/tau2-eval",
            out_dir=tmp_path,
            task_ids=["ok", "boom"],
            runner=flaky_runner,
        )
    finally:
        suite_mod._resolve_task_ids = orig

    rewards = {r["task_id"]: r["reward"] for r in summary["results"]}
    assert rewards["ok"] == 1.0
    assert rewards["boom"] == 0.0  # failure captured, suite continued
