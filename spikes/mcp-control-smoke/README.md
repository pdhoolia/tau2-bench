# Smoke: claude ↔ eval-control MCP server

Validates the in-situ MCP path (Phase 1/2) independent of the user-sim loop: that a live
`claude` session can reach the [eval-control server](../../src/tau2/mcp/eval_control_server.py)
and actually invoke a domain tool, with permissions granted under root via a settings
allowlist (no `bypassPermissions`).

## Run

```bash
bash spikes/mcp-control-smoke/run.sh
```

## Result — PASS (CLI 2.1.179, 2026-06-17)

The eval-control server served 13 legal tools; `claude -p` called
`mcp__tau2-legal__list_practitioners` and answered from the seeded DB:

```
=== domain tool calls ===
      1 "name":"mcp__tau2-legal__list_practitioners"
```
> There are **4 practitioners** at the firm: Sarah Johnson (Principal, Current),
> David Nguyen (Employee, Current), Emma White (Employee, Expired),
> Michael Chen (Principal, Suspended).

Confirms, under root: MCP wiring via `--mcp-config`/`--strict-mcp-config`, the
eval-control server's `/mcp/<domain>` endpoint, the `settings.json` tool allowlist as the
non-root permission path, and that the agent invokes our domain tools against the seeded
world. The remaining gap for full multi-turn e2e (Phase 3) is a reachable **user-sim
model endpoint** (local MLX / proxy / cloud) — see `harnesses/docs/higher-order-harness.md` §7.
