#!/usr/bin/env python3
"""
Evaluate a local n8n / workflow JSON file through the UNICC Council.
Usage:  python3 run_workflow_eval.py <path-to-workflow.json>
"""

import json
import sys
import time
import urllib.request
import urllib.error

API = "http://localhost:8100"
WORKFLOW_PATH = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/yangjunjie/Downloads/My workflow 2 (2) (2).json"


def post(path: str, body: dict, timeout: int = 600) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def summarize_workflow(wf: dict) -> str:
    """Extract human-readable description from an n8n workflow JSON."""
    name = wf.get("name", "Unnamed Workflow")
    nodes = wf.get("nodes", [])

    node_names = [n.get("name", "") for n in nodes if n.get("name")]
    node_types = list({n.get("type", "").split(".")[-1] for n in nodes if n.get("type")})

    # Extract agent system prompts
    agent_roles = []
    for n in nodes:
        params = n.get("parameters", {})
        msgs = params.get("messages", {}).get("messageValues", [])
        for m in msgs:
            msg = m.get("message", "")
            if isinstance(msg, str) and ("you are" in msg.lower() or "your job" in msg.lower()):
                first_sentence = msg.strip().split("\n")[0][:200]
                if first_sentence not in agent_roles:
                    agent_roles.append(first_sentence)

    # Extract models used
    models = []
    for n in nodes:
        m = n.get("parameters", {}).get("model", "")
        if m and m not in models:
            models.append(m)

    # Extract external URLs
    urls = []
    for n in nodes:
        u = n.get("parameters", {}).get("url", "")
        if u and u not in urls:
            urls.append(u)

    # Build description text
    lines = [
        f"System Name: {name}",
        f"Type: n8n Automated Workflow / Multi-Agent AI Pipeline",
        f"",
        f"Nodes ({len(nodes)} total): {', '.join(node_names)}",
        f"Node types: {', '.join(node_types)}",
        f"",
        f"AI Models used: {', '.join(models) if models else 'unspecified'}",
        f"External data sources: {', '.join(urls) if urls else 'none'}",
        f"",
        f"Agent Roles identified:",
    ]
    for role in agent_roles[:5]:
        lines.append(f"  - {role}")

    lines += [
        f"",
        f"Pipeline Description:",
        f"  This is an automated AI safety compliance workflow. It fetches the EU AI Act",
        f"  text in real-time, then runs a multi-stage analysis pipeline:",
        f"  1. Risk Mapping Agent: maps AI model profiles + regulatory text into structured",
        f"     risk dimensions (Technical, Ethical, Legal, Societal) with policy alignment",
        f"     against EU AI Act, NIST AI RMF, ISO/IEC 42001, UNESCO, OECD.",
        f"  2. Test Case Generator: produces adversarial test prompts from risk items.",
        f"  3. Target Model Executor: runs test cases against the AI under evaluation.",
        f"  4. AI Test Evaluation Agent: judges each test result (pass/fail/needs_attention),",
        f"     severity scoring, and generates next_actions.",
        f"  5. Compliance Reporter: synthesises all results into a final compliance report",
        f"     with executive summary and retest checklist.",
        f"  Triggered by: monthly schedule (Schedule Trigger node).",
        f"  Output: structured JSON compliance report with final_recommendation.",
        f"",
        f"Data handled: AI model profiles, test prompts/responses, regulatory text (EU AI Act).",
        f"Deployment: cloud-hosted n8n instance via OpenRouter API (GPT-4o-mini).",
        f"Human oversight: report output only — no human-in-the-loop gate in current workflow.",
    ]
    return "\n".join(lines)


def main():
    # Load workflow
    print(color(f"\n  UNICC Council — Workflow File Evaluation", "1"))
    print(f"  File: {WORKFLOW_PATH}\n")

    try:
        with open(WORKFLOW_PATH, encoding="utf-8") as f:
            wf = json.load(f)
    except Exception as e:
        print(color(f"✗ Cannot read file: {e}", "31"))
        sys.exit(1)

    description_text = summarize_workflow(wf)
    print("  ── Extracted description ─────────────────────────────────")
    print("\n".join("  " + l for l in description_text.splitlines()))
    print()

    # Step 1 — Analyze text
    print(f"  [1/2] Sending to /analyze/repo (text mode)…", end="", flush=True)
    t0 = time.time()
    try:
        info = post("/analyze/repo", {"text": description_text, "backend": "claude"})
        print(color(f"  done ({time.time()-t0:.1f}s)", "32"))
    except urllib.error.HTTPError as e:
        print(color(f"\n  ✗ [{e.code}]: {e.read().decode()[:300]}", "31"))
        sys.exit(1)

    system_name = info.get("system_name") or wf.get("name", "n8n Workflow")
    agent_id    = info.get("agent_id")    or "n8n-ai-compliance-workflow"
    description = info.get("system_description", description_text[:800])
    category    = info.get("category", "Governance")
    deploy_zone = info.get("deploy_zone", "")

    print(f"  {'System':12s} {system_name}")
    print(f"  {'Agent ID':12s} {agent_id}")
    print(f"  {'Category':12s} {category}")
    print(f"  {'Deploy Zone':12s} {deploy_zone}")
    print(f"  {'Desc':12s} {description[:120]}…")

    # Step 2 — Council evaluation
    print(f"\n  [2/2] Running council evaluation…", end="", flush=True)
    t1 = time.time()
    payload = {
        "agent_id":           agent_id,
        "system_name":        system_name,
        "system_description": description,
        "purpose":            info.get("capabilities", ""),
        "deployment_context": f"{deploy_zone} — {category}",
        "data_access":        ["EU AI Act regulatory text", "AI model profiles", "test prompts/responses"],
        "risk_indicators":    ["no human-in-loop gate", "automated compliance decisions", "LLM-as-judge"],
        "backend":            "claude",
    }
    try:
        report = post("/evaluate/council", payload)
        print(color(f"  done ({time.time()-t1:.1f}s)", "32"))
    except urllib.error.HTTPError as e:
        print(color(f"\n  ✗ [{e.code}]: {e.read().decode()[:300]}", "31"))
        sys.exit(1)

    cd          = report.get("council_decision") or {}
    decision    = cd.get("final_recommendation", "?")
    consensus   = cd.get("consensus_level", "?")
    incident_id = report.get("incident_id", "?")
    note        = report.get("council_note", "")

    dc = {"APPROVE": "32", "REVIEW": "33", "REJECT": "31"}.get(decision, "37")
    print(f"\n  {'Decision':12s} {color(decision, dc)}")
    print(f"  {'Consensus':12s} {consensus}")
    print(f"  {'Incident ID':12s} {incident_id}")
    if note:
        print(f"\n  Council Note:\n  {note[:400]}")
    print(f"\n  View full report: http://localhost:5173/ → Dashboard → {incident_id}\n")


if __name__ == "__main__":
    main()
