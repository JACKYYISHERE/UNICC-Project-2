#!/usr/bin/env python3
"""
Batch evaluation script — analyze each GitHub repo then run full council evaluation.
Usage:  python3 run_batch_eval.py
        python3 run_batch_eval.py --backend claude   (default: claude)
        python3 run_batch_eval.py --dry-run           (analyze only, skip evaluation)
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

API = "http://localhost:8100"

REPOS = [
    {"team": "Team 1",  "url": "https://github.com/hg3016-guo/unicc-ai-agent"},
    {"team": "Team 2a", "url": "https://github.com/Dulax0201/VeriMedia-Modified-"},
    {"team": "Team 2b", "url": "https://github.com/Dulax0201/ai-compliance-v2"},
    {"team": "Team 4",  "url": "https://github.com/Macondo0328/UNICC-safety-agent"},
    {"team": "Team 5",  "url": "https://github.com/shixuanlin1/unicc"},
    {"team": "Team 8",  "url": "https://github.com/RyanYang1390/unicc-ai-safety-sandbox-final"},
    {"team": "Team 9",  "url": "https://github.com/dondondon123456/unicc-ai-safety"},
]


def post(path: str, body: dict, timeout: int = 300) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def decision_color(d: str) -> str:
    return {"APPROVE": "32", "REVIEW": "33", "REJECT": "31"}.get(d, "37")


def banner(msg: str):
    print("\n" + "═" * 60)
    print(f"  {msg}")
    print("═" * 60)


def run_batch(backend: str, dry_run: bool):
    # Health check
    try:
        get("/health")
        print(color("✓ Backend reachable at " + API, "32"))
    except Exception as e:
        print(color(f"✗ Backend not reachable: {e}", "31"))
        print("  Start with:  cd frontend_api && uvicorn main:app --port 8100 --reload")
        sys.exit(1)

    results = []

    for entry in REPOS:
        team = entry["team"]
        url  = entry["url"]
        banner(f"{team}  {url}")

        # ── Step 1: Analyze repo ──────────────────────────────────────
        print(f"  [1/2] Analyzing repo…", end="", flush=True)
        t0 = time.time()
        try:
            info = post("/analyze/repo", {"source": url, "backend": backend})
            elapsed = time.time() - t0
            print(color(f"  done ({elapsed:.1f}s)", "32"))
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(color(f"\n  ✗ Analyze failed [{e.code}]: {body[:200]}", "31"))
            results.append({"team": team, "url": url, "status": "analyze_failed", "error": body})
            continue
        except Exception as e:
            print(color(f"\n  ✗ Analyze error: {e}", "31"))
            results.append({"team": team, "url": url, "status": "analyze_failed", "error": str(e)})
            continue

        system_name = info.get("system_name") or url.split("/")[-1]
        agent_id    = info.get("agent_id")    or url.split("/")[-1].lower().replace(" ", "-")
        description = info.get("system_description", "")
        category    = info.get("category", "")
        deploy_zone = info.get("deploy_zone", "")

        print(f"  {'System':12s} {system_name}")
        print(f"  {'Agent ID':12s} {agent_id}")
        print(f"  {'Category':12s} {category}")
        print(f"  {'Deploy Zone':12s} {deploy_zone}")
        if description:
            print(f"  {'Desc':12s} {description[:120]}…")

        if dry_run:
            print(color("  [dry-run] Skipping evaluation.", "33"))
            results.append({
                "team": team, "url": url, "status": "dry_run",
                "system_name": system_name, "agent_id": agent_id,
            })
            continue

        # ── Step 2: Council evaluation ────────────────────────────────
        print(f"\n  [2/2] Running council evaluation (may take 2-4 min)…", end="", flush=True)
        t1 = time.time()
        payload = {
            "agent_id":           agent_id,
            "system_name":        system_name,
            "system_description": description,
            "purpose":            info.get("capabilities", ""),
            "deployment_context": f"{deploy_zone} — {category}",
            "backend":            backend,
        }
        try:
            report = post("/evaluate/council", payload, timeout=600)
            elapsed = time.time() - t1
            print(color(f"  done ({elapsed:.1f}s)", "32"))
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(color(f"\n  ✗ Eval failed [{e.code}]: {body[:200]}", "31"))
            results.append({"team": team, "url": url, "status": "eval_failed",
                            "system_name": system_name, "error": body})
            continue
        except Exception as e:
            print(color(f"\n  ✗ Eval error: {e}", "31"))
            results.append({"team": team, "url": url, "status": "eval_failed",
                            "system_name": system_name, "error": str(e)})
            continue

        cd      = report.get("council_decision") or {}
        decision    = cd.get("final_recommendation", "?")
        consensus   = cd.get("consensus_level", "?")
        incident_id = report.get("incident_id", "?")

        dc = decision_color(decision)
        print(f"\n  {'Decision':12s} {color(decision, dc)}")
        print(f"  {'Consensus':12s} {consensus}")
        print(f"  {'Incident ID':12s} {incident_id}")
        print(f"  {'Report URL':12s} http://localhost:5173/ → ExpertAnalysis → {incident_id}")

        results.append({
            "team":        team,
            "url":         url,
            "status":      "ok",
            "system_name": system_name,
            "agent_id":    agent_id,
            "decision":    decision,
            "consensus":   consensus,
            "incident_id": incident_id,
        })

    # ── Summary ───────────────────────────────────────────────────────
    banner("BATCH SUMMARY")
    header = f"  {'Team':<10} {'System':<35} {'Decision':<10} {'Consensus':<12} {'Status'}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        dec    = r.get("decision", r.get("status", "—"))
        cons   = r.get("consensus", "—")
        dc     = decision_color(dec)
        name   = r.get("system_name", r["url"].split("/")[-1])[:33]
        status = r.get("status", "")
        print(f"  {r['team']:<10} {name:<35} {color(dec, dc):<10} {cons:<12} {status}")

    # Save JSON summary
    out_path = "batch_eval_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Full results saved to: {out_path}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend",  default="claude", choices=["claude", "vllm"])
    parser.add_argument("--dry-run",  action="store_true", help="Analyze repos only, skip evaluation")
    args = parser.parse_args()

    print(color(f"\n  UNICC Council — Batch Evaluation", "1"))
    print(f"  Backend: {args.backend}   Teams: {len(REPOS)}   Dry-run: {args.dry_run}\n")

    run_batch(backend=args.backend, dry_run=args.dry_run)
