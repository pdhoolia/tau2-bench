"""Ensure the Strata router a tau2 run targets exists and is live.

Usage: uv run python scripts/strata/ensure_router.py <router-name>
           [--base http://127.0.0.1:8080] [--definition scripts/strata/router.json]
           [--api-key strata-tenant-credential]

- Router absent  -> create it from the definition file (whose "name" must match)
  and make it live, then probe until the gateway's route refresh tick picks it up.
- Router present -> require status "live" (a draft/paused router is a deliberate
  state; fix it in the console or delete it rather than having this script mutate it).
- Either way, every variant model must be visible via the gateway's LiteLLM catalog.
"""

import argparse
import json
import sys
import time

import httpx


def fail(msg: str) -> None:
    print(f"ensure_router: {msg}", file=sys.stderr)
    sys.exit(1)


def variant_models(router: dict) -> set[str]:
    route = router.get("defaultRoute") or router.get("default_route") or {}
    models = {v["model"] for v in route.get("variants", [])}
    for rule in router.get("rules") or []:
        for v in (rule.get("route") or {}).get("variants", []):
            models.add(v["model"])
    return models


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--definition", default="scripts/strata/router.json")
    ap.add_argument("--api-key", default="strata-tenant-credential")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    with httpx.Client(timeout=30) as http:
        listing = http.get(f"{base}/api/routers")
        listing.raise_for_status()
        existing = next(
            (r for r in listing.json()["routers"] if r["name"] == args.name), None
        )

        if existing is not None:
            if existing["status"] != "live":
                fail(
                    f"router strata/{args.name} exists but is '{existing['status']}' — "
                    "make it live in the Strata console (or delete it and rerun)"
                )
            models = variant_models(existing)
            created = False
        else:
            definition = json.load(open(args.definition))
            if definition.get("name") != args.name:
                fail(
                    f"definition {args.definition} is for "
                    f"'{definition.get('name')}', not '{args.name}'"
                )
            res = http.post(f"{base}/api/routers", json={"name": args.name})
            if res.status_code not in (201, 409):
                fail(f"create failed: {res.status_code} {res.text}")
            router_id = res.json()["router"]["id"]
            res = http.patch(
                f"{base}/api/routers/{router_id}",
                json={
                    "rules": definition.get("rules", []),
                    "defaultRoute": definition["defaultRoute"],
                    "sticky": definition.get("sticky", "user_id"),
                    "status": "live",
                },
            )
            if res.status_code != 200:
                fail(f"configure failed: {res.status_code} {res.text}")
            print(
                f"created router strata/{args.name} (live): {json.dumps(definition['defaultRoute'])}"
            )
            models = variant_models(definition)
            created = True

        catalog = http.get(
            f"{base}/litellm/v1/models",
            headers={"Authorization": f"Bearer {args.api_key}"},
        )
        catalog.raise_for_status()
        available = {m["id"] for m in catalog.json()["data"]}
        missing = models - available
        if missing:
            fail(f"variant model(s) not on LiteLLM via Strata: {sorted(missing)}")

        if created:
            # A new router resolves on the gateway's route refresh tick
            # (STRATA_ROUTE_REFRESH_SECONDS, default 15s). Probe with a 1-token
            # call until the model ref stops 404ing.
            deadline = time.monotonic() + 60
            while True:
                probe = http.post(
                    f"{base}/c/tau2-preflight/litellm/v1/chat/completions",
                    headers={"Authorization": f"Bearer {args.api_key}"},
                    json={
                        "model": f"strata/{args.name}",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
                if probe.status_code != 404:
                    print(
                        f"router strata/{args.name} resolves (probe: {probe.status_code})"
                    )
                    break
                if time.monotonic() > deadline:
                    fail(f"router strata/{args.name} still 404 after 60s")
                time.sleep(3)

    print(f"router strata/{args.name} ready; variants on catalog: {sorted(models)}")


if __name__ == "__main__":
    main()
